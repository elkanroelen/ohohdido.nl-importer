#!/usr/bin/env bash
set -e

MYSQL_DATA_DIR="/home/runner/mysql_data"
MYSQL_SOCKET="/tmp/mysql.sock"
MYSQL_LOG="/tmp/mysql_error.log"

if mysqladmin --socket="$MYSQL_SOCKET" ping --silent 2>/dev/null; then
    echo "MySQL already running."
    exit 0
fi

if [ ! -d "$MYSQL_DATA_DIR" ]; then
    echo "Initializing MySQL data directory..."
    mysqld --initialize-insecure --datadir="$MYSQL_DATA_DIR" 2>>"$MYSQL_LOG"
    echo "Initialized."
fi

echo "Starting MySQL..."
mysqld \
    --datadir="$MYSQL_DATA_DIR" \
    --socket="$MYSQL_SOCKET" \
    --pid-file=/tmp/mysql.pid \
    --port=3306 \
    --bind-address=127.0.0.1 \
    --mysqlx=OFF \
    --log-error="$MYSQL_LOG" \
    --daemonize=ON

for i in $(seq 1 30); do
    if mysqladmin --socket="$MYSQL_SOCKET" ping --silent 2>/dev/null; then
        echo "MySQL is up."
        break
    fi
    sleep 1
done

echo "Ensuring database and user..."
mysql --socket="$MYSQL_SOCKET" -u root <<SQL
CREATE DATABASE IF NOT EXISTS ${DB_NAME:-import_db} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER:-importer}'@'localhost' IDENTIFIED WITH mysql_native_password BY '${DB_PASS:-importpass}';
GRANT ALL PRIVILEGES ON ${DB_NAME:-import_db}.* TO '${DB_USER:-importer}'@'localhost';
FLUSH PRIVILEGES;
SQL

SCHEMA_FILE="$(dirname "$0")/../initdb/001-extra.sql"
if [ -f "$SCHEMA_FILE" ]; then
    echo "Applying schema..."
    mysql --socket="$MYSQL_SOCKET" -u root "${DB_NAME:-import_db}" < "$SCHEMA_FILE"
    echo "Schema applied."
fi

echo "MySQL setup complete."
