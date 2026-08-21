# Testing and pre-push checklist

This document describes how to decide whether a refactor build is safe to push to the `test` branch and what additional checks should pass before merging it to production/main.

The goal is to test three separate layers:

1. code/state correctness in an isolated container;
2. real HTTP compatibility with existing clients;
3. real yt-dlp/ffmpeg behavior against public media.

Do not rely only on `docker compose up` returning success.

## Test levels

### Gate A — safe to push to `test`

Required:

- repository diff is clean from whitespace/secrets mistakes;
- full pytest suite passes inside the built image;
- Compose configuration validates;
- API and worker stay up without tracebacks;
- health endpoint reports expected backend and yt-dlp version;
- `get_info` works through the existing production client;
- `get_audio` or `get_video` produces a non-empty valid media file;
- JSON files remain valid after real requests when `STORAGE_BACKEND=json`;
- no new errors appear in API/worker logs.

### Gate B — safe to merge/deploy broadly

Additionally recommended:

- both audio and video output tested with ffprobe;
- byte-range request returns `206`;
- 4+ concurrent metadata tasks complete without corrupting JSON state;
- wrong/missing API key behavior checked;
- private/local URL rejection checked;
- protected `/status`/`/files` ownership behavior checked using two test keys when those protections will be enabled;
- live endpoint tested if production actually uses live downloads;
- restart/lease recovery tested in a disposable test instance;
- scheduler rebuild command tested once manually;
- old real client runs for a while without incompatibilities.

---

## 1. Inspect the Git diff before testing

```bash
cd /opt/yt-dlp-host

git status
git diff --check
git diff --stat
```

`git diff --check` should print nothing.

Make sure secrets/state are not about to be committed:

```bash
git status --short

git check-ignore .env || true
git check-ignore jsons/.yt-dlp-host-state.json || true
```

Inspect any tracked JSON before committing:

```bash
git diff -- jsons/api_keys.json jsons/tasks.json
```

Never push production API secrets in `jsons/api_keys.json`.

---

## 2. Validate Compose

```bash
docker compose config >/tmp/yt-dlp-host.compose.yml

echo 'compose config: OK'
docker compose config --services
```

Expected services:

```text
api
worker
scheduler
```

Check the active state backend:

```bash
docker compose config | grep -E 'STORAGE_BACKEND|LEGACY_KEYS_FILE|LEGACY_TASKS_FILE|JSON_STATE_FILE'
```

For live legacy JSON testing, expect `STORAGE_BACKEND: json`.

Check network membership if the reverse proxy depends on `yt-dlp-net`:

```bash
docker inspect yt-dlp-host-api-1 \
  --format '{{json .NetworkSettings.Networks}}' | jq
```

---

## 3. Run the full pytest suite in the actual built image

The production image intentionally does not include pytest. Run it in an ephemeral container so production files/volumes are not touched.

Get the built API image ID:

```bash
IMG=$(docker compose images -q api)
echo "$IMG"
```

Then:

```bash
docker run --rm \
  --user root \
  -e PYTHONPATH=/app/src \
  "$IMG" \
  sh -lc 'pip install --no-cache-dir pytest >/dev/null && pytest -q'
```

This container has no production bind mounts, so HTTP tests can initialize temporary/default state safely.

The suite covers, among other things:

- atomic queue claim;
- rolling request limiter;
- quota reservations;
- active-vs-finalized quota window behavior;
- SQLite backend;
- live JSON backend contract;
- existing legacy JSON shape;
- URL/path validation;
- established HTTP error/response shapes;
- protected status ownership on the same API routes;
- absence of the discarded versioned API namespace.

Any failing test is a stop condition before pushing.

---

## 4. Check running containers/logs

```bash
docker compose ps
```

`api` and `worker` should be `Up` and not restart-looping.

```bash
docker compose logs --since=10m api worker
```

Search for obvious failures:

```bash
docker compose logs --since=10m api worker 2>&1 \
  | grep -Ei 'traceback|permissionerror|exception|critical|worker failed to boot' \
  && echo 'ERRORS FOUND' \
  || echo 'no obvious fatal errors'
```

During debugging, keep the scheduler stopped:

```bash
docker compose stop scheduler
```

Enable it only after the manual checks pass.

---

## 5. Health check

From the host/public route:

```bash
curl -fsS "$BASE_URL/health" | jq
```

Expected shape:

```json
{
  "status": "ok",
  "version": "2.0.0",
  "yt_dlp_version": "...",
  "storage_backend": "json"
}
```

Verify:

- `status == ok`;
- `yt_dlp_version` is non-empty;
- `storage_backend` is the mode you intended to test.

---

## 6. Existing API compatibility smoke test

Set:

```bash
export BASE_URL='https://your-real-host'
export API_KEY='existing-api-key'
export TEST_URL='https://www.youtube.com/watch?v=...'
```

### Check existing key/permissions

If the key has `get_info`:

```bash
curl -fsS -X POST "$BASE_URL/check_permissions" \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"permissions":["get_info"]}' | jq
```

Expected:

```json
{"message":"Permissions granted"}
```

### Create `get_info`

```bash
CREATE=$(curl -fsS -X POST "$BASE_URL/get_info" \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d "{\"url\":\"$TEST_URL\"}")

echo "$CREATE" | jq
TASK_ID=$(echo "$CREATE" | jq -r .task_id)
```

Expected create shape:

```json
{
  "status": "waiting",
  "task_id": "..."
}
```

### Poll

```bash
while :; do
  BODY=$(curl -fsS "$BASE_URL/status/$TASK_ID")
  STATUS=$(echo "$BODY" | jq -r .status)
  echo "$BODY" | jq
  [[ "$STATUS" == completed || "$STATUS" == error ]] && break
  sleep 1
done
```

Require `completed`.

### Download/parse info.json

```bash
FILE=$(echo "$BODY" | jq -r .file)

curl -fsS "$BASE_URL$FILE?qualities&title&thumbnail&is_live&duration&language" \
  | jq . >/dev/null

echo 'legacy info/filtering: OK'
```

This specifically exercises old client behavior around `?qualities&...`.

---

## 7. Audio/media test

Use a short section so the test is cheap:

```bash
CREATE=$(curl -fsS -X POST "$BASE_URL/get_audio" \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d "{
    \"url\":\"$TEST_URL\",
    \"audio_format\":\"bestaudio\",
    \"output_format\":\"mp3\",
    \"start_time\":0,
    \"end_time\":15
  }")

TASK_ID=$(echo "$CREATE" | jq -r .task_id)
```

Poll as above, then:

```bash
TASK=$(curl -fsS "$BASE_URL/status/$TASK_ID")
FILE=$(echo "$TASK" | jq -r .file)

curl -f "$BASE_URL$FILE" -o /tmp/yt-dlp-host-test.mp3

test -s /tmp/yt-dlp-host-test.mp3
stat -c '%s bytes' /tmp/yt-dlp-host-test.mp3
```

A `200` access log alone is not enough; verify the output file is non-empty.

Validate the actual media from inside the worker image:

```bash
REL=${FILE#/files/}
docker compose exec -T worker \
  ffprobe -v error \
  -show_entries format=format_name,duration,size \
  -show_entries stream=codec_type,codec_name \
  -of json \
  "/app/downloads/$REL" | jq
```

Require a real audio stream and a sensible non-zero duration/size.

---

## 8. Video test

```bash
CREATE=$(curl -fsS -X POST "$BASE_URL/get_video" \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d "{
    \"url\":\"$TEST_URL\",
    \"video_format\":\"bestvideo[height<=720]\",
    \"audio_format\":\"bestaudio\",
    \"output_format\":\"mp4\",
    \"start_time\":0,
    \"end_time\":15
  }")

TASK_ID=$(echo "$CREATE" | jq -r .task_id)
```

Poll until complete, then inspect:

```bash
TASK=$(curl -fsS "$BASE_URL/status/$TASK_ID")
FILE=$(echo "$TASK" | jq -r .file)
REL=${FILE#/files/}

docker compose exec -T worker \
  ffprobe -v error \
  -show_entries format=format_name,duration,size \
  -show_entries stream=codec_type,codec_name,width,height \
  -of json \
  "/app/downloads/$REL" | jq
```

Require:

- a video stream;
- expected container/format;
- non-zero size;
- audio stream if the request included audio.

---

## 9. Byte-range test

Use a completed media URL:

```bash
curl -sS \
  -D /tmp/ytdlp-range.headers \
  -H 'Range: bytes=0-1023' \
  "$BASE_URL$FILE" \
  -o /tmp/ytdlp-range.bin

cat /tmp/ytdlp-range.headers
wc -c /tmp/ytdlp-range.bin
```

For a file larger than 1024 bytes, require:

```text
HTTP/... 206 PARTIAL CONTENT
Content-Range: bytes 0-1023/...
```

and 1024 output bytes.

---

## 10. Authentication/security smoke tests

### Missing API key

```bash
curl -sS -o /tmp/body -w '%{http_code}\n' \
  -X POST "$BASE_URL/get_info" \
  -H 'Content-Type: application/json' \
  -d "{\"url\":\"$TEST_URL\"}"
cat /tmp/body | jq
```

Require HTTP `401` and the established response shape:

```json
{
  "error": "No API key provided"
}
```

### SSRF/private URL rejection

```bash
curl -sS -o /tmp/body -w '%{http_code}\n' \
  -X POST "$BASE_URL/get_info" \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"url":"http://127.0.0.1:22"}'

cat /tmp/body | jq
```

With default `ALLOW_PRIVATE_URLS=false`, require HTTP `400`.

---

## 11. JSON-backend integrity test

When using:

```env
STORAGE_BACKEND=json
```

validate files before and after real requests:

```bash
python3 -m json.tool jsons/api_keys.json >/dev/null
python3 -m json.tool jsons/tasks.json >/dev/null
python3 -m json.tool jsons/.yt-dlp-host-state.json >/dev/null

echo 'JSON files valid'
```

Also check permissions/ownership on the host because the container runs as a non-root `app` user:

```bash
ls -ln jsons data downloads
```

The container UID/GID must be able to create the sidecar lock/state and task output files.

---

## 12. Concurrent JSON/queue test

Run four metadata creates concurrently using the same real key:

```bash
rm -f /tmp/ytdlp-task-*.json

for i in 1 2 3 4; do
  (
    curl -fsS -X POST "$BASE_URL/get_info" \
      -H "X-API-Key: $API_KEY" \
      -H 'Content-Type: application/json' \
      -d "{\"url\":\"$TEST_URL\"}" \
      > "/tmp/ytdlp-task-$i.json"
  ) &
done
wait

jq . /tmp/ytdlp-task-*.json
```

Collect IDs:

```bash
for f in /tmp/ytdlp-task-*.json; do
  id=$(jq -r .task_id "$f")
  echo "$id"
done
```

Poll all to completion, then validate `tasks.json` again.

This is a useful live check that API/worker file locking is not corrupting the legacy JSON backend under concurrent activity.

---

## 13. Protected status/file ownership test

By default `/status/<task_id>` and `/files/<path>` remain public for backward compatibility. If production will enable:

```env
LEGACY_PUBLIC_STATUS=false
LEGACY_PUBLIC_FILES=false
```

then test ownership on **those same routes** in a disposable/test instance. No second API namespace is involved.

Create two temporary keys (`A` and `B`) with `get_info`, create a task with key A, then request its status with key B:

```bash
curl -i \
  -H "X-API-Key: $KEY_B" \
  "$BASE_URL/status/$TASK_ID"
```

Expected for the wrong owner:

```http
HTTP/1.1 404 NOT FOUND
```

```json
{
  "status": "error",
  "message": "Task not found"
}
```

The owning key must receive `200`. A request without any key must receive `401` while the protection flag is disabled from public mode. Apply the same check to the completed file URL when `LEGACY_PUBLIC_FILES=false`.

Delete temporary keys afterwards.

---

## 14. Restart/lease recovery test

Do this in a disposable test instance, not casually during production traffic.

Recommended procedure:

1. set `WORKER_LEASE_SECONDS=30` in the test environment;
2. start a download long enough to remain `processing`;
3. stop/kill the worker container;
4. restart it;
5. wait longer than the lease;
6. verify the job is reclaimed and `attempts` increases.

The default lease is longer (`900` seconds), so changing it in a dedicated test environment makes recovery testing practical.

---

## 15. Scheduler test

Do not wait until 03:00 to learn the scheduler command is broken.

The scheduled production action is equivalent to:

```bash
cd /opt/yt-dlp-host

docker compose build --pull --no-cache api worker
docker compose up -d --force-recreate api worker
```

Run this once manually during a controlled maintenance/test window, then verify:

```bash
curl -fsS "$BASE_URL/health" | jq .yt_dlp_version
```

and confirm the containers remain healthy.

After all manual checks pass:

```bash
docker compose up -d scheduler
```

---

# Pre-push decision

A practical `test`-branch push gate:

```text
[ ] git diff --check clean
[ ] no .env / real API secrets staged
[ ] docker compose config passes
[ ] full pytest suite passes in isolated built image
[ ] api + worker stable (no restart loop)
[ ] health = ok, correct storage backend, yt-dlp version present
[ ] existing production client get_info works
[ ] existing production client audio/video result is actually non-empty
[ ] at least one result passes ffprobe
[ ] info.json ?qualities filtering works
[ ] JSON files still parse when STORAGE_BACKEND=json
[ ] recent logs contain no fatal traceback/errors
```

If all of those are true, pushing to the remote `test` branch is reasonable:

```bash
git status
git add <intended files>
git diff --cached --check
git diff --cached

git commit -m 'Modernize yt-dlp-host with backward compatibility'
git push origin test
```

Before merging `test` to `main`, also perform the stronger concurrent/range/protected-ownership/live/restart tests relevant to your production usage.
