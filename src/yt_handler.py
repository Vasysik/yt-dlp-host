from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from config import DOWNLOAD_DIR, TASK_CLEANUP_TIME, MAX_WORKERS
from src.json_utils import load_tasks, save_tasks, load_keys
from src.auth import check_memory_limit
import yt_dlp, os, threading, json, time, shutil

executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def get_format_size(info, format_id):
    for f in info.get('formats', []):
        if f.get('format_id') == format_id:
            return f.get('filesize') or f.get('filesize_approx', 0)
    return 0

def get_best_format_size(info, formats, formats_list, is_video=True):
    if not formats_list:
        return 0
    formats_with_size = [f for f in formats_list if (f.get('filesize') or f.get('filesize_approx', 0)) > 0]
    
    if formats_with_size:
        if is_video:
            return max(formats_with_size, 
                        key=lambda f: (f.get('height', 0), f.get('tbr', 0)))
        else:
            return max(formats_with_size, 
                        key=lambda f: (f.get('abr', 0) or f.get('tbr', 0)))
    
    best_format = max(formats_list, 
                    key=lambda f: (f.get('height', 0), f.get('tbr', 0)) if is_video 
                    else (f.get('abr', 0) or f.get('tbr', 0)))
    
    if best_format.get('tbr'):
        estimated_size = int(best_format['tbr'] * info.get('duration', 0) * 128 * 1024 / 8)
        if estimated_size > 0:
            return best_format
    
    similar_formats = [f for f in formats if f.get('height', 0) == best_format.get('height', 0)] if is_video \
                    else [f for f in formats if abs(f.get('abr', 0) - best_format.get('abr', 0)) < 50]
    
    sizes = [f.get('filesize') or f.get('filesize_approx', 0) for f in similar_formats]
    if sizes and any(sizes):
        best_format['filesize_approx'] = max(s for s in sizes if s > 0)
        return best_format
    
    return best_format

def check_and_get_size(url, video_format=None, audio_format=None):
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info['formats']
            total_size = 0
            
            if video_format:
                if video_format == 'bestvideo':
                    video_formats = [f for f in formats if f.get('vcodec') != 'none' and f.get('acodec') == 'none']
                    best_video = get_best_format_size(info, formats, video_formats, is_video=True)
                    total_size += best_video.get('filesize') or best_video.get('filesize_approx', 0)
                else:
                    format_info = next((f for f in formats if f.get('format_id') == video_format), None)
                    if format_info:
                        total_size += format_info.get('filesize') or format_info.get('filesize_approx', 0)

            if audio_format:
                if audio_format == 'bestaudio':
                    audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
                    best_audio = get_best_format_size(info, formats, audio_formats, is_video=False)
                    total_size += best_audio.get('filesize') or best_audio.get('filesize_approx', 0)
                else:
                    format_info = next((f for f in formats if f.get('format_id') == audio_format), None)
                    if format_info:
                        total_size += format_info.get('filesize') or format_info.get('filesize_approx', 0)
            total_size = int(total_size * 1.10)            
            return total_size if total_size > 0 else -1 
    except Exception as e:
        print(f"Error in check_and_get_size: {str(e)}")
        return -1

def get_info(task_id, url):
    try:
        tasks = load_tasks()
        tasks[task_id].update(status='processing')
        save_tasks(tasks)

        download_path = os.path.join(DOWNLOAD_DIR, task_id)
        if not os.path.exists(download_path):
            os.makedirs(download_path)

        ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True, 'skip_download': True}

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            info_file = os.path.join(DOWNLOAD_DIR, task_id, f'info.json')
            os.makedirs(os.path.dirname(info_file), exist_ok=True)
            with open(info_file, 'w') as f:
                json.dump(info, f)

            tasks = load_tasks()
            tasks[task_id].update(status='completed')
            tasks[task_id]['completed_time'] = datetime.now().isoformat()
            tasks[task_id]['file'] = f'/files/{task_id}/info.json'
            save_tasks(tasks)
        except Exception as e:
            handle_task_error(task_id, e)
    except Exception as e:
        handle_task_error(task_id, e)

def get(task_id, url, type, video_format="bestvideo", audio_format="bestaudio"):
    try:
        tasks = load_tasks()
        tasks[task_id].update(status='processing')
        save_tasks(tasks)

        total_size = check_and_get_size(url, video_format if type.lower() == 'video' else None, audio_format)
        if total_size <= 0: handle_task_error(task_id, f"Error getting size: {total_size}")

        key_name = tasks[task_id].get('key_name')
        keys = load_keys()
        if key_name not in keys:
            handle_task_error(task_id, "Invalid API key")
            return
        api_key = keys[key_name]['key']

        if not check_memory_limit(api_key, total_size, task_id):
            raise Exception("Memory limit exceeded. Maximum 5GB per 10 minutes.")
        
        download_path = os.path.join(DOWNLOAD_DIR, task_id)
        if not os.path.exists(download_path):
            os.makedirs(download_path)

        if type.lower() == 'audio':
            format_option = f'{audio_format}/best'
            output_template = f'audio.%(ext)s'
        else:
            format_option = f'{video_format}+{audio_format}/best'
            output_template = f'video.%(ext)s'

        ydl_opts = {
            'format': format_option,
            'outtmpl': os.path.join(download_path, output_template),
            'merge_output_format': 'mp4' if type.lower() == 'video' else None
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            tasks = load_tasks()
            tasks[task_id].update(status='completed')
            tasks[task_id]['completed_time'] = datetime.now().isoformat()
            tasks[task_id]['file'] = f'/files/{task_id}/' + os.listdir(download_path)[0]
            save_tasks(tasks)
        except Exception as e:
            handle_task_error(task_id, e)
    except Exception as e:
        handle_task_error(task_id, e)

def get_live(task_id, url, type, start, duration, video_format="bestvideo", audio_format="bestaudio"):
    try:
        tasks = load_tasks()
        tasks[task_id].update(status='processing')
        save_tasks(tasks)
        
        download_path = os.path.join(DOWNLOAD_DIR, task_id)
        if not os.path.exists(download_path):
            os.makedirs(download_path)

        current_time = int(time.time())
        start_time = current_time - start
        end_time = start_time + duration

        if type.lower() == 'audio':
            format_option = f'{audio_format}'
            output_template = f'live_audio.%(ext)s'
        else:
            format_option = f'{video_format}+{audio_format}'
            output_template = f'live_video.%(ext)s'

        ydl_opts = {
            'format': format_option,
            'outtmpl': os.path.join(download_path, output_template),
            'download_ranges': lambda info, *args: [{'start_time': start_time, 'end_time': end_time,}],
            'merge_output_format': 'mp4' if type.lower() == 'video' else None
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            tasks = load_tasks()
            tasks[task_id].update(status='completed')
            tasks[task_id]['completed_time'] = datetime.now().isoformat()
            tasks[task_id]['file'] = f'/files/{task_id}/' + os.listdir(download_path)[0]
            save_tasks(tasks)
        except Exception as e:
            handle_task_error(task_id, e)
    except Exception as e:
        handle_task_error(task_id, e)

def handle_task_error(task_id, error):
    tasks = load_tasks()
    tasks[task_id].update(status='error', error=str(error), completed_time=datetime.now().isoformat())
    save_tasks(tasks)
    print(f"Error in task {task_id}: {str(error)}")

def cleanup_task(task_id):
    tasks = load_tasks()
    download_path = os.path.join(DOWNLOAD_DIR, task_id)
    if os.path.exists(download_path):
        shutil.rmtree(download_path, ignore_errors=True)
    if task_id in tasks:
        del tasks[task_id]
        save_tasks(tasks)

def cleanup_orphaned_folders():
    tasks = load_tasks()
    task_ids = set(tasks.keys())
    
    for folder in os.listdir(DOWNLOAD_DIR):
        folder_path = os.path.join(DOWNLOAD_DIR, folder)
        if os.path.isdir(folder_path) and folder not in task_ids:
            shutil.rmtree(folder_path, ignore_errors=True)
            print(f"Removed orphaned folder: {folder_path}")

def cleanup_processing_tasks():
    tasks = load_tasks()
    for task_id, task in list(tasks.items()):
        if task['status'] == 'processing':
            task['status'] = 'error'
            task['error'] = 'Task was interrupted during processing'
            task['completed_time'] = datetime.now().isoformat()
    save_tasks(tasks)

def process_tasks():
    while True:
        tasks = load_tasks()
        current_time = datetime.now()
        for task_id, task in list(tasks.items()):
            if task['status'] == 'waiting':
                if task['task_type'] == 'get_video':
                    executor.submit(get, task_id, task['url'], 'video', task['video_format'], task['audio_format'])
                elif task['task_type'] == 'get_audio':
                    executor.submit(get, task_id, task['url'], 'audio', 'bestvideo', task['audio_format'])
                elif task['task_type'] == 'get_info':
                    executor.submit(get_info, task_id, task['url'])
                elif task['task_type'] == 'get_live_video':
                    executor.submit(get_live, task_id, task['url'], 'video', task['start'], task['duration'], task['video_format'], task['audio_format'])
                elif task['task_type'] == 'get_live_audio':
                    executor.submit(get_live, task_id, task['url'], 'audio', task['start'], task['duration'], 'bestvideo', task['audio_format'])
            elif task['status'] in ['completed', 'error']:
                completed_time = datetime.fromisoformat(task['completed_time'])
                if current_time - completed_time > timedelta(minutes=TASK_CLEANUP_TIME):
                    cleanup_task(task_id)
        if current_time.minute % 5 == 0 and current_time.second == 0:
            cleanup_orphaned_folders()
        time.sleep(1)

cleanup_processing_tasks()
cleanup_orphaned_folders()
thread = threading.Thread(target=process_tasks, daemon=True)
thread.start()
