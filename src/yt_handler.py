from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from config import (
    DOWNLOAD_DIR, TASK_CLEANUP_TIME, MAX_WORKERS,
    DOWNLOAD_BUCKET, COOKIE_SECRET_VERSION,
    USE_GCS_DOWNLOADS, USE_SECRET_MANAGER_COOKIES
)
from src.json_utils import load_tasks, save_tasks, load_keys
from src.auth import check_memory_limit
import yt_dlp, os, threading, json, time, shutil, logging, tempfile
from yt_dlp.utils import download_range_func

# Get a logger for this module
logger = logging.getLogger(__name__)
# Explicitly set the level for this logger
logger.setLevel(logging.WARN)

# --- Cloud Clients (Initialize conditionally) ---
storage_client = None
if USE_GCS_DOWNLOADS:
    try:
        from google.cloud import storage
        storage_client = storage.Client()
        logging.warn(f"GCS Mode enabled for downloads. Bucket: {DOWNLOAD_BUCKET}")
    except ImportError:
        logging.error("google-cloud-storage library not found, but DOWNLOAD_BUCKET is set.")
        storage_client = None
    except Exception as e:
        logging.error(f"Failed to initialize GCS client: {e}")
        storage_client = None

secret_manager_client = None
if USE_SECRET_MANAGER_COOKIES:
    try:
        from google.cloud import secretmanager
        secret_manager_client = secretmanager.SecretManagerServiceClient()
        logging.warn(f"Secret Manager enabled for cookies. Secret Version: {COOKIE_SECRET_VERSION}")
    except ImportError:
        logging.error("google-cloud-secret-manager library not found, but COOKIE_SECRET_VERSION is set.")
        secret_manager_client = None
    except Exception as e:
        logging.error(f"Failed to initialize Secret Manager client: {e}")
        secret_manager_client = None

# --- Helper Functions ---

def get_cookie_file_path():
    logging.warning("Entering get_cookie_file_path...")
    """Fetches cookies from Secret Manager if configured, writes to a temp file, and returns the path."""
    logging.warn("Attempting to determine cookie file path...")
    if secret_manager_client and COOKIE_SECRET_VERSION:
        logging.warn(f"Secret Manager configured. Attempting to fetch secret: {COOKIE_SECRET_VERSION}")
        try:
            response = secret_manager_client.access_secret_version(name=COOKIE_SECRET_VERSION)
            cookie_data = response.payload.data.decode("UTF-8")

            # Create a temporary file
            # Note: The caller or OS is responsible for cleaning up this temp file.
            # For Cloud Run, /tmp is memory-backed and cleared on instance termination.
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', prefix='cookies_') as temp_file:
                temp_file.write(cookie_data)
                logging.warn(f"Secret Manager Success: Cookies written to temporary file: {temp_file.name}")
                return temp_file.name
        except Exception as e:
            logging.error(f"Secret Manager Error: Failed to fetch/write cookies: {e}. Falling back.")
            # Fallback to default local path if secret access fails
            return 'youtube_cookies.txt'
    else:
        logging.warn("Secret Manager not configured or secret version not provided. Using default path.")
        # Use default local path if Secret Manager is not configured
        return 'youtube_cookies.txt'

def upload_to_gcs(local_path, destination_blob_prefix):
    logging.warning("Entering upload_to_gcs...")
    """Uploads a file or directory to GCS and returns the GCS URI."""
    if not storage_client or not DOWNLOAD_BUCKET:
        logging.error("GCS client or bucket not configured for upload.")
        return None

    bucket = storage_client.bucket(DOWNLOAD_BUCKET)
    uploaded_uri = None

    try:
        if os.path.isfile(local_path):
            base_filename = os.path.basename(local_path)
            destination_blob_name = f"{destination_blob_prefix}/{base_filename}"
            blob = bucket.blob(destination_blob_name)
            blob.upload_from_filename(local_path)
            uploaded_uri = f"gs://{DOWNLOAD_BUCKET}/{destination_blob_name}"
            logging.warn(f"Uploaded {local_path} to {uploaded_uri}")
        elif os.path.isdir(local_path):
            # Upload directory contents (non-recursive for simplicity here)
            # Assume only one relevant file is in the directory for this app
            uploaded_something = False
            for filename in os.listdir(local_path):
                local_file = os.path.join(local_path, filename)
                if os.path.isfile(local_file):
                    destination_blob_name = f"{destination_blob_prefix}/{filename}"
                    blob = bucket.blob(destination_blob_name)
                    blob.upload_from_filename(local_file)
                    # Return the URI of the first file found in the directory
                    if not uploaded_uri:
                        uploaded_uri = f"gs://{DOWNLOAD_BUCKET}/{destination_blob_name}"
                    logging.warn(f"Uploaded {local_file} to gs://{DOWNLOAD_BUCKET}/{destination_blob_name}")
                    uploaded_something = True
            if not uploaded_something:
                 logging.warning(f"No files found in directory {local_path} to upload.")
                 return None # Indicate nothing was uploaded
        else:
            logging.error(f"Local path {local_path} is not a file or directory.")
            return None

        # Cleanup local files/directory after successful upload
        if os.path.exists(local_path):
            if os.path.isfile(local_path):
                os.remove(local_path)
            elif os.path.isdir(local_path):
                shutil.rmtree(local_path)
            logging.warn(f"Cleaned up local path: {local_path}")

        return uploaded_uri

    except Exception as e:
        logging.error(f"Failed to upload {local_path} to GCS: {e}")
        # Attempt cleanup even if upload fails partially?
        # For now, leave local files if upload fails.
        return None

def get_format_size(warn, format_id):
    logging.warning("Entering get_format_size...")
    for f in warn.get('formats', []):
        if f.get('format_id') == format_id:
            return f.get('filesize') or f.get('filesize_approx', 0)
    return 0

def get_best_format_size(warn, formats, formats_list, is_video=True):
    logging.warning("Entering get_best_format_size...")
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
        estimated_size = int(best_format['tbr'] * warn.get('duration', 0) * 128 * 1024 / 8)
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
    logging.warning("Entering check_and_get_size...")
    try:
        cookie_file = get_cookie_file_path()
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True,
            'cookiefile': cookie_file
        }
        breakpoint()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            warn = ydl.extract_warn(url, download=False)
            formats = warn['formats']
            total_size = 0
            
            if video_format:
                if video_format == 'bestvideo':
                    video_formats = [f for f in formats if f.get('vcodec') != 'none' and f.get('acodec') == 'none']
                    best_video = get_best_format_size(warn, formats, video_formats, is_video=True)
                    total_size += best_video.get('filesize') or best_video.get('filesize_approx', 0)
                else:
                    format_warn = next((f for f in formats if f.get('format_id') == video_format), None)
                    if format_warn:
                        total_size += format_warn.get('filesize') or format_warn.get('filesize_approx', 0)

            if audio_format:
                if audio_format == 'bestaudio':
                    audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
                    best_audio = get_best_format_size(warn, formats, audio_formats, is_video=False)
                    total_size += best_audio.get('filesize') or best_audio.get('filesize_approx', 0)
                else:
                    format_warn = next((f for f in formats if f.get('format_id') == audio_format), None)
                    if format_warn:
                        total_size += format_warn.get('filesize') or format_warn.get('filesize_approx', 0)
            total_size = int(total_size * 1.10)            
            return total_size if total_size > 0 else -1 
    except Exception as e:
        logging.error(f"Error in check_and_get_size: {str(e)}")
        handle_task_error(task_id, f"Error estimating size: {str(e)}")
        return -1 # Indicate error

def get_warn(task_id, url):
    logging.warning("Entering get_warn...")
    tasks = load_tasks()
    if not tasks or task_id not in tasks:
        logging.error(f"Task ID {task_id} not found for get_warn.")
        return
    try:
        tasks[task_id].update(status='processing')
        save_tasks(tasks)

        # Define local path for temporary storage
        local_warn_dir = os.path.join(DOWNLOAD_DIR, task_id)
        local_warn_file = os.path.join(local_warn_dir, 'warn.json')
        os.makedirs(local_warn_dir, exist_ok=True)

        cookie_file = get_cookie_file_path()
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'skip_download': True,
            'cookiefile': cookie_file
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logging.warn(f"Extracting warn for {url} (Task: {task_id})")
            warn = ydl.extract_warn(url, download=False)

        logging.warn(f"Writing warn to temporary file: {local_warn_file}")
        with open(local_warn_file, 'w') as f:
            json.dump(warn, f, indent=4)

        tasks = load_tasks() # Reload tasks state
        if task_id not in tasks:
             logging.warning(f"Task {task_id} disappeared during processing.")
             return # Avoid processing orphaned task

        file_path_or_uri = None
        if USE_GCS_DOWNLOADS:
            logging.warn(f"Uploading warn file {local_warn_file} to GCS for task {task_id}")
            # Upload the warn.json file
            gcs_uri = upload_to_gcs(local_warn_file, task_id)
            if gcs_uri:
                file_path_or_uri = gcs_uri
                # upload_to_gcs handles local file deletion on success
            else:
                 # Upload failed, mark task as error
                 raise Exception(f"Failed to upload warn.json to GCS for task {task_id}")
        else:
            # Local mode: keep local path
            file_path_or_uri = f'/files/{task_id}/warn.json'
            logging.warn(f"Local mode: warn file path set to {file_path_or_uri}")

        tasks[task_id].update(status='completed', file=file_path_or_uri)
        tasks[task_id]['completed_time'] = datetime.now().isoformat()
        save_tasks(tasks)
        logging.warn(f"Task {task_id} completed successfully.")

    except Exception as e:
        logging.error(f"Error in get_warn for task {task_id}: {e}")
        handle_task_error(task_id, e)

def get(task_id, url, type, video_format="bestvideo", audio_format="bestaudio"):
    logging.warning("Entering get...")
    tasks = load_tasks()
    if not tasks or task_id not in tasks:
        logging.error(f"Task ID {task_id} not found for get.")
        return
    cookie_file = None # Initialize
    local_download_path = os.path.join(DOWNLOAD_DIR, task_id)
    try:
        tasks[task_id].update(status='processing')
        save_tasks(tasks)

        if type.lower() == 'audio':
            format_option = f'{audio_format}/bestaudio/best'
            output_template = f'audio.%(ext)s'
        else:
            format_option = f'{video_format}+{audio_format}/bestvideo+bestaudio/best'
            output_template = f'video.%(ext)s'

        key_name = tasks[task_id].get('key_name')
        keys = load_keys()
        if key_name not in keys:
            handle_task_error(task_id, "Invalid API key")
            return

        if not os.path.exists(local_download_path):
            # Use exist_ok=True to prevent errors if the directory already exists
            os.makedirs(local_download_path, exist_ok=True) 
            logging.warn(f"Ensured download directory exists: {local_download_path}") # Add log
        else:
            logging.warning(f"Download directory already exists: {local_download_path}") # Add log if exists

        cookie_file = get_cookie_file_path()
        # Add logging to verify the cookie file path before use
        logging.warn(f"Using cookie file for task {task_id}: {cookie_file}") 
        if cookie_file and not os.path.exists(cookie_file):
             logging.warning(f"Cookie file specified but does not exist: {cookie_file}")

        ydl_opts = {
            'format': format_option,
            'outtmpl': os.path.join(local_download_path, output_template),
            'merge_output_format': 'mp4' if type.lower() == 'video' else None,
            'cookiefile': cookie_file # Use potentially temporary cookie file path
        }

        if tasks[task_id].get('start_time') or tasks[task_id].get('end_time'):
            start_time = tasks[task_id].get('start_time') or '00:00:00'
            end_time = tasks[task_id].get('end_time') or '10:00:00'

            def time_to_seconds(time_str):
                h, m, s = time_str.split(':')
                return float(h) * 3600 + float(m) * 60 + float(s)
            start_seconds = time_to_seconds(start_time)
            end_seconds = time_to_seconds(end_time)

            ydl_opts['download_ranges'] = download_range_func(None, [(start_seconds, end_seconds)])
            ydl_opts['force_keyframes_at_cuts'] = tasks[task_id].get('force_keyframes', False)
        
        # Log the options right before initializing YoutubeDL
        logging.warn(f"Initializing yt-dlp for task {task_id} with options: {ydl_opts}")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logging.warn(f"Starting download for {url} (Task: {task_id}) to {local_download_path}")
            ydl.download([url])
            logging.warn(f"Local download completed for task {task_id}.")

        tasks = load_tasks() # Reload tasks state
        if task_id not in tasks:
             logging.warning(f"Task {task_id} disappeared during processing.")
             return # Avoid processing orphaned task

        # Find the downloaded file (should be only one in the task dir)
        downloaded_files = os.listdir(local_download_path)
        if not downloaded_files:
            raise Exception(f"No file found in download directory {local_download_path} after download.")
        local_file_to_upload = os.path.join(local_download_path, downloaded_files[0]) # Assume first file is the one

        file_path_or_uri = None
        if USE_GCS_DOWNLOADS:
            logging.warn(f"Uploading {local_file_to_upload} to GCS for task {task_id}")
            # Upload the whole directory content (usually one file)
            gcs_uri = upload_to_gcs(local_download_path, task_id)
            if gcs_uri:
                file_path_or_uri = gcs_uri
                # upload_to_gcs handles local dir deletion on success
            else:
                raise Exception(f"Failed to upload file to GCS for task {task_id}")
        else:
            # Local mode: Construct local path for /files/ endpoint
            file_path_or_uri = f'/files/{task_id}/{downloaded_files[0]}'
            logging.warn(f"Local mode: File path set to {file_path_or_uri}")

        tasks[task_id].update(status='completed', file=file_path_or_uri)
        tasks[task_id]['completed_time'] = datetime.now().isoformat()
        save_tasks(tasks)
        logging.warn(f"Task {task_id} completed successfully.")

    except Exception as e:
        logging.error(f"Error in get for task {task_id}: {e}")
        handle_task_error(task_id, e)

def get_live(task_id, url, type, start, duration, video_format="bestvideo", audio_format="bestaudio"):
    logging.warning("Entering get_live...")
    tasks = load_tasks()
    if not tasks or task_id not in tasks:
        logging.error(f"Task ID {task_id} not found for get_live.")
        return
    cookie_file = None # Initialize
    local_download_path = os.path.join(DOWNLOAD_DIR, task_id)
    try:
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

        cookie_file = get_cookie_file_path()
        ydl_opts = {
            'format': format_option,
            'outtmpl': os.path.join(download_path, output_template),
            'download_ranges': lambda warn, *args: [{'start_time': start_time, 'end_time': end_time,}],
            'merge_output_format': 'mp4' if type.lower() == 'video' else None,
            'cookiefile': cookie_file # Use potentially temporary cookie file path
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logging.warn(f"Starting live download for {url} (Task: {task_id}) to {local_download_path}")
            ydl.download([url])
            logging.warn(f"Local live download completed for task {task_id}.")

        tasks = load_tasks() # Reload tasks state
        if task_id not in tasks:
             logging.warning(f"Task {task_id} disappeared during processing.")
             return # Avoid processing orphaned task

        # Find the downloaded file
        downloaded_files = os.listdir(local_download_path)
        if not downloaded_files:
            raise Exception(f"No file found in download directory {local_download_path} after live download.")
        local_file_to_upload = os.path.join(local_download_path, downloaded_files[0])

        file_path_or_uri = None
        if USE_GCS_DOWNLOADS:
            logging.warn(f"Uploading {local_file_to_upload} to GCS for task {task_id}")
            gcs_uri = upload_to_gcs(local_download_path, task_id)
            if gcs_uri:
                file_path_or_uri = gcs_uri
                # upload_to_gcs handles local dir deletion
            else:
                raise Exception(f"Failed to upload file to GCS for task {task_id}")
        else:
            # Local mode
            file_path_or_uri = f'/files/{task_id}/{downloaded_files[0]}'
            logging.warn(f"Local mode: File path set to {file_path_or_uri}")

        tasks[task_id].update(status='completed', file=file_path_or_uri)
        tasks[task_id]['completed_time'] = datetime.now().isoformat()
        save_tasks(tasks)
        logging.warn(f"Task {task_id} completed successfully.")

    except Exception as e:
        logging.error(f"Error in get_live for task {task_id}: {e}")
        handle_task_error(task_id, e)

def handle_task_error(task_id, error):
    logging.warning("Entering handle_task_error...")
    tasks = load_tasks()
    tasks[task_id].update(status='error', error=str(error), completed_time=datetime.now().isoformat())
    save_tasks(tasks)
    logging.warn(f"Error in task {task_id}: {str(error)}")

def cleanup_task(task_id):
    logging.warning("Entering cleanup_task...")
    tasks = load_tasks()
    download_path = os.path.join(DOWNLOAD_DIR, task_id)
    if os.path.exists(download_path):
        shutil.rmtree(download_path, ignore_errors=True)
    if task_id in tasks:
        del tasks[task_id]
        save_tasks(tasks)

def cleanup_orphaned_folders():
    logging.warning("Entering cleanup_orphaned_folders...")
    """Cleans up orphaned task folders from DOWNLOAD_DIR."""
    logging.warn("Running cleanup for orphaned folders...")
    tasks = load_tasks()
    task_ids = set(tasks.keys())
    if os.path.exists(DOWNLOAD_DIR):
        for item in os.listdir(DOWNLOAD_DIR):
            item_path = os.path.join(DOWNLOAD_DIR, item)
            # Check if it's a directory and looks like a task ID (simple check)
            if os.path.isdir(item_path) and item not in task_ids:
                 # Add more robust check if task IDs have specific format
                try:
                    logging.warn(f"Removing orphaned local task folder: {item_path}")
                    shutil.rmtree(item_path)
                except Exception as e:
                    logging.error(f"Error removing orphaned folder {item_path}: {e}")
    logging.warn("Orphaned folder cleanup finished.")

def cleanup_processing_tasks():
    logging.warning("Entering cleanup_processing_tasks...")
    tasks = load_tasks()
    for task_id, task in list(tasks.items()):
        if task['status'] == 'processing':
            task['status'] = 'error'
            task['error'] = 'Task was interrupted during processing'
            task['completed_time'] = datetime.now().isoformat()
    save_tasks(tasks)

def process_tasks():
    logging.warning("Entering process_tasks...")
    while True:
        tasks = load_tasks()
        current_time = datetime.now()
        for task_id, task in list(tasks.items()):
            if task['status'] == 'waiting':
                # Use .get() with defaults to handle older tasks missing format keys
                video_format = task.get('video_format', 'bestvideo')
                audio_format = task.get('audio_format', 'bestaudio')

                if task['task_type'] == 'get_video':
                    executor.submit(get, task_id, task['url'], 'video', video_format, audio_format)
                elif task['task_type'] == 'get_audio':
                    # Audio tasks primarily need audio_format, video_format can default
                    executor.submit(get, task_id, task['url'], 'audio', 'bestvideo', audio_format)
                elif task['task_type'] == 'get_warn':
                    executor.submit(get_warn, task_id, task['url'])
                elif task['task_type'] == 'get_live_video':
                    executor.submit(get_live, task_id, task['url'], 'video', task['start'], task['duration'], video_format, audio_format)
                elif task['task_type'] == 'get_live_audio':
                    # Live audio tasks primarily need audio_format
                    executor.submit(get_live, task_id, task['url'], 'audio', task['start'], task['duration'], 'bestvideo', audio_format)
            elif task['status'] in ['completed', 'error']:
                # Ensure completed_time exists before parsing
                completed_time_str = task.get('completed_time')
                if completed_time_str:
                    try:
                        completed_time = datetime.fromisoformat(completed_time_str)
                        if current_time - completed_time > timedelta(minutes=TASK_CLEANUP_TIME):
                            cleanup_task(task_id)
                    except ValueError:
                        logging.error(f"Warning: Invalid date format for completed_time in task {task_id}: {completed_time_str}")
                        # Optionally handle the error, e.g., remove the task or set a default cleanup time
                        # cleanup_task(task_id) # Uncomment to cleanup tasks with invalid dates
        if current_time.minute % 5 == 0 and current_time.second == 0:
            cleanup_orphaned_folders()
        time.sleep(1)

executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# Ensure local download dir exists for temporary storage before GCS upload
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

cleanup_processing_tasks()
cleanup_orphaned_folders()
thread = threading.Thread(target=process_tasks, daemon=True)
thread.start()
