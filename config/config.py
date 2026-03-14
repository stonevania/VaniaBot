from pathlib import Path
import os
import discord

from config.socialconfig import SocialConfig
from logs import taglog
from config.botconfig import BotConfig
from config.pluggingconfig import PluggingConfig
from config.automodconfig import AutoModerationConfig
from config.serviceconfig import ServiceConfig

class Config:
    def __init__(
            self,
            bot: BotConfig = BotConfig(),
            plugging: PluggingConfig = PluggingConfig(),
            auto_moderation: AutoModerationConfig = AutoModerationConfig(),
            social_config: SocialConfig = SocialConfig()):
        self.bot = bot
        self.plugging = plugging
        self.auto_moderation = auto_moderation
        self.social_config = social_config

        # NEVER STORE SENSITIVE INFORMATION IN THE CONFIG FILE. ALWAYS USE ENVIRONMENT VARIABLES FOR SENSITIVE INFORMATION.
        self.token = os.getenv("DISCORD_TOKEN")
        self.youtube_api_key = os.getenv("YOUTUBE_API_KEY")

    def json(self) -> dict:
        obj = {}
        obj["bot"] = self.bot.json()
        obj["plugs"] = self.plugging.json()
        obj["auto_moderation"] = self.auto_moderation.json()
        obj["social"] = self.social_config.json()
        return obj
    
    def authorized(self, user: discord.User, guild: discord.Guild) -> bool:
        # bot is always authorized to use the bot
        if user.name == "VaniaBot":
            return True
        
        # Guild owner is always authorized to use the bot
        if user == guild.owner:
            return True

        # Admins are always authorized to use the bot
        member = guild.get_member(user.id)
        if member and member.guild_permissions.administrator:
            return True
        
        # Users with the configuration role are authorized to use the bot
        for role in user.roles:
            if role.name == self.bot.configuration_role:
                return True
            
        taglog("CONFIG", f"User {user} is not authorized to use the bot.")
        return False
    
    # PluggingConfig methods
    def confirm(self, message: discord.Message, test_string: str, ignore_channels=False) -> bool:
        return self.plugging.confirm(message, test_string, ignore_channels=ignore_channels)
    
    # AutoModerationConfig methods
    def log_suspicious_activity(self, user: discord.User, reason: str | None) -> str | None:
        if not self.authorized(user, user.guild):
            return self.auto_moderation.log_suspicious_activity(user, reason)
        return None

    def check_message(self, message: discord.Message) -> str | None:
        if not self.authorized(message.author, message.guild):
            return self.auto_moderation.check_message(message)
        return None
        
        

script_dir = Path(__file__).parent
file_path = script_dir / "../config.json"

def get_config() -> Config:
    if not file_path.exists() or file_path.stat().st_size == 0:
        taglog("CONFIG", "Config file does not exist, creating default config.json")
        default_config = Config()
        set_config(default_config)
        return default_config

    try:
        with open(file_path, "r") as f:
            import json
            data = json.load(f)

            bot_data = data.get("bot", {})
            bot = BotConfig(
                bot_name=bot_data.get("bot_name", "VaniaBot"),
                command_prefix=bot_data.get("command_prefix", "!sv_"),
                configuration_role=bot_data.get("configuration_role"),
                permitted_users=bot_data.get("permitted_users", [])
            )

            plugs_data = data.get("plugs", {})
            plugging = PluggingConfig(
                enabled=plugs_data.get("enabled", False),
                watched_channels=plugs_data.get("watched_channels", []),
                watched_users=plugs_data.get("watched_users", []),
                keywords=plugs_data.get("keywords", []),
                twitter=ServiceConfig(**plugs_data.get("twitter")) if plugs_data.get("twitter") else None,
                bluesky=ServiceConfig(**plugs_data.get("bluesky")) if plugs_data.get("bluesky") else None,
                facebook=ServiceConfig(**plugs_data.get("facebook")) if plugs_data.get("facebook") else None,
                reddit=ServiceConfig(**plugs_data.get("reddit")) if plugs_data.get("reddit") else None,
                instagram=ServiceConfig(**plugs_data.get("instagram")) if plugs_data.get("instagram") else None
            )

            auto_mod_data = data.get("auto_moderation", {})
            auto_moderation = AutoModerationConfig(
                reporting_channel=auto_mod_data.get("reporting_channel"),
                banned_words=auto_mod_data.get("banned_words", []),
                banned_links=auto_mod_data.get("banned_links", []),
                user_reports=auto_mod_data.get("user_reports", {}),
                maximum_reports=auto_mod_data.get("maximum_reports", 3),
                maximum_reports_timestamp_threshold=auto_mod_data.get("maximum_reports_timestamp_threshold", 3600)
            )

            social_data = data.get("social", {})
            social_config = SocialConfig(
                enabled=social_data.get("enabled", False),
                polling_interval=social_data.get("polling_interval", 60),
                upload_channel=social_data.get("upload_channel", None),
                live_channel=social_data.get("live_channel", None),
                upload_notification_role=social_data.get("upload_notification_role", None),
                live_notification_role=social_data.get("live_notification_role", None),
                youtube_channels=social_data.get("youtube_channels", []),
                twitch_channels=social_data.get("twitch_channels", [])
            )

            return Config(
                bot=bot,
                plugging=plugging,
                auto_moderation=auto_moderation,
                social_config=social_config
            )
    except Exception as e:
        taglog("CONFIG", f"Error loading config: {e}")
        raise

def set_config(config: Config):
    try:
        with open(file_path, "w") as f:
            import json
            json.dump(config.json(), f, indent=4)
            taglog("CONFIG", f"Config saved successfully [{config.json()}]")
    except Exception as e:
        taglog("CONFIG", f"Error saving config: {e}")
        raise