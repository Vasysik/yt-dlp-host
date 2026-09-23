#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

command -v python3 >/dev/null || { echo "Install python3 and python3-venv first." >&2; exit 1; }
command -v ffmpeg >/dev/null || { echo "Install ffmpeg first." >&2; exit 1; }

if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install --upgrade --pre 'yt-dlp[default]'

if [[ -f .env ]]; then
    set -a
    source .env
    set +a
fi

mkdir -p data downloads jsons cookies
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
export DOWNLOAD_DIR="${DOWNLOAD_DIR:-$PWD/downloads}"
export DATABASE_PATH="${DATABASE_PATH:-$PWD/data/yt-dlp-host.sqlite3}"
export LEGACY_KEYS_FILE="${LEGACY_KEYS_FILE:-$PWD/jsons/api_keys.json}"
export LEGACY_TASKS_FILE="${LEGACY_TASKS_FILE:-$PWD/jsons/tasks.json}"
export JSON_STATE_FILE="${JSON_STATE_FILE:-$PWD/jsons/.yt-dlp-host-state.json}"

if ! command -v deno >/dev/null; then
    echo "Warning: Deno is recommended for YouTube extraction." >&2
fi

worker_pid=''
api_pid=''
cleanup() {
    trap - EXIT INT TERM
    [[ -z "$api_pid" ]] || kill "$api_pid" 2>/dev/null || true
    [[ -z "$worker_pid" ]] || kill "$worker_pid" 2>/dev/null || true
    [[ -z "$api_pid" ]] || wait "$api_pid" 2>/dev/null || true
    [[ -z "$worker_pid" ]] || wait "$worker_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

.venv/bin/python -m yt_dlp_host.worker &
worker_pid=$!
.venv/bin/gunicorn -c gunicorn.conf.py src.server:app &
api_pid=$!
echo "API: http://localhost:${PORT:-5000}"

set +e
wait -n "$worker_pid" "$api_pid"
status=$?
set -e
exit "$status"
