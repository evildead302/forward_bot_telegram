import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatType

class SecureBot:
    def __init__(self):
        self.client = None  # User session client
        self.bot = None     # Bot client
        self.bot_id = None
        self.bot_username = None

    async def initialize(self):
        """Initialize both user session and bot"""
        # User session (for accessing chats)
        self.client = Client(
            "user_session",
            api_id=int(os.environ.get("API_ID", 0)),
            api_hash=os.environ.get("API_HASH", ""),
            session_string=os.environ.get("SESSION_STRING", "")
        )

        # Bot instance (for receiving commands)
        self.bot = Client(
            "bot_instance",
            api_id=int(os.environ.get("API_ID", 0)),
            api_hash=os.environ.get("API_HASH", ""),
            bot_token=os.environ.get("BOT_TOKEN", "")
        )

        await self.client.start()
        await self.bot.start()

        # Get bot identity from the bot token
        bot_me = await self.bot.get_me()
        self.bot_id = bot_me.id
        self.bot_username = bot_me.username
        print(f"✅ Bot @{self.bot_username} (ID: {self.bot_id}) ready")

        # Initialize modules with both clients
        import c_l
        from forward import ForwardBot
        self.combined = c_l.CombinedLinkForwarder(self.client, self.bot)
        self.forwarder = ForwardBot(self.client, self.bot)

    def is_bot_private_chat(self, message: Message):
        """Check if message is in bot's private chat"""
        return (message.chat.type == ChatType.PRIVATE and 
                message.chat.id == self.bot_id)

    async def run(self):
        try:
            await self.initialize()
            print(f"🚀 Bot @{self.bot_username} is now running")

            @self.bot.on_message(filters.create(
                lambda _, __, m: self.is_bot_private_chat(m))
            )
            async def handle_bot_messages(client: Client, message: Message):
                print(f"📩 Received in bot chat (ID: {message.chat.id})")
                if message.text and message.text.startswith('/'):
                    await self.process_commands(message)
                else:
                    await self.process_messages(message)

            @self.bot.on_message(~filters.create(
                lambda _, __, m: self.is_bot_private_chat(m))
            )
            async def ignore_others(client: Client, message: Message):
                if message.chat.type == ChatType.PRIVATE:
                    print(f"🚫 Ignored private message from {message.from_user.id}")
                else:
                    print(f"🚫 Ignored group/channel message from {message.chat.id}")

            await asyncio.Event().wait()

        except Exception as e:
            print(f"💥 Error: {e}")
        finally:
            if self.bot and await self.bot.is_initialized:
                await self.bot.stop()
            if self.client and await self.client.is_initialized:
                await self.client.stop()
            print("✅ All clients stopped")

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
