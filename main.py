import os
import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatType
from pyrogram.errors import FloodWait

class SecureBot:
    def __init__(self):
        self.bot = None
        self.bot_id = None
        self.bot_username = None
        self.allowed_users = set()
        self.combined = None
        self.forwarder = None
        self.username_waiting = True
        self.max_retries = 3
        self.retry_delay = 5  # seconds

    async def initialize(self):
        """Initialize the bot with retry mechanism"""
        retry_count = 0
        last_error = None
        
        while retry_count < self.max_retries:
            try:
                self.bot = Client(
                    "main_bot",
                    api_id=int(os.environ.get("API_ID", 0)),
                    api_hash=os.environ.get("API_HASH", ""),
                    bot_token=os.environ.get("BOT_TOKEN", ""),
                    in_memory=True
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
                
                # Register handlers
                self.register_handlers()
                return True
                
            except FloodWait as e:
                last_error = e
                wait_time = e.value + 5  # Add buffer time
                print(f"⚠️ Flood wait detected. Waiting for {wait_time} seconds...")
                await asyncio.sleep(wait_time)
                retry_count += 1
                
            except Exception as e:
                last_error = e
                print(f"⚠️ Initialization error (attempt {retry_count + 1}/{self.max_retries}): {e}")
                await asyncio.sleep(self.retry_delay)
                retry_count += 1
                
        print(f"💥 Failed to initialize after {self.max_retries} attempts")
        if last_error:
            raise last_error
        return False

    # ... [rest of your existing methods remain the same] ...

    async def run(self):
        """Main bot running loop"""
        try:
            success = await self.initialize()
            if not success:
                print("❌ Bot initialization failed. Exiting...")
                return
                
            print(f"🚀 Bot is now running. Users must send @{self.bot_username} to verify")
            await asyncio.Event().wait()  # Run forever
            
        except Exception as e:
            print(f"💥 Error: {e}")
        finally:
            await self.shutdown()

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
