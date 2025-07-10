import os
import asyncio
import tempfile
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatType

class SecureBot:
    def __init__(self):
        self.bot = None
        self.bot_id = None
        self.bot_username = None  # Will be set during initialization
        self.allowed_users = set()  # Store allowed user IDs
        self.combined = None
        self.forwarder = None
        self.username_waiting = True  # Flag for username verification phase

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
        self.bot_id = me.id
        self.bot_username = me.username  # Store bot username
        print(f"🤖 Bot @{self.bot_username} (ID: {self.bot_id}) initialized")

        # Initialize modules
        import c_l
        from forward import ForwardBot
        self.combined = c_l.CombinedLinkForwarder(self.bot)
        self.forwarder = ForwardBot(self.bot)
        print("✅ Modules loaded")

        # Register handlers
        self.register_handlers()

    def is_allowed_chat(self, message: Message):
        """Check if message is from an allowed user"""
        # During username waiting phase, only accept messages containing bot username
        if self.username_waiting:
            return (message.text and 
                    f"@{self.bot_username}" in message.text.lower() and
                    message.chat.type == ChatType.PRIVATE)
        
        # After verification, check against allowed users
        return (message.chat.type == ChatType.PRIVATE and 
                message.from_user and 
                message.from_user.id in self.allowed_users)

    def register_handlers(self):
        """Register all message handlers"""
        # Handler for initial username verification
        @self.bot.on_message(filters.private & ~filters.create(lambda _, __, m: self.is_allowed_chat(m)))
        async def initial_verification(client: Client, message: Message):
            if self.username_waiting and message.text and f"@{self.bot_username}" in message.text.lower():
                self.allowed_users.add(message.from_user.id)
                self.username_waiting = False
                await message.reply_text(
                    f"✅ Verification successful! You can now use the bot.\n"
                    f"Your User ID: {message.from_user.id}\n\n"
                    f"Available commands:\n"
                    "/cl - Process links\n"
                    "/forward - Forward messages\n"
                    "/cancel - Cancel operation\n"
                    "/help - Show help"
                )
                return
            await message.reply_text(f"Please start by sending a message containing @{self.bot_username}")

        @self.bot.on_message(filters.command("start") & filters.create(lambda _, __, m: self.is_allowed_chat(m)))
        async def start(client: Client, message: Message):
            await message.reply_text(
                "🤖 Combined Link Forwarder Bot\n\n"
                "Available commands:\n"
                "/cl - Process links\n"
                "/forward - Forward messages\n"
                "/cancel - Cancel operation\n"
                "/help - Show help"
            )

        @self.bot.on_message(filters.command("forward") & filters.create(lambda _, __, m: self.is_allowed_chat(m)))
        async def forward_cmd(client: Client, message: Message):
            await self.forwarder.start_forward_setup(message)

        @self.bot.on_message(filters.command("cl") & filters.create(lambda _, __, m: self.is_allowed_chat(m)))
        async def combined_cmd(client: Client, message: Message):
            await self.combined.start_combined_process(message)

        @self.bot.on_message(filters.command("cancel") & filters.create(lambda _, __, m: self.is_allowed_chat(m)))
        async def cancel_cmd(client: Client, message: Message):
            self.combined.reset_state()
            self.forwarder.reset_state()
            await message.reply_text("⏹ Operation cancelled")

        @self.bot.on_message(filters.command("help") & filters.create(lambda _, __, m: self.is_allowed_chat(m)))
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
             filters.reply) & filters.create(lambda _, __, m: self.is_allowed_chat(m)))
        async def handle_messages(client: Client, message: Message):
            if self.combined.state.get('active'):
                await self.combined.handle_message_flow(message)
            elif self.forwarder.state.get('active'):
                await self.forwarder.handle_setup_message(message)

        @self.bot.on_message(~filters.create(lambda _, __, m: self.is_allowed_chat(m)))
        async def ignore_other_messages(_, message: Message):
            user_info = f"user {message.from_user.id}" if message.from_user else "unknown"
            chat_info = f"chat {message.chat.id} (type: {message.chat.type})"
            print(f"🚫 Ignored message from {user_info} in {chat_info}")

    async def run(self):
        """Main bot running loop"""
        try:
            await self.initialize()
            print(f"🚀 Bot is now running. Users must send @{self.bot_username} to verify")
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
