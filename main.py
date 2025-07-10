import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatType

async def run_bot():
    bot = Client(
        "main_bot",
        api_id=int(os.environ.get("API_ID", 0)),
        api_hash=os.environ.get("API_HASH", ""),
        bot_token=os.environ.get("BOT_TOKEN", ""),
        session_string=os.environ.get("SESSION_STRING", "")
    )

    try:
        await bot.start()
        me = await bot.get_me()
        bot_username = me.username
        bot_id = me.id
        print(f"✅ Logged in as @{bot_username} (ID: {bot_id})")

        # Initialize modules
        import c_l
        from forward import ForwardBot
        combined = c_l.CombinedLinkForwarder(bot)
        forward_bot = ForwardBot(bot)

        def is_bot_private_chat(_, __, message: Message):
            """Strict filter for bot's own private chat"""
            is_private = message.chat.type == ChatType.PRIVATE
            is_bot_chat = message.chat.id == bot_id
            return is_private and is_bot_chat

        @bot.on_message(filters.command("start") & filters.create(is_bot_private_chat))
        async def start(client: Client, message: Message):
            print(f"📩 Received /start in bot's chat (ID: {message.chat.id})")
            await message.reply_text(
                "🤖 Bot Menu\n\n"
                "/forward - Forward messages\n"
                "/cl - Combined operations\n"
                "/cancel - Cancel operation"
            )

        @bot.on_message(filters.command("forward") & filters.create(is_bot_private_chat))
        async def forward_cmd(client: Client, message: Message):
            print(f"📩 Received /forward in bot's chat (ID: {message.chat.id})")
            await forward_bot.start_forward_setup(message)

        @bot.on_message(filters.command("cl") & filters.create(is_bot_private_chat))
        async def combined_cmd(client: Client, message: Message):
            print(f"📩 Received /cl in bot's chat (ID: {message.chat.id})")
            await combined.start_combined_process(message)

        @bot.on_message(filters.command("cancel") & filters.create(is_bot_private_chat))
        async def cancel_cmd(client: Client, message: Message):
            print(f"📩 Received /cancel in bot's chat (ID: {message.chat.id})")
            forward_bot.reset_state()
            combined.reset_state()
            await message.reply_text("⏹ Operations cancelled")

        @bot.on_message(
            (filters.text | filters.photo | filters.document |
             filters.video | filters.audio | filters.voice |
             filters.reply) & filters.create(is_bot_private_chat)
        )
        async def handle_messages(client: Client, message: Message):
            print(f"📩 Processing message in bot's chat (ID: {message.id})")
            if forward_bot.state.get('active'):
                await forward_bot.handle_setup_message(message)
            elif combined.state.get('active'):
                if not combined.state.get('destination_chat'):
                    await combined.handle_destination_input(message)
                else:
                    await combined.handle_link_collection(message)

        @bot.on_message(~filters.create(is_bot_private_chat))
        async def ignore_other_chats(client: Client, message: Message):
            if message.chat.type == ChatType.PRIVATE:
                print(f"🚫 Ignored message from other private chat (ID: {message.chat.id})")
            else:
                print(f"🚫 Ignored message from group/channel (ID: {message.chat.id})")

        print(f"🚀 Bot @{bot_username} is now running (only responds to its own private chat)")
        await asyncio.Event().wait()

    except Exception as e:
        print(f"💥 Error: {e}")
    finally:
        if 'bot' in locals() and await bot.is_initialized:
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
