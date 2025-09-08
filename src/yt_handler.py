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

from src.storage import Storage
from src.auth import memory_manager
from src.models import TaskStatus, TaskType
from config import storage, memory
from config import task as task_config

class YTDownloader:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=task_config.MAX_WORKERS)
        self._ensure_download_dir()
    
    def _ensure_download_dir(self):
        os.makedirs(storage.DOWNLOAD_DIR, exist_ok=True)
    
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
                'skip_download': True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                total_size = 0
                formats = info.get('formats', [])
                
                if video_format:
                    total_size += self._get_format_size(formats, video_format, is_video=True)
                
                if audio_format:
                    total_size += self._get_format_size(formats, audio_format, is_video=False)
                
                return int(total_size * memory.SIZE_BUFFER) if total_size > 0 else -1
        except Exception as e:
            print(f"Error in estimate_size: {str(e)}")
            return -1
    
    def _get_format_size(self, formats: list, format_spec: str, is_video: bool) -> int:
        if format_spec == 'bestvideo':
            filtered = [f for f in formats if f.get('vcodec') != 'none' and f.get('acodec') == 'none']
        elif format_spec == 'bestaudio':
            filtered = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
        else:
            filtered = [f for f in formats if f.get('format_id') == format_spec]
        
        if not filtered:
            return 0
        
        best = max(filtered, key=lambda f: f.get('filesize') or f.get('filesize_approx', 0))
        return best.get('filesize') or best.get('filesize_approx', 0)
    
    def download_info(self, task_id: str):
        try:
            tasks = Storage.load_tasks()
            task = tasks[task_id]
            self._update_task(task_id, status=TaskStatus.PROCESSING.value)
            
            download_path = self._get_task_dir(task_id)
            os.makedirs(download_path, exist_ok=True)
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'skip_download': True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(task['url'], download=False)
            
            info_file = os.path.join(download_path, 'info.json')
            with open(info_file, 'w') as f:
                json.dump(info, f)
            
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
            self._update_task(task_id, status=TaskStatus.PROCESSING.value)
            
            # Check memory quota
            is_video = task['task_type'] in ['get_video', 'get_live_video']
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
            download_path = self._get_task_dir(task_id)
            os.makedirs(download_path, exist_ok=True)
            
            # Configure yt-dlp
            ydl_opts = self._build_ydl_options(task, download_path)
            
            # Download
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([task['url']])
            
            # Update task
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
        
        if is_video:
            format_option = f"{task.get('video_format', 'bestvideo')}+{task.get('audio_format', 'bestaudio')}/best"
            output_name = 'live_video.%(ext)s' if is_live else 'video.%(ext)s'
        else:
            format_option = f"{task.get('audio_format', 'bestaudio')}/best"
            output_name = 'live_audio.%(ext)s' if is_live else 'audio.%(ext)s'
        
        opts = {
            'format': format_option,
            'outtmpl': os.path.join(download_path, output_name),
            'merge_output_format': 'mp4' if is_video else None
        }
        
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
    
    def _time_to_seconds(self, time_str: str) -> float:
        h, m, s = map(float, time_str.split(':'))
        return h * 3600 + m * 60 + s
    
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
