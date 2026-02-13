import os
import json
import time
import shutil
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any

import yt_dlp
from yt_dlp.utils import download_range_func
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, ID3NoHeaderError
import mutagen

from src.storage import Storage
from src.auth import memory_manager
from src.models import TaskStatus, TaskType
from config import storage, memory
from config import task as task_config

# Log mutagen version on startup
print(f"[STARTUP] Mutagen version: {mutagen.version_string}")
print(f"[STARTUP] ID3 tagging is available and ready")

class YTDownloader:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=task_config.MAX_WORKERS)
        self._ensure_download_dir()
        print(f"[STARTUP] YTDownloader initialized with ID3 tagging support")
    
    def _ensure_download_dir(self):
        os.makedirs(storage.DOWNLOAD_DIR, exist_ok=True)

    def _update_mp3_id3_tags(self, file_path: str, title: str):
        """Update MP3 ID3 tags based on title format 'artist - track'

        Args:
            file_path: Path to the MP3 file
            title: Video/audio title from YouTube
        """
        try:
            print(f"[ID3] Processing file: {file_path}")
            print(f"[ID3] Title: {title}")

            # Check if file exists
            if not os.path.exists(file_path):
                print(f"[ID3] ERROR: File does not exist: {file_path}")
                return

            # Check if file is MP3
            if not file_path.lower().endswith('.mp3'):
                print(f"[ID3] Skipping non-MP3 file: {file_path}")
                return

            # Try to load existing ID3 tags or create new ones
            try:
                audio = MP3(file_path, ID3=ID3)
                if audio.tags is None:
                    audio.add_tags()
            except ID3NoHeaderError:
                audio = MP3(file_path)
                audio.add_tags()

            # Parse title for "artist - track" format
            if ' - ' in title:
                parts = title.split(' - ', 1)  # Split only on first " - "
                artist = parts[0].strip()
                track = parts[1].strip()

                print(f"[ID3] Setting Artist: {artist}")
                print(f"[ID3] Setting Track: {track}")

                # Delete existing tags first to avoid duplicates
                audio.tags.delall('TPE1')
                audio.tags.delall('TIT2')

                # Update artist and title tags
                audio.tags.add(TPE1(encoding=3, text=artist))
                audio.tags.add(TIT2(encoding=3, text=track))
            else:
                print(f"[ID3] Setting Track only: {title}")

                # Delete existing tags first
                audio.tags.delall('TIT2')

                # No artist separator found, just update title
                audio.tags.add(TIT2(encoding=3, text=title))

            # Save the tags
            audio.save()
            print(f"[ID3] ✓ Successfully updated ID3 tags for: {file_path}")
        except Exception as e:
            import traceback
            print(f"[ID3] ERROR updating ID3 tags for {file_path}: {str(e)}")
            print(f"[ID3] Traceback: {traceback.format_exc()}")

    def _get_task_dir(self, task_id: str) -> str:
        return os.path.join(storage.DOWNLOAD_DIR, task_id)
    
    def _update_task(self, task_id: str, **kwargs):
        tasks = Storage.load_tasks()
        if task_id in tasks:
            tasks[task_id].update(kwargs)
            Storage.save_tasks(tasks)
    
    def _handle_error(self, task_id: str, error: Exception):
        self._update_task(
            task_id,
            status=TaskStatus.ERROR.value,
            error=str(error),
            completed_time=datetime.now().isoformat()
        )
        print(f"Error in task {task_id}: {error}")
    
    def estimate_size(self, url: str, video_format: Optional[str] = None, 
                      audio_format: Optional[str] = None) -> int:
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'skip_download': True,
                'extractor_args': { 'youtube': { 'player_client': ['default', '-tv_simply'], }, },
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                total_size = 0
                formats = info.get('formats', [])
                
                if video_format:
                    video_size = self._get_format_size(formats, video_format, is_video=True)
                    if not video_size:
                        video_size = self._get_format_size(formats, 'bestvideo', is_video=True)
                    total_size += video_size
                
                if audio_format and str(audio_format).lower() not in ['none', 'null']:
                    audio_size = self._get_format_size(formats, audio_format, is_video=False)
                    if not audio_size:
                        audio_size = self._get_format_size(formats, 'bestaudio', is_video=False)
                    total_size += audio_size
                
                return int(total_size * memory.SIZE_BUFFER) if total_size > 0 else -1
        except Exception as e:
            print(f"Error in estimate_size: {str(e)}")
            return -1
    
    def _get_format_size(self, formats: list, format_spec: str, is_video: bool) -> int:
        if format_spec == 'bestvideo':
            filtered = [f for f in formats if f.get('vcodec') and f.get('vcodec') != 'none']
        elif format_spec == 'bestaudio':
            filtered = [f for f in formats if f.get('acodec') and f.get('acodec') != 'none']
        else:
            filtered = [f for f in formats if f.get('format_id') == format_spec]
        
        if not filtered:
            if is_video:
                filtered = [f for f in formats if f.get('vcodec') != 'none']
            else:
                filtered = [f for f in formats if f.get('acodec') != 'none']
        
        if not filtered:
            return 0
        
        best = max(filtered, key=lambda f: (f.get('filesize') or f.get('filesize_approx') or 0, f.get('tbr') or 0, f.get('height') or 0 if is_video else f.get('abr') or 0))
        
        size = best.get('filesize') or best.get('filesize_approx', 0)
        
        if size == 0:
            duration = best.get('duration', 0)
            if is_video:
                bitrate = best.get('tbr') or best.get('vbr') or 0
            else:
                bitrate = best.get('abr') or best.get('tbr') or 0
            
            if duration > 0 and bitrate > 0:
                size = int(bitrate * duration * 128)
        
        return size

    def search(self, query: str) -> Dict[str, Any]:
        """Search YouTube for videos matching a query

        Args:
            query: Search query string (e.g., "artist - song name")

        Returns:
            Dictionary with search results including url, title, duration
        """
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'skip_download': True,
                'extractor_args': { 'youtube': { 'player_client': ['default', '-tv_simply'], }, },
            }

            search_query = f"ytsearch1:{query}"

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(search_query, download=False)

            if result and 'entries' in result and len(result['entries']) > 0:
                video = result['entries'][0]
                video_url = f"https://www.youtube.com/watch?v={video['id']}"

                return {
                    'success': True,
                    'url': video_url,
                    'title': video.get('title', 'Unknown'),
                    'duration': video.get('duration', 0),
                    'id': video.get('id')
                }
            else:
                return {'success': False, 'message': 'No videos found'}
        except Exception as e:
            print(f"Error in search: {str(e)}")
            return {'success': False, 'message': str(e)}

    def download_info(self, task_id: str):
        try:
            tasks = Storage.load_tasks()
            task = tasks[task_id]
            self._update_task(task_id, status=TaskStatus.PROCESSING.value)

            has_custom_filename = task.get('output_filename')
            if has_custom_filename:
                # Save directly to /app/downloads/ with custom filename
                download_path = storage.DOWNLOAD_DIR
                info_filename = f"{task.get('output_filename')}.json"
            else:
                # Save to task directory (original behavior)
                download_path = self._get_task_dir(task_id)
                info_filename = 'info.json'

            os.makedirs(download_path, exist_ok=True)

            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'skip_download': True
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(task['url'], download=False)

            info_file = os.path.join(download_path, info_filename)
            with open(info_file, 'w') as f:
                json.dump(info, f)

            if has_custom_filename:
                self._update_task(
                    task_id,
                    status=TaskStatus.COMPLETED.value,
                    completed_time=datetime.now().isoformat(),
                    file=f'/files/{info_filename}'
                )
            else:
                self._update_task(
                    task_id,
                    status=TaskStatus.COMPLETED.value,
                    completed_time=datetime.now().isoformat(),
                    file=f'/files/{task_id}/info.json'
                )
        except Exception as e:
            self._handle_error(task_id, e)
    
    def download_media(self, task_id: str):
        try:
            tasks = Storage.load_tasks()
            task = tasks[task_id]
            print(f"[DOWNLOAD] Starting download_media for task: {task_id}")
            print(f"[DOWNLOAD] Task type: {task.get('task_type')}")
            print(f"[DOWNLOAD] URL: {task.get('url')}")
            self._update_task(task_id, status=TaskStatus.PROCESSING.value)

            # Check memory quota
            is_video = task['task_type'] in ['get_video', 'get_live_video']
            print(f"[DOWNLOAD] is_video={is_video}")
            total_size = self.estimate_size(
                task['url'],
                task.get('video_format') if is_video else None,
                task.get('audio_format')
            )

            if total_size <= 0:
                raise Exception("Could not estimate file size")

            keys = Storage.load_keys()
            api_key = keys[task['key_name']]['key']
            memory_manager.check_and_update_quota(api_key, total_size, task_id)

            # Prepare download
            has_custom_filename = task.get('output_filename')
            if has_custom_filename:
                # Save directly to /app/downloads/ with custom filename
                download_path = storage.DOWNLOAD_DIR
            else:
                # Save to task directory (original behavior)
                download_path = self._get_task_dir(task_id)

            os.makedirs(download_path, exist_ok=True)

            # Configure yt-dlp
            ydl_opts = self._build_ydl_options(task, download_path)

            # Download and get video info
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(task['url'], download=True)
                video_title = info.get('title', '')

            print(f"[DEBUG] Download completed! Video title: {video_title}")
            print(f"[DEBUG] Now processing ID3 tags...")

            # Find downloaded file and update ID3 tags for audio files
            downloaded_file = None
            print(f"[DEBUG] Searching for downloaded file in: {download_path}")
            print(f"[DEBUG] has_custom_filename: {has_custom_filename}")
            print(f"[DEBUG] is_video: {is_video}")

            if has_custom_filename:
                custom_name = task.get('output_filename')
                print(f"[DEBUG] custom_name: {custom_name}")
                all_files = os.listdir(download_path)
                print(f"[DEBUG] Files in directory: {all_files}")
                matching_files = [f for f in all_files if f.startswith(custom_name)]
                print(f"[DEBUG] Matching files: {matching_files}")
                if matching_files:
                    downloaded_file = os.path.join(download_path, matching_files[0])
                    print(f"[DEBUG] Selected file: {downloaded_file}")
            else:
                files = os.listdir(download_path)
                print(f"[DEBUG] Files in directory: {files}")
                if files:
                    downloaded_file = os.path.join(download_path, files[0])
                    print(f"[DEBUG] Selected file: {downloaded_file}")

            # Update ID3 tags for audio downloads (MP3 format)
            print(f"[DEBUG] About to check ID3 conditions: downloaded_file={downloaded_file}, is_video={is_video}")
            if downloaded_file and not is_video:
                print(f"[DEBUG] Calling _update_mp3_id3_tags with title: {video_title}")
                self._update_mp3_id3_tags(downloaded_file, video_title)
            else:
                print(f"[DEBUG] Skipping ID3 update - downloaded_file={downloaded_file}, is_video={is_video}")

            # Update task
            if has_custom_filename:
                # For custom filename, find the actual downloaded file
                custom_name = task.get('output_filename')
                matching_files = [f for f in os.listdir(download_path) if f.startswith(custom_name)]
                if matching_files:
                    self._update_task(
                        task_id,
                        status=TaskStatus.COMPLETED.value,
                        completed_time=datetime.now().isoformat(),
                        file=f'/files/{matching_files[0]}'
                    )
            else:
                # Original behavior for task directory
                files = os.listdir(download_path)
                if files:
                    self._update_task(
                        task_id,
                        status=TaskStatus.COMPLETED.value,
                        completed_time=datetime.now().isoformat(),
                        file=f'/files/{task_id}/{files[0]}'
                    )
        except Exception as e:
            self._handle_error(task_id, e)
    
    def _build_ydl_options(self, task: dict, download_path: str) -> dict:
        is_video = task['task_type'] in ['get_video', 'get_live_video']
        is_live = 'live' in task['task_type']
        output_format = task.get('output_format')
        audio_format = task.get('audio_format')
        filename = task.get('output_filename')

        if is_video:
            video_format = task.get('video_format', 'bestvideo')
            if audio_format is None or str(audio_format).lower() in ['none', 'null']:
                format_option = f"{video_format}/bestvideo"
            else:
                format_option = f"{video_format}+{audio_format}/best"
            if filename:
                output_name = f"{filename}.%(ext)s"
            else:
                output_name = 'live_video.%(ext)s' if is_live else 'video.%(ext)s'
        else:
            format_option = f"{task.get('audio_format', 'bestaudio')}/bestaudio"
            if filename:
                output_name = f"{filename}.%(ext)s"
            else:
                output_name = 'live_audio.%(ext)s' if is_live else 'audio.%(ext)s'
        
        opts = {
            'format': format_option,
            'outtmpl': os.path.join(download_path, output_name),
            'extractor_args': { 'youtube': { 'player_client': ['default', '-tv_simply'], }, },
        }
        
        if output_format:
            if not is_video:
                opts['extract_audio'] = True 
                opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': output_format,
                }]
            else:
                opts['merge_output_format'] = output_format
        
        # Handle time ranges
        if is_live and task.get('duration'):
            current = int(time.time())
            start_time = current - task.get('start', 0)
            end_time = start_time + task['duration']
            opts['download_ranges'] = lambda *_: [{'start_time': start_time, 'end_time': end_time}]
        
        elif task.get('start_time') or task.get('end_time'):
            start = self._time_to_seconds(task.get('start_time', '00:00:00'))
            end = self._time_to_seconds(task.get('end_time', '10:00:00'))
            opts['download_ranges'] = download_range_func(None, [(start, end)])
            opts['force_keyframes_at_cuts'] = task.get('force_keyframes', False)
        
        return opts
    
    def _time_to_seconds(self, ts) -> float:
        if ts is None:
            return 0.0
        
        if isinstance(ts, (int, float)):
            return float(ts)

        ts_str = str(ts)
        
        if ':' not in ts_str:
            try:
                return float(ts_str)
            except ValueError:
                return 0.0
        
        # Time format string
        parts = ts_str.split(':')
        try:
            # Support formats: "SS", "MM:SS", "HH:MM:SS"
            if len(parts) == 1:
                return float(parts[0])
            elif len(parts) == 2:
                m, s = map(float, parts)
                return m * 60 + s
            elif len(parts) == 3:
                h, m, s = map(float, parts)
                return h * 3600 + m * 60 + s
            else:
                # Invalid format, return 0
                return 0.0
        except (ValueError, TypeError):
            return 0.0
    
    def cleanup_task(self, task_id: str):
        task_dir = self._get_task_dir(task_id)
        if os.path.exists(task_dir):
            shutil.rmtree(task_dir, ignore_errors=True)
        
        tasks = Storage.load_tasks()
        if task_id in tasks:
            del tasks[task_id]
            Storage.save_tasks(tasks)
    
    def process_tasks(self):
        while True:
            tasks = Storage.load_tasks()
            current_time = datetime.now()
            
            for task_id, task_data in list(tasks.items()):
                if task_data['status'] == TaskStatus.WAITING.value:
                    self._submit_task(task_id, task_data)
                
                elif task_data['status'] in [TaskStatus.COMPLETED.value, TaskStatus.ERROR.value]:
                    if 'completed_time' in task_data:
                        completed = datetime.fromisoformat(task_data['completed_time'])
                        if current_time - completed > timedelta(minutes=task_config.CLEANUP_TIME_MINUTES):
                            self.cleanup_task(task_id)
            
            # Cleanup orphaned folders every 5 minutes
            if current_time.minute % 5 == 0 and current_time.second == 0:
                self._cleanup_orphaned_folders()
            
            time.sleep(1)
    
    def _submit_task(self, task_id: str, task_data: dict):
        task_type = task_data['task_type']
        
        if task_type == TaskType.GET_INFO.value:
            self.executor.submit(self.download_info, task_id)
        else:
            self.executor.submit(self.download_media, task_id)
    
    def _cleanup_orphaned_folders(self):
        tasks = Storage.load_tasks()
        task_ids = set(tasks.keys())
        
        for folder in os.listdir(storage.DOWNLOAD_DIR):
            folder_path = os.path.join(storage.DOWNLOAD_DIR, folder)
            if os.path.isdir(folder_path) and folder not in task_ids:
                shutil.rmtree(folder_path, ignore_errors=True)
    
    def initialize(self):
        # Fix interrupted tasks
        tasks = Storage.load_tasks()
        for task_id, task_data in tasks.items():
            if task_data['status'] == TaskStatus.PROCESSING.value:
                task_data['status'] = TaskStatus.ERROR.value
                task_data['error'] = 'Task was interrupted'
                task_data['completed_time'] = datetime.now().isoformat()
        Storage.save_tasks(tasks)
        
        # Start processing thread
        thread = threading.Thread(target=self.process_tasks, daemon=True)
        thread.start()

# Initialize downloader
downloader = YTDownloader()
downloader.initialize()
