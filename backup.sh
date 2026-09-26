#!/usr/bin/env bash
set -euo pipefail

# Configuration with defaults
if [[ -f ".env" ]]; then
  PUBLIC_PORT="${PUBLIC_PORT:-$(grep -E '^PUBLIC_PORT=' .env | cut -d '=' -f2 | tr -d ' "\r')}"
fi
APP_URL="${APP_URL:-http://127.0.0.1:${PUBLIC_PORT:-8080}}"
PROJECT_NAME="${PROJECT_NAME:-barq-assessment}"
CONTAINER_NAME="${CONTAINER_NAME:-postgres}"
POSTGRES_USER="${POSTGRES_USER:-barq_app}"
POSTGRES_DB="${POSTGRES_DB:-barq_tasks}"
BACKUP_DIR="${BACKUP_DIR:-backups}"

mkdir -p "${BACKUP_DIR}"

create_record() {
  curl -sf -X POST "${APP_URL}/records" \
    -H 'Content-Type: application/json' \
    -d "{\"title\":\"$1\"}" > /dev/null
}

check_record_exists() {
  curl -sf "${APP_URL}/records" | jq -e --arg t "$1" '.records[] | select(.title == $t)' > /dev/null 2>&1
}

create_sql_backup() {
  docker compose -p "${PROJECT_NAME}" exec -T "${CONTAINER_NAME}" pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" > "$1"
  echo "$1"
}

wait_for_ready() {
  retries=30
  while [[ $retries -gt 0 ]]; do
    if curl -sf "${APP_URL}/ready" > /dev/null 2>&1; then
      return 0
    fi
    sleep 1
    ((retries--))
  done
  return 1
}

recreate_containers() {
  docker compose -p "${PROJECT_NAME}" down --remove-orphans >/dev/null 2>&1
  docker compose -p "${PROJECT_NAME}" up -d >/dev/null 2>&1
  wait_for_ready
}

# --- Execution ---
main() {
  title="${1:-backup-proof}"
  backup_file="${2:-${BACKUP_DIR}/backup_$(date +%Y-%m-%d_%H-%M-%S).sql}"

  echo "1. Creating proof record: '${title}'..."
  if ! create_record "${title}"; then
    echo "ERROR: Failed to create record." >&2
    exit 1
  fi

  echo "2. Verifying record exists before backup..."
  if ! check_record_exists "${title}"; then
    echo "ERROR: Failed to find created record." >&2
    exit 1
  fi

  echo "3. Taking PostgreSQL backup..."
  backup_path=$(create_sql_backup "${backup_file}")
  echo "Backup successfully saved to: ${backup_path}"

  echo "4. Testing container recreation (volume retention)..."
  if ! recreate_containers; then
    echo "ERROR: Failed to recreate containers." >&2
    exit 1
  fi

  echo "5. Verifying record survived container recreation..."
  if check_record_exists "${title}"; then
    echo "SUCCESS: Record '${title}' survived container recreation!"
    echo "OVERALL: BACKUP & VOLUME PERSISTENCE TEST PASSED"
  else
    echo "ERROR: Record lost after container recreation!" >&2
    exit 1
  fi
}

main "$@"
