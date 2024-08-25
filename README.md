# API Documentation

## Table of Contents

1. [Download Video (`/download`)](#download-video-download)
2. [Get Video Info (`/get_info`)](#get-video-info-get_info)
3. [Create API Key (`/create_key`)](#create-api-key-create_key)
4. [Delete API Key (`/delete_key/<name>`)](#delete-api-key-delete_keyname)
5. [List API Keys (`/list_keys`)](#list-api-keys-list_keys)
6. [Get Task Status (`/status/<task_id>`)](#get-task-status-statustask_id)
7. [Get File (`/files/<path:filename>`)](#get-file-filespathfilename)

## Download Video (`/download`)

**Description:**
This request is used to initiate a video download task from the specified URL.

**URL:**
```
POST /download
```

**Headers:**
```json
{
    "X-API-Key": "your_api_key",
    "Content-Type": "application/json"
}
```

**Request Body:**
```json
{
    "url": "https://youtu.be/sPX3bonQPT4?si=flh4-nW1MJK3TIjw",
    "format": "video",
    "quality": "1080p"
}
```

**Parameters:**
- `url` (required): The URL of the video to be downloaded.
- `format` (required): The format of the video (e.g., "video" or "audio").
- `quality` (optional): The quality of the video (e.g., "360p", "720p", "1080p"). Default is "360p".

**Permissions:**
- Requires the `download` permission.

## Get Video Info (`/get_info`)

**Description:**
This request is used to retrieve information about the video from the specified URL.

**URL:**
```
POST /get_info
```

**Headers:**
```json
{
    "X-API-Key": "your_api_key",
    "Content-Type": "application/json"
}
```

**Request Body:**
```json
{
    "url": "https://youtu.be/E2S5CmWyvsM?si=aD3RcOfSEfelIA_z"
}
```

**Parameters:**
- `url` (required): The URL of the video to retrieve information about.

**Permissions:**
- Requires the `get_info` permission.

## Create API Key (`/create_key`)

**Description:**
This request is used to create a new API key with the specified permissions.

**URL:**
```
POST /create_key
```

**Headers:**
```json
{
    "X-API-Key": "your_api_key",
    "Content-Type": "application/json"
}
```

**Request Body:**
```json
{
    "name": "key_name",
    "permissions": ["download", "get_info"]
}
```

**Parameters:**
- `name` (required): The name for the new API key.
- `permissions` (required): A list of permissions for the new API key.

**Permissions:**
- Requires the `admin` permission.

## Delete API Key (`/delete_key/<name>`)

**Description:**
This request is used to delete an existing API key by its name.

**URL:**
```
DELETE /delete_key/<name>
```

**Headers:**
```json
{
    "X-API-Key": "your_api_key",
    "Content-Type": "application/json"
}
```

**Parameters:**
- `name` (required): The name of the API key to be deleted.

**Permissions:**
- Requires the `admin` permission.

## List API Keys (`/list_keys`)

**Description:**
This request is used to retrieve a list of all existing API keys.

**URL:**
```
GET /list_keys
```

**Headers:**
```json
{
    "X-API-Key": "your_api_key",
    "Content-Type": "application/json"
}
```

**Permissions:**
- Requires the `admin` permission.

## Get Task Status (`/status/<task_id>`)

**Description:**
This request is used to retrieve the status of a specific task by its ID.

**URL:**
```
GET /status/<task_id>
```

**Headers:**
```json
{
    "X-API-Key": "your_api_key",
    "Content-Type": "application/json"
}
```

**Parameters:**
- `task_id` (required): The ID of the task to retrieve the status for.

**Permissions:**
- No specific permission required, but the task must be associated with the API key used.

## Get File (`/files/<path:filename>`)

**Description:**
This request is used to retrieve a file from the server.

**URL:**
```
GET /files/<path:filename>
```

**Headers:**
```json
{
    "X-API-Key": "your_api_key",
    "Content-Type": "application/json"
}
```

**Parameters:**
- `filename` (required): The name of the file to retrieve.

**Permissions:**
- No specific permission required, but the file must be associated with the API key used.

**Notes:**
- If the file ends with `info.json`, the response will include the video information.
- You can filter the response by adding query parameters. For example, `?qualities` will return a list of available video qualities.
