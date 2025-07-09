import os
import tempfile
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import MessageEntityType

# Check if required modules exist
try:
    import c_l
    import forward
    print("✅ c_l and forward modules imported successfully")
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
    forward_bot = forward.ForwardBot(bot)
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
        "/forward - Start message forwarding setup\n"
        "/cancel - Cancel current operation\n"
        "/help - Show help"
    )

@bot.on_message(filters.command("cl"))
async def combined_cmd(client: Client, message: Message):
    await combined.start_combined_process(message)

@bot.on_message(filters.command("forward"))
async def forward_cmd(client: Client, message: Message):
    await forward_bot.start_forward_setup(message)

@bot.on_message(filters.command("cancel"))
async def cancel_cmd(client: Client, message: Message):
    combined.reset_state()
    forward_bot.reset_state()
    await message.reply_text("⏹ Operation cancelled and state reset")

@bot.on_message(filters.command("help"))
async def help_cmd(client: Client, message: Message):
    await message.reply_text(
        "🆘 Help Information\n\n"
        "/cl - Combined link clicker and forwarder:\n"
        "1. First provide destination chat\n"
        "2. Then provide links to process\n"
        "3. Bot will click links and forward responses\n\n"
        "/forward - Message forwarding tool:\n"
        "1. First provide target chat\n"
        "2. Then provide destination chat\n"
        "3. Select messages to forward\n"
        "4. Choose to delete after forwarding\n\n"
        "/cancel - Cancel current operation\n"
    )

@bot.on_message(
    filters.text & filters.private |
    filters.create(lambda _, __, m: (
        m.text and m.text.startswith('/') or
        (forward_bot.state.get('active') or combined.state.get('active'))
    ))
)
async def handle_messages(client: Client, message: Message):
    if forward_bot.state.get('active'):
        await forward_bot.handle_setup_message(message)
    elif combined.state.get('active'):
        if not combined.state.get('destination_chat'):
            await combined.handle_destination_input(message)
        else:
            await combined.handle_link_collection(message)

def create_temp_dirs():
    """Create required temp directories"""
    dir_names = [
        "temp_cl_data",
        "forward_temp/media_temp",
        "forward_temp/message_temp"
    ]
    for dir_name in dir_names:
        try:
            os.makedirs(dir_name, exist_ok=True)
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
