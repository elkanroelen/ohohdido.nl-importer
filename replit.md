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

## Draaien via Docker op de server (aanbevolen voor grote imports)

De import draait het snelst als de container op dezelfde server staat als MySQL (geen netwerk-latency). De container blijft ook draaien als de SSH-verbinding wegvalt.

Geen custom image bouwen nodig — gebruik de standaard `python:3.12` image:

```bash
# 1. Clone de repo op de server
git clone https://github.com/elkanroelen/ohohdido.nl-importer.git
cd ohohdido.nl-importer

# 2. Maak een .env bestand (zie .env.example)
cp .env.example .env
nano .env   # vul je echte waarden in

# 3. Start de import (installeert deps automatisch, draait in achtergrond)
docker run -d --rm \
  --name import_run \
  --network=host \
  --env-file .env \
  -v $(pwd):/app \
  -v /pad/naar/data:/data \
  -w /app \
  python:3.12 \
  bash -c "apt-get update -qq && apt-get install -y -qq p7zip-full && pip install -q -r requirements.txt && python scripts/import_records.py"

# 4. Voortgang volgen (ook vanuit een nieuwe SSH-sessie)
docker logs -f import_run

# 5. Klaar? Container opruimen
docker rm import_run
```

> **Let op `--network=host`:** als MySQL op `127.0.0.1` staat op de server, zorg dan dat `DB_HOST=127.0.0.1` in je `.env` staat en gebruik `--network=host`. Draait MySQL op een andere host? Dan `--network=host` weglaten en de echte IP gebruiken.

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
