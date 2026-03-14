
from typing import List, Optional
import discord

from config.serviceconfig import ServiceConfig
from logs import taglog

class PluggingConfig:
    def __init__(
            self,
            enabled: bool = False,
            watched_channels: Optional[List[str]] = None,
            watched_users: Optional[List[str]] = None,
            keywords: Optional[List[str]] = None,
            twitter: Optional[ServiceConfig] = None,
            bluesky: Optional[ServiceConfig] = None,
            facebook: Optional[ServiceConfig] = None,
            reddit: Optional[ServiceConfig] = None,
            instagram: Optional[ServiceConfig] = None):
        self.enabled = enabled
        self.watched_channels = watched_channels or []
        self.watched_users = watched_users or []
        self.keywords = keywords or []
        self.twitter = twitter
        self.bluesky = bluesky
        self.facebook = facebook
        self.reddit = reddit
        self.instagram = instagram

    def json(self) -> dict:
        obj = {}
        obj["enabled"] = self.enabled
        obj["watched_channels"] = self.watched_channels
        obj["watched_users"] = self.watched_users
        obj["keywords"] = self.keywords

        if self.twitter:
            obj["twitter"] = self.twitter.json()
        if self.bluesky:
            obj["bluesky"] = self.bluesky.json()
        if self.facebook:
            obj["facebook"] = self.facebook.json()
        if self.reddit:
            obj["reddit"] = self.reddit.json()
        if self.instagram:
            obj["instagram"] = self.instagram.json()

        return obj
    
    def confirm(self, message: discord.Message, test_string: str, ignore_channels=False) -> bool:
        if message.author.name == "VaniaBot":
            taglog("CONFIG", "ignore messages from bot")
            return False

        if self.watched_users != [] and message.author.id not in self.watched_users:
            taglog("CONFIG", f"ignore messages from non-watched user {message.author.name}")
            return False

        if not ignore_channels and message.channel.id not in self.watched_channels:
            taglog("CONFIG", f"ignore messages from unmonitored channel {message.channel.name}")
            return False

        if self.keywords != [] and any(keyword not in test_string for keyword in self.keywords):
            taglog("CONFIG", "ignore message without key phrases")
            return False

        return True

