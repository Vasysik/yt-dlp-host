from flask import Flask, request, jsonify, send_from_directory
from config import DOWNLOAD_DIR, TASKS_FILE
import yt_handler
import auth
import random
import string
import os
import json

app = Flask(__name__)

def generate_random_id(length=16):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

@app.route('/download', methods=['POST'])
@auth.check_api_key('download')
def download():
    data = request.json
    url = data.get('url')
    format = data.get('format')
    quality = data.get('quality', '360p')
    
    if not url:
        return jsonify({'status': 'error', 'message': 'URL is required'}), 400
    elif not format:
        return jsonify({'status': 'error', 'message': 'Format is required'}), 400
    
    task_id = generate_random_id()
    tasks = yt_handler.load_tasks()
    tasks[task_id] = {
        'status': 'waiting',
        'task_type': 'download',
        'url': url,
        'format': format,
        'quality': quality
    }
    yt_handler.save_tasks(tasks)

    return jsonify({'status': 'waiting', 'task_id': task_id})

@app.route('/get_info', methods=['POST'])
@auth.check_api_key('get_info')
def get_info():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({'status': 'error', 'message': 'URL is required'}), 400

    task_id = generate_random_id()
    tasks = yt_handler.load_tasks()
    tasks[task_id] = {
        'status': 'waiting',
        'task_type': 'get_info',
        'url': url
    }
    yt_handler.save_tasks(tasks)

    return jsonify({'status': 'waiting', 'task_id': task_id})

@app.route('/status/<task_id>', methods=['GET'])
def status(task_id):
    tasks = yt_handler.load_tasks()
    if task_id not in tasks:
        return jsonify({'status': 'error', 'message': 'Task ID not found'}), 404

    return jsonify(tasks[task_id])

@app.route('/files/<path:filename>', methods=['GET'])
def get_file(filename):
    if filename.endswith('info.json'):
        with open(os.path.join(DOWNLOAD_DIR, filename), 'r') as f:
            data = json.load(f)
        params = request.args
        
        if params:
            filtered_data = {}
            for key, value in params.items():
                if key in data:
                    filtered_data[key] = data[key]
                elif key == 'qualities':
                    qualities = set()
                    for f in data['formats']:
                        if f.get('height'):
                            qualities.add(f'{f["height"]}p')
                    filtered_data[key] = sorted(list(qualities), key=lambda x: int(x[:-1]))

            if filtered_data:
                return jsonify(filtered_data)
            else:
                return jsonify({"error": "No matching parameters found"}), 404
        return jsonify(data)
    return send_from_directory(DOWNLOAD_DIR, filename)

@app.route('/create_key', methods=['POST'])
@auth.check_api_key('admin')
def create_key():
    data = request.json
    name = data.get('name')
    permissions = data.get('permissions')
    if not name or not permissions:
        return jsonify({'error': 'Name and permissions are required'}), 400
    if 'admin' in permissions:
        return jsonify({'error': 'Insufficient permissions'}), 403
    new_key = auth.create_api_key(name, permissions)
    return jsonify({'message': 'API key created successfully', 'key': new_key}), 201

@app.route('/delete_key/<name>', methods=['DELETE'])
@auth.check_api_key('admin')
def delete_key(name):
    auth.delete_api_key(name)
    return jsonify({'message': 'API key deleted successfully'}), 200

@app.route('/list_keys', methods=['GET'])
@auth.check_api_key('admin')
def list_keys():
    keys = auth.get_all_keys()
    return jsonify(keys), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0')
