import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, BotCommand
from pyrogram.enums import ParseMode, ChatType

class BotManager:
    def __init__(self):
        self.bot = Client(
            "secure_bot",
            api_id=int(os.environ["API_ID"]),
            api_hash=os.environ["API_HASH"],
            bot_token=os.environ["BOT_TOKEN"],
            session_string=os.environ.get("SESSION_STRING")
        )
        self.owner_id = None
        self.bot_id = None
        self.forwarder = None
        self.combined = None

    async def initialize(self):
        # Start the bot client first
        await self.bot.start()
        self.bot_id = (await self.bot.get_me()).id
        
        # Initialize owner session if available
        if self.bot.session_string:
            user_client = Client("owner_session", session_string=self.bot.session_string)
            await user_client.start()
            self.owner_id = (await user_client.get_me()).id
            await user_client.stop()

        # Initialize modules after client is ready
        import forward
        import c_l
        self.forwarder = forward.ForwardBot(self.bot)
        self.combined = c_l.CombinedLinkForwarder(self.bot)

        print(f"✅ Bot initialized | Owner: {self.owner_id} | Bot: {self.bot_id}")

    async def is_authorized(self, _, __, message: Message):
        if not message.from_user:
            return False
        if message.from_user.id not in [self.owner_id, self.bot_id]:
            return False
        if message.chat.type == ChatType.PRIVATE:
            return True
        try:
            member = await self.bot.get_chat_member(message.chat.id, "me")
            return member.status in ["member", "administrator", "creator"]
        except:
            return False

    async def run(self):
        await self.initialize()
        
        # Register commands
        await self.bot.set_bot_commands([
            BotCommand("start", "Show bot info"),
            BotCommand("cl", "Link forwarder"),
            BotCommand("forward", "Message forwarder"),
            BotCommand("cancel", "Cancel operations")
        ])

        # Command handlers
        @self.bot.on_message(filters.command("start") & filters.create(self.is_authorized))
        async def start(_, message: Message):
            await message.reply_text(
                f"👑 Owner ID: <code>{self.owner_id}</code>\n"
                f"🤖 Bot ID: <code>{self.bot_id}</code>\n\n"
                "Commands:\n/cl /forward /cancel",
                parse_mode=ParseMode.HTML
            )

        @self.bot.on_message(filters.command("forward") & filters.private & filters.create(self.is_authorized))
        async def forward_cmd(_, message: Message):
            await self.forwarder.start_forward_setup(message)

        @self.bot.on_message(filters.command("cl") & filters.create(self.is_authorized))
        async def combined_cmd(_, message: Message):
            await self.combined.start_combined_process(message)

        @self.bot.on_message(filters.command("cancel") & filters.create(self.is_authorized))
        async def cancel_cmd(_, message: Message):
            self.forwarder.reset_state()
            self.combined.reset_state()
            await message.reply_text("🛑 Operations cancelled")

        # Message handler
        @self.bot.on_message(filters.create(self.is_authorized))
        async def handle_messages(_, message: Message):
            if self.forwarder.state.get('active'):
                await self.forwarder.handle_setup_message(message)
            elif self.combined.state.get('active'):
                if not self.combined.state.get('destination_chat'):
                    await self.combined.handle_destination_input(message)
                else:
                    await self.combined.handle_link_collection(message)

        # Ignore unauthorized
        @self.bot.on_message(~filters.create(self.is_authorized))
        async def ignore_unauthorized(_, __):
            return

        print("🚀 Bot is now running")
        await asyncio.Event().wait()  # Run forever

if __name__ == "__main__":
    manager = BotManager()
    try:
        asyncio.run(manager.run())
    except KeyboardInterrupt:
        print("🛑 Bot stopped by user")
    except Exception as e:
        print(f"💥 Bot crashed: {str(e)}")
    finally:
        asyncio.run(manager.bot.stop())
