import os
import asyncio
import json
import time
import shutil
from typing import List, Dict, Tuple
from pyrogram import Client, raw
from pyrogram.types import Message
from pyrogram.errors import FloodWait, RPCError

class ForwardBot:
    def __init__(self, bot: Client):
        self.bot = bot
        self.base_temp_dir = "forward_temp"
        self.media_temp_dir = os.path.join(self.base_temp_dir, "media_temp")
        self.message_temp_dir = os.path.join(self.base_temp_dir, "message_temp")
        
        os.makedirs(self.media_temp_dir, exist_ok=True)
        os.makedirs(self.message_temp_dir, exist_ok=True)
        
        self._clear_media_temp()
        self.reset_state()
        
        # Configuration
        self.MAX_PARALLEL = 1
        self.SCAN_WORKERS = 5
        self.SCAN_BATCH_SIZE = 5000
        self.FORWARD_DELAY = 10
        self.PROGRESS_UPDATE_INTERVAL = 2
        self.GET_HISTORY_LIMIT = 1000

    def _clear_media_temp(self):
        """Clear all files in media_temp directory"""
        for filename in os.listdir(self.media_temp_dir):
            file_path = os.path.join(self.media_temp_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"Failed to delete {file_path}. Reason: {e}")

    def reset_state(self):
        """Reset bot state and clear media temp files"""
        self._clear_media_temp()
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
            'processing_queue': asyncio.Queue(),
            'workers': [],
            'is_running': False,
            'scan_workers': [],
            'scan_queue': asyncio.Queue(),
            'scan_results': [],
            'scan_progress': {'scanned': 0, 'total': 0},
            'scan_lock': asyncio.Lock(),
            'worker_status': {},
            'last_progress_text': None,
            'last_progress_time': 0,
            'resume_scan': False
        }

    def _get_cache_filename(self, chat_id: int, username: str = None):
        """Generate cache filename in message_temp directory"""
        if username:
            return os.path.join(self.message_temp_dir, f"{username}_{chat_id}_messages.json")
        return os.path.join(self.message_temp_dir, f"{chat_id}_messages.json")

    async def _load_cached_messages(self, chat_id: int, username: str = None):
        """Load cached messages from file if exists in message_temp"""
        cache_file = self._get_cache_filename(chat_id, username)
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data.get('message_ids', []), data.get('min_id'), data.get('max_id')
            except Exception as e:
                print(f"Cache load error: {e}")
        return [], None, None

    async def _save_cached_messages(self, chat_id: int, message_ids: List[int], 
                                  min_id: int, max_id: int, username: str = None):
        """Save messages to cache file in message_temp"""
        cache_file = self._get_cache_filename(chat_id, username)
        data = {
            'message_ids': message_ids,
            'min_id': min_id,
            'max_id': max_id,
            'timestamp': time.time()
        }
        try:
            with open(cache_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Cache save error: {e}")

    async def _update_cached_messages(self, chat_id: int, new_ids: List[int], 
                                    new_min_id: int, new_max_id: int, username: str = None):
        """Update existing cache with new messages"""
        cache_file = self._get_cache_filename(chat_id, username)
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                
                existing_ids = set(data.get('message_ids', []))
                updated_ids = sorted(list(existing_ids.union(set(new_ids))))
                
                data.update({
                    'message_ids': updated_ids,
                    'min_id': min(data.get('min_id', new_min_id), new_min_id),
                    'max_id': max(data.get('max_id', new_max_id), new_max_id),
                    'timestamp': time.time()
                })
                
                with open(cache_file, 'w') as f:
                    json.dump(data, f)
                
                return updated_ids, data['min_id'], data['max_id']
            except Exception as e:
                print(f"Cache update error: {e}")
        
        return new_ids, new_min_id, new_max_id

    async def _remove_deleted_from_cache(self, chat_id: int, deleted_ids: List[int], username: str = None):
        """Remove deleted message IDs from cache"""
        cache_file = self._get_cache_filename(chat_id, username)
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                
                remaining_ids = [msg_id for msg_id in data.get('message_ids', []) 
                               if msg_id not in deleted_ids]
                
                data['message_ids'] = remaining_ids
                
                with open(cache_file, 'w') as f:
                    json.dump(data, f)
                
                return remaining_ids
            except Exception as e:
                print(f"Cache update error: {e}")
        return []

    async def _get_newest_message_id(self, chat_id: int) -> int:
        """Get the newest message ID from chat"""
        try:
            async for msg in self.bot.get_chat_history(chat_id, limit=1):
                if msg and not msg.empty:
                    return msg.id
        except Exception as e:
            print(f"Error getting newest message: {e}")
        return None

    async def _scan_worker(self, worker_id: int):
        """Worker to scan message ranges"""
        while not self.state['cancelled']:
            try:
                start_id, end_id = await self.state['scan_queue'].get()
                
                if self.state['cancelled']:
                    self.state['scan_queue'].task_done()
                    break
                    
                self.state['worker_status'][worker_id] = f"Scanning {start_id}-{end_id}"
                
                try:
                    peer = await self.bot.resolve_peer(self.state['target_chat'].id)
                    current_max = end_id
                    batch_messages = []
                    retry_count = 0
                    
                    while current_max >= start_id and not self.state['cancelled']:
                        try:
                            result = await self.bot.invoke(
                                raw.functions.messages.GetHistory(
                                    peer=peer,
                                    offset_id=current_max,
                                    offset_date=0,
                                    add_offset=0,
                                    limit=self.GET_HISTORY_LIMIT,
                                    max_id=current_max,
                                    min_id=start_id,
                                    hash=0
                                ),
                                sleep_threshold=10
                            )
                            
                            if not isinstance(result, (raw.types.messages.Messages,
                                                    raw.types.messages.MessagesSlice,
                                                    raw.types.messages.ChannelMessages)):
                                break
                                
                            if not result.messages:
                                break
                                
                            messages = [msg.id for msg in result.messages]
                            batch_messages.extend(messages)
                            
                            async with self.state['scan_lock']:
                                self.state['scan_progress']['scanned'] += len(messages)
                                if not self.state['min_id'] or min(messages) < self.state['min_id']:
                                    self.state['min_id'] = min(messages)
                                if not self.state['max_id'] or max(messages) > self.state['max_id']:
                                    self.state['max_id'] = max(messages)
                            
                            current_max = min(messages) - 1
                            retry_count = 0
                            
                        except FloodWait as e:
                            await asyncio.sleep(e.value)
                            continue
                        except Exception as e:
                            retry_count += 1
                            if retry_count > 3:
                                print(f"Failed after 3 retries: {e}")
                                break
                            await asyncio.sleep(1)
                            continue
                    
                    async with self.state['scan_lock']:
                        self.state['scan_results'].extend(batch_messages)
                    
                except Exception as e:
                    print(f"Error scanning batch {start_id}-{end_id}: {e}")
                
                self.state['scan_queue'].task_done()
                self.state['worker_status'][worker_id] = "Idle"
                
            except Exception as e:
                print(f"Scan worker error: {e}")
                if not self.state['scan_queue'].empty():
                    self.state['scan_queue'].task_done()
                self.state['worker_status'][worker_id] = f"Error: {str(e)}"
                continue

    async def _update_scan_progress(self, message: Message):
        """Update scanning progress message"""
        try:
            while (not self.state['cancelled'] and 
                  (not self.state['scan_queue'].empty() or 
                   any(not w.done() for w in self.state['scan_workers']))):

                current_time = asyncio.get_event_loop().time()
                if current_time - self.state['last_progress_time'] >= self.PROGRESS_UPDATE_INTERVAL:
                    async with self.state['scan_lock']:
                        scanned = self.state['scan_progress']['scanned']
                        total = self.state['scan_progress']['total']
                        progress = min(100, int((scanned / total) * 100)) if total > 0 else 0
                        
                        worker_statuses = "\n".join(
                            f"👷 Worker {i+1}: {status}" 
                            for i, status in enumerate(self.state['worker_status'].values()))
                        
                        progress_text = (
                            f"🔍 Scanning messages...\n"
                            f"📊 Progress: {progress}%\n"
                            f"🔢 Scanned: {scanned}/{total}\n"
                            f"🆔 Range: {self.state['min_id'] or '?'} to {self.state['max_id'] or '?'}\n\n"
                            f"{worker_statuses}"
                        )
                        
                        if progress_text != self.state['last_progress_text']:
                            try:
                                if self.state['progress_msg']:
                                    await self.state['progress_msg'].edit_text(progress_text)
                                else:
                                    self.state['progress_msg'] = await message.reply_text(progress_text)
                                self.state['last_progress_text'] = progress_text
                                self.state['last_progress_time'] = current_time
                            except Exception as e:
                                print(f"Error updating progress: {e}")
                
                await asyncio.sleep(0.5)
        finally:
            if self.state['progress_msg']:
                try:
                    await self.state['progress_msg'].delete()
                except:
                    pass
                self.state['progress_msg'] = None
                self.state['last_progress_text'] = None

    async def _forward_media(self, message: Message, dest_chat) -> bool:
        """Forward media message with download fallback to media_temp"""
        temp_path = None
        thumb_path = None
        
        try:
            try:
                await message.copy(dest_chat.id)
                await asyncio.sleep(self.FORWARD_DELAY)
                return True
            except Exception as copy_err:
                print(f"Copy failed, trying download-upload: {copy_err}")

            file_ext = ".mp4" if message.video else ".jpg" if message.photo else ""
            temp_filename = f"media_{message.id}{file_ext}"
            temp_path = os.path.join(self.media_temp_dir, temp_filename)
            
            temp_path = await self.bot.download_media(message, file_name=temp_path)
            
            if not temp_path or not os.path.exists(temp_path):
                print(f"Download failed for message {message.id}")
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
                        thumb_filename = f"thumb_{message.id}.jpg"
                        thumb_path = os.path.join(self.media_temp_dir, thumb_filename)
                        thumb_path = await self.bot.download_media(message.video.thumbs[0].file_id, file_name=thumb_path)
                    except Exception as thumb_err:
                        print(f"Thumbnail download failed, generating with ffmpeg: {thumb_err}")
                        thumb_path = await self._generate_thumbnail(temp_path)
                
                if thumb_path:
                    video_args['thumb'] = thumb_path
                
                try:
                    await self.bot.send_video(dest_chat.id, temp_path, **video_args)
                    await asyncio.sleep(self.FORWARD_DELAY)
                finally:
                    if thumb_path and os.path.exists(thumb_path):
                        try:
                            os.remove(thumb_path)
                        except:
                            pass
            elif message.document:
                if message.document.thumbs:
                    try:
                        thumb_filename = f"doc_thumb_{message.id}.jpg"
                        thumb_path = os.path.join(self.media_temp_dir, thumb_filename)
                        thumb_path = await self.bot.download_media(message.document.thumbs[0].file_id, file_name=thumb_path)
                        send_args['thumb'] = thumb_path
                    except Exception as thumb_err:
                        print(f"Document thumbnail download failed: {thumb_err}")
                
                await self.bot.send_document(dest_chat.id, temp_path, **send_args)
                await asyncio.sleep(self.FORWARD_DELAY)
            elif message.photo:
                await self.bot.send_photo(dest_chat.id, temp_path, **send_args)
                await asyncio.sleep(self.FORWARD_DELAY)
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

    async def _forward_message(self, message_id: int, dest_chat) -> bool:
        """Forward a single message by ID"""
        if self.state['cancelled']:
            return False

        try:
            msg = await self.bot.get_messages(self.state['target_chat'].id, message_id)
            if not msg or msg.empty:
                self.state['message_status'][message_id] = {
                    'status': 'skipped',
                    'progress': 0
                }
                return False
                
            self.state['message_status'][message_id] = {
                'status': 'in_progress',
                'progress': 20
            }
            
            if msg.media:
                result = await self._forward_media(msg, dest_chat)
            elif msg.text:
                try:
                    await self.bot.send_message(
                        dest_chat.id,
                        msg.text,
                        entities=msg.entities,
                        reply_to_message_id=msg.reply_to_message_id if msg.reply_to_message_id else None
                    )
                    await asyncio.sleep(self.FORWARD_DELAY)
                    result = True
                except Exception as text_err:
                    print(f"Error sending text message: {text_err}")
                    result = False
            else:
                try:
                    await msg.copy(dest_chat.id)
                    await asyncio.sleep(self.FORWARD_DELAY)
                    result = True
                except Exception as copy_err:
                    print(f"Error copying message: {copy_err}")
                    result = False
            
            if result:
                self.state['message_status'][message_id] = {
                    'status': 'completed',
                    'progress': 100
                }
                self.state['success_count'] += 1
            else:
                self.state['message_status'][message_id] = {
                    'status': 'failed',
                    'progress': 0
                }
                self.state['failed_messages'].append(message_id)
            
            return result
            
        except Exception as e:
            print(f"Error forwarding message: {e}")
            self.state['message_status'][message_id] = {
                'status': 'failed',
                'progress': 0
            }
            self.state['failed_messages'].append(message_id)
            return False

    async def _worker(self, worker_id: int, dest_chat):
        """Worker to process messages from queue"""
        while not self.state['cancelled']:
            try:
                msg_id = await self.state['processing_queue'].get()
                
                if self.state['cancelled']:
                    self.state['processing_queue'].task_done()
                    break
                    
                self.state['worker_status'][worker_id] = f"Processing {msg_id}"
                
                try:
                    await self._forward_message(msg_id, dest_chat)
                except Exception as e:
                    print(f"Error processing {msg_id}: {e}")
                    self.state['message_status'][msg_id] = {
                        'status': 'failed',
                        'progress': 0
                    }
                    self.state['failed_messages'].append(msg_id)
                
                self.state['processing_queue'].task_done()
                self.state['worker_status'][worker_id] = "Idle"
                
            except Exception as e:
                print(f"Worker error: {e}")
                self.state['processing_queue'].task_done()
                self.state['worker_status'][worker_id] = f"Error: {str(e)}"

    async def _continuous_progress_updater(self, message: Message):
        """Update forwarding progress periodically"""
        while self.state['is_running'] and not self.state['cancelled']:
            try:
                await self._update_progress(message)
                await asyncio.sleep(self.PROGRESS_UPDATE_INTERVAL)
            except Exception as e:
                print(f"Progress updater error: {e}")
                await asyncio.sleep(1)
        
        try:
            await self._update_progress(message)
        except Exception as e:
            print(f"Final progress update error: {e}")

    async def _update_progress(self, message: Message):
        """Update progress message with current status"""
        if not self.state['active'] or self.state['cancelled']:
            return

        target = self.state['target_chat']
        total = len(self.state['message_ids'])
        
        completed = sum(1 for status in self.state['message_status'].values() 
                     if status.get('status') == 'completed')
        in_progress = sum(1 for status in self.state['message_status'].values() 
                        if status.get('status') == 'in_progress')
        failed = sum(1 for status in self.state['message_status'].values() 
                if status.get('status') == 'failed')
        skipped = sum(1 for status in self.state['message_status'].values() 
                 if status.get('status') == 'skipped')

        worker_statuses = "\n".join(
            f"👷 Worker {i+1}: {status}" 
            for i, status in enumerate(self.state['worker_status'].values()))
        
        progress_text = (
            f"📊 Forwarding Progress\n\n"
            f"✅ Completed: {completed}/{total}\n"
            f"🔄 In Progress: {in_progress}\n"
            f"❌ Failed: {failed}\n"
            f"⚠️ Skipped: {skipped}\n\n"
            f"{worker_statuses}\n\n"
        )

        active_messages = [
            msg_id for msg_id, status in self.state['message_status'].items()
            if status.get('status') in ('pending', 'in_progress')
        ][:5]

        for msg_id in active_messages:
            status = self.state['message_status'].get(msg_id, {})
            progress = status.get('progress', 0)
            
            status_text = {
                'pending': f'pending ({progress}%)',
                'in_progress': f'forwarding ({progress}%)',
                'completed': 'completed ✅',
                'failed': 'failed ❌',
                'skipped': 'skipped ⚠️'
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

        if progress_text != self.state['last_progress_text']:
            try:
                if self.state['progress_msg']:
                    await self.state['progress_msg'].edit_text(progress_text)
                else:
                    self.state['progress_msg'] = await message.reply_text(progress_text)
                self.state['last_progress_text'] = progress_text
            except Exception as e:
                print(f"Error updating progress: {e}")

    async def _start_forwarding(self, message: Message):
        """Start the forwarding process"""
        self.state['is_running'] = True
        dest = self.state['destination_chat']
        
        self.state['worker_status'] = {
            i: "Waiting" for i in range(self.MAX_PARALLEL)
        }
        
        self.state['message_status'] = {
            msg_id: {'status': 'pending', 'progress': 0} 
            for msg_id in self.state['message_ids']
        }
        
        self.state['workers'] = [
            asyncio.create_task(self._worker(i, dest))
            for i in range(self.MAX_PARALLEL)
        ]
        
        self.state['progress_updater_task'] = asyncio.create_task(
            self._continuous_progress_updater(message)
        )
        
        for msg_id in self.state['message_ids']:
            await self.state['processing_queue'].put(msg_id)
        
        await self.state['processing_queue'].join()
        
        for worker in self.state['workers']:
            worker.cancel()
        await asyncio.gather(*self.state['workers'], return_exceptions=True)
        
        self.state['is_running'] = False
        if self.state['progress_updater_task']:
            self.state['progress_updater_task'].cancel()
            try:
                await self.state['progress_updater_task']
            except:
                pass
        
        if self.state['delete_after_forward'] and not self.state['cancelled']:
            await self._delete_forwarded_messages(message)

        await self._send_completion_report(message)
        self.reset_state()

    async def _delete_forwarded_messages(self, message: Message):
        """Delete forwarded messages and update cache"""
        target = self.state['target_chat']
        username = target.username if hasattr(target, 'username') else None
        success_ids = [
            msg_id for msg_id, status in self.state['message_status'].items()
            if status.get('status') == 'completed'
        ]
        
        if not success_ids:
            return

        await message.reply_text(f"🗑️ Deleting {len(success_ids)} messages...")
        
        batch_size = 100
        deleted_ids = []
        
        for i in range(0, len(success_ids), batch_size):
            batch = success_ids[i:i + batch_size]
            try:
                await self.bot.delete_messages(target.id, batch)
                deleted_ids.extend(batch)
            except Exception as e:
                await message.reply_text(f"⚠️ Failed to delete batch: {str(e)}")
        
        # Update cache by removing deleted IDs
        if deleted_ids and self.state['delete_after_forward']:
            await self._remove_deleted_from_cache(target.id, deleted_ids, username)
            self.state['deleted_messages'].extend(deleted_ids)

    async def start_forward_setup(self, message: Message):
        """Start the forwarding setup process"""
        self.reset_state()
        self.state['active'] = True
        self.state['step'] = 1
        await message.reply_text(
            "📨 <b>Forward Setup</b>\n\n"
            "1. Send <b>TARGET</b> chat (username/ID/URL):\n\n"
            "Type /cancel to stop"
        )

    async def handle_setup_message(self, message: Message):
        """Handle user input during setup"""
        if not self.state['active'] or self.state['cancelled']:
            return

        try:
            text = message.text.strip()
            if text.lower() == '/cancel':
                self.state['cancelled'] = True
                await message.reply_text("❌ Process cancelled")
                self.reset_state()
                return

            if self.state['step'] == 1:
                try:
                    target = await self.bot.get_chat(text)
                    self.state['target_chat'] = target
                    
                    # Verify we can access messages
                    try:
                        test_msg = await self.bot.get_messages(target.id, 1)
                        if not test_msg or test_msg.empty:
                            raise ValueError("Couldn't access messages")
                    except Exception as e:
                        raise ValueError(f"Can't access chat messages: {str(e)}")
                    
                    await message.reply_text("🔍 Scanning messages...")
                    self.state['all_message_ids'] = await self._scan_and_cache_messages(target.id, message)
                    
                    if not self.state['all_message_ids']:
                        raise ValueError("❌ No messages found in target chat")
                    
                    self.state['step'] = 2
                    await message.reply_text(
                        f"✅ <b>Target set:</b> {target.title if hasattr(target, 'title') else 'Private Chat'}\n\n"
                        f"📊 Message IDs: {self.state['min_id']} to {self.state['max_id']}\n"
                        f"💬 Total messages: {len(self.state['all_message_ids'])}\n\n"
                        "2. Send <b>DESTINATION</b> chat:"
                    )

                except Exception as e:
                    raise ValueError(f"❌ Error setting target: {str(e)}")

            elif self.state['step'] == 2:
                dest = await self.bot.get_chat(text)
                self.state['destination_chat'] = dest
                
                me = await self.bot.get_me()
                try:
                    member = await self.bot.get_chat_member(dest.id, me.id)
                    if not member.privileges or not member.privileges.can_post_messages:
                        raise ValueError("❌ Bot needs 'Post Messages' permission")
                except Exception as e:
                    raise ValueError(f"❌ Can't check bot permissions: {str(e)}")
                
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

    async def _send_completion_report(self, message: Message):
        """Send final report after forwarding completes and clear media_temp"""
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
                    if status.get('status') == 'completed' and not status.get('deleted', False)
                ]
                report += f"\nFailed delete IDs:\n{', '.join(map(str, failed_deletes))}"
        
        # Clear media temp after successful forwarding
        self._clear_media_temp()
        
        await message.reply_text(report)

    async def _scan_and_cache_messages(self, chat_id: int, message: Message):
        """Main scanning function with caching logic"""
        try:
            # Get chat info and username for cache filename
            chat = await self.bot.get_chat(chat_id)
            username = chat.username if hasattr(chat, 'username') else None
            cache_file = self._get_cache_filename(chat_id, username)
            
            # Load existing cache if available
            cached_ids, cached_min, cached_max = await self._load_cached_messages(chat_id, username)
            
            # Get current newest message ID
            current_max_id = await self._get_newest_message_id(chat_id)
            
            if current_max_id is None:
                raise ValueError("❌ Could not access chat messages")
            
            # Check if we need to scan at all
            if cached_ids and cached_max and current_max_id <= cached_max:
                # No new messages, use cached data
                self.state['all_message_ids'] = cached_ids
                self.state['min_id'] = cached_min
                self.state['max_id'] = cached_max
                self.state['resume_scan'] = True
                return cached_ids
            
            # Initialize scan state
            self.state['scan_results'] = []
            self.state['min_id'] = cached_min if cached_min else None
            self.state['max_id'] = current_max_id
            
            # If we have existing cache, only scan new messages
            scan_min = cached_max + 1 if cached_max else 1
            scan_max = current_max_id
            
            # Initialize progress tracking
            total_to_scan = scan_max - scan_min + 1
            self.state['scan_progress'] = {
                'scanned': 0,
                'total': total_to_scan if total_to_scan > 0 else 1
            }
            
            # Initialize workers
            self.state['worker_status'] = {
                i: "Waiting" for i in range(self.SCAN_WORKERS)
            }
            self.state['scan_workers'] = [
                asyncio.create_task(self._scan_worker(i))
                for i in range(self.SCAN_WORKERS)
            ]
            
            progress_task = asyncio.create_task(self._update_scan_progress(message))
            
            try:
                # Divide the work into chunks
                chunk_size = self.SCAN_BATCH_SIZE
                current_id = scan_max
                
                while current_id >= scan_min and not self.state['cancelled']:
                    chunk_end = current_id
                    chunk_start = max(scan_min, current_id - chunk_size + 1)
                    await self.state['scan_queue'].put((chunk_start, chunk_end))
                    current_id = chunk_start - 1
            except Exception as e:
                print(f"Error creating scan batches: {e}")
                self.state['cancelled'] = True
            
            try:
                await self.state['scan_queue'].join()
            except Exception as e:
                print(f"Error waiting for scan queue: {e}")
                self.state['cancelled'] = True
            
            # Clean up workers
            for worker in self.state['scan_workers']:
                if not worker.done():
                    worker.cancel()
            
            await asyncio.gather(*self.state['scan_workers'], return_exceptions=True)
            progress_task.cancel()
            
            try:
                await progress_task
            except:
                pass
            
            if self.state['cancelled']:
                raise ValueError("❌ Scan cancelled by user")
            
            new_message_ids = sorted(list(set(self.state['scan_results'])))
            
            if not new_message_ids and not cached_ids:
                raise ValueError("❌ No messages found after full scan")
            
            # Combine with cached messages if available
            if cached_ids:
                all_message_ids = sorted(list(set(cached_ids + new_message_ids)))
                min_id = min(cached_min, self.state['min_id']) if cached_min else self.state['min_id']
                max_id = max(cached_max, self.state['max_id']) if cached_max else self.state['max_id']
            else:
                all_message_ids = new_message_ids
                min_id = self.state['min_id']
                max_id = self.state['max_id']
            
            # Save/update cache
            if cached_ids:
                await self._update_cached_messages(chat_id, new_message_ids, min_id, max_id, username)
            else:
                await self._save_cached_messages(chat_id, all_message_ids, min_id, max_id, username)
            
            self.state['all_message_ids'] = all_message_ids
            self.state['min_id'] = min_id
            self.state['max_id'] = max_id
            
            return all_message_ids

        except Exception as e:
            print(f"Scan and cache error: {e}")
            raise ValueError(f"❌ Error: {str(e)}")

    async def _generate_thumbnail(self, video_path: str) -> str:
        """Generate thumbnail for video using ffmpeg"""
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
            else:
                print(f"ffmpeg failed to generate thumbnail: {stderr.decode().strip()}")
                return None
        except Exception as e:
            print(f"Error generating thumbnail with ffmpeg: {e}")
            return None
