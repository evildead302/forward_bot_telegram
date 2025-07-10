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
        self.bot_username = me.username
        print(f"✅ Logged in as @{self.bot_username} (ID: {self.bot_id})")

        # Initialize only required modules
        import c_l
        from forward import ForwardBot
        self.combined = c_l.CombinedLinkForwarder(self.bot)
        self.forwarder = ForwardBot(self.bot)

    def is_bot_private_chat(self, message: Message):
        """Strict filter for bot's own private chat"""
        return (message.chat.type == ChatType.PRIVATE and 
                message.chat.id == self.bot_id)

    async def run(self):
        try:
            await self.initialize()
            print(f"🚀 Bot @{self.bot_username} is now running")

            @self.bot.on_message(filters.create(
                lambda _, __, m: self.is_bot_private_chat(m)
            ))
            async def handle_commands(client: Client, message: Message):
                print(f"📩 Received in bot's chat (ID: {message.chat.id})")
                if message.text.startswith('/'):
                    await self.process_commands(message)
                else:
                    await self.process_messages(message)

            @self.bot.on_message(~filters.create(
                lambda _, __, m: self.is_bot_private_chat(m)
            ))
            async def ignore_others(client: Client, message: Message):
                chat_type = "private chat" if message.chat.type == ChatType.PRIVATE else "group/channel"
                print(f"🚫 Ignored message from {chat_type} (ID: {message.chat.id})")

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
