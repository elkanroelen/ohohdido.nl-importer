# Salesforce Account Import

A Python script that imports Salesforce account records from a JSONL file into a MySQL database with HMAC-hashed PII fields.

## Project Structure

```
scripts/
  import_records.py   # Main import script
  run_import.sh       # Entry point: starts MySQL, then runs the import
  start_mysql.sh      # Initializes and starts a local MySQL server
initdb/
  001-extra.sql       # Database schema (tables: accounts, account_emails, account_phones, search_logs, metadata)
requirements.txt      # Python dependencies: pymysql, tqdm, python-dotenv
```

## How It Works

1. `run_import.sh` starts a local MySQL server (if not already running) and applies the schema
2. `import_records.py` reads a JSONL file line by line, normalizes and HMAC-hashes PII fields, then upserts records into MySQL

## Required Secrets

| Secret | Description |
|--------|-------------|
| `DB_HOST` | MySQL host (127.0.0.1 for local) |
| `DB_PORT` | MySQL port (3306) |
| `DB_USER` | MySQL username |
| `DB_PASS` | MySQL password |
| `DB_NAME` | MySQL database name |
| `HASH_PEPPER` | Secret pepper for HMAC-SHA256 hashing of PII |
| `INPUT_PATH` | Full path to the JSONL input file |

## Running the Import

Use the **Run Import** workflow, or manually:

```bash
bash scripts/run_import.sh
```

## Database Tables

- `accounts` — main record table with hashed PII fields
- `account_emails` — normalized email hashes per account
- `account_phones` — normalized phone hashes per account
- `search_logs` — lookup audit trail
- `metadata` — key/value store (tracks `last_update`)
