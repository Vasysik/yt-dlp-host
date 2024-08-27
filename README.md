# YouTube Downloader API

## Overview

This API provides a set of endpoints for downloading YouTube videos, retrieving video information, and managing API keys. It's designed to be simple to use while offering powerful functionality for video processing and information retrieval.

## Table of Contents

1. [Running the Server](#running-the-server)
2. [Configuration](#configuration)
3. [Authentication](#authentication)
4. [Rate Limiting](#rate-limiting)
5. [Endpoints](#endpoints)
   - [Get Video (`/get_video`)](#get-video-get_video)
   - [Get Audio (`/get_audio`)](#get-audio-get_audio)
   - [Get Info (`/get_info`)](#get-info-get_info)
   - [Create API Key (`/create_key`)](#create-api-key-create_key)
   - [Delete API Key (`/delete_key/<name>`)](#delete-api-key-delete_keyname)
   - [List API Keys (`/list_keys`)](#list-api-keys-list_keys)
   - [Get Task Status (`/status/<task_id>`)](#get-task-status-statustask_id)
   - [Get File (`/files/<path:filename>`)](#get-file-filespathfilename)
6. [Error Handling](#error-handling)
7. [Examples](#examples)

## Running the Server

To run the server, follow these steps:

1. Clone the repository:
   ```
   git clone https://github.com/your-username/youtube-downloader-api.git
   cd youtube-downloader-api
   ```

2. Build and run the Docker container:
   ```
   docker-compose up --build
   ```

3. The server will be accessible at `http://localhost:5000`.

## Configuration

The server's configuration is defined in the `config.py` file. Here are the default values:

- `DOWNLOAD_DIR`: The directory where downloaded files will be stored. Default is `'/app/downloads'`.
- `TASKS_FILE`: The path to the JSON file that stores task information. Default is `'jsons/tasks.json'`.
- `KEYS_FILE`: The path to the JSON file that stores API keys and their permissions. Default is `'jsons/api_keys.json'`.
- `TASK_CLEANUP_TIME`: The time (in minutes) after which completed tasks will be removed. Default is `10`.
- `REQUEST_LIMIT`: The maximum number of requests allowed within the `TASK_CLEANUP_TIME` period. Default is `20`.
- `MAX_WORKERS`: The maximum number of concurrent workers for processing tasks. Default is `4`.

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
      "quality": "1080p"
  }
  ```
- **Parameters:**
  - `url` (required): The URL of the video to be downloaded.
  - `quality` (optional): The quality of the video (e.g., "360p", "720p", "1080p", "best"). Default is "best".
- **Permissions:** Requires the `get_video` permission.
- **Response:**
  ```json
  {
      "status": "waiting",
      "task_id": "abcdefgh12345678"
  }
  ```

### Get Audio (`/get_audio`)

Initiates a audio get_audio task from the specified URL.

- **Method:** POST
- **URL:** `/get_audio`
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
  - `url` (required): The URL of the audio to be downloaded.
- **Permissions:** Requires the `get_audio` permission.
- **Response:**
  ```json
  {
      "status": "waiting",
      "task_id": "abcdefgh12345678"
  }
  ```

### Get Info (`/get_info`)

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
      "permissions": ["get_video", "get_audio", "get_info"]
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
          "permissions": ["admin", "get_video", "get_audio", "get_info"]
      },
      "user_key": {
          "key": "user_api_key_here",
          "permissions": ["get_video", "get_audio", "get_info"]
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
      "url": "https://youtu.be/1FPdtR_5KFo"
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
```

## Contributing

Contributions to yt-dlp-host are welcome! If you have any suggestions, bug reports, or feature requests, please open an issue on the GitHub repository. Pull requests are also encouraged.
