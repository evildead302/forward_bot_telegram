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
        """Initialize the bot with proper session handling"""
        try:
            self.bot = Client(
                "secure_bot",
                api_id=int(os.environ.get("API_ID", 0)),
                api_hash=os.environ.get("API_HASH", ""),
                bot_token=os.environ.get("BOT_TOKEN", ""),
                in_memory=True
            )
            
            # Explicit login with error handling
            try:
                await self.bot.start()
                me = await self.bot.get_me()
                self.bot_id = me.id
                self.bot_username = me.username
                print(f"✅ Bot @{me.username} (ID: {self.bot_id}) successfully logged in")
            except Exception as login_error:
                print(f"❌ Login failed: {login_error}")
                raise
            
            # Initialize modules
            try:
                import c_l
                from forward import ForwardBot
                self.combined = c_l.CombinedLinkForwarder(self.bot)
                self.forwarder = ForwardBot(self.bot)
                print("✅ Modules loaded")
            except Exception as module_error:
                print(f"❌ Module loading failed: {module_error}")
                raise

            self.register_handlers()

        except Exception as e:
            print(f"❌ Initialization failed: {e}")
            await self.shutdown()
            raise

    def is_private_chat(self, message: Message):
        """Check if message is in private chat"""
        return message.chat.type == ChatType.PRIVATE

    def should_process(self, message: Message):
        """Determine if message should be processed"""
        # Process all messages during active operations
        if (self.forwarder and self.forwarder.state.get('active')) or \
           (self.combined and self.combined.state.get('active')):
            return True
            
        # Only process commands in private chat otherwise
        return self.is_private_chat(message) and filters.command([])(None, None, message)

    def register_handlers(self):
        """Register all message handlers"""
        @self.bot.on_message(filters.command("start") & filters.private)
        async def start(client: Client, message: Message):
            await message.reply_text(
                "🤖 Bot Started\n\n"
                "Available commands:\n"
                "/cl - Process links\n"
                "/forward - Forward messages\n"
                "/cancel - Cancel operation"
            )

        @self.bot.on_message(filters.command("forward") & filters.private)
        async def forward_cmd(client: Client, message: Message):
            try:
                await self.forwarder.start_forward_setup(message)
                print("🔹 Forward operation started")
            except Exception as e:
                print(f"❌ Forward command failed: {e}")
                await message.reply_text("❌ Failed to start forwarding")

        @self.bot.on_message(filters.command("cl") & filters.private)
        async def combined_cmd(client: Client, message: Message):
            try:
                await self.combined.start_combined_process(message)
                print("🔹 Combined operation started")
            except Exception as e:
                print(f"❌ Combined command failed: {e}")
                await message.reply_text("❌ Failed to start link processing")

        @self.bot.on_message(filters.command("cancel") & filters.private)
        async def cancel_cmd(client: Client, message: Message):
            if self.forwarder:
                self.forwarder.reset_state()
            if self.combined:
                self.combined.reset_state()
            await message.reply_text("⏹ All operations cancelled")
            print("🛑 Operations cancelled by user")

        @self.bot.on_message(filters.create(lambda _, __, m: self.should_process(m)))
        async def handle_messages(client: Client, message: Message):
            try:
                # Skip bot's own messages
                if message.from_user and message.from_user.id == self.bot_id:
                    return
                    
                if self.combined and self.combined.state.get('active'):
                    await self.combined.handle_message_flow(message)
                elif self.forwarder and self.forwarder.state.get('active'):
                    await self.forwarder.handle_setup_message(message)
            except Exception as e:
                print(f"❌ Message handling failed: {e}")

        @self.bot.on_message(~filters.create(lambda _, __, m: self.should_process(m)))
        async def ignore_other_messages(_, message: Message):
            # Only respond to unauthorized private messages
            if message.chat.type == ChatType.PRIVATE:
                await message.reply(f"❌ Please use commands in private chat with @{self.bot_username}")

    async def run(self):
        """Main bot running loop"""
        try:
            await self.initialize()
            print("🚀 Bot is now running (Press Ctrl+C to stop)")
            await asyncio.get_event_loop().create_future()  # Run forever
        except Exception as e:
            print(f"💥 Critical error: {e}")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Graceful shutdown procedure"""
        if self.bot and await self.bot.is_initialized:
            try:
                await self.bot.stop()
                print("✅ Bot stopped gracefully")
            except Exception as e:
                print(f"⚠️ Error during shutdown: {e}")

def create_temp_dirs():
    """Create required temporary directories"""
    os.makedirs("temp_cl_data", exist_ok=True)
    os.makedirs("forward_temp", exist_ok=True)
    print("📁 Temporary directories created")

if __name__ == "__main__":
    print("🔹 Starting bot...")
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
        print("🔹 Bot process ended")
