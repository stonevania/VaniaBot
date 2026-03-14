from typing import List

class SocialConfig:
    def __init__(
            self, 
            enabled: bool = False,
            polling_interval: int = 60,
            upload_channel: int | None = None,
            live_channel: int | None = None,
            upload_notification_role: int | None = None,
            live_notification_role: int | None = None,
            youtube_channels: List[dict] = None,
            twitch_channels: List[dict] = None):
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
