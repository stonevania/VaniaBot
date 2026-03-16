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
TWITCH_EVENTSUB_MAX_CHANNELS = 10

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
        self.polling_task = None
        self.eventsub_logins: set[str] = set()

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

    def twitch_request(self, method: str, url: str, **kwargs) -> requests.Response:
        response = requests.request(method, url, headers=self.twitch_headers, timeout=20, **kwargs)
        if response.status_code == 401 and self.refresh_token:
            self.taglog("Twitch", f"Twitch API request unauthorized, refreshing token and retrying [{url}]")
            self.refresh_access_token()
            response = requests.request(method, url, headers=self.twitch_headers, timeout=20, **kwargs)
        return response

    async def _notify_unexpected_twitch_state(self, message: str):
        reporting_channel_id = self.config.auto_moderation.reporting_channel

        if reporting_channel_id:
            channel = self.bot.get_channel(reporting_channel_id)
            if channel:
                try:
                    await channel.send(f"**ERROR**: {message}")
                    return
                except Exception as e:
                    self.taglog("Twitch", f"Failed to send auto-moderation alert: {e}")

        for guild in self.bot.guilds:
            owner = guild.owner or await guild.fetch_owner()
            if owner is None:
                continue

            try:
                await owner.send(f"VaniaBot detected an unexpected Twitch state in {guild.name}: {message}")
            except Exception as e:
                self.taglog("Twitch", f"Failed to DM guild owner for {guild.name}: {e}")

    def _schedule_unexpected_twitch_state_notification(self, message: str):
        try:
            asyncio.create_task(self._notify_unexpected_twitch_state(message))
        except RuntimeError as e:
            self.taglog("Twitch", f"Failed to schedule Twitch alert: {e}")

    async def start(self):
        self.taglog("Twtich", "Starting Twtich event sub service...")
        self.twitch_channels = self.social_config.twitch_channels or []
        self.channel_map = {}
        self.eventsub_logins = set()
        self.should_stop = False
        self.validate_token()
        self.resolve_users()
        self.polling_task = asyncio.create_task(self.poll_for_offline_channels())

        try:
            await self.run_forever()
        finally:
            if self.polling_task is not None:
                self.polling_task.cancel()
                self.polling_task = None
    
    async def stop(self) -> None:
        self.taglog("Twtich", "Stopping Twtich event sub service...")
        self.should_stop = True
        if self.polling_task is not None:
            self.polling_task.cancel()
            self.polling_task = None
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

    def refresh_access_token(self) -> str:
        if not self.refresh_token:
            message = "TWITCH_REFRESH_TOKEN is required to refresh the Twitch user access token."
            self._schedule_unexpected_twitch_state_notification(message)
            raise RuntimeError(message)

        try:
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
        except Exception as e:
            self._schedule_unexpected_twitch_state_notification(f"Failed to refresh Twitch access token [{e}]")
            raise

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
        try:
            response = requests.get(url, headers=headers, timeout=20)
            if response.status_code == 401 and self.refresh_token:
                self.taglog("Twitch", "Twitch user token expired or invalid, refreshing it...")
                self.refresh_access_token()
                headers["Authorization"] = f"OAuth {self.access_token}"
                response = requests.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            self._schedule_unexpected_twitch_state_notification(f"Failed to validate Twitch token [{e}]")
            raise
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

        response = self.twitch_request(
            "GET",
            f"{TWITCH_HELIX_BASE}/users",
            params=params,
        )
        response.raise_for_status()

        data = response.json().get("data", [])
        found = set()

        for user in data:
            user_login = user.get("login", None)
            user_id = user.get("id", None)
            user_display_name = user.get("display_name", None)

            if user_login is None or user_id is None or user_display_name is None:
                message = f"Malformed user data in Twitch users response [{response.json()}]"
                self._schedule_unexpected_twitch_state_notification(message)
                self.taglog("Twitch", message)
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
            message = f"Malformed user data in Twitch users response [{response.json()}]"
            self._schedule_unexpected_twitch_state_notification(message)
            self.taglog("Twitch", message)
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
                self._schedule_unexpected_twitch_state_notification(f"WebSocket loop error [{e}]")
                self.taglog("Twitch", f"WebSocket loop error [{e}]")
                await asyncio.sleep(5)

    def subscribe_all(self, session_id: str) -> None:
        self.eventsub_logins = set()

        for login, user in list(self.channel_map.items())[:TWITCH_EVENTSUB_MAX_CHANNELS]:
            broadcaster_user_id = user["id"]

            result = self.create_subscription(session_id, broadcaster_user_id, "stream.online")
            self.taglog("Twitch", f"Subscribed to stream.online for {login} ({broadcaster_user_id}): {result}...")
            self.eventsub_logins.add(login)

        overflow_logins = list(self.channel_map.keys())[TWITCH_EVENTSUB_MAX_CHANNELS:]
        if overflow_logins:
            self.taglog("Twitch", f"Using polling for Twitch channels beyond EventSub limit: {overflow_logins}")

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

        r = self.twitch_request(
            "POST",
            f"{TWITCH_HELIX_BASE}/eventsub/subscriptions",
            json=payload,
        )

        # Twitch may return 409 if the same subscription already exists.
        if r.status_code == 409:
            self.taglog("Twitch", f"Subscription already exists [{broadcaster_user_id} | {sub_type}]...")
            return {"status": "exists"}

        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            self._schedule_unexpected_twitch_state_notification(
                f"Failed to create Twitch subscription [{broadcaster_user_id} | {sub_type} | {r.status_code}]"
            )
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

    def save_live_notification(self, channel: dict, event: dict, discord_message_id: int | None = None) -> None:
        channel["last_live_notification"] = event
        if discord_message_id is not None:
            channel["last_live_message_id"] = discord_message_id
        self.social_config.register_new_content(channel)
        self.twitch_channels = self.social_config.twitch_channels or []
        self.set_config(self.config)

    def clear_live_notification(self, channel: dict) -> None:
        channel["last_live_notification"] = None
        channel["last_live_message_id"] = None
        self.social_config.register_new_content(channel)
        self.twitch_channels = self.social_config.twitch_channels or []
        self.set_config(self.config)

    def get_active_live_channels(self) -> list[dict]:
        return [
            channel for channel in (self.twitch_channels or [])
            if channel.get("last_live_notification") and channel.get("last_live_message_id")
        ]

    def get_polled_channels(self) -> list[dict]:
        polled_channels = []

        for channel in self.twitch_channels or []:
            channel_url = channel.get("url", "")
            login = urlparse(channel_url).path.strip("/").lower()
            if login and login not in self.eventsub_logins:
                polled_channels.append(channel)

        return polled_channels

    def get_live_streams(self, logins: list[str]) -> dict[str, dict]:
        live_streams: dict[str, dict] = {}

        for i in range(0, len(logins), 100):
            batch = logins[i:i + 100]
            params = [("user_login", login) for login in batch]
            response = self.twitch_request(
                "GET",
                f"{TWITCH_HELIX_BASE}/streams",
                params=params,
            )
            response.raise_for_status()

            for stream in response.json().get("data", []):
                login = (stream.get("user_login") or "").lower()
                if login:
                    live_streams[login] = stream

        return live_streams

    def get_live_stream(self, login: str) -> dict | None:
        if not login:
            return None

        response = self.twitch_request(
            "GET",
            f"{TWITCH_HELIX_BASE}/streams",
            params={"user_login": login}
        )
        response.raise_for_status()

        data = response.json().get("data", [])
        if not data:
            return None

        return data[0]

    async def sync_polled_channel_statuses(self) -> None:
        polled_channels = self.get_polled_channels()
        if not polled_channels:
            return

        logins = [
            urlparse(channel.get("url", "")).path.strip("/").lower()
            for channel in polled_channels
        ]
        live_streams = self.get_live_streams(logins)

        for channel, login in zip(polled_channels, logins):
            if not login:
                continue

            last_live_notification = channel.get("last_live_notification")

            if login in live_streams and not last_live_notification:
                stream = live_streams[login]
                event = {
                    "broadcaster_user_login": login,
                    "broadcaster_user_name": stream.get("user_name") or self.channel_map.get(login, {}).get("display_name", login),
                    "started_at": stream.get("started_at"),
                }
                self.taglog("Twitch", f"Polling detected new live for {channel.get('url', None)}, send a social notification!")
                content = self.format_online_message(event)
                message = await self.send_discord_message(content, event, is_live=True)
                if message:
                    self.save_live_notification(channel, event, message.id)
                continue

            if login not in live_streams and last_live_notification and channel.get("last_live_message_id"):
                content = self.format_offline_message(last_live_notification)
                self.taglog("Twitch", f"Offline poll detected [{content.replace('\n', ' | ')}]...")
                await self.update_discord_message(channel, content, last_live_notification)
                self.clear_live_notification(channel)

    async def poll_for_offline_channels(self) -> None:
        while not self.should_stop:
            try:
                await self.sync_polled_channel_statuses()

                active_channels = self.get_active_live_channels()
                eventsub_active_channels = [
                    channel for channel in active_channels
                    if urlparse(channel.get("url", "")).path.strip("/").lower() in self.eventsub_logins
                ]
                if eventsub_active_channels:
                    logins = [
                        urlparse(channel.get("url", "")).path.strip("/").lower()
                        for channel in eventsub_active_channels
                    ]
                    live_streams = self.get_live_streams(logins)

                    for channel, login in zip(eventsub_active_channels, logins):
                        if login and login not in live_streams:
                            last_live_notification = channel.get("last_live_notification") or {}
                            content = self.format_offline_message(last_live_notification)
                            self.taglog("Twitch", f"Offline poll detected [{content.replace('\n', ' | ')}]...")
                            await self.update_discord_message(channel, content, last_live_notification)
                            self.clear_live_notification(channel)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._schedule_unexpected_twitch_state_notification(f"Twitch offline polling error [{e}]")
                self.taglog("Twitch", f"Twitch offline polling error [{e}]")

            await asyncio.sleep(self.social_config.polling_interval or 60)

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
            self._schedule_unexpected_twitch_state_notification(f"Twitch subscription revoked [{sub}]")
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
                notification_started_at = last_live_notification.get("started_at", None) if last_live_notification else None

                if channel and event:
                    live_started_at = event.get("started_at", None)
                    if notification_started_at is None or notification_started_at != live_started_at:
                        self.taglog("Twitch", f"New live fetched for {channel.get('url', None)}, send a social notification!")
                        content = self.format_online_message(event)
                        message = await self.send_discord_message(content, event, is_live=True)
                        if message:
                            self.save_live_notification(channel, event, message.id if message else None)
                        return None

                self.taglog("Twitch", f"No new lives fetched for {channel.get('url', None) if channel else login}...")
                return None

            elif sub_type == "stream.offline":
                login = event.get("broadcaster_user_login", "").lower()
                channel = self.get_configured_channel(login)
                content = self.format_offline_message(event)
                self.taglog("Twitch", f"Offline event [{content.replace("\n", " | ")}]...")
                await self.update_discord_message(channel, content, event)
                if channel:
                    self.clear_live_notification(channel)

            else:
                self.taglog("Twitch", f"Unhandled notification type [{sub_type}]...")

            return None

        self.taglog("Twitch", f"Unhandled message type [{msg_type}]...")
        return None
    
    async def send_discord_message(self, content: str, event: dict | None = None, is_live: bool = True) -> discord.Message | None:
        live_channel_id = self.social_config.live_channel
        if not live_channel_id:
            message = "Live notification channel is not configured."
            self._schedule_unexpected_twitch_state_notification(message)
            self.taglog("Twitch", message)
            return None

        discord_channel = self.bot.get_channel(live_channel_id)
        if not discord_channel:
            message = f"Live notification channel with ID {live_channel_id} not found."
            self._schedule_unexpected_twitch_state_notification(message)
            self.taglog("Twitch", message)
            return None

        event = event or {}
        name = event.get("broadcaster_user_name", event.get("broadcaster_user_login", "Unknown"))
        login = event.get("broadcaster_user_login", "").lower()
        url = f"https://www.twitch.tv/{login}" if login else "https://www.twitch.tv"
        started_at = event.get("started_at")
        stream = None

        if is_live and login:
            try:
                stream = self.get_live_stream(login)
            except Exception as e:
                self.taglog("Twitch", f"Failed to fetch live stream details for {login}: {e}")

        embed = discord.Embed(
            description=content,
            color=discord.Color.purple() if is_live else discord.Color.dark_grey(),
            url=url
        )
        if is_live:
            stream_title = stream.get("title") if stream else None
            game_name = stream.get("game_name") if stream else None
            viewer_count = stream.get("viewer_count") if stream else None
            thumbnail_url = stream.get("thumbnail_url") if stream else None

            embed.title = stream_title or f"{name} is now live on Twitch"
            embed.set_author(name=name, url=url)
            if game_name:
                embed.add_field(name="Game", value=game_name, inline=True)
            if viewer_count is not None:
                embed.add_field(name="Viewers", value=str(viewer_count), inline=True)
            if thumbnail_url:
                embed.set_image(url=thumbnail_url.replace("{width}", "1280").replace("{height}", "720"))
        else:
            embed.title = f"{name} has gone offline"
            embed.set_author(name=name, url=url)

        if started_at:
            try:
                started_dt = discord.utils.parse_time(started_at)
                if started_dt:
                    embed.timestamp = started_dt
                    embed.set_footer(text="Started" if is_live else "Ended")
            except (ValueError, TypeError):
                pass
        elif is_live:
            embed.set_footer(text="Live now")

        role_id = self.social_config.live_notification_role if is_live else None
        message_content = f"<@&{role_id}>" if role_id else "@everyone"
        view = None

        if is_live and login:
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Watch Stream", url=url))

        try:
            return await discord_channel.send(
                content=message_content,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(roles=True, everyone=True),
                view=view
            )
        except Exception as e:
            self._schedule_unexpected_twitch_state_notification(f"Failed to send Twitch Discord notification [{e}]")
            raise

    async def update_discord_message(self, channel: dict | None, content: str, event: dict | None = None) -> None:
        if not channel:
            message = "Offline event received for an unconfigured channel."
            self._schedule_unexpected_twitch_state_notification(message)
            self.taglog("Twitch", message)
            return

        live_channel_id = self.social_config.live_channel
        if not live_channel_id:
            message = "Live notification channel is not configured."
            self._schedule_unexpected_twitch_state_notification(message)
            self.taglog("Twitch", message)
            return

        discord_channel = self.bot.get_channel(live_channel_id)
        if not discord_channel:
            message = f"Live notification channel with ID {live_channel_id} not found."
            self._schedule_unexpected_twitch_state_notification(message)
            self.taglog("Twitch", message)
            return

        message_id = channel.get("last_live_message_id")
        if not message_id:
            message = f"No existing live notification message found for {channel.get('url', None)}."
            self._schedule_unexpected_twitch_state_notification(message)
            self.taglog("Twitch", message)
            return

        event = event or {}
        name = event.get("broadcaster_user_name", event.get("broadcaster_user_login", "Unknown"))
        login = event.get("broadcaster_user_login", "").lower()
        url = f"https://www.twitch.tv/{login}" if login else "https://www.twitch.tv"

        embed = discord.Embed(
            description=content,
            color=discord.Color.dark_grey(),
            url=url
        )
        embed.title = f"{name} has gone offline"
        embed.set_author(name=name, url=url)

        try:
            message = await discord_channel.fetch_message(message_id)
        except discord.NotFound:
            notify_message = f"Live notification message {message_id} was not found for {channel.get('url', None)}."
            self._schedule_unexpected_twitch_state_notification(notify_message)
            self.taglog("Twitch", notify_message)
            return

        try:
            await message.edit(
                content=None,
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none()
            )
        except Exception as e:
            self._schedule_unexpected_twitch_state_notification(f"Failed to update Twitch Discord notification [{e}]")
            raise

    def format_online_message(self, event: dict) -> str:
        login = event.get("broadcaster_user_login", "").lower()
        url = f"https://www.twitch.tv/{login}" if login else "https://www.twitch.tv"
        return url

    def format_offline_message(self, event: dict) -> str:
        name = event.get("broadcaster_user_name", event.get("broadcaster_user_login", "Unknown"))
        login = event.get("broadcaster_user_login", "").lower()
        url = f"https://www.twitch.tv/{login}" if login else "https://www.twitch.tv"
        return f"⚫ **{name}** has gone offline.\n{url}"
