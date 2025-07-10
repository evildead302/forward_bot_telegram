import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, BotCommand
from pyrogram.enums import ParseMode

class WorkingBot:
    def __init__(self):
        # Initialize bot with environment variables
        self.bot = Client(
            "main_bot",
            api_id=int(os.environ["API_ID"]),
            api_hash=os.environ["API_HASH"],
            bot_token=os.environ["BOT_TOKEN"],
            in_memory=True
        )
        
        # Initialize modules
        self.forwarder = None
        self.combined = None
        self.bot_id = None

    async def initialize_modules(self):
        """Initialize all required modules"""
        from forward import ForwardBot  # Your forwarding module
        import c_l  # Your combined links module
        
        self.forwarder = ForwardBot(self.bot)
        self.combined = c_l.CombinedLinkForwarder(self.bot)
        print("✅ Modules initialized")

    async def run(self):
        await self.bot.start()
        me = await self.bot.get_me()
        self.bot_id = me.id
        print(f"🤖 Bot @{me.username} ready (ID: {self.bot_id})")

        # Initialize modules
        await self.initialize_modules()

        # Set bot commands
        await self.bot.set_bot_commands([
            BotCommand("start", "Show bot info"),
            BotCommand("forward", "Message forwarding"),
            BotCommand("cl", "Combined link processor"),
            BotCommand("cancel", "Cancel current operation")
        ])

        # Command handlers
        @self.bot.on_message(filters.command("start"))
        async def start(_, message: Message):
            await message.reply_text(
                "🔧 <b>Bot is fully operational!</b>\n\n"
                "<b>Available commands:</b>\n"
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

        # Debug handler
        @self.bot.on_message()
        async def debug(_, message: Message):
            print(f"Received message from {message.from_user.id}: {message.text}")

        print("⚡ Bot is now fully operational")
        await asyncio.Event().wait()  # Run forever

    async def shutdown(self):
        await self.bot.stop()
        print("🛑 Bot stopped gracefully")

if __name__ == "__main__":
    bot = WorkingBot()
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
