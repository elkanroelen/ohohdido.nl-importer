# Salesforce Account Import

A Python script that imports Salesforce account records from a JSONL file into a MySQL database with HMAC-hashed PII fields.

## Project Structure

```
scripts/
  import_records.py   # Main import script (batch-optimized)
  run_import.sh       # Entry point: waits for MySQL, then runs the import
  mysql_server.sh     # Initializes and keeps a local MySQL server running
initdb/
  001-extra.sql       # Database schema (tables: accounts, account_emails, account_phones, search_logs, metadata)
requirements.txt      # Python dependencies: pymysql, tqdm, python-dotenv
```

## How It Works

1. **MySQL Server** workflow keeps a local MySQL instance running persistently
2. **Run Import** workflow waits for MySQL to be ready, then runs the import
3. `import_records.py` reads a JSONL (or .gz) file in batches of 2000, normalizes and HMAC-hashes PII fields, then upserts records into MySQL

## Required Secrets

| Secret | Description |
|--------|-------------|
| `DB_HOST` | MySQL host (127.0.0.1 for local) |
| `DB_PORT` | MySQL port (3306) |
| `DB_USER` | MySQL username |
| `DB_PASS` | MySQL password |
| `DB_NAME` | MySQL database name |
| `HASH_PEPPER` | Secret pepper for HMAC-SHA256 hashing of PII |
| `INPUT_PATH` | Full path to the JSONL or .gz input file |

## Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `IMPORT_BATCH_SIZE` | 2000 | Records per batch insert |
| `IMPORT_COMMIT_EVERY` | 10000 | Records between MySQL commits |
| `HASH_ENABLED` | true | Set to false to store PII unhashed |

## Running the Import

Start **MySQL Server** workflow first, then run **Run Import**. Or manually:

```bash
bash scripts/run_import.sh
```

Supports both plain `.jsonl` and gzipped `.jsonl.gz` files via `INPUT_PATH`.

## Performance

- Batch inserts (2000 records/batch) instead of row-by-row
- FK + unique checks disabled during import for speed
- Commits every 10,000 records
- tqdm progress bar showing records/second
- Gzip files read directly without decompression step

## Database Tables

- `accounts` — main record table with hashed PII fields
- `account_emails` — normalized email hashes per account
- `account_phones` — normalized phone hashes per account
- `search_logs` — lookup audit trail
- `metadata` — key/value store (tracks `last_update`)
