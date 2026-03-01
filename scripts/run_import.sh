#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Starting local MySQL ==="
bash "$SCRIPT_DIR/start_mysql.sh"

echo ""
echo "=== Running import ==="
python "$SCRIPT_DIR/import_records.py"
