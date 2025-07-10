import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatType
from pyrogram.errors import FloodWait, SessionExpired

class SecureBot:
    def __init__(self):
        self.bot = None
        self.bot_id = None
        self.bot_username = None
        self.allowed_users = set()
        self.combined = None
        self.forwarder = None
        self.session_file = "bot_session"
        self.max_retries = 3
        self.retry_delay = 10  # Increased delay for better recovery

    async def initialize(self):
        """Initialize the bot with proper session management"""
        retry_count = 0
        
        while retry_count < self.max_retries:
            try:
                self.bot = Client(
                    name=self.session_file,
                    api_id=int(os.environ.get("API_ID", 0)),
                    api_hash=os.environ.get("API_HASH", ""),
                    bot_token=os.environ.get("BOT_TOKEN", ""),
                    workdir=".",  # Store session file in current directory
                )
                
                await self.bot.start()
                me = await self.bot.get_me()
                self.bot_id = me.id
                self.bot_username = me.username
                print(f"🤖 Bot @{self.bot_username} (ID: {self.bot_id}) initialized")
                
                # Initialize modules
                import c_l
                from forward import ForwardBot
                self.combined = c_l.CombinedLinkForwarder(self.bot)
                self.forwarder = ForwardBot(self.bot)
                print("✅ Modules loaded")
                
                self.register_handlers()
                return True
                
            except SessionExpired:
                print("⚠️ Session expired. Creating new session...")
                if os.path.exists(f"{self.session_file}.session"):
                    os.remove(f"{self.session_file}.session")
                retry_count += 1
                
            except FloodWait as e:
                print(f"⚠️ Flood wait detected. Waiting for {e.value} seconds...")
                await asyncio.sleep(e.value)
                retry_count += 1
                
            except Exception as e:
                print(f"⚠️ Initialization error (attempt {retry_count + 1}/{self.max_retries}): {e}")
                await asyncio.sleep(self.retry_delay)
                retry_count += 1
                
        print(f"💥 Failed to initialize after {self.max_retries} attempts")
        return False

    # [Rest of your methods remain the same as previous version...]

    async def shutdown(self):
        """Graceful shutdown with session preservation"""
        if self.bot and await self.bot.is_initialized:
            try:
                await self.bot.stop()
                print("✅ Bot stopped gracefully. Session saved.")
            except Exception as e:
                print(f"⚠️ Error during shutdown: {e}")

if __name__ == "__main__":
    # Create required directories
    os.makedirs("temp_cl_data", exist_ok=True)
    os.makedirs("forward_temp", exist_ok=True)
    
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
