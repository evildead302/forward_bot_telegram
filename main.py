import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import MessageEntityType

# Check if required modules exist
try:
    import forward
    import duplicate_checker 
    import link_clicker
    import c_l
    import deleteM
    import schedule_bot
    import f_c
    print("✅ All modules imported successfully")
except ImportError as e:
    print(f"❌ Missing module: {e}")
    raise

async def run_bot():
    # Initialize bot with error handling
    try:
        bot = Client(
            "main_bot",
            api_id=int(os.environ.get("API_ID", 0)),
            api_hash=os.environ.get("API_HASH", ""),
            bot_token=os.environ.get("BOT_TOKEN", ""),
            session_string=os.environ.get("SESSION_STRING", "")
        )
        
        # Explicit login with verification
        await bot.start()
        me = await bot.get_me()
        print(f"✅ Bot @{me.username} logged in successfully (ID: {me.id})")
        print(f"🔑 Using {'session string' if os.environ.get('SESSION_STRING') else 'bot token'}")

        # Initialize modules with verification
        try:
            forward_bot = forward.ForwardBot(bot)
            dup_checker = duplicate_checker.DuplicateChecker(bot) 
            clicker = link_clicker.LinkClicker(bot)
            combined = c_l.CombinedLinkForwarder(bot)
            delete_bot = deleteM.DeleteBot(bot)
            scheduler = schedule_bot.ScheduleBot(bot)
            fc_bot = f_c.ForwardCheckBot(bot)
            print("✅ All modules initialized")
        except Exception as e:
            print(f"❌ Module initialization failed: {e}")
            raise

        @bot.on_message(filters.command("start"))
        async def start(client: Client, message: Message):
            await message.reply_text(
                "🤖 Main Bot Menu\n\n"
                "Available commands:\n"
                "/forward - Message forwarding\n" 
                "/duplicate - Find duplicates\n"
                "/clicker - Bot link clicking\n"
                "/cl - Combined clicker+forwarder\n"
                "/delete - Delete messages\n"
                "/schedule - Advanced scheduling\n"
                "/fc - Forward check (auto-forward new messages)\n"
                "/help - Show help"
            )

        @bot.on_message(filters.command("forward"))
        async def forward_cmd(client: Client, message: Message):
            await forward_bot.start_forward_setup(message)

        @bot.on_message(filters.command("duplicate")) 
        async def duplicate_cmd(client: Client, message: Message):
            await dup_checker.start_duplicate_check(message)

        @bot.on_message(filters.command("clicker"))
        async def clicker_cmd(client: Client, message: Message):
            await clicker.start_clicker_setup(message)

        @bot.on_message(filters.command("cl"))
        async def combined_cmd(client: Client, message: Message):
            await combined.start_combined_process(message)

        @bot.on_message(filters.command("delete"))
        async def delete_cmd(client: Client, message: Message):
            await delete_bot.start_delete_setup(message)

        @bot.on_message(filters.command("schedule"))
        async def schedule_cmd(client: Client, message: Message):
            await scheduler.start_setup(message)

        @bot.on_message(filters.command("fc"))
        async def fc_cmd(client: Client, message: Message):
            await fc_bot.start_fc_setup(message)

        @bot.on_message(filters.command("cancel"))
        async def cancel_cmd(client: Client, message: Message):
            forward_bot.reset_state()
            dup_checker.reset_state()
            clicker.reset_state()
            combined.reset_state()
            delete_bot.reset_state()
            scheduler.reset_state()
            fc_bot.reset_state()
            await message.reply_text("⏹ All operations cancelled and states reset")

        @bot.on_message(filters.command("help"))
        async def help_cmd(client: Client, message: Message):
            await message.reply_text(
                "🆘 Help Information\n\n"
                "1. /forward - Forward messages between chats\n"
                "2. /duplicate - Find and forward duplicate messages\n" 
                "3. /clicker - Click bot links and track responses\n"
                "4. /cl - Combined link clicker and forwarder\n"
                "5. /delete - Delete messages in a chat\n"
                "6. /schedule - Advanced message scheduler\n"
                "7. /fc - Forward check (auto-forward new messages)\n"
                "8. /cancel - Cancel current operation\n"
                "\nAll commands maintain their own state independently"
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
            if forward_bot.state.get('active'):
                await forward_bot.handle_setup_message(message)
            elif scheduler.state.get('setup_step', 0) > 0:
                await scheduler.handle_setup_message(message)
            elif delete_bot.state.get('active'):
                await delete_bot.handle_setup_message(message)
            elif dup_checker.state.get('active'):
                await dup_checker.handle_setup_message(message)
            elif clicker.state.get('active'):
                await clicker.handle_clicker_message(message)
            elif combined.state.get('active'):
                if not combined.state.get('destination_chat'):
                    await combined.handle_destination_input(message)
                else:
                    await combined.handle_link_collection(message)
            elif fc_bot.state.get('active'):
                await fc_bot.handle_fc_message(message)

        # Keep the bot running
        print("🚀 Bot is now running")
        await asyncio.Event().wait()

    except Exception as e:
        print(f"💥 Error: {e}")
    finally:
        if 'bot' in locals() and await bot.is_initialized:
            await bot.stop()
            print("✅ Bot stopped gracefully")

def create_temp_dirs():
    """Create all required temp directories"""
    dirs = [
        "temp_media",
        "temp_duplicate_data",
        "temp_link_clicker",
        "temp_cl_data",
        "temp_delete_data",
        "temp_schedule_data",
        "temp_fc_data"
    ]
    for dir in dirs:
        try:
            os.makedirs(dir, exist_ok=True)
            print(f"✅ Created directory: {dir}")
        except Exception as e:
            print(f"❌ Failed to create {dir}: {e}")

if __name__ == "__main__":
    print("🚀 Starting bot...")
    create_temp_dirs()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(run_bot())
    except KeyboardInterrupt:
        print("\n🛑 Received shutdown signal")
    except Exception as e:
        print(f"💥 Bot crashed: {e}")
    finally:
        loop.close()
        print("🤖 Bot process ended")
