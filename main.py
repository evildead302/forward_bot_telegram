import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, BotCommand
from pyrogram.enums import ParseMode, ChatType

class SecureBot:
    def __init__(self):
        # Validate essential environment variables
        self._validate_env_vars()
        
        # Initialize bot client
        self.bot = Client(
            "bot_account",
            api_id=int(os.environ["API_ID"]),
            api_hash=os.environ["API_HASH"],
            bot_token=os.environ["BOT_TOKEN"],
            in_memory=True
        )
        self.bot_id = None
        self.combined = None

    def _validate_env_vars(self):
        """Validate required environment variables"""
        required_vars = ["API_ID", "API_HASH", "BOT_TOKEN"]
        missing_vars = [var for var in required_vars if not os.environ.get(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    async def initialize(self):
        """Initialize bot session and modules"""
        await self.bot.start()
        self.bot_id = (await self.bot.get_me()).id
        
        # Initialize modules
        import c_l  # Your custom module
        self.combined = c_l.CombinedLinkForwarder(self.bot)
        
        print(f"🤖 Bot ready | ID: {self.bot_id}")

    async def is_authorized(self, _, message: Message):
        """
        Only allow messages sent directly to the bot chat
        (No groups/channels/private chats)
        """
        return message.chat.type == ChatType.BOT

    async def run(self):
        """Main bot operation"""
        try:
            await self.initialize()
            
            # Register bot commands
            await self._register_commands()
            
            # Setup handlers
            self._setup_handlers()

            print("🚀 Bot is now running (only responds in bot chat)")
            await asyncio.Event().wait()  # Run forever

        except Exception as e:
            print(f"💥 Error: {str(e)}")
            raise
        finally:
            await self._shutdown()

    async def _register_commands(self):
        """Register bot commands"""
        commands = [
            BotCommand("start", "Show bot info"),
            BotCommand("cl", "Link forwarder"), 
            BotCommand("cancel", "Cancel operations")
        ]
        await self.bot.set_bot_commands(commands)

    def _setup_handlers(self):
        """Setup all message handlers"""
        auth_filter = filters.create(self.is_authorized)

        @self.bot.on_message(filters.command("start") & auth_filter)
        async def start(_, message: Message):
            await message.reply_text(
                "🤖 **Combined Link Forwarder Bot**\n\n"
                "**Commands:**\n"
                "/cl - Start link processing\n"
                "/cancel - Cancel current operation",
                parse_mode=ParseMode.HTML
            )

        @self.bot.on_message(filters.command("cl") & auth_filter)
        async def combined_cmd(_, message: Message):
            await self.combined.start_combined_process(message)

        @self.bot.on_message(filters.command("cancel") & auth_filter)
        async def cancel_cmd(_, message: Message):
            self.combined.reset_state()
            await message.reply_text("🛑 Operation cancelled")

        @self.bot.on_message(auth_filter)
        async def handle_messages(_, message: Message):
            if self.combined.state.get('active'):
                if not self.combined.state.get('destination_chat'):
                    await self.combined.handle_destination_input(message)
                else:
                    await self.combined.handle_link_collection(message)

        @self.bot.on_message(~auth_filter)
        async def ignore_unauthorized(_, message: Message):
            print(f"Ignored message from chat {message.chat.id} (type: {message.chat.type})")

    async def _shutdown(self):
        """Proper shutdown sequence"""
        print("\n🛑 Shutting down...")
        if self.bot.is_initialized:
            await self.bot.stop()
        print("✅ Shutdown complete")

if __name__ == "__main__":
    # Create and manage event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        bot = SecureBot()
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        print("\n🛑 Received shutdown signal")
    except Exception as e:
        print(f"💥 Critical error: {e}")
    finally:
        loop.close()
