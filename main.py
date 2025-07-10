import os
import tempfile
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import MessageEntityType

# Global variables
bot = None
bot_username = None
combined = None
forwarder = None

async def initialize_bot():
    global bot, bot_username, combined, forwarder
    
    # Initialize bot client
    bot = Client(
        "main_bot",
        api_id=int(os.environ.get("API_ID", 0)),
        api_hash=os.environ.get("API_HASH", ""),
        bot_token=os.environ.get("BOT_TOKEN", ""),
        in_memory=True
    )
    
    await bot.start()
    me = await bot.get_me()
    bot_username = me.username.lower()
    print(f"🤖 Bot @{bot_username} initialized")

    # Initialize modules
    import c_l
    from forward import ForwardBot
    combined = c_l.CombinedLinkForwarder(bot)
    forwarder = ForwardBot(bot)
    print("✅ Modules loaded")

def is_bot_chat(_, __, message: Message):
    """Strict filter to only allow messages in bot's private chat"""
    if not message.chat.type == "private":
        return False
    if message.from_user and message.from_user.is_bot:
        return False
    return True

bot_chat_filter = filters.create(is_bot_chat)

@bot.on_message(filters.command("start") & bot_chat_filter)
async def start(client: Client, message: Message):
    await message.reply_text(
        "🤖 Combined Link Forwarder Bot\n\n"
        "Available commands:\n"
        "/cl - Process links\n"
        "/forward - Forward messages\n"
        "/cancel - Cancel operation\n"
        "/help - Show help"
    )

@bot.on_message(filters.command("forward") & bot_chat_filter)
async def forward_cmd(client: Client, message: Message):
    await forwarder.start_forward_setup(message)

@bot.on_message(filters.command("cl") & bot_chat_filter)
async def combined_cmd(client: Client, message: Message):
    await combined.start_combined_process(message)

@bot.on_message(filters.command("cancel") & bot_chat_filter)
async def cancel_cmd(client: Client, message: Message):
    combined.reset_state()
    forwarder.reset_state()
    await message.reply_text("⏹ Operation cancelled")

@bot.on_message(filters.command("help") & bot_chat_filter)
async def help_cmd(client: Client, message: Message):
    await message.reply_text(
        "🆘 Help Information\n\n"
        "/cl - Process links\n"
        "/forward - Forward messages\n"
        "/cancel - Cancel operation"
    )

@bot.on_message(
    (filters.text | filters.photo | filters.document |
     filters.video | filters.audio | filters.voice |
     filters.reply) & bot_chat_filter
)
async def handle_messages(client: Client, message: Message):
    if combined.state.get('active'):
        await combined.handle_message_flow(message)
    elif forwarder.state.get('active'):
        await forwarder.handle_setup_message(message)

@bot.on_message(~bot_chat_filter)
async def ignore_other_messages(_, message: Message):
    print(f"🚫 Ignored message from {message.chat.id}")

def create_temp_dirs():
    os.makedirs("temp_cl_data", exist_ok=True)
    os.makedirs("forward_temp", exist_ok=True)

async def run_bot():
    try:
        await initialize_bot()
        create_temp_dirs()
        print("🚀 Bot is now running")
        await asyncio.Event().wait()  # Run forever
    except Exception as e:
        print(f"💥 Error: {e}")
    finally:
        await safe_shutdown()

async def safe_shutdown():
    if bot and bot.is_initialized:
        try:
            await bot.stop()
            print("✅ Bot stopped gracefully")
        except Exception as e:
            print(f"⚠️ Error during shutdown: {e}")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_bot())
    except KeyboardInterrupt:
        print("\n🛑 Received shutdown signal")
    except Exception as e:
        print(f"💥 Fatal error: {e}")
    finally:
        loop.run_until_complete(safe_shutdown())
        loop.close()
