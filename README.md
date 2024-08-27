# YouTube Downloader API

## Overview

This API provides a set of endpoints for downloading YouTube videos, retrieving video information, and managing API keys. It's designed to be simple to use while offering powerful functionality for video processing and information retrieval.

## Table of Contents

1. [Authentication](#authentication)
2. [Rate Limiting](#rate-limiting)
3. [Endpoints](#endpoints)
   - [Get Video (`/get_video`)](#get-video-get_video)
   - [Get Video Info (`/get_info`)](#get-video-info-get_info)
   - [Create API Key (`/create_key`)](#create-api-key-create_key)
   - [Delete API Key (`/delete_key/<name>`)](#delete-api-key-delete_keyname)
   - [List API Keys (`/list_keys`)](#list-api-keys-list_keys)
   - [Get Task Status (`/status/<task_id>`)](#get-task-status-statustask_id)
   - [Get File (`/files/<path:filename>`)](#get-file-filespathfilename)
4. [Error Handling](#error-handling)
5. [Examples](#examples)

## Authentication

All requests to the API must include an API key in the `X-API-Key` header. To obtain an API key, contact the API administrator or use the `/create_key` endpoint if you have admin permissions.

## Endpoints

### Get Video (`/get_video`)

Initiates a video get_video task from the specified URL.

- **Method:** POST
- **URL:** `/get_video`
- **Headers:**
  - `X-API-Key`: Your API key
  - `Content-Type`: application/json
- **Body:**
  ```json
  {
      "url": "https://youtu.be/1FPdtR_5KFo",
      "file_type": "video",
      "quality": "1080p"
  }
  ```
- **Parameters:**
  - `url` (required): The URL of the video to be downloaded.
  - `file_type` (required): The type of final media ("video" or "audio").
  - `quality` (optional): The quality of the video (e.g., "360p", "720p", "1080p", "best"). Default is "best".
- **Permissions:** Requires the `get_video` permission.
- **Response:**
  ```json
  {
      "status": "waiting",
      "task_id": "abcdefgh12345678"
  }
  ```

### Get Video Info (`/get_info`)

Retrieves information about the video from the specified URL.

- **Method:** POST
- **URL:** `/get_info`
- **Headers:**
  - `X-API-Key`: Your API key
  - `Content-Type`: application/json
- **Body:**
  ```json
  {
      "url": "https://youtu.be/1FPdtR_5KFo"
  }
  ```
- **Parameters:**
  - `url` (required): The URL of the video to retrieve information about.
- **Permissions:** Requires the `get_info` permission.
- **Response:**
  ```json
  {
      "status": "waiting",
      "task_id": "ijklmnop87654321"
  }
  ```

### Create API Key (`/create_key`)

Creates a new API key with the specified permissions.

- **Method:** POST
- **URL:** `/create_key`
- **Headers:**
  - `X-API-Key`: Your admin API key
  - `Content-Type`: application/json
- **Body:**
  ```json
  {
      "name": "user_key",
      "permissions": ["get_video", "get_info"]
  }
  ```
- **Parameters:**
  - `name` (required): The name for the new API key.
  - `permissions` (required): A list of permissions for the new API key.
- **Permissions:** Requires the `admin` permission.
- **Response:**
  ```json
  {
      "message": "API key created successfully",
      "key": "new_api_key_here"
  }
  ```

### Delete API Key (`/delete_key/<name>`)

Deletes an existing API key by its name.

- **Method:** DELETE
- **URL:** `/delete_key/<name>`
- **Headers:**
  - `X-API-Key`: Your admin API key
- **Permissions:** Requires the `admin` permission.
- **Response:**
  ```json
  {
      "message": "API key deleted successfully"
  }
  ```

### List API Keys (`/list_keys`)

Retrieves a list of all existing API keys.

- **Method:** GET
- **URL:** `/list_keys`
- **Headers:**
  - `X-API-Key`: Your admin API key
- **Permissions:** Requires the `admin` permission.
- **Response:**
  ```json
  {
      "admin_key": {
          "key": "admin_api_key_here",
          "permissions": ["admin", "get_video", "get_info"]
      },
      "user_key": {
          "key": "user_api_key_here",
          "permissions": ["get_video", "get_info"]
      }
  }
  ```

### Get Task Status (`/status/<task_id>`)

Retrieves the status of a specific task by its ID.

- **Method:** GET
- **URL:** `/status/<task_id>`
- **Headers:**
  - `X-API-Key`: Your API key
- **Permissions:** No specific permission required, but the task must be associated with the API key used.
- **Response:**
  ```json
  {
      "status": "completed",
      "task_type": "get_video",
      "url": "https://youtu.be/1FPdtR_5KFo",
      "file_type": "video",
      "quality": "1080p",
      "file": "/files/abcdefgh12345678/video.mp4"
  }
  ```

### Get File (`/files/<path:filename>`)

Retrieves a file from the server.

- **Method:** GET
- **URL:** `/files/<path:filename>`
- **Headers:**
  - `X-API-Key`: Your API key
- **Permissions:** No specific permission required, but the file must be associated with the API key used.
- **Query Parameters:**
  - `qualities`: Returns a list of available video qualities (only for `info.json` files)
- **Response:**
  - For regular files: The file content
  - For `info.json` files:
    ```json
    {
        "title": "Video Title",
        "duration": 180,
        "upload_date": "20230101",
        "uploader": "Channel Name",
        "view_count": 1000000,
        "qualities": ["360p", "720p", "1080p"]
    }
    ```

## Error Handling

The API uses standard HTTP status codes to indicate the success or failure of requests. In case of an error, the response will include a JSON object with an `error` field describing the issue.

Example error response:
```json
{
    "error": "Invalid API key"
}
```

Common error codes:
- 400: Bad Request
- 401: Unauthorized (Invalid or missing API key)
- 403: Forbidden (Insufficient permissions)
- 404: Not Found
- 429: Too Many Requests (Rate limit exceeded)
- 500: Internal Server Error

## Examples

### Getting a video

```python
import requests

api_key = "your_api_key_here"
base_url = "http://api.example.com"

headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json"
}

data = {
    "url": "https://youtu.be/1FPdtR_5KFo",
    "file_type": "video",
    "quality": "720p"
}

response = requests.post(f"{base_url}/get_video", json=data, headers=headers)
print(response.json())
```

### Checking task status

```python
import requests

api_key = "your_api_key_here"
base_url = "http://api.example.com"
task_id = "abcdefgh12345678"

headers = {
    "X-API-Key": api_key
}

response = requests.get(f"{base_url}/status/{task_id}", headers=headers)
print(response.json())
