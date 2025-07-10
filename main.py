import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import MessageEntityType

# Initialize bot with error handling
bot = Client(
    "main_bot",
    api_id=int(os.environ.get("API_ID", 0)),
    api_hash=os.environ.get("API_HASH", ""),
    bot_token=os.environ.get("BOT_TOKEN", ""),
    session_string=os.environ.get("SESSION_STRING", "")
)

# Initialize module
try:
    import c_l
    combined = c_l.CombinedLinkForwarder(bot)
    print("✅ Module initialized")
except Exception as e:
    print(f"❌ Module initialization failed: {e}")
    raise

@bot.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "🤖 Combined Link Forwarder Bot\n\n"
        "Available commands:\n"
        "/cl - Combined link clicker and forwarder\n"
        "/cancel - Cancel current operation\n"
        "/help - Show help"
    )

@bot.on_message(filters.command("cl"))
async def combined_cmd(client, message):
    await combined.start_combined_process(message)

@bot.on_message(filters.command("cancel"))
async def cancel_cmd(client, message):
    combined.reset_state()
    await message.reply_text("⏹ Operation cancelled and state reset")

@bot.on_message(filters.command("help"))
async def help_cmd(client, message):
    await message.reply_text(
        "🆘 Help Information\n\n"
        "/cl - Combined link clicker and forwarder:\n"
        "1. First provide destination chat\n"
        "2. Then provide links to process\n"
        "3. Bot will click links and forward responses\n"
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
async def handle_messages(client, message):
    if combined.state.get('active'):
        if not combined.state.get('destination_chat'):
            await combined.handle_destination_input(message)
        else:
            await combined.handle_link_collection(message)

async def main():
    print("🚀 Starting bot...")
    try:
        print("🔌 Connecting to Telegram...")
        await bot.start()
        print("🤖 Bot is now running")
        await asyncio.Event().wait()  # Run forever
    except Exception as e:
        print(f"💥 Bot crashed: {e}")
    finally:
        await bot.stop()
        print("🛑 Bot stopped")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n🛑 Received shutdown signal")
    finally:
        loop.close()
