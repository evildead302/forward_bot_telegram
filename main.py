import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatType

class SecureBot:
    def __init__(self):
        self.bot = None
        self.bot_id = None
        # Editable bot username (change this to your bot's username)
        self.bot_username = "Saverestrictcontant2_bot"  # EDIT THIS LINE WITH YOUR BOT USERNAME
        self.combined = None
        self.forwarder = None

    async def initialize(self):
        """Initialize with proper session handling"""
        self.bot = Client(
            "main_bot",
            api_id=int(os.environ.get("API_ID", 0)),
            api_hash=os.environ.get("API_HASH", ""),
            bot_token=os.environ.get("BOT_TOKEN", ""),
            session_string=os.environ.get("SESSION_STRING", "")
        )

        await self.bot.start()
        me = await self.bot.get_me()
        self.bot_id = me.id
        # Use the manually set username instead of getting from Telegram
        print(f"✅ Logged in as @{self.bot_username} (ID: {self.bot_id})")

        # Initialize only required modules
        import c_l
        from forward import ForwardBot
        self.combined = c_l.CombinedLinkForwarder(self.bot)
        self.forwarder = ForwardBot(self.bot)

    def is_bot_username_message(self, message: Message):
        """Check if message is directed to the bot username"""
        if message.text and f"@{self.bot_username}" in message.text:
            return True
        if message.reply_to_message and message.reply_to_message.from_user:
            return message.reply_to_message.from_user.username == self.bot_username
        return False

    async def run(self):
        try:
            await self.initialize()
            print(f"🚀 Bot @{self.bot_username} is now running")

            @self.bot.on_message(filters.create(
                lambda _, __, m: self.is_bot_username_message(m)
            ))
            async def handle_bot_username(client: Client, message: Message):
                print(f"📩 Received message for @{self.bot_username} in chat: {message.chat.id}")
                if message.text and message.text.startswith('/'):
                    await self.process_commands(message)
                else:
                    await self.process_messages(message)

            @self.bot.on_message(~filters.create(
                lambda _, __, m: self.is_bot_username_message(m)
            ))
            async def ignore_others(client: Client, message: Message):
                # Silent ignore of other messages
                pass

            await asyncio.Event().wait()

        except Exception as e:
            print(f"💥 Error: {e}")
        finally:
            if self.bot and await self.bot.is_initialized:
                await self.bot.stop()
                print("✅ Bot stopped")

    async def process_commands(self, message: Message):
        """Handle commands in bot's private chat"""
        if message.text.startswith('/start'):
            await message.reply_text(
                "🤖 Bot Menu\n\n"
                "/forward - Forward messages\n"
                "/cl - Combined operations\n"
                "/cancel - Cancel operation"
            )
        elif message.text.startswith('/forward'):
            await self.forwarder.start_forward_setup(message)
        elif message.text.startswith('/cl'):
            await self.combined.start_combined_process(message)
        elif message.text.startswith('/cancel'):
            self.forwarder.reset_state()
            self.combined.reset_state()
            await message.reply_text("⏹ Operations cancelled")

    async def process_messages(self, message: Message):
        """Handle non-command messages during operations"""
        if self.forwarder.state.get('active'):
            await self.forwarder.handle_setup_message(message)
        elif self.combined.state.get('active'):
            if not self.combined.state.get('destination_chat'):
                await self.combined.handle_destination_input(message)
            else:
                await self.combined.handle_link_collection(message)

if __name__ == "__main__":
    # Create required directories
    os.makedirs("temp_cl_data", exist_ok=True)
    os.makedirs("forward_temp", exist_ok=True)
    
    # Run the bot
    bot = SecureBot()
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    finally:
        loop.close()
