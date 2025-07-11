import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatType
import logging

class SecureBot:
    def __init__(self):
        self.user_client = None
        self.bot_client = None
        self.bot_id = None
        self.bot_username = None
        self.user_id = None
        self.user_username = None
        self.forwarder = None
        self.logger = self._setup_logger()

    def _setup_logger(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)

    async def _validate_env(self):
        required_vars = {
            "API_ID": int,
            "API_HASH": str,
            "BOT_TOKEN": str,
            "SESSION_STRING": str
        }
        missing = []
        for var, var_type in required_vars.items():
            val = os.environ.get(var)
            if not val:
                missing.append(var)
            try:
                required_vars[var] = var_type(val)
            except (ValueError, TypeError):
                raise ValueError(f"Invalid type for {var}")
        
        if missing:
            raise ValueError(f"Missing env vars: {', '.join(missing)}")
        return required_vars

    async def initialize_identity(self):
        """Get bot identity from token"""
        env_vars = await self._validate_env()
        
        async with Client(
            "temp_bot",
            api_id=env_vars["API_ID"],
            api_hash=env_vars["API_HASH"],
            bot_token=env_vars["BOT_TOKEN"],
            in_memory=True
        ) as temp_bot:
            bot_me = await temp_bot.get_me()
            self.bot_id = bot_me.id
            self.bot_username = bot_me.username
            self.logger.info(f"Bot Identity: @{self.bot_username} (ID: {self.bot_id})")

    async def initialize_user_session(self):
        """Get user identity from session"""
        env_vars = await self._validate_env()
        
        async with Client(
            "temp_user",
            api_id=env_vars["API_ID"],
            api_hash=env_vars["API_HASH"],
            session_string=env_vars["SESSION_STRING"],
            in_memory=True
        ) as temp_user:
            user_me = await temp_user.get_me()
            self.user_id = user_me.id
            self.user_username = user_me.username
            self.logger.info(f"User Identity: @{self.user_username} (ID: {self.user_id})")

    async def initialize_clients(self):
        """Initialize operational clients"""
        env_vars = await self._validate_env()
        
        self.bot_client = Client(
            "bot_instance",
            api_id=env_vars["API_ID"],
            api_hash=env_vars["API_HASH"],
            bot_token=env_vars["BOT_TOKEN"]
        )
        
        self.user_client = Client(
            "user_session",
            api_id=env_vars["API_ID"],
            api_hash=env_vars["API_HASH"],
            session_string=env_vars["SESSION_STRING"]
        )

    async def run(self):
        try:
            # Step 1: Get identities
            await self.initialize_identity()
            await self.initialize_user_session()
            
            # Step 2: Initialize clients
            await self.initialize_clients()
            
            # Initialize forwarder
            from forward import ForwardBot
            self.forwarder = ForwardBot(self.user_client)
            
            # Start clients
            await self.user_client.start()
            await self.bot_client.start()
            
            self.logger.info(f"Operational: Bot @{self.bot_username} | User @{self.user_username}")

            @self.bot_client.on_message(filters.all)
            async def handle_all_messages(client: Client, message: Message):
                if self._should_ignore(message):
                    self._log_ignored_message(message)
                    return
                
                if message.text and message.text.startswith('/'):
                    await self._handle_command(message)
                else:
                    await self._handle_message(message)

            await asyncio.Event().wait()

        except Exception as e:
            self.logger.critical(f"Fatal error: {e}", exc_info=True)
        finally:
            await self._shutdown()

    def _should_ignore(self, message: Message) -> bool:
        """Determine if message should be ignored"""
        if not message.chat:
            return True
            
        return not (
            message.chat.type == ChatType.PRIVATE and 
            message.chat.id == self.bot_id
        )

    def _log_ignored_message(self, message: Message):
        """Log ignored messages with details"""
        if message.chat:
            chat_type = message.chat.type.value
            chat_id = message.chat.id
            sender = getattr(message.from_user, 'id', None)
            
            if message.chat.type == ChatType.PRIVATE:
                log_msg = f"🚫 Ignored private message from {sender} (chat ID: {chat_id})"
            else:
                chat_title = getattr(message.chat, 'title', 'Untitled')
                log_msg = (f"🚫 Ignored {chat_type} message from {sender} "
                          f"in {chat_title} (ID: {chat_id})")
        else:
            log_msg = "🚫 Ignored message with no chat info"
            
        self.logger.info(log_msg)

    async def _handle_command(self, message: Message):
        """Handle bot commands"""
        try:
            if message.command[0] == "start":
                await message.reply(
                    "🤖 **Bot Menu**\n\n"
                    "/forward - Setup forwarding\n"
                    "/cancel - Cancel operation"
                )
            elif message.command[0] == "forward":
                await self.forwarder.start_forward_setup(message)
            elif message.command[0] == "cancel":
                self.forwarder.reset_state()
                await message.reply("✅ Operation cancelled")
        except Exception as e:
            self.logger.error(f"Command error: {e}")
            await message.reply("⚠️ An error occurred")

    async def _handle_message(self, message: Message):
        """Handle non-command messages"""
        if self.forwarder.is_active():
            await self.forwarder.handle_message(message)
        else:
            self.logger.info(f"Received non-command message in bot chat: {message.text}")
            await message.reply("ℹ️ Send /start to begin")

    async def _shutdown(self):
        """Clean shutdown sequence"""
        shutdown_tasks = []
        
        if self.bot_client and await self.bot_client.is_initialized:
            shutdown_tasks.append(self.bot_client.stop())
            self.logger.info("Bot client stopped")
        
        if self.user_client and await self.user_client.is_initialized:
            shutdown_tasks.append(self.user_client.stop())
            self.logger.info("User client stopped")
        
        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks)
        
        self.logger.info("All clients stopped gracefully")

if __name__ == "__main__":
    # Create required directories
    os.makedirs("forward_temp", exist_ok=True)
    
    # Run the bot
    bot = SecureBot()
    
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"💥 Critical error: {e}")
