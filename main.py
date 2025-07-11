import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

class SecureBot:
    def __init__(self):
        self.bot = None
        self.bot_id = None
        # Set this to your bot's username (without @)
        self.bot_username = "Saverestrictcontant2_bot"  
        self.combined = None
        self.forwarder = None

    async def initialize(self):
        """Initialize the bot client"""
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
        print(f"✅ Bot @{self.bot_username} ready (ID: {self.bot_id})")
        print(f"🔷 Will ONLY respond in @{self.bot_username}'s chat")

        # Initialize modules
        import c_l
        from forward import ForwardBot
        self.combined = c_l.CombinedLinkForwarder(self.bot)
        self.forwarder = ForwardBot(self.bot)

    def is_bots_own_chat(self, message: Message):
        """Check if message is in bot's own chat"""
        return (message.chat.username and 
                message.chat.username.lower() == self.bot_username.lower())

    async def run(self):
        try:
            await self.initialize()
            
            @self.bot.on_message(filters.create(
                lambda _, __, m: self.is_bots_own_chat(m)
            ))
            async def handle_bot_chat(client: Client, message: Message):
                print(f"📩 New message in bot's chat")
                if message.text and message.text.startswith('/'):
                    await self.process_commands(message)
                else:
                    await self.process_messages(message)

            @self.bot.on_message(~filters.create(
                lambda _, __, m: self.is_bots_own_chat(m)
            ))
            async def ignore_others(client: Client, message: Message):
                pass  # Complete silent ignore

            await asyncio.Event().wait()

        except Exception as e:
            print(f"💥 Error: {e}")
        finally:
            if self.bot:
                await self.bot.stop()
                print("✅ Bot stopped")

    async def process_commands(self, message: Message):
        """Handle commands in bot's chat"""
        if message.text.startswith('/start'):
            await message.reply("🤖 Bot is active in this chat")
        elif message.text.startswith('/forward'):
            await self.forwarder.start_forward_setup(message)
        elif message.text.startswith('/cl'):
            await self.combined.start_combined_process(message)
        elif message.text.startswith('/cancel'):
            self.forwarder.reset_state()
            self.combined.reset_state()
            await message.reply("🛑 Operations cancelled")

    async def process_messages(self, message: Message):
        """Handle non-command messages in bot's chat"""
        if self.forwarder.state.get('active'):
            await self.forwarder.handle_setup_message(message)
        elif self.combined.state.get('active'):
            if not self.combined.state.get('destination_chat'):
                await self.combined.handle_destination_input(message)
            else:
                await self.combined.handle_link_collection(message)

if __name__ == "__main__":
    os.makedirs("temp_cl_data", exist_ok=True)
    os.makedirs("forward_temp", exist_ok=True)
    
    bot = SecureBot()
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    finally:
        loop.close()
