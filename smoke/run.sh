#!/usr/bin/env bash
# Installs the built wheel the way a customer would and runs the quickstart
# against a local stand-in for api.blujay.io. No real API key is used.
# Usage: smoke/run.sh <python executable>
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
python="${1:-python3}"
work="$(mktemp -d)"
"$python" -m venv "$work/venv"
"$work/venv/bin/pip" install --quiet "$(ls "$repo"/dist/*.whl)"
node "$repo/smoke/mock-server.mjs" "$work/requests.log" & mock=$!
trap 'kill $mock' EXIT
sleep 1
export BLUJAY_API_KEY=blu_test BLUJAY_BASE_URL=http://127.0.0.1:4010
out="$("$work/venv/bin/python" "$repo/smoke/quickstart.py")"
echo "$out"
grep -q "chat: chat_3" <<<"$out"
grep -q "flaky chat after retry: chat_flaky" <<<"$out"
grep -q "send failed: 503 QUEUE_UNAVAILABLE" <<<"$out"
grep -q "error message: 503 QUEUE_UNAVAILABLE: Sending is paused for a moment. Try again shortly. (trace_id trc_mock)" <<<"$out"
grep -q "edit failed: 503" <<<"$out"
grep -q "pages: 2" <<<"$out"
grep -q "error class: UnauthorizedError" <<<"$out"
grep -q "error class: TooManyRequestsError" <<<"$out"
# Writes are never retried: the send (and, in TypeScript, the client.fetch() send) once each, the edit once.
test "$(grep -c '"key":"POST /v1/chats/chat_down/messages"' "$work/requests.log")" = 1
test "$(grep -c '"key":"PATCH /v1/messages/msg_down"' "$work/requests.log")" = 1
test "$(grep -c '"key":"GET /v1/chats/chat_flaky"' "$work/requests.log")" = 2
grep -q '"key":"POST /v1/chats/chat_abc123/messages".*"idem":"[^"]' "$work/requests.log"
echo "smoke: ok"
