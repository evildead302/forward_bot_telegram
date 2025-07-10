import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

# Initialize with your exact working configuration
bot = Client(
    "my_bot",
    api_id=int(os.environ["API_ID"]),
    api_hash=os.environ["API_HASH"],
    bot_token=os.environ["BOT_TOKEN"],
    in_memory=True
)

# Initialize your modules exactly as in your working version
try:
    import c_l
    combined = c_l.CombinedLinkForwarder(bot)
    print("✅ c_l module loaded successfully")
except Exception as e:
    print(f"❌ Failed to load c_l module: {e}")
    raise

@bot.on_message(filters.command("start"))
async def start(client, message):
    """This will definitely respond in bot chat"""
    print(f"Received start command from {message.from_user.id}")
    await message.reply_text(
        "🤖 Bot is ONLINE\n\n"
        "Commands:\n"
        "/cl - Process links\n"
        "/cancel - Reset operation"
    )

@bot.on_message(filters.command("cl"))
async def cl_command(client, message):
    print(f"CL command received from {message.chat.id}")
    await combined.start_combined_process(message)

@bot.on_message(filters.command("cancel"))
async def cancel(client, message):
    combined.reset_state()
    await message.reply("Operation cancelled")

# CRITICAL: Add this debug handler
@bot.on_message()
async def message_logger(client, message):
    print(f"\nDEBUG MESSAGE LOG:")
    print(f"Chat ID: {message.chat.id}")
    print(f"From: {message.from_user.id if message.from_user else 'None'}")
    print(f"Text: {message.text or 'No text'}")
    print(f"Chat Type: {message.chat.type}\n")

async def run_bot():
    await bot.start()
    me = await bot.get_me()
    print(f"\n🔊 BOT ACTIVE: @{me.username}")
    print("📡 Waiting for messages...\n")
    
    # Keep running
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(run_bot())
    except KeyboardInterrupt:
        print("\n🛑 Stopping bot...")
    finally:
        loop.run_until_complete(bot.stop())
        loop.close()
        print("✅ Bot stopped cleanly")
