import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, BotCommand
from pyrogram.enums import ParseMode

class Bot:
    def __init__(self):
        self.bot = Client(
            "my_bot",
            api_id=int(os.environ["API_ID"]),
            api_hash=os.environ["API_HASH"],
            bot_token=os.environ["BOT_TOKEN"],
            in_memory=True
        )
        self.bot_id = None
        self.forwarder = None
        self.combined = None

    async def initialize(self):
        await self.bot.start()
        me = await self.bot.get_me()
        self.bot_id = me.id
        print(f"🤖 Bot @{me.username} ready (ID: {self.bot_id})")

        # Initialize modules
        from forward import ForwardBot
        import c_l
        self.forwarder = ForwardBot(self.bot)
        self.combined = c_l.CombinedLinkForwarder(self.bot)

        # Register commands
        await self.bot.set_bot_commands([
            BotCommand("start", "Show bot info"),
            BotCommand("forward", "Message forwarding"),
            BotCommand("cl", "Combined link processor"),
            BotCommand("cancel", "Cancel operations")
        ])

    async def run(self):
        await self.initialize()

        @self.bot.on_message(filters.command("start"))
        async def start(_, message: Message):
            await message.reply_text(
                "🤖 <b>Bot is working!</b>\n\n"
                "<b>Commands:</b>\n"
                "/forward - Message forwarding\n"
                "/cl - Combined link processor\n"
                "/cancel - Cancel operations",
                parse_mode=ParseMode.HTML
            )

        @self.bot.on_message(filters.command("forward"))
        async def forward_cmd(_, message: Message):
            await self.forwarder.start_forward_setup(message)

        @self.bot.on_message(filters.command("cl"))
        async def combined_cmd(_, message: Message):
            await self.combined.start_combined_process(message)

        @self.bot.on_message(filters.command("cancel"))
        async def cancel_cmd(_, message: Message):
            self.forwarder.reset_state()
            self.combined.reset_state()
            await message.reply_text("🛑 All operations cancelled")

        # Log all messages for debugging
        @self.bot.on_message()
        async def log_message(_, message: Message):
            print(f"Received in chat {message.chat.id}: {message.text or 'media message'}")

        print("🚀 Bot is now responding to all messages in bot chat")
        await asyncio.Event().wait()  # Run forever

    async def shutdown(self):
        await self.bot.stop()
        print("🛑 Bot stopped")

if __name__ == "__main__":
    bot = Bot()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        print("\n🛑 Received shutdown signal")
    except Exception as e:
        print(f"💥 Error: {e}")
    finally:
        loop.run_until_complete(bot.shutdown())
        loop.close()
