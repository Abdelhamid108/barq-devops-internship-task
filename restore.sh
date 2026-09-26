#!/usr/bin/env bash
set -euo pipefail

# Configuration with defaults
APP_URL="${APP_URL:-http://127.0.0.1:${PUBLIC_PORT:-8080}}"
PROJECT_NAME="${PROJECT_NAME:-barq-assessment}"
CONTAINER_NAME="${CONTAINER_NAME:-postgres}"
POSTGRES_USER="${POSTGRES_USER:-barq_app}"
POSTGRES_DB="${POSTGRES_DB:-barq_tasks}"
BACKUP_DIR="${BACKUP_DIR:-backups}"

delete_existing_database() {
  if ! docker compose -p "${PROJECT_NAME}" exec -T "${CONTAINER_NAME}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
       -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null 2>&1; then
    echo "ERROR: Failed to clear database schema." >&2
    exit 1
  fi
}

restore_database() {
  if ! docker compose -p "${PROJECT_NAME}" exec -T "${CONTAINER_NAME}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" < "$1" >/dev/null 2>&1; then
    echo "ERROR: Failed to restore database from $1." >&2
    exit 1
  fi
}

check_record_exists() {
  curl -sf "${APP_URL}/records" | jq -e --arg t "$1" '.records[] | select(.title == $t)' > /dev/null 2>&1
}

# --- Execution ---
main() {
  backup_file="${1:-$(ls -t "${BACKUP_DIR}"/*.sql 2>/dev/null | head -1)}"
  expected_title="${2:-backup-proof}"

  if [[ -z "${backup_file}" || ! -f "${backup_file}" ]]; then
    echo "ERROR: No valid backup file found to restore." >&2
    exit 1
  fi

  echo "1. Deleting existing database data..."
  delete_existing_database
  echo "Database cleared successfully."

  echo "2. Restoring from: ${backup_file}..."
  restore_database "${backup_file}"
  echo "Database restored successfully."

  echo "3. Verifying record '${expected_title}' after restore..."
  if check_record_exists "${expected_title}"; then
    echo "Record '${expected_title}' verified successfully!"
    echo "SUCCESS: Data restored from backup!"
    echo "OVERALL: RESTORE TEST PASSED"
  else
    echo "ERROR: Expected record '${expected_title}' not found after restore." >&2
    exit 1
  fi
}

main "$@"
