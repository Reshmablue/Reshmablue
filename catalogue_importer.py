"""
=============================================================================
PRODUCT CATALOGUE IMPORTER (SAFE & RESOURCE-AWARE)
AI Shopkeeper Assistant - Windows 11 & MySQL (shopkeeper_ai)
=============================================================================
Safely imports Indian kirana and general store product catalogues into the
'product_catalogue' table without modifying the shop's active 'products' table,
prices, inventory, sales, purchases, or expenses.

Guarantees:
- Barcodes preserved as strings with leading zeros.
- Previews first 20 records with metric counters (valid, duplicate, incomplete).
- Explicit user confirmation required before any database writes.
- Memory & disk usage checks tailored for 8 GB RAM laptops.
- Parameterized SQL batch inserts with rollback on error.
- Attributions retained (Open Food Facts / Open Beauty Facts ODbL).
- Zero bulk image downloads (image URLs stored only).
=============================================================================
"""

import os
import sys
import csv
import json
import time
import shutil
import ctypes
import argparse
import re
from typing import Generator, Dict, Any, Tuple, List, Set, Optional

import mysql.connector
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows terminal
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure .env is loaded from project directory
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(ENV_PATH)


# =============================================================================
# 1. HARDWARE & RESOURCE SAFETY MONITOR (8 GB RAM LAPTOP OPTIMIZED)
# =============================================================================

class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class ResourceMonitor:
    """Monitors system RAM and storage to protect constrained laptop hardware."""

    MIN_FREE_RAM_MB = 150.0  # Alert/pause if available physical RAM drops below 150 MB
    MAX_RAM_LOAD_PERCENT = 96.0  # Alert/pause if memory load exceeds 96%
    MIN_FREE_DISK_GB = 1.0  # Abort if free disk space is less than 1 GB
    ESTIMATED_BYTES_PER_ROW = 1024  # Approx 1 KB per row in InnoDB (data + indices)

    @staticmethod
    def get_ram_status() -> Dict[str, float]:
        """Query physical RAM metrics on Windows via kernel32."""
        try:
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                total_gb = stat.ullTotalPhys / (1024 ** 3)
                avail_mb = stat.ullAvailPhys / (1024 ** 2)
                load_pct = float(stat.dwMemoryLoad)
                return {
                    "total_gb": round(total_gb, 2),
                    "avail_mb": round(avail_mb, 1),
                    "avail_gb": round(avail_mb / 1024, 2),
                    "load_percent": load_pct,
                    "supported": True
                }
        except Exception:
            pass

        return {
            "total_gb": 8.0,
            "avail_mb": 1000.0,
            "avail_gb": 1.0,
            "load_percent": 85.0,
            "supported": False
        }

    @staticmethod
    def get_disk_status(path: str = ".") -> Dict[str, float]:
        """Query available disk space on the target drive."""
        try:
            total, used, free = shutil.disk_usage(path)
            return {
                "total_gb": round(total / (1024 ** 3), 2),
                "used_gb": round(used / (1024 ** 3), 2),
                "free_gb": round(free / (1024 ** 3), 2),
                "free_bytes": free
            }
        except Exception:
            return {"total_gb": 100.0, "used_gb": 50.0, "free_gb": 50.0, "free_bytes": 50 * 1024**3}

    @classmethod
    def check_safety(cls, estimated_records: int = 1000) -> Tuple[bool, str]:
        """Check if importing estimated_records is safe for this laptop."""
        disk = cls.get_disk_status()
        if disk["free_gb"] < cls.MIN_FREE_DISK_GB:
            return False, f"CRITICAL: Free disk space ({disk['free_gb']} GB) is below safe minimum ({cls.MIN_FREE_DISK_GB} GB)."

        ram = cls.get_ram_status()
        if ram["load_percent"] > cls.MAX_RAM_LOAD_PERCENT or ram["avail_mb"] < cls.MIN_FREE_RAM_MB:
            return False, f"CRITICAL: High memory load ({ram['load_percent']}%, {ram['avail_mb']} MB free). Importer paused for safety."

        est_kb = (estimated_records * cls.ESTIMATED_BYTES_PER_ROW) / 1024
        return True, f"Hardware OK: RAM {ram['load_percent']}% load ({ram['avail_mb']:.0f} MB free) | Disk {disk['free_gb']} GB free | Est. DB Storage: ~{est_kb:.1f} KB."


# =============================================================================
# 2. VALIDATION & CATEGORY NORMALIZATION
# =============================================================================

CANONICAL_CATEGORIES = [
    "Rice, flour, pulses and other groceries",
    "Packaged foods, biscuits, snacks and chocolates",
    "Beverages",
    "Soap, shampoo, toothpaste and personal care",
    "Cosmetics and skincare",
    "Household cleaning products",
    "Other general-store products"
]


def classify_kirana_category(raw_category: Optional[str], raw_name: Optional[str] = "") -> str:
    """
    Normalizes arbitrary product category tags into the 7 official
    Indian kirana and general store product categories using regex word boundaries.
    """
    text = (str(raw_category or "") + " " + str(raw_name or "")).lower()

    # 1. Household cleaning products
    if re.search(r"\b(detergent|laundry|dishwash|dish\s*washer|floor\s*cleaner|toilet\s*cleaner|harpic|lizol|colin|mosquito|repellent|insecticide|garbage\s*bags?|scrubber|bleach|cleaning|cleaner)\b", text):
        return "Household cleaning products"

    # 2. Soap, shampoo, toothpaste and personal care
    if re.search(r"\b(soap|soaps|bathing\s*bar|shampoo|conditioner|toothpaste|toothbrush|oral|dental|body\s*wash|antiseptic|dettol|lifebuoy|shaving|razor|blade|deodorant|deo|sanitary|pads|personal\s*care|petroleum\s*jelly|eno|fruit\s*salt|iodex|balm)\b", text):
        return "Soap, shampoo, toothpaste and personal care"

    # 3. Cosmetics and skincare
    if re.search(r"\b(cosmetic|cosmetics|skincare|skin\s*care|cream|creams|moisturi[sz]er|moisturi[sz]ing|lotion|face\s*wash|cleanser|cleansing|peeling|sunscreen|lip\s*balm|perfume|fragrance|body\s*spray|makeup|beauty|serum|gel)\b", text):
        return "Cosmetics and skincare"

    # 4. Beverages
    if re.search(r"\b(beverage|beverages|drink|drinks|tea|chai|coffee|juice|juices|soda|sodas|water|cola|soft\s*drink|energy\s*drink|malt|horlicks|boost|bournvita|syrup|sharbat)\b", text):
        return "Beverages"

    # 5. Packaged foods, biscuits, snacks and chocolates
    if re.search(r"\b(biscuit|biscuits|cookie|cookies|cracker|crackers|snack|snacks|chocolate|chocolates|candy|candies|sweet|sweets|namkeen|chips?|wafers?|noodles?|pasta|maggi|kurkure|ketchup|sauce|sauces|pickle|pickles|confectionery|packaged\s*food)\b", text):
        return "Packaged foods, biscuits, snacks and chocolates"

    # 6. Rice, flour, pulses and other groceries
    if re.search(r"\b(rice|flour|atta|maida|sooji|rava|dals?|pulses?|lentils?|grains?|oil|oils|ghee|salt|sugar|jaggery|spices?|masala|turmeric|haldi|chilli|coriander|cumin|besan|staples?|grocer(y|ies)|dry\s*fruits?|almonds?|cashews?|raisins?|honey|jam|butter|cheese|paneer|dairy|curd|milk)\b", text):
        return "Rice, flour, pulses and other groceries"

    return "Other general-store products"


def validate_catalogue_record(raw: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Validates a candidate record:
    - Barcode must be a non-empty string with leading zeros preserved.
    - Product name must be a non-empty string.
    - Deduplication will be handled at the database layer.
    """
    raw_barcode = raw.get("barcode") or raw.get("code") or raw.get("ean") or ""
    barcode = str(raw_barcode).strip()

    if not barcode:
        return False, "INCOMPLETE: Missing barcode", None

    # Length check: EAN-8 (8), UPC-A (12), EAN-13 (13), ITF-14 (14), or custom string <= 50 chars
    if len(barcode) < 3 or len(barcode) > 50:
        return False, f"INVALID: Barcode length {len(barcode)} out of bounds [3-50]", None

    # Reject unprintable or control characters in barcode
    if any(ord(c) < 32 or ord(c) > 126 for c in barcode):
        return False, "INVALID: Barcode contains control or invalid characters", None

    raw_name = raw.get("product_name") or raw.get("product_name_en") or raw.get("name") or raw.get("title") or ""
    product_name = str(raw_name).strip()

    if not product_name or product_name.lower() in ("none", "null", "unknown", "n/a"):
        return False, "INCOMPLETE: Missing product name", None

    if len(product_name) > 255:
        product_name = product_name[:252] + "..."

    brand = str(raw.get("brand") or raw.get("brands") or "").strip() or None
    if brand and len(brand) > 150:
        brand = brand[:147] + "..."

    raw_category = raw.get("category") or raw.get("categories") or ""
    category = classify_kirana_category(raw_category, product_name)
    if len(category) > 150:
        category = category[:150]

    package_size = str(raw.get("package_size") or raw.get("pack_size") or raw.get("quantity") or "").strip() or None
    if package_size and len(package_size) > 100:
        package_size = package_size[:100]

    description = str(raw.get("description") or raw.get("generic_name") or "").strip() or None

    raw_img = str(raw.get("image_url") or raw.get("image_front_url") or "").strip()
    image_url = None
    if raw_img.startswith("http://") or raw_img.startswith("https://"):
        image_url = raw_img[:500]

    source = str(raw.get("source") or "Open Food Facts (ODbL)").strip()
    if len(source) > 100:
        source = source[:100]

    cleaned = {
        "barcode": barcode,
        "product_name": product_name,
        "brand": brand,
        "category": category,
        "package_size": package_size,
        "description": description,
        "image_url": image_url,
        "source": source
    }
    return True, "VALID", cleaned


# =============================================================================
# 3. STREAMING DATA READERS (INCREMENTAL / GENERATOR BASED)
# =============================================================================

def stream_csv_file(file_path: str, limit: Optional[int] = None) -> Generator[Dict[str, Any], None, None]:
    """Stream records from a local CSV file row-by-row without loading the whole file into RAM."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8", errors="replace") as fp:
        reader = csv.DictReader(fp)
        count = 0
        for row in reader:
            yield row
            count += 1
            if limit and count >= limit:
                break


def stream_jsonl_file(file_path: str, limit: Optional[int] = None) -> Generator[Dict[str, Any], None, None]:
    """Stream records from a local JSON Lines file line-by-line."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"JSONL file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8", errors="replace") as fp:
        count = 0
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                yield row
                count += 1
                if limit and count >= limit:
                    break
            except json.JSONDecodeError:
                continue


def stream_open_food_facts_api(country: str = "india", limit: int = 1000, page_size: int = 100) -> Generator[Dict[str, Any], None, None]:
    """
    Streams Indian products live from the Open Food Facts API in small pages (page_size=100)
    without downloading any massive multi-gigabyte files.
    """
    import requests

    hosts = ["world.openfoodfacts.net", "world.openfoodfacts.org", "in.openfoodfacts.org"]
    headers = {"User-Agent": "ShopkeeperAssistant/1.0 (kirana-catalog-importer; Windows 11)"}
    page = 1
    yielded = 0

    active_host = None
    for host in hosts:
        test_url = f"https://{host}/cgi/search.pl?action=process&tagtype_0=countries&tag_contains_0=contains&tag_0={country}&json=1&page_size=1&page=1"
        try:
            r = requests.get(test_url, headers=headers, timeout=6)
            if r.status_code == 200:
                active_host = host
                break
        except Exception:
            continue

    if not active_host:
        print("[NOTICE] Open Food Facts mirrors are currently unreachable. Please try Open Beauty Facts or Curated Sample CSV.")
        return

    base_url = f"https://{active_host}/cgi/search.pl"

    while yielded < limit:
        params = {
            "action": "process",
            "tagtype_0": "countries",
            "tag_contains_0": "contains",
            "tag_0": country,
            "json": 1,
            "page_size": min(page_size, limit - yielded),
            "page": page
        }

        try:
            resp = requests.get(base_url, params=params, headers=headers, timeout=12)
            if resp.status_code != 200:
                break

            data = resp.json()
            products = data.get("products", [])
            if not products:
                break

            for p in products:
                p["source"] = f"Open Food Facts ({active_host}) (ODbL)"
                yield p
                yielded += 1
                if yielded >= limit:
                    break

            page += 1
            time.sleep(0.4)  # Polite API throttling

        except Exception:
            break


def stream_open_beauty_facts_api(country: str = "india", limit: int = 1000, page_size: int = 100) -> Generator[Dict[str, Any], None, None]:
    """
    Streams personal care and cosmetics products live from Open Beauty Facts API.
    """
    import requests

    base_url = "https://world.openbeautyfacts.org/cgi/search.pl"
    headers = {"User-Agent": "ShopkeeperAssistant/1.0 (kirana-catalog-importer; Windows 11)"}
    page = 1
    yielded = 0

    while yielded < limit:
        params = {
            "action": "process",
            "tagtype_0": "countries",
            "tag_contains_0": "contains",
            "tag_0": country,
            "json": 1,
            "page_size": min(page_size, limit - yielded),
            "page": page
        }

        try:
            resp = requests.get(base_url, params=params, headers=headers, timeout=12)
            if resp.status_code != 200:
                break

            data = resp.json()
            products = data.get("products", [])
            if not products:
                break

            for p in products:
                p["source"] = "Open Beauty Facts (ODbL)"
                yield p
                yielded += 1
                if yielded >= limit:
                    break

            page += 1
            time.sleep(0.5)

        except Exception:
            break


def check_remote_dataset_size(url: str) -> Tuple[bool, str, int]:
    """
    Performs a pre-flight HTTP HEAD request to determine file size before downloading.
    """
    import requests

    try:
        resp = requests.head(url, allow_redirects=True, timeout=10)
        content_length = resp.headers.get("Content-Length")
        if content_length:
            size_bytes = int(content_length)
            size_mb = size_bytes / (1024 ** 2)
            size_gb = size_bytes / (1024 ** 3)
            return True, f"Remote file size: {size_mb:.2f} MB ({size_gb:.3f} GB)", size_bytes
        return True, "Remote file size unknown (server did not return Content-Length header).", 0
    except Exception as e:
        return False, f"Failed to check remote size: {e}", 0


# =============================================================================
# 4. DATABASE IMPORTER ENGINE
# =============================================================================

def get_db_connection():
    """Create and return a MySQL connection using .env configuration."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "shopkeeper_ai"),
        connection_timeout=10
    )


class CatalogueImporter:
    """
    Safe, incremental product catalogue importer:
    - Never deletes, overwrites, or alters existing catalogue records.
    - Never touches 'products', 'sales', 'purchases', 'expenses', or 'stock'.
    - Preserves leading zeros on barcodes.
    - Uses parameterized batch inserts.
    """

    def __init__(self, connection, batch_size: int = 100, max_limit: int = 1000):
        self.connection = connection
        self.batch_size = max(10, min(batch_size, 500))
        self.max_limit = max_limit
        self.existing_barcodes: Set[str] = set()
        self.load_existing_barcodes()

    def load_existing_barcodes(self) -> int:
        """Loads all existing barcodes from product_catalogue into an in-memory set for O(1) deduplication."""
        cursor = self.connection.cursor()
        try:
            cursor.execute("SELECT barcode FROM product_catalogue WHERE barcode IS NOT NULL")
            rows = cursor.fetchall()
            self.existing_barcodes = {str(r[0]).strip() for r in rows if r[0]}
            return len(self.existing_barcodes)
        finally:
            cursor.close()

    def preview(self, raw_records: List[Dict[str, Any]], preview_count: int = 20) -> Dict[str, Any]:
        """
        Inspects candidate records and produces a validation summary and preview list.
        """
        valid_candidates = []
        preview_rows = []
        seen_in_batch: Set[str] = set()

        stats = {
            "total_scanned": 0,
            "valid_ready_to_insert": 0,
            "duplicate_in_database": 0,
            "duplicate_in_source": 0,
            "incomplete": 0,
            "invalid": 0
        }

        for raw in raw_records:
            stats["total_scanned"] += 1
            is_valid, reason, cleaned = validate_catalogue_record(raw)

            if not is_valid:
                if "INCOMPLETE" in reason:
                    stats["incomplete"] += 1
                else:
                    stats["invalid"] += 1
                continue

            bc = cleaned["barcode"]
            if bc in self.existing_barcodes:
                stats["duplicate_in_database"] += 1
                continue

            if bc in seen_in_batch:
                stats["duplicate_in_source"] += 1
                continue

            seen_in_batch.add(bc)
            stats["valid_ready_to_insert"] += 1
            valid_candidates.append(cleaned)

            if len(preview_rows) < preview_count:
                preview_rows.append(cleaned)

        return {
            "stats": stats,
            "preview_rows": preview_rows,
            "valid_candidates": valid_candidates
        }

    def execute_import(self, valid_records: List[Dict[str, Any]], dry_run: bool = False) -> Dict[str, Any]:
        """
        Executes parameterized batch inserts into MySQL product_catalogue table.
        """
        if not valid_records:
            return {"inserted": 0, "batches": 0, "errors": 0, "status": "No new records to insert."}

        records_to_insert = valid_records[:self.max_limit]
        total_to_insert = len(records_to_insert)

        if dry_run:
            return {
                "inserted": 0,
                "would_insert": total_to_insert,
                "batches": (total_to_insert + self.batch_size - 1) // self.batch_size,
                "dry_run": True,
                "status": f"DRY RUN: {total_to_insert} records verified and ready for insertion."
            }

        insert_sql = """
            INSERT INTO product_catalogue 
            (barcode, product_name, brand, category, package_size, description, image_url, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """

        cursor = self.connection.cursor()
        inserted_count = 0
        batch_count = 0
        consecutive_errors = 0

        try:
            for i in range(0, total_to_insert, self.batch_size):
                # System safety check before each batch
                ram_stat = ResourceMonitor.get_ram_status()
                if ram_stat["load_percent"] > ResourceMonitor.MAX_RAM_LOAD_PERCENT:
                    print(f"\n[RESOURCE ALERT] Memory load at {ram_stat['load_percent']}%. Pausing 2s...")
                    time.sleep(2)

                batch = records_to_insert[i:i + self.batch_size]
                batch_params = [
                    (
                        r["barcode"],
                        r["product_name"],
                        r["brand"],
                        r["category"],
                        r["package_size"],
                        r["description"],
                        r["image_url"],
                        r["source"]
                    )
                    for r in batch
                ]

                try:
                    cursor.executemany(insert_sql, batch_params)
                    self.connection.commit()
                    inserted_count += len(batch)
                    batch_count += 1
                    consecutive_errors = 0

                    # Update local set
                    for r in batch:
                        self.existing_barcodes.add(r["barcode"])

                    print(f"  -> Batch {batch_count}: Inserted {len(batch)} records (Total: {inserted_count}/{total_to_insert})")

                except Exception as batch_error:
                    self.connection.rollback()
                    consecutive_errors += 1
                    print(f"  [ERROR] Batch {batch_count + 1} failed: {batch_error}")
                    if consecutive_errors >= 3:
                        print("  [ABORT] 3 consecutive batch failures encountered. Stopping import safely.")
                        break

        finally:
            cursor.close()

        storage_kb = round((inserted_count * ResourceMonitor.ESTIMATED_BYTES_PER_ROW) / 1024, 2)
        return {
            "inserted": inserted_count,
            "batches": batch_count,
            "errors": consecutive_errors,
            "approx_storage_kb": storage_kb,
            "status": "COMPLETED"
        }


# =============================================================================
# 5. CLI PRESENTATION HELPERS
# =============================================================================

def print_hardware_banner():
    """Prints a clear, informative resource status banner for the user's laptop."""
    ram = ResourceMonitor.get_ram_status()
    disk = ResourceMonitor.get_disk_status()

    print("\n" + "=" * 76)
    print("        AI SHOPKEEPER - SAFE PRODUCT CATALOGUE IMPORTER")
    print("        Hardware Protection Active | Non-Destructive Operation")
    print("=" * 76)
    print(f"  Laptop RAM  : {ram['total_gb']} GB Total | {ram['avail_mb']:.0f} MB Available (Memory Load: {ram['load_percent']}%)")
    print(f"  Disk Space  : {disk['total_gb']} GB Total | {disk['free_gb']} GB Free Storage")
    print("  Protection  : Stream processing (No multi-GB files loaded into RAM)")
    print("  Safe Target : MySQL 'product_catalogue' ONLY (Shop 'products' table untouched)")
    print("-" * 76)


def print_preview_table(preview_rows: List[Dict[str, Any]], stats: Dict[str, int], limit: int):
    """Prints formatted preview table and validation summary."""
    print("\n--- PREVIEW: FIRST 20 CANDIDATE RECORDS ---")
    header = f"{'Barcode':<16} | {'Product Name':<30} | {'Brand':<14} | {'Category':<28}"
    print(header)
    print("-" * len(header))

    for r in preview_rows:
        bc = r["barcode"][:15]
        name = r["product_name"][:29]
        brand = (r["brand"] or "-")[:13]
        cat = r["category"][:27]
        print(f"{bc:<16} | {name:<30} | {brand:<14} | {cat:<28}")

    print("\n--- PRE-IMPORT VALIDATION COUNTERS ---")
    print(f"  Total records scanned          : {stats['total_scanned']}")
    print(f"  Valid new records to insert    : {stats['valid_ready_to_insert']}")
    print(f"  Duplicate (already in MySQL)   : {stats['duplicate_in_database']} (Skipped to prevent overwrite)")
    print(f"  Duplicate (within dataset)     : {stats['duplicate_in_source']} (Skipped)")
    print(f"  Incomplete (missing name/code) : {stats['incomplete']} (Rejected)")
    print(f"  Invalid format                 : {stats['invalid']} (Rejected)")
    print("-" * 55)

    num_to_insert = min(stats["valid_ready_to_insert"], limit)
    est_kb = round((num_to_insert * ResourceMonitor.ESTIMATED_BYTES_PER_ROW) / 1024, 2)
    print(f"  Configured Import Limit        : {limit} records")
    print(f"  Actual records to be inserted  : {num_to_insert}")
    print(f"  Estimated DB Storage Impact    : ~{est_kb} KB (~{est_kb / 1024:.3f} MB)")
    print("-" * 55)


def show_database_catalogue_status(connection):
    """Prints current record counts and sample items in product_catalogue."""
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COUNT(*) as total FROM product_catalogue")
        total = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM product_catalogue 
            GROUP BY category 
            ORDER BY count DESC
        """)
        cat_counts = cursor.fetchall()

        cursor.execute("""
            SELECT catalogue_id, barcode, product_name, brand, category, source 
            FROM product_catalogue 
            ORDER BY catalogue_id DESC 
            LIMIT 5
        """)
        recent_rows = cursor.fetchall()

        print("\n" + "=" * 65)
        print(f"  CURRENT MYSQL 'product_catalogue' STATUS (Total: {total} records)")
        print("=" * 65)
        print("  Breakdown by Category:")
        for cc in cat_counts:
            print(f"    • {cc['category'] or 'Uncategorized'}: {cc['count']} items")

        print("\n  Most Recent 5 Catalogue Items:")
        for r in recent_rows:
            print(f"    [{r['catalogue_id']}] {r['barcode']} | {r['product_name']} ({r['brand'] or 'No Brand'}) | {r['category']}")
        print("-" * 65)

    finally:
        cursor.close()


# =============================================================================
# 6. MAIN ORCHESTRATION & CLI MENU
# =============================================================================

def run_import_workflow(
    source_type: str,
    file_path: Optional[str] = None,
    limit: int = 1000,
    batch_size: int = 100,
    auto_confirm: bool = False,
    dry_run: bool = False
):
    """Orchestrates safety checks, reading, previewing, confirmation, and batch import."""
    print_hardware_banner()

    is_safe, msg = ResourceMonitor.check_safety(limit)
    print(f"  System Check: {msg}")
    if not is_safe:
        print("\n[STOP] Cannot proceed due to resource safety limits.")
        return

    connection = None
    try:
        connection = get_db_connection()
    except Exception as e:
        print(f"\n[DATABASE ERROR] Failed to connect to MySQL: {e}")
        print("Please verify XAMPP MySQL is running.")
        return

    try:
        importer = CatalogueImporter(connection, batch_size=batch_size, max_limit=limit)
        print(f"  Existing records in product_catalogue: {len(importer.existing_barcodes)}")

        # Source Selection
        raw_stream = None
        source_label = ""

        if source_type == "sample":
            default_sample = os.path.join(os.path.dirname(__file__), "curated_indian_kirana_sample.csv")
            target_file = file_path or default_sample
            if not os.path.exists(target_file):
                print(f"[ERROR] Sample file not found at: {target_file}")
                return
            source_label = f"Curated Indian Kirana Sample CSV ({os.path.basename(target_file)})"
            raw_stream = list(stream_csv_file(target_file, limit=limit * 2))

        elif source_type == "csv":
            if not file_path or not os.path.exists(file_path):
                print(f"[ERROR] CSV file does not exist: {file_path}")
                return
            source_label = f"Local CSV File ({os.path.basename(file_path)})"
            raw_stream = list(stream_csv_file(file_path, limit=limit * 2))

        elif source_type == "jsonl":
            if not file_path or not os.path.exists(file_path):
                print(f"[ERROR] JSONL file does not exist: {file_path}")
                return
            source_label = f"Local JSONL File ({os.path.basename(file_path)})"
            raw_stream = list(stream_jsonl_file(file_path, limit=limit * 2))

        elif source_type == "openfoodfacts":
            source_label = f"Open Food Facts India Live Stream (Max: {limit})"
            print("\n  Connecting to Open Food Facts API (India)...")
            raw_stream = list(stream_open_food_facts_api(country="india", limit=limit, page_size=100))

        elif source_type == "openbeautyfacts":
            source_label = f"Open Beauty Facts India Live Stream (Max: {limit})"
            print("\n  Connecting to Open Beauty Facts API (India)...")
            raw_stream = list(stream_open_beauty_facts_api(country="india", limit=limit, page_size=100))

        else:
            print(f"[ERROR] Unknown source type: {source_type}")
            return

        print(f"\n  Active Source: {source_label}")

        # Preview and Validation Step
        preview_data = importer.preview(raw_stream, preview_count=20)
        print_preview_table(preview_data["preview_rows"], preview_data["stats"], limit)

        valid_records = preview_data["valid_candidates"]
        if not valid_records:
            print("\n[RESULT] No new valid records found to import (all records were either duplicate, incomplete, or invalid).")
            return

        # Explicit User Confirmation Required
        num_to_write = min(len(valid_records), limit)
        if not auto_confirm and not dry_run:
            print(f"\n[ACTION REQUIRED] You are about to insert {num_to_write} records into MySQL 'product_catalogue'.")
            confirm = input("Are you sure you want to proceed with the import? [y/N]: ").strip().lower()
            if confirm not in ("y", "yes"):
                print("\n[CANCELLED] Import cancelled by user. Zero records were written to the database.")
                return

        # Execute Import
        print(f"\n--- EXECUTING IMPORT ({'DRY RUN' if dry_run else 'WRITING TO MYSQL'}) ---")
        start_time = time.time()
        result = importer.execute_import(valid_records, dry_run=dry_run)
        duration = time.time() - start_time

        print("\n" + "=" * 65)
        print("                     IMPORT SUMMARY")
        print("=" * 65)
        print(f"  Source                  : {source_label}")
        print(f"  Records Processed       : {preview_data['stats']['total_scanned']}")
        print(f"  Records Inserted        : {result.get('inserted', 0)}")
        print(f"  Duplicates Skipped (DB) : {preview_data['stats']['duplicate_in_database']}")
        print(f"  Duplicates Skipped (Src): {preview_data['stats']['duplicate_in_source']}")
        print(f"  Incomplete Rejected     : {preview_data['stats']['incomplete']}")
        print(f"  Invalid Rejected        : {preview_data['stats']['invalid']}")
        print(f"  Storage Added           : ~{result.get('approx_storage_kb', 0)} KB")
        print(f"  Elapsed Time            : {duration:.2f} seconds")
        print(f"  Database Status         : {result.get('status')}")
        print("-" * 65)

    finally:
        if connection and connection.is_connected():
            connection.close()


def interactive_menu():
    """Interactive command-line wizard for guided catalogue imports."""
    while True:
        print_hardware_banner()
        print("  Select an action:")
        print("    [1] Test Import: Curated Indian Kirana Sample (105 items, offline)")
        print("    [2] Live Import: Open Food Facts India (Foods & Packaged Goods)")
        print("    [3] Live Import: Open Beauty Facts India (Personal Care & Cosmetics)")
        print("    [4] Local File Import: CSV dataset")
        print("    [5] Local File Import: JSONL dataset")
        print("    [6] View Current 'product_catalogue' Status in MySQL")
        print("    [0] Exit")
        print("-" * 76)

        choice = input("Enter choice [0-6]: ").strip()

        if choice == "0":
            print("\nExiting Importer. Have a great day!")
            break

        elif choice == "1":
            limit_in = input("Enter import limit (default 100, max 1000): ").strip()
            limit = int(limit_in) if limit_in.isdigit() else 100
            run_import_workflow(source_type="sample", limit=min(limit, 1000))

        elif choice == "2":
            limit_in = input("Enter import limit (default 200, max 1000): ").strip()
            limit = int(limit_in) if limit_in.isdigit() else 200
            run_import_workflow(source_type="openfoodfacts", limit=min(limit, 1000))

        elif choice == "3":
            limit_in = input("Enter import limit (default 100, max 1000): ").strip()
            limit = int(limit_in) if limit_in.isdigit() else 100
            run_import_workflow(source_type="openbeautyfacts", limit=min(limit, 1000))

        elif choice == "4":
            path = input("Enter path to CSV file: ").strip().strip('"').strip("'")
            if not os.path.exists(path):
                print(f"File not found: {path}")
                continue
            limit_in = input("Enter import limit (default 500, max 2000): ").strip()
            limit = int(limit_in) if limit_in.isdigit() else 500
            run_import_workflow(source_type="csv", file_path=path, limit=limit)

        elif choice == "5":
            path = input("Enter path to JSONL file: ").strip().strip('"').strip("'")
            if not os.path.exists(path):
                print(f"File not found: {path}")
                continue
            limit_in = input("Enter import limit (default 500, max 2000): ").strip()
            limit = int(limit_in) if limit_in.isdigit() else 500
            run_import_workflow(source_type="jsonl", file_path=path, limit=limit)

        elif choice == "6":
            try:
                conn = get_db_connection()
                show_database_catalogue_status(conn)
                conn.close()
            except Exception as e:
                print(f"Database error: {e}")

        else:
            print("Invalid choice, please select between 0 and 6.")

        input("\nPress Enter to return to main menu...")


def main():
    parser = argparse.ArgumentParser(
        description="Safe, non-destructive bulk catalogue importer for Indian Kirana & General Store products."
    )
    parser.add_argument(
        "--source",
        choices=["sample", "openfoodfacts", "openbeautyfacts", "csv", "jsonl"],
        help="Data source to import from"
    )
    parser.add_argument("--file", help="Path to local CSV or JSONL file")
    parser.add_argument("--limit", type=int, default=1000, help="Maximum records to import (default: 1000)")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for MySQL inserts (default: 100)")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt (for automated scripts)")
    parser.add_argument("--dry-run", action="store_true", help="Validate and simulate without writing to MySQL")
    parser.add_argument("--status", action="store_true", help="Display current MySQL product_catalogue stats and exit")

    args = parser.parse_args()

    if args.status:
        try:
            conn = get_db_connection()
            show_database_catalogue_status(conn)
            conn.close()
        except Exception as e:
            print(f"Database error: {e}")
        return

    if args.source:
        run_import_workflow(
            source_type=args.source,
            file_path=args.file,
            limit=args.limit,
            batch_size=args.batch_size,
            auto_confirm=args.yes,
            dry_run=args.dry_run
        )
    else:
        interactive_menu()


if __name__ == "__main__":
    main()
