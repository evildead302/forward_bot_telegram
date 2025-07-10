import os
import asyncio
import tempfile
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import MessageEntityType

class SecureBot:
    def __init__(self):
        self.bot = None
        self.bot_username = None
        self.combined = None
        self.forwarder = None

    async def initialize(self):
        """Initialize the bot and all components"""
        self.bot = Client(
            "main_bot",
            api_id=int(os.environ.get("API_ID", 0)),
            api_hash=os.environ.get("API_HASH", ""),
            bot_token=os.environ.get("BOT_TOKEN", ""),
            in_memory=True
        )
        
        await self.bot.start()
        me = await self.bot.get_me()
        self.bot_username = me.username.lower()
        print(f"🤖 Bot @{self.bot_username} initialized")

        # Initialize modules
        import c_l
        from forward import ForwardBot
        self.combined = c_l.CombinedLinkForwarder(self.bot)
        self.forwarder = ForwardBot(self.bot)
        print("✅ Modules loaded")

        # Register handlers
        self.register_handlers()

    def register_handlers(self):
        """Register all message handlers"""
        
        def is_bot_chat(_, __, message: Message):
            """Strict filter to only allow messages in bot's private chat"""
            return message.chat.type == "private"

        bot_chat_filter = filters.create(is_bot_chat)

        @self.bot.on_message(filters.command("start") & bot_chat_filter)
        async def start(client: Client, message: Message):
            await message.reply_text(
                "🤖 Combined Link Forwarder Bot\n\n"
                "Available commands:\n"
                "/cl - Process links\n"
                "/forward - Forward messages\n"
                "/cancel - Cancel operation\n"
                "/help - Show help"
            )

        @self.bot.on_message(filters.command("forward") & bot_chat_filter)
        async def forward_cmd(client: Client, message: Message):
            await self.forwarder.start_forward_setup(message)

        @self.bot.on_message(filters.command("cl") & bot_chat_filter)
        async def combined_cmd(client: Client, message: Message):
            await self.combined.start_combined_process(message)

        @self.bot.on_message(filters.command("cancel") & bot_chat_filter)
        async def cancel_cmd(client: Client, message: Message):
            self.combined.reset_state()
            self.forwarder.reset_state()
            await message.reply_text("⏹ Operation cancelled")

        @self.bot.on_message(filters.command("help") & bot_chat_filter)
        async def help_cmd(client: Client, message: Message):
            await message.reply_text(
                "🆘 Help Information\n\n"
                "/cl - Process links\n"
                "/forward - Forward messages\n"
                "/cancel - Cancel operation"
            )

        @self.bot.on_message(
            (filters.text | filters.photo | filters.document |
             filters.video | filters.audio | filters.voice |
             filters.reply) & bot_chat_filter
        )
        async def handle_messages(client: Client, message: Message):
            if self.combined.state.get('active'):
                await self.combined.handle_message_flow(message)
            elif self.forwarder.state.get('active'):
                await self.forwarder.handle_setup_message(message)

        @self.bot.on_message(~bot_chat_filter)
        async def ignore_other_messages(_, message: Message):
            print(f"🚫 Ignored message from {message.chat.id}")

    async def run(self):
        """Main bot running loop"""
        try:
            await self.initialize()
            print("🚀 Bot is now running")
            await asyncio.Event().wait()  # Run forever
        except Exception as e:
            print(f"💥 Error: {e}")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Graceful shutdown procedure"""
        if self.bot and self.bot.is_initialized:
            try:
                await self.bot.stop()
                print("✅ Bot stopped gracefully")
            except Exception as e:
                print(f"⚠️ Error during shutdown: {e}")

def create_temp_dirs():
    """Create required temporary directories"""
    os.makedirs("temp_cl_data", exist_ok=True)
    os.makedirs("forward_temp", exist_ok=True)

if __name__ == "__main__":
    create_temp_dirs()
    bot = SecureBot()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        print("\n🛑 Received shutdown signal")
    except Exception as e:
        print(f"💥 Fatal error: {e}")
    finally:
        loop.run_until_complete(bot.shutdown())
        loop.close()
