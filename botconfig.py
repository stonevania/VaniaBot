from typing import List, Optional

class BotConfig:
    def __init__(
            self,
            bot_name: str = "VaniaBot",
            command_prefix: str = "!sv_",
            configuration_role: Optional[str] = None,
            permitted_users: Optional[List[str]] = None):
        self.bot_name = bot_name
        self.command_prefix = command_prefix
        self.configuration_role = configuration_role
        self.permitted_users = permitted_users or []

    def json(self) -> dict:
        obj = {}
        obj["bot_name"] = self.bot_name
        obj["command_prefix"] = self.command_prefix
        obj["configuration_role"] = self.configuration_role
        obj["permitted_users"] = self.permitted_users
        return obj

