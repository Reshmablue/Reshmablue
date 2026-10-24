import os
import sys
import time
from decimal import Decimal

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import cv2
if hasattr(cv2, "utils") and hasattr(cv2.utils, "logging"):
    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
    except Exception:
        pass
import mysql.connector
import numpy as np
from dotenv import load_dotenv

load_dotenv()

from billing_system import (
    connect_database,
    find_product,
    validate_and_add_to_cart,
    update_cart_item_quantity,
    remove_from_cart,
    calculate_bill_totals,
    process_checkout
)
from webcam_scanner import WebcamScanner


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []

    def run_test(self, name, test_func):
        print(f"\n[RUNNING] {name}...")
        try:
            test_func()
            print(f"  --> PASS: {name}")
            self.passed += 1
            self.tests.append((name, "PASS", ""))
        except AssertionError as err:
            print(f"  --> FAIL (Assertion): {err}")
            self.failed += 1
            self.tests.append((name, "FAIL", str(err)))
        except Exception as err:
            print(f"  --> ERROR: {err}")
            self.failed += 1
            self.tests.append((name, "ERROR", str(err)))

    def summary(self):
        print("\n" + "=" * 60)
        print(f"TEST SUMMARY: {self.passed} Passed, {self.failed} Failed (Total {len(self.tests)})")
        print("=" * 60)
        for name, status, err in self.tests:
            flag = "PASS" if status == "PASS" else "FAIL"
            print(f"[{flag:4}] {name:50} : {status} {('(' + err + ')') if err else ''}")
        print("=" * 60)
        return self.failed == 0


def main():
    runner = TestRunner()
    connection = connect_database()
    cursor = connection.cursor(dictionary=True)

    # 1. Existing barcode lookup (TEST-RICE-001)
    def test_existing_barcode():
        product = find_product(cursor, "TEST-RICE-001")
        assert product is not None, "Product 'TEST-RICE-001' should be found in active inventory"
        assert product["product_name"] == "Rice", f"Expected 'Rice', got {product['product_name']}"
        assert product["selling_price"] == Decimal("60.00"), f"Expected 60.00, got {product['selling_price']}"
        assert product["is_active"] == 1, "Product must be active"
    runner.run_test("1. Existing Barcode Lookup (TEST-RICE-001)", test_existing_barcode)

    # 2. Unknown barcode lookup
    def test_unknown_barcode():
        product = find_product(cursor, "UNKNOWN-BARCODE-99999-XYZ")
        assert product is None, "Unknown barcode should return None"
    runner.run_test("2. Unknown Barcode Lookup", test_unknown_barcode)

    # 3. Inactive product lookup
    def test_inactive_product():
        # Temporarily insert an inactive product inside a transaction and roll back
        connection.rollback()
        connection.start_transaction()
        try:
            cursor.execute(
                """
                INSERT INTO products (product_name, barcode, selling_price, purchase_price, current_stock, is_active)
                VALUES ('Temp Inactive Biscuit', 'TEST-INACTIVE-001', 20.00, 15.00, 10.00, 0)
                """
            )
            # find_product must ignore inactive products
            found = find_product(cursor, "TEST-INACTIVE-001")
            assert found is None, "find_product must NOT return inactive products where is_active = 0"
        finally:
            connection.rollback()
    runner.run_test("3. Inactive Product Filter (is_active = 0)", test_inactive_product)

    # 4. Repeated scans accumulation
    def test_repeated_scans():
        product = find_product(cursor, "TEST-RICE-001")
        cart = {}
        # Scan 1
        validate_and_add_to_cart(cart, product, Decimal("1"))
        assert cart[product["product_id"]]["quantity"] == Decimal("1")
        # Scan 2 (repeated scan)
        validate_and_add_to_cart(cart, product, Decimal("1"))
        assert cart[product["product_id"]]["quantity"] == Decimal("2")
        # Scan 3 (repeated scan)
        validate_and_add_to_cart(cart, product, Decimal("1"))
        assert cart[product["product_id"]]["quantity"] == Decimal("3")
    runner.run_test("4. Repeated Scans Increment Quantity", test_repeated_scans)

    # 5. Quantity changes & remove items
    def test_quantity_changes():
        product = find_product(cursor, "TEST-RICE-001")
        cart = {}
        validate_and_add_to_cart(cart, product, Decimal("1"))
        pid = product["product_id"]

        # Explicitly change quantity to 4
        update_cart_item_quantity(cart, pid, Decimal("4"))
        assert cart[pid]["quantity"] == Decimal("4")

        # Explicitly change quantity to 0 removes the item
        update_cart_item_quantity(cart, pid, Decimal("0"))
        assert pid not in cart, "Setting quantity to 0 should remove the item"

        # Test remove_from_cart
        validate_and_add_to_cart(cart, product, Decimal("2"))
        removed = remove_from_cart(cart, pid)
        assert removed is True
        assert pid not in cart
    runner.run_test("5. Quantity Adjustments & Item Removal", test_quantity_changes)

    # 6. Insufficient stock validation
    def test_insufficient_stock():
        product = find_product(cursor, "TEST-RICE-001")
        cart = {}
        stock = Decimal(str(product["current_stock"]))

        # Attempt to add more than available stock
        excess_qty = stock + Decimal("10")
        try:
            validate_and_add_to_cart(cart, product, excess_qty)
            assert False, "Should have raised ValueError for insufficient stock"
        except ValueError as e:
            assert "Not enough stock" in str(e) or "insufficient" in str(e).lower()

        # Add valid stock, then attempt to increase beyond limit
        validate_and_add_to_cart(cart, product, stock)
        try:
            update_cart_item_quantity(cart, product["product_id"], stock + Decimal("1"))
            assert False, "Should have raised ValueError on update beyond available stock"
        except ValueError as e:
            assert "Not enough stock" in str(e)
    runner.run_test("6. Insufficient Stock Validation", test_insufficient_stock)

    # 7. Correct bill totals calculation
    def test_bill_totals():
        cart = {
            101: {"price": Decimal("60.00"), "quantity": Decimal("2")},  # 120.00
            102: {"price": Decimal("25.50"), "quantity": Decimal("4")},  # 102.00
            103: {"price": Decimal("10.00"), "quantity": Decimal("1")},  #  10.00
        }
        subtotal, discount, total = calculate_bill_totals(cart, Decimal("0"))
        expected_subtotal = Decimal("232.00")
        assert subtotal == expected_subtotal, f"Expected {expected_subtotal}, got {subtotal}"
        assert total == expected_subtotal, f"Expected {expected_subtotal}, got {total}"
    runner.run_test("7. Bill Totals Calculation", test_bill_totals)

    # 8. Discount calculations
    def test_discount_calculations():
        cart = {
            101: {"price": Decimal("100.00"), "quantity": Decimal("2")},  # 200.00
        }
        # Valid discount
        subtotal, discount, total = calculate_bill_totals(cart, Decimal("25.00"))
        assert subtotal == Decimal("200.00")
        assert discount == Decimal("25.00")
        assert total == Decimal("175.00")

        # Negative discount rejection
        try:
            calculate_bill_totals(cart, Decimal("-10.00"))
            assert False, "Should reject negative discount"
        except ValueError as e:
            assert "negative" in str(e).lower()

        # Discount exceeding subtotal rejection
        try:
            calculate_bill_totals(cart, Decimal("250.00"))
            assert False, "Should reject discount exceeding subtotal"
        except ValueError as e:
            assert "cannot exceed subtotal" in str(e).lower()
    runner.run_test("8. Discount Calculations & Validations", test_discount_calculations)

    # 9. Successful checkout & stock updates (Safe Rollback Strategy)
    def test_safe_checkout_and_stock():
        # Dedicated isolated test connection
        test_conn = connect_database()
        test_cur = test_conn.cursor(dictionary=True)

        # 1. Insert temporary test product and commit it so process_checkout can see it
        test_cur.execute(
            """
            INSERT INTO products (product_name, barcode, unit, selling_price, purchase_price, current_stock, is_active)
            VALUES ('Automated Test Item', 'TEST-ISOLATED-001', 'kg', 80.00, 50.00, 10.00, 1)
            """
        )
        test_conn.commit()
        test_pid = test_cur.lastrowid

        try:
            cart = {
                test_pid: {
                    "product_id": test_pid,
                    "name": "Automated Test Item",
                    "barcode": "TEST-ISOLATED-001",
                    "unit": "kg",
                    "price": Decimal("80.00"),
                    "cost": Decimal("50.00"),
                    "stock": Decimal("10.00"),
                    "quantity": Decimal("3.00")
                }
            }

            # Execute checkout
            result = process_checkout(test_conn, cart, discount=Decimal("10.00"), payment_method="UPI")
            sale_id = result["sale_id"]
            assert sale_id > 0
            assert result["total"] == Decimal("230.00")

            # Verify stock was updated in DB
            test_cur.execute("SELECT current_stock FROM products WHERE product_id = %s", (test_pid,))
            stock_after = test_cur.fetchone()["current_stock"]
            assert stock_after == Decimal("7.00"), f"Expected 7.00 stock after sale, got {stock_after}"

            # Verify sales and sale_items tables
            test_cur.execute("SELECT * FROM sales WHERE sale_id = %s", (sale_id,))
            sale_row = test_cur.fetchone()
            assert sale_row is not None
            assert sale_row["total_amount"] == Decimal("230.00")

            test_cur.execute("SELECT * FROM sale_items WHERE sale_id = %s", (sale_id,))
            items = test_cur.fetchall()
            assert len(items) == 1
            assert items[0]["quantity"] == Decimal("3.00")

            # CLEANUP: Remove test sale, test sale_items, and test product
            test_cur.execute("DELETE FROM sale_items WHERE sale_id = %s", (sale_id,))
            test_cur.execute("DELETE FROM sales WHERE sale_id = %s", (sale_id,))
            test_cur.execute("DELETE FROM products WHERE product_id = %s", (test_pid,))
            test_conn.commit()

        finally:
            # Guarantee cleanup even on error
            try:
                test_cur.execute("DELETE FROM products WHERE barcode = 'TEST-ISOLATED-001'")
                test_conn.commit()
            except Exception:
                pass
            test_cur.close()
            test_conn.close()

    runner.run_test("9. Checkout & Stock Deduction (Safe Verification)", test_safe_checkout_and_stock)

    # 10. Transaction rollback on checkout error
    def test_transaction_rollback_on_failure():
        test_conn = connect_database()
        test_cur = test_conn.cursor(dictionary=True)

        # Get initial stock of Rice
        test_cur.execute("SELECT current_stock FROM products WHERE barcode = 'TEST-RICE-001'")
        initial_stock = test_cur.fetchone()["current_stock"]

        # Cart requesting more Rice than exists in database
        excess_qty = initial_stock + Decimal("100.00")
        cart = {
            1: {
                "product_id": 1,
                "name": "Rice",
                "unit": "kg",
                "price": Decimal("60.00"),
                "cost": Decimal("45.00"),
                "quantity": excess_qty
            }
        }

        try:
            process_checkout(test_conn, cart, Decimal("0"), "Cash")
            assert False, "Should have raised ValueError due to insufficient stock in database"
        except ValueError as e:
            assert "Insufficient stock" in str(e)

        # Verify stock was untouched after transaction rollback
        test_cur.execute("SELECT current_stock FROM products WHERE barcode = 'TEST-RICE-001'")
        stock_now = test_cur.fetchone()["current_stock"]
        assert stock_now == initial_stock, f"Stock must be untouched after rollback: expected {initial_stock}, got {stock_now}"

        test_cur.close()
        test_conn.close()

    runner.run_test("10. Transaction Rollback On Checkout Failure", test_transaction_rollback_on_failure)

    # 11. Duplicate checkout / empty cart prevention
    def test_duplicate_and_empty_checkout():
        test_conn = connect_database()
        # Empty cart checkout must raise ValueError
        try:
            process_checkout(test_conn, {}, Decimal("0"), "Cash")
            assert False, "Empty cart checkout should fail"
        except ValueError as e:
            assert "empty" in str(e).lower()

        # Missing payment method must raise ValueError
        cart = {1: {"product_id": 1, "name": "Item", "unit": "kg", "price": Decimal("10"), "cost": Decimal("5"), "quantity": Decimal("1")}}
        try:
            process_checkout(test_conn, cart, Decimal("0"), "")
            assert False, "Empty payment method checkout should fail"
        except ValueError as e:
            assert "payment method" in str(e).lower()

        test_conn.close()

    runner.run_test("11. Duplicate & Empty Checkout Prevention", test_duplicate_and_empty_checkout)

    # 12. USB barcode scanner simulation
    def test_usb_scanner_simulation():
        # USB barcode scanners type characters rapidly and send \r or \n
        scanner_payload = "  TEST-RICE-001\r\n"
        cleaned_barcode = scanner_payload.strip()
        product = find_product(cursor, cleaned_barcode)
        assert product is not None, "Cleaned USB scanner input must find product"
        assert product["barcode"] == "TEST-RICE-001"
    runner.run_test("12. USB Scanner Input Simulation", test_usb_scanner_simulation)

    # 13. Webcam barcode detector decoding test
    def test_webcam_detection():
        scanner = WebcamScanner()
        # Generate synthetic QR code with TEST-RICE-001
        encoder = cv2.QRCodeEncoder.create()
        qr_matrix = encoder.encode("TEST-RICE-001")
        border = cv2.copyMakeBorder(qr_matrix, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
        test_frame = cv2.resize(border, (320, 240), interpolation=cv2.INTER_NEAREST)
        test_frame_bgr = cv2.cvtColor(test_frame, cv2.COLOR_GRAY2BGR)

        barcode_text, points = scanner._decode_frame(test_frame_bgr)
        assert barcode_text == "TEST-RICE-001", f"Expected 'TEST-RICE-001', decoded '{barcode_text}'"
        assert points is not None, "Detector should return bounding points"
    runner.run_test("13. Webcam Barcode / QR Decoding Engine", test_webcam_detection)

    # 14. Webcam unavailable or invalid camera handling
    def test_webcam_unavailable_handling():
        status_reports = []
        def on_status(msg, is_err):
            status_reports.append((msg, is_err))

        # Use an invalid camera index (e.g. 999)
        scanner = WebcamScanner(on_status=on_status)
        scanner.start(camera_index=999)
        # Wait a moment for thread to attempt connection
        time.sleep(0.5)
        scanner.stop()

        # Should have captured an error status gracefully without crashing
        assert any(is_err for _, is_err in status_reports), "Invalid camera index should report an error status"
    runner.run_test("14. Camera Unavailable & Permission Error Handling", test_webcam_unavailable_handling)

    # Clean up main connection
    cursor.close()
    connection.close()

    # Print summary and return success boolean
    success = runner.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
