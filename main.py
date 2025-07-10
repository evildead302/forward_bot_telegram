import os
import tempfile
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import MessageEntityType

# Check if required module exists
try:
    import c_l
    print("✅ c_l module imported successfully")
except ImportError as e:
    print(f"❌ Missing module: {e}")
    raise

# Initialize bot with error handling
try:
    bot = Client(
        "main_bot",
        api_id=int(os.environ.get("API_ID", 0)),
        api_hash=os.environ.get("API_HASH", ""),
        bot_token=os.environ.get("BOT_TOKEN", ""),
        session_string=os.environ.get("SESSION_STRING", "")
    )
    print("✅ Bot client initialized")
except Exception as e:
    print(f"❌ Bot initialization failed: {e}")
    raise

# Initialize modules with verification
try:
    combined = c_l.CombinedLinkForwarder(bot)
    from forward import ForwardBot
    forwarder = ForwardBot(bot)
    print("✅ Modules initialized")
except Exception as e:
    print(f"❌ Module initialization failed: {e}")
    raise

# Get bot username
bot_username = None
async def get_bot_username():
    global bot_username
    me = await bot.get_me()
    bot_username = me.username.lower()
    print(f"🤖 Bot username: @{bot_username}")

def is_bot_private_chat(_, __, message: Message):
    """Strict filter to only allow messages in bot's own chat"""
    if not message.text:
        return False
    
    # Check if message is sent to bot's username
    if (message.chat.type == "private" and 
        message.text.startswith(f'@{bot_username}')):
        return True
    
    # Check if it's a direct command to the bot
    if (message.chat.type == "private" and 
        any(message.text.startswith(cmd) for cmd in ['/start', '/cl', '/forward', '/cancel', '/help'])):
        return True
    
    return False

bot_chat_filter = filters.create(is_bot_private_chat)

@bot.on_message(filters.command("start") & bot_chat_filter)
async def start(client: Client, message: Message):
    await message.reply_text(
        "🤖 Combined Link Forwarder Bot\n\n"
        "Available commands:\n"
        "/cl - Combined link clicker and forwarder\n"
        "/forward - Message forwarding\n"
        "/cancel - Cancel current operation\n"
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
    await message.reply_text("⏹ Operation cancelled and state reset")

@bot.on_message(filters.command("help") & bot_chat_filter)
async def help_cmd(client: Client, message: Message):
    await message.reply_text(
        "🆘 Help Information\n\n"
        "/cl - Combined link clicker and forwarder:\n"
        "1. First provide destination chat\n"
        "2. Then provide links to process\n"
        "3. Bot will click links and forward responses\n"
        "/forward - Forward messages between chats\n"
        "/cancel - Cancel current operation\n"
    )

def has_quote_entities(filter, client, message: Message):
    """Check if message has quote-like formatting"""
    if not message.entities:
        return False
    
    quote_entity_types = (
        MessageEntityType.BOLD,
        MessageEntityType.ITALIC,
        MessageEntityType.BLOCKQUOTE,
        MessageEntityType.PRE,
        MessageEntityType.CODE,
        MessageEntityType.STRIKETHROUGH,
        MessageEntityType.UNDERLINE,
        MessageEntityType.SPOILER
    )
    
    if message.text and message.text.startswith('>'):
        return True
    
    return any(entity.type in quote_entity_types for entity in message.entities)

@bot.on_message(
    (filters.text | filters.photo | filters.document |
     filters.video | filters.audio | filters.voice |
     filters.reply | filters.create(has_quote_entities)) &
    bot_chat_filter
)
async def handle_messages(client: Client, message: Message):
    if combined.state.get('active'):
        if not combined.state.get('destination_chat'):
            await combined.handle_destination_input(message)
        else:
            await combined.handle_link_collection(message)
    elif forwarder.state.get('active'):
        await forwarder.handle_setup_message(message)

# Strictly ignore all other messages
@bot.on_message(~bot_chat_filter)
async def ignore_all_other_messages(client: Client, message: Message):
    print(f"Ignored message from {message.chat.id} (not bot chat)")

def create_temp_dirs():
    """Create required temp directories"""
    dir_names = [
        "temp_cl_data",
        "forward_temp"
    ]
    for dir_name in dir_names:
        try:
            tempfile.mkdtemp(prefix=f"{dir_name}_")
        except Exception as e:
            print(f"Error creating temp dir {dir_name}: {e}")

# Keep-alive server for Heroku
from flask import Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running"

async def run_bot():
    await get_bot_username()
    create_temp_dirs()
    print("🚀 Starting bot...")
    await bot.start()
    print("🤖 Bot is now running")
    await asyncio.Event().wait()  # Run forever

if __name__ == "__main__":
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_bot())
    except KeyboardInterrupt:
        print("\n🛑 Received shutdown signal")
    except Exception as e:
        print(f"💥 Bot crashed: {e}")
    finally:
        loop.run_until_complete(bot.stop())
        loop.close()
        print("✅ Bot stopped cleanly")
