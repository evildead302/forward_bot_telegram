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
            import c_l
            from forward import ForwardBot
            self.combined = c_l.CombinedLinkForwarder(self.bot)
            self.forwarder = ForwardBot(self.bot)
            print("✅ Modules loaded")

            self.register_handlers()

        except Exception as e:
            print(f"❌ Initialization failed: {e}")
            await self.shutdown()
            raise

    def is_bot_chat(self, message: Message):
        """Fixed strict check that allows bot's own messages"""
        # Allow bot's own messages
        if message.from_user and message.from_user.id == self.bot_id:
            return True
            
        # Strict check for user messages
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

        # [Rest of your command handlers...]

        @self.bot.on_message(
            (filters.text | filters.photo | filters.document |
             filters.video | filters.audio | filters.voice |
             filters.reply) & filters.create(lambda _, __, m: self.is_bot_chat(m)))
        async def handle_messages(client: Client, message: Message):
            # Skip processing if message is from bot itself
            if message.from_user and message.from_user.id == self.bot_id:
                return
                
            if self.combined.state.get('active'):
                await self.combined.handle_message_flow(message)
            elif self.forwarder.state.get('active'):
                await self.forwarder.handle_setup_message(message)

        @self.bot.on_message(~filters.create(lambda _, __, m: self.is_bot_chat(m)))
        async def ignore_other_messages(_, message: Message):
            # Skip logging for bot's own messages
            if message.from_user and message.from_user.id == self.bot_id:
                return
                
            if message.chat.type == ChatType.PRIVATE:
                await message.reply(f"❌ Please message @{self.bot_username} directly.")
            print(f"🚫 Ignored message from {message.from_user.id if message.from_user else 'unknown'} in chat {message.chat.id}")

    # [Rest of your class methods...]

if __name__ == "__main__":
    # [Rest of your main code...]
