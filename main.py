import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode, ChatType

class AuthManager:
    def __init__(self):
        self.owner_id = None
        self.bot_id = None
    
    async def initialize(self, client: Client):
        """Detect owner and bot IDs automatically"""
        self.bot_id = (await client.get_me()).id
        if client.session_string:
            user_client = Client(
                "user_account", 
                session_string=client.session_string
            )
            await user_client.start()
            self.owner_id = (await user_client.get_me()).id
            await user_client.stop()
            print(f"🆔 Owner ID detected: {self.owner_id}")

class BotController:
    def __init__(self):
        self.auth = AuthManager()
        self.bot = Client(
            "secure_bot",
            api_id=int(os.environ["API_ID"]),
            api_hash=os.environ["API_HASH"],
            bot_token=os.environ["BOT_TOKEN"],
            session_string=os.environ.get("SESSION_STRING")
        )
        self.forwarder = None

    async def is_authorized(self, _, __, message: Message):
        """Multi-layer security check"""
        if not message.from_user:
            return False
            
        # From owner
        if message.from_user.id != self.auth.owner_id:
            return False
            
        # In private chats or where bot is member
        if message.chat.type == ChatType.PRIVATE:
            return True
            
        try:
            member = await self.bot.get_chat_member(message.chat.id, "me")
            return member.status in ["member", "administrator", "creator"]
        except:
            return False

    async def start_bot(self):
        """Initialize and run the bot"""
        await self.auth.initialize(self.bot)
        
        # Command handlers
        @self.bot.on_message(
            filters.command("start") & 
            filters.create(self.is_authorized)
        )
        async def start(_, message: Message):
            await message.reply(
                f"🔒 <b>Authorized Control Panel</b>\n\n"
                f"Owner ID: <code>{self.auth.owner_id}</code>\n"
                f"Bot ID: <code>{self.auth.bot_id}</code>\n\n"
                "Available commands:\n"
                "/forward - Message forwarding\n"
                "/cancel - Cancel operation",
                parse_mode=ParseMode.HTML
            )

        @self.bot.on_message(
            filters.command("forward") & 
            filters.private & 
            filters.create(self.is_authorized)
        )
        async def forward_cmd(_, message: Message):
            from forward import ForwardBot
            self.forwarder = ForwardBot(self.bot)
            await self.forwarder.start_forward_setup(message)

        @self.bot.on_message(
            filters.command("cancel") & 
            filters.create(self.is_authorized)
        )
        async def cancel_cmd(_, message: Message):
            if self.forwarder:
                self.forwarder.reset_state()
            await message.reply("🛑 All operations cancelled")

        # Global security filter
        @self.bot.on_message(~filters.create(self.is_authorized))
        async def ignore_unauthorized(_, __):
            return

        # Start the bot
        await self.bot.start()
        print(f"✅ Bot @{(await self.bot.get_me()).username} is running")
        await asyncio.Event().wait()  # Run indefinitely

if __name__ == "__main__":
    controller = BotController()
    
    try:
        asyncio.run(controller.start_bot())
    except KeyboardInterrupt:
        print("🛑 Bot stopped gracefully")
    except Exception as e:
        print(f"💥 Critical error: {e}")
