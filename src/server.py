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

@app.route('/get_audio', methods=['POST'])
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
        'key_name': 'anonymous',
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

@app.route('/status/<task_id>', methods=['GET'])
def status(task_id):
    tasks = load_tasks()
    if task_id not in tasks:
        return jsonify({'status': 'error', 'message': 'Task ID not found'}), 404
    return jsonify(tasks[task_id])

@app.route('/')
def index():
    return jsonify({'message': 'yt-dlp-host API is running', 'status': 'ok'})

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
