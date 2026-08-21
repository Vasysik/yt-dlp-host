#!/usr/bin/env bash
set -euo pipefail

: "${BASE_URL:?Set BASE_URL, e.g. https://download.example.com}"
: "${API_KEY:?Set API_KEY to an existing key with get_info permission}"
: "${TEST_URL:?Set TEST_URL to a public media URL}"

BASE_URL="${BASE_URL%/}"
POLL_SECONDS="${POLL_SECONDS:-1}"
POLL_LIMIT="${POLL_LIMIT:-180}"
RUN_AUDIO="${RUN_AUDIO:-0}"

for cmd in curl jq; do
  command -v "$cmd" >/dev/null || { echo "missing dependency: $cmd" >&2; exit 2; }
done

poll_task() {
  local task_id=$1 body status i
  for ((i=0; i<POLL_LIMIT; i++)); do
    body=$(curl -fsS "$BASE_URL/status/$task_id")
    status=$(jq -r .status <<<"$body")
    printf 'task %s: %s\n' "$task_id" "$status" >&2
    case "$status" in
      completed) printf '%s' "$body"; return 0 ;;
      error) jq . <<<"$body" >&2; return 1 ;;
    esac
    sleep "$POLL_SECONDS"
  done
  echo "timeout waiting for task $task_id" >&2
  return 1
}

TMP_BODY=$(mktemp)
trap 'rm -f "$TMP_BODY" "${TMP_AUDIO:-}" /tmp/yt-dlp-host-range.bin' EXIT

echo '== health =='
HEALTH=$(curl -fsS "$BASE_URL/health")
jq . <<<"$HEALTH"
test "$(jq -r .status <<<"$HEALTH")" = ok
test -n "$(jq -r .yt_dlp_version <<<"$HEALTH")"
test -n "$(jq -r .storage_backend <<<"$HEALTH")"

echo '== missing-key compatibility =='
CODE=$(curl -sS -o "$TMP_BODY" -w '%{http_code}' \
  -X POST "$BASE_URL/get_info" \
  -H 'Content-Type: application/json' \
  -d "{\"url\":$(jq -Rn --arg v "$TEST_URL" '$v')}")
test "$CODE" = 401
test "$(jq -r .error "$TMP_BODY")" = 'No API key provided'
echo 'missing-key response OK'

echo '== permissions =='
curl -fsS -X POST "$BASE_URL/check_permissions" \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"permissions":["get_info"]}' | jq .

echo '== get_info =='
CREATE=$(curl -fsS -X POST "$BASE_URL/get_info" \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d "{\"url\":$(jq -Rn --arg v "$TEST_URL" '$v')}")
TASK_ID=$(jq -r .task_id <<<"$CREATE")
test -n "$TASK_ID" && test "$TASK_ID" != null
TASK=$(poll_task "$TASK_ID")
FILE=$(jq -r .file <<<"$TASK")
test -n "$FILE" && test "$FILE" != null
curl -fsS "$BASE_URL$FILE?qualities&title&thumbnail&is_live&duration&language" | jq . >/dev/null
echo "get_info OK: $TASK_ID"

echo '== private URL guard =='
CODE=$(curl -sS -o "$TMP_BODY" -w '%{http_code}' \
  -X POST "$BASE_URL/get_info" \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"url":"http://127.0.0.1:22"}')
if [[ "$CODE" == 400 ]]; then
  echo 'private URL guard OK'
else
  echo "WARNING: expected 400 from private URL guard, got $CODE (ALLOW_PRIVATE_URLS may be enabled)" >&2
fi

if [[ "$RUN_AUDIO" == 1 ]]; then
  echo '== short MP3 =='
  CREATE=$(curl -fsS -X POST "$BASE_URL/get_audio" \
    -H "X-API-Key: $API_KEY" \
    -H 'Content-Type: application/json' \
    -d "{\"url\":$(jq -Rn --arg v "$TEST_URL" '$v'),\"audio_format\":\"bestaudio\",\"output_format\":\"mp3\",\"start_time\":0,\"end_time\":15}")
  AUDIO_ID=$(jq -r .task_id <<<"$CREATE")
  AUDIO_TASK=$(poll_task "$AUDIO_ID")
  AUDIO_FILE=$(jq -r .file <<<"$AUDIO_TASK")
  TMP_AUDIO=$(mktemp --suffix=.mp3)
  curl -fsS "$BASE_URL$AUDIO_FILE" -o "$TMP_AUDIO"
  test -s "$TMP_AUDIO"
  echo "audio bytes: $(stat -c %s "$TMP_AUDIO")"

  RANGE_CODE=$(curl -sS -o /tmp/yt-dlp-host-range.bin -w '%{http_code}' \
    -H 'Range: bytes=0-1023' "$BASE_URL$AUDIO_FILE")
  test "$RANGE_CODE" = 206
  test "$(stat -c %s /tmp/yt-dlp-host-range.bin)" = 1024
  echo 'audio + range OK'
fi

echo '== smoke test PASSED =='
