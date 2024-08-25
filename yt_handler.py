from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from config import DOWNLOAD_DIR, TASKS_FILE, TASK_CLEANUP_TIME, MAX_WORKERS
import yt_dlp
import os
import threading
import json
import time

executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def load_tasks():
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_tasks(tasks):
    with open(TASKS_FILE, 'w') as f:
        json.dump(tasks, f, indent=4)

def get_info(task_id, url):
    try:
        tasks = load_tasks()
        tasks[task_id].update(status='processing')
        save_tasks(tasks)

        download_path = os.path.join(DOWNLOAD_DIR, task_id)
        if not os.path.exists(download_path):
            os.makedirs(download_path)

        ydl_opts = {'quiet': True, 'no_warnings': True}

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

def download_video(task_id, url, format, quality):
    try:
        tasks = load_tasks()
        tasks[task_id].update(status='processing')
        save_tasks(tasks)
        
        download_path = os.path.join(DOWNLOAD_DIR, task_id)
        if not os.path.exists(download_path):
            os.makedirs(download_path)

        if format.lower() == 'audio':
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(download_path, f'audio.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            }
        else:
            ydl_opts = {
                'format': f'bestvideo[height<={quality[:-1]}]+bestaudio/best',
                'outtmpl': os.path.join(download_path, f'video.%(ext)s'),
                'merge_output_format': 'mp4'
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
        for file in os.listdir(download_path):
            os.remove(os.path.join(download_path, file))
        os.rmdir(download_path)
    del tasks[task_id]
    save_tasks(tasks)

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
                if task['task_type'] == 'download':
                    executor.submit(download_video, task_id, task['url'], task['format'], task['quality'])
                elif task['task_type'] == 'get_info':
                    executor.submit(get_info, task_id, task['url'])
            elif task['status'] in ['completed', 'error']:
                completed_time = datetime.fromisoformat(task['completed_time'])
                if current_time - completed_time > timedelta(minutes=TASK_CLEANUP_TIME):
                    cleanup_task(task_id)
        time.sleep(1)

cleanup_processing_tasks()
thread = threading.Thread(target=process_tasks, daemon=True)
thread.start()