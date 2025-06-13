import os
import asyncio
import tempfile
import json
from typing import List, Dict
from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait, RPCError

class ForwardBot:
    def __init__(self, bot: Client):
        self.bot = bot
        self.temp_dir = tempfile.mkdtemp(prefix="temp_forward_data_")
        os.makedirs(self.temp_dir, exist_ok=True)
        self.reset_state()
        self.MAX_PARALLEL = 3
        self.progress_messages = {}

    def reset_state(self):
        """Reset all state variables and clear temp files"""
        self._clean_temp_files()
        self.state = {
            'active': False,
            'target_chat': None,
            'destination_chat': None,
            'message_ids': [],
            'failed_messages': [],
            'success_count': 0,
            'progress_msg': None,
            'step': 0,
            'cancelled': False,
            'min_id': None,
            'max_id': None,
            'all_message_ids': [],
            'delete_after_forward': False,
            'deleted_messages': [],
            'message_status': {},
            'current_batch': [],
            'processing_queue': asyncio.Queue(),
            'workers': [],
            'last_shown_messages': set()
        }

    def _clean_temp_files(self):
        """Clean up temporary files"""
        for filename in os.listdir(self.temp_dir):
            file_path = os.path.join(self.temp_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")

    async def _scan_and_cache_messages(self, chat_id: int):
        """Scan chat and cache message IDs with min/max tracking"""
        cache_file = os.path.join(self.temp_dir, f"{chat_id}_messages.json")
        message_ids = []

        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    cached_data = json.load(f)
                if isinstance(cached_data, dict):
                    self.state['min_id'] = cached_data.get('min_id')
                    self.state['max_id'] = cached_data.get('max_id')
                    return cached_data.get('message_ids', [])
            except Exception as e:
                print(f"Cache load error: {e}")

        min_id = None
        max_id = None
        message_ids = []

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

    async def _generate_thumbnail(self, video_path: str) -> str:
        """Generate thumbnail from video using ffmpeg if not available"""
        thumbnail_path = os.path.splitext(video_path)[0] + "_thumb.jpg"
        try:
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y",
                "-i", video_path,
                "-ss", "00:00:01.000",
                "-vframes", "1",
                thumbnail_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0 and os.path.exists(thumbnail_path):
                return thumbnail_path
        except Exception as e:
            print(f"Error generating thumbnail: {e}")
        return None

    async def _forward_media(self, message: Message, dest_chat) -> bool:
        """Enhanced media forwarding with proper temp file handling"""
        temp_path = None
        thumb_path = None
        
        try:
            # Try direct copy first
            try:
                await message.copy(dest_chat.id)
                return True
            except FloodWait as e:
                await asyncio.sleep(e.value)
                return await self._forward_media(message, dest_chat)
            except Exception:
                pass  # Fall through to download method

            # Download and resend if needed
            file_ext = ".mp4" if message.video else ".jpg" if message.photo else ""
            temp_path = os.path.join(self.temp_dir, f"media_{message.id}{file_ext}")
            temp_path = await self.bot.download_media(message, file_name=temp_path)
            
            if not temp_path or not os.path.exists(temp_path):
                return False

            send_args = {
                'caption': message.caption,
                'caption_entities': message.caption_entities,
                'reply_to_message_id': message.reply_to_message_id if message.reply_to_message_id else None
            }

            if message.video:
                video_args = {
                    'duration': message.video.duration,
                    'width': message.video.width,
                    'height': message.video.height,
                    'supports_streaming': True,
                    **send_args
                }
                
                if message.video.thumbs and message.video.thumbs[0].file_id:
                    try:
                        thumb_path = await self.bot.download_media(message.video.thumbs[0].file_id)
                    except Exception:
                        thumb_path = await self._generate_thumbnail(temp_path)
                
                if thumb_path:
                    video_args['thumb'] = thumb_path

                await self.bot.send_video(dest_chat.id, temp_path, **video_args)

            elif message.photo:
                await self.bot.send_photo(dest_chat.id, temp_path, **send_args)

            elif message.document:
                if message.document.thumbs:
                    try:
                        thumb_path = await self.bot.download_media(message.document.thumbs[0].file_id)
                        send_args['thumb'] = thumb_path
                    except Exception:
                        pass
                
                await self.bot.send_document(dest_chat.id, temp_path, **send_args)

            return True

        except FloodWait as e:
            await asyncio.sleep(e.value)
            return await self._forward_media(message, dest_chat)
        except Exception as e:
            print(f"Media forwarding failed: {e}")
            return False
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            if thumb_path and os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                except:
                    pass

    async def _forward_message(self, message: Message, dest_chat) -> bool:
        """Forward single message with rate limiting"""
        if self.state['cancelled']:
            return False

        try:
            # Update progress to 20%
            self.state['message_status'][message.id]['progress'] = 20
            await self._update_progress(None)
            
            if message.media:
                result = await self._forward_media(message, dest_chat)
            elif message.text:
                try:
                    await self.bot.send_message(
                        dest_chat.id,
                        message.text,
                        entities=message.entities,
                        reply_to_message_id=message.reply_to_message_id if message.reply_to_message_id else None
                    )
                    result = True
                except Exception:
                    result = False
            else:
                try:
                    await message.copy(dest_chat.id)
                    result = True
                except Exception:
                    result = False
            
            # Update progress in 20% increments
            if result:
                for progress in [40, 60, 80, 100]:
                    self.state['message_status'][message.id]['progress'] = progress
                    await self._update_progress(None)
                    await asyncio.sleep(0.1)
            return result
            
        except Exception as e:
            print(f"Error forwarding message: {e}")
            return False
        finally:
            await asyncio.sleep(0.5)

    async def _worker(self, dest_chat):
        """Worker that processes messages from the queue"""
        while True:
            try:
                msg_id, target_chat = await self.state['processing_queue'].get()
                
                if self.state['cancelled']:
                    self.state['processing_queue'].task_done()
                    break
                    
                self.state['message_status'][msg_id]['status'] = 'in_progress'
                await self._update_progress(None)
                
                try:
                    msg = await self.bot.get_messages(target_chat.id, msg_id)
                    if msg and not msg.empty:
                        success = await self._forward_message(msg, dest_chat)
                        if success:
                            self.state['message_status'][msg_id]['status'] = 'completed'
                            self.state['success_count'] += 1
                            
                            if self.state['delete_after_forward']:
                                try:
                                    await self.bot.delete_messages(target_chat.id, msg_id)
                                    self.state['deleted_messages'].append(msg_id)
                                except Exception:
                                    pass
                        else:
                            self.state['message_status'][msg_id]['status'] = 'failed'
                            self.state['failed_messages'].append(msg_id)
                    else:
                        self.state['message_status'][msg_id]['status'] = 'failed'
                        self.state['failed_messages'].append(msg_id)
                except Exception as e:
                    print(f"Error processing {msg_id}: {e}")
                    self.state['message_status'][msg_id]['status'] = 'failed'
                    self.state['failed_messages'].append(msg_id)
                
                await self._update_progress(None)
                self.state['processing_queue'].task_done()
                
            except Exception as e:
                print(f"Worker error: {e}")
                self.state['processing_queue'].task_done()

    async def _update_progress(self, message: Message):
        """Update progress with detailed percentage for each message"""
        target = self.state['target_chat']
        total = len(self.state['message_ids'])
        
        completed = sum(1 for status in self.state['message_status'].values() 
                      if status.get('status') == 'completed')
        in_progress = sum(1 for status in self.state['message_status'].values() 
                        if status.get('status') == 'in_progress')
        failed = sum(1 for status in self.state['message_status'].values() 
                  if status.get('status') == 'failed')

        progress_text = (
            f"📊 Progress for @{target.username if target.username else target.id}:\n"
            f"✅ {completed}/{total} completed\n"
            f"🔄 {in_progress} in progress\n"
            f"❌ {failed} failed\n\n"
        )

        # Show active messages (up to 10)
        active_messages = [
            (msg_id, status) 
            for msg_id, status in self.state['message_status'].items()
            if status.get('status') in ('pending', 'in_progress')
        ][:10]

        for msg_id, status in active_messages:
            progress = status.get('progress', 0)
            status_text = {
                'pending': f'pending ({progress}%)',
                'in_progress': f'forwarding ({progress}%)',
                'completed': 'completed (100%) ✅',
                'failed': 'failed ❌'
            }.get(status.get('status', 'pending'), f'pending ({progress}%)')
            
            progress_text += f"📦 {msg_id}: {status_text}\n"

        if len(active_messages) < len(self.state['message_ids']) - completed - failed:
            remaining = len(self.state['message_ids']) - completed - failed - len(active_messages)
            progress_text += f"\n...and {remaining} more messages waiting\n"

        if self.state['delete_after_forward']:
            deleted_count = len(self.state['deleted_messages'])
            progress_text += (
                f"\n🗑️ Deletion Status:\n"
                f"• Total to delete: {completed}\n"
                f"• Successfully deleted: {deleted_count}\n"
                f"• Failed to delete: {completed - deleted_count}"
            )

        if self.state['progress_msg']:
            try:
                await self.state['progress_msg'].edit_text(progress_text)
            except:
                if message:
                    self.state['progress_msg'] = await message.reply_text(progress_text)
        else:
            if message:
                self.state['progress_msg'] = await message.reply_text(progress_text)

    async def _start_forwarding(self, message: Message):
        """Execute the forwarding process with enhanced progress tracking"""
        target = self.state['target_chat']
        dest = self.state['destination_chat']
        total = len(self.state['message_ids'])
        
        self.state['message_status'] = {
            msg_id: {'status': 'pending', 'progress': 0} 
            for msg_id in self.state['message_ids']
        }
        
        # Create workers
        self.state['workers'] = [
            asyncio.create_task(self._worker(dest))
            for _ in range(self.MAX_PARALLEL)
        ]
        
        # Add messages to queue in order (oldest first)
        for msg_id in self.state['message_ids']:
            self.state['current_batch'].append(msg_id)
            await self.state['processing_queue'].put((msg_id, target))
        
        await self._update_progress(message)
        
        # Wait for all messages to be processed
        await self.state['processing_queue'].join()
        
        # Cancel workers
        for worker in self.state['workers']:
            worker.cancel()
        await asyncio.gather(*self.state['workers'], return_exceptions=True)
        
        await self._send_completion_report(message)
        self.reset_state()

    async def _send_completion_report(self, message: Message):
        """Send final report with all failed IDs"""
        total = len(self.state['message_ids'])
        success = self.state['success_count']
        failed = len(self.state['failed_messages'])
        
        report = (
            f"🎉 <b>Forwarding Complete</b>\n\n"
            f"• Total: {total}\n"
            f"• Success: {success}\n"
            f"• Failed: {failed}"
        )
        
        if failed > 0:
            failed_ids = ', '.join(map(str, self.state['failed_messages']))
            report += f"\n\n❌ Failed IDs:\n{failed_ids}"
        
        if self.state['delete_after_forward']:
            deleted = len(self.state['deleted_messages'])
            report += (
                f"\n\n🗑️ Deletion Results:\n"
                f"• Total to delete: {success}\n"
                f"• Successfully deleted: {deleted}\n"
                f"• Failed to delete: {success - deleted}"
            )
            
            if (success - deleted) > 0:
                failed_deletes = [
                    msg_id for msg_id, status in self.state['message_status'].items()
                    if status.get('status') == 'completed' and msg_id not in self.state['deleted_messages']
                ]
                report += f"\nFailed delete IDs:\n{', '.join(map(str, failed_deletes))}"
        
        await message.reply_text(report)

    async def start_forward_setup(self, message: Message):
        """Initialize forwarding process"""
        self.reset_state()
        self.state['active'] = True
        self.state['step'] = 1
        await message.reply_text(
            "📨 <b>Forward Setup</b>\n\n"
            "1. Send <b>TARGET</b> chat (username/ID/URL):\n\n"
            "Type /cancel to stop"
        )

    async def handle_setup_message(self, message: Message):
        """Handle all setup steps with delete option"""
        if not self.state['active'] or self.state['cancelled']:
            return

        try:
            text = message.text.strip()
            if text.lower() == '/cancel':
                self.state['cancelled'] = True
                await message.reply_text("❌ Process cancelled")
                return

            if self.state['step'] == 1:
                target = await self.bot.get_chat(text)
                self.state['target_chat'] = target
                
                await message.reply_text("🔍 Scanning messages...")
                self.state['all_message_ids'] = await self._scan_and_cache_messages(target.id)
                
                if not self.state['all_message_ids']:
                    raise ValueError("❌ No messages found in target chat")
                
                self.state['step'] = 2
                await message.reply_text(
                    f"✅ <b>Target set:</b> {target.title if hasattr(target, 'title') else 'Private Chat'}\n\n"
                    "2. Send <b>DESTINATION</b> chat:"
                )

            elif self.state['step'] == 2:
                dest = await self.bot.get_chat(text)
                self.state['destination_chat'] = dest
                
                me = await self.bot.get_me()
                member = await self.bot.get_chat_member(dest.id, me.id)
                if not member.privileges or not member.privileges.can_post_messages:
                    raise ValueError("❌ Bot needs 'Post Messages' permission")
                
                self.state['step'] = 3
                await message.reply_text(
                    f"✅ <b>Destination set:</b> {dest.title}\n\n"
                    f"📊 Available message IDs: {self.state['min_id']} to {self.state['max_id']}\n\n"
                    "3. Select messages to forward:\n"
                    "• <code>all</code> - All messages\n"
                    "• <code>100-200</code> - Range\n"
                    "• <code>1,2,3</code> - Specific IDs\n\n"
                    "Type /cancel to stop"
                )

            elif self.state['step'] == 3:
                if text.lower() == 'all':
                    selected_ids = self.state['all_message_ids']
                elif '-' in text:
                    try:
                        start, end = map(int, text.split('-'))
                        selected_ids = [mid for mid in self.state['all_message_ids'] if start <= mid <= end]
                        if not selected_ids:
                            raise ValueError("❌ No messages in specified range")
                    except ValueError:
                        raise ValueError("❌ Invalid range format. Use 'start-end'")
                else:
                    try:
                        requested_ids = [int(id.strip()) for id in text.split(',')]
                        selected_ids = [mid for mid in self.state['all_message_ids'] if mid in requested_ids]
                        if not selected_ids:
                            raise ValueError("❌ No matching IDs found")
                    except ValueError:
                        raise ValueError("❌ Invalid ID format. Use comma-separated numbers")
                
                self.state['message_ids'] = sorted(selected_ids)
                self.state['step'] = 4
                await message.reply_text(
                    "4. Delete successfully forwarded messages?\n"
                    "Send <code>delete</code> to enable deletion\n"
                    "Send <code>keep</code> to keep original messages"
                )

            elif self.state['step'] == 4:
                if text.lower() == 'delete':
                    self.state['delete_after_forward'] = True
                    await message.reply_text("🗑️ Deletion after forwarding enabled")
                elif text.lower() == 'keep':
                    self.state['delete_after_forward'] = False
                    await message.reply_text("💾 Original messages will be kept")
                else:
                    raise ValueError("❌ Invalid option. Send 'delete' or 'keep'")
                
                await self._start_forwarding(message)

        except Exception as e:
            await message.reply_text(f"❌ Error: {str(e)}")
            self.reset_state()

    def __del__(self):
        """Destructor to clean up temp files"""
        self._clean_temp_files()