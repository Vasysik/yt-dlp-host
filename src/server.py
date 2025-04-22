from flask import Flask, request, jsonify, send_from_directory, redirect
from flask_cors import CORS
from src.json_utils import load_tasks, save_tasks, load_keys
from config import DOWNLOAD_DIR, USE_GCS_DOWNLOADS, DOWNLOAD_BUCKET
from src.yt_handler import storage_client
import src.yt_handler as yt_handler
import os, logging
from datetime import timedelta
from src.auth import check_api_key, get_key_name

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

if not os.path.exists(DOWNLOAD_DIR):
    try:
        os.makedirs(DOWNLOAD_DIR)
        logging.info(f"Created download directory: {DOWNLOAD_DIR}")
    except OSError as e:
        logging.error(f"Failed to create download directory {DOWNLOAD_DIR}: {e}")

def generate_random_id(length=16):
    import random, string
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

@app.route('/get_video', methods=['POST'])
@check_api_key('get_video')
def get_video():
    key_name = get_key_name(request.headers.get('X-API-Key'))
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'status': 'error', 'message': 'URL is required'}), 400
    url = data['url']
    video_format = data.get('video_format', 'bestvideo')
    audio_format = data.get('audio_format', 'bestaudio')
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    force_keyframes = data.get('force_keyframes', False)

    task_id = generate_random_id()
    tasks = load_tasks()
    tasks[task_id] = {
        'key_name': key_name,
        'status': 'waiting',
        'task_type': 'get_video',
        'url': url,
        'video_format': video_format,
        'audio_format': audio_format,
        'start_time': start_time,
        'end_time': end_time,
        'force_keyframes': force_keyframes
    }
    save_tasks(tasks)
    return jsonify({'status': 'waiting', 'task_id': task_id})

@app.route('/get_audio', methods=['POST'])
@check_api_key('get_audio')
def get_audio():
    key_name = get_key_name(request.headers.get('X-API-Key'))
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'status': 'error', 'message': 'URL is required'}), 400
    url = data['url']
    audio_format = data.get('audio_format', 'bestaudio')
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    force_keyframes = data.get('force_keyframes', False)

    task_id = generate_random_id()
    tasks = load_tasks()
    tasks[task_id] = {
        'key_name': key_name,
        'status': 'waiting',
        'task_type': 'get_audio',
        'url': url,
        'audio_format': audio_format,
        'start_time': start_time,
        'end_time': end_time,
        'force_keyframes': force_keyframes
    }
    save_tasks(tasks)
    return jsonify({'status': 'waiting', 'task_id': task_id})

@app.route('/get_info', methods=['POST'])
@check_api_key('get_info')
def get_info():
    key_name = get_key_name(request.headers.get('X-API-Key'))
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'status': 'error', 'message': 'URL is required'}), 400
    url = data['url']

    task_id = generate_random_id()
    tasks = load_tasks()
    tasks[task_id] = {
        'key_name': key_name,
        'status': 'waiting',
        'task_type': 'get_info',
        'url': url
    }
    save_tasks(tasks)
    return jsonify({'status': 'waiting', 'task_id': task_id})

@app.route('/get_live_video', methods=['POST'])
@check_api_key('get_live_video')
def get_live_video():
    key_name = get_key_name(request.headers.get('X-API-Key'))
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'status': 'error', 'message': 'URL is required'}), 400
    url = data['url']
    start = data.get('start', 0)
    duration = data.get('duration')
    if duration is None:
         return jsonify({'status': 'error', 'message': 'Duration is required for live video'}), 400
    video_format = data.get('video_format', 'bestvideo')
    audio_format = data.get('audio_format', 'bestaudio')

    task_id = generate_random_id()
    tasks = load_tasks()
    tasks[task_id] = {
        'key_name': key_name,
        'status': 'waiting',
        'task_type': 'get_live_video',
        'url': url,
        'start': start,
        'duration': duration,
        'video_format': video_format,
        'audio_format': audio_format
    }
    save_tasks(tasks)
    return jsonify({'status': 'waiting', 'task_id': task_id})

@app.route('/get_live_audio', methods=['POST'])
@check_api_key('get_live_audio')
def get_live_audio():
    key_name = get_key_name(request.headers.get('X-API-Key'))
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'status': 'error', 'message': 'URL is required'}), 400
    url = data['url']
    start = data.get('start', 0)
    duration = data.get('duration')
    if duration is None:
         return jsonify({'status': 'error', 'message': 'Duration is required for live audio'}), 400
    audio_format = data.get('audio_format', 'bestaudio')

    task_id = generate_random_id()
    tasks = load_tasks()
    tasks[task_id] = {
        'key_name': key_name,
        'status': 'waiting',
        'task_type': 'get_live_audio',
        'url': url,
        'start': start,
        'duration': duration,
        'video_format': 'bestvideo', 
        'audio_format': audio_format
    }
    save_tasks(tasks)
    return jsonify({'status': 'waiting', 'task_id': task_id})

@app.route('/status/<task_id>', methods=['GET'])
@check_api_key('get_status')
def status(task_id):
    tasks = load_tasks()
    if task_id not in tasks:
        return jsonify({'status': 'error', 'message': 'Task ID not found'}), 404
    return jsonify(tasks[task_id])

@app.route('/files/<path:filename>', methods=['GET'])
@check_api_key('get_file')
def get_file(filename):
    key_name = get_key_name(request.headers.get('X-API-Key'))
    if USE_GCS_DOWNLOADS:
        if not storage_client or not DOWNLOAD_BUCKET:
            logging.error("GCS check failed: client or bucket not configured.")
            return jsonify({"error": "Server configuration error."}), 500
        try:
            logging.info(f"Attempting GCS signed URL for gs://{DOWNLOAD_BUCKET}/{filename}")
            bucket = storage_client.bucket(DOWNLOAD_BUCKET)
            blob = bucket.blob(filename)

            if not blob.exists():
                 logging.warning(f"File not found in GCS: gs://{DOWNLOAD_BUCKET}/{filename}")
                 return jsonify({"error": "File not found"}), 404

            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(minutes=15),
                method="GET"
            )
            logging.info(f"Redirecting to signed URL for {filename}")
            return redirect(signed_url)
        except Exception as e:
            logging.error(f"Error generating signed URL for gs://{DOWNLOAD_BUCKET}/{filename}: {e}")
            return jsonify({"error": "Failed to generate file URL."}), 500
    else:
        try:
            directory = os.path.abspath(DOWNLOAD_DIR)
            logging.info(f"Serving local file: {filename} from directory: {directory}")
            return send_from_directory(directory, filename, as_attachment=False)
        except FileNotFoundError:
             logging.error(f"Local file not found: {os.path.join(directory, filename)}")
             return jsonify({"error": "File not found"}), 404
        except Exception as e:
            logging.error(f"Error serving local file {filename}: {e}")
            return jsonify({"error": "Failed to serve file."}), 500

@app.route('/create_key', methods=['POST'])
@check_api_key('create_key')
def create_key():
    data = request.get_json()
    name = data.get('name')
    permissions = data.get('permissions', [])
    memory_quota = data.get('memory_quota') 

    if not name:
        return jsonify({'status': 'error', 'message': 'Key name is required'}), 400

    new_key = auth.create_key(name, permissions, memory_quota)
    if not new_key:
        return jsonify({'status': 'error', 'message': 'Key name already exists'}), 409

    return jsonify({'name': name, 'key': new_key, 'permissions': permissions, 'memory_quota': memory_quota}), 201

@app.route('/delete_key/<name>', methods=['DELETE'])
@check_api_key('delete_key')
def delete_key(name):
    if auth.delete_key(name):
        return jsonify({'status': 'success', 'message': f'Key {name} deleted'}), 200
    else:
        return jsonify({'status': 'error', 'message': f'Key {name} not found'}), 404

@app.route('/get_key/<name>', methods=['GET'])
@check_api_key('get_key')
def get_key(name):
    key_info = auth.get_key(name)
    if key_info:
        return jsonify({'name': name, 'permissions': key_info.get('permissions', []), 'memory_quota': key_info.get('memory_quota')})
    else:
        return jsonify({'status': 'error', 'message': 'Key not found'}), 404

@app.route('/get_keys', methods=['GET'])
@check_api_key('get_keys')
def get_keys():
    keys = auth.get_keys_info() 
    return jsonify(keys)

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0')
