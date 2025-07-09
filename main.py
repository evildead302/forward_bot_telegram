import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, BotCommand
from pyrogram.enums import ParseMode, ChatType

# Initialize bot
bot = Client(
    "secure_forward_bot",
    api_id=int(os.environ.get("API_ID", 0)),
    api_hash=os.environ.get("API_HASH", ""),
    bot_token=os.environ.get("BOT_TOKEN", ""),
    session_string=os.environ.get("SESSION_STRING", "")
)

# Security configuration
class Security:
    def __init__(self):
        self.owner_id = None
        self.bot_id = None
    
    async def initialize(self):
        # Get bot account info
        self.bot_id = (await bot.get_me()).id
        print(f"🤖 Bot ID: {self.bot_id}")
        
        # Get owner account info from session
        if bot.session_string:
            user_client = Client("owner_account", session_string=bot.session_string)
            await user_client.start()
            self.owner_id = (await user_client.get_me()).id
            await user_client.stop()
            print(f"👑 Owner ID: {self.owner_id}")

security = Security()

# Initialize modules
async def initialize_modules():
    global combined, forwarder
    import c_l
    import forward
    combined = c_l.CombinedLinkForwarder(bot)
    forwarder = forward.ForwardBot(bot)

# Security filter
async def is_authorized(_, __, message: Message):
    # Ignore if no user
    if not message.from_user:
        return False
    
    # Allow only from owner or the bot itself
    if message.from_user.id not in [security.owner_id, security.bot_id]:
        return False
    
    # For non-private chats, verify bot is member
    if message.chat.type != ChatType.PRIVATE:
        try:
            member = await bot.get_chat_member(message.chat.id, "me")
            return member.status in ["member", "administrator", "creator"]
        except:
            return False
    return True

# Command: Start
@bot.on_message(filters.command("start") & filters.create(is_authorized))
async def start(client: Client, message: Message):
    await message.reply_text(
        "🤖 <b>Secure Forward Bot</b>\n\n"
        f"👑 Owner: <code>{security.owner_id}</code>\n"
        f"🤖 Bot ID: <code>{security.bot_id}</code>\n\n"
        "Commands:\n"
        "/cl - Combined link forwarder\n"
        "/forward - Message forwarding\n"
        "/cancel - Cancel operation",
        parse_mode=ParseMode.HTML
    )

# Command: Forward
@bot.on_message(filters.command("forward") & filters.private & filters.create(is_authorized))
async def forward_cmd(client: Client, message: Message):
    await forwarder.start_forward_setup(message)

# Command: CL
@bot.on_message(filters.command("cl") & filters.create(is_authorized))
async def combined_cmd(client: Client, message: Message):
    await combined.start_combined_process(message)

# Command: Cancel
@bot.on_message(filters.command("cancel") & filters.create(is_authorized))
async def cancel_cmd(client: Client, message: Message):
    combined.reset_state()
    forwarder.reset_state()
    await message.reply_text("🛑 All operations cancelled")

# Handle messages for active modules
@bot.on_message(filters.create(is_authorized))
async def handle_messages(client: Client, message: Message):
    if forwarder.state.get('active'):
        await forwarder.handle_setup_message(message)
    elif combined.state.get('active'):
        if not combined.state.get('destination_chat'):
            await combined.handle_destination_input(message)
        else:
            await combined.handle_link_collection(message)

# Ignore all unauthorized messages
@bot.on_message(~filters.create(is_authorized))
async def ignore_unauthorized(_, message: Message):
    return

# Register bot commands
async def set_commands():
    await bot.set_bot_commands([
        BotCommand("start", "Show bot info"),
        BotCommand("cl", "Link forwarder"),
        BotCommand("forward", "Message forwarder"),
        BotCommand("cancel", "Cancel operations")
    ])

# Main function
async def main():
    await security.initialize()
    await initialize_modules()
    await set_commands()
    
    print(f"🚀 Bot @{(await bot.get_me()).username} is running")
    await asyncio.Event().wait()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Bot stopped by user")
    except Exception as e:
        print(f"💥 Bot crashed: {str(e)}")
