from config import (STATE_BUCKET, TASKS_OBJECT_PATH, KEYS_OBJECT_PATH,
                    LOCAL_TASKS_FILE, LOCAL_KEYS_FILE)
import os
import json
import logging

# Conditionally import and initialize GCS client only if needed
storage_client = None
if STATE_BUCKET:
    try:
        from google.cloud import storage
        storage_client = storage.Client()
        logging.info(f"GCS Mode enabled. State Bucket: {STATE_BUCKET}")
    except ImportError:
        logging.error("google-cloud-storage library not found, but STATE_BUCKET is set. Please install.")
        storage_client = None # Ensure it's None if import fails
    except Exception as e:
        logging.error(f"Failed to initialize GCS client: {e}")
        storage_client = None
else:
    logging.info("Local file mode enabled for state.")

def _read_from_gcs(bucket_name, object_path):
    """Helper to read JSON data from GCS.
    Returns dictionary or None if error/not found.
    """
    if not storage_client:
        logging.error("Attempted GCS read but client is not initialized.")
        return None
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(object_path)

        if not blob.exists():
            logging.warning(f"GCS object {object_path} not found in bucket {bucket_name}. Returning empty dict.")
            return {}

        data_bytes = blob.download_as_bytes()
        if not data_bytes:
             logging.warning(f"GCS object {object_path} in bucket {bucket_name} is empty. Returning empty dict.")
             return {}
        return json.loads(data_bytes)
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from GCS {bucket_name}/{object_path}: {e}")
        return None # Indicate failure to load
    except Exception as e:
        logging.error(f"Error reading from GCS {bucket_name}/{object_path}: {e}")
        return None

def _write_to_gcs(bucket_name, object_path, data):
    """Helper to write JSON data to GCS.
    Returns True on success, False otherwise.
    """
    if not storage_client:
        logging.error("Attempted GCS write but client is not initialized.")
        return False
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(object_path)
        json_data = json.dumps(data, indent=4)
        blob.upload_from_string(json_data, content_type='application/json')
        logging.debug(f"Successfully wrote to GCS {bucket_name}/{object_path}")
        return True
    except Exception as e:
        logging.error(f"Error writing to GCS {bucket_name}/{object_path}: {e}")
        return False

def load_tasks():
    if storage_client and STATE_BUCKET:
        tasks = _read_from_gcs(STATE_BUCKET, TASKS_OBJECT_PATH)
        return tasks if tasks is not None else {} # Return empty if read failed
    else:
        # Fallback to local file
        if os.path.exists(LOCAL_TASKS_FILE):
            try:
                with open(LOCAL_TASKS_FILE, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                logging.error(f"Error decoding JSON from local file {LOCAL_TASKS_FILE}: {e}")
                return {}
            except Exception as e:
                 logging.error(f"Error reading local file {LOCAL_TASKS_FILE}: {e}")
                 return {}
        return {}

def save_tasks(tasks):
    if storage_client and STATE_BUCKET:
        _write_to_gcs(STATE_BUCKET, TASKS_OBJECT_PATH, tasks)
    else:
        # Fallback to local file
        try:
            os.makedirs(os.path.dirname(LOCAL_TASKS_FILE), exist_ok=True)
            with open(LOCAL_TASKS_FILE, 'w') as f:
                json.dump(tasks, f, indent=4)
        except Exception as e:
            logging.error(f"Error writing local file {LOCAL_TASKS_FILE}: {e}")

def load_keys():
    if storage_client and STATE_BUCKET:
        keys = _read_from_gcs(STATE_BUCKET, KEYS_OBJECT_PATH)
        return keys if keys is not None else {} # Return empty if read failed
    else:
        # Fallback to local file
        if os.path.exists(LOCAL_KEYS_FILE):
            try:
                with open(LOCAL_KEYS_FILE, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                logging.error(f"Error decoding JSON from local file {LOCAL_KEYS_FILE}: {e}")
                return {}
            except Exception as e:
                 logging.error(f"Error reading local file {LOCAL_KEYS_FILE}: {e}")
                 return {}
        return {}

def save_keys(keys):
    if storage_client and STATE_BUCKET:
        _write_to_gcs(STATE_BUCKET, KEYS_OBJECT_PATH, keys)
    else:
        # Fallback to local file
        try:
            os.makedirs(os.path.dirname(LOCAL_KEYS_FILE), exist_ok=True)
            with open(LOCAL_KEYS_FILE, 'w') as f:
                json.dump(keys, f, indent=4)
        except Exception as e:
            logging.error(f"Error writing local file {LOCAL_KEYS_FILE}: {e}")
