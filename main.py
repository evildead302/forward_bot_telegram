import os
import asyncio
import tempfile
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
        self.session_name = "secure_bot_session"

    async def initialize(self):
        """Initialize the bot with proper session handling"""
        try:
            self.bot = Client(
                name=self.session_name,
                api_id=int(os.environ.get("API_ID", 0)),
                api_hash=os.environ.get("API_HASH", ""),
                bot_token=os.environ.get("BOT_TOKEN", ""),
                workdir="."  # Store session in current directory
            )
            
            # Connect and authenticate
            await self.bot.start()
            
            # Get bot info
            me = await self.bot.get_me()
            self.bot_id = me.id
            self.bot_username = me.username
            print(f"🤖 Bot @{self.bot_username} (ID: {self.bot_id}) initialized and logged in")
            
            # Initialize modules
            import c_l
            from forward import ForwardBot
            self.combined = c_l.CombinedLinkForwarder(self.bot)
            self.forwarder = ForwardBot(self.bot)
            print("✅ Modules loaded")
            
            self.register_handlers()
            return True
            
        except FloodWait as e:
            print(f"⏳ Flood wait: Need to wait {e.value} seconds")
            await asyncio.sleep(e.value)
            return await self.initialize()
        except Exception as e:
            print(f"💥 Login failed: {str(e)}")
            return False

    def is_allowed_chat(self, message: Message):
        """Check if message is from allowed user"""
        return message.chat.type == ChatType.PRIVATE

    def register_handlers(self):
        """Register all message handlers"""
        @self.bot.on_message(filters.command("start") & filters.private)
        async def start(client: Client, message: Message):
            self.allowed_users.add(message.from_user.id)
            await message.reply_text(
                "🤖 Bot Ready!\n\n"
                "Available commands:\n"
                "/cl - Process links\n"
                "/forward - Forward messages\n"
                "/cancel - Cancel operation"
            )

        # [Add your other handlers here...]

    async def run(self):
        """Main bot running loop"""
        try:
            if await self.initialize():
                print("🚀 Bot is now running")
                await asyncio.Event().wait()  # Run forever
            else:
                print("❌ Bot failed to start")
        except Exception as e:
            print(f"💥 Error: {e}")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Graceful shutdown"""
        if self.bot:
            try:
                await self.bot.stop()
                print("✅ Bot stopped gracefully")
            except:
                pass

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
