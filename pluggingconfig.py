from typing import List, Optional
import base64
import re
import discord
import json

from serviceconfig import ServiceConfig
from logs import taglog
import bluesky as bluesky

class PluggingConfig:
    def __init__(
            self,
            enabled: bool = False,
            watched_channels: Optional[List[str]] = None,
            watched_users: Optional[List[str]] = None,
            keywords: Optional[List[str]] = None,
            twitter_config: Optional[ServiceConfig] = None,
            bluesky_config: Optional[ServiceConfig] = None,
            facebook_config: Optional[ServiceConfig] = None,
            reddit_config: Optional[ServiceConfig] = None,
            instagram_config: Optional[ServiceConfig] = None):
        self.enabled = enabled
        self.watched_channels = watched_channels or []
        self.watched_users = watched_users or []
        self.keywords = keywords or []
        self.twitter_config = twitter_config
        self.bluesky_config = bluesky_config
        self.facebook_config = facebook_config
        self.reddit_config = reddit_config
        self.instagram_config = instagram_config

    def json(self) -> dict:
        obj = {}
        obj["enabled"] = self.enabled
        obj["watched_channels"] = self.watched_channels
        obj["watched_users"] = self.watched_users
        obj["keywords"] = self.keywords

        if self.twitter_config:
            obj["twitter"] = self.twitter_config.json()
        if self.bluesky_config:
            obj["bluesky"] = self.bluesky_config.json()
        if self.facebook_config:
            obj["facebook"] = self.facebook_config.json()
        if self.reddit_config:
            obj["reddit"] = self.reddit_config.json()
        if self.instagram_config:
            obj["instagram"] = self.instagram_config.json()

        return obj
    
    def confirm(self, message: discord.Message, test_string: str, ignore_channels=False) -> bool:
        if message.author.name == "VaniaBot":
            taglog("PLUGGINGCONFIG", "ignore messages from bot")
            return False

        if self.watched_users != [] and message.author.id not in self.watched_users:
            taglog("PLUGGINGCONFIG", f"ignore messages from non-watched user {message.author.name}")
            return False

        if not ignore_channels and message.channel.id not in self.watched_channels:
            taglog("PLUGGINGCONFIG", f"ignore messages from unmonitored channel {message.channel.name}")
            return False

        if self.keywords != [] and any(keyword not in test_string for keyword in self.keywords):
            taglog("PLUGGINGCONFIG", "ignore message without key phrases")
            return False

        return True
    
    def enable_service(self, service_name: str, username: str, password: str):
        new_service_config = ServiceConfig(service_name, True, username, base64.b64encode(password.encode()).decode())

        if service_name == "twitter":
            self.twitter_config = new_service_config
        elif service_name == "bluesky":
            self.bluesky_config = new_service_config
        elif service_name == "facebook":
            self.facebook_config = new_service_config
        elif service_name == "reddit":
            self.reddit_config = new_service_config
        elif service_name == "instagram":
            self.instagram_config = new_service_config
        else:
            taglog("PLUGGINGCONFIG", f"Unknown service name: {service_name}")

    def disable_service(self, service_name: str):
        new_service_config = ServiceConfig(service_name, False, None, None)

        if service_name == "twitter":
            self.twitter_config = new_service_config
        elif service_name == "bluesky":
            self.bluesky_config = new_service_config
        elif service_name == "facebook":
            self.facebook_config = new_service_config
        elif service_name == "reddit":
            self.reddit_config = new_service_config
        elif service_name == "instagram":
            self.instagram_config = new_service_config
        else:
            taglog("PLUGGINGCONFIG", f"Unknown service name: {service_name}")
    
    def message_json(self, message: discord.Message) -> dict:
        attachments = []
        embeds = []
        mentions = []
        role_mentions = []
        channel_mentions = []

        for attachment in message.attachments:
            attachment_payload = []
            attachment_payload["id"] = attachment.id
            attachment_payload["filename"] = attachment.filename
            attachment_payload["content_type"] = attachment.content_type
            attachment_payload["size"] = attachment.size
            attachment_payload["url"] = attachment.url
            attachment_payload["proxy_url"] = attachment.proxy_url
            attachment_payload["height"] = attachment.height
            attachment_payload["width"] = attachment.width
            attachment_payload["description"] = attachment.description
            attachments.append(attachment_payload)

        for embed in message.embeds:
            if embed:
                embed_payload = {}
                embed_payload["url"] = embed.url
                embed_payload["description"] = embed.description
                embed_payload["title"] = embed.title
                embed_payload["author"] = embed.author.name
                embed_payload["image_url"] = embed.image.url
                embed_payload["thumbnail_url"] = embed.thumbnail.url
                embed_payload["footer_text"] = embed.footer.text
                embed_payload["footer_icon_url"] = embed.footer.icon_url
                embed_payload["video_url"] = embed.video.url
                embeds.append(embed_payload)

        for mention in message.mentions:
            mention_payload = {}
            mention_payload["id"] = mention.id
            mention_payload["name"] = mention.name
            mention_payload["discriminator"] = mention.discriminator
            mention_payload["display_name"] = mention.display_name
            mention_payload["global_name"] = mention.global_name
            mention_payload["bot"] = mention.bot
            mention_payload["mention"] = mention.mention
            mentions.append(mention_payload)

        for mention in message.role_mentions:
            mention_payload = {}
            mention_payload["id"] = mention.id
            mention_payload["name"] = mention.name
            mention_payload["mention"] = mention.mention
            mention_payload["position"] = mention.position
            mention_payload["mentionable"] = mention.mentionable
            mention_payload["hoist"] = mention.hoist
            mention_payload["managed"] = mention.managed
            role_mentions.append(mention_payload)

        for mention in message.channel_mentions:
            mention_payload = {}
            mention_payload["id"] = mention.id
            mention_payload["name"] = mention.name
            mention_payload["mention"] = mention.mention
            mention_payload["created_at"] = str(mention.created_at)
            mention_payload["guild"] = mention.guild.id
            mention_payload["category"] = mention.category.id
            channel_mentions.append(mention_payload)
        
        payload = {}
        payload["content"] = message.content
        payload["author"] = message.author.name
        payload["channel_id"] = message.channel.id
        payload["guild_id"] = message.guild.id
        payload["id"] = message.id
        payload["type"] = message.type.name
        payload["attachments"] = attachments
        payload["embeds"] = embeds
        payload["mentions"] = mentions
        payload["role_mentions"] = role_mentions
        payload["channel_mentions"] = channel_mentions

        return json.dumps(payload)
    
    def title_from_message_json(self, data: dict) -> str:
        post_title = "Untitled Post"
        embeds = data.get("embeds", [])
        content = data.get("content", "")

        # --- Twitch Stream Detected ---
        if embeds and "twitch.tv" in (embeds[0].get("url") or ""):
            # Extract user from 'author' field if possible
            embed_author = embeds[0].get("author", "")
            user = embed_author.replace(" is live on Twitch", "").strip() if "is live on Twitch" in embed_author else embed_author
            
            # Fallback to parsing from content if needed
            if not user and "**" in content:
                user = content.split("**")[1]

            if user:
                post_title = f"{user} is live!"

        # --- YouTube Video Detected ---
        elif embeds and "youtu" in (embeds[0].get("url") or ""):
            embed_author = embeds[0].get("author", "")
            if "published a new video" in embed_author:
                user = embed_author.split(" published a new video")[0].strip()
                post_title = f"{user} uploaded a video!"
        
        # --- Fallback for plain content detection ---
        elif "just posted a new video" in content:
            # Example: "**ThatOneGuyJames** just posted a new video!"
            user = content.split("**")[1] if "**" in content else "Unknown"
            post_title = f"{user} uploaded a video!"

        return post_title

    async def description_from_json(data: dict, message: discord.Message) -> str:
        embeds = data.get("embeds", [])

        if embeds and embeds[0].get("title"):
            return embeds[0]["title"]

        content = data.get("content", message.content or "")

        # Sanitize @everyone and @here
        content = re.sub(r"@everyone", "everyone", content)
        content = re.sub(r"@here", "here", content)

        # Replace channel mentions
        def replace_channel(match):
            channel_id = int(match.group(1))
            channel = message.guild.get_channel(channel_id)
            return f"#{channel.name}" if channel else "#channel"

        content = re.sub(r"<#(\d+)>", replace_channel, content)

        # Replace role mentions
        def replace_role(match):
            role_id = int(match.group(1))
            role = message.guild.get_role(role_id)
            return f"@{role.name}" if role else "@role"

        content = re.sub(r"<@&(\d+)>", replace_role, content)

        # Replace user mentions
        async def replace_user(match):
            user_id = int(match.group(1))
            member = message.guild.get_member(user_id) or await message.guild.fetch_member(user_id)
            return f"@{member.display_name}" if member else "@user"

        # Process <@123> and <@!123> mentions one by one
        user_mention_pattern = r"<@!?(\d+)>"
        matches = list(re.finditer(user_mention_pattern, content))

        for match in reversed(matches):
            replacement = await replace_user(match)
            start, end = match.span()
            content = content[:start] + replacement + content[end:]

        return content.strip()

    def url_from_json(data: dict) -> str:
        url_pattern = re.compile(r"https?://[^\s)>\]]+")
        
        embeds = data.get("embeds", [])
        content = data.get("content", "")
        url = ""

        # Check embeds first
        if embeds and embeds[0].get("url"):
            url = embeds[0]["url"]

        # If no URL from embeds, search content
        if not url:
            match = url_pattern.search(content)
            if match:
                url = match.group(0)

        return url

    def thumbnail_url_from_json(data: dict) -> str:
        embeds = data.get("embeds", [])
        content = data.get("content", "")
        img_url = ""

        if embeds:
            embed = embeds[0]
            url = embed.get("url", "") or ""
            
            # Step 1: image_url
            if embed.get("image_url"):
                img_url = embed["image_url"]

            # Step 2: thumbnail_url
            elif embed.get("thumbnail_url"):
                img_url = embed["thumbnail_url"]

            # Step 3: Construct YouTube thumbnail from URL
            elif embed.get("url") and "youtu" in embed["url"]:
                match = youtube_pattern.search(embed["url"])
                if match:
                    video_id = match.group(1)
                    img_url = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
            
            # Step 4: Construct Twitch thumbnail from URL
            elif "twitch.tv" in url:
                # Extract username from URL
                match = re.search(r"twitch\.tv/([\w\d_]+)", url)
                if match:
                    username = match.group(1).lower()
                    img_url = f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{username}-880x496.jpg"

        return img_url

    async def send_to_social_networks(self, message: discord.Message, ctx):
        if not self.enabled:
            taglog("PLUGGINGCONFIG", "Plugging is disabled, not posting message")
            return
        
        data = self.message_json(message)
        post_title = self.title_from_message_json(data)
        post_description = await self.description_from_json(data, message)
        post_url = self.url_from_json(data)
        post_thumbnail_url = self.thumbnail_url_from_json(data)

        if self.twitter_config and self.twitter_config.enabled:
            taglog("PLUGGINGCONFIG", "Twitter enabled, but funtionality has not been added yet...")
            return

        if self.bluesky_config and self.bluesky_config.enabled:
            return await self.send_to_bluesky(message, ctx)

        if self.facebook_config and self.facebook_config.enabled:
            taglog("PLUGGINGCONFIG", "Facebook enabled, but funtionality has not been added yet...")
            return

        if self.reddit_config and self.reddit_config.enabled:
            taglog("PLUGGINGCONFIG", "Reddit enabled, but funtionality has not been added yet...")
            return

        if self.instagram_config and self.instagram_config.enabled:
            taglog("PLUGGINGCONFIG", "Instagram enabled, but funtionality has not been added yet...")
            return

    async def test_social_network(self, message: discord.Message, ctx, service: str):
        if not self.enabled:
            taglog("PLUGGINGCONFIG", "Plugging is disabled, not posting message")
            return
        
        data = self.message_json(message)
        post_title = self.title_from_message_json(data)
        post_description = await self.description_from_json(data, message)
        post_url = self.url_from_json(data)
        post_thumbnail_url = self.thumbnail_url_from_json(data)

        if service == "twitter" and self.twitter_config and self.twitter_config.enabled:
            taglog("PLUGGINGCONFIG", "Twitter enabled, but funtionality has not been added yet...")
            return

        if service == "bluesky" and self.bluesky_config and self.bluesky_config.enabled:
            return await self.send_to_bluesky(message, ctx)

        if service == "facebook" and self.facebook_config and self.facebook_config.enabled:
            taglog("PLUGGINGCONFIG", "Facebook enabled, but funtionality has not been added yet...")
            return

        if service == "reddit" and self.reddit_config and self.reddit_config.enabled:
            taglog("PLUGGINGCONFIG", "Reddit enabled, but funtionality has not been added yet...")
            return

        if service == "instagram" and self.instagram_config and self.instagram_config.enabled:
            taglog("PLUGGINGCONFIG", "Instagram enabled, but funtionality has not been added yet...")
            return