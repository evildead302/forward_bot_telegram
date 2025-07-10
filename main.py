import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, BotCommand
from pyrogram.enums import ParseMode, ChatType

class SecureBot:
    def __init__(self):
        self.bot = Client(
            "bot_session",
            api_id=int(os.environ["API_ID"]),
            api_hash=os.environ["API_HASH"],
            bot_token=os.environ["BOT_TOKEN"],
            in_memory=True
        )
        
        self.user_client = None
        if os.environ.get("SESSION_STRING"):
            self.user_client = Client(
                "user_session",
                session_string=os.environ["SESSION_STRING"],
                in_memory=True
            )
        
        self.owner_id = None
        self.bot_id = None

    async def initialize(self):
        """Initialize all components"""
        await self.bot.start()
        self.bot_id = (await self.bot.get_me()).id
        
        if self.user_client:
            await self.user_client.start()
            self.owner_id = (await self.user_client.get_me()).id
        
        from forward import ForwardBot
        import c_l
        self.forwarder = ForwardBot(self.bot)
        self.combined = c_l.CombinedLinkForwarder(self.bot)

        print(f"✅ Bot ready | Owner: {self.owner_id} | Bot: {self.bot_id}")

    async def is_authorized(self, client: Client, message: Message):
        """Security verification (now properly takes 3 parameters)"""
        if not message.from_user:
            return False
        if self.owner_id and message.from_user.id != self.owner_id:
            return False
        if message.chat.type == ChatType.PRIVATE:
            return True
        try:
            member = await self.bot.get_chat_member(message.chat.id, "me")
            return member.status in ["member", "administrator", "creator"]
        except:
            return False

    async def run(self):
        """Main bot operation"""
        try:
            await self.initialize()
            
            if self.bot.is_initialized:
                await self.bot.set_bot_commands([
                    BotCommand("start", "Bot information"),
                    BotCommand("forward", "Message forwarding"),
                    BotCommand("cl", "Link forwarding"),
                    BotCommand("cancel", "Cancel operations")
                ])

            # Create filter instance bound to this object
            auth_filter = filters.create(self.is_authorized)

            @self.bot.on_message(filters.command("start") & auth_filter)
            async def start(_, message: Message):
                await message.reply_text(
                    f"👑 Owner: <code>{self.owner_id}</code>\n"
                    f"🤖 Bot: <code>{self.bot_id}</code>\n\n"
                    "Available commands:\n"
                    "/forward - Message forwarding\n"
                    "/cl - Link forwarding\n"
                    "/cancel - Stop operations",
                    parse_mode=ParseMode.HTML
                )

            @self.bot.on_message(filters.command("forward") & filters.private & auth_filter)
            async def forward_cmd(_, message: Message):
                await self.forwarder.start_forward_setup(message)

            @self.bot.on_message(filters.command("cl") & auth_filter)
            async def combined_cmd(_, message: Message):
                await self.combined.start_combined_process(message)

            @self.bot.on_message(filters.command("cancel") & auth_filter)
            async def cancel_cmd(_, message: Message):
                self.forwarder.reset_state()
                self.combined.reset_state()
                await message.reply_text("🛑 All operations cancelled")

            @self.bot.on_message(auth_filter)
            async def handle_messages(_, message: Message):
                if self.forwarder.state.get('active'):
                    await self.forwarder.handle_setup_message(message)
                elif self.combined.state.get('active'):
                    if not self.combined.state.get('destination_chat'):
                        await self.combined.handle_destination_input(message)
                    else:
                        await self.combined.handle_link_collection(message)

            @self.bot.on_message(~auth_filter)
            async def ignore_unauthorized(_, __):
                return

            print("🚀 Bot is now running")
            await asyncio.Event().wait()

        except Exception as e:
            print(f"💥 Error: {str(e)}")
        finally:
            if hasattr(self, 'bot') and self.bot.is_initialized:
                await self.bot.stop()
            if hasattr(self, 'user_client') and self.user_client and self.user_client.is_initialized:
                await self.user_client.stop()
            print("🛑 Bot shutdown complete")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        bot = SecureBot()
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        print("\n🛑 Manual shutdown requested")
    finally:
        loop.close()
