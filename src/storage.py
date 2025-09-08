import json
import os
from typing import Dict, Any
from config import storage

class Storage:
    @staticmethod
    def _load_json(file_path: str) -> Dict[str, Any]:
        if not os.path.exists(file_path):
            return {}
        with open(file_path, 'r') as f:
            return json.load(f)
    
    @staticmethod
    def _save_json(file_path: str, data: Dict[str, Any]) -> None:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
    
    @classmethod
    def load_tasks(cls) -> Dict[str, Any]:
        return cls._load_json(storage.TASKS_FILE)
    
    @classmethod
    def save_tasks(cls, tasks: Dict[str, Any]) -> None:
        cls._save_json(storage.TASKS_FILE, tasks)
    
    @classmethod
    def load_keys(cls) -> Dict[str, Any]:
        return cls._load_json(storage.KEYS_FILE)
    
    @classmethod
    def save_keys(cls, keys: Dict[str, Any]) -> None:
        cls._save_json(storage.KEYS_FILE, keys)
