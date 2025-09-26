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
   - [Get Live Video (`/get_live_video`)](#get-live-video-get_live_video)
   - [Get Live Audio (`/get_live_audio`)](#get-live-audio-get_live_audio)
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

1. Clone the repository:
   ```
   git clone https://github.com/Vasysik/yt-dlp-host.git
   cd yt-dlp-host
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
- `CLEANUP_TIME_MINUTES`: The time (in minutes) after which completed tasks will be removed. Default is `10`.
- `REQUEST_LIMIT`: The maximum number of requests allowed within the `CLEANUP_TIME_MINUTES` period. Default is `60`.
- `MAX_WORKERS`: The maximum number of concurrent workers for processing tasks. Default is `4`.
- `DEFAULT_QUOTA_GB`: Default memory quota for new API keys in GB. Default is `5`.
- `QUOTA_RATE_MINUTES`: Time window for quota calculation in minutes. Default is `10`.
- `AVAILABLE_BYTES`: Total available memory for all users in bytes. Default is `20GB`.

## Authentication

All requests to the API must include an API key in the `X-API-Key` header. To obtain an API key, contact the API administrator or use the `/create_key` endpoint if you have create_key permissions.

## Rate Limiting

The API implements rate limiting to prevent abuse. Each API key is limited to `60` requests within a `10` minute window. Additionally, memory quotas are enforced to prevent excessive storage usage.

## Endpoints

### Get Video (`/get_video`)

Initiates a video download task from the specified URL.

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
      "output_format": "mp4",
      "start_time": "00:00:30",
      "end_time": "00:01:00",
      "force_keyframes": false
  }
  ```
- **Parameters:**
  - `url` (required): The URL of the video to be downloaded.
  - `video_format` (optional): The [format](https://github.com/yt-dlp/yt-dlp?tab=readme-ov-file#format-selection) of the video. Default is "bestvideo".
  - `audio_format` (optional): The [format](https://github.com/yt-dlp/yt-dlp?tab=readme-ov-file#format-selection) of the audio. Default is "bestaudio".
  - `output_format` (optional): The output container format (mp4, mkv, webm, mov, avi, gif, etc.). Default is "mp4".
  - `start_time` (optional): Starting point for video fragment in HH:MM:SS format or seconds as number.
  - `end_time` (optional): Ending point for video fragment in HH:MM:SS format or seconds as number.
  - `force_keyframes` (optional): If true, ensures precise cutting but slower processing. If false, faster but less precise cutting. Default is false.
- **Permissions:** Requires the `get_video` permission.
- **Response:**
  ```json
  {
      "status": "waiting",
      "task_id": "abcdefgh12345678"
  }
  ```

### Get Audio (`/get_audio`)

Initiates an audio download task from the specified URL.

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
      "output_format": "mp3",
      "start_time": "00:00:30",
      "end_time": "00:01:00",
      "force_keyframes": false
  }
  ```
- **Parameters:**
  - `url` (required): The URL of the audio to be downloaded.
  - `audio_format` (optional): The [format](https://github.com/yt-dlp/yt-dlp?tab=readme-ov-file#format-selection) of the audio. Default is "bestaudio".
  - `output_format` (optional): The output audio format (mp3, m4a, opus, flac, wav, etc.). Default is original format.
  - `start_time` (optional): Starting point for audio fragment in HH:MM:SS format or seconds as number.
  - `end_time` (optional): Ending point for audio fragment in HH:MM:SS format or seconds as number.
  - `force_keyframes` (optional): If true, ensures precise cutting but slower processing. If false, faster but less precise cutting. Default is false.
- **Permissions:** Requires the `get_audio` permission.
- **Response:**
  ```json
  {
      "status": "waiting",
      "task_id": "abcdefgh12345678"
  }
  ```

### Get Live Video (`/get_live_video`)

Initiates a live video download task from the specified URL.

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
      "audio_format": "bestaudio[abr<=129]",
      "output_format": "mp4"
  }
  ```
- **Parameters:**
  - `url` (required): The URL of the live stream to be downloaded.
  - `start` (optional): The starting point in seconds for the stream recording. Default is 0.
  - `duration` (required): The length of the recording in seconds from the start point.
  - `video_format` (optional): The [format](https://github.com/yt-dlp/yt-dlp?tab=readme-ov-file#format-selection) of the video. Default is "bestvideo".
  - `audio_format` (optional): The [format](https://github.com/yt-dlp/yt-dlp?tab=readme-ov-file#format-selection) of the audio. Default is "bestaudio".
  - `output_format` (optional): The output container format (mp4, mkv, webm, etc.). Default is "mp4".
- **Permissions:** Requires the `get_live_video` permission.
- **Response:**
  ```json
  {
      "status": "waiting",
      "task_id": "abcdefgh12345678"
  }
  ```

### Get Live Audio (`/get_live_audio`)

Initiates a live audio download task from the specified URL.

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
      "output_format": "mp3",
      "start": 0,
      "duration": 300
  }
  ```
- **Parameters:**
  - `url` (required): The URL of the live stream to be downloaded.
  - `audio_format` (optional): The [format](https://github.com/yt-dlp/yt-dlp?tab=readme-ov-file#format-selection) of the audio. Default is "bestaudio".
  - `output_format` (optional): The output audio format (mp3, m4a, opus, flac, wav, etc.). Default is original format.
  - `start` (optional): The starting point in seconds for the stream recording. Default is 0.
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
      "name": "user_key"
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
      "name": "user_key", 
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
      "admin": {
          "key": "admin_api_key_here",
          "permissions": ["create_key", "delete_key", "get_key", "get_keys", "get_video", "get_audio", "get_live_video", "get_live_audio", "get_info"],
          "memory_quota": 5368709120,
          "memory_usage": [],
          "last_access": "2024-01-01T12:00:00"
      },
      "user_key": {
          "key": "user_api_key_here",
          "permissions": ["get_video", "get_audio", "get_live_video", "get_live_audio", "get_info"],
          "memory_quota": 5368709120,
          "memory_usage": [],
          "last_access": "2024-01-01T12:00:00"
      }
  }
  ```

### Get API Key (`/get_key/<name>`)

Gets an existing API key by its name.

- **Method:** GET
- **URL:** `/get_key/<name>`
- **Headers:**
  - `X-API-Key`: Your admin API key
- **Permissions:** Requires the `get_key` permission.
- **Response:**
  ```json
  {
      "name": "user_key", 
      "key": "user_api_key_here"
  }
  ```

### Check Permissions (`/check_permissions`)

Checks if the current API key has the specified permissions.

- **Method:** POST
- **URL:** `/check_permissions`
- **Headers:**
  - `X-API-Key`: Your API key
  - `Content-Type`: application/json
- **Body:**
  ```json
  {
      "permissions": ["get_video", "get_audio"]
  }
  ```
- **Response:**
  - Success (200):
    ```json
    {
        "message": "Permissions granted"
    }
    ```
  - Insufficient permissions (403):
    ```json
    {
        "message": "Insufficient permissions"
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
      "key_name": "user_key",
      "status": "completed",
      "task_type": "get_video",
      "url": "https://youtu.be/1FPdtR_5KFo",
      "video_format": "bestvideo[height<=1080]",
      "audio_format": "bestaudio[abr<=129]",
      "output_format": "mp4",
      "completed_time": "2024-01-01T12:00:00",
      "file": "/files/abcdefgh12345678/video.mp4"
  }
  ```

### Get File (`/files/<path:filename>`)

Retrieves a file from the server.

- **Method:** GET
- **URL:** `/files/<path:filename>`
- **Query Parameters:**
  - `raw` (optional): If set to "true", forces download of the file.
  - Any parameter matching keys in the `info.json` file (for info.json files only).
  - `qualities`: Returns a structured list of available video and audio qualities formats (for info.json files only).
- **Response:**
  - For regular files: The file content with appropriate headers.
  - For `info.json` files:
    - If no query parameters: Full content of the `info.json` file.
    - If query parameters present: Filtered data based on the parameters.
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
- 400: Bad Request - Invalid request parameters
- 401: Unauthorized - Invalid or missing API key
- 403: Forbidden - Insufficient permissions
- 404: Not Found - Resource not found
- 429: Too Many Requests - Rate limit exceeded
- 500: Internal Server Error - Server-side error

## Examples

### Getting a video in MP4 format

```python
import requests

api_key = "your_api_key_here"
base_url = "http://localhost:5000"

headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json"
}

data = {
    "url": "https://youtu.be/1FPdtR_5KFo",
    "video_format": "bestvideo[height<=1080]",
    "audio_format": "bestaudio[abr<=129]",
    "output_format": "mp4"
}

response = requests.post(f"{base_url}/get_video", json=data, headers=headers)
print(response.json())
```

### Getting audio in MP3 format

```python
import requests

api_key = "your_api_key_here"
base_url = "http://localhost:5000"

headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json"
}

data = {
    "url": "https://youtu.be/1FPdtR_5KFo",
    "audio_format": "bestaudio",
    "output_format": "mp3"
}

response = requests.post(f"{base_url}/get_audio", json=data, headers=headers)
print(response.json())
```

### Getting a video fragment

```python
import requests

api_key = "your_api_key_here"
base_url = "http://localhost:5000"

headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json"
}

data = {
    "url": "https://youtu.be/1FPdtR_5KFo",
    "video_format": "bestvideo[height<=720]",
    "audio_format": "bestaudio",
    "output_format": "webm",
    "start_time": "00:00:30",
    "end_time": "00:01:30",
    "force_keyframes": True
}

response = requests.post(f"{base_url}/get_video", json=data, headers=headers)
print(response.json())
```

### Getting a GIF from video

```python
import requests

api_key = "your_api_key_here"
base_url = "http://localhost:5000"

headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json"
}

data = {
    "url": "https://youtu.be/1FPdtR_5KFo",
    "video_format": "bestvideo[height<=480]",
    "output_format": "gif",
    "start_time": 30,  # Can use number of seconds
    "end_time": 35
}

response = requests.post(f"{base_url}/get_video", json=data, headers=headers)
print(response.json())
```

### Checking task status and downloading the file

```python
import requests
import time

api_key = "your_api_key_here"
base_url = "http://localhost:5000"
task_id = "abcdefgh12345678"

headers = {
    "X-API-Key": api_key
}

# Check status
while True:
    response = requests.get(f"{base_url}/status/{task_id}", headers=headers)
    status_data = response.json()
    
    if status_data['status'] == 'completed':
        file_url = base_url + status_data['file']
        # Download the file
        file_response = requests.get(file_url, headers=headers)
        with open('downloaded_video.mp4', 'wb') as f:
            f.write(file_response.content)
        print("Download completed!")
        break
    elif status_data['status'] == 'error':
        print(f"Error: {status_data.get('error', 'Unknown error')}")
        break
    else:
        print(f"Status: {status_data['status']}")
        time.sleep(2)
```

### Getting video information

```python
import requests

api_key = "your_api_key_here"
base_url = "http://localhost:5000"

headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json"
}

# Start info task
data = {"url": "https://youtu.be/1FPdtR_5KFo"}
response = requests.post(f"{base_url}/get_info", json=data, headers=headers)
task_id = response.json()['task_id']

# Wait for completion and get info
time.sleep(2)
status_response = requests.get(f"{base_url}/status/{task_id}", headers=headers)
if status_response.json()['status'] == 'completed':
    info_url = base_url + status_response.json()['file']
    
    # Get full info
    info = requests.get(info_url, headers=headers).json()
    
    # Get only qualities
    qualities = requests.get(f"{info_url}?qualities", headers=headers).json()
    print(qualities)
```

## Supported Output Formats

### Video Formats
- **mp4** - MPEG-4 Part 14 (recommended)
- **mkv** - Matroska
- **webm** - WebM
- **avi** - Audio Video Interleave
- **mov** - QuickTime File Format
- **flv** - Flash Video
- **gif** - Graphics Interchange Format (animated, no audio, 480p15)

### Audio Formats
- **mp3** - MPEG Audio Layer III
- **m4a** - MPEG-4 Audio
- **opus** - Opus Audio
- **flac** - Free Lossless Audio Codec
- **wav** - Waveform Audio File Format
- **aac** - Advanced Audio Coding
- **ogg** - Ogg Vorbis

## Contributing

Contributions to yt-dlp-host are welcome! If you have any suggestions, bug reports, or feature requests, please open an issue on the [GitHub repository](https://github.com/Vasysik/yt-dlp-host). Pull requests are also encouraged.

## License

This project is licensed under the MIT License. See the LICENSE file for details.
