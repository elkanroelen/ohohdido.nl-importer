import os
import sys
import io
import json
import re
import gzip
import subprocess
import hashlib
import hmac
import pymysql
from datetime import datetime
from dotenv import load_dotenv
from tqdm import tqdm

# =========================
# Load .env
# =========================

load_dotenv()

HASH_ENABLED = os.getenv("HASH_ENABLED", "true").lower() == "true"
HASH_PEPPER = os.getenv("HASH_PEPPER")

if HASH_ENABLED and not HASH_PEPPER:
    raise RuntimeError("HASH_PEPPER missing in .env")

HASH_KEY = HASH_PEPPER.encode() if HASH_PEPPER else None

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "port": int(os.getenv("DB_PORT")),
    "password": os.getenv("DB_PASS"),
    "database": os.getenv("DB_NAME"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

# =========================
# Hash helpers
# =========================

def hmac_hash(value: str) -> str:
    if not value:
        return None
    if not HASH_ENABLED:
        return value
    return hmac.new(HASH_KEY, value.encode(), hashlib.sha256).hexdigest()

def normalize_generic(v):
    return v.strip().lower() if v else None

def normalize_postcode(v):
    if not v:
        return None
    return re.sub(r"\s+", "", v).strip().lower()

def normalize_phone(v):
    if not v:
        return None
    return re.sub(r"\D", "", v)

def normalize_iban(v):
    if not v:
        return None
    return re.sub(r"\s+", "", v).strip().upper()

def normalize_date(value):
    if not value:
        return None
    value = str(value).strip()
    if value == "":
        return None
    return value

def normalize_address(postcode, house_number, house_ext):
    if not postcode or not house_number:
        return None
    pc = re.sub(r"\s+", "", postcode).upper()
    hn = str(house_number).strip()
    ext = str(house_ext).strip().lower() if house_ext else ""
    return f"{pc}{hn}{ext}".lower()

def normalize_name(name: str) -> str | None:
    if not name:
        return None

    # Verwijder (Inactive) of varianten
    name = re.sub(r"\(inactive\)", "", name, flags=re.IGNORECASE)

    # Trim dubbele spaties
    name = re.sub(r"\s+", " ", name).strip()

    # Split op eerste echte naamdeel
    parts = name.split(" ")
    if not parts:
        return None

    initials_part = parts[0]
    last_name = " ".join(parts[1:]).strip()

    # Pak alle letters uit initialen (K.M., K M, KM etc)
    letters = re.findall(r"[A-Za-z]", initials_part.upper())

    if not letters:
        return name.strip()

    # Maak correcte voorletters: K.M.
    normalized_initials = "".join([f"{l}." for l in letters])

    if last_name:
        return f"{normalized_initials} {last_name}"
    else:
        return normalized_initials

# =========================
# Contact parsing
# =========================

def parse_contacts(log_text):
    if not log_text:
        return 0, None, None, None

    pattern = r"(\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2})"
    matches = re.findall(pattern, log_text)

    dates = []
    for m in matches:
        try:
            dt = datetime.strptime(m, "%d-%m-%Y %H:%M:%S")
            dates.append(dt)
        except:
            continue

    if not dates:
        return 0, None, None, None

    dates.sort()
    return (
        len(dates),
        dates[0],
        dates[-1],
        json.dumps([d.isoformat() for d in dates])
    )

# =========================
# Email / phone getter
# =========================

EMAIL_RE = re.compile(r'(?i)\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b')
# Telefoon: +316..., 06..., 00316..., met rommel eromheen
PHONE_RE = re.compile(r'(?:(?:\+|00)\s?31\s?6|0\s?6)\s?(?:[\s\-]?\d){8}\b')

def extract_emails(text: str) -> list[str]:
    if not text:
        return []
    emails = EMAIL_RE.findall(text)
    # dedupe + normaliseer
    out = []
    seen = set()
    for e in emails:
        e2 = normalize_generic(e)
        if e2 and e2 not in seen:
            seen.add(e2)
            out.append(e2)
    return out

def extract_phones(text: str) -> list[str]:
    if not text:
        return []
    matches = PHONE_RE.findall(text)
    out = []
    seen = set()
    for m in matches:
        # m kan de hele match bevatten; normalize_phone haalt alle niet-digits weg
        p = normalize_phone(m)
        # maak NL mobiel consistent: 06xxxxxxxx -> 316xxxxxxxx, 00316 -> 316
        if p:
            if p.startswith("06") and len(p) == 10:
                p = "31" + p[1:]   # 06.. -> 316..
            if p.startswith("0031"):
                p = p[2:]          # 0031.. -> 31..
            if p.startswith("31") and len(p) >= 11:
                # ok
                pass
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out

def get_email_candidates(obj, log_text, flash_text):
    candidates = []
    # velden
    for v in [
        obj.get("Email"),
        obj.get("vlocity_cmt__BillingEmailAddress__c"),
    ]:
        if v:
            candidates.append(v)

    # tekstbronnen
    candidates += extract_emails(log_text)
    candidates += extract_emails(flash_text)

    # normalize + dedupe
    out, seen = [], set()
    for e in candidates:
        e2 = normalize_generic(e)
        if e2 and e2 not in seen:
            seen.add(e2)
            out.append(e2)
    return out


def get_phone_candidates(obj, log_text, flash_text):
    candidates = []
    if obj.get("Phone"):
        candidates.append(obj.get("Phone"))

    candidates += extract_phones(log_text)
    candidates += extract_phones(flash_text)

    out, seen = [], set()
    for p in candidates:
        p2 = normalize_phone(p)
        if not p2:
            continue

        # consistent NL mobiel
        if p2.startswith("06") and len(p2) == 10:
            p2 = "31" + p2[1:]
        if p2.startswith("0031"):
            p2 = p2[2:]

        if p2 not in seen:
            seen.add(p2)
            out.append(p2)
    return out

# =========================
# Import logic
# =========================

BATCH_SIZE = int(os.getenv("IMPORT_BATCH_SIZE", "2000"))
COMMIT_EVERY = int(os.getenv("IMPORT_COMMIT_EVERY", "10000"))

ACCOUNT_SQL = """
INSERT INTO accounts (
    sf_id,
    name, type, segment, status,
    is_active, is_deleted,
    email, iban, phone,
    billing_street, billing_city, billing_state,
    billing_postcode, billing_country,
    house_number, house_number_ext,
    billing_address_hash,
    last_activity_date, flash_message,
    contact_moment_count,
    contact_first_at,
    contact_last_at,
    contact_dates_json
) VALUES (
    %(sf_id)s,
    %(name)s, %(type)s, %(segment)s, %(status)s,
    %(is_active)s, %(is_deleted)s,
    %(email)s, %(iban)s, %(phone)s,
    %(billing_street)s, %(billing_city)s, %(billing_state)s,
    %(billing_postcode)s, %(billing_country)s,
    %(house_number)s, %(house_number_ext)s,
    %(billing_address_hash)s,
    %(last_activity_date)s, %(flash_message)s,
    %(contact_moment_count)s,
    %(contact_first_at)s,
    %(contact_last_at)s,
    %(contact_dates_json)s
)
ON DUPLICATE KEY UPDATE
  name = VALUES(name),
  type = VALUES(type),
  segment = VALUES(segment),
  status = VALUES(status),
  is_active = VALUES(is_active),
  is_deleted = VALUES(is_deleted),
  email = VALUES(email),
  iban = VALUES(iban),
  phone = VALUES(phone),
  billing_street = VALUES(billing_street),
  billing_city = VALUES(billing_city),
  billing_state = VALUES(billing_state),
  billing_postcode = VALUES(billing_postcode),
  billing_country = VALUES(billing_country),
  house_number = VALUES(house_number),
  house_number_ext = VALUES(house_number_ext),
  billing_address_hash = VALUES(billing_address_hash),
  last_activity_date = VALUES(last_activity_date),
  flash_message = VALUES(flash_message),
  contact_moment_count = VALUES(contact_moment_count),
  contact_first_at = VALUES(contact_first_at),
  contact_last_at = VALUES(contact_last_at),
  contact_dates_json = VALUES(contact_dates_json)
"""


def process_record(obj):
    log_text = obj.get("SObjectLog__c") or ""
    flash_text = obj.get("Flash_Message__c") or ""

    email_norms = get_email_candidates(obj, log_text, flash_text)
    phone_norms = get_phone_candidates(obj, log_text, flash_text)

    email_hashes = [hmac_hash(e) for e in email_norms]
    phone_hashes = [hmac_hash(p) for p in phone_norms]

    billing_postcode_raw = obj.get("BillingPostalCode")
    house_number_raw = obj.get("House_Number__c")
    house_number_ext_raw = obj.get("House_Number_Extension__c")

    contact_count, contact_first, contact_last, contact_json = parse_contacts(
        obj.get("SObjectLog__c")
    )

    row = {
        "sf_id": obj.get("Id"),
        "name": hmac_hash(normalize_name(obj.get("Name"))),
        "type": obj.get("Type"),
        "segment": obj.get("Segment__c") or obj.get("Segment"),
        "status": obj.get("vlocity_cmt__Status__c"),
        "is_active": 1 if obj.get("IsActive") == "true" else 0,
        "is_deleted": 1 if obj.get("IsDeleted") == "true" else 0,
        "email": email_hashes[0] if email_hashes else None,
        "iban": hmac_hash(normalize_iban(obj.get("Bank_Account_Number__c"))),
        "phone": phone_hashes[0] if phone_hashes else None,
        "billing_street": hmac_hash(normalize_generic(obj.get("BillingStreet"))),
        "billing_city": hmac_hash(normalize_generic(obj.get("BillingCity"))),
        "billing_state": hmac_hash(normalize_generic(obj.get("BillingState"))),
        "billing_postcode": hmac_hash(normalize_postcode(billing_postcode_raw)),
        "billing_country": hmac_hash(normalize_generic(obj.get("BillingCountry"))),
        "house_number": hmac_hash(normalize_generic(house_number_raw)),
        "house_number_ext": hmac_hash(normalize_generic(house_number_ext_raw)),
        "billing_address_hash": hmac_hash(normalize_address(
            billing_postcode_raw, house_number_raw, house_number_ext_raw
        )),
        "last_activity_date": normalize_date(obj.get("LastActivityDate")),
        "flash_message": obj.get("Flash_Message__c"),
        "contact_moment_count": contact_count,
        "contact_first_at": contact_first,
        "contact_last_at": contact_last,
        "contact_dates_json": contact_json,
    }
    return row, email_hashes, phone_hashes


def flush_batch(cursor, batch_rows, batch_emails, batch_phones):
    if not batch_rows:
        return

    cursor.executemany(ACCOUNT_SQL, batch_rows)

    sf_ids = [r["sf_id"] for r in batch_rows]
    placeholders = ",".join(["%s"] * len(sf_ids))
    cursor.execute(
        f"SELECT id, sf_id FROM accounts WHERE sf_id IN ({placeholders})",
        sf_ids
    )
    id_map = {row["sf_id"]: row["id"] for row in cursor.fetchall()}

    account_ids = list(id_map.values())
    if account_ids:
        id_placeholders = ",".join(["%s"] * len(account_ids))
        cursor.execute(f"DELETE FROM account_emails WHERE account_id IN ({id_placeholders})", account_ids)
        cursor.execute(f"DELETE FROM account_phones WHERE account_id IN ({id_placeholders})", account_ids)

    email_rows = []
    phone_rows = []
    for sf_id, hashes in batch_emails.items():
        acc_id = id_map.get(sf_id)
        if acc_id:
            email_rows.extend((acc_id, h) for h in hashes)
    for sf_id, hashes in batch_phones.items():
        acc_id = id_map.get(sf_id)
        if acc_id:
            phone_rows.extend((acc_id, h) for h in hashes)

    if email_rows:
        cursor.executemany(
            "INSERT IGNORE INTO account_emails (account_id, email_hash) VALUES (%s, %s)",
            email_rows
        )
    if phone_rows:
        cursor.executemany(
            "INSERT IGNORE INTO account_phones (account_id, phone_hash) VALUES (%s, %s)",
            phone_rows
        )


class _SevenZStream:
    """Streams a single-file 7z archive line by line without decompressing to disk."""
    def __init__(self, path):
        for cmd in (["7z", "e", "-so", path], ["7za", "e", "-so", path]):
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                self._wrapper = io.TextIOWrapper(self._proc.stdout, encoding="utf-8")
                return
            except FileNotFoundError:
                continue
        raise RuntimeError(
            "7z / 7za niet gevonden. Installeer p7zip:\n"
            "  Mac:   brew install p7zip\n"
            "  Linux: sudo apt install p7zip-full"
        )

    def __enter__(self):
        return self._wrapper

    def __exit__(self, *args):
        self._wrapper.close()
        self._proc.wait()


def open_input(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    if path.endswith(".7z"):
        return _SevenZStream(path)
    return open(path, "r", encoding="utf-8")


def import_file():
    path = os.getenv("INPUT_PATH")
    if not path:
        print("ERROR: INPUT_PATH not set.", file=sys.stderr)
        sys.exit(1)

    connection = pymysql.connect(**DB_CONFIG)
    total = 0
    since_commit = 0
    start_time = datetime.now()
    last_print_total = 0

    batch_rows = []
    batch_emails = {}
    batch_phones = {}

    with connection.cursor() as cursor:
        cursor.execute("SET SESSION foreign_key_checks = 0")
        cursor.execute("SET SESSION unique_checks = 0")

        is_tty = sys.stderr.isatty()

        with open_input(path) as f:
            progress = tqdm(f, unit=" rec", unit_scale=True, dynamic_ncols=True,
                            disable=not is_tty)
            for line in progress:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                row, email_hashes, phone_hashes = process_record(obj)

                batch_rows.append(row)
                if email_hashes:
                    batch_emails[row["sf_id"]] = email_hashes
                if phone_hashes:
                    batch_phones[row["sf_id"]] = phone_hashes

                if len(batch_rows) >= BATCH_SIZE:
                    flush_batch(cursor, batch_rows, batch_emails, batch_phones)
                    total += len(batch_rows)
                    since_commit += len(batch_rows)
                    batch_rows = []
                    batch_emails = {}
                    batch_phones = {}

                    if since_commit >= COMMIT_EVERY:
                        connection.commit()
                        since_commit = 0
                        if is_tty:
                            progress.set_postfix(committed=total)
                        else:
                            elapsed = (datetime.now() - start_time).total_seconds()
                            rate = total / elapsed if elapsed > 0 else 0
                            chunk = total - last_print_total
                            last_print_total = total
                            print(
                                f"  {total:>10,} rec  |  "
                                f"{rate:>8,.0f} rec/s  |  "
                                f"elapsed {int(elapsed//60)}m{int(elapsed%60):02d}s  |  "
                                f"+{chunk:,} deze batch",
                                flush=True
                            )

            if batch_rows:
                flush_batch(cursor, batch_rows, batch_emails, batch_phones)
                total += len(batch_rows)

        cursor.execute("SET SESSION foreign_key_checks = 1")
        cursor.execute("SET SESSION unique_checks = 1")

        elapsed_sec = (datetime.now() - start_time).total_seconds()
        rate = int(total / elapsed_sec) if elapsed_sec > 0 else 0

        cursor.execute("SELECT COUNT(*) AS n FROM accounts")
        n_accounts = (cursor.fetchone() or {}).get("n", 0)

        cursor.execute("SELECT COUNT(*) AS n FROM account_emails")
        n_emails = (cursor.fetchone() or {}).get("n", 0)

        cursor.execute("SELECT COUNT(*) AS n FROM account_phones")
        n_phones = (cursor.fetchone() or {}).get("n", 0)

        cursor.execute("SELECT COUNT(*) AS n FROM accounts WHERE is_active = 1")
        n_active = (cursor.fetchone() or {}).get("n", 0)

        cursor.execute("SELECT COUNT(*) AS n FROM accounts WHERE is_deleted = 1")
        n_deleted = (cursor.fetchone() or {}).get("n", 0)

        stats = [
            ("last_update",          str(datetime.now().date())),
            ("total_accounts",       str(n_accounts)),
            ("total_emails",         str(n_emails)),
            ("total_phones",         str(n_phones)),
            ("total_active",         str(n_active)),
            ("total_deleted",        str(n_deleted)),
            ("last_import_count",    str(total)),
            ("last_import_duration", f"{int(elapsed_sec//60)}m{int(elapsed_sec%60):02d}s"),
            ("last_import_rate",     f"{rate} rec/s"),
        ]

        cursor.executemany("""
            INSERT INTO metadata (`key`, value) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE value = VALUES(value)
        """, stats)

        connection.commit()

    connection.close()

    print(f"\nDONE. Total processed: {total}")
    print(f"  Duur:            {int(elapsed_sec//60)}m{int(elapsed_sec%60):02d}s")
    print(f"  Gemiddeld:       {rate:,} rec/s")
    print(f"  Totaal accounts: {n_accounts:,}")
    print(f"  Totaal emails:   {n_emails:,}")
    print(f"  Totaal telefoons:{n_phones:,}")
    print(f"  Actief:          {n_active:,}")
    print(f"  Verwijderd:      {n_deleted:,}")

if __name__ == "__main__":
    import_file()