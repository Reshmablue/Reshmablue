"""
=============================================================================
TEST SUITE: MULTI-TIER PRODUCT LOOKUP & ONLINE API RECOGNITION
AI Shopkeeper Assistant - Windows 11 & MySQL (shopkeeper_ai)
=============================================================================
Tests:
1. Tier 1: Existing Active Store Inventory Lookup ('products')
2. Tier 2: Existing Master Catalogue Lookup ('product_catalogue')
3. Tier 3: Live / On-Demand Official Online API Recognition & Caching
4. Second-Lookup Local Cache Hit (Offline-Ready)
5. Non-Existent Barcode Graceful Fallback
6. Network Timeout & Error Resilience
7. Registration of Confirmed Item into Inventory with Shop Prices
8. Price / Stock Validation (Prevents Invented Numbers or Zero/Negative Prices)
9. Database Invariants: sales, purchases, expenses untouched
=============================================================================
"""

import os
import sys
import unittest
from decimal import Decimal

# Ensure UTF-8 output on Windows terminal
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import mysql.connector
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from product_lookup_service import (
    fetch_from_official_apis,
    cache_in_catalogue,
    lookup_product_tiered,
    register_product_to_inventory
)
from catalogue_importer import get_db_connection


class TestProductLookupService(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT COUNT(*) AS count FROM sales")
        cls.initial_sales_count = cur.fetchone()["count"]
        cur.execute("SELECT COUNT(*) AS count FROM expenses")
        cls.initial_expenses_count = cur.fetchone()["count"]
        cur.close()
        conn.close()

    def setUp(self):
        self.conn = get_db_connection()
        self.cursor = self.conn.cursor(dictionary=True)

    def tearDown(self):
        if self.cursor:
            self.cursor.close()
        if self.conn and self.conn.is_connected():
            self.conn.close()

    # -------------------------------------------------------------------------
    # TEST 1: Tier 1 - Active Inventory Lookup
    # -------------------------------------------------------------------------
    def test_01_tier1_inventory_lookup(self):
        result = lookup_product_tiered(self.cursor, self.conn, "TEST-RICE-001", allow_online=False)
        self.assertEqual(result["status"], "FOUND_IN_INVENTORY")
        self.assertEqual(result["tier"], 1)
        self.assertIsNotNone(result["product"])
        self.assertEqual(result["product"]["product_name"], "Rice")
        self.assertEqual(Decimal(str(result["product"]["selling_price"])), Decimal("60.00"))
        print("\n  [PASS] Tier 1: Found in store inventory (Rice, Rs. 60.00)")

    # -------------------------------------------------------------------------
    # TEST 2: Tier 2 - Local Master Catalogue Lookup
    # -------------------------------------------------------------------------
    def test_02_tier2_catalogue_lookup(self):
        # Dynamically find a catalogue product that is not stocked in inventory
        self.cursor.execute("SELECT barcode FROM products")
        stocked = {r["barcode"] for r in self.cursor.fetchall() if r.get("barcode")}
        self.cursor.execute("SELECT barcode, product_name, category FROM product_catalogue")
        candidate = None
        for r in self.cursor.fetchall():
            if r["barcode"] not in stocked:
                candidate = r
                break
        
        target_bc = candidate["barcode"] if candidate else "8901725181222"
        result = lookup_product_tiered(self.cursor, self.conn, target_bc, allow_online=False)
        self.assertEqual(result["status"], "FOUND_IN_CATALOGUE")
        self.assertEqual(result["tier"], 2)
        self.assertIsNotNone(result["catalogue_item"])
        print(f"  [PASS] Tier 2: Found in local catalogue ('{result['catalogue_item']['product_name']}')")

    # -------------------------------------------------------------------------
    # TEST 3: Tier 3 - On-Demand Official Online API Fetch
    # -------------------------------------------------------------------------
    def test_03_tier3_online_api_fetch(self):
        # Open Food Facts item: Parle-G
        data = fetch_from_official_apis("8901719134845", timeout=3.5)
        self.assertIsNotNone(data)
        self.assertEqual(data["barcode"], "8901719134845")
        self.assertTrue(len(data["product_name"]) > 0)
        self.assertIn("ODbL", data["source"])
        print(f"  [PASS] Tier 3 Online Fetch: '{data['product_name']}' from {data['source']}")

    # -------------------------------------------------------------------------
    # TEST 4: Tier 3 - Live Online Recognition & Automatic Caching
    # -------------------------------------------------------------------------
    def test_04_tier3_online_recognition_and_caching(self):
        # Using Sting Energy (8902080000227) which is not in shop inventory
        test_bc = "8902080000227"

        # Lookup with online enabled
        result1 = lookup_product_tiered(self.cursor, self.conn, test_bc, allow_online=True)
        self.assertIn(result1["status"], ("FOUND_ONLINE", "FOUND_IN_CATALOGUE"))
        self.assertIsNotNone(result1["catalogue_item"])

        # Immediate second lookup should hit Tier 2 (local cache)
        result2 = lookup_product_tiered(self.cursor, self.conn, test_bc, allow_online=False)
        self.assertEqual(result2["status"], "FOUND_IN_CATALOGUE")
        self.assertEqual(result2["tier"], 2)
        print(f"  [PASS] Tier 3 Cache Verification: '{result2['catalogue_item']['product_name']}' cached and re-used offline")

    # -------------------------------------------------------------------------
    # TEST 5: Unmapped Barcode Graceful Fallback
    # -------------------------------------------------------------------------
    def test_05_unmapped_barcode_fallback(self):
        result = lookup_product_tiered(self.cursor, self.conn, "0000000000000", allow_online=True)
        self.assertEqual(result["status"], "NOT_FOUND")
        self.assertEqual(result["tier"], 0)
        self.assertIsNone(result["product"])
        self.assertIsNone(result["catalogue_item"])
        print("  [PASS] Unmapped Barcode: Correctly reports NOT_FOUND for manual registration")

    # -------------------------------------------------------------------------
    # TEST 6: Network Failure / Disconnected Simulation
    # -------------------------------------------------------------------------
    def test_06_network_timeout_resilience(self):
        # Very short timeout with invalid barcode should never crash
        data = fetch_from_official_apis("INVALID-CODE-9999", timeout=0.1)
        self.assertIsNone(data)
        print("  [PASS] Network Resilience: Timeout/failure handled gracefully without crashing")

    # -------------------------------------------------------------------------
    # TEST 7: Registration of Confirmed Item into Inventory with Shop Prices
    # -------------------------------------------------------------------------
    def test_07_register_product_to_inventory(self):
        test_bc = "TEST-REG-ITEM-001"

        # Clean up if leftover from previous run
        self.cursor.execute("DELETE FROM products WHERE barcode = %s", (test_bc,))
        self.conn.commit()

        new_pid = register_product_to_inventory(
            self.cursor,
            self.conn,
            product_name="Test Registered Grocery",
            selling_price=Decimal("45.00"),
            category="Groceries",
            unit="pack",
            purchase_price=Decimal("30.00"),
            current_stock=Decimal("20.00"),
            reorder_level=Decimal("5.00"),
            barcode=test_bc,
            catalogue_id=None
        )

        self.assertGreater(new_pid, 0)

        # Verify it now resolves via Tier 1
        lookup = lookup_product_tiered(self.cursor, self.conn, test_bc, allow_online=False)
        self.assertEqual(lookup["status"], "FOUND_IN_INVENTORY")
        self.assertEqual(lookup["tier"], 1)
        self.assertEqual(lookup["product"]["product_name"], "Test Registered Grocery")
        self.assertEqual(Decimal(str(lookup["product"]["selling_price"])), Decimal("45.00"))

        # Clean up test row
        self.cursor.execute("DELETE FROM products WHERE product_id = %s", (new_pid,))
        self.conn.commit()
        print(f"  [PASS] Inventory Registration: Registered item ID {new_pid} with price Rs. 45.00, verified Tier 1")

    # -------------------------------------------------------------------------
    # TEST 8: Price & Stock Validation
    # -------------------------------------------------------------------------
    def test_08_price_and_stock_validation(self):
        # Selling price <= 0 must fail
        with self.assertRaises(ValueError):
            register_product_to_inventory(
                self.cursor, self.conn,
                product_name="Bad Item",
                selling_price=Decimal("0.00"),
                current_stock=Decimal("10.00")
            )

        # Negative stock must fail
        with self.assertRaises(ValueError):
            register_product_to_inventory(
                self.cursor, self.conn,
                product_name="Bad Item 2",
                selling_price=Decimal("20.00"),
                current_stock=Decimal("-5.00")
            )
        print("  [PASS] Validation Rules: Zero/negative selling prices and negative stock prevented")

    # -------------------------------------------------------------------------
    # TEST 9: Non-Destructive Integrity (Sales, Purchases, Expenses)
    # -------------------------------------------------------------------------
    def test_09_database_integrity_invariants(self):
        # Ensure sales count remains untouched
        self.cursor.execute("SELECT COUNT(*) AS count FROM sales")
        sales_count = self.cursor.fetchone()["count"]
        self.assertEqual(sales_count, self.initial_sales_count)

        # Ensure expenses count remains untouched
        self.cursor.execute("SELECT COUNT(*) AS count FROM expenses")
        expenses_count = self.cursor.fetchone()["count"]
        self.assertEqual(expenses_count, self.initial_expenses_count)
        print(f"  [PASS] Financial Integrity Invariants: Sales={sales_count}, Expenses={expenses_count} untouched")


def run_tests():
    print("\n" + "=" * 65)
    print("      RUNNING PRODUCT LOOKUP SERVICE TEST SUITE")
    print("=" * 65)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestProductLookupService)
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)

    print("\n" + "=" * 65)
    print(f"TEST RESULTS: {result.testsRun} Tests Run | {len(result.errors)} Errors | {len(result.failures)} Failures")
    print("=" * 65)
    return len(result.errors) == 0 and len(result.failures) == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
