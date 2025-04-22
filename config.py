import os

# --- Cloud Run Configuration (read from environment variables or use defaults) ---
# GCS Bucket for storing state files (tasks.json, api_keys.json)
STATE_BUCKET = os.getenv('STATE_BUCKET', None) # e.g., 'your-project-id-yt-state'
# GCS Object path for tasks file within STATE_BUCKET
TASKS_OBJECT_PATH = os.getenv('TASKS_OBJECT_PATH', 'jsons/tasks.json')
# GCS Object path for API keys file within STATE_BUCKET
KEYS_OBJECT_PATH = os.getenv('KEYS_OBJECT_PATH', 'jsons/api_keys.json')
# GCS Bucket for storing downloaded media files
DOWNLOAD_BUCKET = os.getenv('DOWNLOAD_BUCKET', None) # e.g., 'your-project-id-yt-downloads'
# Secret Manager path for YouTube cookies
# e.g., projects/YOUR_PROJECT_ID/secrets/youtube-cookie-data/versions/latest
COOKIE_SECRET_VERSION = os.getenv('COOKIE_SECRET_VERSION', None)

# --- Original Configuration (used as defaults or if not running on Cloud Run) ---
# Default local paths if GCS variables are not set
LOCAL_DOWNLOAD_DIR = '/app/downloads'
LOCAL_TASKS_FILE = 'jsons/tasks.json'
LOCAL_KEYS_FILE = 'jsons/api_keys.json'

# Configuration selection logic (can be enhanced in app logic if needed)
# For simplicity here, other parts of the app will need to check if STATE_BUCKET etc. are None
# and decide whether to use GCS paths or local paths.

# File system (These might become less relevant if GCS is used)
DOWNLOAD_DIR = '/app/downloads' # Kept for potential temporary local storage before GCS upload
TASKS_FILE = 'jsons/tasks.json' # Original path, logic should check STATE_BUCKET
KEYS_FILE = 'jsons/api_keys.json'   # Original path, logic should check STATE_BUCKET

# Task management
TASK_CLEANUP_TIME = int(os.getenv('TASK_CLEANUP_TIME', 10)) # minutes
REQUEST_LIMIT = int(os.getenv('REQUEST_LIMIT', 60)) # per TASK_CLEANUP_TIME
# Read MAX_WORKERS from env var, default to 4
MAX_WORKERS = int(os.getenv('MAX_WORKERS', 4))

# API key settings
DEFAULT_MEMORY_QUOTA = 5 * 1024 * 1024 * 1024  # 5GB default quota (in bytes) - Stays hardcoded for now
DEFAULT_MEMORY_QUOTA_RATE = 10  # minutes to rate limit - Stays hardcoded for now

# Memory control
SIZE_ESTIMATION_BUFFER = 1.10 # Stays hardcoded
AVAILABLE_MEMORY = 20 * 1024 * 1024 * 1024  # 20GB - This becomes less relevant on Cloud Run

# --- Derived Configuration --- (Example - Adapt as needed in app logic)
# Determine if running in a GCS-configured environment
USE_GCS_STATE = STATE_BUCKET is not None
USE_GCS_DOWNLOADS = DOWNLOAD_BUCKET is not None
USE_SECRET_MANAGER_COOKIES = COOKIE_SECRET_VERSION is not None
