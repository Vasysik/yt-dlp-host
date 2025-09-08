import secrets
from functools import wraps
from datetime import datetime, timedelta
from typing import Optional, List, Tuple

from flask import request, jsonify
from src.storage import Storage
from src.models import ApiKey
from config import task, memory

class AuthManager:
    @staticmethod
    def generate_key() -> str:
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def get_key_name(api_key: str) -> Optional[str]:
        keys = Storage.load_keys()
        for key_name, key_info in keys.items():
            if key_info['key'] == api_key:
                return key_name
        return None
    
    def create_key(self, name: str, permissions: List[str], 
                   memory_quota: int = memory.DEFAULT_QUOTA_BYTES) -> str:
        keys = Storage.load_keys()
        api_key = ApiKey(
            key=self.generate_key(),
            name=name,
            permissions=permissions,
            memory_quota=memory_quota,
            last_access=datetime.now().isoformat()
        )
        keys[name] = api_key.to_dict()
        Storage.save_keys(keys)
        return api_key.key
    
    def delete_key(self, name: str) -> bool:
        keys = Storage.load_keys()
        if name in keys:
            del keys[name]
            Storage.save_keys(keys)
            return True
        return False

class MemoryManager:
    @staticmethod
    def _clean_old_usage(memory_usage: List[dict]) -> List[dict]:
        current_time = datetime.now()
        cutoff_time = current_time - timedelta(minutes=memory.QUOTA_RATE_MINUTES)
        return [
            usage for usage in memory_usage
            if datetime.fromisoformat(usage['timestamp']) > cutoff_time
        ]
    
    def get_total_usage(self) -> int:
        keys = Storage.load_keys()
        total = 0
        
        for key_info in keys.values():
            if 'memory_usage' not in key_info:
                continue
            
            key_info['memory_usage'] = self._clean_old_usage(key_info['memory_usage'])
            total += sum(usage['size'] for usage in key_info['memory_usage'])
        
        return total
    
    def check_server_memory(self, new_size: int = 0) -> Tuple[bool, str]:
        total_usage = self.get_total_usage()
        
        if total_usage + new_size > memory.AVAILABLE_BYTES:
            gb = lambda x: x / (1024 ** 3)
            return False, (
                f"Server memory limit exceeded. "
                f"Current: {gb(total_usage):.2f}GB, "
                f"Requested: {gb(new_size):.2f}GB, "
                f"Available: {gb(memory.AVAILABLE_BYTES - total_usage):.2f}GB"
            )
        return True, ""
    
    def check_and_update_quota(self, api_key: str, new_size: int, task_id: str) -> None:
        ok, error = self.check_server_memory(new_size)
        if not ok:
            raise Exception(error)
        
        keys = Storage.load_keys()
        key_name = AuthManager.get_key_name(api_key)
        
        if not key_name or key_name not in keys:
            raise Exception("Invalid API key")
        
        key_info = keys[key_name]
        key_info.setdefault('memory_quota', memory.DEFAULT_QUOTA_BYTES)
        key_info.setdefault('memory_usage', [])
        
        key_info['memory_usage'] = self._clean_old_usage(key_info['memory_usage'])
        current_usage = sum(u['size'] for u in key_info['memory_usage'])
        
        if current_usage + new_size > key_info['memory_quota']:
            gb = lambda x: x / (1024 ** 3)
            raise Exception(
                f"User quota exceeded. Current: {gb(current_usage):.2f}GB, "
                f"Requested: {gb(new_size):.2f}GB, Quota: {gb(key_info['memory_quota']):.2f}GB"
            )
        
        if new_size > 0:
            key_info['memory_usage'].append({
                'size': new_size,
                'timestamp': datetime.now().isoformat(),
                'task_id': task_id
            })
            key_info['last_access'] = datetime.now().isoformat()
        
        Storage.save_keys(keys)

class RateLimiter:
    @staticmethod
    def check_rate_limit(api_key: str) -> bool:
        tasks = Storage.load_tasks()
        key_name = AuthManager.get_key_name(api_key)
        count = sum(1 for t in tasks.values() if t.get('key_name') == key_name)
        return count < task.REQUEST_LIMIT

def require_permission(permission: str):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            api_key = request.headers.get('X-API-Key')
            
            if not api_key:
                return jsonify({'error': 'No API key provided'}), 401
            
            keys = Storage.load_keys()
            key_name = AuthManager.get_key_name(api_key)
            
            if not key_name:
                return jsonify({'error': 'Invalid API key'}), 401
            
            key_info = keys[key_name]
            
            if not RateLimiter.check_rate_limit(api_key):
                return jsonify({
                    'error': f'Rate limit exceeded. Max {task.REQUEST_LIMIT} per {task.CLEANUP_TIME_MINUTES} min'
                }), 429
            
            if permission not in key_info['permissions']:
                return jsonify({'error': 'Insufficient permissions'}), 403
            
            key_info['last_access'] = datetime.now().isoformat()
            Storage.save_keys(keys)
            
            return f(*args, **kwargs)
        return wrapper
    return decorator

# Initialize admin key if needed
auth_manager = AuthManager()
memory_manager = MemoryManager()

if not Storage.load_keys():
    auth_manager.create_key(
        "admin",
        ["create_key", "delete_key", "get_key", "get_keys", 
         "get_video", "get_audio", "get_live_video", "get_live_audio", "get_info"]
    )
