#!/usr/bin/env bash
set -euo pipefail

# Configuration
CONTAINER_NAME=${CONTAINER_NAME:-postgres}
POSTGRES_USER=${POSTGRES_USER:-barq_app}
POSTGRES_DB=${POSTGRES_DB:-barq_tasks}
BACKUP_DIR=${BACKUP_DIR:-backups}
BACKUP_FILE="${1:-$(ls -t ${BACKUP_DIR}/*.sql 2>/dev/null | head -1)}"

delete_existing_database(){
   if ! docker compose exec -T ${CONTAINER_NAME} psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} \
        -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null 2>&1; then
        echo "ERROR: Failed to delete existing database."
        exit 1
    fi
}
restore_database(){
    if ! docker compose exec -T ${CONTAINER_NAME} psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} < ${BACKUP_FILE} >/dev/null 2>&1; then
        echo "ERROR: Failed to restore database."
        exit 1
    fi
    
}
check_record_exists(){
  local APP_URL="${APP_URL:-http://localhost:8080}"
  local count
  count=$(curl -sf "${APP_URL}/records" | jq '.records | length')
  if [[ "${count}" -eq 0 ]]; then
    echo "ERROR: No records found after restore." >&2
    exit 1
  fi
}

main(){
    echo "Deleting existing data..."
    delete_existing_database
    echo "Database cleared successfully."

    echo "Restoring from: ${BACKUP_FILE}..."
    restore_database
    echo "Database restored successfully."

    echo "Verifying records after restore..."
    check_record_exists
    echo "Record found successfully."

    echo "SUCCESS: Data restored from backup!"
    echo "OVERALL: RESTORE TEST PASSED"
}
main
