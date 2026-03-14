from typing import List
from urllib.parse import parse_qs, urlparse

class SocialConfig:
    def __init__(
            self, 
            enabled: bool = False,
            polling_interval: int = 60,
            upload_channel: int | None = None,
            live_channel: int | None = None,
            upload_notification_role: int | None = None,
            live_notification_role: int | None = None,
            youtube_channels: List[dict] = [],
            twitch_channels: List[dict] = []):
        self.enabled = enabled
        self.polling_interval = polling_interval
        self.upload_channel = upload_channel
        self.upload_notification_role = upload_notification_role
        self.live_notification_role = live_notification_role
        self.live_channel = live_channel
        self.youtube_channels = youtube_channels
        self.twitch_channels = twitch_channels

    def json(self) -> dict:
        obj = {}
        obj["enabled"] = self.enabled
        obj["polling_interval"] = self.polling_interval
        obj["upload_channel"] = self.upload_channel
        obj["live_channel"] = self.live_channel
        obj["upload_notification_role"] = self.upload_notification_role
        obj["live_notification_role"] = self.live_notification_role
        obj["youtube_channels"] = self.youtube_channels
        obj["twitch_channels"] = self.twitch_channels
        return obj
    
    def set_enabled(self, enabled: bool, polling_interval: int = 60):
        self.enabled = enabled
        self.polling_interval = polling_interval

        if not enabled:
            self.upload_channel = None
            self.live_channel = None
            self.upload_notification_role = None
            self.live_notification_role = None
            self.youtube_channels = None
            self.twitch_channels = None

    def configure_upload_notifications(self, channel_id, role_id):
        self.upload_channel = channel_id
        self.upload_notification_role = role_id

    def configure_live_notifications(self, channel_id, role_id):
        self.live_channel = channel_id
        self.live_notification_role = role_id

    def _remove_channel_by_url(self, channels: List[dict], url: str) -> List[dict]:
        return [
            item for item in channels or []
            if item.get("url", None) != url
        ]

    # Handles configuring any given channel by determining the platform and then adding the 
    # channel to the json in the proper format.
    def configure_channel(self, url: str, enabled: bool, lives: bool) -> str:
        # If we're not enabling, we're disabling, so remove it if it exists
        if not enabled:
            old_channel_count = len(self.youtube_channels or []) + len(self.twitch_channels or [])
            self.youtube_channels = self._remove_channel_by_url(self.youtube_channels, url)
            self.twitch_channels = self._remove_channel_by_url(self.twitch_channels, url)
            new_channel_count = len(self.youtube_channels or []) + len(self.twitch_channels or [])

            if old_channel_count != new_channel_count:
                return f"Success: Channel `{url}` was removed."
            return f"Fail: Channel `{url}` is not currently monitored."
        
        # Otherwise, determine platform then overwrite the appropriate values if it exists
        # or add if it doesn't
        platform = self.get_url_platform(url)
        if platform == "youtube":
            if not self.youtube_channels:
                self.youtube_channels = []

            for channel in self.youtube_channels:
                # If the channel is already monitored, update its values
                if channel.get("url", None) == url:
                    channel["lives"] = lives
                    return f"Success: Updated `{url} [{channel}]`."
            
            # Otherwise, add it as a new channel
            channel_json = {
                "url": url,
                "lives": lives,
                "last_notification": None
            }
            self.youtube_channels.append(channel_json)
            return f"Success: Added `{url} [{channel_json}]`."
        
        if platform == "twitch":
            return "Fail: not implemented, yet"
        
        return f"Fail: Invalid platform [`{url}`]"

    def channel_list(self) -> str:
        length = len(self.twitch_channels or []) + len(self.youtube_channels or [])

        if length == 0:
            return "Not currently monitoring any channels. Add one by using the `configurechannel` command."

        message = f"Currently monitoring {length} channels: `"

        for channel in self.twitch_channels or []:
            message += f"\n{channel.get("url", None)}"

        for channel in self.youtube_channels or []:
            message += f"\n{channel.get("url", None)}"
            
            monitoring_lives = channel.get("lives", False)
            if monitoring_lives:
                message += " (also monitoring lives)"

        message += "`"

        return message

    def get_url_platform(self, url: str) -> str | None:
        parsed = urlparse(url.strip())
        hostname = (parsed.netloc or "").lower()
        path = parsed.path.strip("/")

        if hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            if path.startswith(("@", "channel/", "c/", "user/", "shorts/", "live/")):
                return "youtube"

            if path == "watch" and parse_qs(parsed.query).get("v"):
                return "youtube"

        if hostname == "youtu.be" and path:
            return "youtube"

        if hostname in {"twitch.tv", "www.twitch.tv", "m.twitch.tv"} and path:
            first_segment = path.split("/")[0]
            if first_segment and first_segment not in {"directory", "downloads", "jobs", "p"}:
                return "twitch"

        return None

    def confirm_url(self, url: str) -> bool:
        return self.get_url_platform(url) is not None
    
    def register_new_upload(self, channel: dict, platform: str):
        channel_url = channel.get("url", None)

        if platform == "youtube":
           self.youtube_channels = [
                channel if item.get("url") == channel_url else item
                for item in self.youtube_channels or []
            ]

        if platform == "twitch":
            print("not implemented yet")