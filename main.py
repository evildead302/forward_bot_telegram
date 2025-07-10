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
                session_string=os.environ.get("SESSION_STRING", ""),
                in_memory=True
            )
            
            await self.bot.start()
            me = await self.bot.get_me()
            self.bot_id = me.id
            self.bot_username = me.username
            
            if os.environ.get("SESSION_STRING"):
                print("🔑 Using existing session string")
            else:
                print("🆕 Created new session")
            
            print(f"🤖 Bot @{me.username} (ID: {self.bot_id}) initialized")

            # Initialize modules
            try:
                import c_l
                from forward import ForwardBot
                self.combined = c_l.CombinedLinkForwarder(self.bot)
                self.forwarder = ForwardBot(self.bot)
                print("✅ Modules loaded")
            except Exception as e:
                print(f"❌ Module loading failed: {e}")
                raise

            self.register_handlers()

        except Exception as e:
            print(f"❌ Initialization failed: {e}")
            await self.shutdown()
            raise

    def is_bot_chat(self, message: Message):
        """Allow messages during active operations or in direct private chat"""
        # Allow messages when any operation is active
        if (self.forwarder and self.forwarder.state.get('active')) or \
           (self.combined and self.combined.state.get('active')):
            return True
            
        # Otherwise only allow in direct private chat
        return (message.chat.type == ChatType.PRIVATE and 
                message.from_user is not None and
                message.chat.id == message.from_user.id)

    def register_handlers(self):
        """Register all message handlers with proper filtering"""
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
            await self.forwarder.start_forward_setup(message)

        @self.bot.on_message(filters.command("cl") & filters.create(lambda _, __, m: self.is_bot_chat(m)))
        async def combined_cmd(client: Client, message: Message):
            await self.combined.start_combined_process(message)

        @self.bot.on_message(filters.command("cancel") & filters.create(lambda _, __, m: self.is_bot_chat(m)))
        async def cancel_cmd(client: Client, message: Message):
            self.combined.reset_state()
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
            if message.from_user and message.from_user.id == self.bot_id:
                return
                
            if self.combined and self.combined.state.get('active'):
                await self.combined.handle_message_flow(message)
            elif self.forwarder and self.forwarder.state.get('active'):
                await self.forwarder.handle_setup_message(message)

        @self.bot.on_message(~filters.create(lambda _, __, m: self.is_bot_chat(m)))
        async def ignore_other_messages(_, message: Message):
            if message.from_user and message.from_user.id == self.bot_id:
                return
                
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
    try:
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
    except Exception as e:
        print(f"🔥 Critical startup error: {e}")
