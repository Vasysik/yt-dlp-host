from flask import Flask, request, jsonify, send_from_directory
from src.json_utils import load_tasks, save_tasks, load_keys
from config import DOWNLOAD_DIR
import src.yt_handler as yt_handler
import src.auth as auth
import random
import string
import os
import json

app = Flask(__name__)
app.json.sort_keys = False

def generate_random_id(length=16):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

@app.route('/get_video', methods=['POST'])
@auth.check_api_key('get_video')
def get_video():
    data = request.json
    url = data.get('url')
    video_format = data.get('video_format', 'bestvideo')
    audio_format = data.get('audio_format', 'bestaudio')
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    force_keyframes = data.get('force_keyframes')
    
    if not url:
        return jsonify({'status': 'error', 'message': 'URL is required'}), 400
    
    task_id = generate_random_id()
    tasks = load_tasks()
    tasks[task_id] = {
        'key_name': auth.get_key_name(request.headers.get('X-API-Key')),
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
@auth.check_api_key('get_audio')
def get_audio():
    data = request.json
    url = data.get('url')
    audio_format = data.get('audio_format', 'bestaudio')
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    force_keyframes = data.get('force_keyframes')
    
    if not url:
        return jsonify({'status': 'error', 'message': 'URL is required'}), 400
    
    task_id = generate_random_id()
    tasks = load_tasks()
    tasks[task_id] = {
        'key_name': auth.get_key_name(request.headers.get('X-API-Key')),
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
@auth.check_api_key('get_info')
def get_info():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({'status': 'error', 'message': 'URL is required'}), 400
    
    task_id = generate_random_id()
    # keys = load_keys()
    # key_name = auth.get_key_name(request.headers.get('X-API-Key'))
    # key_info = keys[key_name]

    # if 'task_ids' not in key_info:
    #     key_info['task_ids'] = []
    # key_info['task_ids'].append(task_id)
    # keys[key_name] = key_info
    # auth.save_keys(keys)
    
    tasks = load_tasks()
    tasks[task_id] = {
        'key_name': auth.get_key_name(request.headers.get('X-API-Key')),
        'status': 'waiting',
        'task_type': 'get_info',
        'url': url
    }
    save_tasks(tasks)

    return jsonify({'status': 'waiting', 'task_id': task_id})

@app.route('/get_live_video', methods=['POST'])
@auth.check_api_key('get_live_video')
def get_live_video():
    data = request.json
    url = data.get('url')
    start = data.get('start', 0)
    duration = data.get('duration')
    video_format = data.get('video_format', 'bestvideo')
    audio_format = data.get('audio_format', 'bestaudio')
    
    if not url:
        return jsonify({'status': 'error', 'message': 'URL is required'}), 400
    
    task_id = generate_random_id()
    # keys = load_keys()
    # key_name = auth.get_key_name(request.headers.get('X-API-Key'))
    # key_info = keys[key_name]
    # keys[key_name] = key_info
    # auth.save_keys(keys)

    # if 'task_ids' not in key_info:
    #     key_info['task_ids'] = []
    # key_info['task_ids'].append(task_id)

    tasks = load_tasks()
    tasks[task_id] = {
        'key_name': auth.get_key_name(request.headers.get('X-API-Key')),
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
@auth.check_api_key('get_live_audio')
def get_live_audio():
    data = request.json
    url = data.get('url')
    start = data.get('start', 0)
    duration = data.get('duration', 5)
    audio_format = data.get('audio_format', 'bestaudio')
    
    if not url:
        return jsonify({'status': 'error', 'message': 'URL is required'}), 400
    
    task_id = generate_random_id()
    # keys = load_keys()
    # key_name = auth.get_key_name(request.headers.get('X-API-Key'))
    # key_info = keys[key_name]

    # if 'task_ids' not in key_info:
    #     key_info['task_ids'] = []
    # key_info['task_ids'].append(task_id)
    # keys[key_name] = key_info
    # auth.save_keys(keys)

    tasks = load_tasks()
    tasks[task_id] = {
        'key_name': auth.get_key_name(request.headers.get('X-API-Key')),
        'status': 'waiting',
        'task_type': 'get_live_audio',
        'url': url,
        'start': start,
        'duration': duration,
        'audio_format': audio_format
    }
    save_tasks(tasks)

    return jsonify({'status': 'waiting', 'task_id': task_id})

@app.route('/status/<task_id>', methods=['GET'])
def status(task_id):
    tasks = load_tasks()
    if task_id not in tasks:
        return jsonify({'status': 'error', 'message': 'Task ID not found'}), 404
    return jsonify(tasks[task_id])

@app.route('/files/<path:filename>', methods=['GET'])
def get_file(filename):
    file_path = os.path.abspath(os.path.join(DOWNLOAD_DIR, filename))

    if not os.path.isfile(file_path):
        return jsonify({"error": "File not found"}), 404
    if not file_path.startswith(os.path.abspath(DOWNLOAD_DIR)):
        return jsonify({"error": "Access denied"}), 403
    
    if filename.endswith('info.json'):
        with open(file_path, 'r') as f:
            data = json.load(f)
        params = request.args
        
        if params:
            filtered_data = {}
            for key, value in params.items():
                if key in data:
                    filtered_data[key] = data[key]
                elif key == 'qualities':
                    qualities = {"audio": {}, "video": {}}
                    for f in data['formats']:
                        if f.get('format_note') in ['unknown', 'storyboard']: continue
                        if f.get('acodec') != 'none' and f.get('vcodec') == 'none' and f.get('abr'):
                            qualities["audio"][f['format_id']] = {
                                "abr": int(f['abr']),
                                "acodec": f['acodec'],
                                "audio_channels": int(f.get('audio_channels', 0)),
                                "filesize": int(f.get('filesize') or f.get('filesize_approx') or 0)
                            }
                        elif f.get('acodec') == 'none' and f.get('vcodec') != 'none' and f.get('height') and f.get('fps') :
                            video_size = int(f.get('filesize') or f.get('filesize_approx') or 0)
                            qualities["video"][f['format_id']] = {
                                "height": int(f['height']),
                                "width": int(f['width']),
                                "fps": int(f['fps']),
                                "vcodec": f['vcodec'],
                                "format_note": f.get('format_note', 'unknown'),
                                "dynamic_range": f.get('dynamic_range', 'unknown'),
                                "filesize": video_size
                            }
                    qualities["video"] = dict(sorted(qualities["video"].items(), key=lambda x: (x[1]['height'], x[1]['fps'])))
                    qualities["audio"] = dict(sorted(qualities["audio"].items(), key=lambda x: x[1]['abr']))
                    filtered_data[key] = qualities
            if filtered_data:
                return jsonify(filtered_data)
            else:
                return jsonify({"error": "No matching parameters found"}), 404
        return jsonify(data)
    raw = request.args.get('raw', 'false').lower() == 'true'
    response = send_from_directory(DOWNLOAD_DIR, filename, as_attachment=raw)
    response.headers['Accept-Ranges'] = 'bytes'
    response.headers['Cache-Control'] = 'public, max-age=3600'
    if raw: response.headers['Content-Disposition'] = f'inline; filename="{filename}"'
    return response

@app.route('/create_key', methods=['POST'])
@auth.check_api_key('create_key')
def create_key():
    data = request.json
    name = data.get('name')
    permissions = data.get('permissions')
    if not name or not permissions:
        return jsonify({'error': 'Name and permissions are required'}), 400
    new_key = auth.create_api_key(name, permissions)
    return jsonify({'message': 'API key created successfully', 'name': name, 'key': new_key}), 201

@app.route('/delete_key/<name>', methods=['DELETE'])
@auth.check_api_key('delete_key')
def delete_key(name):
    if auth.delete_api_key(name):
        return jsonify({'message': 'API key deleted successfully', 'name': name}), 200
    return jsonify({'error': 'The key name does not exist'}), 403

@app.route('/get_key/<name>', methods=['GET'])
@auth.check_api_key('get_key')
def get_key(name):
    keys = load_keys()
    if name in keys:
        return jsonify({'message': 'API key get successfully', 'name': name, 'key': keys[name]['key']}), 200
    return jsonify({'error': 'The key name does not exist'}), 403

@app.route('/get_keys', methods=['GET'])
@auth.check_api_key('get_keys')
def get_keys():
    keys = load_keys()
    return jsonify(keys), 200

@app.route('/check_permissions', methods=['POST'])
def check_permissions():
    data = request.json
    permissions = data.get('permissions')

    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'No API key provided'}), 401
    key_info = auth.get_key_info(api_key)
    if not key_info:
        return jsonify({'error': 'Invalid API key'}), 401
    current_permissions = key_info['permissions']

    if set(permissions).issubset(current_permissions):
        return jsonify({'message': 'Permissions granted'}), 200
    return jsonify({'message': 'Insufficient permissions'}), 403

if __name__ == '__main__':
    app.run(host='0.0.0.0')
