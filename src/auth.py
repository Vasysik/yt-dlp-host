from functools import wraps
from flask import request, jsonify
from json_utils import load_keys, save_keys, load_tasks
from config import REQUEST_LIMIT, TASK_CLEANUP_TIME
import secrets

def generate_key():
    return secrets.token_urlsafe(32)

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
            permissions = get_permissions(api_key)
            if required_permission not in permissions:
                return jsonify({'error': 'Insufficient permissions'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_key_name(api_key):
    keys = load_keys()
    for key_name, key_info in keys.items():
        if key_info['key'] == api_key:
            return key_name
    return None

def create_api_key(name, permissions):
    keys = load_keys()
    new_key = generate_key()
    keys[name] = {
        'key': new_key,
        'permissions': permissions
    }
    save_keys(keys)
    return new_key

def delete_api_key(name):
    keys = load_keys()
    if name in keys:
        del keys[name]
        save_keys(keys)

def get_all_keys():
    return load_keys()

def get_permissions(api_key):
    if not api_key:
        return jsonify({'error': 'No API key provided'}), 401
    keys = load_keys()
    key_info = next((item for item in keys.values() if item['key'] == api_key), None)
    if not key_info:
        return jsonify({'error': 'Invalid API key'}), 401
    return key_info['permissions']

def permissions_check(permissions):
    api_key = request.headers.get('X-API-Key')
    current_permissions = get_permissions(api_key)
    return set(permissions).issubset(current_permissions)

if load_keys() == {}: create_api_key("admin", ["admin", "download", "get_info"])