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

@bot.on_message(filters.command("start"))
async def start(client: Client, message: Message):
    await message.reply_text(
        "🤖 Combined Link Forwarder Bot\n\n"
        "Available commands:\n"
        "/cl - Combined link clicker and forwarder\n"
        "/forward - Message forwarding\n"
        "/cancel - Cancel current operation\n"
        "/help - Show help"
    )

@bot.on_message(filters.command("forward"))
async def forward_cmd(client: Client, message: Message):
    await forwarder.start_forward_setup(message)

@bot.on_message(filters.command("cl"))
async def combined_cmd(client: Client, message: Message):
    await combined.start_combined_process(message)

@bot.on_message(filters.command("cancel"))
async def cancel_cmd(client: Client, message: Message):
    combined.reset_state()
    forwarder.reset_state()
    await message.reply_text("⏹ Operation cancelled and state reset")

@bot.on_message(filters.command("help"))
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
    filters.text | filters.photo | filters.document |
    filters.video | filters.audio | filters.voice |
    filters.reply | filters.create(has_quote_entities)
)
async def handle_messages(client: Client, message: Message):
    if combined.state.get('active'):
        if not combined.state.get('destination_chat'):
            await combined.handle_destination_input(message)
        else:
            await combined.handle_link_collection(message)
    elif forwarder.state.get('active'):
        await forwarder.handle_setup_message(message)

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

import threading
threading.Thread(target=lambda: app.run(port=int(os.environ.get('PORT', 5000)))).start()

if __name__ == "__main__":
    print("🚀 Starting bot...")
    create_temp_dirs()
    
    try:
        print("🔌 Connecting to Telegram...")
        bot.run()
        print("🤖 Bot stopped gracefully")
    except Exception as e:
        print(f"💥 Bot crashed: {e}")
