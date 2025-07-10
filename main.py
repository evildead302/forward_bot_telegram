import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, BotCommand

# Initialize bot with minimal configuration
bot = Client(
    "simple_bot",
    api_id=int(os.environ["API_ID"]),
    api_hash=os.environ["API_HASH"],
    bot_token=os.environ["BOT_TOKEN"],
    in_memory=True
)

@bot.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply("🚀 Bot is working!")

@bot.on_message(filters.command("cl"))
async def cl_command(client, message: Message):
    await message.reply("🔗 CL command received")

@bot.on_message(filters.command("forward"))
async def forward_command(client, message: Message):
    await message.reply("📤 Forward command received")

@bot.on_message(filters.command("cancel"))
async def cancel_command(client, message: Message):
    await message.reply("🛑 Operation cancelled")

@bot.on_message()
async def echo(client, message: Message):
    print(f"Received message: {message.text}")
    # await message.reply(f"You said: {message.text}")

async def main():
    await bot.start()
    
    # Set bot commands
    await bot.set_bot_commands([
        BotCommand("start", "Start the bot"),
        BotCommand("cl", "Combined links"),
        BotCommand("forward", "Forward messages"),
        BotCommand("cancel", "Cancel operation")
    ])
    
    me = await bot.get_me()
    print(f"🤖 Bot @{me.username} is now running")
    await asyncio.Event().wait()  # Run forever

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped")
    finally:
        loop.run_until_complete(bot.stop())
        loop.close()
