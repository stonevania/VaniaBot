import discord
from discord import app_commands
from discord.ext import commands

class SocailConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.taglog = bot.taglog
        self.is_authorized = bot.is_authorized
        self.set_config = bot.set_config

    async def _authorize_interaction(self, interaction: discord.Interaction) -> bool:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True
            )
            return False

        if await self.is_authorized(interaction.user, guild):
            return True

        if interaction.response.is_done():
            await interaction.followup.send(
                "You are not authorized to use this command.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "You are not authorized to use this command.",
                ephemeral=True
            )
        return False

    ###
    # BOT COMMANDS MUST GO BETWEEN THESE LINES
    ###

    @app_commands.command(name='enablesocialnotifications', description='Enable notificaitons when a new video is posted.')
    @app_commands.describe(polling_interval='The number of seconds that should pass before the bot checks for new uploads.')
    async def enablesocialnotifications(self, interaction: discord.Interaction, polling_interval: int | None):
        self.taglog("SocailConfigCog", f"enablesocialnotifications [{polling_interval}]")
        if await self._authorize_interaction(interaction):
            self.config.social_config.set_enabled(True, polling_interval)
            self.set_config(self.config)

            message = f"Social notifications have been enabled with a polling interval of {polling_interval} seconds."

            if not self.config.social_config.upload_channel:
                message += "\n**WARNING:** No upload notifications channel has been set. To set one, use the `configureuploadnotifications` command."

            if not self.config.social_config.upload_notification_role:
                message += "\n**WARNING:** No upload notifications role has been set. To set one, use the `configureuploadnotifications` command."

            if not self.config.social_config.youtube_channels or len(self.config.social_config.youtube_channels) == 0:
                message += "\n**WARNING:** No YouTube channels are currently being monitored. To monitor one, use the `addyoutubechannel` command."

            if not self.config.social_config.live_channel:
                message += "\n**WARNING:** No live notifications channel has been set. To set one, use the `configurelivenotifications` command."

            if not self.config.social_config.live_notification_role:
                message += "\n**WARNING:** No live notifications role has been set. To set one, use the `configurelivenotifications` command."

            if not self.config.social_config.twitch_channels or len(self.config.social_config.twitch_channels) == 0:
                message += "\n**WARNING:** No Twitch channels are currently being monitored. To monitor one, use the `addtwitchchannel` command."

            await interaction.response.send_message(message)

    @app_commands.command(name='disablesocialnotifications', description='Disable notificaitons when a new video is posted.')
    async def disablesocialnotifications(self, interaction: discord.Interaction):
        self.taglog("SocailConfigCog", f"disablesocialnotifications")
        if await self._authorize_interaction(interaction):
            self.config.social_config.set_enabled(False)
            self.set_config(self.config)
            await interaction.response.send_message('Social notifications have been disabled.')

    ###
    # BOT COMMANDS MUST GO BETWEEN THESE LINES
    ###

async def setup(bot):
    await bot.add_cog(SocailConfigCog(bot))