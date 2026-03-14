from typing import List

class SocialConfig:
    def __init__(
            self, 
            enabled: bool = False,
            polling_interval: int = 60,
            upload_channel: int | None = None,
            live_channel: int | None = None,
            youtube_channels: List[dict] = None,
            twitch_channels: List[dict] = None):
        self.enabled = enabled
        self.polling_interval = polling_interval
        self.upload_channel = upload_channel
        self.live_channel = live_channel
        self.youtube_channels = youtube_channels
        self.twitch_channels = twitch_channels
