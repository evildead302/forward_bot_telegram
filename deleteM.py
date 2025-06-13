import os
import asyncio
import tempfile
import json
from typing import List
from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait, RPCError

class DeleteBot:
    def __init__(self, bot: Client):
        self.bot = bot
        self.temp_dir = tempfile.mkdtemp(prefix="temp_delete_data_")
        os.makedirs(self.temp_dir, exist_ok=True)
        self.reset_state()

    def reset_state(self):
        """Reset all state variables and clean temp files"""
        self._clean_temp_files()
        self.state = {
            'active': False,
            'target_chat': None,
            'message_ids': [],
            'all_message_ids': [],
            'deleted_ids': [],
            'failed_ids': [],
            'progress_msg': None,
            'status_chat_id': None,
            'step': 0,
            'cancelled': False,
            'min_id': None,
            'max_id': None
        }

    def _clean_temp_files(self):
        """Clean up all temporary files including cache"""
        try:
            for filename in os.listdir(self.temp_dir):
                file_path = os.path.join(self.temp_dir, filename)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"Error deleting {file_path}: {e}")
        except Exception as e:
            print(f"Error cleaning temp dir: {e}")

    async def _send_status(self, text: str):
        """Send status updates to original chat"""
        if self.state['status_chat_id']:
            try:
                if self.state['progress_msg']:
                    await self.state['progress_msg'].edit_text(text)
                else:
                    self.state['progress_msg'] = await self.bot.send_message(
                        self.state['status_chat_id'],
                        text
                    )
            except Exception:
                pass

    async def _scan_and_cache_messages(self, chat_id: int):
        """Scan chat and cache message IDs with min/max tracking"""
        cache_file = os.path.join(self.temp_dir, f"{chat_id}_messages.json")
        
        # Clean existing cache file if present
        if os.path.exists(cache_file):
            try:
                os.unlink(cache_file)
            except Exception as e:
                print(f"Error cleaning cache: {e}")

        message_ids = []
        min_id = None
        max_id = None
        
        async for message in self.bot.get_chat_history(chat_id):
            if message and not message.empty:
                message_ids.append(message.id)
                if min_id is None or message.id < min_id:
                    min_id = message.id
                if max_id is None or message.id > max_id:
                    max_id = message.id

        if message_ids:
            self.state['min_id'] = min_id
            self.state['max_id'] = max_id
            cache_data = {
                'message_ids': message_ids,
                'min_id': min_id,
                'max_id': max_id
            }
            try:
                with open(cache_file, 'w') as f:
                    json.dump(cache_data, f)
            except Exception as e:
                print(f"Cache save error: {e}")

        return message_ids

    async def start_delete_setup(self, message: Message):
        """Initialize delete process with cleanup"""
        self.reset_state()
        self.state['active'] = True
        self.state['status_chat_id'] = message.chat.id
        self.state['step'] = 1
        await message.reply_text(
            "🗑️ <b>Message Deleter</b>\n\n"
            "1. Send <b>TARGET</b> chat (username/ID/URL):\n\n"
            "Type /cancel to stop"
        )

    async def handle_setup_message(self, message: Message):
        """Handle all setup steps with proper cleanup"""
        if not self.state['active'] or self.state['cancelled']:
            return

        try:
            text = message.text.strip()
            if text.lower() == '/cancel':
                self.state['cancelled'] = True
                await message.reply_text("❌ Process cancelled")
                self.reset_state()
                return

            if self.state['step'] == 1:  # Target chat
                target = await self.bot.get_chat(text)
                self.state['target_chat'] = target
                
                # Scan messages and cache them
                await self._send_status("🔍 Scanning messages...")
                self.state['all_message_ids'] = await self._scan_and_cache_messages(target.id)
                
                if not self.state['all_message_ids']:
                    raise ValueError("❌ No messages found in target chat")
                
                self.state['step'] = 2
                await message.reply_text(
                    f"✅ <b>Target set:</b> {target.title if hasattr(target, 'title') else 'Private Chat'}\n\n"
                    f"📊 Available message IDs: {self.state['min_id']} to {self.state['max_id']}\n\n"
                    "2. Select messages to delete:\n"
                    "• <code>all</code> - All messages\n"
                    "• <code>100-200</code> - Range\n"
                    "• <code>1,2,3,5-10</code> - Specific IDs\n\n"
                    "Type /cancel to stop"
                )

            elif self.state['step'] == 2:  # Message selection
                if text.lower() == 'all':
                    selected_ids = self.state['all_message_ids']
                else:
                    selected_ids = []
                    parts = text.split(',')
                    for part in parts:
                        part = part.strip()
                        if '-' in part:
                            try:
                                start, end = map(int, part.split('-'))
                                selected_ids.extend(
                                    mid for mid in self.state['all_message_ids'] 
                                    if start <= mid <= end
                                )
                            except ValueError:
                                raise ValueError("❌ Invalid range format. Use 'start-end'")
                        else:
                            try:
                                msg_id = int(part)
                                if msg_id in self.state['all_message_ids']:
                                    selected_ids.append(msg_id)
                            except ValueError:
                                raise ValueError("❌ Invalid ID format. Use numbers or ranges")
                
                if not selected_ids:
                    raise ValueError("❌ No matching messages found")
                
                self.state['message_ids'] = sorted(list(set(selected_ids)))
                await self._delete_messages(message)

        except Exception as e:
            await message.reply_text(f"❌ Error: {str(e)}")
            self.reset_state()

    async def _delete_messages(self, message: Message):
        """Delete selected messages in batches with guaranteed cleanup"""
        try:
            target = self.state['target_chat']
            total = len(self.state['message_ids'])
            
            await self._send_status(
                f"🗑️ Deleting {total} messages from {target.title if hasattr(target, 'title') else 'chat'}...\n"
                f"⏳ Please wait..."
            )

            # Delete in batches of 100 (Telegram limit)
            batch_size = 100
            for i in range(0, total, batch_size):
                if self.state['cancelled']:
                    await self._send_status("❌ Deletion cancelled")
                    break

                batch = self.state['message_ids'][i:i + batch_size]
                try:
                    await self.bot.delete_messages(target.id, batch)
                    self.state['deleted_ids'].extend(batch)
                    
                    # Update progress
                    progress = min(i + batch_size, total)
                    await self._send_status(
                        f"🗑️ Deletion progress: {progress}/{total}\n"
                        f"✅ Deleted: {len(self.state['deleted_ids'])}\n"
                        f"❌ Failed: {len(self.state['failed_ids'])}"
                    )
                except Exception as e:
                    self.state['failed_ids'].extend(batch)
                    await self._send_status(f"⚠️ Failed to delete batch: {str(e)}")

            await self._send_completion_report(message)
        finally:
            self._clean_temp_files()
            self.reset_state()

    async def _send_completion_report(self, message: Message):
        """Send final deletion report with cleanup"""
        try:
            total = len(self.state['message_ids'])
            deleted = len(self.state['deleted_ids'])
            failed = len(self.state['failed_ids'])
            
            report = (
                f"🎉 <b>Deletion Complete</b>\n\n"
                f"• Total selected: {total}\n"
                f"• Successfully deleted: {deleted}\n"
                f"• Failed to delete: {failed}"
            )
            
            if failed > 0:
                failed_ids = ', '.join(map(str, self.state['failed_ids'][:50]))
                if failed > 50:
                    failed_ids += f" (and {failed-50} more)"
                report += f"\n\n❌ Failed IDs:\n{failed_ids}"
            
            await message.reply_text(report)
        finally:
            self._clean_temp_files()

    def __del__(self):
        """Destructor to ensure cleanup"""
        self._clean_temp_files()