import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

async def run_bot():
    # Initialize bot with session string support
    bot = Client(
        "main_bot",
        api_id=int(os.environ.get("API_ID", 0)),
        api_hash=os.environ.get("API_HASH", ""),
        bot_token=os.environ.get("BOT_TOKEN", ""),
        session_string=os.environ.get("SESSION_STRING", "")
    )

    try:
        # Start the bot with login verification
        await bot.start()
        me = await bot.get_me()
        print(f"✅ Logged in as @{me.username} (ID: {me.id})")
        print(f"🔑 Using {'session string' if os.environ.get('SESSION_STRING') else 'bot token'}")

        # Initialize ONLY the required modules
        import c_l
        from forward import ForwardBot
        combined = c_l.CombinedLinkForwarder(bot)
        forward_bot = ForwardBot(bot)
        print("✅ Modules loaded: c_l, forward")

        @bot.on_message(filters.command("start"))
        async def start(client: Client, message: Message):
            await message.reply_text(
                "🤖 Bot Menu\n\n"
                "/forward - Forward messages\n"
                "/cl - Combined operations\n"
                "/cancel - Cancel operation"
            )

        @bot.on_message(filters.command("forward"))
        async def forward_cmd(client: Client, message: Message):
            await forward_bot.start_forward_setup(message)

        @bot.on_message(filters.command("cl"))
        async def combined_cmd(client: Client, message: Message):
            await combined.start_combined_process(message)

        @bot.on_message(filters.command("cancel"))
        async def cancel_cmd(client: Client, message: Message):
            forward_bot.reset_state()
            combined.reset_state()
            await message.reply_text("⏹ Operations cancelled")

        @bot.on_message(
            filters.text | filters.photo | filters.document |
            filters.video | filters.audio | filters.voice |
            filters.reply
        )
        async def handle_messages(client: Client, message: Message):
            if forward_bot.state.get('active'):
                await forward_bot.handle_setup_message(message)
            elif combined.state.get('active'):
                if not combined.state.get('destination_chat'):
                    await combined.handle_destination_input(message)
                else:
                    await combined.handle_link_collection(message)

        print("🚀 Bot is now running")
        await asyncio.Event().wait()  # Run forever

    except Exception as e:
        print(f"💥 Error: {e}")
    finally:
        if await bot.is_initialized:
            await bot.stop()
            print("✅ Bot stopped")

if __name__ == "__main__":
    # Create required directories
    os.makedirs("temp_cl_data", exist_ok=True)
    os.makedirs("forward_temp", exist_ok=True)
    
    # Run the bot
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(run_bot())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    finally:
        loop.close()
