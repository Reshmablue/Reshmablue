"""
=============================================================================
AI SHOPKEEPER ASSISTANT - WEB APPLICATION (FLASK BACKEND)
Windows 11 & MySQL (shopkeeper_ai) & Google Gemma
=============================================================================
Provides REST API endpoints and web routes for:
1. Dashboard
2. Billing & Point of Sale (POS)
3. Smart Product Lookup (3-tier)
4. Inventory Management
5. Sales & Purchases
6. Profit & Loss Reports
7. Gemma AI Chatbot
8. Voice-to-Voice Assistant
9. Sales Analytics
10. Settings & System Health
=============================================================================
"""

import os
import sys
import json
import traceback
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional
import base64
import cv2
import numpy as np

try:
    import zxingcpp
    HAS_ZXING = True
except ImportError:
    zxingcpp = None
    HAS_ZXING = False

# Ensure UTF-8 output
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from flask import Flask, render_template, request, jsonify, send_from_directory, send_file
import io
from gtts import gTTS
import mysql.connector
from dotenv import load_dotenv

# Ensure .env is loaded from this directory
base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, ".env"))

# Import existing verified modules
from billing_system import (
    find_product,
    validate_and_add_to_cart,
    update_cart_item_quantity,
    remove_from_cart,
    calculate_bill_totals,
    process_checkout
)
from daily_report import calculate_financial_report
from shop_analytics import (
    get_financial_summary,
    get_best_selling_products,
    get_slow_moving_products,
    get_low_stock_products,
    get_inventory_summary,
    get_expenses_breakdown,
    get_purchase_history,
    get_sales_trends,
    resolve_business_data_for_question,
    parse_date_period
)
from chatbot import ask_shopkeeper_assistant
from voice_assistant import (
    process_voice_query,
    clean_speech_text,
    detect_language
)
from product_lookup_service import (
    lookup_product_tiered,
    register_product_to_inventory,
    fetch_from_official_apis,
    cache_in_catalogue
)

app = Flask(
    __name__,
    template_folder=os.path.join(base_dir, "templates"),
    static_folder=os.path.join(base_dir, "static")
)
app.config["JSON_AS_ASCII"] = False

SETTINGS_FILE = os.path.join(base_dir, "shop_settings.json")


def get_db():
    """Create a MySQL connection using verified environment credentials."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "shopkeeper_ai"),
        connection_timeout=10
    )


def serialize_val(val: Any) -> Any:
    """Helper to convert Decimal and datetime objects to JSON-serializable types."""
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    if isinstance(val, dict):
        return {k: serialize_val(v) for k, v in val.items()}
    if isinstance(val, list):
        return [serialize_val(v) for v in val]
    return val


def load_settings() -> Dict[str, Any]:
    """Load or initialize shop settings from local JSON file."""
    default_settings = {
        "shop_name": "Sri Lakshmi Kirana & General Stores",
        "owner_name": "Ramesh Kumar",
        "phone": "+91 98765 43210",
        "address": "Main Road, Market Yard, Hyderabad, Telangana",
        "gstin": "36AAAAA0000A1Z5",
        "currency_symbol": "₹",
        "receipt_footer": "Thank you for shopping with us! Visit again.",
        "voice_language": "en-IN",
        "auto_speak_response": True,
        "low_stock_default_threshold": 5
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_settings.update(data)
        except Exception:
            pass
    return default_settings


def save_settings(settings: Dict[str, Any]) -> None:
    """Persist settings to local JSON file safely."""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


# =============================================================================
# 0. MAIN WEB APPLICATION ROUTE
# =============================================================================

@app.route("/")
def index():
    """Serve single-page unified application."""
    settings = load_settings()
    return render_template("index.html", settings=settings)


# =============================================================================
# 1. DASHBOARD API
# =============================================================================

@app.route("/api/dashboard", methods=["GET"])
def api_dashboard():
    """
    Returns today's metrics, active product count, low stock warnings,
    recent sales, 7-day sales trend, and month-to-date summary.
    """
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        today = date.today()
        tomorrow = today + timedelta(days=1)

        # 1. Today's Financials (from daily_report calculation)
        today_rep = calculate_financial_report(cursor, today, tomorrow)

        # 2. Total active products & inventory count
        cursor.execute("SELECT COUNT(*) AS total_active FROM products WHERE is_active = 1")
        total_active = cursor.fetchone()["total_active"]

        # 3. Low stock count
        cursor.execute("""
            SELECT COUNT(*) AS low_count
            FROM products
            WHERE is_active = 1 AND current_stock <= reorder_level
        """)
        low_count = cursor.fetchone()["low_count"]

        # 4. Recent 5 sales
        cursor.execute("""
            SELECT s.sale_id, s.sale_date, s.total_amount, s.discount, s.payment_method,
                   COUNT(si.sale_item_id) AS item_count
            FROM sales s
            LEFT JOIN sale_items si ON si.sale_id = s.sale_id
            GROUP BY s.sale_id, s.sale_date, s.total_amount, s.discount, s.payment_method
            ORDER BY s.sale_id DESC
            LIMIT 5
        """)
        recent_sales = cursor.fetchall()

        # 5. Month-to-date Financials
        first_of_month = date(today.year, today.month, 1)
        if today.month == 12:
            first_of_next_month = date(today.year + 1, 1, 1)
        else:
            first_of_next_month = date(today.year, today.month + 1, 1)
        month_rep = calculate_financial_report(cursor, first_of_month, first_of_next_month)

        # 6. 7-day sales trend for chart
        seven_days_ago = today - timedelta(days=6)
        cursor.execute("""
            SELECT DATE(sale_date) AS sdate, COALESCE(SUM(total_amount), 0) AS daily_rev, COUNT(*) AS bills
            FROM sales
            WHERE sale_date >= %s
            GROUP BY DATE(sale_date)
            ORDER BY sdate ASC
        """, (seven_days_ago,))
        trend_rows = cursor.fetchall()

        # Map to all 7 days
        trend_map = {r["sdate"].strftime("%Y-%m-%d") if isinstance(r["sdate"], date) else str(r["sdate"]): float(r["daily_rev"]) for r in trend_rows}
        chart_labels = []
        chart_data = []
        for i in range(7):
            d = (seven_days_ago + timedelta(days=i)).strftime("%Y-%m-%d")
            chart_labels.append(d)
            chart_data.append(trend_map.get(d, 0.0))

        # 7. Low stock alert items (top 5)
        cursor.execute("""
            SELECT product_id, product_name, category, unit, current_stock, reorder_level
            FROM products
            WHERE is_active = 1 AND current_stock <= reorder_level
            ORDER BY current_stock ASC
            LIMIT 5
        """)
        low_stock_items = cursor.fetchall()

        return jsonify({
            "status": "success",
            "today": serialize_val(today_rep),
            "month": serialize_val(month_rep),
            "total_active_products": total_active,
            "low_stock_count": low_count,
            "recent_sales": serialize_val(recent_sales),
            "chart_labels": chart_labels,
            "chart_data": chart_data,
            "low_stock_items": serialize_val(low_stock_items)
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


# =============================================================================
# 2. BILLING & POINT OF SALE (POS) API
# =============================================================================

@app.route("/api/billing/lookup", methods=["GET"])
def api_billing_lookup():
    """
    Look up product for POS by exact barcode or product name search.
    Only returns active products.
    """
    barcode = request.args.get("barcode", "").strip()
    query = request.args.get("query", "").strip()

    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        if barcode:
            prod = find_product(cursor, barcode)
            if prod:
                return jsonify({"status": "success", "found": True, "product": serialize_val(prod)})
            return jsonify({"status": "success", "found": False, "product": None, "message": "Product not found with this barcode."})

        if query:
            pattern = f"%{query}%"
            cursor.execute("""
                SELECT product_id, product_name, unit, selling_price, purchase_price, current_stock, barcode, is_active
                FROM products
                WHERE is_active = 1 AND (product_name LIKE %s OR barcode LIKE %s)
                ORDER BY product_name ASC
                LIMIT 10
            """, (pattern, pattern))
            matches = cursor.fetchall()
            return jsonify({"status": "success", "matches": serialize_val(matches)})

        return jsonify({"status": "error", "message": "Barcode or search query is required."}), 400

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route("/api/billing/checkout", methods=["POST"])
def api_billing_checkout():
    """
    Executes atomic sale checkout using billing_system.process_checkout.
    Prevents duplicate transactions, validates stock with FOR UPDATE lock,
    deducts inventory, records sale and sale_items.
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Invalid JSON payload."}), 400

    items_in = data.get("items", [])
    if not items_in:
        return jsonify({"status": "error", "message": "Shopping cart is empty."}), 400

    discount_raw = data.get("discount", 0)
    payment_method = str(data.get("payment_method", "Cash")).strip() or "Cash"
    notes = str(data.get("notes", "Web POS Sale")).strip()

    try:
        discount = Decimal(str(discount_raw or 0))
    except (InvalidOperation, TypeError):
        return jsonify({"status": "error", "message": "Discount must be a valid number."}), 400

    # Format cart dict for process_checkout
    cart = {}
    for it in items_in:
        pid = int(it.get("product_id"))
        qty = Decimal(str(it.get("quantity", 1)))
        price = Decimal(str(it.get("selling_price", it.get("price", 0))))
        cost = Decimal(str(it.get("purchase_price", it.get("cost", 0))))
        name = str(it.get("product_name", it.get("name", f"Product #{pid}")))
        unit = str(it.get("unit", "piece"))

        if qty <= Decimal("0"):
            return jsonify({"status": "error", "message": f"Invalid quantity for {name}."}), 400

        cart[pid] = {
            "product_id": pid,
            "name": name,
            "unit": unit,
            "price": price,
            "cost": cost,
            "quantity": qty
        }

    conn = None
    try:
        conn = get_db()
        result = process_checkout(conn, cart, discount=discount, payment_method=payment_method, notes=notes)
        return jsonify({
            "status": "success",
            "message": "Sale completed successfully!",
            "sale": serialize_val(result)
        })

    except ValueError as ve:
        return jsonify({"status": "error", "message": str(ve)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": f"Checkout failed: {str(e)}"}), 500
    finally:
        if conn and conn.is_connected():
            conn.close()


@app.route("/api/scanner/decode_frame", methods=["POST"])
def api_scanner_decode_frame():
    """
    Decodes barcode from base64 image frame using high-performance zxingcpp in Python.
    Provides 100% universal camera barcode decoding across all browsers and devices.
    """
    data = request.get_json(force=True, silent=True)
    if not data or "image" not in data:
        return jsonify({"status": "error", "message": "Image data required."}), 400

    b64_data = str(data["image"]).strip()
    if not b64_data:
        return jsonify({"status": "success", "found": False, "message": "Empty image payload."}), 200

    if "," in b64_data:
        b64_data = b64_data.split(",", 1)[1]

    try:
        raw_bytes = base64.b64decode(b64_data)
        if not raw_bytes:
            return jsonify({"status": "success", "found": False, "message": "Empty image data."}), 200
        arr = np.frombuffer(raw_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

        if img is None:
            return jsonify({"status": "success", "found": False, "message": "Could not decode image."}), 200

        if HAS_ZXING and zxingcpp is not None:
            res = zxingcpp.read_barcode(img)
            if not res:
                # Try center crop with high contrast for camera clarity
                h, w = img.shape[:2]
                cx, cy = w // 2, h // 2
                rw, rh = int(w * 0.8), int(h * 0.8)
                x1, y1 = max(0, cx - rw // 2), max(0, cy - rh // 2)
                x2, y2 = min(w, cx + rw // 2), min(h, cy + rh // 2)
                crop = img[y1:y2, x1:x2]
                res = zxingcpp.read_barcode(crop)

            if res and res.text:
                barcode_str = str(res.text).strip()
                if barcode_str:
                    return jsonify({
                        "status": "success",
                        "found": True,
                        "barcode": barcode_str,
                        "format": str(res.format)
                    })

        return jsonify({"status": "success", "found": False})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# =============================================================================
# 3. SMART PRODUCT LOOKUP API
# =============================================================================

@app.route("/api/lookup/tiered", methods=["GET"])
def api_lookup_tiered():
    """
    Executes 3-tier lookup:
    Tier 1: products (inventory)
    Tier 2: product_catalogue (master catalogue)
    Tier 3: Online APIs (Open Food Facts, Open Beauty Facts, Open Products Facts)
    Caches online results in product_catalogue without duplicates.
    """
    barcode = request.args.get("barcode", "").strip()
    if not barcode:
        return jsonify({"status": "error", "message": "Barcode is required."}), 400

    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        res = lookup_product_tiered(cursor, conn, barcode, allow_online=True)
        return jsonify({"status": "success", "result": serialize_val(res)})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route("/api/products/register", methods=["POST"])
def api_products_register():
    """
    Add a confirmed catalogue item or new item to the active shop inventory.
    Requires shopkeeper confirmation of selling price, purchase price, and initial stock.
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Invalid JSON body."}), 400

    product_name = str(data.get("product_name", "")).strip()
    if not product_name:
        return jsonify({"status": "error", "message": "Product name is required."}), 400

    try:
        selling_price = Decimal(str(data.get("selling_price", 0)))
        purchase_price = Decimal(str(data.get("purchase_price", 0)))
        current_stock = Decimal(str(data.get("current_stock", 0)))
        reorder_level = Decimal(str(data.get("reorder_level", 5)))
    except (InvalidOperation, TypeError):
        return jsonify({"status": "error", "message": "Prices and stock must be valid numbers."}), 400

    category = str(data.get("category", "General")).strip() or "General"
    unit = str(data.get("unit", "piece")).strip() or "piece"
    barcode = str(data.get("barcode", "")).strip() or None
    catalogue_id = data.get("catalogue_id")

    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        # Check if barcode already exists in products
        if barcode:
            cursor.execute("SELECT product_id, product_name FROM products WHERE barcode = %s", (barcode,))
            existing = cursor.fetchone()
            if existing:
                return jsonify({
                    "status": "error",
                    "message": f"A product with barcode '{barcode}' already exists: '{existing['product_name']}'."
                }), 400

        new_id = register_product_to_inventory(
            cursor=cursor,
            connection=conn,
            product_name=product_name,
            selling_price=selling_price,
            category=category,
            unit=unit,
            purchase_price=purchase_price,
            current_stock=current_stock,
            reorder_level=reorder_level,
            barcode=barcode,
            catalogue_id=catalogue_id
        )

        return jsonify({
            "status": "success",
            "message": f"Product '{product_name}' successfully added to inventory!",
            "product_id": new_id
        })

    except ValueError as ve:
        return jsonify({"status": "error", "message": str(ve)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


# =============================================================================
# 4. INVENTORY MANAGEMENT API
# =============================================================================

@app.route("/api/inventory", methods=["GET"])
def api_inventory_list():
    """
    List all products with search, category filter, and stock status filters.
    """
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    stock_filter = request.args.get("stock_filter", "all").strip()

    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT p.product_id, p.product_name, p.category, p.unit,
                   p.selling_price, p.purchase_price, p.current_stock,
                   p.reorder_level, p.barcode, p.is_active, p.catalogue_id,
                   c.brand, c.image_url
            FROM products p
            LEFT JOIN product_catalogue c ON c.catalogue_id = p.catalogue_id
            WHERE 1=1
        """
        params = []

        if search:
            query += " AND (p.product_name LIKE %s OR p.barcode LIKE %s OR c.brand LIKE %s)"
            pattern = f"%{search}%"
            params.extend([pattern, pattern, pattern])

        if category and category.lower() != "all":
            query += " AND p.category = %s"
            params.append(category)

        if stock_filter == "low_stock":
            query += " AND p.current_stock <= p.reorder_level AND p.current_stock > 0"
        elif stock_filter == "out_of_stock":
            query += " AND p.current_stock <= 0"
        elif stock_filter == "active":
            query += " AND p.is_active = 1"
        elif stock_filter == "inactive":
            query += " AND p.is_active = 0"

        query += " ORDER BY p.product_name ASC"

        cursor.execute(query, tuple(params))
        products = cursor.fetchall()

        # Get list of unique categories
        cursor.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != '' ORDER BY category ASC")
        categories = [r["category"] for r in cursor.fetchall()]

        return jsonify({
            "status": "success",
            "count": len(products),
            "products": serialize_val(products),
            "categories": categories
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route("/api/inventory/update/<int:product_id>", methods=["POST"])
def api_inventory_update(product_id):
    """Update existing product details."""
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Invalid JSON body."}), 400

    name = str(data.get("product_name", "")).strip()
    category = str(data.get("category", "")).strip()
    unit = str(data.get("unit", "piece")).strip()
    barcode = str(data.get("barcode", "")).strip() or None

    try:
        selling_price = Decimal(str(data.get("selling_price", 0)))
        purchase_price = Decimal(str(data.get("purchase_price", 0)))
        current_stock = Decimal(str(data.get("current_stock", 0)))
        reorder_level = Decimal(str(data.get("reorder_level", 5)))
        is_active = 1 if int(data.get("is_active", 1)) else 0
    except (InvalidOperation, TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid numerical values provided."}), 400

    if not name:
        return jsonify({"status": "error", "message": "Product name cannot be empty."}), 400
    if selling_price <= Decimal("0"):
        return jsonify({"status": "error", "message": "Selling price must be greater than zero."}), 400
    if purchase_price < Decimal("0") or current_stock < Decimal("0"):
        return jsonify({"status": "error", "message": "Cost and stock cannot be negative."}), 400

    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        # Check unique barcode if changed
        if barcode:
            cursor.execute(
                "SELECT product_id FROM products WHERE barcode = %s AND product_id != %s",
                (barcode, product_id)
            )
            if cursor.fetchone():
                return jsonify({"status": "error", "message": f"Barcode '{barcode}' is already in use by another product."}), 400

        update_sql = """
            UPDATE products
            SET product_name = %s, category = %s, unit = %s,
                selling_price = %s, purchase_price = %s, current_stock = %s,
                reorder_level = %s, barcode = %s, is_active = %s
            WHERE product_id = %s
        """
        cursor.execute(
            update_sql,
            (name, category, unit, selling_price, purchase_price, current_stock, reorder_level, barcode, is_active, product_id)
        )
        conn.commit()

        return jsonify({"status": "success", "message": f"Product #{product_id} updated successfully!"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route("/api/inventory/toggle-status/<int:product_id>", methods=["POST"])
def api_inventory_toggle_status(product_id):
    """Toggle is_active between 1 and 0."""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT is_active, product_name FROM products WHERE product_id = %s", (product_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"status": "error", "message": "Product not found."}), 404

        new_status = 0 if row["is_active"] == 1 else 1
        cursor.execute("UPDATE products SET is_active = %s WHERE product_id = %s", (new_status, product_id))
        conn.commit()

        status_label = "activated" if new_status == 1 else "deactivated"
        return jsonify({
            "status": "success",
            "message": f"Product '{row['product_name']}' {status_label}.",
            "new_status": new_status
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route("/api/catalogue", methods=["GET"])
def api_catalogue_list():
    """List master catalogue items."""
    search = request.args.get("search", "").strip()
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT c.catalogue_id, c.barcode, c.product_name, c.brand, c.category,
                   c.package_size, c.image_url, c.source,
                   (SELECT COUNT(*) FROM products p WHERE p.catalogue_id = c.catalogue_id) AS in_inventory
            FROM product_catalogue c
            WHERE 1=1
        """
        params = []
        if search:
            query += " AND (c.product_name LIKE %s OR c.barcode LIKE %s OR c.brand LIKE %s)"
            pattern = f"%{search}%"
            params.extend([pattern, pattern, pattern])

        query += " ORDER BY c.product_name ASC LIMIT 50"
        cursor.execute(query, tuple(params))
        items = cursor.fetchall()

        return jsonify({"status": "success", "count": len(items), "items": serialize_val(items)})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


# =============================================================================
# 5. SALES & PURCHASES API
# =============================================================================

@app.route("/api/sales", methods=["GET"])
def api_sales_history():
    """Retrieve historical sales with date range and search filtering."""
    start_date_str = request.args.get("start_date", "").strip()
    end_date_str = request.args.get("end_date", "").strip()
    payment_method = request.args.get("payment_method", "").strip()

    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT s.sale_id, s.sale_date, s.total_amount, s.discount, s.payment_method, s.notes,
                   COUNT(si.sale_item_id) AS item_count,
                   COALESCE(SUM(si.quantity), 0) AS total_units_sold
            FROM sales s
            LEFT JOIN sale_items si ON si.sale_id = s.sale_id
            WHERE 1=1
        """
        params = []

        if start_date_str:
            query += " AND s.sale_date >= %s"
            params.append(start_date_str)
        if end_date_str:
            # End date inclusive
            query += " AND s.sale_date <= %s"
            params.append(end_date_str + " 23:59:59")
        if payment_method and payment_method.lower() != "all":
            query += " AND LOWER(s.payment_method) = LOWER(%s)"
            params.append(payment_method)

        query += " GROUP BY s.sale_id, s.sale_date, s.total_amount, s.discount, s.payment_method, s.notes"
        query += " ORDER BY s.sale_id DESC LIMIT 100"

        cursor.execute(query, tuple(params))
        sales = cursor.fetchall()

        return jsonify({"status": "success", "count": len(sales), "sales": serialize_val(sales)})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route("/api/sales/<int:sale_id>", methods=["GET"])
def api_sale_detail(sale_id):
    """Retrieve line items for a specific sale."""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM sales WHERE sale_id = %s", (sale_id,))
        sale = cursor.fetchone()
        if not sale:
            return jsonify({"status": "error", "message": "Sale record not found."}), 404

        cursor.execute("""
            SELECT si.sale_item_id, si.product_id, si.quantity, si.unit_price, si.unit_cost,
                   p.product_name, p.unit, p.category,
                   (si.quantity * si.unit_price) AS line_total
            FROM sale_items si
            LEFT JOIN products p ON p.product_id = si.product_id
            WHERE si.sale_id = %s
            ORDER BY si.sale_item_id ASC
        """, (sale_id,))
        items = cursor.fetchall()

        return jsonify({
            "status": "success",
            "sale": serialize_val(sale),
            "items": serialize_val(items)
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route("/api/purchases", methods=["GET"])
def api_purchases_list():
    """List supplier purchases."""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT p.purchase_id, p.supplier_name, p.purchase_date, p.total_amount, p.notes,
                   COUNT(pi.purchase_item_id) AS item_count
            FROM purchases p
            LEFT JOIN purchase_items pi ON pi.purchase_id = p.purchase_id
            GROUP BY p.purchase_id, p.supplier_name, p.purchase_date, p.total_amount, p.notes
            ORDER BY p.purchase_date DESC, p.purchase_id DESC
            LIMIT 50
        """)
        purchases = cursor.fetchall()

        return jsonify({"status": "success", "purchases": serialize_val(purchases)})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route("/api/purchases/add", methods=["POST"])
def api_purchase_add():
    """Record a supplier purchase invoice and replenish stock."""
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Invalid JSON body."}), 400

    supplier_name = str(data.get("supplier_name", "")).strip() or "General Supplier"
    purchase_date = str(data.get("purchase_date", date.today().isoformat())).strip()
    notes = str(data.get("notes", "")).strip()
    items = data.get("items", [])

    if not items:
        return jsonify({"status": "error", "message": "At least one product item is required for a purchase invoice."}), 400

    total_amount = Decimal("0")
    validated_items = []
    for it in items:
        pid = int(it.get("product_id"))
        qty = Decimal(str(it.get("quantity", 0)))
        cost = Decimal(str(it.get("unit_cost", 0)))

        if qty <= Decimal("0") or cost < Decimal("0"):
            return jsonify({"status": "error", "message": "Quantity must be > 0 and unit cost cannot be negative."}), 400

        total_amount += qty * cost
        validated_items.append((pid, qty, cost))

    conn = None
    cursor = None
    try:
        conn = get_db()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            INSERT INTO purchases (supplier_name, purchase_date, total_amount, notes)
            VALUES (%s, %s, %s, %s)
        """, (supplier_name, purchase_date, total_amount, notes))
        purchase_id = cursor.lastrowid

        for pid, qty, cost in validated_items:
            cursor.execute("""
                INSERT INTO purchase_items (purchase_id, product_id, quantity, unit_cost)
                VALUES (%s, %s, %s, %s)
            """, (purchase_id, pid, qty, cost))

            # Update product stock & optionally purchase_price
            cursor.execute("""
                UPDATE products
                SET current_stock = current_stock + %s,
                    purchase_price = %s
                WHERE product_id = %s
            """, (qty, cost, pid))

        conn.commit()

        return jsonify({
            "status": "success",
            "message": f"Purchase invoice #{purchase_id} recorded successfully! Stock updated.",
            "purchase_id": purchase_id,
            "total_amount": float(total_amount)
        })

    except Exception as e:
        if conn and conn.is_connected():
            conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route("/api/expenses", methods=["GET"])
def api_expenses_list():
    """List operational expenses."""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT expense_id, expense_date, category, amount, description, created_at
            FROM expenses
            ORDER BY expense_date DESC, expense_id DESC
            LIMIT 50
        """)
        expenses = cursor.fetchall()

        return jsonify({"status": "success", "expenses": serialize_val(expenses)})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route("/api/expenses/add", methods=["POST"])
def api_expense_add():
    """Record a shop operational expense."""
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Invalid JSON body."}), 400

    category = str(data.get("category", "")).strip() or "General"
    description = str(data.get("description", "")).strip()
    expense_date = str(data.get("expense_date", date.today().isoformat())).strip()

    try:
        amount = Decimal(str(data.get("amount", 0)))
    except (InvalidOperation, TypeError):
        return jsonify({"status": "error", "message": "Amount must be a valid number."}), 400

    if amount <= Decimal("0"):
        return jsonify({"status": "error", "message": "Expense amount must be greater than zero."}), 400

    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            INSERT INTO expenses (expense_date, category, amount, description)
            VALUES (%s, %s, %s, %s)
        """, (expense_date, category, amount, description))
        conn.commit()
        expense_id = cursor.lastrowid

        return jsonify({
            "status": "success",
            "message": f"Expense entry #{expense_id} recorded successfully!",
            "expense_id": expense_id
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


# =============================================================================
# 6. PROFIT & LOSS REPORTS API
# =============================================================================

@app.route("/api/reports/financial", methods=["GET"])
def api_financial_report():
    """
    Computes exact P&L metrics: Revenue, Discounts, COGS, Gross Profit, Expenses, Net Profit
    and active low-stock alerts using daily_report.calculate_financial_report.
    Supports daily, monthly, yearly, or custom date ranges.
    """
    period_type = request.args.get("period_type", "daily").lower()
    selected_date = request.args.get("date", "").strip()
    selected_month = request.args.get("month", "").strip()
    selected_year = request.args.get("year", "").strip()
    custom_start = request.args.get("start_date", "").strip()
    custom_end = request.args.get("end_date", "").strip()

    today = date.today()

    try:
        if period_type == "daily":
            if selected_date:
                dt = datetime.strptime(selected_date, "%Y-%m-%d").date()
            else:
                dt = today
            start_date = dt
            end_date = dt + timedelta(days=1)
            title = f"Daily Financial Report - {dt.strftime('%d %B %Y')}"

        elif period_type == "monthly":
            if selected_month:
                parts = selected_month.split("-")
                y = int(parts[0])
                m = int(parts[1])
            else:
                y = today.year
                m = today.month
            start_date = date(y, m, 1)
            end_date = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
            title = f"Monthly Financial Report - {start_date.strftime('%B %Y')}"

        elif period_type == "yearly":
            if selected_year:
                y = int(selected_year)
            else:
                y = today.year
            start_date = date(y, 1, 1)
            end_date = date(y + 1, 1, 1)
            title = f"Yearly Financial Report - {y}"

        elif period_type == "custom" and custom_start and custom_end:
            start_date = datetime.strptime(custom_start, "%Y-%m-%d").date()
            end_date = datetime.strptime(custom_end, "%Y-%m-%d").date() + timedelta(days=1)
            title = f"Custom Report ({custom_start} to {custom_end})"

        else:
            start_date = today
            end_date = today + timedelta(days=1)
            title = f"Daily Report - {today}"

    except Exception as e:
        return jsonify({"status": "error", "message": f"Invalid date parameters: {e}"}), 400

    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        report = calculate_financial_report(cursor, start_date, end_date)

        # Retrieve low stock alerts
        cursor.execute("""
            SELECT product_id, product_name, category, unit, current_stock, reorder_level
            FROM products
            WHERE is_active = 1 AND current_stock <= reorder_level
            ORDER BY current_stock ASC
        """)
        low_stock_alerts = cursor.fetchall()

        # Retrieve top categories for the period
        cursor.execute("""
            SELECT p.category, SUM(si.quantity) AS qty, SUM(si.quantity * si.unit_price) AS rev
            FROM sale_items si
            JOIN sales s ON s.sale_id = si.sale_id
            JOIN products p ON p.product_id = si.product_id
            WHERE s.sale_date >= %s AND s.sale_date < %s
            GROUP BY p.category
            ORDER BY rev DESC
        """, (start_date, end_date))
        period_categories = cursor.fetchall()

        return jsonify({
            "status": "success",
            "title": title,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "report": serialize_val(report),
            "low_stock_alerts": serialize_val(low_stock_alerts),
            "categories": serialize_val(period_categories)
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


# =============================================================================
# 7 & 8. GEMMA AI CHATBOT & VOICE ASSISTANT API
# =============================================================================

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Handles natural language questions from text input or speech recognition.
    Pre-resolves verified database metrics, queries Gemma API with conversation history,
    and falls back to exact direct SQL results if Gemma servers are busy.
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Invalid JSON body."}), 400

    message = str(data.get("message", "")).strip()
    if not message:
        return jsonify({"status": "error", "message": "Question cannot be empty."}), 400

    lang_req = str(data.get("language", "en-IN")).strip().lower()
    target_lang = "en-IN"
    if "te" in lang_req or "telugu" in lang_req:
        target_lang = "te-IN"
    elif "hi" in lang_req or "hindi" in lang_req:
        target_lang = "hi-IN"

    history = data.get("history", [])

    conn = None
    try:
        conn = get_db()
        answer = ask_shopkeeper_assistant(message, connection=conn, history=history, language=target_lang)
        speech_text = clean_speech_text(answer, language=target_lang)
        return jsonify({
            "status": "success",
            "question": message,
            "response": answer,
            "speech_text": speech_text,
            "language": target_lang
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"AI Assistant encountered an error: {str(e)}"
        }), 500
    finally:
        if conn and conn.is_connected():
            conn.close()


@app.route("/api/voice/process", methods=["POST"])
def api_voice_process():
    """
    Dedicated voice-to-voice processing endpoint:
    Receives transcribed user speech, resolves business facts via safe parameterized queries,
    prompts Gemma for a natural spoken answer strictly in the requested language,
    and returns both formatted display_text and audio-clean speech_text with playback metadata.
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Invalid JSON body."}), 400

    transcript = str(data.get("transcript", "") or data.get("message", "")).strip()
    if not transcript:
        return jsonify({
            "status": "error",
            "message": "Transcript cannot be empty."
        }), 400

    lang_req = str(data.get("language", "en-IN")).strip().lower()
    target_lang = "en-IN"
    if "te" in lang_req or "telugu" in lang_req:
        target_lang = "te-IN"
    elif "hi" in lang_req or "hindi" in lang_req:
        target_lang = "hi-IN"

    history = data.get("history", [])

    conn = None
    try:
        conn = get_db()
        result = process_voice_query(transcript, language=target_lang, connection=conn, history=history)
        result["language"] = target_lang
        status_code = 200 if result.get("status") == "success" else 400
        return jsonify(result), status_code

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Voice processing error: {str(e)}"
        }), 500
    finally:
        if conn and conn.is_connected():
            conn.close()


@app.route("/api/tts", methods=["GET", "POST"])
def api_tts():
    """
    Synthesizes speech audio (MP3) using gTTS for crystal-clear regional pronunciation
    in Telugu (te), Hindi (hi), and Indian English (en).
    """
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        text = str(data.get("text", "")).strip()
        lang = str(data.get("language", data.get("lang", "en"))).strip().lower()
    else:
        text = str(request.args.get("text", "")).strip()
        lang = str(request.args.get("language", request.args.get("lang", "en"))).strip().lower()

    if not text:
        return jsonify({"status": "error", "message": "Text parameter is required."}), 400

    # Clean text to ensure proper spoken pronunciation
    clean_text = clean_speech_text(text, language=lang)
    if not clean_text:
        clean_text = text

    # Map language codes
    target_lang = "en"
    tld = "co.in"
    if "te" in lang or "telugu" in lang:
        target_lang = "te"
        tld = "com"
    elif "hi" in lang or "hindi" in lang:
        target_lang = "hi"
        tld = "com"
    else:
        # Detect Telugu or Devanagari characters in text directly if language was passed as default
        has_telugu = any("\u0C00" <= ch <= "\u0C7F" for ch in clean_text)
        has_hindi = any("\u0900" <= ch <= "\u097F" for ch in clean_text)
        if has_telugu:
            target_lang = "te"
            tld = "com"
        elif has_hindi:
            target_lang = "hi"
            tld = "com"

    try:
        fp = io.BytesIO()
        # Cap text length to prevent excessive payload
        tts = gTTS(text=clean_text[:600], lang=target_lang, tld=tld)
        tts.write_to_fp(fp)
        fp.seek(0)
        return send_file(
            fp,
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name="speech.mp3"
        )
    except Exception as e:
        return jsonify({"status": "error", "message": f"TTS generation failed: {str(e)}"}), 500


# =============================================================================
# 9. SALES ANALYTICS API
# =============================================================================

@app.route("/api/analytics/summary", methods=["GET"])
def api_analytics_summary():
    """
    Provides comprehensive analytics:
    - Best-selling products
    - Slow-moving products
    - Sales trends (last 7 and 30 days)
    - Category-wise sales distribution
    - Period comparisons (This Month vs Last Month)
    """
    conn = None
    try:
        conn = get_db()

        best_selling = get_best_selling_products(conn, limit=10)
        slow_moving = get_slow_moving_products(conn, limit=10)
        seven_days_trend = get_sales_trends(conn, days=7)
        thirty_days_trend = get_sales_trends(conn, days=30)

        cursor = conn.cursor(dictionary=True)

        # Category sales distribution
        cursor.execute("""
            SELECT p.category,
                   SUM(si.quantity) AS total_units,
                   SUM(si.quantity * si.unit_price) AS total_revenue
            FROM sale_items si
            JOIN products p ON p.product_id = si.product_id
            GROUP BY p.category
            ORDER BY total_revenue DESC
        """)
        category_distribution = cursor.fetchall()

        # Monthly comparison
        today = date.today()
        first_this_month = date(today.year, today.month, 1)
        first_next_month = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)

        last_month_end = first_this_month
        last_month_start = (first_this_month - timedelta(days=1)).replace(day=1)

        this_month_data = calculate_financial_report(cursor, first_this_month, first_next_month)
        last_month_data = calculate_financial_report(cursor, last_month_start, last_month_end)

        cursor.close()

        return jsonify({
            "status": "success",
            "best_selling": serialize_val(best_selling),
            "slow_moving": serialize_val(slow_moving),
            "seven_days_trend": serialize_val(seven_days_trend),
            "thirty_days_trend": serialize_val(thirty_days_trend),
            "category_distribution": serialize_val(category_distribution),
            "this_month": serialize_val(this_month_data),
            "last_month": serialize_val(last_month_data)
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn and conn.is_connected():
            conn.close()


# =============================================================================
# 10. SETTINGS & SYSTEM HEALTH API
# =============================================================================

@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    """Retrieve current shop settings and safe system health."""
    settings = load_settings()

    # Safe system health check without exposing keys
    health = {
        "database_connected": False,
        "database_name": os.getenv("DB_NAME", "shopkeeper_ai"),
        "tables_count": 0,
        "active_products": 0,
        "gemma_configured": bool(os.getenv("GEMINI_API_KEY")),
        "model_name": "gemma-4-31b-it"
    }

    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        health["database_connected"] = True
        health["tables_count"] = len(tables)

        cursor.execute("SELECT COUNT(*) FROM products WHERE is_active = 1")
        health["active_products"] = cursor.fetchone()[0]
        cursor.close()
    except Exception as err:
        health["database_error"] = str(err)
    finally:
        if conn and conn.is_connected():
            conn.close()

    return jsonify({
        "status": "success",
        "settings": settings,
        "system_health": health
    })


@app.route("/api/settings", methods=["POST"])
def api_update_settings():
    """Update shop settings."""
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Invalid JSON body."}), 400

    current = load_settings()
    for key in current.keys():
        if key in data:
            current[key] = data[key]

    save_settings(current)
    return jsonify({
        "status": "success",
        "message": "Settings saved successfully!",
        "settings": current
    })


# =============================================================================
# START APPLICATION SERVER
# =============================================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"\n=======================================================")
    print(f"  AI SHOPKEEPER ASSISTANT - WEB APPLICATION STARTED")
    print(f"  URL: http://127.0.0.1:{port}")
    print(f"  Database: {os.getenv('DB_NAME', 'shopkeeper_ai')} on MySQL")
    print(f"  Gemma Model: gemma-4-31b-it")
    print(f"=======================================================\n")
    app.run(host="127.0.0.1", port=port, debug=False)
