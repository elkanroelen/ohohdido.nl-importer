#!/usr/bin/env bash
set -e

MYSQL_SOCKET="/tmp/mysql.sock"

echo "Waiting for MySQL to be available..."
for i in $(seq 1 30); do
    if mysqladmin --socket="$MYSQL_SOCKET" ping --silent 2>/dev/null; then
        echo "MySQL is up."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: MySQL did not become available. Start the MySQL Server workflow first."
        exit 1
    fi
    sleep 1
done

echo "Running import..."
python "$(dirname "$0")/import_records.py"
