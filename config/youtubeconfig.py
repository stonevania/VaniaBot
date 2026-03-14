###
# YOUTUBE CONFIG
###
# This file contains the configuration for the YouTube API integration.
# 

class YouTubeConfig:
    def __init__(
            self, 
            watched_channels: list[str] = None, 
            publish_channel: str = None, 
            polling_interval: int = 60):
        self.watched_channels = watched_channels or []
        self.publish_channel = publish_channel
        self.polling_interval = polling_interval

    def json(self) -> dict:
        return {
            "watched_channels": self.watched_channels,
            "publish_channel": self.publish_channel,
            "polling_interval": self.polling_interval
        }