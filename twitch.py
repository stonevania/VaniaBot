import asyncio
import dotenv
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import discord
import requests
import websockets

TWITCH_EVENTSUB_WS_URL = "wss://eventsub.wss.twitch.tv/ws"
TWITCH_HELIX_BASE = "https://api.twitch.tv/helix"

# # The Twitch channel login names to monitor. Will get these from config object
# CHANNEL_LOGINS = [
#     "dadmannwalking",
#     "lynntfluffle",
#     # add the rest of your Stonevania streamers here
# ]

class Twitch:
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.social_config = bot.config.social_config
        self.taglog = bot.taglog
        self.set_config = bot.set_config
        
        self.client_id = os.getenv("TWITCH_CLIENT_ID")
        self.client_secret = os.getenv("TWITCH_CLIENT_SECRET")
        self.refresh_token = os.getenv("TWITCH_REFRESH_TOKEN")
        self.access_token = self.fetch_access_token()

        self.channel_map: dict = {}
        self.twitch_channels = self.social_config.twitch_channels or []
        self.should_stop = False
        self.ws = None

        # signal.signal(signal.SIGINT, self._stop_handler)
        # signal.signal(signal.SIGTERM, self._stop_handler)

    @property
    def twitch_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Client-Id": self.client_id,
            "Content-Type": "application/json"
        }
    
    def _stop_handler(self, signum, frame):
        self.taglog("Twitch", f"Received signal {signum}, shutting down")
        self.stop()

    def _persist_tokens_to_env(self):
        script_dir = Path(__file__).parent
        file_path = script_dir / "../.env"
        dotenv.set_key(file_path, "TWITCH_USER_ACCESS_TOKEN", self.access_token)
        dotenv.set_key(file_path, "TWITCH_REFRESH_TOKEN", self.refresh_token)

    async def start(self):
        self.taglog("Twtich", "Starting Twtich event sub service...")
        self.should_stop = False
        self.validate_token()
        self.resolve_users()
        await self.run_forever()
    
    async def stop(self) -> None:
        self.taglog("Twtich", "Stopping Twtich event sub service...")
        self.should_stop = True
        if self.ws is not None:
            await self.ws.close()
        await asyncio.sleep(1)
    
    def fetch_access_token(self) -> str:
        user_access_token = os.getenv("TWITCH_USER_ACCESS_TOKEN") or os.getenv("TWITCH_ACCESS_TOKEN")
        if user_access_token:
            return user_access_token

        raise RuntimeError(
            "TWITCH_USER_ACCESS_TOKEN is required for Twitch EventSub WebSocket subscriptions."
        )

    def fetch_app_access_token(self) -> str:
        response = requests.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("access_token", None)

    def refresh_access_token(self) -> str:
        if not self.refresh_token:
            raise RuntimeError("TWITCH_REFRESH_TOKEN is required to refresh the Twitch user access token.")

        response = requests.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()

        self.access_token = data.get("access_token", self.access_token)
        self.refresh_token = data.get("refresh_token", self.refresh_token)

        os.environ["TWITCH_USER_ACCESS_TOKEN"] = self.access_token
        if self.refresh_token:
            os.environ["TWITCH_REFRESH_TOKEN"] = self.refresh_token

        self._persist_tokens_to_env()

        return self.access_token
    
    def validate_token(self):
        url = "https://id.twitch.tv/oauth2/validate"
        headers = {
            "Authorization": f"OAuth {self.access_token}"
        }
        response = requests.get(url, headers=headers, timeout=20)
        if response.status_code == 401 and self.refresh_token:
            self.taglog("Twitch", "Twitch user token expired or invalid, refreshing it...")
            self.refresh_access_token()
            headers["Authorization"] = f"OAuth {self.access_token}"
            response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()
        self.taglog("Twitch", f"Validated Twitch token for login={data.get("login")} client_id={data.get("client_id")}")

    def resolve_users(self):
        self.taglog("Twitch", f"Configuring list of channels to monitor...")

        users = set()
        params = []
        for channel in self.social_config.twitch_channels:
            channel_url = channel.get("url", None)
            username = urlparse(channel_url).path.split("/")[1]

            # Register username for tag logs later and add to parameters
            users.add(username)
            params.append(("login", username))

        response = requests.get(
            f"{TWITCH_HELIX_BASE}/users",
            headers=self.twitch_headers,
            params=params,
            timeout=20
        )
        response.raise_for_status()

        data = response.json().get("data", [])
        found = set()

        for user in data:
            user_login = user.get("login", None)
            user_id = user.get("id", None)
            user_display_name = user.get("display_name", None)

            if user_login is None or user_id is None or user_display_name is None:
                # TODO: Register error to automod channel or guild owner for visibility
                self.taglog("Twitch", f"Malformed user data in Twitch users response [{response.json()}]")
                return 
            
            user_login = user_login.lower()

            self.channel_map[user_login] = {
                "id": user_id,
                "login": user_login,
                "display_name": user_display_name
            }
            found.add(user_login)

        missing = users - found
        if missing and len(missing) > 0:
            # TODO: Register error to automod channel or guild owner for visibility
            self.taglog("Twitch", f"Malformed user data in Twitch users response [{response.json()}]")
            return 
        
        self.taglog("Twitch", f"Configured {len(found)} channels to monitor...")

    async def run_forever(self, ws_url: str = TWITCH_EVENTSUB_WS_URL) -> None:
        while not self.should_stop:
            try:
                self.taglog("Twitch", f"Connecting to {ws_url}...")
                async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as websocket:
                    self.ws = websocket

                    async for raw_message in websocket:
                        reconnect_url = await self.handle_message(raw_message)
                        if reconnect_url:
                            ws_url = reconnect_url
                            self.taglog("Twitch", f"Switching to reconnect URL {ws_url}...")
                            break

            except Exception as e:
                # TODO: Register error to automod channel or guild owner for visibility
                self.taglog("Twitch", f"WebSocket loop error [{e}]")
                await asyncio.sleep(5)

    def subscribe_all(self, session_id: str) -> None:
        for login, user in self.channel_map.items():
            broadcaster_user_id = user["id"]

            result = self.create_subscription(session_id, broadcaster_user_id, "stream.online")
            self.taglog("Twitch", f"Subscribed to stream.online for {login} ({broadcaster_user_id}): {result}...")

            # Optional: also listen for stream.offline
            result = self.create_subscription(session_id, broadcaster_user_id, "stream.offline")
            self.taglog("Twitch", f"Subscribed to stream.offline for {login} ({broadcaster_user_id}): {result}...")

    def create_subscription(self, session_id: str, broadcaster_user_id: str, sub_type: str = "stream.online") -> dict:
        payload = {
            "type": sub_type,
            "version": "1",
            "condition": {
                "broadcaster_user_id": broadcaster_user_id
            },
            "transport": {
                "method": "websocket",
                "session_id": session_id
            }
        }

        r = requests.post(
            f"{TWITCH_HELIX_BASE}/eventsub/subscriptions",
            headers=self.twitch_headers,
            json=payload,
            timeout=20,
        )

        # Twitch may return 409 if the same subscription already exists.
        if r.status_code == 409:
            self.taglog("Twitch", f"Subscription already exists [{broadcaster_user_id} | {sub_type}]...")
            return {"status": "exists"}

        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            raise requests.HTTPError(
                f"{e}. Twitch response: {r.text}",
                response=r
            ) from e
        return r.json()

    def get_configured_channel(self, login: str) -> dict | None:
        channel_url_suffix = f"/{login.lower()}"
        for channel in self.twitch_channels:
            channel_url = (channel.get("url") or "").rstrip("/").lower()
            if channel_url.endswith(channel_url_suffix):
                return channel
        return None

    def save_live_notification(self, channel: dict, event: dict) -> None:
        channel["last_live_notification"] = event
        self.social_config.register_new_content(channel)
        self.twitch_channels = self.social_config.twitch_channels or []
        self.set_config(self.config)

    async def handle_message(self, message: str) -> str | None:
        payload = json.loads(message)
        metadata = payload.get("metadata", {})
        msg_type = metadata.get("message_type")

        if msg_type == "session_welcome":
            session = payload["payload"]["session"]
            session_id = session["id"]
            keepalive_timeout = session.get("keepalive_timeout_seconds")
            self.taglog("Twitch", f"Received session_welcome [{session_id} | {keepalive_timeout}]")

            self.subscribe_all(session_id)
            return None

        if msg_type == "session_keepalive":
            self.taglog("Twitch", f"Received keepalive...")
            return None

        if msg_type == "session_reconnect":
            session = payload["payload"]["session"]
            reconnect_url = session.get("reconnect_url")
            self.taglog("Twitch", f"Received session_reconnect [{reconnect_url}]...")
            return reconnect_url

        if msg_type == "revocation":
            sub = payload["payload"].get("subscription", {})
            self.taglog("Twitch", f"Subscription revoked [{sub}]...")
            return None

        if msg_type == "notification":
            sub = payload["payload"].get("subscription", {})
            event = payload["payload"].get("event", {})
            sub_type = sub.get("type")

            if sub_type == "stream.online":
                login = event.get("broadcaster_user_login", "").lower()
                channel = self.get_configured_channel(login)
                last_live_notification = channel.get("last_live_notification", None) if channel else None

                if channel and event and not last_live_notification:
                    self.taglog("Twitch", f"First ever live fetched for {channel.get('url', None)}, log and do nothing...")
                    self.save_live_notification(channel, event)
                    return None

                if channel and last_live_notification and event:
                    notification_started_at = last_live_notification.get("started_at", None)
                    live_started_at = event.get("started_at", None)
                    if notification_started_at != live_started_at:
                        self.taglog("Twitch", f"New live fetched for {channel.get('url', None)}, send a social notification!")
                        content = self.format_online_message(event)
                        await self.send_discord_message(content, event, is_live=True)
                        self.save_live_notification(channel, event)
                        return None

                self.taglog("Twitch", f"No new lives fetched for {channel.get('url', None) if channel else login}...")
                return None

            elif sub_type == "stream.offline":
                content = self.format_offline_message(event)
                self.taglog("Twitch", f"Offline event [{content.replace("\n", " | ")}]...")
                await self.send_discord_message(content, event, is_live=False)

            else:
                self.taglog("Twitch", f"Unhandled notification type [{sub_type}]...")

            return None

        self.taglog("Twitch", f"Unhandled message type [{msg_type}]...")
        return None
    
    async def send_discord_message(self, content: str, event: dict | None = None, is_live: bool = True) -> None:
        live_channel_id = self.social_config.live_channel
        if not live_channel_id:
            self.taglog("Twitch", "Live notification channel is not configured.")
            return

        discord_channel = self.bot.get_channel(live_channel_id)
        if not discord_channel:
            self.taglog("Twitch", f"Live notification channel with ID {live_channel_id} not found.")
            return

        event = event or {}
        name = event.get("broadcaster_user_name", event.get("broadcaster_user_login", "Unknown"))
        login = event.get("broadcaster_user_login", "").lower()
        url = f"https://www.twitch.tv/{login}" if login else "https://www.twitch.tv"
        started_at = event.get("started_at")

        embed = discord.Embed(
            description=content,
            color=discord.Color.purple() if is_live else discord.Color.dark_grey(),
            url=url
        )
        embed.title = f"{name} is now live on Twitch" if is_live else f"{name} has gone offline"
        embed.set_author(name=name, url=url)

        if started_at:
            try:
                started_dt = discord.utils.parse_time(started_at)
                if started_dt:
                    embed.timestamp = started_dt
                    embed.set_footer(text="Started" if is_live else "Ended")
            except (ValueError, TypeError):
                pass

        role_id = self.social_config.live_notification_role if is_live else None
        message_content = f"<@&{role_id}>" if role_id else "@everyone"

        await discord_channel.send(
            content=message_content,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(roles=True, everyone=True)
        )

    def format_online_message(self, event: dict) -> str:
        name = event.get("broadcaster_user_name", event.get("broadcaster_user_login", "Unknown"))
        login = event.get("broadcaster_user_login", "").lower()
        url = f"https://www.twitch.tv/{login}" if login else "https://www.twitch.tv"
        started_at = event.get("started_at", "unknown start time")
        return f"🟣 **{name}** is now live on Twitch!\n{url}\nStarted: `{started_at}`"

    def format_offline_message(self, event: dict) -> str:
        name = event.get("broadcaster_user_name", event.get("broadcaster_user_login", "Unknown"))
        login = event.get("broadcaster_user_login", "").lower()
        url = f"https://www.twitch.tv/{login}" if login else "https://www.twitch.tv"
        return f"⚫ **{name}** has gone offline.\n{url}"
