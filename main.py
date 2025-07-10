import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, BotCommand
from pyrogram.enums import ParseMode, ChatType

class SecureBot:
    def __init__(self):
        # Bot account (required)
        self.bot = Client(
            "bot_account",
            api_id=int(os.environ["API_ID"]),
            api_hash=os.environ["API_HASH"],
            bot_token=os.environ["BOT_TOKEN"],
            in_memory=True
        )
        
        # User account (optional)
        self.user = None
        self.owner_id = None
        self.bot_id = None

    async def initialize(self):
        """Initialize both bot and user sessions"""
        # Start bot client
        await self.bot.start()
        self.bot_id = (await self.bot.get_me()).id
        
        # Initialize user session if SESSION_STRING exists
        if os.environ.get("SESSION_STRING"):
            self.user = Client(
                "user_account",
                session_string=os.environ["SESSION_STRING"],
                in_memory=True
            )
            await self.user.start()
            self.owner_id = (await self.user.get_me()).id
            print(f"👤 User session ready | ID: {self.owner_id}")
        else:
            print("⚠️ No user session configured")

        # Initialize modules
        from forward import ForwardBot
        import c_l
        self.forwarder = ForwardBot(self.bot)
        self.combined = c_l.CombinedLinkForwarder(self.bot)

        print(f"✅ Bot ready | Owner: {self.owner_id} | Bot: {self.bot_id}")

    async def is_authorized(self, _, message: Message):
        """Check if message is from authorized source"""
        if not message.from_user:
            return False
            
        # Allow if from owner (when session exists) or the bot itself
        if message.from_user.id in [self.owner_id, self.bot_id]:
            # For groups/channels, verify bot is member
            if message.chat.type != ChatType.PRIVATE:
                try:
                    member = await self.bot.get_chat_member(message.chat.id, "me")
                    return member.status in ["member", "administrator", "creator"]
                except:
                    return False
            return True
        return False

    async def run(self):
        """Main bot operation"""
        try:
            await self.initialize()
            
            # Register bot commands
            await self.bot.set_bot_commands([
                BotCommand("start", "Show bot info"),
                BotCommand("forward", "Message forwarding"),
                BotCommand("cl", "Link forwarder"), 
                BotCommand("cancel", "Cancel operations")
            ])

            # Create authorization filter
            auth_filter = filters.create(self.is_authorized)

            # Command handlers
            @self.bot.on_message(filters.command("start") & auth_filter)
            async def start(_, message: Message):
                await message.reply_text(
                    f"🔐 <b>Authorized Session</b>\n\n"
                    f"👤 Owner ID: <code>{self.owner_id}</code>\n"
                    f"🤖 Bot ID: <code>{self.bot_id}</code>\n\n"
                    "<b>Commands:</b>\n"
                    "/forward - Message forwarding\n"
                    "/cl - Link forwarder\n"
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

            # Message handler
            @self.bot.on_message(auth_filter)
            async def handle_messages(_, message: Message):
                if self.forwarder.state.get('active'):
                    await self.forwarder.handle_setup_message(message)
                elif self.combined.state.get('active'):
                    if not self.combined.state.get('destination_chat'):
                        await self.combined.handle_destination_input(message)
                    else:
                        await self.combined.handle_link_collection(message)

            # Ignore all unauthorized messages
            @self.bot.on_message(~auth_filter)
            async def ignore_unauthorized(_, __):
                return

            print("🚀 Bot is now running")
            await asyncio.Event().wait()  # Run forever

        except Exception as e:
            print(f"💥 Error: {str(e)}")
        finally:
            # Proper shutdown sequence
            if hasattr(self, 'bot') and self.bot.is_initialized:
                await self.bot.stop()
            if hasattr(self, 'user') and self.user and self.user.is_initialized:
                await self.user.stop()
            print("🛑 Bot shutdown complete")

if __name__ == "__main__":
    # Create and manage event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        bot = SecureBot()
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        print("\n🛑 Received shutdown signal")
    finally:
        loop.close()
