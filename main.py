import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, BotCommand
from pyrogram.enums import ParseMode, ChatType

class SecureBot:
    def __init__(self):
        self.bot = Client(
            "secure_session",
            api_id=int(os.environ["API_ID"]),
            api_hash=os.environ["API_HASH"],
            bot_token=os.environ["BOT_TOKEN"],
            session_string=os.environ.get("SESSION_STRING"),
            in_memory=True
        )
        self.owner_id = None
        self.bot_id = None

    async def initialize(self):
        """Initialize all components with proper loop management"""
        await self.bot.start()
        self.bot_id = (await self.bot.get_me()).id
        
        if self.bot.session_string:
            user_client = Client(
                "user_session",
                session_string=self.bot.session_string,
                in_memory=True
            )
            await user_client.start()
            self.owner_id = (await user_client.get_me()).id
            await user_client.stop()

        # Initialize modules after clients are ready
        from forward import ForwardBot
        import c_l
        self.forwarder = ForwardBot(self.bot)
        self.combined = c_l.CombinedLinkForwarder(self.bot)

        print(f"✅ Bot ready | Owner: {self.owner_id} | Bot: {self.bot_id}")

    async def is_authorized(self, _, __, message: Message):
        """Security verification"""
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
        """Main bot operation with proper loop handling"""
        try:
            await self.initialize()
            
            # Register commands
            await self.bot.set_bot_commands([
                BotCommand("start", "Bot information"),
                BotCommand("forward", "Message forwarding"),
                BotCommand("cl", "Link forwarding"),
                BotCommand("cancel", "Cancel operations")
            ])

            # Command handlers
            @self.bot.on_message(filters.command("start") & filters.create(self.is_authorized))
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
                await message.reply_text("🛑 All operations cancelled")

            # Message processing
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
            await asyncio.Event().wait()

        except asyncio.CancelledError:
            print("🛑 Received shutdown signal")
        except Exception as e:
            print(f"💥 Error: {str(e)}")
        finally:
            if hasattr(self, 'bot') and self.bot.is_initialized:
                await self.bot.stop()
            print("🛑 Bot shutdown complete")

async def main():
    bot = SecureBot()
    await bot.run()

if __name__ == "__main__":
    # Create and manage a single event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n🛑 Manual shutdown requested")
    finally:
        loop.close()
