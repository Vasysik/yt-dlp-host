from fastapi import FastAPI, Depends, HTTPException, Body, Path as FastApiPath, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.status import HTTP_201_CREATED, HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND, HTTP_403_FORBIDDEN, HTTP_500_INTERNAL_SERVER_ERROR
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
import json
from typing import List, Dict, Any, Union
from pathlib import Path as SystemPath
from pydantic import HttpUrl

from app.core.config import settings
from app.database import init_db, get_db
from app import schemas, crud, models, auth, background_tasks, yt_handler
from app.auth import Authorize, get_current_api_key_object


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    description="API for downloading YouTube videos and audio using yt-dlp, with task management and API key authentication."
)

@app.on_event("startup")
async def startup_event():
    print(f"[{datetime.utcnow()}] Application startup: {settings.PROJECT_NAME}")
    yt_handler.init_executor()
    yt_handler.ensure_download_dir_exists()
    
    await init_db()
    await background_tasks.reset_processing_tasks_on_startup()
    
    asyncio.create_task(background_tasks.task_processor_worker())
    asyncio.create_task(background_tasks.task_cleanup_worker())
    print(f"[{datetime.utcnow()}] Background workers started.")

@app.on_event("shutdown")
async def shutdown_event():
    print(f"[{datetime.utcnow()}] Application shutdown: {settings.PROJECT_NAME}")
    if yt_handler.executor:
        yt_handler.executor.shutdown(wait=True)
    print(f"[{datetime.utcnow()}] ThreadPoolExecutor shut down.")

@app.post(
    f"{settings.API_V1_STR}/keys", 
    response_model=schemas.ApiKeyCreateResponse, 
    status_code=HTTP_201_CREATED, 
    tags=["API Keys"],
    summary="Create a new API key"
)
async def create_new_api_key_endpoint(
    key_in: schemas.ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_admin_key: models.ApiKey = Depends(Authorize(required_permissions=[settings.PERM_CREATE_KEY]))
):
    existing_key = await crud.get_api_key_by_name(db, name=key_in.name)
    if existing_key:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="API key with this name already exists.")
    
    new_key_value = auth.generate_api_key_value()
    db_key = await crud.create_api_key_db(
        db, 
        name=key_in.name, 
        key_value=new_key_value, 
        permissions=key_in.permissions,
        memory_quota_bytes=key_in.memory_quota_bytes 
    )
    return schemas.ApiKeyCreateResponse(message="API key created successfully", name=db_key.name, key=new_key_value)

@app.get(
    f"{settings.API_V1_STR}/keys", 
    response_model=List[schemas.ApiKeyPublic], 
    tags=["API Keys"],
    summary="List all API keys"
)
async def list_api_keys_endpoint(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_admin_key: models.ApiKey = Depends(Authorize(required_permissions=[settings.PERM_LIST_KEYS]))
):
    keys_from_db = await crud.get_api_keys(db, skip=skip, limit=limit)
    return [schemas.ApiKeyPublic.model_validate(key_db) for key_db in keys_from_db]

@app.get(
    f"{settings.API_V1_STR}/keys/{{key_name}}", 
    response_model=schemas.ApiKeyPublic, 
    tags=["API Keys"],
    summary="Get a specific API key by name"
)
async def get_single_api_key_endpoint(
    key_name: str = FastApiPath(..., title="The name of the API key"),
    db: AsyncSession = Depends(get_db),
    current_admin_key: models.ApiKey = Depends(Authorize(required_permissions=[settings.PERM_GET_KEY]))
):
    db_key = await crud.get_api_key_by_name(db, name=key_name)
    if not db_key:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="API key not found.")
    return schemas.ApiKeyPublic.model_validate(db_key)

@app.delete(
    f"{settings.API_V1_STR}/keys/{{key_name}}", 
    response_model=schemas.MessageResponse, 
    tags=["API Keys"],
    summary="Delete an API key by name"
)
async def delete_api_key_endpoint(
    key_name: str = FastApiPath(..., title="The name of the API key to delete"),
    db: AsyncSession = Depends(get_db),
    current_admin_key: models.ApiKey = Depends(Authorize(required_permissions=[settings.PERM_DELETE_KEY]))
):
    if key_name == current_admin_key.name:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Cannot delete the API key currently in use for this request.")
    
    if key_name == settings.INITIAL_ADMIN_KEY_NAME:
        all_keys = await crud.get_api_keys(db, limit=0)
        admin_keys = [k for k in all_keys if settings.PERM_CREATE_KEY in k.permissions]
        if len(admin_keys) == 1 and admin_keys[0].name == key_name:
             raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Cannot delete the last remaining admin API key.")

    deleted_key = await crud.delete_api_key_db(db, name=key_name)
    if not deleted_key:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="API key not found or already deleted.")
    return schemas.MessageResponse(message=f"API key '{key_name}' deleted successfully.")

async def _handle_task_creation(
    task_model_request: Union[schemas.GetVideoRequest, schemas.GetAudioRequest, schemas.GetInfoRequest, schemas.GetLiveVideoRequest, schemas.GetLiveAudioRequest],
    task_type_str: str,
    db: AsyncSession,
    current_api_key: models.ApiKey
):
    task_params_for_db = task_model_request.model_dump(exclude_none=True)
    if isinstance(task_params_for_db.get("url"), HttpUrl):
         task_params_for_db["url"] = str(task_params_for_db["url"])
    
    if "live" in task_type_str and not task_params_for_db.get("duration_seconds"):
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="duration_seconds is required for live tasks.")

    task_to_create_internal = schemas.TaskCreateInternal(
        task_type=task_type_str,
        params=task_params_for_db,
        api_key_name=current_api_key.name
    )
    
    db_task = await crud.create_task_db(db, task_create_internal=task_to_create_internal)
    return schemas.TaskCreateResponse(task_id=db_task.id, status=db_task.status)

@app.post(f"{settings.API_V1_STR}/tasks/video", response_model=schemas.TaskCreateResponse, tags=["Tasks"], summary="Submit a video download task")
async def submit_get_video_task(
    request_data: schemas.GetVideoRequest,
    db: AsyncSession = Depends(get_db),
    current_api_key: models.ApiKey = Depends(Authorize(required_permissions=[settings.PERM_GET_VIDEO]))
):
    return await _handle_task_creation(request_data, settings.PERM_GET_VIDEO, db, current_api_key)

@app.post(f"{settings.API_V1_STR}/tasks/audio", response_model=schemas.TaskCreateResponse, tags=["Tasks"], summary="Submit an audio download task")
async def submit_get_audio_task(
    request_data: schemas.GetAudioRequest,
    db: AsyncSession = Depends(get_db),
    current_api_key: models.ApiKey = Depends(Authorize(required_permissions=[settings.PERM_GET_AUDIO]))
):
    request_data_dict = request_data.model_dump()
    request_data_dict["audio_only_explicit"] = True
    return await _handle_task_creation(request_data, settings.PERM_GET_AUDIO, db, current_api_key)


@app.post(f"{settings.API_V1_STR}/tasks/info", response_model=schemas.TaskCreateResponse, tags=["Tasks"], summary="Submit a task to get video information")
async def submit_get_info_task(
    request_data: schemas.GetInfoRequest,
    db: AsyncSession = Depends(get_db),
    current_api_key: models.ApiKey = Depends(Authorize(required_permissions=[settings.PERM_GET_INFO]))
):
    return await _handle_task_creation(request_data, settings.PERM_GET_INFO, db, current_api_key)

@app.post(f"{settings.API_V1_STR}/tasks/live-video", response_model=schemas.TaskCreateResponse, tags=["Tasks"], summary="Submit a live video recording task")
async def submit_get_live_video_task(
    request_data: schemas.GetLiveVideoRequest,
    db: AsyncSession = Depends(get_db),
    current_api_key: models.ApiKey = Depends(Authorize(required_permissions=[settings.PERM_GET_LIVE_VIDEO]))
):
    return await _handle_task_creation(request_data, settings.PERM_GET_LIVE_VIDEO, db, current_api_key)

@app.post(f"{settings.API_V1_STR}/tasks/live-audio", response_model=schemas.TaskCreateResponse, tags=["Tasks"], summary="Submit a live audio recording task")
async def submit_get_live_audio_task(
    request_data: schemas.GetLiveAudioRequest,
    db: AsyncSession = Depends(get_db),
    current_api_key: models.ApiKey = Depends(Authorize(required_permissions=[settings.PERM_GET_LIVE_AUDIO]))
):
    return await _handle_task_creation(request_data, settings.PERM_GET_LIVE_AUDIO, db, current_api_key)

@app.get(
    f"{settings.API_V1_STR}/tasks/status/{{task_id}}", 
    response_model=schemas.TaskPublic, 
    tags=["Tasks"],
    summary="Get the status of a specific task"
)
async def get_task_status_endpoint(
    task_id: str = FastApiPath(..., title="The ID of the task"),
    db: AsyncSession = Depends(get_db),
    current_api_key: models.ApiKey = Depends(get_current_api_key_object) 
):
    db_task = await crud.get_task_db(db, task_id=task_id)
    if not db_task:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Task not found.")
    
    if db_task.api_key_name != current_api_key.name:
        if settings.PERM_LIST_KEYS not in current_api_key.permissions:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="You do not have permission to view this task's status.")
            
    return schemas.TaskPublic.model_validate(db_task)


@app.get(f"{settings.API_V1_STR}/files/{{task_id}}/{{filename:path}}", tags=["Files"], summary="Download a file associated with a task")
async def download_file_endpoint(
    request: Request,
    task_id: str = FastApiPath(..., title="Task ID"),
    filename: str = FastApiPath(..., title="Filename"),
    db: AsyncSession = Depends(get_db),
    current_api_key: models.ApiKey = Depends(get_current_api_key_object)
):
    db_task = await crud.get_task_db(db, task_id=task_id)
    if not db_task:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Task not found, or file does not exist for this task.")
    
    if db_task.api_key_name != current_api_key.name:
        if settings.PERM_LIST_KEYS not in current_api_key.permissions:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Access to this task's files is denied.")
    
    if db_task.status != models.TaskStatusEnum.COMPLETED:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Task {task_id} is not completed. Current status: {db_task.status}")

    if not db_task.result or not db_task.result.get("file_path"):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"File path not found in task result for task {task_id}.")
    
    expected_relative_path_from_result = db_task.result.get("file_path")
    expected_filename_from_result = SystemPath(expected_relative_path_from_result).name

    if filename != expected_filename_from_result:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, 
                            detail=f"Requested filename '{filename}' does not match expected file '{expected_filename_from_result}' for task {task_id}.")
    
    server_file_path = settings.DOWNLOAD_DIR / task_id / filename
    
    try:
        resolved_server_file_path = server_file_path.resolve(strict=True) 
        if not str(resolved_server_file_path).startswith(str(settings.DOWNLOAD_DIR.resolve())):
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Access denied (path security check failed).")
        if not resolved_server_file_path.is_file():
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="File not found on server (resolved path is not a file).")
    except FileNotFoundError:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="File not found on server at the expected location.")
    except Exception as e:
        print(f"Error resolving file path {server_file_path}: {e}")
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail="Error accessing file system.")
    
    if filename == "info.json":
        query_params_dict = dict(request.query_params)
        with open(resolved_server_file_path, 'r', encoding='utf-8') as f:
            info_data_content = json.load(f)
        
        if not query_params_dict:
            return JSONResponse(content=info_data_content)
        
        response_data: Dict[str, Any] = {}
        if "qualities" in query_params_dict:
            qualities_res = schemas.InfoFileQualitiesResponse()
            for f_format in info_data_content.get('formats', []):
                if f_format.get('format_note') in ['unknown', 'storyboard']: continue
                
                detail = schemas.InfoFileQualityDetail.model_validate(f_format, strict=False)
                
                if f_format.get('acodec') != 'none' and f_format.get('vcodec') == 'none' and f_format.get('abr'):
                    qualities_res.audio[str(f_format.get('format_id', 'unknown_audio_id'))] = detail
                elif f_format.get('acodec') == 'none' and f_format.get('vcodec') != 'none' and f_format.get('height') and f_format.get('fps'):
                    qualities_res.video[str(f_format.get('format_id', 'unknown_video_id'))] = detail
            
            response_data["qualities"] = qualities_res.model_dump()
            query_params_dict.pop("qualities", None)

        for key_param in query_params_dict:
            if key_param in info_data_content:
                response_data[key_param] = info_data_content[key_param]
        
        if not response_data:
            if "qualities" in response_data and not query_params_dict:
                 return JSONResponse(content=response_data)
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="No matching parameters found in info.json")
        
        return JSONResponse(content=response_data)
    
    custom_headers = {
        'Accept-Ranges': 'bytes',
        'Cache-Control': 'public, max-age=3600'
    }
    is_raw_download = request.query_params.get('raw', 'false').lower() == 'true'
    if is_raw_download: custom_headers['Content-Disposition'] = f'inline; filename="{filename}"'

    return FileResponse(path=str(resolved_server_file_path), filename=filename, headers=custom_headers)

@app.post(
    f"{settings.API_V1_STR}/auth/check-permissions", 
    response_model=schemas.MessageResponse, 
    tags=["Auth"],
    summary="Check if the current API key has a given set of permissions"
)
async def check_permissions_route_endpoint(
    payload: Dict[str, List[str]] = Body(..., example={"permissions": ["get_video", "get_info"]}),
    current_api_key: models.ApiKey = Depends(get_current_api_key_object)
):
    permissions_to_check = payload.get("permissions")
    if permissions_to_check is None:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Missing 'permissions' field in request body.")
    if not isinstance(permissions_to_check, list):
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="'permissions' must be a list of strings.")

    user_permissions_set = set(current_api_key.permissions)
    required_perms_set = set(permissions_to_check)

    invalid_perms_for_check = list(required_perms_set - settings.VALID_PERMISSIONS_SET)
    if invalid_perms_for_check:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Invalid permissions provided for check: {invalid_perms_for_check}")

    if required_perms_set.issubset(user_permissions_set):
        return schemas.MessageResponse(message="Permissions granted.")
    else:
        missing_perms = list(required_perms_set - user_permissions_set)
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail=f"Insufficient permissions. Missing: {missing_perms}")

@app.get("/", tags=["Root"], summary="API Root", response_model=schemas.MessageResponse)
async def read_root_endpoint():
    return schemas.MessageResponse(message=f"Welcome to {settings.PROJECT_NAME}! API V1 is at {settings.API_V1_STR}")

from datetime import datetime
