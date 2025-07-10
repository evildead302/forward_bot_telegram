import os
import asyncio
import signal
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
        self.shutdown_event = asyncio.Event()

    async def initialize(self):
        """Initialize the bot with proper error handling"""
        try:
            self.bot = Client(
                "secure_bot_session",
                api_id=int(os.environ.get("API_ID", 0)),
                api_hash=os.environ.get("API_HASH", ""),
                bot_token=os.environ.get("BOT_TOKEN", ""),
                session_string=os.environ.get("SESSION_STRING", ""),
                in_memory=True
            )
            
            # Set up signal handlers for graceful shutdown
            loop = asyncio.get_running_loop()
            for signame in ('SIGINT', 'SIGTERM'):
                loop.add_signal_handler(
                    getattr(signal, signame),
                    lambda: asyncio.create_task(self.graceful_shutdown())
                )

            await self.bot.start()
            me = await self.bot.get_me()
            self.bot_id = me.id
            self.bot_username = me.username
            
            print(f"🤖 Bot @{me.username} (ID: {self.bot_id}) initialized and logged in")

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
            print(f"💥 Initialization error: {e}")
            await self.shutdown()
            raise

    def is_bot_chat(self, message: Message):
        """Enhanced check for bot's private chat"""
        if not message.chat or message.chat.type != ChatType.PRIVATE:
            return False
        if not message.from_user:
            return False
        return message.chat.id == message.from_user.id == self.bot_id

    async def graceful_shutdown(self):
        """Handle graceful shutdown"""
        print("\n🛑 Received shutdown signal")
        self.shutdown_event.set()

    # ... [rest of your existing methods unchanged] ...

    async def run(self):
        """Main bot running loop with proper shutdown handling"""
        try:
            await self.initialize()
            print("🚀 Bot is now running")
            await self.shutdown_event.wait()
        except Exception as e:
            print(f"💥 Runtime error: {e}")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Enhanced shutdown procedure"""
        if self.bot and self.bot.is_initialized:
            try:
                print("🛑 Shutting down gracefully...")
                await self.bot.stop()
                print("✅ Bot stopped successfully")
            except Exception as e:
                print(f"⚠️ Error during shutdown: {e}")

def create_temp_dirs():
    """Create required temporary directories"""
    dirs = ["temp_cl_data", "forward_temp"]
    for dir in dirs:
        try:
            os.makedirs(dir, exist_ok=True)
            print(f"📁 Created directory: {dir}")
        except Exception as e:
            print(f"❌ Failed to create directory {dir}: {e}")
            raise

if __name__ == "__main__":
    create_temp_dirs()
    bot = SecureBot()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot.run())
    except Exception as e:
        print(f"💥 Fatal error: {e}")
    finally:
        tasks = asyncio.all_tasks(loop)
        for task in tasks:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        loop.close()
        print("🔌 Event loop closed")
