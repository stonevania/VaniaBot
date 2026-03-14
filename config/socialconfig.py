import os

from config.youtubeconfig import YouTubeConfig

class SocialConfig:
    def __init__(
            self, 
            enabled: bool = False, 
            youtube_config: YouTubeConfig = None):
        self.enabled = enabled
        self.youtube_config = youtube_config