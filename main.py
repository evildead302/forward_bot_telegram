import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, BotCommand
from pyrogram.enums import ParseMode

class SecureBot:
    def __init__(self):
        self.bot = Client(
            "bot_account",
            api_id=int(os.environ["API_ID"]),
            api_hash=os.environ["API_HASH"],
            bot_token=os.environ["BOT_TOKEN"],
            in_memory=True
        )
        self.bot_id = None

    async def initialize(self):
        await self.bot.start()
        self.bot_id = (await self.bot.get_me()).id
        print(f"🤖 Bot ready | ID: {self.bot_id}")

    async def is_authorized(self, _, message: Message):
        """Allow messages sent to the bot in any private context"""
        return message.chat.type == "private"  # Changed from ChatType.BOT

    async def run(self):
        try:
            await self.initialize()
            
            # Debug command to check chat type
            @self.bot.on_message(filters.command("chatid"))
            async def chatid(_, message: Message):
                await message.reply(f"Chat ID: {message.chat.id}\nType: {message.chat.type}")

            auth_filter = filters.create(self.is_authorized)

            @self.bot.on_message(filters.command("start") & auth_filter)
            async def start(_, message: Message):
                await message.reply_text(
                    "🤖 <b>Bot is working!</b>\n\n"
                    "Send /cl to start link processing",
                    parse_mode=ParseMode.HTML
                )

            @self.bot.on_message(filters.command("cl") & auth_filter)
            async def combined_cmd(_, message: Message):
                await message.reply("CL command received!")  # Test response
                # await self.combined.start_combined_process(message)

            @self.bot.on_message(~auth_filter)
            async def log_unauthorized(_, message: Message):
                print(f"DEBUG - Chat Type: {message.chat.type}")

            print("🚀 Bot is now running")
            await asyncio.Event().wait()

        except Exception as e:
            print(f"💥 Error: {e}")
        finally:
            await self.bot.stop()

if __name__ == "__main__":
    bot = SecureBot()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped")
    finally:
        loop.close()
