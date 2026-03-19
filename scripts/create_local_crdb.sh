#!/bin/bash
# Create a minimal Redis Enterprise CRDB on the local Docker cluster and
# print the resulting CRDB/BDB identifiers from the admin API.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SETUP_CLUSTER_SCRIPT="$SCRIPT_DIR/setup_redis_enterprise_cluster.sh"

NODE_CONTAINER="redis-enterprise-node1"
ADMIN_URL="https://localhost:9443"
ADMIN_USER="admin@redis.com"
ADMIN_PASSWORD="admin"
INSTANCE_FQDN="cluster.local"
CRDB_NAME="local-crdb"
CRDB_PORT="13000"
MEMORY_SIZE="32MB"
DELETE_DB_NAME=""
BOOTSTRAP_CLUSTER=0

usage() {
    cat <<'EOF'
Usage: scripts/create_local_crdb.sh [options]

Options:
  --name NAME              CRDB name to create (default: local-crdb)
  --port PORT              Database port to allocate (default: 13000)
  --memory-size SIZE       Memory size accepted by crdb-cli (default: 32MB)
  --delete-db NAME         Delete an existing local BDB before creating the CRDB
  --bootstrap-cluster      Run scripts/setup_redis_enterprise_cluster.sh first
  --help                   Show this help text

Examples:
  scripts/create_local_crdb.sh --name local-crdb-script --port 13001
  scripts/create_local_crdb.sh --bootstrap-cluster --delete-db test-db
EOF
}

log() {
    printf '==> %s\n' "$1"
}

die() {
    printf 'ERROR: %s\n' "$1" >&2
    exit 1
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

api() {
    local method="$1"
    local path="$2"
    shift 2

    curl -ksS -u "$ADMIN_USER:$ADMIN_PASSWORD" \
        -X "$method" \
        "$ADMIN_URL$path" \
        "$@"
}

wait_for_admin_api() {
    local attempts="${1:-30}"

    for ((i=1; i<=attempts; i++)); do
        if api GET /v1/cluster >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done

    return 1
}

get_bdb_uid_by_name() {
    local name="$1"

    api GET /v1/bdbs | jq -r --arg name "$name" '.[]? | select(.name == $name) | .uid' | head -n 1
}

get_crdb_json_by_name() {
    local name="$1"

    api GET /v1/crdbs | jq -c --arg name "$name" '
        (if type == "object" and has("crdbs") then .crdbs else . end)
        | [.[]? | select(.name == $name)][0]
    '
}

delete_bdb_by_name() {
    local name="$1"
    local uid

    uid="$(get_bdb_uid_by_name "$name")"
    if [ -z "$uid" ] || [ "$uid" = "null" ]; then
        log "No existing BDB named '$name' found"
        return 0
    fi

    log "Deleting BDB '$name' (uid=$uid)"
    api DELETE "/v1/bdbs/$uid" >/dev/null

    for ((i=1; i<=30; i++)); do
        uid="$(get_bdb_uid_by_name "$name")"
        if [ -z "$uid" ] || [ "$uid" = "null" ]; then
            log "Deleted BDB '$name'"
            return 0
        fi
        sleep 2
    done

    die "Timed out waiting for BDB '$name' to be deleted"
}

wait_for_task() {
    local task_id="$1"
    local status_output=""

    for ((i=1; i<=60; i++)); do
        status_output="$(
            docker exec "$NODE_CONTAINER" /opt/redislabs/bin/crdb-cli \
                --cluster-url "$ADMIN_URL" \
                --cluster-username "$ADMIN_USER" \
                --cluster-password "$ADMIN_PASSWORD" \
                task status --task-id "$task_id" 2>&1 || true
        )"

        if printf '%s\n' "$status_output" | grep -q '^Status: finished$'; then
            return 0
        fi

        if printf '%s\n' "$status_output" | grep -q '^Status: failed$'; then
            printf '%s\n' "$status_output" >&2
            die "CRDB task $task_id failed"
        fi

        sleep 2
    done

    printf '%s\n' "$status_output" >&2
    die "Timed out waiting for CRDB task $task_id"
}

print_summary() {
    local crdb_json="$1"
    local bdb_uid
    local bdb_json

    bdb_uid="$(printf '%s\n' "$crdb_json" | jq -r '.local_databases[0].bdb_uid // .instances[0].db_uid // empty')"
    [ -n "$bdb_uid" ] || die "Could not determine BDB uid from CRDB response"

    bdb_json="$(api GET "/v1/bdbs/$bdb_uid")"

    jq -n \
        --argjson crdb "$crdb_json" \
        --argjson bdb "$bdb_json" \
        '{
            crdb_guid: $crdb.guid,
            crdb_name: $crdb.name,
            crdb_instance_fqdn: ($crdb.instances[0].cluster.name // $crdb.instances[0].cluster_fqdn // ""),
            bdb_uid: $bdb.uid,
            bdb_name: $bdb.name,
            bdb_status: $bdb.status,
            bdb_port: $bdb.port,
            bdb_crdt: $bdb.crdt,
            bdb_crdt_guid: $bdb.crdt_guid
        }'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --name)
            CRDB_NAME="$2"
            shift 2
            ;;
        --port)
            CRDB_PORT="$2"
            shift 2
            ;;
        --memory-size)
            MEMORY_SIZE="$2"
            shift 2
            ;;
        --delete-db)
            DELETE_DB_NAME="$2"
            shift 2
            ;;
        --bootstrap-cluster)
            BOOTSTRAP_CLUSTER=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            usage >&2
            die "Unknown argument: $1"
            ;;
    esac
done

require_cmd docker
require_cmd curl
require_cmd jq

if [ "$BOOTSTRAP_CLUSTER" -eq 1 ]; then
    log "Bootstrapping local Redis Enterprise cluster"
    bash "$SETUP_CLUSTER_SCRIPT"
fi

wait_for_admin_api || die "Redis Enterprise admin API is not reachable at $ADMIN_URL"
docker exec "$NODE_CONTAINER" /opt/redislabs/bin/crdb-cli --help >/dev/null 2>&1 || \
    die "crdb-cli is not available in $NODE_CONTAINER"

existing_crdb_json="$(get_crdb_json_by_name "$CRDB_NAME")"
if [ -n "$existing_crdb_json" ] && [ "$existing_crdb_json" != "null" ]; then
    log "CRDB '$CRDB_NAME' already exists"
    print_summary "$existing_crdb_json"
    exit 0
fi

if [ -n "$DELETE_DB_NAME" ]; then
    delete_bdb_by_name "$DELETE_DB_NAME"
fi

log "Creating CRDB '$CRDB_NAME' on port $CRDB_PORT"
set +e
create_output="$(
    docker exec "$NODE_CONTAINER" /opt/redislabs/bin/crdb-cli \
        --cluster-url "$ADMIN_URL" \
        --cluster-username "$ADMIN_USER" \
        --cluster-password "$ADMIN_PASSWORD" \
        crdb create \
        --name "$CRDB_NAME" \
        --memory-size "$MEMORY_SIZE" \
        --port "$CRDB_PORT" \
        --sharding false \
        --replication false \
        --instance "fqdn=$INSTANCE_FQDN,username=$ADMIN_USER,password=$ADMIN_PASSWORD" \
        --no-wait 2>&1
)"
create_status=$?
set -e
if [ "$create_status" -ne 0 ]; then
    printf '%s\n' "$create_output" >&2
    die "crdb-cli create failed"
fi
printf '%s\n' "$create_output"

task_id="$(printf '%s\n' "$create_output" | grep -Eo '[0-9a-fA-F-]{36}' | head -n 1)"
[ -n "$task_id" ] || die "Could not parse task ID from crdb-cli output"

wait_for_task "$task_id"

crdb_json="$(get_crdb_json_by_name "$CRDB_NAME")"
[ "$crdb_json" != "null" ] || die "CRDB '$CRDB_NAME' was created but not found via /v1/crdbs"

print_summary "$crdb_json"
