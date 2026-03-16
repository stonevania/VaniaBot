from typing import List
from urllib.parse import parse_qs, urlparse, urlunparse

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

    def configure_upload_notifications(self, channel_id, role_id):
        self.upload_channel = channel_id
        self.upload_notification_role = role_id

    def configure_live_notifications(self, channel_id, role_id):
        self.live_channel = channel_id
        self.live_notification_role = role_id

    def _remove_channel_by_url(self, channels: List[dict], url: str) -> List[dict]:
        normalized_url = self.normalize_url(url)
        return [
            item for item in channels or []
            if self.normalize_url(item.get("url", "")) != normalized_url
        ]

    # Handles configuring any given channel by determining the platform and then adding the 
    # channel to the json in the proper format.
    def configure_channel(self, url: str, enabled: bool, lives: bool) -> str:
        normalized_url = self.normalize_url(url)

        # If we're not enabling, we're disabling, so remove it if it exists
        if not enabled:
            old_channel_count = len(self.youtube_channels or []) + len(self.twitch_channels or [])
            self.youtube_channels = self._remove_channel_by_url(self.youtube_channels, normalized_url)
            self.twitch_channels = self._remove_channel_by_url(self.twitch_channels, normalized_url)
            new_channel_count = len(self.youtube_channels or []) + len(self.twitch_channels or [])

            if old_channel_count != new_channel_count:
                return f"Success: Channel `{normalized_url}` was removed."
            return f"Fail: Channel `{normalized_url}` is not currently monitored."
        
        # Otherwise, determine platform then overwrite the appropriate values if it exists
        # or add if it doesn't
        platform = self.get_url_platform(normalized_url)
        if platform == "youtube":
            if not self.youtube_channels:
                self.youtube_channels = []

            for channel in self.youtube_channels:
                # If the channel is already monitored, update its values
                if self.normalize_url(channel.get("url", "")) == normalized_url:
                    channel["lives"] = lives
                    channel["url"] = normalized_url
                    return f"Success: Updated `{normalized_url} [{channel}]`."
            
            # Otherwise, add it as a new channel
            channel_json = {
                "url": normalized_url,
                "lives": lives,
                "channel_id": None,
                "uploads_playlist_id": None,
                "channel_title": None,
                "channel_image_url": None,
                "last_live_notification": None,
                "last_video_notification": None,
                "last_live_message_id": None
            }
            self.youtube_channels.append(channel_json)
            return f"Success: Added `{normalized_url} [{channel_json}]`."
        
        if platform == "twitch":
            if not self.twitch_channels:
                self.twitch_channels = []

            for channel in self.twitch_channels:
                # If the channel is already monitored, there's nothing to do but return a failure
                if self.normalize_url(channel.get("url", "")) == normalized_url:
                    return f"Fail: Channel is already monitored `{normalized_url} [{channel}]`."
            
            # Otherwise, add it as a new channel
            channel_json = {
                "url": normalized_url,
                "last_live_notification": None,
                "last_video_notification": None,
                "last_live_message_id": None
            }
            self.twitch_channels.append(channel_json)
            return f"Success: Added `{normalized_url} [{channel_json}]`."
        
        return f"Fail: Invalid platform [`{normalized_url}`]"

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

    def normalize_url(self, url: str) -> str:
        parsed = urlparse(url.strip())
        hostname = (parsed.netloc or "").lower()
        path = parsed.path.rstrip("/")
        query = parsed.query

        normalized_url = url.strip().rstrip("/")
        platform = self.get_url_platform(normalized_url)
        if platform == "twitch":
            login = path.strip("/").split("/")[0].lower()
            return f"https://www.twitch.tv/{login}"

        if platform == "youtube":
            if hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
                if path.startswith("/@"):
                    return f"https://www.youtube.com/{path.strip('/').lower()}"
                if path.startswith("/channel/") or path.startswith("/user/") or path.startswith("/c/"):
                    segments = path.strip("/").split("/")
                    return f"https://www.youtube.com/{'/'.join(segment.lower() for segment in segments)}"
                if path == "/watch" and query:
                    video_ids = parse_qs(query).get("v", [])
                    if video_ids:
                        return f"https://www.youtube.com/watch?v={video_ids[0]}"
                return urlunparse(("https", "www.youtube.com", path, "", query, "")).rstrip("/")

            if hostname == "youtu.be":
                return urlunparse(("https", "youtu.be", path, "", query, "")).rstrip("/")

        return normalized_url

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
        return self.get_url_platform(self.normalize_url(url)) is not None
    
    def register_new_content(self, channel: dict):
        channel_url = channel.get("url", None)
        platform = self.get_url_platform(channel_url)

        if platform == "youtube":
           self.youtube_channels = [
                channel if item.get("url") == channel_url else item
                for item in self.youtube_channels or []
            ]

        if platform == "twitch":
           self.twitch_channels = [
                channel if item.get("url") == channel_url else item
                for item in self.twitch_channels or []
            ]
