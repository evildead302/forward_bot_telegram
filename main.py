import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatType
from pyrogram.errors import FloodWait

class SecureBot:
    def __init__(self):
        self.bot = None
        self.bot_id = None
        self.bot_username = None
        self.allowed_users = set()  # Stores verified user IDs
        self.combined = None
        self.forwarder = None
        self.max_retries = 3
        self.retry_delay = 5  # seconds

    async def initialize(self):
        """Initialize the bot with retry mechanism"""
        retry_count = 0
        
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
                
                self.register_handlers()
                return True
                
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

    def is_verified_user(self, message: Message):
        """Check if message is from verified user"""
        return (message.chat.type == ChatType.PRIVATE and 
                message.from_user and 
                message.from_user.id in self.allowed_users)

    def register_handlers(self):
        """Register all message handlers"""
        # Verification handler - accepts any private message
        @self.bot.on_message(filters.private & ~filters.create(lambda _, __, m: self.is_verified_user(m)))
        async def verify_user(client: Client, message: Message):
            self.allowed_users.add(message.from_user.id)
            await message.reply_text(
                f"✅ Verification successful!\n"
                f"Your User ID: {message.from_user.id}\n\n"
                "Available commands:\n"
                "/cl - Process links\n"
                "/forward - Forward messages\n"
                "/cancel - Cancel operation\n"
                "/help - Show help"
            )

        @self.bot.on_message(filters.command("start") & filters.private)
        async def start(client: Client, message: Message):
            if message.from_user.id not in self.allowed_users:
                self.allowed_users.add(message.from_user.id)
                
            await message.reply_text(
                "🤖 Combined Link Forwarder Bot\n\n"
                "Available commands:\n"
                "/cl - Process links\n"
                "/forward - Forward messages\n"
                "/cancel - Cancel operation\n"
                "/help - Show help"
            )

        @self.bot.on_message(filters.command("forward") & filters.create(lambda _, __, m: self.is_verified_user(m)))
        async def forward_cmd(client: Client, message: Message):
            await self.forwarder.start_forward_setup(message)

        @self.bot.on_message(filters.command("cl") & filters.create(lambda _, __, m: self.is_verified_user(m)))
        async def combined_cmd(client: Client, message: Message):
            await self.combined.start_combined_process(message)

        @self.bot.on_message(filters.command("cancel") & filters.create(lambda _, __, m: self.is_verified_user(m)))
        async def cancel_cmd(client: Client, message: Message):
            self.combined.reset_state()
            self.forwarder.reset_state()
            await message.reply_text("⏹ Operation cancelled")

        @self.bot.on_message(filters.command("help") & filters.create(lambda _, __, m: self.is_verified_user(m)))
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
             filters.reply) & filters.create(lambda _, __, m: self.is_verified_user(m)))
        async def handle_messages(client: Client, message: Message):
            if self.combined.state.get('active'):
                await self.combined.handle_message_flow(message)
            elif self.forwarder.state.get('active'):
                await self.forwarder.handle_setup_message(message)

        @self.bot.on_message(~filters.create(lambda _, __, m: self.is_verified_user(m)))
        async def ignore_other_messages(_, message: Message):
            if message.chat.type != ChatType.PRIVATE:
                print(f"🚫 Ignored non-private message from chat {message.chat.id}")

    async def run(self):
        """Main bot running loop"""
        try:
            if await self.initialize():
                print("🚀 Bot is now running")
                await asyncio.Event().wait()  # Run forever
        except Exception as e:
            print(f"💥 Error: {e}")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Graceful shutdown procedure"""
        if self.bot and self.bot.is_initialized:
            await self.bot.stop()
            print("✅ Bot stopped gracefully")

def create_temp_dirs():
    """Create required temporary directories"""
    os.makedirs("temp_cl_data", exist_ok=True)
    os.makedirs("forward_temp", exist_ok=True)
    print("📁 Created temporary directories")

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
