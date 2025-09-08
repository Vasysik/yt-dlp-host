import os
import json
import random
import string
from flask import Flask, request, jsonify, send_from_directory

from src.storage import Storage
from src.auth import auth_manager, memory_manager, require_permission, AuthManager
from src.models import Task, TaskStatus, TaskType
from config import storage

from src import yt_handler

app = Flask(__name__)
app.json.sort_keys = False

def generate_task_id(length: int = 16) -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def create_task(task_type: TaskType, data: dict) -> dict:
    if not data.get('url'):
        return {'status': 'error', 'message': 'URL is required'}, 400
    
    task_id = generate_task_id()
    api_key = request.headers.get('X-API-Key')
    
    task = Task(
        task_id=task_id,
        key_name=AuthManager.get_key_name(api_key),
        status=TaskStatus.WAITING,
        task_type=task_type,
        url=data['url'],
        video_format=data.get('video_format', 'bestvideo'),
        audio_format=data.get('audio_format', 'bestaudio'),
        start_time=data.get('start_time'),
        end_time=data.get('end_time'),
        force_keyframes=data.get('force_keyframes', False),
        start=data.get('start', 0),
        duration=data.get('duration')
    )
    
    tasks = Storage.load_tasks()
    tasks[task_id] = task.to_dict()
    Storage.save_tasks(tasks)
    
    return jsonify({'status': 'waiting', 'task_id': task_id})

@app.route('/get_video', methods=['POST'])
@require_permission('get_video')
def get_video():
    return create_task(TaskType.GET_VIDEO, request.json)

@app.route('/get_audio', methods=['POST'])
@require_permission('get_audio')
def get_audio():
    return create_task(TaskType.GET_AUDIO, request.json)

@app.route('/get_info', methods=['POST'])
@require_permission('get_info')
def get_info():
    return create_task(TaskType.GET_INFO, request.json)

@app.route('/get_live_video', methods=['POST'])
@require_permission('get_live_video')
def get_live_video():
    return create_task(TaskType.GET_LIVE_VIDEO, request.json)

@app.route('/get_live_audio', methods=['POST'])
@require_permission('get_live_audio')
def get_live_audio():
    return create_task(TaskType.GET_LIVE_AUDIO, request.json)

@app.route('/status/<task_id>', methods=['GET'])
def status(task_id: str):
    tasks = Storage.load_tasks()
    if task_id not in tasks:
        return jsonify({'status': 'error', 'message': 'Task not found'}), 404
    return jsonify(tasks[task_id])

@app.route('/files/<path:filename>', methods=['GET'])
def get_file(filename: str):
    file_path = os.path.abspath(os.path.join(storage.DOWNLOAD_DIR, filename))
    
    if not os.path.isfile(file_path):
        return jsonify({"error": "File not found"}), 404
    
    if not file_path.startswith(os.path.abspath(storage.DOWNLOAD_DIR)):
        return jsonify({"error": "Access denied"}), 403
    
    if filename.endswith('info.json'):
        return handle_info_file(file_path)
    
    return handle_regular_file(filename)

def handle_info_file(file_path: str):
    with open(file_path, 'r') as f:
        data = json.load(f)
    
    params = request.args
    if not params:
        return jsonify(data)
    
    if 'qualities' in params:
        return jsonify({'qualities': extract_qualities(data)})
    
    filtered = {k: data[k] for k in params if k in data}
    return jsonify(filtered) if filtered else jsonify({"error": "No matching parameters"}), 404

def extract_qualities(data: dict) -> dict:
    qualities = {"audio": {}, "video": {}}
    
    for fmt in data.get('formats', []):
        if fmt.get('format_note') in ['unknown', 'storyboard']:
            continue
        
        # Audio format
        if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none' and fmt.get('abr'):
            qualities["audio"][fmt['format_id']] = {
                "abr": int(fmt['abr']),
                "acodec": fmt['acodec'],
                "audio_channels": int(fmt.get('audio_channels', 0)),
                "filesize": int(fmt.get('filesize') or fmt.get('filesize_approx') or 0)
            }
        
        # Video format
        elif fmt.get('vcodec') != 'none' and fmt.get('height') and fmt.get('fps'):
            qualities["video"][fmt['format_id']] = {
                "height": int(fmt['height']),
                "width": int(fmt['width']),
                "fps": int(fmt['fps']),
                "vcodec": fmt['vcodec'],
                "format_note": fmt.get('format_note', 'unknown'),
                "dynamic_range": fmt.get('dynamic_range', 'unknown'),
                "filesize": int(fmt.get('filesize') or fmt.get('filesize_approx') or 0)
            }
    
    qualities["video"] = dict(sorted(qualities["video"].items(), 
                                   key=lambda x: (x[1]['height'], x[1]['fps'])))
    qualities["audio"] = dict(sorted(qualities["audio"].items(), 
                                   key=lambda x: x[1]['abr']))
    
    return qualities

def handle_regular_file(filename: str):
    raw = request.args.get('raw', 'false').lower() == 'true'
    response = send_from_directory(storage.DOWNLOAD_DIR, filename, as_attachment=raw)
    response.headers['Accept-Ranges'] = 'bytes'
    response.headers['Cache-Control'] = 'public, max-age=3600'
    if raw:
        response.headers['Content-Disposition'] = f'inline; filename="{filename}"'
    return response

@app.route('/create_key', methods=['POST'])
@require_permission('create_key')
def create_key():
    data = request.json
    name = data.get('name')
    permissions = data.get('permissions')
    
    if not name or not permissions:
        return jsonify({'error': 'Name and permissions required'}), 400
    
    key = auth_manager.create_key(name, permissions)
    return jsonify({'message': 'API key created', 'name': name, 'key': key}), 201

@app.route('/delete_key/<name>', methods=['DELETE'])
@require_permission('delete_key')
def delete_key(name: str):
    if auth_manager.delete_key(name):
        return jsonify({'message': 'API key deleted', 'name': name}), 200
    return jsonify({'error': 'Key not found'}), 404

@app.route('/get_key/<name>', methods=['GET'])
@require_permission('get_key')
def get_key(name: str):
    keys = Storage.load_keys()
    if name in keys:
        return jsonify({'name': name, 'key': keys[name]['key']}), 200
    return jsonify({'error': 'Key not found'}), 404

@app.route('/get_keys', methods=['GET'])
@require_permission('get_keys')
def get_keys():
    return jsonify(Storage.load_keys()), 200

@app.route('/check_permissions', methods=['POST'])
def check_permissions():
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'No API key provided'}), 401
    
    keys = Storage.load_keys()
    key_name = AuthManager.get_key_name(api_key)
    
    if not key_name or key_name not in keys:
        return jsonify({'error': 'Invalid API key'}), 401
    
    required = request.json.get('permissions', [])
    current = keys[key_name]['permissions']
    
    if set(required).issubset(current):
        return jsonify({'message': 'Permissions granted'}), 200
    return jsonify({'message': 'Insufficient permissions'}), 403

if __name__ == '__main__':
    app.run(host='0.0.0.0')
