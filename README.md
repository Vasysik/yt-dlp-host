# YouTube Downloader API

## Overview

This API offers a range of endpoints for downloading YouTube videos, retrieving video information, and managing API keys. It is designed to be user-friendly while providing robust functionality for video processing and information retrieval. The API leverages yt-dlp to handle video downloads and information retrieval efficiently on a dedicated host.

## Table of Contents

1. [Running the Server](#running-the-server)
2. [Configuration](#configuration)
3. [Authentication](#authentication)
4. [Rate Limiting](#rate-limiting)
5. [Endpoints](#endpoints)
   - [Get Video (`/get_video`)](#get-video-get_video)
   - [Get Audio (`/get_audio`)](#get-audio-get_audio)
   - [Get Live Video (`/get_video`)](#get-live-video-get_live_video)
   - [Get Live Audio (`/get_audio`)](#get-live-audio-get_live_audio)
   - [Get Info (`/get_info`)](#get-info-get_info)
   - [Create API Key (`/create_key`)](#create-api-key-create_key)
   - [Delete API Key (`/delete_key/<name>`)](#delete-api-key-delete_keyname)
   - [List API Keys (`/get_keys`)](#list-api-keys-get_keys)
   - [Get API Key (`/get_key/<name>`)](#get-api-key-get_keyname)
   - [Get Task Status (`/status/<task_id>`)](#get-task-status-statustask_id)
   - [Get File (`/files/<path:filename>`)](#get-file-filespathfilename)
6. [Error Handling](#error-handling)
7. [Examples](#examples)

## Running the Server

To run the server, follow these steps:

1. Build and run the Docker container:
   ```
   docker-compose up --build
   ```

2. The server will be accessible at `http://localhost:5001`.

3. Test it
```bash
curl -X POST \
  http://127.0.0.1:5001/get_video \
  -H "Content-Type: application/json" \
  -H "X-API-Key: HRlnuuSGlpZdiktEflILeG9m6jrgvXoiah-ZlCxFkiw" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "start_time": "00:00:00",
    "end_time": "00:00:10"
  }'
```

4. Get youtube_cookies.txt from chrome browser by

```bash
yt-dlp \ --cookies-from-browser chrome \ --cookies youtube_cookies.txt \ --skip-download https://www.youtube.com/watch\?v\=1XF-NG_35NE

yt-dlp --cookies-from-browser chrome --cookies youtube_cookies.txt --skip-download https://www.youtube.com/watch\?v\=1XF-NG_35NE
```

## Configuration

The server's configuration is defined in the `config.py` file. Here are the default values:

- `DOWNLOAD_DIR`: The directory where downloaded files will be stored. Default is `'/app/downloads'`.
- `TASKS_FILE`: The path to the JSON file that stores task information. Default is `'jsons/tasks.json'`.
- `KEYS_FILE`: The path to the JSON file that stores API keys and their permissions. Default is `'jsons/api_keys.json'`.
- `TASK_CLEANUP_TIME`: The time (in minutes) after which completed tasks will be removed. Default is `10`.
- `REQUEST_LIMIT`: The maximum number of requests allowed within the `TASK_CLEANUP_TIME` period. Default is `20`.
- `MAX_WORKERS`: The maximum number of concurrent workers for processing tasks. Default is `4`.

## Authentication

All requests to the API must include an API key in the `X-API-Key` header. To obtain an API key, contact the API administrator or use the `/create_key` endpoint if you have create_key permissions.

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
      "video_format": "bestvideo[height<=1080]",
      "audio_format": "bestaudio[abr<=129]",
      "start_time": 30,
      "end_time": 60,
      "force_keyframes": false
  }
  ```
- **Parameters:**
  - `url` (required): The URL of the video to be downloaded.
  - `video_format` (optional): The [format](https://github.com/yt-dlp/yt-dlp?tab=readme-ov-file#format-selection) of the video. Default is "bestvideo".
  - `audio_format` (optional): The [format](https://github.com/yt-dlp/yt-dlp?tab=readme-ov-file#format-selection) of the audio. Default is "bestaudio".
  - `start_time` (optional): Starting point for video fragment in seconds
  - `end_time` (optional): Ending point for video fragment in seconds
  - `force_keyframes` (optional): If true, ensures precise cutting but slower processing. If false, faster but less precise cutting. Default is false
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
      "url": "https://youtu.be/1FPdtR_5KFo",
      "audio_format": "bestaudio[abr<=129]",
      "start_time": 30,
      "end_time": 60,
      "force_keyframes": false
  }
  ```
- **Parameters:**
  - `url` (required): The URL of the audio to be downloaded.
  - `audio_format` (optional): The [format](https://github.com/yt-dlp/yt-dlp?tab=readme-ov-file#format-selection) of the audio. Default is "bestaudio".
  - `start_time` (optional): Starting point for video fragment in seconds
  - `end_time` (optional): Ending point for video fragment in seconds
  - `force_keyframes` (optional): If true, ensures precise cutting but slower processing. If false, faster but less precise cutting. Default is false
- **Permissions:** Requires the `get_audio` permission.
- **Response:**
  ```json
  {
      "status": "waiting",
      "task_id": "abcdefgh12345678"
  }
  ```

### Get Live Video (`/get_live_video`)

Initiates a video get_live_video task from the specified URL.

- **Method:** POST
- **URL:** `/get_live_video`
- **Headers:**
  - `X-API-Key`: Your API key
  - `Content-Type`: application/json
- **Body:**
  ```json
  {
      "url": "https://youtu.be/1FPdtR_5KFo",
      "start": 0,
      "duration": 300,
      "video_format": "bestvideo[height<=1080]",
      "audio_format": "bestaudio[abr<=129]"
  }
  ```
- **Parameters:**
  - `url` (required): The URL of the live stream to be downloaded.
  - `start` (optional): The starting point in seconds for the stream recording.
  - `duration` (required): The length of the recording in seconds from the start point.
  - `video_format` (optional): The [format](https://github.com/yt-dlp/yt-dlp?tab=readme-ov-file#format-selection) of the video. Default is "bestvideo".
  - `audio_format` (optional): The [format](https://github.com/yt-dlp/yt-dlp?tab=readme-ov-file#format-selection) of the audio. Default is "bestaudio".
- **Permissions:** Requires the `get_live_video` permission.
- **Response:**
  ```json
  {
      "status": "waiting",
      "task_id": "abcdefgh12345678"
  }
  ```

### Get Live Audio (`/get_live_audio`)

Initiates a audio get_live_audio task from the specified URL.

- **Method:** POST
- **URL:** `/get_live_audio`
- **Headers:**
  - `X-API-Key`: Your API key
  - `Content-Type`: application/json
- **Body:**
  ```json
  {
      "url": "https://youtu.be/1FPdtR_5KFo",
      "audio_format": "bestaudio[abr<=129]",
      "start": 0,
      "duration": 300
  }
  ```
- **Parameters:**
  - `url` (required): The URL of the live stream to be downloaded.
  - `audio_format` (optional): The [format](https://github.com/yt-dlp/yt-dlp?tab=readme-ov-file#format-selection) of the audio. Default is "bestaudio".
  - `start` (optional): The starting point in seconds for the stream recording.
  - `duration` (required): The length of the recording in seconds from the start point.
- **Permissions:** Requires the `get_live_audio` permission.
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
      "permissions": ["get_video", "get_audio", "get_live_video", "get_live_audio", "get_info"]
  }
  ```
- **Parameters:**
  - `name` (required): The name for the new API key.
  - `permissions` (required): A list of permissions for the new API key.
- **Permissions:** Requires the `create_key` permission.
- **Response:**
  ```json
  {
      "message": "API key created successfully",
      "key": "new_api_key_here",
      "name": "name"
  }
  ```

### Delete API Key (`/delete_key/<name>`)

Deletes an existing API key by its name.

- **Method:** DELETE
- **URL:** `/delete_key/<name>`
- **Headers:**
  - `X-API-Key`: Your admin API key
- **Permissions:** Requires the `delete_key` permission.
- **Response:**
  ```json
  {
      "name": "name", 
      "message": "API key deleted successfully"
  }
  ```

### List API Keys (`/get_keys`)

Retrieves a list of all existing API keys.

- **Method:** GET
- **URL:** `/get_keys`
- **Headers:**
  - `X-API-Key`: Your admin API key
- **Permissions:** Requires the `get_keys` permission.
- **Response:**
  ```json
  {
      "admin_key": {
          "key": "admin_api_key_here",
          "name": "name", 
          "permissions": ["create_key", "delete_key", "get_key", "get_keys", "get_video", "get_audio", "get_live_video", "get_live_audio", "get_info"]
      },
      "user_key": {
          "key": "user_api_key_here",
          "name": "name", 
          "permissions": ["get_video", "get_audio", "get_live_video", "get_live_audio", "get_info"]
      }
  }
  ```

  ### Get API Key (`/get_key/<name>`)

  Gets an existing API key by its name.

  - **Method:** DELETE
  - **URL:** `/get_key/<name>`
  - **Headers:**
    - `X-API-Key`: Your admin API key
  - **Permissions:** Requires the `get_key` permission.
  - **Response:**
    ```json
    {
      "message": "API key get successfully", 
      "name": "name", 
      "key": "user_api_key_here"
    }
    ```

  ### List API Keys (`/get_keys`)

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
      "video_format": "bestvideo[height<=1080]",
      "audio_format": "bestaudio[abr<=129]",
      "file": "/files/abcdefgh12345678/video.mp4"
  }
  ```

### Get File (`/files/<path:filename>`)

Retrieves a file from the server.

- **Method:** GET
- **URL:** `/files/<path:filename>`
- **Query Parameters:**
  - Any parameter matching keys in the `info.json` file
  - `qualities`: Returns a structured list of available video and audio qualities formats
- **Response:**
  - For regular files: The file content
  - For `info.json` files:
    - If no query parameters: Full content of the `info.json` file
    - If query parameters present: Filtered data based on the parameters
    - For `qualities` parameter:
      ```json
      {
        "qualities": {
          "audio": {
            "249": {
              "abr": 47,
              "acodec": "opus",
              "audio_channels": 2,
              "filesize": 528993
            },
            "139": {
              "abr": 48,
              "acodec": "mp4a.40.5",
              "audio_channels": 2,
              "filesize": 549935
            }
          },
          "video": {
            "394": {
              "height": 144,
              "width": 256,
              "fps": 25,
              "vcodec": "av01.0.00M.08",
              "format_note": "144p",
              "dynamic_range": "SDR",
              "filesize": 1009634
            },
            "134": {
              "height": 360,
              "width": 640,
              "fps": 25,
              "vcodec": "avc1.4D401E",
              "format_note": "360p",
              "dynamic_range": "SDR",
              "filesize": 6648273
            }
          }
        }
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
base_url = "http://api.example.com:5001"

headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json"
}

data = {
    "url": "https://youtu.be/1FPdtR_5KFo",
    "video_format": "bestvideo[height<=1080]",
    "audio_format": "bestaudio[abr<=129]"
}

response = requests.post(f"{base_url}/get_video", json=data, headers=headers)
print(response.json())
```

### Checking task status

```python
import requests

api_key = "your_api_key_here"
base_url = "http://api.example.com:5001"
task_id = "abcdefgh12345678"

headers = {
    "X-API-Key": api_key
}

response = requests.get(f"{base_url}/status/{task_id}", headers=headers)
print(response.json())
```

## Contributing

Contributions to yt-dlp-host are welcome! If you have any suggestions, bug reports, or feature requests, please open an issue on the GitHub repository. Pull requests are also encouraged.
