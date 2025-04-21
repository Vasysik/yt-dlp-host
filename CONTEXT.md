# YouTube Clipping Service - Context

**Last Updated:** 2024-08-23

## 1. Project Goal & Status
- High-level objective: Provide an API service to download full YouTube videos/audio, specific clips, live streams, and retrieve video metadata using `yt-dlp`.
- Current Phase: Development/Operational
- Key Stakeholders: [Unknown - Please fill in]
- Next Major Milestone: [Unknown - Please fill in]

## 2. Core Architecture
- Frontend: None detected. This appears to be a backend-only service.
- Backend: Flask (v3.0.3), Python 3.9, `yt-dlp` (v2024.8.6). Uses JSON files for task queue (`jsons/tasks.json`) and API key storage (`jsons/api_keys.json`).
- LLM Integration: None detected.
- Deployment Environment (if any): Docker (`docker-compose.yml`, `Dockerfile`). Runs on host port 5001.

## 3. Key File Structure Overview
- `/src`: Main Python application code
  - `server.py`: Flask application, API endpoints definition.
  - `yt_handler.py`: Logic for interacting with `yt-dlp`.
  - `auth.py`: API key generation and validation logic.
  - `json_utils.py`: Utilities for reading/writing JSON files (tasks, API keys).
- `/jsons`: Storage for runtime data
  - `tasks.json`: Stores details and status of submitted download/info tasks.
  - `api_keys.json`: Stores generated API keys and their permissions.
- `/downloads`: Default directory for downloaded media files.
- `config.py`: Configuration settings (e.g., `DOWNLOAD_DIR`).
- `requirements.txt`: Python dependencies (`Flask`, `yt-dlp`).
- `Dockerfile`: Defines the Docker image for the service.
- `docker-compose.yml`: Defines the Docker service configuration.
- `CONTEXT.md`: This file!
- `README.md`: Project description and usage (likely).
- `cookies_fix_TODO.md`: Notes regarding cookie handling.
- `youtube_cookies.txt`: Potentially used by `yt-dlp` for accessing private content.

## 4. Common Commands & Setup
- **Docker (Recommended):**
  - Build: `docker compose build`
  - Run: `docker compose up` (runs in foreground, use `-d` for detached)
- **Local (Requires Python 3.9, ffmpeg, and manual dependency installation):**
  - Install dependencies: `pip install -r requirements.txt` (ideally in a virtual environment)
  - Run: `export FLASK_APP=src/server:app && flask run --host=0.0.0.0 --port=5001`
- **API Key Management:**
  - Requires an initial "master" key with `create_key` permission (see `auth.py` or `jsons/api_keys.json`).
  - Use the `/create_key` endpoint to generate new keys.

## 5. Key Dependencies & Gotchas
- Requires `ffmpeg` to be installed in the environment (handled by `Dockerfile`).
- API access is controlled by keys stored in `jsons/api_keys.json`. An initial key might need manual setup or there might be a default one (check `auth.py`).
- Uses `yt-dlp` for all YouTube interactions. Ensure it's up-to-date if issues arise (`pip install --upgrade yt-dlp`).
- Download/clipping tasks are asynchronous. Submit a task via API, get a `task_id`, and poll the `/status/<task_id>` endpoint. Results (file paths or info) are provided in the status response upon completion.
- Check `config.py` for configurable paths like the download directory.
- Cookie handling (`youtube_cookies.txt`, `cookies_fix_TODO.md`) might be relevant for accessing age-restricted or private content.
