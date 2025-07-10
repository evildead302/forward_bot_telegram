import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, BotCommand
from pyrogram.enums import ParseMode, ChatType

class SecureBot:
    def __init__(self):
        # Validate essential environment variables
        self._validate_env_vars()
        
        # Initialize both bot and user clients
        self.bot = Client(
            "bot_account",
            api_id=int(os.environ["API_ID"]),
            api_hash=os.environ["API_HASH"],
            bot_token=os.environ["BOT_TOKEN"],
            in_memory=True
        )
        
        # User client initialization (if session string exists)
        self.user = None
        self.owner_id = None
        self.bot_id = None
        self.is_user_session = bool(os.environ.get("SESSION_STRING"))

    def _validate_env_vars(self):
        """Validate required environment variables"""
        required_vars = ["API_ID", "API_HASH", "BOT_TOKEN"]
        missing_vars = [var for var in required_vars if not os.environ.get(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    async def initialize(self):
        """Initialize both bot and user sessions"""
        # Start bot client
        await self.bot.start()
        self.bot_id = (await self.bot.get_me()).id
        
        # Initialize user session if SESSION_STRING exists
        if self.is_user_session:
            self.user = Client(
                "user_account",
                api_id=int(os.environ["API_ID"]),  # Added API credentials
                api_hash=os.environ["API_HASH"],   # for user client
                session_string=os.environ["SESSION_STRING"],
                in_memory=True
            )
            await self.user.start()
            self.owner_id = (await self.user.get_me()).id
            print(f"👤 User session ready | ID: {self.owner_id}")
            
            # Set user client for modules that need it
            self._set_user_client_for_modules()
        else:
            print("⚠️ Running in bot-only mode")

        print(f"🤖 Bot ready | ID: {self.bot_id}")

    def _set_user_client_for_modules(self):
        """Inject user client into modules that need it"""
        # Assuming your c_l module can accept user client
        if hasattr(self, 'combined') and hasattr(self.combined, 'set_user_client'):
            self.combined.set_user_client(self.user)
        if hasattr(self, 'forwarder') and hasattr(self.forwarder, 'set_user_client'):
            self.forwarder.set_user_client(self.user)

    async def is_authorized(self, _, message: Message):
        """Check if message is from authorized source"""
        if not message.from_user:
            return False
            
        # Allow if from owner (when user session exists) or the bot itself
        authorized_ids = [self.bot_id]
        if self.is_user_session:
            authorized_ids.append(self.owner_id)
            
        if message.from_user.id in authorized_ids:
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
            await self._register_commands()
            
            # Setup handlers
            self._setup_handlers()

            print("🚀 Bot is now running")
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
            BotCommand("forward", "Message forwarding"),
            BotCommand("cl", "Link forwarder"), 
            BotCommand("cancel", "Cancel operations")
        ]
        await self.bot.set_bot_commands(commands)

    def _setup_handlers(self):
        """Setup all message handlers"""
        auth_filter = filters.create(self.is_authorized)

        @self.bot.on_message(filters.command("start") & auth_filter)
        async def start(_, message: Message):
            text = [
                f"🔐 <b>Authorized Session</b>",
                f"🤖 Bot ID: <code>{self.bot_id}</code>"
            ]
            
            if self.is_user_session:
                text.insert(1, f"👤 Owner ID: <code>{self.owner_id}</code>")
                
            text.extend([
                "",
                "<b>Commands:</b>",
                "/forward - Message forwarding",
                "/cl - Link forwarder",
                "/cancel - Stop operations"
            ])
            
            await message.reply_text("\n".join(text), parse_mode=ParseMode.HTML)

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

    async def _shutdown(self):
        """Proper shutdown sequence"""
        print("\n🛑 Shutting down...")
        if self.bot.is_initialized:
            await self.bot.stop()
        if self.is_user_session and self.user and self.user.is_initialized:
            await self.user.stop()
        print("✅ Shutdown complete")

if __name__ == "__main__":
    bot = SecureBot()
    
    # Create and manage event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        print("\n🛑 Received shutdown signal")
    except Exception as e:
        print(f"💥 Critical error: {e}")
    finally:
        loop.close()
