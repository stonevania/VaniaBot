import asyncio
import os
import discord

from datetime import datetime
from googleapiclient.discovery import build
from urllib.parse import urlparse

class YouTube:
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.social_config = bot.config.social_config
        self.taglog = bot.taglog
        self.set_config = bot.set_config

        self.api_key = os.getenv("YOUTUBE_API_KEY")
        self.youtube = build("youtube", "v3", developerKey=self.api_key)
        self.polling_task = None

    def start_polling(self):
        if self.polling_task is None or self.polling_task.done():
            self.polling_task = asyncio.create_task(self.begin_polling())

    async def begin_polling(self):
        self.taglog("YouTube", "Starting YouTube polling...")
        while True:
            try:
                await self.check_for_new_videos()
            except Exception as e:
                self.taglog("YouTube", f"Error during polling: {e}")

            await asyncio.sleep(self.social_config.polling_interval or 60)

    def _search_for_channel_id(self, query: str, expected_custom_url: str | None = None) -> str | None:
        self.taglog("YouTube", f"Searching for channel id with query {query}...")

        resp = self.youtube.search().list(
            q=query,
            type="channel",
            part="snippet",
            maxResults=5
        ).execute()

        items = resp.get("items", [])
        if not items:
            return None

        channel_ids = [item["snippet"]["channelId"] for item in items if item.get("snippet", {}).get("channelId")]
        if not channel_ids:
            return None

        if expected_custom_url:
            details = self.youtube.channels().list(
                part="snippet",
                id=",".join(channel_ids)
            ).execute()

            expected = expected_custom_url.removeprefix("@").lower()
            for channel in details.get("items", []):
                custom_url = (channel.get("snippet", {}).get("customUrl") or "").removeprefix("@").lower()
                if custom_url == expected:
                    return channel.get("id")

        return channel_ids[0]

    def get_channel_id(self, url: str) -> str | None:
        path = urlparse(url).path
        self.taglog("YouTube", f"Getting channel id from {url}...")

        # Case 1: already contains channel id
        if path.startswith("/channel/"):
            return path.split("/")[2]

        # Case 2: handle @handle URLs
        if path.startswith("/@"):
            handle = path[2:]
            self.taglog("YouTube", f"Looking up channel id with forHandle for {handle}...")

            resp = self.youtube.channels().list(
                part="id",
                forHandle=handle
            ).execute()

            items = resp.get("items", [])
            if items:
                return items[0].get("id")

            self.taglog("YouTube", f"No exact handle match for {handle}, falling back to search.")
            channel_id = self._search_for_channel_id(f"@{handle}", expected_custom_url=handle)
            if channel_id is None:
                self.taglog("YouTube", f"No channel found for handle {handle}.")
            return channel_id

        # Case 3: custom URL /c/ or /user/
        path_parts = [part for part in path.split("/") if part]
        if len(path_parts) < 2:
            self.taglog("YouTube", f"Unsupported YouTube URL format: {url}")
            return None

        kind = path_parts[0]
        name = path_parts[1]

        if kind == "user":
            resp = self.youtube.channels().list(
                part="id",
                forUsername=name
            ).execute()

            items = resp.get("items", [])
            if not items:
                self.taglog("YouTube", f"No channel found for username {name}.")
                return None

            return items[0].get("id")

        channel_id = self._search_for_channel_id(name, expected_custom_url=name if kind == "c" else None)
        if channel_id is None:
            self.taglog("YouTube", f"No channel found for custom URL name {name}.")
        return channel_id

    def get_playlist_id(self, channel_id: str) -> str | None:
        self.taglog("YouTube", f"Getting latest upload playlist for {channel_id}...")

        # Example response found in .ref/youtube.channelListResponse.json
        response = self.youtube.channels().list(
            part="contentDetails",
            id=channel_id
        ).execute()

        items = response.get("items", [])
        if not items:
            # TODO: If we get here, something probably changed, so this error should be more visible.
            self.taglog("YouTube", f"Channel not found: {channel_id}")
            return None

        if len(items) == 0:
            self.taglog("YouTube", "Channel has no playlists")
            return None
        
        # TODO: Is there a safer way to get to this data?
        return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    
    # Example response found in .ref/youtube.playlistItemListResponse.json
    def get_latest_upload(self, uploads_playlist_id: str) -> dict | None:
        response = self.youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=1
        ).execute()
  
        items = response.get("items", [])
        if not items:
            # TODO: If we get here, something probably changed, so this error should be more visible.
            self.taglog("YouTube", f"Channel not found: {uploads_playlist_id}")
            return None
        
        if len(items) == 0:
            self.taglog("YouTube", "Playlist has no items")
            return None

        return items[0]
    
    async def check_for_new_videos(self):
        self.taglog("YouTube", "Checking for new content on monitored YouTube channels...")

        for channel in self.social_config.youtube_channels or []:
            channel_url = channel.get("url", None)
            channel_id = self.get_channel_id(channel_url)
            if channel_id is None:
                # TODO: If we get here, something probably changed, so this error should be more visible.
                self.taglog("YouTube", f"Channel ID not found: {channel_id}")
                continue

            playlist_id = self.get_playlist_id(channel_id)
            latest_upload = self.get_latest_upload(playlist_id)
            last_notification = channel.get("last_notification", None)

            # Don't send upload notificaiton as this is the first time we are fetching a new upload,
            # BUT we should set this so that the next time we come through and find a different ID, we
            # DO send an upload notification.
            if latest_upload and not last_notification:
                self.taglog("YouTube", f"First ever upload fetched for {channel_url}, log and do nothing...")
                channel["last_notification"] = latest_upload
                self.social_config.register_new_upload(channel, "youtube")
                self.set_config(self.config)
                continue
            
            if last_notification and last_notification.get("id", None) != latest_upload.get("id", None):
                self.taglog("YouTube", f"New upload fetched for {channel_url}, send a social notification!")
                if await self.post_to_discord(latest_upload, channel_url):
                    channel["last_notification"] = latest_upload
                    self.social_config.register_new_upload(channel, "youtube")
                    self.set_config(self.config)
                    continue
                continue
            
            self.taglog("YouTube", f"No new uploads fetched for {channel_url}...")
    
    async def post_to_discord(self, upload: dict, channel_url: str) -> bool:
        upload_channel_id = self.social_config.upload_channel
        if upload_channel_id:
            discord_channel = self.bot.get_channel(upload_channel_id)
            if discord_channel:
                snippet = upload.get("snippet", {})
                video_id = (
                    upload.get("contentDetails", {}).get("videoId")
                    or snippet.get("resourceId", {}).get("videoId")
                )
                channel_title = snippet.get("channelTitle", channel_url)
                video_title = snippet.get("title", "New upload")
                video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else channel_url
                thumbnails = snippet.get("thumbnails", {})
                image_url = (
                    thumbnails.get("maxres", {}).get("url")
                    or thumbnails.get("standard", {}).get("url")
                    or thumbnails.get("high", {}).get("url")
                    or thumbnails.get("medium", {}).get("url")
                    or thumbnails.get("default", {}).get("url")
                )
                published_at = snippet.get("publishedAt")
                role_id = self.social_config.upload_notification_role
                role_mention = f"<@&{role_id}>" if role_id else "@everyone"

                embed = discord.Embed(
                    description=f"**{channel_title}** published a new video on YouTube",
                    color=discord.Color.red(),
                    url=video_url
                )
                embed.title = video_title
                if image_url:
                    embed.set_image(url=image_url)
                if published_at:
                    try:
                        published_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                        embed.timestamp = published_dt
                        embed.set_footer(text="Published")
                    except ValueError:
                        pass

                await self.bot.loop.create_task(
                    discord_channel.send(
                        content=role_mention,
                        embed=embed,
                        allowed_mentions=discord.AllowedMentions(roles=True, everyone=True)
                    )
                )
                return True
            else:
                self.taglog("YouTube", f"Upload notification channel with ID {upload_channel_id} not found.")
                return False
        else:
            self.taglog("YouTube", "Upload notification channel is not configured.")
            return False