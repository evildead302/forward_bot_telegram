import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import MessageEntityType

# Initialize bot with your exact configuration
bot = Client(
    "main_bot",
    api_id=int(os.environ.get("API_ID", 0)),
    api_hash=os.environ.get("API_HASH", ""),
    bot_token=os.environ.get("BOT_TOKEN", ""),
    session_string=os.environ.get("SESSION_STRING", "")
)

# Initialize modules exactly as in your original code
try:
    import c_l
    combined = c_l.CombinedLinkForwarder(bot)
    print("✅ c_l module loaded successfully")
    
    # Add forwarder module
    from forward import ForwardBot
    forwarder = ForwardBot(bot)
    print("✅ forward module loaded successfully")
except Exception as e:
    print(f"❌ Module initialization failed: {e}")
    raise

@bot.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "🤖 Combined Link Forwarder Bot\n\n"
        "Available commands:\n"
        "/forward - Message forwarding\n"
        "/cl - Combined link processor\n"
        "/cancel - Cancel current operation\n"
        "/help - Show help"
    )

@bot.on_message(filters.command("forward"))
async def forward_cmd(client, message):
    await forwarder.start_forward_setup(message)

@bot.on_message(filters.command("cl"))
async def combined_cmd(client, message):
    await combined.start_combined_process(message)

@bot.on_message(filters.command("cancel"))
async def cancel_cmd(client, message):
    combined.reset_state()
    forwarder.reset_state()
    await message.reply_text("⏹ All operations cancelled")

@bot.on_message(filters.command("help"))
async def help_cmd(client, message):
    await message.reply_text(
        "🆘 Help Information\n\n"
        "/forward - Forward messages between chats\n"
        "/cl - Combined link processor\n"
        "1. First provide destination chat\n"
        "2. Then provide links to process\n"
        "3. Bot will click links and forward responses\n"
        "/cancel - Cancel current operation"
    )

def has_quote_entities(filter, client, message: Message):
    """Your original quote detection function"""
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
async def handle_messages(client, message):
    if forwarder.state.get('active'):
        await forwarder.handle_setup_message(message)
    elif combined.state.get('active'):
        if not combined.state.get('destination_chat'):
            await combined.handle_destination_input(message)
        else:
            await combined.handle_link_collection(message)

# Add debug message logger
@bot.on_message()
async def debug_logger(client, message):
    print(f"\n📩 Received message:")
    print(f"Chat ID: {message.chat.id}")
    print(f"From: {message.from_user.id if message.from_user else 'None'}")
    print(f"Text: {message.text or 'No text'}\n")

async def run():
    print("🚀 Starting bot with your original configuration...")
    await bot.start()
    print("🤖 Bot is now running")
    await asyncio.Event().wait()  # Run forever

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run())
    except KeyboardInterrupt:
        print("\n🛑 Received shutdown signal")
    finally:
        loop.run_until_complete(bot.stop())
        loop.close()
