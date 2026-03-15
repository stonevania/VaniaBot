import asyncio
import json
import logging
import os
import signal
import sys
from typing import Any, Dict, List, Optional, Set

import requests
import websockets

class Twitch:
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.social_config = bot.config.social_config
        self.taglog = bot.taglog
        self.set_config = bot.set_config
        
        # TODO: Do any twitch-specific setup here
        self.client_id = os.getenv("TWITCH_CLIENT_ID")
        self.access_token = os.getenv("TWITCH_USER_ACCESS_TOKEN")
        self.polling_task = None

    def start_polling(self):
        if self.polling_task is None or self.polling_task.done():
            self.polling_task = asyncio.create_task(self.begin_polling())

    async def begin_polling(self):
        self.taglog("Twitch", "Starting Twitch polling...")
        while True:
            try:
                await self.check_for_new_content()
            except Exception as e:
                self.taglog("Twitch", f"Error during polling: {e}")

            await asyncio.sleep(self.social_config.polling_interval or 60)

    async def check_for_new_content(self):
        print('not implemented yet')




# TWITCH_CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
# TWITCH_USER_ACCESS_TOKEN = os.environ["TWITCH_USER_ACCESS_TOKEN"]
# DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

# # The Twitch channel login names to monitor
# CHANNEL_LOGINS = [
#     "dadmannwalking",
#     "lynntfluffle",
#     # add the rest of your Stonevania streamers here
# ]

# TWITCH_EVENTSUB_WS_URL = "wss://eventsub.wss.twitch.tv/ws"
# TWITCH_HELIX_BASE = "https://api.twitch.tv/helix"

# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s [%(levelname)s] %(message)s"
# )


# class TwitchEventSubMonitor:
#     def __init__(self, channel_logins: List[str]) -> None:
#         self.channel_logins = sorted({c.lower() for c in channel_logins})
#         self.channel_map: Dict[str, Dict[str, str]] = {}
#         self.seen_message_ids: Set[str] = set()
#         self.should_stop = False
#         self.ws = None

#     @property
#     def twitch_headers(self) -> Dict[str, str]:
#         return {
#             "Authorization": f"Bearer {TWITCH_USER_ACCESS_TOKEN}",
#             "Client-Id": TWITCH_CLIENT_ID,
#             "Content-Type": "application/json",
#         }

#     def validate_token(self) -> None:
#         """
#         Optional but helpful startup check.
#         """
#         url = "https://id.twitch.tv/oauth2/validate"
#         headers = {
#             "Authorization": f"OAuth {TWITCH_USER_ACCESS_TOKEN}"
#         }
#         r = requests.get(url, headers=headers, timeout=20)
#         r.raise_for_status()
#         data = r.json()
#         logging.info("Validated Twitch token for login=%s client_id=%s", data.get("login"), data.get("client_id"))

#     def resolve_users(self) -> None:
#         """
#         Resolve Twitch login names to user IDs using Helix Get Users.
#         """
#         params = []
#         for login in self.channel_logins:
#             params.append(("login", login))

#         r = requests.get(
#             f"{TWITCH_HELIX_BASE}/users",
#             headers=self.twitch_headers,
#             params=params,
#             timeout=20,
#         )
#         r.raise_for_status()

#         data = r.json().get("data", [])
#         found = set()

#         for user in data:
#             login = user["login"].lower()
#             self.channel_map[login] = {
#                 "id": user["id"],
#                 "login": user["login"],
#                 "display_name": user["display_name"],
#             }
#             found.add(login)

#         missing = set(self.channel_logins) - found
#         if missing:
#             raise RuntimeError(f"Could not resolve Twitch users: {sorted(missing)}")

#         logging.info("Resolved %d Twitch users", len(self.channel_map))

#     def create_subscription(self, session_id: str, broadcaster_user_id: str, sub_type: str = "stream.online") -> Dict[str, Any]:
#         """
#         Create one EventSub subscription tied to the current WebSocket session.
#         """
#         payload = {
#             "type": sub_type,
#             "version": "1",
#             "condition": {
#                 "broadcaster_user_id": broadcaster_user_id
#             },
#             "transport": {
#                 "method": "websocket",
#                 "session_id": session_id
#             }
#         }

#         r = requests.post(
#             f"{TWITCH_HELIX_BASE}/eventsub/subscriptions",
#             headers=self.twitch_headers,
#             json=payload,
#             timeout=20,
#         )

#         # Twitch may return 409 if the same subscription already exists.
#         if r.status_code == 409:
#             logging.info("Subscription already exists for broadcaster_user_id=%s type=%s", broadcaster_user_id, sub_type)
#             return {"status": "exists"}

#         r.raise_for_status()
#         return r.json()

#     def subscribe_all(self, session_id: str) -> None:
#         """
#         Subscribe to all configured channels.
#         """
#         for login, user in self.channel_map.items():
#             broadcaster_user_id = user["id"]

#             result = self.create_subscription(session_id, broadcaster_user_id, "stream.online")
#             logging.info("Subscribed to stream.online for %s (%s): %s", login, broadcaster_user_id, result)

#             # Optional: also listen for stream.offline
#             result = self.create_subscription(session_id, broadcaster_user_id, "stream.offline")
#             logging.info("Subscribed to stream.offline for %s (%s): %s", login, broadcaster_user_id, result)

#     def send_discord_message(self, content: str) -> None:
#         """
#         Post a simple message to Discord via webhook.
#         """
#         payload = {"content": content}
#         r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=20)
#         r.raise_for_status()

#     def format_online_message(self, event: Dict[str, Any]) -> str:
#         name = event.get("broadcaster_user_name", event.get("broadcaster_user_login", "Unknown"))
#         login = event.get("broadcaster_user_login", "").lower()
#         url = f"https://www.twitch.tv/{login}" if login else "https://www.twitch.tv"
#         started_at = event.get("started_at", "unknown start time")
#         return f"🟣 **{name}** is now live on Twitch!\n{url}\nStarted: `{started_at}`"

#     def format_offline_message(self, event: Dict[str, Any]) -> str:
#         name = event.get("broadcaster_user_name", event.get("broadcaster_user_login", "Unknown"))
#         login = event.get("broadcaster_user_login", "").lower()
#         url = f"https://www.twitch.tv/{login}" if login else "https://www.twitch.tv"
#         return f"⚫ **{name}** has gone offline.\n{url}"

#     async def handle_message(self, message: str) -> Optional[str]:
#         payload = json.loads(message)
#         metadata = payload.get("metadata", {})
#         msg_type = metadata.get("message_type")
#         msg_id = metadata.get("message_id")

#         if msg_id:
#             if msg_id in self.seen_message_ids:
#                 logging.info("Skipping duplicate message_id=%s", msg_id)
#                 return None
#             self.seen_message_ids.add(msg_id)

#             # Prevent unbounded growth in a long-running process
#             if len(self.seen_message_ids) > 10000:
#                 self.seen_message_ids = set(list(self.seen_message_ids)[-5000:])

#         if msg_type == "session_welcome":
#             session = payload["payload"]["session"]
#             session_id = session["id"]
#             keepalive_timeout = session.get("keepalive_timeout_seconds")
#             logging.info("Received session_welcome session_id=%s keepalive_timeout=%s", session_id, keepalive_timeout)

#             self.subscribe_all(session_id)
#             return None

#         if msg_type == "session_keepalive":
#             logging.debug("Received keepalive")
#             return None

#         if msg_type == "session_reconnect":
#             session = payload["payload"]["session"]
#             reconnect_url = session.get("reconnect_url")
#             logging.warning("Received session_reconnect reconnect_url=%s", reconnect_url)
#             return reconnect_url

#         if msg_type == "revocation":
#             sub = payload["payload"].get("subscription", {})
#             logging.warning("Subscription revoked: %s", sub)
#             return None

#         if msg_type == "notification":
#             sub = payload["payload"].get("subscription", {})
#             event = payload["payload"].get("event", {})
#             sub_type = sub.get("type")

#             if sub_type == "stream.online":
#                 content = self.format_online_message(event)
#                 logging.info("Online event: %s", content.replace("\n", " | "))
#                 self.send_discord_message(content)

#             elif sub_type == "stream.offline":
#                 content = self.format_offline_message(event)
#                 logging.info("Offline event: %s", content.replace("\n", " | "))
#                 self.send_discord_message(content)

#             else:
#                 logging.info("Unhandled notification type=%s", sub_type)

#             return None

#         logging.info("Unhandled message type=%s", msg_type)
#         return None

#     async def run_forever(self, ws_url: str = TWITCH_EVENTSUB_WS_URL) -> None:
#         while not self.should_stop:
#             try:
#                 logging.info("Connecting to %s", ws_url)
#                 async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as websocket:
#                     self.ws = websocket

#                     async for raw_message in websocket:
#                         reconnect_url = await self.handle_message(raw_message)
#                         if reconnect_url:
#                             ws_url = reconnect_url
#                             logging.info("Switching to reconnect URL")
#                             break

#             except Exception as e:
#                 logging.exception("WebSocket loop error: %s", e)
#                 await asyncio.sleep(5)

#     def stop(self) -> None:
#         self.should_stop = True


# async def main() -> None:
    # monitor = TwitchEventSubMonitor(CHANNEL_LOGINS)

    # def _stop_handler(signum, frame):
    #     logging.info("Received signal %s, shutting down", signum)
    #     monitor.stop()

    # signal.signal(signal.SIGINT, _stop_handler)
    # signal.signal(signal.SIGTERM, _stop_handler)

    # monitor.validate_token()
    # monitor.resolve_users()
    # await monitor.run_forever()


# if __name__ == "__main__":
#     try:
#         asyncio.run(main())
#     except KeyboardInterrupt:
#         sys.exit(0)