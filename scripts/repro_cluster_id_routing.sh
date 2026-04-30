#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_ROOT="${OUT_ROOT:-$REPO_ROOT/tmp/cluster_id_routing}"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
RUN_DIR="$OUT_ROOT/$RUN_ID"

AGENT_REDIS_PORT="${AGENT_REDIS_PORT:-7853}"
API_PORT="${API_PORT:-18080}"
RE_ADMIN_URL="${RE_ADMIN_URL:-https://localhost:9443}"
RE_ADMIN_USERNAME="${RE_ADMIN_USERNAME:-admin@redis.com}"
RE_ADMIN_PASSWORD="${RE_ADMIN_PASSWORD:-admin}"
CLI_QUERY="${CLI_QUERY:-What nodes are in this cluster?}"
API_QUERY="${API_QUERY:-What nodes are in this cluster?}"
API_DIAGNOSTIC_QUERY="${API_DIAGNOSTIC_QUERY:-What is the memory usage across this cluster?}"

mkdir -p "$RUN_DIR"

API_LOG="$RUN_DIR/api.log"
WORKER_LOG="$RUN_DIR/worker.log"
CLI_OUTPUT="$RUN_DIR/cli-query.txt"
TASK_SIMPLE_JSON="$RUN_DIR/task-simple.json"
TASK_DIAGNOSTIC_JSON="$RUN_DIR/task-diagnostic.json"
SUMMARY_TXT="$RUN_DIR/summary.txt"

REDIS_CONTAINER="sre3-cluster-routing-redis-$RUN_ID"
API_PID=""
WORKER_PID=""
CLUSTER_ID=""

log() {
  printf '[cluster-id-repro] %s\n' "$*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

cleanup() {
  set +e
  if [[ -n "$WORKER_PID" ]]; then
    kill "$WORKER_PID" >/dev/null 2>&1 || true
    wait "$WORKER_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "$API_PID" ]]; then
    kill "$API_PID" >/dev/null 2>&1 || true
    wait "$API_PID" >/dev/null 2>&1 || true
  fi
  docker rm -f "$REDIS_CONTAINER" >/dev/null 2>&1 || true
}

trap cleanup EXIT

wait_for_http() {
  local url="$1"
  local name="$2"
  local attempts="${3:-60}"
  for ((i=1; i<=attempts; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      log "$name is ready: $url"
      return 0
    fi
    sleep 1
  done
  echo "$name did not become ready: $url" >&2
  exit 1
}

create_cluster_config() {
  local output
  output="$(
    REDIS_URL="redis://localhost:${AGENT_REDIS_PORT}/0" \
      "$REPO_ROOT/.venv/bin/redis-sre-agent" cluster create \
      --name "Local Redis Enterprise Cluster $RUN_ID" \
      --cluster-type redis_enterprise \
      --environment test \
      --description "Local Redis Enterprise cluster for cluster-id routing repro ($RUN_ID)" \
      --admin-url "$RE_ADMIN_URL" \
      --admin-username "$RE_ADMIN_USERNAME" \
      --admin-password "$RE_ADMIN_PASSWORD" \
      --json
  )"

  python3 - <<'PY' "$output"
import json, sys
payload = json.loads(sys.argv[1])
if "error" in payload:
    raise SystemExit(payload["error"])
print(payload["id"])
PY
}

create_task() {
  local query="$1"
  local escaped_query
  escaped_query="$(python3 - <<'PY' "$query"
import json, sys
print(json.dumps(sys.argv[1]))
PY
)"
  local task_json
  task_json="$(
    curl -fsS -X POST "http://127.0.0.1:${API_PORT}/api/v1/tasks" \
      -H 'Content-Type: application/json' \
      -d "{\"message\":${escaped_query},\"context\":{\"cluster_id\":\"${CLUSTER_ID}\"}}"
  )"

  python3 - <<'PY' "$task_json"
import json, sys
payload = json.loads(sys.argv[1])
print(payload["task_id"])
PY
}

wait_for_task_terminal_state() {
  local task_id="$1"
  local destination="$2"
  local attempts="${3:-90}"

  for ((i=1; i<=attempts; i++)); do
    curl -fsS "http://127.0.0.1:${API_PORT}/api/v1/tasks/${task_id}" > "$destination"
    local status
    status="$(python3 - <<'PY' "$destination"
import json, pathlib, sys
payload = json.loads(pathlib.Path(sys.argv[1]).read_text())
print(payload["status"])
PY
)"
    if [[ "$status" == "done" || "$status" == "failed" ]]; then
      log "Task ${task_id} reached terminal state: ${status}"
      return 0
    fi
    sleep 2
  done

  log "Task ${task_id} did not reach terminal state; preserving latest snapshot"
  return 0
}

require_cmd docker
require_cmd curl
require_cmd python3

if [[ ! -x "$REPO_ROOT/.venv/bin/redis-sre-agent" ]]; then
  echo "Expected CLI at $REPO_ROOT/.venv/bin/redis-sre-agent" >&2
  exit 1
fi

log "Bootstrapping Redis Enterprise cluster via included setup script"
if ! (cd "$REPO_ROOT" && ./scripts/setup_redis_enterprise_cluster.sh); then
  if ! curl -ksf -u "${RE_ADMIN_USERNAME}:${RE_ADMIN_PASSWORD}" "${RE_ADMIN_URL}/v1/cluster" >/dev/null; then
    echo "Redis Enterprise bootstrap failed and admin API is not reachable at ${RE_ADMIN_URL}" >&2
    exit 1
  fi
  log "Continuing because cluster admin API is reachable despite setup script returning non-zero"
fi

if lsof -iTCP:"$AGENT_REDIS_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port ${AGENT_REDIS_PORT} is already in use; choose another with AGENT_REDIS_PORT=..." >&2
  exit 1
fi

if lsof -iTCP:"$API_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port ${API_PORT} is already in use; choose another with API_PORT=..." >&2
  exit 1
fi

if lsof -iTCP:9101 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port 9101 is already in use; stop the existing worker metrics server before running this script." >&2
  exit 1
fi

log "Starting disposable operational Redis on localhost:${AGENT_REDIS_PORT}"
docker run -d --name "$REDIS_CONTAINER" -p "${AGENT_REDIS_PORT}:6379" redis:8.2.1 >/dev/null

log "Starting local API on localhost:${API_PORT}"
(
  cd "$REPO_ROOT"
  REDIS_URL="redis://localhost:${AGENT_REDIS_PORT}/0" \
    .venv/bin/uvicorn redis_sre_agent.api.app:app --host 127.0.0.1 --port "$API_PORT" \
    >"$API_LOG" 2>&1
) &
API_PID="$!"

log "Starting local worker"
(
  cd "$REPO_ROOT"
  REDIS_URL="redis://localhost:${AGENT_REDIS_PORT}/0" \
    .venv/bin/redis-sre-agent worker start \
    >"$WORKER_LOG" 2>&1
) &
WORKER_PID="$!"

wait_for_http "http://127.0.0.1:${API_PORT}/api/v1/health" "API"

log "Creating RedisCluster config against ${RE_ADMIN_URL}"
CLUSTER_ID="$(create_cluster_config)"
log "Created cluster: ${CLUSTER_ID}"

log "Running CLI query with --redis-cluster-id"
(
  cd "$REPO_ROOT"
  REDIS_URL="redis://localhost:${AGENT_REDIS_PORT}/0" \
    .venv/bin/redis-sre-agent query --redis-cluster-id "$CLUSTER_ID" "$CLI_QUERY"
) >"$CLI_OUTPUT" 2>&1

log "Running API task query with context.cluster_id"
SIMPLE_TASK_ID="$(create_task "$API_QUERY")"
wait_for_task_terminal_state "$SIMPLE_TASK_ID" "$TASK_SIMPLE_JSON"

log "Running contrast API task query with DB-diagnostic wording"
DIAGNOSTIC_TASK_ID="$(create_task "$API_DIAGNOSTIC_QUERY")"
wait_for_task_terminal_state "$DIAGNOSTIC_TASK_ID" "$TASK_DIAGNOSTIC_JSON" 30

{
  echo "run_dir=$RUN_DIR"
  echo "cluster_id=$CLUSTER_ID"
  echo "simple_task_id=$SIMPLE_TASK_ID"
  echo "diagnostic_task_id=$DIAGNOSTIC_TASK_ID"
  echo
  echo "[cli-output]"
  sed -n '1,160p' "$CLI_OUTPUT"
  echo
  echo "[simple-task-result]"
  cat "$TASK_SIMPLE_JSON"
  echo
  echo "[diagnostic-task-result]"
  cat "$TASK_DIAGNOSTIC_JSON"
  echo
  echo "[worker-routing-snippets]"
  rg -n \
    "Using cluster_id from client|LLM categorized query as REDIS_CHAT|Auto-upgrading cluster-scoped diagnostic query to REDIS_TRIAGE|Routing query to|No redis_instance provided - loading only instance-independent providers|Processing query with Redis cluster context" \
    "$WORKER_LOG" || true
} >"$SUMMARY_TXT"

log "Repro complete"
log "Artifacts:"
log "  summary: $SUMMARY_TXT"
log "  worker log: $WORKER_LOG"
log "  api log: $API_LOG"
log "  cli output: $CLI_OUTPUT"
