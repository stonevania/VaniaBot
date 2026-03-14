import discord
from discord import app_commands
from discord.ext import commands

class BotConfigCog(commands.Cog):
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

    # Test basic command to check if bot is running
    @commands.command(name='ping', help='Responds with pong to test if bot is running')
    async def ping(self, ctx):
        self.taglog("MAIN", f"ping: {ctx.author.name}")
        if await self.is_authorized(ctx.author, ctx.guild):
            await ctx.send('pong')

    @app_commands.command(name='setbotconfigurationrole', description='Sets the role that is allowed to configure the bot')
    @app_commands.describe(role='Role that can configure the bot')
    async def setbotconfigurationrole(self, interaction: discord.Interaction, role: discord.Role):
        self.taglog("MAIN", f"setbotconfigurationrole: {interaction.user.name}")
        if await self._authorize_interaction(interaction):
            self.config.bot.configuration_role = role.name
            self.set_config(self.config)
            await interaction.response.send_message(f'Configuration role set to {role.name}')

    @app_commands.command(name='addbotconfiguraitonuser', description='Adds a user to the list of permitted users')
    @app_commands.describe(user='User to permit')
    async def addbotconfiguraitonuser(self, interaction: discord.Interaction, user: discord.User):
        self.taglog("MAIN", f"addbotconfiguraitonuser: {interaction.user.name}")
        if await self._authorize_interaction(interaction):
            if user.id not in self.config.bot.permitted_users:
                self.config.bot.permitted_users.append(user.id)
                self.set_config(self.config)
                await interaction.response.send_message(f'User {user.name} added to permitted users.')
            else:
                await interaction.response.send_message(
                    f'User {user.name} is already a permitted user.',
                    ephemeral=True
                )

    @app_commands.command(name='removebotconfigurationuser', description='Removes a user from the list of permitted users')
    @app_commands.describe(user='User to remove from permitted users')
    async def removebotconfigurationuser(self, interaction: discord.Interaction, user: discord.User):
        self.taglog("MAIN", f"removebotconfigurationuser: {interaction.user.name}")
        if await self._authorize_interaction(interaction):
            if user.id in self.config.bot.permitted_users:
                self.config.bot.permitted_users.remove(user.id)
                self.set_config(self.config)
                await interaction.response.send_message(f'User {user.name} removed from permitted users.')
            else:
                await interaction.response.send_message(
                    f'User {user.name} is not a permitted user.',
                    ephemeral=True
                )

async def setup(bot):
    await bot.add_cog(BotConfigCog(bot))
