#!/bin/bash
# Trigger a Redis Enterprise rebalance action for a database
# Usage: ./scripts/trigger_rebalance.sh [DB_NAME] [--dry-run] [--only-failovers]
# Defaults: DB_NAME=test-db, not dry-run, not only-failovers

set -euo pipefail

DB_NAME="${1:-test-db}"
DRY_RUN="false"
ONLY_FAILOVERS="false"

# Parse flags
for arg in "$@"; do
  case "$arg" in
    --dry-run)
      DRY_RUN="true" ;;
    --only-failovers)
      ONLY_FAILOVERS="true" ;;
  esac
done

BASE_URL="https://localhost:9443"
AUTH="admin@redis.com:admin"

# Resolve DB UID using rladmin (preferred on macOS/BSD sed environments)
DB_UID=""
DB_UID=$(docker exec redis-enterprise-node1 rladmin status databases 2>/dev/null | awk -v db="$DB_NAME" '$0 ~ db {print $1}' | sed 's/db://')

# Fallback to REST (jq if available; otherwise a sed pattern without non-greedy tokens)
if ! [[ "$DB_UID" =~ ^[0-9]+$ ]]; then
  RAW=$(curl -k -s -u "$AUTH" "$BASE_URL/v1/bdbs")
  if command -v jq >/dev/null 2>&1; then
    DB_UID=$(echo "$RAW" | jq -r ".[] | select(.name==\"$DB_NAME\") | .uid")
  else
    DB_UID=$(printf "%s" "$RAW" | tr -d '\n' | sed -E "s/.*\"name\":\"${DB_NAME//\//\\/}\"[^}]*\"uid\":([0-9]+).*/\1/")
  fi
fi

if ! [[ "$DB_UID" =~ ^[0-9]+$ ]]; then
  echo "\e[31mFailed to resolve UID for database '$DB_NAME'\e[0m"
  exit 1
fi

echo "[34mTriggering rebalance for DB '$DB_NAME' (uid=$DB_UID) ...[0m"

PARAMS=()
if [ "$DRY_RUN" = "true" ]; then PARAMS+=("dry_run=true"); fi
if [ "$ONLY_FAILOVERS" = "true" ]; then PARAMS+=("only_failovers=true"); fi
QS=""
if [ ${#PARAMS[@]} -gt 0 ]; then QS="?$(IFS='&'; echo "${PARAMS[*]}")"; fi

RESP=$(curl -k -s -u "$AUTH" -X PUT "$BASE_URL/v1/bdbs/$DB_UID/actions/rebalance$QS")

if [ "$DRY_RUN" = "true" ]; then
  echo "[33mDry-run blueprint returned:[0m"
  echo "$RESP" | sed -E 's/},{/},\n{/g' | head -n 50
  exit 0
fi

ACTION_UID=$(echo "$RESP" | sed -E 's/.*"action_uid"\s*:\s*"([^"]+)".*/\1/')
if [ -z "$ACTION_UID" ] || [ "$ACTION_UID" = "$RESP" ]; then
  echo "No action_uid found in response: $RESP"
  exit 1
fi

echo "[32mAccepted. action_uid=$ACTION_UID[0m"

echo "Polling action status (10 attempts):"
for i in {1..10}; do
  STATUS=$(curl -k -s -u "$AUTH" "$BASE_URL/v1/actions/$ACTION_UID")
  echo "[$i] $STATUS" | head -n 5
  # Stop early if obviously complete
  if echo "$STATUS" | grep -qi 'completed\|finished\|success'; then
    break
  fi
  sleep 3
done
