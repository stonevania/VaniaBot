import asyncio

class Twitch:
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.social_config = bot.config.social_config
        self.taglog = bot.taglog
        self.set_config = bot.set_config
        
        # TODO: Do any twitch-specific setup here
        self.polling_task = None

    def start_polling(self):
        if self.polling_task is None or self.polling_task.done():
            self.polling_task = asyncio.create_task(self.begin_polling())

    async def begin_polling(self):
        self.taglog("Twitch", "Starting Twitch polling...")
        while True:
            try:
                await self.check_for_new_content()
            except Exception as e:
                self.taglog("Twitch", f"Error during polling: {e}")

            await asyncio.sleep(self.social_config.polling_interval or 60)

    async def check_for_new_content(self):
        print('not implemented yet')