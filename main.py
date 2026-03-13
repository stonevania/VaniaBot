from dotenv import load_dotenv
from discord.ext import commands
import discord
import logging
import os

# helper imports
import bluesky
from config import get_config, set_config
from logs import getLogger, taglog

class DummyCtx:
    def __init__(self, message):
        self.message = message

    async def reply(self, msg):
        await self.message.reply(msg)

# set up environment
load_dotenv()
config = get_config()  # Load the configuration from config.json

# Set up intents
# NOTE: May need to activate more and/or disable some as the project needs; see 
# https://discordpy.readthedocs.io/en/stable/intents.html for more information!
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True
intents.dm_messages = True

# Configure bot to watch for prefix commands with given intents
bot = commands.Bot(command_prefix=config.bot.command_prefix, intents=intents)

# ================================================================================================ #
# ================================================================================================ #
# ======================== ALL BOT-RELATED COMMANDS MUST BE INSERTED BELOW ======================= #
# ================================================================================================ #
# ================================================================================================ #

# ================================================================================================ #
# ========================================= HELPER METHODS ======================================= #
# ================================================================================================ #
async def is_authorized(author: discord.User, guild: discord.Guild) -> bool:
    if not config.authorized(author, guild):
        # Log suspicious activity or ban the user
        ban_reason = config.log_suspicious_activity(author, "unauthorized access attempt")
        if ban_reason:
            await ban(author, guild, reason=ban_reason)
            set_config(config)
            return False
        else: 
            await reportModerationEvent(f"**WARNING**: {author} attempted unauthorized access at {discord.utils.utcnow()}.")
            set_config(config)
            return False
    return True

async def reportModerationEvent(msg: str):
    if not config.auto_moderation.reporting_channel:
        taglog("MAIN", "Auto-moderation is disabled. No report will be sent.")
        return
    
    channel = bot.get_channel(config.auto_moderation.reporting_channel)
    if not channel:
        taglog("MAIN", f"Reporting channel with ID {config.auto_moderation.reporting_channel} not found.")
        return 
    
    await channel.send(msg)
    
async def ban(user: discord.User, guild: discord.Guild, reason: str = "Auto-banned by VaniaBot."):
    if config.authorized(user, guild):
        return
    
    try:
        # DM the user to inform them of the ban BEFORE banning
        try:
            await user.send(f"You have been banned from {guild.name}. Reason: {reason}")
        except Exception as e:
            taglog("MAIN", f"Failed to send DM to user {user.name}: {e}")
        
        await guild.ban(user, reason=f"Auto-banned by VaniaBot [{reason}].")
        taglog("MAIN", f"User {user.name} has been banned from the server.")
        await reportModerationEvent(f"**ALERT**: User {user.name} has been banned from the server. Reason: {reason}")
    except Exception as e:
        taglog("MAIN", f"Failed to ban user {user.name}: {e}")
        await reportModerationEvent(f"**ERROR**: Failed to ban user {user.name}. Reason: {e}")

# Test basic command to check if bot is running
@bot.command(name='ping', help='Responds with pong to test if bot is running')
async def ping(ctx):
    taglog("MAIN", f"ping: {ctx.author.name}")
    if await is_authorized(ctx.author, ctx.guild):
        await ctx.send('pong')

# ================================================================================================ #
# ======================================= BOT CONFIGURATION ====================================== #
# ================================================================================================ #
@bot.command(name='setrole', help='Sets the role that is allowed to configure the bot')
async def setrole(ctx, role: discord.Role):
    taglog("MAIN", f"setrole: {ctx.author.name}")
    if await is_authorized(ctx.author, ctx.guild):
        config.bot.configuration_role = role.name
        await ctx.send(f'Configuration role set to {role.name}')
        set_config(config)

@bot.command(name='adduser', help='Adds a user to the list of permitted users')
async def adduser(ctx, user: discord.User):
    taglog("MAIN", f"adduser: {ctx.author.name}")
    if await is_authorized(ctx.author, ctx.guild):
        if user.id not in config.bot.permitted_users:
            config.bot.permitted_users.append(user.id)
            await ctx.send(f'User {user.name} added to permitted users.')
            set_config(config)
        else:
            await ctx.send(f'User {user.name} is already a permitted user.')

@bot.command(name='removeuser', help='Removes a user from the list of permitted users')
async def removeuser(ctx, user: discord.User):
    taglog("MAIN", f"removeuser: {ctx.author.name}")
    if await is_authorized(ctx.author, ctx.guild):
        if user.id in config.bot.permitted_users:
            config.bot.permitted_users.remove(user.id)
            await ctx.send(f'User {user.name} removed from permitted users.')
            set_config(config)
        else:
            await ctx.send(f'User {user.name} is not a permitted user.')

# ================================================================================================ #
# ====================================== PLUG CONFIGURATION ====================================== #
# ================================================================================================ #
@bot.command(name='plugging_enabled', help='Enables or disables social network auto-plugging')
async def plugging_enabled(ctx, enabled: bool):
    if await is_authorized(ctx.author, ctx.guild):
        config.plugging.enabled = enabled
        await ctx.send(f'Social network auto-plugging enabled: {enabled}')
        set_config(config)

@bot.command(name='plugging_watchchannel', help='Adds a channel to the list of channels to watch for auto-plugging')
async def plugging_watchchannel(ctx, channel: discord.TextChannel):
    if await is_authorized(ctx.author, ctx.guild):
        if channel.id not in config.plugging.watched_channels:
            config.plugging.watched_channels.append(channel.id)
            await ctx.send(f'Channel {channel.name} added to watched channels.')
            set_config(config)
        else:
            await ctx.send(f'Channel {channel.name} is already being watched.')

@bot.command(name='plugging_unwatchchannel', help='Removes a channel from the list of channels to watch for auto-plugging')
async def plugging_unwatchchannel(ctx, channel: discord.TextChannel):
    if await is_authorized(ctx.author, ctx.guild):
        if channel.id in config.plugging.watched_channels:
            config.plugging.watched_channels.remove(channel.id)
            await ctx.send(f'Channel {channel.name} removed from watched channels.')
            set_config(config)
        else:
            await ctx.send(f'Channel {channel.name} is not being watched.')

@bot.command(name='plugging_watchuser', help='Adds a user to the list of users to watch for auto-plugging')
async def plugging_watchuser(ctx, user: discord.User):
    if await is_authorized(ctx.author, ctx.guild):
        if user.id not in config.plugging.watched_users:
            config.plugging.watched_users.append(user.id)
            await ctx.send(f'User {user.name} added to watched users.')
            set_config(config)
        else:
            await ctx.send(f'User {user.name} is already being watched.')

@bot.command(name='plugging_unwatchuser', help='Removes a user from the list of users to watch for auto-plugging')
async def plugging_unwatchuser(ctx, user: discord.User):
    if await is_authorized(ctx.author, ctx.guild):
        if user.id in config.plugging.watched_users:
            config.plugging.watched_users.remove(user.id)
            await ctx.send(f'User {user.name} removed from watched users.')
            set_config(config)
        else:
            await ctx.send(f'User {user.name} is not being watched.')

@bot.command(name='plugging_addkeyword', help='Adds a keyword to the list of keywords for auto-plugging')
async def plugging_addkeyword(ctx, keyword: str):
    if await is_authorized(ctx.author, ctx.guild):
        if keyword not in config.plugging.keywords:
            config.plugging.keywords.append(keyword)
            await ctx.send(f'Keyword "{keyword}" added to the list of keywords.')
            set_config(config)
        else:
            await ctx.send(f'Keyword "{keyword}" is already in the list of keywords.')

@bot.command(name='plugging_removekeyword', help='Removes a keyword from the list of keywords for auto-plugging')
async def plugging_removekeyword(ctx, keyword: str):
    if await is_authorized(ctx.author, ctx.guild):
        if keyword in config.plugging.keywords:
            config.plugging.keywords.remove(keyword)
            await ctx.send(f'Keyword "{keyword}" removed from the list of keywords.')
            set_config(config)
        else:
            await ctx.send(f'Keyword "{keyword}" is not in the list of keywords.')

# Bluesky configuration commands
@bot.command(name='plugging_disablebluesky', help='Disables auto-plugging to Bluesky')
async def plugging_disablebluesky(ctx):
    if await is_authorized(ctx.author, ctx.guild):
        if not config.plugging.bluesky_config.enabled:
            await ctx.send('Auto-plugging to Bluesky is already disabled.')
            return
        config.plugging.disable_service("bluesky")
        await ctx.send('Auto-plugging to Bluesky disabled.')
        set_config(config)

@bot.command(name='plugging_configurebluesky', help='Configures auto-plugging to Bluesky')
async def plugging_configurebluesky(ctx, username: str, password: str):
    taglog("MAIN", f"plugging_configurebluesky: {ctx.author.name}")
    # Delete the command message to avoid exposing credentials
    try:
        await ctx.message.delete()
    except Exception as e:
        taglog("MAIN", f"Failed to delete command message: {e}")

    if await is_authorized(ctx.author, ctx.guild):
        if config.plugging.bluesky_config.enabled:
            return await ctx.send(f'Auto-plugging to Bluesky is already configured. Use {config.bot.command_prefix}plugging_disablebluesky to disable it first.')
        
        config.plugging.enable_service("bluesky", username, password)
        set_config(config)

        if not await bluesky.login(ctx, config.plugging.bluesky_config):
            config.plugging.disable_service("bluesky")
            set_config(config)
            
            return await ctx.send('Failed to log in to Bluesky with the provided credentials. Please check your username and password.')
        
        await ctx.send('Auto-plugging to Bluesky configured.')
        set_config(config)

@bot.command(name='plugging_testbluesky', help='Tests auto-plugging to Bluesky')
async def plugging_testbluesky(ctx, message: discord.Message):
    if await is_authorized(ctx.author, ctx.guild):
        # Implementation for testing Bluesky integration
        pass

# ================================================================================================ #
# ===================================== AUTOMOD CONFIGURATION ==================================== #
# ================================================================================================ #
@bot.command(name='automod_disable', help='Disables auto-moderation')
async def automod_disable(ctx):
    if await is_authorized(ctx.author, ctx.guild):
        config.auto_moderation.reporting_channel = None
        await ctx.send('Auto-moderation disabled.')
        set_config(config)

@bot.command(name='automod_setreportingchannel', help='Sets the channel for auto-moderation reports')
async def automod_setreportingchannel(ctx, channel: discord.TextChannel):
    if await is_authorized(ctx.author, ctx.guild):
        config.auto_moderation.reporting_channel = channel.id
        await ctx.send(f'Auto-moderation enabled and reporting channel set to {channel.name}')
        set_config(config)

@bot.command(name='automod_setmaxreports', help='Sets the maximum number of reports before action is taken')
async def automod_setmaxreports(ctx, max_reports: int):
    if await is_authorized(ctx.author, ctx.guild):
        config.auto_moderation.maximum_reports = max_reports
        await ctx.send(f'Maximum reports before action set to {max_reports}')
        set_config(config)

@bot.command(name='automod_setmaxtimestamp', help='Sets the maximum timestamp threshold for reports')
async def automod_setmaxtimestamp(ctx, max_timestamp: int):
    if await is_authorized(ctx.author, ctx.guild):
        config.auto_moderation.maximum_reports_timestamp_threshold = max_timestamp
        await ctx.send(f'Maximum timestamp threshold for reports set to {max_timestamp}')
        set_config(config)

@bot.command(name='automod_addbannedword', help='Adds a banned word for auto-moderation')
async def automod_addbannedword(ctx, word: str):
    if await is_authorized(ctx.author, ctx.guild):
        if word not in config.auto_moderation.banned_words:
            config.auto_moderation.banned_words.append(word)
            await ctx.send(f'Banned word "{word}" added.')
            set_config(config)
        else:
            await ctx.send(f'Banned word "{word}" is already in the list.')

@bot.command(name='automod_removebannedword', help='Removes a banned word for auto-moderation')
async def automod_removebannedword(ctx, word: str):
    if await is_authorized(ctx.author, ctx.guild):
        if word in config.auto_moderation.banned_words:
            config.auto_moderation.banned_words.remove(word)
            await ctx.send(f'Banned word "{word}" removed.')
            set_config(config)
        else:
            await ctx.send(f'Banned word "{word}" is not in the list.')

@bot.command(name='automod_addbannedlink', help='Adds a banned link for auto-moderation')
async def automod_addbannedlink(ctx, link: str):
    if await is_authorized(ctx.author, ctx.guild):
        if link not in config.auto_moderation.banned_links:
            config.auto_moderation.banned_links.append(link)
            await ctx.send(f'Banned link "{link}" added.')
            set_config(config)
        else:
            await ctx.send(f'Banned link "{link}" is already in the list.')

@bot.command(name='automod_removebannedlink', help='Removes a banned link for auto-moderation')
async def automod_removebannedlink(ctx, link: str):
    if await is_authorized(ctx.author, ctx.guild):
        if link in config.auto_moderation.banned_links:
            config.auto_moderation.banned_links.remove(link)
            await ctx.send(f'Banned link "{link}" removed.')
            set_config(config)
        else:
            await ctx.send(f'Banned link "{link}" is not in the list.')

@bot.command(name='automod_addignoreduser', help='Adds a user to the list of ignored users for auto-moderation')
async def automod_addignoreduser(ctx, user: discord.User):
    if await is_authorized(ctx.author, ctx.guild):
        if str(user.id) not in config.auto_moderation.ignored_users:
            config.auto_moderation.ignored_users.append(str(user.id))
            await ctx.send(f'User {user.name} added to ignored users.')
            set_config(config)
        else:
            await ctx.send(f'User {user.name} is already in the list of ignored users.')

@bot.command(name='automod_removeignoreduser', help='Removes a user from the list of ignored users for auto-moderation')
async def automod_removeignoreduser(ctx, user: discord.User):
    if await is_authorized(ctx.author, ctx.guild):
        if str(user.id) in config.auto_moderation.ignored_users:
            config.auto_moderation.ignored_users.remove(str(user.id))
            await ctx.send(f'User {user.name} removed from ignored users.')
            set_config(config)
        else:
            await ctx.send(f'User {user.name} is not in the list of ignored users.')

@bot.command(name='automod_addignoredrole', help='Adds a role to the list of ignored roles for auto-moderation')
async def automod_addignoredrole(ctx, role: discord.Role):
    if await is_authorized(ctx.author, ctx.guild):
        if role.name not in config.auto_moderation.ignored_roles:
            config.auto_moderation.ignored_roles.append(role.name)
            await ctx.send(f'Role {role.name} added to ignored roles.')
            set_config(config)
        else:
            await ctx.send(f'Role {role.name} is already in the list of ignored roles.')

@bot.command(name='automod_removeignoredrole', help='Removes a role from the list of ignored roles for auto-moderation')
async def automod_removeignoredrole(ctx, role: discord.Role):
    if await is_authorized(ctx.author, ctx.guild):
        if role.name in config.auto_moderation.ignored_roles:
            config.auto_moderation.ignored_roles.remove(role.name)
            await ctx.send(f'Role {role.name} removed from ignored roles.')
            set_config(config)
        else:
            await ctx.send(f'Role {role.name} is not in the list of ignored roles.')

# ================================================================================================ #
# ============================================ EVENTS ============================================ #
# ================================================================================================ #
@bot.event
async def on_ready():
    taglog("MAIN", f'Logged in as {bot.user.name} - {bot.user.id}')
    taglog("MAIN", 'Bot is ready to receive commands.')

# A user left or was removed from a guild
# VaniaBot should only do something under the following conditions:
# - user is in the list of permitted users -> remove from list
# - user is in the list of watched users -> remove from list
@bot.event
async def on_member_remove(member):
    if member.id in config.permitted_users:
        taglog("MAIN", f"on_member_remove: removing {member.id} from permitted users")
        config.permitted_users.remove(member.id)
        set_config(config)
        await reportModerationEvent(f"User {member.name} ({member.id}) has left the server and was removed from the list of permitted users.")
    if member.id in config.plugging.watched_users:
        taglog("MAIN", f"on_member_remove: removing {member.id} from watched users")
        config.plugging.watched_users.remove(member.id)
        set_config(config)
        await reportModerationEvent(f"User {member.name} ({member.id}) has left the server and was removed from the list of watched users.")

    config.auto_moderation.remove_user_reports(str(member.id))

@bot.event
async def on_message(message):
    if isinstance(message.channel, discord.DMChannel) and not message.author.bot:
        taglog("MAIN", f"on_message: received DM from {message.author.name}: {message.content}")
        await reportModerationEvent(f"**DM RECEIVED**: {message.author} sent a DM to the bot at {discord.utils.utcnow()}. Content: {message.content}")
        return bot.process_commands(message)

    # Check the message against the auto-moderation rules first
    ban_reason = config.check_message(message)
    if ban_reason:
        await ban(message.author, message.guild, reason="spamming or suspicious activity detected by auto-moderation")
        return await bot.process_commands(message)
    
    # Check the message against the plugging configuration rules
    # If there's a match, send the message to any configured social network(s)
    if config.confirm(message, message.content):
        taglog("MAIN", f"on_message: message from {message.author.name} in {message.channel.name} confirmed for auto-plugging")
        dummy_ctx = DummyCtx(message)
        await config.send_to_social_networks(message, dummy_ctx)
        return await bot.process_commands(message)

    # NOTE: always required, this function is effectively an override allows continued
    # handling of other messages
    taglog("MAIN", f"on_message: fallthrough, process {message.content}")
    await bot.process_commands(message)

# ================================================================================================ #
# ================================================================================================ #
# ======================== ALL BOT-RELATED COMMANDS MUST BE INSERTED ABOVE ======================= #
# ================================================================================================ #
# ================================================================================================ #

# Configure and run the bot
bot.run(token=config.token, log_handler=getLogger(), log_level=logging.DEBUG)