import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatType

class SecureBot:
    def __init__(self):
        self.bot = None
        self.bot_id = None
        self.bot_username = None
        self.combined = None
        self.forwarder = None

    async def initialize(self):
        """Initialize the bot with session support"""
        try:
            self.bot = Client(
                "secure_bot_session",
                api_id=int(os.environ.get("API_ID", 0)),
                api_hash=os.environ.get("API_HASH", ""),
                bot_token=os.environ.get("BOT_TOKEN", ""),
                in_memory=True
            )
            
            await self.bot.start()
            me = await self.bot.get_me()
            self.bot_id = me.id
            self.bot_username = me.username
            print(f"🤖 Bot @{me.username} (ID: {self.bot_id}) initialized")

            # Initialize modules with error handling
            try:
                from forward import ForwardBot
                self.forwarder = ForwardBot(self.bot)
                print("✅ Forward module loaded")
            except Exception as e:
                print(f"❌ Failed to load forward module: {e}")
                raise

            try:
                import c_l
                self.combined = c_l.CombinedLinkForwarder(self.bot)
                print("✅ Combined link module loaded")
            except Exception as e:
                print(f"❌ Failed to load combined link module: {e}")
                raise

            self.register_handlers()

        except Exception as e:
            print(f"❌ Initialization failed: {e}")
            await self.shutdown()
            raise

    def is_bot_chat(self, message: Message):
        """Strict check - only allows messages in bot's direct private chat"""
        return (message.chat.type == ChatType.PRIVATE and 
                message.from_user is not None and
                message.chat.id == message.from_user.id and
                message.chat.id == self.bot_id)

    def register_handlers(self):
        """Register all message handlers with strict filtering"""
        @self.bot.on_message(filters.command("start") & filters.create(lambda _, __, m: self.is_bot_chat(m)))
        async def start(client: Client, message: Message):
            await message.reply_text(
                "🤖 Secure Bot\n\n"
                "Available commands:\n"
                "/cl - Process links\n"
                "/forward - Forward messages\n"
                "/cancel - Cancel operation\n"
                "/help - Show help"
            )

        @self.bot.on_message(filters.command("forward") & filters.create(lambda _, __, m: self.is_bot_chat(m)))
        async def forward_cmd(client: Client, message: Message):
            if not self.forwarder:
                await message.reply_text("❌ Forward module not loaded")
                return
            await self.forwarder.start_forward_setup(message)

        @self.bot.on_message(filters.command("cl") & filters.create(lambda _, __, m: self.is_bot_chat(m)))
        async def combined_cmd(client: Client, message: Message):
            if not self.combined:
                await message.reply_text("❌ Combined link module not loaded")
                return
            await self.combined.start_combined_process(message)

        @self.bot.on_message(filters.command("cancel") & filters.create(lambda _, __, m: self.is_bot_chat(m)))
        async def cancel_cmd(client: Client, message: Message):
            if self.combined:
                self.combined.reset_state()
            if self.forwarder:
                self.forwarder.reset_state()
            await message.reply_text("⏹ Operation cancelled")

        @self.bot.on_message(filters.command("help") & filters.create(lambda _, __, m: self.is_bot_chat(m)))
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
             filters.reply) & filters.create(lambda _, __, m: self.is_bot_chat(m)))
        async def handle_messages(client: Client, message: Message):
            if self.combined and self.combined.state.get('active'):
                await self.combined.handle_message_flow(message)
            elif self.forwarder and self.forwarder.state.get('active'):
                await self.forwarder.handle_setup_message(message)

        @self.bot.on_message(~filters.create(lambda _, __, m: self.is_bot_chat(m)))
        async def ignore_other_messages(_, message: Message):
            if message.chat.type == ChatType.PRIVATE:
                await message.reply(f"❌ Please message @{self.bot_username} directly.")
            print(f"🚫 Ignored message from {message.from_user.id if message.from_user else 'unknown'} in chat {message.chat.id}")

    async def run(self):
        """Main bot running loop"""
        try:
            await self.initialize()
            print("🚀 Bot is now running (Ctrl+C to stop)")
            await asyncio.Event().wait()
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
    print("📁 Created temp directories")

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
