from functools import wraps
from flask import request, jsonify
from config import KEYS_FILE
import json
import os
import secrets

def generate_key():
    return secrets.token_urlsafe(32)

def load_keys():
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_keys(keys):
    with open(KEYS_FILE, 'w') as f:
        json.dump(keys, f, indent=4)

def check_api_key(required_permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            api_key = request.headers.get('X-API-Key')
            if not api_key:
                return jsonify({'error': 'No API key provided'}), 401
            
            keys = load_keys()
            key_info = next((item for item in keys.values() if item['key'] == api_key), None)
            if not key_info:
                return jsonify({'error': 'Invalid API key'}), 401
            
            permissions = key_info['permissions']
            if required_permission not in permissions:
                return jsonify({'error': 'Insufficient permissions'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

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

if load_keys() == {}: create_api_key("admin", ["admin", "download", "get_info"])