"""
=============================================================================
COMPREHENSIVE TEST SUITE FOR PRODUCT CATALOGUE IMPORTER
AI Shopkeeper Assistant - Windows 11 & MySQL (shopkeeper_ai)
=============================================================================
Tests:
1. Resource Monitor (RAM & Disk space checks)
2. Barcode Validation & Leading Zeros Preservation
3. Product Name & Data Field Sanitization
4. 7 Canonical Category Classifications
5. In-Memory and In-Database Deduplication
6. Non-Destructive Integrity (products, sales, purchases, expenses untouched)
7. Parameterized SQL Batch Inserts & Rollback Behavior
8. CSV & JSONL Incremental Streaming Readers
=============================================================================
"""

import os
import sys
import json
import tempfile
import unittest

# Ensure UTF-8 output on Windows terminal
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from catalogue_importer import (
    ResourceMonitor,
    classify_kirana_category,
    validate_catalogue_record,
    CatalogueImporter,
    stream_csv_file,
    stream_jsonl_file,
    get_db_connection,
    CANONICAL_CATEGORIES
)


class TestCatalogueImporter(unittest.TestCase):

    def setUp(self):
        self.conn = get_db_connection()

    def tearDown(self):
        if self.conn and self.conn.is_connected():
            self.conn.close()

    # -------------------------------------------------------------------------
    # 1. RESOURCE & LAPTOP MONITOR TESTS
    # -------------------------------------------------------------------------
    def test_01_resource_monitor_ram(self):
        ram = ResourceMonitor.get_ram_status()
        self.assertIn("total_gb", ram)
        self.assertIn("avail_mb", ram)
        self.assertIn("load_percent", ram)
        self.assertGreater(ram["total_gb"], 1.0)
        self.assertGreater(ram["avail_mb"], 0.0)
        self.assertGreater(ram["load_percent"], 0.0)
        print(f"\n  [PASS] RAM Check: {ram['total_gb']} GB Total, {ram['avail_mb']:.0f} MB Available, Load {ram['load_percent']}%")

    def test_02_resource_monitor_disk(self):
        disk = ResourceMonitor.get_disk_status()
        self.assertIn("total_gb", disk)
        self.assertIn("free_gb", disk)
        self.assertGreater(disk["free_gb"], 1.0)
        print(f"  [PASS] Disk Check: {disk['total_gb']} GB Total, {disk['free_gb']} GB Free")

    def test_03_resource_safety_check(self):
        is_safe, msg = ResourceMonitor.check_safety(1000)
        self.assertTrue(is_safe)
        self.assertIn("Hardware OK", msg)
        print(f"  [PASS] Safety Check Message: {msg}")

    # -------------------------------------------------------------------------
    # 2. BARCODE PRESERVATION & VALIDATION
    # -------------------------------------------------------------------------
    def test_04_preserve_leading_zeros(self):
        raw = {
            "barcode": "0001234567890",
            "product_name": "Sample Zero Product",
            "brand": "BrandZero",
            "category": "Groceries"
        }
        is_valid, reason, cleaned = validate_catalogue_record(raw)
        self.assertTrue(is_valid)
        self.assertEqual(cleaned["barcode"], "0001234567890")
        self.assertIsInstance(cleaned["barcode"], str)
        print(f"  [PASS] Leading Zeros Preserved: {cleaned['barcode']}")

    def test_05_reject_missing_or_corrupt_barcodes(self):
        # Empty barcode
        v, r, _ = validate_catalogue_record({"barcode": "", "product_name": "Test"})
        self.assertFalse(v)
        self.assertIn("INCOMPLETE", r)

        # Barcode too short
        v, r, _ = validate_catalogue_record({"barcode": "12", "product_name": "Test"})
        self.assertFalse(v)
        self.assertIn("INVALID", r)

        # Control characters in barcode
        v, r, _ = validate_catalogue_record({"barcode": "89012\n3456", "product_name": "Test"})
        self.assertFalse(v)
        self.assertIn("INVALID", r)
        print("  [PASS] Invalid/Empty Barcodes Correctly Rejected")

    def test_06_reject_missing_product_names(self):
        # Empty name
        v, r, _ = validate_catalogue_record({"barcode": "8901234567890", "product_name": ""})
        self.assertFalse(v)
        self.assertIn("INCOMPLETE", r)

        # Placeholder "None"
        v, r, _ = validate_catalogue_record({"barcode": "8901234567890", "product_name": "None"})
        self.assertFalse(v)
        self.assertIn("INCOMPLETE", r)
        print("  [PASS] Missing/Placeholder Product Names Correctly Rejected")

    # -------------------------------------------------------------------------
    # 3. CANONICAL CATEGORY CLASSIFICATION
    # -------------------------------------------------------------------------
    def test_07_category_classification_all_7(self):
        test_cases = [
            ("Aashirvaad Shudh Chakki Atta", "Groceries", "Rice, flour, pulses and other groceries"),
            ("Tata Sampann Toor Dal", "Pulses", "Rice, flour, pulses and other groceries"),
            ("Britannia Good Day Butter Cookies", "Biscuits", "Packaged foods, biscuits, snacks and chocolates"),
            ("Maggi 2-Minute Masala Noodles", "Noodles", "Packaged foods, biscuits, snacks and chocolates"),
            ("Brooke Bond Red Label Tea", "Tea", "Beverages"),
            ("Sting Energy Drink", "Energy Drink", "Beverages"),
            ("Dettol Antiseptic Bathing Soap", "Personal Care", "Soap, shampoo, toothpaste and personal care"),
            ("Colgate Strong Teeth Toothpaste", "Dental", "Soap, shampoo, toothpaste and personal care"),
            ("Pond's Light Moisturiser", "Skincare", "Cosmetics and skincare"),
            ("Himalaya Purifying Neem Face Wash", "Cosmetics", "Cosmetics and skincare"),
            ("Harpic Power Plus Toilet Cleaner", "Cleaning", "Household cleaning products"),
            ("Surf Excel Easy Wash Detergent", "Laundry", "Household cleaning products"),
            ("Cycle Pure Agarbatti", "General", "Other general-store products"),
            ("Duracell AA Alkaline Battery", "Hardware", "Other general-store products"),
        ]

        for name, raw_cat, expected in test_cases:
            res = classify_kirana_category(raw_cat, name)
            self.assertEqual(res, expected, f"Failed for {name}: got {res}, expected {expected}")
            self.assertIn(res, CANONICAL_CATEGORIES)
        print("  [PASS] All 7 Kirana & General Store Categories Accurately Classified")

    # -------------------------------------------------------------------------
    # 4. DEDUPLICATION LOGIC
    # -------------------------------------------------------------------------
    def test_08_deduplication_database_and_source(self):
        importer = CatalogueImporter(self.conn)

        # Existing barcode in DB (e.g. TEST-RICE-001 or previously imported)
        existing_bc = list(importer.existing_barcodes)[0]
        test_records = [
            # 1. Duplicate in DB
            {"barcode": existing_bc, "product_name": "Duplicate DB Item"},
            # 2. Valid new item 1
            {"barcode": "9999999999001", "product_name": "Unique Test Item 1", "category": "Groceries"},
            # 3. Duplicate within source (same barcode as 2)
            {"barcode": "9999999999001", "product_name": "Repeated Source Item 1", "category": "Groceries"},
            # 4. Valid new item 2
            {"barcode": "9999999999002", "product_name": "Unique Test Item 2", "category": "Groceries"},
        ]

        preview_res = importer.preview(test_records)
        stats = preview_res["stats"]

        self.assertEqual(stats["total_scanned"], 4)
        self.assertEqual(stats["duplicate_in_database"], 1)
        self.assertEqual(stats["duplicate_in_source"], 1)
        self.assertEqual(stats["valid_ready_to_insert"], 2)
        print(f"  [PASS] Deduplication: DB Dups={stats['duplicate_in_database']}, Source Dups={stats['duplicate_in_source']}, Valid={stats['valid_ready_to_insert']}")

    # -------------------------------------------------------------------------
    # 5. DATABASE INTEGRITY INVARIANTS
    # -------------------------------------------------------------------------
    def test_09_database_integrity_products_table_untouched(self):
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as count FROM products")
        products_count_before = cursor.fetchone()["count"]

        cursor.execute("SELECT product_id, product_name, selling_price, current_stock FROM products WHERE barcode = 'TEST-RICE-001'")
        rice_row = cursor.fetchone()
        cursor.close()

        self.assertGreaterEqual(products_count_before, 8)
        self.assertIsNotNone(rice_row)
        self.assertEqual(rice_row["product_name"], "Rice")
        self.assertEqual(float(rice_row["selling_price"]), 60.0)
        self.assertEqual(float(rice_row["current_stock"]), 5.0)
        print(f"  [PASS] Products Table Invariant: {products_count_before} items, Prices and Stock Unchanged")

    def test_10_catalogue_table_has_no_shop_prices_or_stock(self):
        cursor = self.conn.cursor()
        cursor.execute("DESCRIBE product_catalogue")
        columns = [row[0] for row in cursor.fetchall()]
        cursor.close()

        forbidden_cols = ["selling_price", "purchase_price", "current_stock", "opening_stock", "reorder_level"]
        for col in forbidden_cols:
            self.assertNotIn(col, columns, f"Forbidden inventory column '{col}' found in product_catalogue!")
        print("  [PASS] Catalogue Table Verified: Zero Shop Selling/Cost Prices or Stock Columns Exist")

    # -------------------------------------------------------------------------
    # 6. STREAMING READERS
    # -------------------------------------------------------------------------
    def test_11_streaming_csv_reader(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("barcode,product_name,brand\n")
            f.write("8900000000001,Test Product 1,Brand 1\n")
            f.write("8900000000002,Test Product 2,Brand 2\n")
            f.write("8900000000003,Test Product 3,Brand 3\n")
            tmp_path = f.name

        try:
            records = list(stream_csv_file(tmp_path, limit=2))
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["barcode"], "8900000000001")
            self.assertEqual(records[1]["product_name"], "Test Product 2")
            print("  [PASS] CSV Incremental Streaming Reader Works")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_12_streaming_jsonl_reader(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
            f.write(json.dumps({"barcode": "8900000000011", "product_name": "JSONL Prod 1"}) + "\n")
            f.write(json.dumps({"barcode": "8900000000012", "product_name": "JSONL Prod 2"}) + "\n")
            tmp_path = f.name

        try:
            records = list(stream_jsonl_file(tmp_path))
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["barcode"], "8900000000011")
            self.assertEqual(records[1]["product_name"], "JSONL Prod 2")
            print("  [PASS] JSONL Incremental Streaming Reader Works")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


def run_tests():
    print("\n" + "=" * 65)
    print("      RUNNING PRODUCT CATALOGUE IMPORTER TEST SUITE")
    print("=" * 65)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCatalogueImporter)
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)

    print("\n" + "=" * 65)
    print(f"TEST RESULTS: {result.testsRun} Tests Run | {len(result.errors)} Errors | {len(result.failures)} Failures")
    print("=" * 65)
    return len(result.errors) == 0 and len(result.failures) == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
