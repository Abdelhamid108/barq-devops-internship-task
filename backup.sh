#!/usr/bin/env bash
set -euo pipefail

# Configuration with defaults
APP_URL="${APP_URL:-http://127.0.0.1:8080}"
POSTGRES_USER="${POSTGRES_USER:-barq_app}"
POSTGRES_DB="${POSTGRES_DB:-barq_tasks}"
BACKUP_DIR="${BACKUP_DIR:-backups}"

mkdir -p "$BACKUP_DIR"

create_record() {
  local title="$1"
  curl -sf -X POST "${APP_URL}/records" \
    -H 'Content-Type: application/json' \
    -d "{\"title\":\"${title}\"}" > /dev/null
}

check_record_exists() {
  local title="$1"
  curl -sf "${APP_URL}/records" | jq -e --arg t "$title" '.records[] | select(.title == $t)' > /dev/null 2>&1
}

create_sql_backup() {
  local backup_file="${1:-${BACKUP_DIR}/backup_$(date +%Y-%m-%d_%H-%M-%S).sql}"
  docker compose exec -T postgres pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" > "${backup_file}"
  echo "${backup_file}"
}

wait_for_ready() {
  local retries=30
  while [[ $retries -gt 0 ]]; do
    if curl -sf "${APP_URL}/ready" > /dev/null 2>&1; then
      return 0
    fi
    sleep 1
    ((retries--))
  done
  return 1
}

app_recreate() {
  docker compose down --remove-orphans >/dev/null 2>&1
  docker compose up -d >/dev/null 2>&1
  wait_for_ready
}

# --- Execution ---
main() {
  local test_title="backup-proof-$(date +%s)"

  echo "1. Creating proof record: '${test_title}'..."
  if ! create_record "${test_title}"; then
    echo "ERROR: Failed to create record." >&2
    exit 1
  fi
  

  echo "2. Verifying record exists before backup..."
  if ! check_record_exists "${test_title}"; then
    echo "ERROR: Failed to find created record." >&2
    exit 1
  fi

  echo "3. Taking PostgreSQL backup..."
  BACKUP_PATH=$(create_sql_backup)
  echo "Backup successfully saved to: ${BACKUP_PATH}"

  echo "4. Testing container recreation (volume retention)..."
  if ! app_recreate; then
    echo "ERROR: Failed to recreate container." >&2
    exit 1
  fi

  echo "5. Verifying record survived container recreation..."
  if check_record_exists "${test_title}"; then
    echo "SUCCESS: Record survived container recreation!"
  else
    echo "ERROR: Record lost after container recreation!" >&2
    exit 1
  fi
}

main "$@"
