    
from atproto import AsyncClient, models
from discord import client
import httpx

from logs import taglog
from serviceconfig import ServiceConfig

client = AsyncClient()

async def login(ctx, config: ServiceConfig) -> bool:
    if config is None or config.username is None or config.password is None:
        await ctx.reply("Bluesky config is malformed")
        return False

    # Ensure the username is in the correct format for Bluesky
    # The username should not start with "@" and should end with ".bsky.social"
    corrected_username = config.username
    if corrected_username.startswith("@"):
        corrected_username = corrected_username[1:]
    if not corrected_username.endswith(".bsky.social"):
        corrected_username = f"{corrected_username}.bsky.social"

    taglog("BLUESKY", f"logging in [{corrected_username}]...")

    try:
        await client.login(corrected_username, config.password)
        taglog("BLUESKY", "login successful!")
        return True
    except Exception as e:
        taglog("BLUESKY", f"login failed: {e}")
        return False

async def test(ctx, msg: str, config: ServiceConfig):
    if not msg.strip():
        await ctx.reply("Cannot send an empty message.")
        return

    if not await login(ctx, config):
        await ctx.reply("Bluesky login failed, cannot send test message.")
        return

    try:
        await client.send_post(text=msg)
        await ctx.reply("Test message sent successfully!")
    except Exception as e:
        await ctx.reply(f"Failed to send test message: {e}")

async def create_post(title, description, url, thumbnail, ctx, config, skip_login=False):
    if not skip_login and not await login(ctx, config):
        await ctx.reply("Bluesky login failed, cannot create post.")
        return

    plaintext = f"{title}\n{description}\n{url}"
    start = plaintext.find(url)
    end = start + len(url)

    if start == -1:
        taglog("BLUESKY", "URL not found in plaintext.")
        await ctx.reply("Could not create post due to formatting issue.")
        return

    # Create facet to embed url properly
    facet = models.AppBskyRichtextFacet.Main(
        index=models.AppBskyRichtextFacet.ByteSlice(
            byte_start=start, byte_end=end
        ),
        features=[models.AppBskyRichtextFacet.Link(uri=url)]
    )
    taglog("BLUESKY", f"created facet [{facet}]")

    # Download the thumbmnail from the url and upload to atproto blob
    async with httpx.AsyncClient() as client_http:
        response = await client_http.get(thumbnail)
        if response.status_code != 200:
            taglog("BLUESKY", f"Failed to download thumbnail: {response.status_code}")
            await ctx.reply("Thumbnail download failed.")
            return
        taglog("BLUESKY", f"received image with response [{response}]")
        
    blob = await client.com.atproto.repo.upload_blob(response.content)
    taglog("BLUESKY", f"got blob [{blob.blob}]")
    
    # Create embed to include in message
    taglog("BLUESKY", f"creating embed with {url}, {title}, and {description}")
    external_embed = models.AppBskyEmbedExternal.Main(
        external=models.AppBskyEmbedExternal.External(
            uri=url,
            title=title,
            description=description or "",
            thumb=blob.blob
        )
    )
    taglog("BLUESKY", f"created external embed [{external_embed}]")
    
    await client.send_post(text=plaintext, facets=[facet], embed=external_embed)

async def create_text_post(text, ctx, config, skip_login=False):
    if not skip_login and not await login(ctx, config):
        await ctx.reply("Bluesky login failed, cannot create post.")
        return

    await client.send_post(text=text)