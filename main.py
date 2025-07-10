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
        self.allowed_user_id = None  # To store the authorized user ID
        self.combined = None
        self.forwarder = None
        self.waiting_for_user = False  # Flag to track if we're waiting for initial user

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
        print(f"🤖 Bot @{me.username} (ID: {self.bot_id}) initialized")
        print("🕒 Waiting for initial message from user in bot's private chat...")
        self.waiting_for_user = True

        # Initialize modules
        import c_l
        from forward import ForwardBot
        self.combined = c_l.CombinedLinkForwarder(self.bot)
        self.forwarder = ForwardBot(self.bot)
        print("✅ Modules loaded")

        # Register handlers
        self.register_handlers()

    def is_authorized_chat(self, message: Message):
        """Check if message is in authorized chat (either bot's self-chat or from authorized user)"""
        if self.waiting_for_user:
            # During initial setup, only accept messages from bot's self-chat
            return message.chat.id == self.bot_id
        
        if not self.allowed_user_id:
            return False
            
        # After setup, accept messages from either:
        # 1. The authorized user's private chat
        # 2. The bot's self-chat
        return (message.chat.id == self.allowed_user_id or 
                message.chat.id == self.bot_id)

    def register_handlers(self):
        """Register all message handlers"""
        @self.bot.on_message(filters.create(lambda _, __, m: self.is_authorized_chat(m)))
        async def handle_all_messages(client: Client, message: Message):
            if self.waiting_for_user:
                # First message after startup - store user ID
                if message.chat.id == self.bot_id and message.from_user:
                    self.allowed_user_id = message.from_user.id
                    self.waiting_for_user = False
                    await message.reply_text(
                        f"✅ Authorized user set: {self.allowed_user_id}\n"
                        "Bot is now ready to receive your commands."
                    )
                    print(f"🔑 Authorized user set: {self.allowed_user_id}")
                return
            
            # Process commands normally after setup
            if message.text and message.text.startswith("/"):
                await self.process_command(message)
            elif self.combined.state.get('active'):
                await self.combined.handle_message_flow(message)
            elif self.forwarder.state.get('active'):
                await self.forwarder.handle_setup_message(message)

        @self.bot.on_message(~filters.create(lambda _, __, m: self.is_authorized_chat(m)))
        async def ignore_other_messages(_, message: Message):
            print(f"🚫 Ignored message from {message.from_user.id if message.from_user else 'unknown'} in chat {message.chat.id}")

    async def process_command(self, message: Message):
        """Process bot commands"""
        command = message.text.split()[0].lower()
        
        if command == "/start":
            await message.reply_text(
                "🤖 Secure Bot\n\n"
                "Available commands:\n"
                "/cl - Process links\n"
                "/forward - Forward messages\n"
                "/cancel - Cancel operation\n"
                "/help - Show help"
            )
        elif command == "/forward":
            await self.forwarder.start_forward_setup(message)
        elif command == "/cl":
            await self.combined.start_combined_process(message)
        elif command == "/cancel":
            self.combined.reset_state()
            self.forwarder.reset_state()
            await message.reply_text("⏹ Operation cancelled")
        elif command == "/help":
            await message.reply_text(
                "🆘 Help Information\n\n"
                "/cl - Process links\n"
                "/forward - Forward messages\n"
                "/cancel - Cancel operation"
            )

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
