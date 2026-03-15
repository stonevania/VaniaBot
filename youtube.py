import asyncio
import os
import discord

from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from urllib.parse import urlparse

class YouTube:
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.social_config = bot.config.social_config
        self.taglog = bot.taglog
        self.set_config = bot.set_config

        self.api_key = os.getenv("YOUTUBE_API_KEY")
        self.youtube = None
        self.should_stop = False
        self.polling_task = None
        self.quota_backoff_until = 0.0

        try:
            self.youtube = build("youtube", "v3", developerKey=self.api_key)
        except Exception as e:
            self.taglog("YouTube", f"Failed to initialize YouTube client: {e}")
            self._schedule_unexpected_youtube_state_notification(f"Failed to initialize YouTube client [{e}]")
            raise

    def start_polling(self):
        self.should_stop = False
        if self.polling_task is None or self.polling_task.done():
            self.polling_task = asyncio.create_task(self.begin_polling())

    def stop(self):
        self.should_stop = True

        if self.polling_task is not None:
            self.polling_task.cancel()

    async def begin_polling(self):
        self.taglog("YouTube", "Starting YouTube polling...")
        while not self.should_stop:
            try:
                now = asyncio.get_running_loop().time()
                if self.quota_backoff_until > now:
                    await asyncio.sleep(self.quota_backoff_until - now)
                await self.check_for_new_content()
            except HttpError as e:
                if self._is_quota_exceeded(e):
                    backoff_seconds = 3600
                    self.quota_backoff_until = asyncio.get_running_loop().time() + backoff_seconds
                    message = f"YouTube request quota exceeded, backing off for {backoff_seconds} seconds"
                    self.taglog("YouTube", f"{message} [{e}]")
                    self._schedule_unexpected_youtube_state_notification(message)
                else:
                    self._schedule_unexpected_youtube_state_notification(f"YouTube polling HTTP error [{e}]")
                    self.taglog("YouTube", f"Error during polling: {e}")
            except Exception as e:
                self._schedule_unexpected_youtube_state_notification(f"YouTube polling error [{e}]")
                self.taglog("YouTube", f"Error during polling: {e}")

            await asyncio.sleep(self.social_config.polling_interval or 60)

    async def _notify_unexpected_youtube_state(self, message: str):
        reporting_channel_id = self.config.auto_moderation.reporting_channel

        if reporting_channel_id:
            channel = self.bot.get_channel(reporting_channel_id)
            if channel:
                try:
                    await channel.send(f"**ERROR**: {message}")
                    return
                except Exception as e:
                    self.taglog("YouTube", f"Failed to send auto-moderation alert: {e}")

        for guild in self.bot.guilds:
            owner = guild.owner or await guild.fetch_owner()
            if owner is None:
                continue

            try:
                await owner.send(f"VaniaBot detected an unexpected YouTube state in {guild.name}: {message}")
            except Exception as e:
                self.taglog("YouTube", f"Failed to DM guild owner for {guild.name}: {e}")

    def _schedule_unexpected_youtube_state_notification(self, message: str):
        try:
            asyncio.create_task(self._notify_unexpected_youtube_state(message))
        except RuntimeError as e:
            self.taglog("YouTube", f"Failed to schedule YouTube alert: {e}")

    def _is_quota_exceeded(self, error: HttpError) -> bool:
        try:
            details = error.error_details or []
        except AttributeError:
            details = []

        if any(detail.get("reason") == "quotaExceeded" for detail in details if isinstance(detail, dict)):
            return True

        return getattr(error.resp, "status", None) == 403 and "quota" in str(error).lower()

    def _cache_channel_data(self, channel: dict, channel_id: str, channel_response: dict | None = None) -> None:
        channel["channel_id"] = channel_id

        if channel_response:
            items = channel_response.get("items", [])
            if items:
                snippet = items[0].get("snippet", {})
                thumbnails = snippet.get("thumbnails", {})
                uploads_playlist_id = (
                    items[0].get("contentDetails", {})
                    .get("relatedPlaylists", {})
                    .get("uploads")
                )

                if uploads_playlist_id:
                    channel["uploads_playlist_id"] = uploads_playlist_id

                channel["channel_title"] = snippet.get("title", channel.get("channel_title"))
                channel["channel_image_url"] = (
                    thumbnails.get("high", {}).get("url")
                    or thumbnails.get("medium", {}).get("url")
                    or thumbnails.get("default", {}).get("url")
                )

        self.social_config.register_new_content(channel)
        self.set_config(self.config)

    def _get_channel_details(self, channel_id: str) -> dict:
        return self.youtube.channels().list(
            part="snippet,contentDetails",
            id=channel_id
        ).execute()

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

    def get_channel_id(self, channel: dict) -> str | None:
        cached_channel_id = channel.get("channel_id")
        if cached_channel_id:
            return cached_channel_id

        url = channel.get("url")
        self.taglog("YouTube", f"Getting channel id from {url}...")

        path = urlparse(url).path

        # Case 1: already contains channel id
        if path.startswith("/channel/"):
            channel_id = path.split("/")[2]
            self._cache_channel_data(channel, channel_id, self._get_channel_details(channel_id))
            return channel_id

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
                channel_id = items[0].get("id")
                self._cache_channel_data(channel, channel_id, self._get_channel_details(channel_id))
                return channel_id

            self.taglog("YouTube", f"No exact handle match for {handle}, falling back to search.")
            channel_id = self._search_for_channel_id(f"@{handle}", expected_custom_url=handle)
            if channel_id is None:
                self.taglog("YouTube", f"No channel found for handle {handle}.")
            else:
                self._cache_channel_data(channel, channel_id, self._get_channel_details(channel_id))
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

            channel_id = items[0].get("id")
            self._cache_channel_data(channel, channel_id, self._get_channel_details(channel_id))
            return channel_id

        channel_id = self._search_for_channel_id(name, expected_custom_url=name if kind == "c" else None)
        if channel_id is None:
            self.taglog("YouTube", f"No channel found for custom URL name {name}.")
        else:
            self._cache_channel_data(channel, channel_id, self._get_channel_details(channel_id))
        return channel_id

    def get_playlist_id(self, channel: dict, channel_id: str) -> str | None:
        cached_playlist_id = channel.get("uploads_playlist_id")
        if cached_playlist_id:
            return cached_playlist_id

        self.taglog("YouTube", f"Getting latest upload playlist for {channel_id}...")

        # Example response found in .ref/youtube.latest_videos_playlist_respons.json
        response = self.youtube.channels().list(
            part="contentDetails",
            id=channel_id
        ).execute()

        items = response.get("items", [])
        if not items:
            error_message = f"Channel not found: {channel_id}"
            self.taglog("YouTube", f"{error_message} [{response}]")
            self._schedule_unexpected_youtube_state_notification(error_message)
            return None

        if len(items) == 0:
            self.taglog("YouTube", "Channel has no playlists")
            return None
        
        uploads_playlist_id = (
            items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
        )
        if uploads_playlist_id is None:
            error_message = f"Uploads playlist not found for channel {channel_id}"
            self.taglog("YouTube", f"{error_message} [{response}]")
            self._schedule_unexpected_youtube_state_notification(error_message)
            return None

        channel["uploads_playlist_id"] = uploads_playlist_id
        self.social_config.register_new_content(channel)
        self.set_config(self.config)
        return uploads_playlist_id
    
    # Example response found in .ref/youtube.latest_video_response.json
    def get_latest_upload(self, uploads_playlist_id: str) -> dict | None:
        response = self.youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=1
        ).execute()
  
        items = response.get("items", [])
        if not items:
            error_message = f"YouTube playlist returned no items for uploads playlist {uploads_playlist_id}"
            self.taglog("YouTube", f"{error_message} [{response}]")
            self._schedule_unexpected_youtube_state_notification(error_message)
            return None
        
        if len(items) == 0:
            self.taglog("YouTube", "Playlist has no items")
            return None

        return items[0]
    
    def get_latest_live(self, channel_id: str):
        # Example response found in .ref/youtube.latest_live_response.json
        response = self.youtube.search().list(
            part="snippet",
            channelId=channel_id,
            type="video",
            eventType="live",
            maxResults=1
        ).execute()

        items = response.get("items", [])
        if not items:
            # We should do nothing here because this just means that the channel is not currently live
            return None

        return items[0]
    
    async def check_for_new_content(self):
        self.taglog("YouTube", "Checking for new content on monitored YouTube channels...")

        for channel in self.social_config.youtube_channels or []:
            channel_url = channel.get("url", None)
            channel_id = self.get_channel_id(channel)
            if channel_id is None:
                error_message = f"Channel ID not found for configured YouTube channel URL: {channel_url}"
                self.taglog("YouTube", error_message)
                self._schedule_unexpected_youtube_state_notification(error_message)
                continue
            
            playlist_id = self.get_playlist_id(channel, channel_id)
            # Error is handled in get_playlist_id because we can include the response there, but if we
            # don't get a playlist_id here, move on.
            if playlist_id is None:
                continue
            
            latest_upload = self.get_latest_upload(playlist_id)
            last_video_notification = channel.get("last_video_notification", None)
            await self.handle_new_upload(channel, last_video_notification, latest_upload)

            if channel.get("lives", False):
                latest_live = self.get_latest_live(channel_id)
                last_live_notification = channel.get("last_live_notification", None)
                await self.handle_new_live(channel, last_live_notification, latest_live)

    async def handle_new_live(self, channel: dict, last_live_notification: dict, latest_live: dict):
        channel_url = channel.get("url", None)

        # Don't send upload notificaiton as this is the first time we are fetching a new upload,
        # BUT we should set this so that the next time we come through and find a different ID, we
        # DO send an upload notification.
        if latest_live and not last_live_notification:
            self.taglog("YouTube", f"First ever live fetched for {channel_url}, log and do nothing...")
            channel["last_live_notification"] = latest_live
            self.social_config.register_new_content(channel)
            self.set_config(self.config)
            return
        
        if last_live_notification and latest_live:
            notification_id = last_live_notification.get("id", {}).get("videoId", None)
            live_id = latest_live.get("id", {}).get("videoId", None)
            if notification_id != live_id:
                self.taglog("YouTube", f"New live fetched for {channel_url}, send a social notification!")
                message = await self.post_live_to_discord(channel, latest_live, channel_url)
                if message:
                    channel["last_live_notification"] = latest_live
                    channel["last_live_message_id"] = message.id
                    self.social_config.register_new_content(channel)
                    self.set_config(self.config)
                    return
                return

        if last_live_notification and not latest_live:
            self.taglog("YouTube", f"Live ended for {channel_url}, update the existing social notification!")
            if await self.update_live_discord_message(channel, channel_url):
                channel["last_live_notification"] = None
                channel["last_live_message_id"] = None
                self.social_config.register_new_content(channel)
                self.set_config(self.config)
                return
        
        self.taglog("YouTube", f"No new lives fetched for {channel_url}...")
    
    async def handle_new_upload(self, channel: dict, last_video_notification: dict, latest_upload: dict):
        channel_url = channel.get("url", None)

        # Don't send upload notificaiton as this is the first time we are fetching a new upload,
        # BUT we should set this so that the next time we come through and find a different ID, we
        # DO send an upload notification.
        if latest_upload and not last_video_notification:
            self.taglog("YouTube", f"First ever upload fetched for {channel_url}, log and do nothing...")
            channel["last_video_notification"] = latest_upload
            self.social_config.register_new_content(channel)
            self.set_config(self.config)
            return
        
        if last_video_notification and latest_upload:
            if last_video_notification.get("id", None) != latest_upload.get("id", None):
                self.taglog("YouTube", f"New upload fetched for {channel_url}, send a social notification!")
                if await self.post_upload_to_discord(channel, latest_upload, channel_url):
                    channel["last_video_notification"] = latest_upload
                    self.social_config.register_new_content(channel)
                    self.set_config(self.config)
                    return
                return
        
        self.taglog("YouTube", f"No new uploads fetched for {channel_url}...")
    
    async def post_upload_to_discord(self, channel: dict, upload: dict, channel_url: str) -> bool:
        upload_channel_id = self.social_config.upload_channel
        if upload_channel_id:
            discord_channel = self.bot.get_channel(upload_channel_id)
            if discord_channel:
                snippet = upload.get("snippet", {})
                video_id = (
                    upload.get("contentDetails", {}).get("videoId")
                    or snippet.get("resourceId", {}).get("videoId")
                )
                channel_title = channel.get("channel_title") or snippet.get("channelTitle", channel_url)
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
                author_icon_url = channel.get("channel_image_url")

                embed = discord.Embed(
                    color=discord.Color.red(),
                    url=video_url
                )
                embed.title = video_title
                if author_icon_url:
                    embed.set_author(
                        name=f"{channel_title} published a new video on YouTube",
                        url=channel_url,
                        icon_url=author_icon_url
                    )
                else:
                    embed.set_author(
                        name=f"{channel_title} published a new video on YouTube",
                        url=channel_url
                    )
                if image_url:
                    embed.set_image(url=image_url)
                if published_at:
                    try:
                        published_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                        embed.timestamp = published_dt
                        embed.set_footer(text="Published")
                    except ValueError:
                        pass

                try:
                    await self.bot.loop.create_task(
                        discord_channel.send(
                            content=role_mention,
                            embed=embed,
                            allowed_mentions=discord.AllowedMentions(roles=True, everyone=True)
                        )
                    )
                    return True
                except Exception as e:
                    self._schedule_unexpected_youtube_state_notification(f"Failed to send YouTube upload notification [{e}]")
                    raise
            else:
                message = f"Upload notification channel with ID {upload_channel_id} not found."
                self.taglog("YouTube", message)
                self._schedule_unexpected_youtube_state_notification(message)
                return False
        else:
            message = "Upload notification channel is not configured."
            self.taglog("YouTube", message)
            self._schedule_unexpected_youtube_state_notification(message)
            return False

    async def post_live_to_discord(self, channel: dict, live_video: dict, channel_url: str) -> discord.Message | None:
        live_channel_id = self.social_config.live_channel
        if not live_channel_id:
            message = "Live notification channel is not configured."
            self.taglog("YouTube", message)
            self._schedule_unexpected_youtube_state_notification(message)
            return None

        discord_channel = self.bot.get_channel(live_channel_id)
        if not discord_channel:
            message = f"Live notification channel with ID {live_channel_id} not found."
            self.taglog("YouTube", message)
            self._schedule_unexpected_youtube_state_notification(message)
            return None

        snippet = live_video.get("snippet", {})
        if snippet.get("liveBroadcastContent") != "live":
            self.taglog("YouTube", "Live result was not marked as actively live.")
            return None

        video_id = live_video.get("id", {}).get("videoId")
        channel_title = channel.get("channel_title") or snippet.get("channelTitle", channel_url)
        stream_title = snippet.get("title", "Live now on YouTube")
        video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else channel_url

        thumbnails = snippet.get("thumbnails", {})
        image_url = (
            thumbnails.get("high", {}).get("url")
            or thumbnails.get("medium", {}).get("url")
            or thumbnails.get("default", {}).get("url")
        )

        published_at = (
            snippet.get("publishedAt")
            or snippet.get("publishTime")
        )

        role_id = self.social_config.live_notification_role
        role_mention = f"<@&{role_id}>" if role_id else "@everyone"
        author_icon_url = channel.get("channel_image_url")

        embed = discord.Embed(
            color=discord.Color.red(),
            url=video_url
        )
        embed.title = stream_title

        if author_icon_url:
            embed.set_author(
                name=f"{channel_title} is live on YouTube",
                url=channel_url,
                icon_url=author_icon_url
            )
        else:
            embed.set_author(
                name=f"{channel_title} is live on YouTube",
                url=channel_url
            )

        if image_url:
            embed.set_image(url=image_url)

        if published_at:
            try:
                published_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                embed.timestamp = published_dt
                embed.set_footer(text="Started")
            except ValueError:
                pass

        try:
            return await self.bot.loop.create_task(
                discord_channel.send(
                    content=role_mention,
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(roles=True, everyone=True)
                )
            )
        except Exception as e:
            self._schedule_unexpected_youtube_state_notification(f"Failed to send YouTube live notification [{e}]")
            raise

    async def update_live_discord_message(self, channel: dict, channel_url: str) -> bool:
        live_channel_id = self.social_config.live_channel
        if not live_channel_id:
            message = "Live notification channel is not configured."
            self.taglog("YouTube", message)
            self._schedule_unexpected_youtube_state_notification(message)
            return False

        discord_channel = self.bot.get_channel(live_channel_id)
        if not discord_channel:
            message = f"Live notification channel with ID {live_channel_id} not found."
            self.taglog("YouTube", message)
            self._schedule_unexpected_youtube_state_notification(message)
            return False

        message_id = channel.get("last_live_message_id")
        if not message_id:
            message = f"No existing live notification message found for {channel_url}."
            self.taglog("YouTube", message)
            self._schedule_unexpected_youtube_state_notification(message)
            return False

        last_live_notification = channel.get("last_live_notification", {})
        snippet = last_live_notification.get("snippet", {})
        channel_title = snippet.get("channelTitle", channel_url)
        stream_title = snippet.get("title", "Live ended on YouTube")
        video_id = last_live_notification.get("id", {}).get("videoId")
        video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else channel_url

        embed = discord.Embed(
            color=discord.Color.dark_grey(),
            url=video_url
        )
        embed.title = stream_title
        embed.set_author(
            name=f"{channel_title} is no longer live on YouTube",
            url=channel_url
        )

        try:
            message = await discord_channel.fetch_message(message_id)
        except discord.NotFound:
            message = f"Live notification message {message_id} was not found for {channel_url}."
            self.taglog("YouTube", message)
            self._schedule_unexpected_youtube_state_notification(message)
            return False

        try:
            await message.edit(
                content=None,
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none()
            )
        except Exception as e:
            self._schedule_unexpected_youtube_state_notification(f"Failed to update YouTube live notification [{e}]")
            raise
        return True
