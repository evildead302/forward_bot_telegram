import asyncio
import re
import tempfile
import os
import json
from typing import List, Dict, Optional
from pyrogram import Client, raw
from pyrogram.types import Message
from pyrogram.errors import FloodWait, RPCError
from collections import deque
import time

class CombinedLinkForwarder:
    def __init__(self, bot: Client):
        self.bot = bot
        self.temp_dir = tempfile.mkdtemp(prefix="temp_cl_data_")
        os.makedirs(self.temp_dir, exist_ok=True)
        self.clean_temp_dir()
        
        # Worker configuration
        self.worker_config = {
            'link_processor': 1,
            'forwarders': 3,
            'deleter': 1
        }
        
        # Worker queues
        self.link_queue = asyncio.Queue()
        self.forward_queue = asyncio.Queue()
        self.delete_queue = asyncio.Queue()
        
        # Worker tasks
        self.workers = {
            'link_processor': [],
            'forwarders': [],
            'deleter': []
        }
        
        # Shared state
        self.state = {
            'active': False,
            'processing': False,
            'cancelled': False,
            'status_chat_id': None,
            'destination_chat': None,
            'current_sequence': 0,
            'total_links': 0,
            'processed_links': 0,
            'collected_links': 0,
            'stats': {
                'links_processed': 0,
                'messages_forwarded': 0,
                'messages_failed': 0,
                'messages_deleted': 0,
                'current_link': None,
                'current_link_messages': 0,
                'pending_deletions': 0,
                'pending_forwards': 0
            }
        }
        
        # Configurable settings
        self.settings = {
            'initial_wait': 10,
            'stabilization_checks': 12,
            'progress_update_interval': 10,
            'completion_delay': 3
        }

    def clean_temp_dir(self):
        """Clean up temp directory"""
        try:
            for filename in os.listdir(self.temp_dir):
                file_path = os.path.join(self.temp_dir, filename)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"Error deleting temp file {file_path}: {e}")
        except Exception as e:
            print(f"Error cleaning temp dir: {e}")

    async def send_status(self, text: str):
        """Send status updates to user"""
        if self.state['status_chat_id']:
            try:
                await self.bot.send_message(self.state['status_chat_id'], text)
            except Exception:
                pass

    def extract_links(self, text: str) -> list:
        """Extract t.me bot links from text"""
        if not text:
            return []
        pattern = r'(?:https?://)?(?:t\.me/|telegram\.me/)([a-zA-Z0-9_]+)\?start=([a-zA-Z0-9_-]+)'
        return [f"https://t.me/{m.group(1)}?start={m.group(2)}" 
               for m in re.finditer(pattern, text)]

    async def _get_last_message_id(self, chat_id: int) -> Optional[int]:
        """Get last message ID in chat"""
        try:
            async for message in self.bot.get_chat_history(chat_id, limit=1):
                if message and not message.empty:
                    return message.id
        except Exception as e:
            await self.send_status(f"⚠️ Error getting last message ID: {str(e)}")
            return None

    async def _resolve_username(self, username: str):
        """Resolve username to chat ID"""
        try:
            peer = await self.bot.resolve_peer(username)
            return peer.user_id if hasattr(peer, 'user_id') else peer.chat_id
        except Exception as e:
            await self.send_status(f"⚠️ Error resolving @{username}: {str(e)}")
            return None

    async def _wait_for_stabilization(self, chat_id: int, initial_msg_id: int) -> Optional[int]:
        """Wait for message flow to stabilize"""
        last_msg_id = initial_msg_id
        checks_done = 0
        
        while checks_done < self.settings['stabilization_checks']:
            await asyncio.sleep(self.settings['initial_wait'])
            current_msg_id = await self._get_last_message_id(chat_id)
            
            if current_msg_id is None:
                return None
                
            if current_msg_id == last_msg_id:
                return last_msg_id
                
            last_msg_id = current_msg_id
            checks_done += 1
            
            await self.send_status(
                f"🔍 Stabilization check {checks_done}/{self.settings['stabilization_checks']} "
                f"New messages detected (ID: {current_msg_id})"
            )
        
        return last_msg_id

    async def _save_link_data(self, link: str):
        """Save link to processing queue file"""
        links_file = os.path.join(self.temp_dir, "links_queue.json")
        try:
            data = []
            if os.path.exists(links_file):
                with open(links_file, 'r') as f:
                    data = json.load(f)
            
            data.append(link)
            
            with open(links_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            await self.send_status(f"⚠️ Error saving link data: {str(e)}")

    async def _save_messages_to_forward(self, username: str, messages: List[int]):
        """Save messages to forward queue file"""
        messages_file = os.path.join(self.temp_dir, "messages_to_forward.json")
        try:
            data = []
            if os.path.exists(messages_file):
                with open(messages_file, 'r') as f:
                    data = json.load(f)
            
            for msg_id in messages:
                data.append({
                    'username': username,
                    'message_id': msg_id,
                    'sequence': self.state['current_sequence'],
                    'status': 'pending'
                })
                self.state['current_sequence'] += 1
            
            with open(messages_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            await self.send_status(f"⚠️ Error saving messages to forward: {str(e)}")

    async def _save_messages_to_delete(self, username: str, messages: List[int]):
        """Save messages to delete queue file"""
        delete_file = os.path.join(self.temp_dir, "messages_to_delete.json")
        try:
            data = []
            if os.path.exists(delete_file):
                with open(delete_file, 'r') as f:
                    data = json.load(f)
            
            for msg_id in messages:
                data.append({
                    'username': username,
                    'message_id': msg_id
                })
            
            with open(delete_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            await self.send_status(f"⚠️ Error saving messages to delete: {str(e)}")

    async def link_processor_worker(self):
        """Worker that processes links and finds messages to forward"""
        while not self.state['cancelled'] and self.state['processing']:
            try:
                link = await self.link_queue.get()
                if link is None:
                    break
                
                username = link.split('/')[3].split('?')[0]
                start_param = link.split('start=')[1]

                # Update total links count dynamically
                current_total = max(self.state['total_links'], self.state['processed_links'] + self.link_queue.qsize() + 1)
                self.state['total_links'] = current_total

                # Send link processing report
                await self.send_status(
                    f"🔗 Processing link {self.state['processed_links'] + 1}/{self.state['total_links']}: {link}"
                )
                self.state['stats']['current_link'] = username

                # Resolve chat ID
                chat_id = await self._resolve_username(username)
                if not chat_id:
                    self.state['processed_links'] += 1
                    continue

                # Get initial last message ID
                initial_msg_id = await self._get_last_message_id(chat_id)
                if not initial_msg_id:
                    self.state['processed_links'] += 1
                    continue

                # Wait for stabilization before invoking
                stabilized_msg_id = await self._wait_for_stabilization(chat_id, initial_msg_id)
                if not stabilized_msg_id:
                    self.state['processed_links'] += 1
                    continue

                # Invoke the bot
                try:
                    peer = await self.bot.resolve_peer(username)
                    await self.bot.invoke(
                        raw.functions.messages.StartBot(
                            bot=peer,
                            peer=peer,
                            start_param=start_param,
                            random_id=self.bot.rnd_id()
                        )
                    )
                    
                    # Wait after invoking
                    await asyncio.sleep(self.settings['initial_wait'])
                    first_after_msg_id = await self._get_last_message_id(chat_id)
                    
                    if not first_after_msg_id:
                        self.state['processed_links'] += 1
                        continue

                    # Wait for stabilization after invoking
                    stabilized_after_msg_id = await self._wait_for_stabilization(chat_id, first_after_msg_id)
                    if not stabilized_after_msg_id:
                        self.state['processed_links'] += 1
                        continue

                    # Collect messages between initial and final message IDs
                    message_ids = []
                    async for message in self.bot.get_chat_history(chat_id):
                        if message and not message.empty and stabilized_msg_id < message.id <= stabilized_after_msg_id:
                            message_ids.append(message.id)
                        elif message.id <= stabilized_msg_id:
                            break
                    
                    # Send link processed report
                    await self.send_status(
                        f"✅ Link processed for @{username}\n"
                        f"📨 Message range: {stabilized_msg_id + 1}-{stabilized_after_msg_id}\n"
                        f"🔢 Available messages: {len(message_ids)}"
                    )
                    self.state['stats']['current_link_messages'] = len(message_ids)

                    # Save messages to forward and delete queues
                    if message_ids:
                        await self._save_messages_to_forward(username, message_ids)
                        await self._save_messages_to_delete(username, message_ids)
                        self.state['stats']['links_processed'] += 1
                        
                        # Put messages in forward queue (oldest first)
                        for msg_id in sorted(message_ids):
                            await self.forward_queue.put({
                                'username': username,
                                'message_id': msg_id,
                                'chat_id': chat_id
                            })
                            self.state['stats']['pending_forwards'] += 1

                    self.state['processed_links'] += 1

                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    await self.link_queue.put(link)  # Retry same link
                except Exception as e:
                    await self.send_status(f"❌ Failed @{username}: {str(e)}")
                    self.state['processed_links'] += 1

            except Exception as e:
                await self.send_status(f"🚨 Link processor error: {str(e)}")
                self.state['processed_links'] += 1
            finally:
                self.link_queue.task_done()

    async def forwarder_worker(self):
        """Worker that forwards messages in sequence"""
        while not self.state['cancelled'] and self.state['processing']:
            try:
                task = await self.forward_queue.get()
                if task is None:
                    break
                
                username = task['username']
                message_id = task['message_id']
                chat_id = task['chat_id']
                
                # Get the message
                try:
                    message = await self.bot.get_messages(chat_id, message_id)
                    if not message or message.empty:
                        self.state['stats']['messages_failed'] += 1
                        self.state['stats']['pending_forwards'] -= 1
                        continue
                    
                    # Forward the message
                    try:
                        if message.media:
                            await message.copy(self.state['destination_chat'].id)
                        else:
                            await self.bot.send_message(
                                self.state['destination_chat'].id,
                                message.text,
                                entities=message.entities
                            )
                        self.state['stats']['messages_forwarded'] += 1
                        
                        # Put in delete queue and increment pending deletions
                        self.state['stats']['pending_deletions'] += 1
                        await self.delete_queue.put({
                            'username': username,
                            'message_id': message_id,
                            'chat_id': chat_id
                        })
                        
                        await self.send_status(f"🗑️ Deleted message {message_id} from @{username}")
                        
                    except RPCError as e:
                        if "CHAT_FORWARDS_RESTRICTED" in str(e):
                            # Fallback to download-upload
                            success = await self._download_and_upload(message)
                            if success:
                                self.state['stats']['messages_forwarded'] += 1
                                self.state['stats']['pending_deletions'] += 1
                                await self.delete_queue.put({
                                    'username': username,
                                    'message_id': message_id,
                                    'chat_id': chat_id
                                })
                                await self.send_status(f"🗑️ Deleted message {message_id} from @{username}")
                            else:
                                self.state['stats']['messages_failed'] += 1
                        else:
                            self.state['stats']['messages_failed'] += 1
                            await self.send_status(f"⚠️ Failed to forward {message_id}: {str(e)}")
                    
                    self.state['stats']['pending_forwards'] -= 1
                except Exception as e:
                    self.state['stats']['messages_failed'] += 1
                    self.state['stats']['pending_forwards'] -= 1
                    await self.send_status(f"⚠️ Error getting message {message_id}: {str(e)}")

            except Exception as e:
                await self.send_status(f"🚨 Forwarder worker error: {str(e)}")
            finally:
                self.forward_queue.task_done()

    async def deleter_worker(self):
        """Worker that deletes forwarded messages"""
        while not self.state['cancelled'] and self.state['processing']:
            try:
                task = await self.delete_queue.get()
                if task is None:
                    break
                
                message_id = task['message_id']
                chat_id = task['chat_id']
                
                try:
                    await self.bot.delete_messages(chat_id, message_id)
                    self.state['stats']['messages_deleted'] += 1
                except Exception as e:
                    await self.send_status(f"⚠️ Failed to delete {message_id}: {str(e)}")
                finally:
                    # Decrement pending deletions counter
                    self.state['stats']['pending_deletions'] -= 1
                    self.delete_queue.task_done()

            except Exception as e:
                await self.send_status(f"🚨 Deleter worker error: {str(e)}")
                self.state['stats']['pending_deletions'] -= 1
                self.delete_queue.task_done()

    async def _download_and_upload(self, message: Message) -> bool:
        """Download and upload media with thumbnail handling"""
        temp_path = None
        thumb_path = None
        try:
            # Determine file extension
            if message.video:
                file_ext = ".mp4"
            elif message.photo:
                file_ext = ".jpg"
            elif message.document:
                file_ext = os.path.splitext(message.document.file_name or "")[1] or ".bin"
            else:
                return False

            # Download media
            temp_path = os.path.join(self.temp_dir, f"media_{message.id}{file_ext}")
            temp_path = await self.bot.download_media(message, file_name=temp_path)
            
            if not temp_path or not os.path.exists(temp_path):
                return False

            # Prepare send arguments
            kwargs = {
                'caption': message.caption,
                'caption_entities': message.caption_entities
            }

            # Handle different media types
            if message.video:
                kwargs.update({
                    'duration': message.video.duration,
                    'width': message.video.width,
                    'height': message.video.height,
                    'supports_streaming': True
                })
                
                # Handle thumbnail
                if message.video.thumbs:
                    thumb_path = await self.bot.download_media(message.video.thumbs[0].file_id)
                    if thumb_path:
                        kwargs['thumb'] = thumb_path

                await self.bot.send_video(
                    chat_id=self.state['destination_chat'].id,
                    video=temp_path,
                    **kwargs
                )

            elif message.photo:
                await self.bot.send_photo(
                    chat_id=self.state['destination_chat'].id,
                    photo=temp_path,
                    **kwargs
                )

            elif message.document:
                if message.document.thumbs:
                    kwargs['thumb'] = message.document.thumbs[0].file_id
                await self.bot.send_document(
                    chat_id=self.state['destination_chat'].id,
                    document=temp_path,
                    **kwargs
                )

            return True

        except Exception as e:
            await self.send_status(f"⚠️ Download/upload failed for {message.id}: {str(e)}")
            return False
        finally:
            # Clean up temp files
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

    async def start_workers(self):
        """Start all worker tasks"""
        # Start link processor workers
        for _ in range(self.worker_config['link_processor']):
            task = asyncio.create_task(self.link_processor_worker())
            self.workers['link_processor'].append(task)
        
        # Start forwarder workers
        for _ in range(self.worker_config['forwarders']):
            task = asyncio.create_task(self.forwarder_worker())
            self.workers['forwarders'].append(task)
        
        # Start deleter workers
        for _ in range(self.worker_config['deleter']):
            task = asyncio.create_task(self.deleter_worker())
            self.workers['deleter'].append(task)

    async def stop_workers(self):
        """Stop all worker tasks gracefully"""
        # Send sentinel values to queues
        for _ in range(self.worker_config['link_processor']):
            await self.link_queue.put(None)
        for _ in range(self.worker_config['forwarders']):
            await self.forward_queue.put(None)
        for _ in range(self.worker_config['deleter']):
            await self.delete_queue.put(None)
        
        # Wait for all workers to complete
        await asyncio.gather(
            *self.workers['link_processor'],
            *self.workers['forwarders'],
            *self.workers['deleter']
        )
        
        # Clean up temp files
        self.clean_temp_dir()

    async def status_reporter(self):
        """Periodically report status and check for completion"""
        while not self.state['cancelled'] and self.state['processing']:
            # Check if all work is done (queues empty, all links processed, and no pending operations)
            queues_empty = (self.link_queue.qsize() == 0 and 
                          self.forward_queue.qsize() == 0 and 
                          self.delete_queue.qsize() == 0)
            
            all_links_processed = (self.state['processed_links'] >= self.state['total_links'])
            no_pending_operations = (self.state['stats']['pending_forwards'] == 0 and 
                                    self.state['stats']['pending_deletions'] == 0)
            
            if queues_empty and all_links_processed and no_pending_operations:
                # Small delay to ensure no more operations are pending
                await asyncio.sleep(self.settings['completion_delay'])
                
                # Final verification
                if (self.link_queue.qsize() == 0 and 
                    self.forward_queue.qsize() == 0 and 
                    self.delete_queue.qsize() == 0 and
                    self.state['stats']['pending_forwards'] == 0 and
                    self.state['stats']['pending_deletions'] == 0):
                    
                    # Calculate accurate totals
                    total_messages = (self.state['stats']['messages_forwarded'] + 
                                    self.state['stats']['messages_failed'])
                    total_links = max(self.state['total_links'], self.state['processed_links'])
                    
                    # Send final report
                    await self.send_status(
                        f"🎉 All processing complete!\n\n"
                        f"• Total links: {total_links}\n"
                        f"• Processed links: {self.state['processed_links']}\n\n"
                        f"📊 Forwarding totals:\n"
                        f"• Total messages: {total_messages}\n"
                        f"• ✅ Successfully forwarded: {self.state['stats']['messages_forwarded']}\n"
                        f"• ❌ Failed: {self.state['stats']['messages_failed']}\n\n"
                        f"🗑️ Deletion totals:\n"
                        f"• ✅ Successfully deleted: {self.state['stats']['messages_deleted']}"
                    )
                    self.state['processing'] = False
                    await self.stop_workers()
                    break
            
            # Calculate current totals
            current_total = max(self.state['total_links'], 
                              self.state['processed_links'] + self.link_queue.qsize() + 1)
            
            stats = self.state['stats']
            report = (
                "📊 Current Status:\n\n"
                f"• Links processed: {stats['links_processed']}/{current_total}\n"
                f"• Messages forwarded: {stats['messages_forwarded']}\n"
                f"• Messages failed: {stats['messages_failed']}\n"
                f"• Messages deleted: {stats['messages_deleted']}\n"
                f"• Pending forwards: {stats['pending_forwards']}\n"
                f"• Pending deletions: {stats['pending_deletions']}\n\n"
                f"• Current link: @{stats['current_link']} ({stats['current_link_messages']} messages)\n"
                f"• Links in queue: {self.link_queue.qsize()}\n"
                f"• Messages to forward: {self.forward_queue.qsize()}\n"
                f"• Messages to delete: {self.delete_queue.qsize()}"
            )
            
            await self.send_status(report)
            await asyncio.sleep(self.settings['progress_update_interval'])

    async def start_combined_process(self, message: Message):
        """Initialize combined process"""
        self.clean_temp_dir()
        self.state = {
            'active': True,
            'processing': False,
            'cancelled': False,
            'status_chat_id': message.chat.id,
            'destination_chat': None,
            'current_sequence': 0,
            'total_links': 0,
            'processed_links': 0,
            'collected_links': 0,
            'stats': {
                'links_processed': 0,
                'messages_forwarded': 0,
                'messages_failed': 0,
                'messages_deleted': 0,
                'current_link': None,
                'current_link_messages': 0,
                'pending_deletions': 0,
                'pending_forwards': 0
            }
        }
        
        await message.reply_text(
            "🔗 Combined Link Clicker & Forwarder\n\n"
            "1. Send DESTINATION chat (username/ID):\n\n"
            "Type /cancel to stop"
        )

    async def handle_destination_input(self, message: Message):
        """Handle destination chat input"""
        if not self.state['active']:
            return

        text = message.text.strip()
        if text.lower() == '/cancel':
            self.state['cancelled'] = True
            await message.reply_text("❌ Process cancelled")
            self.state['active'] = False
            return

        try:
            dest_chat = await self.bot.get_chat(text)
            self.state['destination_chat'] = dest_chat
            
            await message.reply_text(
                f"✅ Destination set: {dest_chat.title}\n\n"
                "Now send bot links (t.me/username?start=XXX):\n"
                "• Can be in messages or photo captions\n"
                "• Send /process when ready\n"
                "• /cancel to stop"
            )
        except Exception as e:
            await message.reply_text(f"❌ Error: {str(e)}")
            self.state['active'] = False

    async def handle_link_collection(self, message: Message):
        """Handle link collection from messages"""
        if not self.state['active'] or not self.state['destination_chat']:
            return

        if message.text:
            text = message.text.strip().lower()
            if text == '/process':
                if self.state['collected_links'] == 0:
                    await message.reply_text("❌ No links to process")
                    return
                
                # Set initial total links count
                self.state['total_links'] = self.state['collected_links']
                self.state['processed_links'] = 0
                
                await message.reply_text("⏳ Processing started...")
                self.state['processing'] = True
                await self.start_workers()
                asyncio.create_task(self.status_reporter())
                return
            
            if text == '/cancel':
                self.state['cancelled'] = True
                await message.reply_text("❌ Process cancelled")
                self.state['active'] = False
                self.clean_temp_dir()
                return

        # Extract links from all message sources
        found_links = []
        if message.text:
            found_links.extend(self.extract_links(message.text))
        if message.caption:
            found_links.extend(self.extract_links(message.caption))
        if message.entities:
            for entity in message.entities:
                if entity.type in ["text_link", "url"]:
                    url = entity.url if entity.type == "text_link" else message.text[entity.offset:entity.offset+entity.length]
                    found_links.extend(self.extract_links(url))
        if message.caption_entities:
            for entity in message.caption_entities:
                if entity.type in ["text_link", "url"]:
                    url = entity.url if entity.type == "text_link" else message.caption[entity.offset:entity.offset+entity.length]
                    found_links.extend(self.extract_links(url))

        if found_links:
            # Add links to queue and save to file
            for link in found_links:
                await self.link_queue.put(link)
                await self._save_link_data(link)
                self.state['collected_links'] += 1
            
            await message.reply_text(
                f"➕ Added {len(found_links)} link(s)\n"
                f"📊 Total collected: {self.state['collected_links']}\n\n"
                "Send /process to start forwarding"
            )

    def __del__(self):
        """Destructor to clean up temp files"""
        self.clean_temp_dir()
