import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

# ===== CONFIG =====
BOT_USERNAME = "@Saverestrictcontant2_bot"  # Change this to your bot's username
# ==================

class SimpleBot:
    def __init__(self):
        self.bot = None
        self.user = None
        self.bot_username = BOT_USERNAME.lower().strip("@")
        self.forwarder = None

    async def initialize(self):
        """Initialize both clients in one go"""
        self.bot = Client(
            "my_bot",
            api_id=int(os.environ["API_ID"]),
            api_hash=os.environ["API_HASH"],
            bot_token=os.environ["BOT_TOKEN"]
        )
        
        self.user = Client(
            "my_user",
            api_id=int(os.environ["API_ID"]),
            api_hash=os.environ["API_HASH"],
            session_string=os.environ["SESSION_STRING"]
        )

        await self.bot.start()
        await self.user.start()
        
        # Verify bot username
        me = await self.bot.get_me()
        print(f"🤖 Bot @{me.username} ready!")
        print(f"👤 User {self.user.storage.first_name} ready!")

    async def run(self):
        await self.initialize()
        
        # Initialize forwarder (create forward.py with your forwarding logic)
        from forward import Forwarder
        self.forwarder = Forwarder(self.user)

        @self.bot.on_message(filters.private)
        async def handle_messages(_, message: Message):
            # Check if message is for our bot
            if message.chat.username.lower() != self.bot_username:
                print(f"🚫 Ignored message from @{message.chat.username}")
                return
                
            if message.text.startswith('/start'):
                await message.reply(f"Hello! I'm {BOT_USERNAME}\nUse /forward to start")
            elif message.text.startswith('/forward'):
                await self.forwarder.start(message)
            elif message.text.startswith('/cancel'):
                self.forwarder.cancel()
                await message.reply("Operation cancelled")
            else:
                if self.forwarder.is_active:
                    await self.forwarder.handle(message)
                else:
                    await message.reply("Send /forward to begin")

        print(f"✅ {BOT_USERNAME} is listening...")
        await asyncio.Event().wait()  # Run forever

    async def shutdown(self):
        await self.bot.stop()
        await self.user.stop()
        print("🛑 Bot stopped")

if __name__ == "__main__":
    # Check required env variables
    required = ["API_ID", "API_HASH", "BOT_TOKEN", "SESSION_STRING"]
    if not all(os.environ.get(x) for x in required):
        print("❌ Missing environment variables")
        exit(1)

    bot = SimpleBot()
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        asyncio.run(bot.shutdown())
    except Exception as e:
        print(f"💥 Error: {e}")
        asyncio.run(bot.shutdown())
