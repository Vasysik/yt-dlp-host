from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from config import DOWNLOAD_DIR, TASK_CLEANUP_TIME, MAX_WORKERS
from src.json_utils import load_tasks, save_tasks
import yt_dlp, os, threading, json, time, shutil

executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

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
