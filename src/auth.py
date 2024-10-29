from functools import wraps
from flask import request, jsonify
from src.json_utils import load_keys, save_keys, load_tasks
from config import REQUEST_LIMIT, TASK_CLEANUP_TIME, DEFAULT_MEMORY_QUOTA
from config import DEFAULT_MEMORY_QUOTA_RATE, AVAILABLE_MEMORY
from datetime import datetime, timedelta
import secrets

def generate_key():
    return secrets.token_urlsafe(32)

def get_total_memory_usage():
    keys = load_keys()
    total_usage = 0
    current_time = datetime.now()
    
    for key_info in keys.values():
        if 'memory_usage' not in key_info:
            continue

        key_info['memory_usage'] = [
            usage for usage in key_info['memory_usage']
            if datetime.fromisoformat(usage['timestamp']) > current_time - timedelta(minutes=DEFAULT_MEMORY_QUOTA_RATE)
        ]
        total_usage += sum(usage['size'] for usage in key_info['memory_usage'])
    return total_usage

def check_server_memory(new_size=0):
    total_usage = get_total_memory_usage()
    
    if total_usage + new_size > AVAILABLE_MEMORY:
        current_usage_gb = total_usage / (1024 * 1024 * 1024)
        new_size_gb = new_size / (1024 * 1024 * 1024)
        available_gb = (AVAILABLE_MEMORY - total_usage) / (1024 * 1024 * 1024)
        
        error_msg = (
            f"Server memory limit exceeded. "
            f"Current usage: {current_usage_gb:.2f}GB, "
            f"Requested: {new_size_gb:.2f}GB, "
            f"Available: {available_gb:.2f}GB. "
            "Please try downloading a smaller file or try again later."
        )
        return False, error_msg
    return True, ""

def check_memory_limit(api_key, new_size=0, task_id=None):
    server_memory_ok, error_msg = check_server_memory(new_size)
    if not server_memory_ok:
        raise Exception(error_msg)
    
    keys = load_keys()
    current_time = datetime.now()
    key_name = get_key_name(api_key)
    if not key_name or key_name not in keys:
        return False
        
    key_info = keys[key_name]
    if 'memory_quota' not in key_info:
        key_info['memory_quota'] = DEFAULT_MEMORY_QUOTA
    if 'memory_usage' not in key_info:
        key_info['memory_usage'] = []
    
    key_info['memory_usage'] = [
        usage for usage in key_info['memory_usage']
        if datetime.fromisoformat(usage['timestamp']) > current_time - timedelta(minutes=DEFAULT_MEMORY_QUOTA_RATE)
    ]
    
    current_usage = sum(usage['size'] for usage in key_info['memory_usage'])

    if current_usage + new_size > key_info['memory_quota']:
        current_usage_gb = current_usage / (1024 * 1024 * 1024)
        quota_gb = key_info['memory_quota'] / (1024 * 1024 * 1024)
        new_size_gb = new_size / (1024 * 1024 * 1024)
        raise Exception(
            f"User memory quota exceeded. "
            f"Current usage: {current_usage_gb:.2f}GB, "
            f"Requested: {new_size_gb:.2f}GB, "
            f"Quota: {quota_gb:.2f}GB"
        )
    
    if new_size > 0:
        key_info['current_usage'] = current_usage + new_size
        key_info['memory_usage'].append({
            'size': new_size,
            'timestamp': current_time.isoformat(),
            'task_id': task_id
        })
        key_info['last_access'] = current_time.isoformat()
    
    keys[key_name] = key_info
    save_keys(keys)
    return True

def check_rate_limit(api_key):
    tasks = load_tasks()
    key_name = get_key_name(api_key)
    rate = 0
    for task_name, task_info in tasks.items():
        if task_info['key_name'] == key_name:
            rate += 1
    if rate >= REQUEST_LIMIT: return False
    return True

def check_api_key(required_permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            api_key = request.headers.get('X-API-Key')
            if not api_key:
                return jsonify({'error': 'No API key provided'}), 401
            keys = load_keys()
            key_name = get_key_name(api_key)
            if not key_name:
                return jsonify({'error': 'Invalid API key'}), 401
            key_info = keys[key_name]
            if not check_rate_limit(api_key):
                return jsonify({'error': f'Rate limit exceeded. Maximum {REQUEST_LIMIT} requests per {TASK_CLEANUP_TIME} minutes.'}), 429
            permissions = key_info['permissions']
            if required_permission not in permissions:
                return jsonify({'error': 'Insufficient permissions'}), 403
            key_info['last_access'] = datetime.now().isoformat()
            save_keys(keys)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_key_name(api_key):
    keys = load_keys()
    for key_name, key_info in keys.items():
        if key_info['key'] == api_key:
            return key_name
    return None

def create_api_key(name, permissions, memory_quota=5368709120):
    keys = load_keys()
    new_key = generate_key()
    keys[name] = {
        'key': new_key,
        'permissions': permissions,
        'memory_quota': memory_quota,
        'current_usage': 0,
        'task_ids': [],
        'memory_usage': [],
        'last_access': datetime.now().isoformat()
    }
    save_keys(keys)
    return new_key

def delete_api_key(name):
    keys = load_keys()
    if name in keys:
        del keys[name]
        save_keys(keys)
        return True
    return False

def get_key_info(api_key):
    keys = load_keys()
    key_info = next((item for item in keys.values() if item['key'] == api_key), None)
    return key_info

if load_keys() == {}: create_api_key("admin", ["create_key", "delete_key", "get_key", "get_keys", "get_video", "get_audio", "get_live_video", "get_live_audio", "get_info"])
