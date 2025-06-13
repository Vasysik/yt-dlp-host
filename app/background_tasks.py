import asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
from typing import List, Optional, Dict, Any

from app.core.config import settings
from app import crud, models, yt_handler, schemas
from app.database import AsyncSessionLocal
from app.auth import check_memory_quotas_and_server_limit, record_task_memory_usage
from fastapi import HTTPException

async def _prepare_download_params(task_db_params: Dict[str, Any], is_live: bool) -> Dict[str, Any]:
    return {
        "url_str": str(task_db_params["url"]),
        "task_specific_params": task_db_params,
        "is_live": is_live
    }

async def _prepare_getinfo_params(task_db_params: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "url_str": str(task_db_params["url"])
    }

TASK_TYPE_HANDLERS = {
    settings.PERM_GET_VIDEO: {
        "processor_func": yt_handler.run_download_task,
        "params_builder": lambda p: _prepare_download_params(p, is_live=False),
        "is_download": True, "is_live": False, "is_info": False
    },
    settings.PERM_GET_AUDIO: {
        "processor_func": yt_handler.run_download_task,
        "params_builder": lambda p: _prepare_download_params(p, is_live=False),
        "is_download": True, "is_live": False, "is_info": False
    },
    settings.PERM_GET_LIVE_VIDEO: {
        "processor_func": yt_handler.run_download_task,
        "params_builder": lambda p: _prepare_download_params(p, is_live=True),
        "is_download": True, "is_live": True, "is_info": False
    },
    settings.PERM_GET_LIVE_AUDIO: {
        "processor_func": yt_handler.run_download_task,
        "params_builder": lambda p: _prepare_download_params(p, is_live=True),
        "is_download": True, "is_live": True, "is_info": False
    },
    settings.PERM_GET_INFO: {
        "processor_func": yt_handler.run_getinfo_task,
        "params_builder": _prepare_getinfo_params,
        "is_download": False, "is_live": False, "is_info": True
    },
}


async def _process_single_task_logic(db_task: models.Task, db: AsyncSession):
    task_id = db_task.id
    task_type = db_task.task_type
    task_params_from_db = db_task.params

    print(f"[{datetime.utcnow()}] Processing task {task_id} of type {task_type}")
    await crud.update_task_status_db(db, task_id, models.TaskStatusEnum.PROCESSING)

    handler_config = TASK_TYPE_HANDLERS.get(task_type)
    if not handler_config:
        error_msg = f"No processor configured for task type: {task_type}"
        print(f"[{datetime.utcnow()}] {error_msg} for task {task_id}")
        await crud.update_task_status_db(db, task_id, models.TaskStatusEnum.ERROR, {"error": error_msg})
        return

    processing_func = handler_config["processor_func"]
    params_builder = handler_config["params_builder"]
    
    try:
        estimated_size_bytes = 0
        if handler_config["is_download"] and not handler_config["is_live"]:
            video_f_eval = task_params_from_db.get('video_format')
            audio_f_eval = task_params_from_db.get('audio_format')
            if task_type == settings.PERM_GET_AUDIO:
                video_f_eval = None 
            
            url_for_eval = str(task_params_from_db["url"])
            estimated_size_bytes = await yt_handler.get_estimated_size(url_for_eval, video_f_eval, audio_f_eval)
            print(f"[{datetime.utcnow()}] Task {task_id}: Estimated size: {estimated_size_bytes} bytes for URL {url_for_eval}")

            if estimated_size_bytes == -1:
                print(f"[{datetime.utcnow()}] Task {task_id}: Failed to estimate size. Proceeding with caution (size 0 for quota check).")
                estimated_size_bytes = 0
            
            api_key_obj = await crud.get_api_key_by_name(db, name=db_task.api_key_name)
            if not api_key_obj:
                raise Exception(f"API key '{db_task.api_key_name}' not found for task {task_id} during processing.")
            
            await check_memory_quotas_and_server_limit(api_key_obj, estimated_size_bytes, db)
            print(f"[{datetime.utcnow()}] Task {task_id}: Memory quotas passed for estimated size {estimated_size_bytes}.")
        
        kwargs_for_processor = await params_builder(task_params_from_db)
        
        result_from_handler = await processing_func(task_id=task_id, **kwargs_for_processor)
        
        task_result_payload = {}
        actual_size_bytes = 0

        if handler_config["is_info"]:
            info_file_path_obj, _ = result_from_handler
            task_result_payload["file_path"] = f"/files/{task_id}/{info_file_path_obj.name}"
            actual_size_bytes = info_file_path_obj.stat().st_size
        elif handler_config["is_download"]:
            downloaded_file_path_obj, actual_size_bytes = result_from_handler
            task_result_payload["file_path"] = f"/files/{task_id}/{downloaded_file_path_obj.name}"
            task_result_payload["size_bytes"] = actual_size_bytes

        await crud.update_task_status_db(db, task_id, models.TaskStatusEnum.COMPLETED, task_result_payload)
        print(f"[{datetime.utcnow()}] Task {task_id} completed. Result: {task_result_payload}")

        if handler_config["is_download"] and actual_size_bytes > 0:
            await record_task_memory_usage(db, db_task.api_key_name, task_id, actual_size_bytes)
            print(f"[{datetime.utcnow()}] Task {task_id}: Recorded memory usage of {actual_size_bytes} bytes.")
        elif handler_config["is_download"] and estimated_size_bytes > 0 and actual_size_bytes == 0:
            print(f"[{datetime.utcnow()}] Warning: Task {task_id} resulted in 0 bytes, but was estimated at {estimated_size_bytes} bytes. Memory usage not recorded for 0 bytes.")
        
    except HTTPException as http_exc:
        error_detail = http_exc.detail
        print(f"[{datetime.utcnow()}] Quota/HTTP Exception for task {task_id}: {error_detail}")
        await crud.update_task_status_db(db, task_id, models.TaskStatusEnum.ERROR, {"error": f"Processing aborted: {error_detail}"})
    except Exception as e:
        error_msg = f"Error processing task {task_id}: {type(e).__name__} - {str(e)}"
        print(f"[{datetime.utcnow()}] {error_msg}")
        await crud.update_task_status_db(db, task_id, models.TaskStatusEnum.ERROR, {"error": error_msg})


async def task_processor_worker():
    print(f"[{datetime.utcnow()}] Task processor worker started.")
    yt_handler.init_executor()
    yt_handler.ensure_download_dir_exists()

    while True:
        try:
            async with AsyncSessionLocal() as db:
                waiting_tasks = await crud.get_tasks_by_status_db(db, models.TaskStatusEnum.WAITING, limit=settings.MAX_WORKERS)
                
                if waiting_tasks:
                    print(f"[{datetime.utcnow()}] Found {len(waiting_tasks)} waiting tasks. Processing...")
                    await asyncio.gather(*( _process_single_task_logic(task, db) for task in waiting_tasks ))
                else:
                    await asyncio.sleep(1)

        except Exception as e:
            print(f"[{datetime.utcnow()}] Critical error in task_processor_worker main loop: {e}")
            await asyncio.sleep(5)


async def task_cleanup_worker():
    print(f"[{datetime.utcnow()}] Task cleanup worker started.")
    while True:
        try:
            cleanup_older_than_dt = datetime.utcnow() - timedelta(minutes=settings.TASK_CLEANUP_TIME_MINUTES)
            async with AsyncSessionLocal() as db:
                tasks_to_cleanup = await crud.get_tasks_for_cleanup_db(db, cleanup_older_than_dt)
                if tasks_to_cleanup:
                    print(f"[{datetime.utcnow()}] Found {len(tasks_to_cleanup)} tasks for cleanup (older than {cleanup_older_than_dt}).")
                for task in tasks_to_cleanup:
                    print(f"[{datetime.utcnow()}] Cleaning up task {task.id} (completed/error at {task.completed_at})")
                    await yt_handler.cleanup_task_files(task.id)
                    await crud.delete_task_from_db(db, task.id)
                
                # very_old_mu_threshold = datetime.utcnow() - timedelta(days=settings.TASK_CLEANUP_TIME_MINUTES / (60*24) + 2) # Например, старше времени очистки задач + 2 дня
                # await crud.delete_old_memory_usage_entries_db(db, very_old_mu_threshold)

            await asyncio.sleep(60 * 5)
        except Exception as e:
            print(f"[{datetime.utcnow()}] Error in task_cleanup_worker: {e}")
            await asyncio.sleep(60)


async def reset_processing_tasks_on_startup():
    print(f"[{datetime.utcnow()}] Resetting tasks stuck in 'processing' state on startup...")
    async with AsyncSessionLocal() as db:
        processing_tasks = await crud.get_processing_tasks_on_startup_db(db)
        if processing_tasks:
            print(f"[{datetime.utcnow()}] Found {len(processing_tasks)} tasks in 'processing' state. Setting to 'error'.")
            for task in processing_tasks:
                await crud.update_task_status_db(
                    db,
                    task.id,
                    models.TaskStatusEnum.ERROR,
                    {"error": "Task was interrupted due to server restart/shutdown."}
                )
        else:
            print(f"[{datetime.utcnow()}] No tasks found in 'processing' state at startup.")
