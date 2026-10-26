import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

import mysql.connector
from dotenv import load_dotenv

# Ensure .env is loaded from the project directory
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

from daily_report import calculate_financial_report


def get_db_connection():
    """
    Create and return a MySQL database connection using .env configuration.
    Supports either individual variables (DB_HOST, etc.) or connection URI (DATABASE_URL).
    """
    db_url = os.getenv("DATABASE_URL") or os.getenv("MYSQL_URL")
    if db_url:
        import urllib.parse
        parsed = urllib.parse.urlparse(db_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 3306
        user = parsed.username or "root"
        password = urllib.parse.unquote(parsed.password or "")
        database = parsed.path.lstrip("/") or "shopkeeper_ai"
    else:
        host = os.getenv("DB_HOST", "localhost")
        port = int(os.getenv("DB_PORT", "3306"))
        user = os.getenv("DB_USER", "root")
        password = os.getenv("DB_PASSWORD", "")
        database = os.getenv("DB_NAME", "shopkeeper_ai")

    conn_kwargs = {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
        "connection_timeout": int(os.getenv("DB_TIMEOUT", "10"))
    }

    ssl_ca = os.getenv("DB_SSL_CA")
    if ssl_ca and os.path.exists(ssl_ca):
        conn_kwargs["ssl_ca"] = ssl_ca
    if os.getenv("DB_SSL_DISABLED", "false").lower() in ("true", "1"):
        conn_kwargs["ssl_disabled"] = True

    return mysql.connector.connect(**conn_kwargs)


def parse_date_period(query_text):
    """
    Identify time periods from natural language in English and Telugu.
    Returns (period_name, start_date, end_date_exclusive).
    """
    q = query_text.lower()
    today = date.today()

    # Check for YYYY-MM-DD or YYYY-MM pattern
    iso_date_match = re.search(r"\b(20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b", q)
    if iso_date_match:
        dt = datetime.strptime(iso_date_match.group(0), "%Y-%m-%d").date()
        return f"DATE: {dt}", dt, dt + timedelta(days=1)

    iso_month_match = re.search(r"\b(20\d{2})-(0[1-9]|1[0-2])\b", q)
    if iso_month_match:
        year = int(iso_month_match.group(1))
        month = int(iso_month_match.group(2))
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        return f"MONTH: {start.strftime('%B %Y')}", start, end

    # Yesterday / నిన్న / कल
    if any(w in q for w in ["yesterday", "previous day", "నిన్న", "कल", "बीता कल"]):
        yesterday = today - timedelta(days=1)
        return "YESTERDAY", yesterday, today

    # Last month / పోయిన నెల / గత నెల / पिछला महीना
    if any(w in q for w in ["last month", "previous month", "గత నెల", "పోయిన నెల", "पिछला महीना", "पिछले महीने"]):
        first_of_this_month = today.replace(day=1)
        last_day_of_last_month = first_of_this_month - timedelta(days=1)
        start = last_day_of_last_month.replace(day=1)
        return "LAST_MONTH", start, first_of_this_month

    # This month / monthly / ఈ నెల / इस महीने
    if any(w in q for w in ["this month", "monthly", "current month", "month", "ఈ నెల", "నెలవారీ", "నెల", "इस महीने", "इस माह"]):
        start = today.replace(day=1)
        end = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)
        return "THIS_MONTH", start, end

    # Last year / గత సంవత్సరం / पिछला साल
    if any(w in q for w in ["last year", "previous year", "పోయిన సంవత్సరం", "గత సంవత్సరం", "पिछले साल", "पिछला साल"]):
        start = date(today.year - 1, 1, 1)
        end = date(today.year, 1, 1)
        return "LAST_YEAR", start, end

    # This year / yearly / annual / ఈ సంవత్సరం / इस साल
    if any(w in q for w in ["this year", "yearly", "annual", "current year", "year", "ఈ సంవత్సరం", "సంవత్సరం", "इस साल", "इस वर्ष"]):
        start = date(today.year, 1, 1)
        end = date(today.year + 1, 1, 1)
        return "THIS_YEAR", start, end

    # Default to TODAY / ఈ రోజు / आज
    return "TODAY", today, today + timedelta(days=1)


def get_financial_summary(connection, start_date, end_date, period_label="TODAY"):
    """
    Calculate financial metrics by reusing the verified reporting calculation from daily_report.py.
    Guarantees 100% consistency between daily_report.py and chatbot responses.
    """
    cursor = connection.cursor(dictionary=True)
    try:
        report = calculate_financial_report(cursor, start_date, end_date)

        bills = report["number_of_bills"]
        sales = report["total_sales"]
        discounts = report["total_discount"]
        cost = report["cost_of_goods"]
        expenses = report["total_expenses"]
        gross_profit = report["gross_profit"]
        net_profit = report["net_profit"]
        has_sales = report["has_sales"]

        if has_sales:
            db_status = f"CONFIRMED_DATA: Found {bills} recorded sales transaction(s) for {period_label}."
        else:
            db_status = f"CONFIRMED_DATA: Exactly 0 sales transactions are recorded in the database for {period_label}."

        return {
            "period": period_label,
            "start_date": str(start_date),
            "end_date_exclusive": str(end_date),
            "number_of_bills": bills,
            "total_sales_after_discounts": f"Rs. {sales:.2f}",
            "discounts_given": f"Rs. {discounts:.2f}",
            "cost_of_goods_sold": f"Rs. {cost:.2f}",
            "gross_profit": f"Rs. {gross_profit:.2f}",
            "operating_expenses": f"Rs. {expenses:.2f}",
            "net_profit": f"Rs. {net_profit:.2f}",
            "is_profitable": net_profit >= 0,
            "has_sales": has_sales,
            "database_verification": db_status
        }
    finally:
        cursor.close()


def get_best_selling_products(connection, limit=5):
    """Retrieve top selling products by quantity and revenue."""
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
                p.product_id,
                p.product_name,
                p.category,
                p.unit,
                SUM(si.quantity) AS total_quantity_sold,
                SUM(si.quantity * si.unit_price) AS total_revenue
            FROM sale_items si
            JOIN products p ON p.product_id = si.product_id
            GROUP BY si.product_id, p.product_name, p.category, p.unit
            ORDER BY total_quantity_sold DESC, total_revenue DESC
            LIMIT %s
            """,
            (limit,)
        )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append({
                "product_name": r["product_name"],
                "category": r["category"] or "General",
                "quantity_sold": f"{Decimal(str(r['total_quantity_sold']))} {r['unit']}",
                "revenue": f"Rs. {Decimal(str(r['total_revenue'])):.2f}"
            })
        return {
            "top_products": result,
            "best_selling_products": result,
            "total_found": len(result),
            "has_sales_history": len(result) > 0,
            "database_verification": f"Found {len(result)} best-selling products recorded in sale_items." if result else "No sale items recorded yet."
        }
    finally:
        cursor.close()


def get_slow_moving_products(connection, limit=5):
    """
    Retrieve active products that have lowest or zero sales.
    Checks whether sufficient sales history exists.
    """
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COUNT(*) AS count FROM sales")
        total_sales_count = cursor.fetchone()["count"]

        if total_sales_count == 0:
            return {
                "slow_moving_products": [],
                "sufficient_history": False,
                "message": "No sales have been recorded yet in the database to evaluate slow-moving products."
            }

        cursor.execute(
            """
            SELECT
                p.product_id,
                p.product_name,
                p.unit,
                p.current_stock,
                p.selling_price,
                COALESCE(SUM(si.quantity), 0) AS total_quantity_sold
            FROM products p
            LEFT JOIN sale_items si ON si.product_id = p.product_id
            WHERE p.is_active = 1
            GROUP BY p.product_id, p.product_name, p.unit, p.current_stock, p.selling_price
            ORDER BY total_quantity_sold ASC, p.current_stock DESC
            LIMIT %s
            """,
            (limit,)
        )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append({
                "product_name": r["product_name"],
                "in_stock": f"{Decimal(str(r['current_stock']))} {r['unit']}",
                "price": f"Rs. {Decimal(str(r['selling_price'])):.2f}",
                "quantity_sold": f"{Decimal(str(r['total_quantity_sold']))} {r['unit']}"
            })
        return {
            "slow_moving_products": result,
            "sufficient_history": True,
            "total_sales_in_db": total_sales_count
        }
    finally:
        cursor.close()


def get_low_stock_products(connection):
    """Retrieve all active products currently at or below their reorder level."""
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
                product_id,
                product_name,
                category,
                unit,
                current_stock,
                reorder_level
            FROM products
            WHERE is_active = 1
              AND current_stock <= reorder_level
            ORDER BY current_stock ASC
            """
        )
        rows = cursor.fetchall()
        alerts = []
        for r in rows:
            stock = Decimal(str(r["current_stock"]))
            alerts.append({
                "product_name": r["product_name"],
                "current_stock": f"{stock} {r['unit']}",
                "reorder_level": f"{Decimal(str(r['reorder_level']))} {r['unit']}",
                "urgency": "CRITICAL - OUT OF STOCK" if stock <= 0 else "LOW STOCK"
            })
        return {
            "low_stock_count": len(alerts),
            "alerts": alerts,
            "low_stock_products": alerts,
            "needs_restocking": len(alerts) > 0,
            "database_verification": f"Found {len(alerts)} product(s) needing restocking." if alerts else "All products currently have sufficient stock above reorder levels."
        }
    finally:
        cursor.close()


def get_inventory_summary(connection):
    """Retrieve full inventory statistics and active products."""
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
                product_id,
                product_name,
                category,
                unit,
                selling_price,
                purchase_price,
                current_stock,
                barcode
            FROM products
            WHERE is_active = 1
            ORDER BY product_name ASC
            """
        )
        products = cursor.fetchall()

        total_cost_val = Decimal("0")
        total_retail_val = Decimal("0")
        items = []

        for p in products:
            stock = Decimal(str(p["current_stock"] or 0))
            sp = Decimal(str(p["selling_price"] or 0))
            cp = Decimal(str(p["purchase_price"] or 0))
            total_cost_val += stock * cp
            total_retail_val += stock * sp

            items.append({
                "name": p["product_name"],
                "barcode": p["barcode"] or "None",
                "stock": f"{stock} {p['unit']}",
                "price": f"Rs. {sp:.2f}",
                "category": p["category"] or "General"
            })

        return {
            "total_active_products": len(products),
            "total_inventory_value_at_cost": f"Rs. {total_cost_val:.2f}",
            "potential_sales_value": f"Rs. {total_retail_val:.2f}",
            "items": items
        }
    finally:
        cursor.close()


def get_product_price_info(connection, search_term):
    """Search price and availability for specific product names or barcodes."""
    cursor = connection.cursor(dictionary=True)
    try:
        pattern = f"%{search_term.strip()}%"
        cursor.execute(
            """
            SELECT
                product_id,
                product_name,
                category,
                unit,
                selling_price,
                purchase_price,
                current_stock,
                barcode
            FROM products
            WHERE is_active = 1
              AND (product_name LIKE %s OR barcode = %s)
            LIMIT 5
            """,
            (pattern, search_term.strip())
        )
        rows = cursor.fetchall()
        matches = []
        for r in rows:
            matches.append({
                "product_name": r["product_name"],
                "barcode": r["barcode"] or "None",
                "selling_price": f"Rs. {Decimal(str(r['selling_price'])):.2f}",
                "unit": r["unit"],
                "available_stock": f"{Decimal(str(r['current_stock']))} {r['unit']}",
                "category": r["category"] or "General"
            })
        return {
            "search_term": search_term,
            "found_count": len(matches),
            "matches": matches,
            "database_verification": f"Found {len(matches)} matching product(s)." if matches else f"No active product found matching '{search_term}'."
        }
    finally:
        cursor.close()


def get_expenses_breakdown(connection, start_date, end_date, period_label="THIS_MONTH"):
    """Retrieve operating expenses grouped by category for a period."""
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
                category,
                SUM(amount) AS category_total,
                COUNT(*) AS count
            FROM expenses
            WHERE expense_date >= %s AND expense_date < %s
            GROUP BY category
            ORDER BY category_total DESC
            """,
            (start_date, end_date)
        )
        rows = cursor.fetchall()
        breakdown = []
        grand_total = Decimal("0")
        for r in rows:
            amt = Decimal(str(r["category_total"]))
            grand_total += amt
            breakdown.append({
                "category": r["category"],
                "amount": f"Rs. {amt:.2f}",
                "entries": int(r["count"])
            })

        has_expenses = len(breakdown) > 0
        return {
            "period": period_label,
            "total_expenses": f"Rs. {grand_total:.2f}",
            "categories": breakdown,
            "has_expenses_recorded": has_expenses,
            "database_verification": f"Found {len(breakdown)} expense category entries totaling Rs. {grand_total:.2f}." if has_expenses else "Exactly 0 expenses are recorded in the database for this period."
        }
    finally:
        cursor.close()


def get_purchase_history(connection, limit=5):
    """Retrieve supplier purchase history if recorded in the database."""
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
                p.purchase_id,
                p.supplier_name,
                p.purchase_date,
                p.total_amount,
                p.notes
            FROM purchases p
            ORDER BY p.purchase_date DESC, p.purchase_id DESC
            LIMIT %s
            """,
            (limit,)
        )
        rows = cursor.fetchall()
        purchases = []
        for r in rows:
            purchases.append({
                "purchase_id": r["purchase_id"],
                "supplier": r["supplier_name"] or "Unknown Supplier",
                "date": str(r["purchase_date"]),
                "amount": f"Rs. {Decimal(str(r['total_amount'])):.2f}",
                "notes": r["notes"] or ""
            })
        has_purchases = len(purchases) > 0
        return {
            "recent_purchases": purchases,
            "has_purchase_records": has_purchases,
            "total_records_found": len(purchases),
            "database_verification": f"Found {len(purchases)} purchase record(s)." if has_purchases else "Exactly 0 purchase records are currently stored in the purchases table."
        }
    finally:
        cursor.close()


def get_sales_trends(connection, days=7):
    """Retrieve daily sales breakdown over the last N days to evaluate trends."""
    cursor = connection.cursor(dictionary=True)
    try:
        start_date = date.today() - timedelta(days=days)
        cursor.execute(
            """
            SELECT
                DATE(sale_date) AS day,
                COUNT(*) AS bills,
                COALESCE(SUM(total_amount), 0) AS daily_sales
            FROM sales
            WHERE sale_date >= %s
            GROUP BY DATE(sale_date)
            ORDER BY day ASC
            """,
            (start_date,)
        )
        rows = cursor.fetchall()
        daily_breakdown = []
        for r in rows:
            daily_breakdown.append({
                "date": str(r["day"]),
                "bills": int(r["bills"]),
                "sales": f"Rs. {Decimal(str(r['daily_sales'])):.2f}"
            })

        has_sufficient_trend = len(daily_breakdown) >= 3

        return {
            "days_evaluated": days,
            "active_sales_days_found": len(daily_breakdown),
            "daily_trend": daily_breakdown,
            "sufficient_history_for_trend": has_sufficient_trend,
            "note": "More days of historical transactions will provide stronger trend forecasting." if not has_sufficient_trend else "Adequate historical data."
        }
    finally:
        cursor.close()


def resolve_business_data_for_question(connection, question, conversation_history=None):
    """
    Intelligently inspects the question and retrieves verified data from MySQL.
    Supports English, Telugu, and Hindi natural language queries.
    Guarantees that ANY inquiry regarding store status, profit, sales, or performance
    is grounded in live database queries, preventing hallucinated 0-sales reports.
    Also handles greetings and casual conversational interactions without forcing fake data.
    """
    q = question.lower().strip()
    cleaned_q = re.sub(r"[!?,.\s]+", " ", q).strip()

    # 0. Greetings, pleasantries & casual conversational queries
    greetings = [
        "hello", "hi", "hey", "namaste", "namaskar", "namaskaram", "good morning",
        "good afternoon", "good evening", "how are you", "who are you", "what can you do",
        "tell me about yourself", "who made you",
        "హలో", "నమస్తే", "నమస్కారం", "బాగున్నారా", "ఎలా ఉన్నారు", "నువ్వు ఎవరు", "నువ్వేం చేయగలవు",
        "नमस्ते", "प्रणाम", "हेलो", "हाय", "आप कैसे हैं", "तुम कौन हो", "तुम क्या कर सकते हो", "कैसे हो"
    ]
    if any(cleaned_q == g or cleaned_q.startswith(g + " ") or cleaned_q.endswith(" " + g) for g in greetings):
        return {
            "category": "greeting",
            "data": None,
            "is_general_advice": False,
            "is_ambiguous": False
        }

    # Politeness / Gratitude
    gratitude = [
        "thank you", "thanks", "thank you so much", "thanks a lot",
        "ధన్యవాదాలు", "చాలా థాంక్స్", "థాంక్యూ",
        "धन्यवाद", "बहुत बहुत धन्यवाद", "शुक्रिया"
    ]
    if any(cleaned_q == g or cleaned_q.startswith(g + " ") for g in gratitude):
        return {
            "category": "gratitude",
            "data": None,
            "is_general_advice": False,
            "is_ambiguous": False
        }

    # Ambiguous one-word requests
    if q in ("report", "details", "help", "summary", "సమాచారం", "రిపోర్ట్", "विवरण", "रिपोर्ट", "मदद"):
        return {
            "category": "ambiguous",
            "data": None,
            "is_general_advice": False,
            "is_ambiguous": True
        }

    # 1. Product price inquiry (e.g. "how much is Rice?", "price of Dot & Key Sunscreen")
    price_match = re.search(r"(?:price|cost|rate|how much is|how much for|ధర|ఖరీదు|రేటు|दाम|कीमत|भाव|रेट|कितने का है)\s+(?:of|for|का|की|లో)?\s*([a-zA-Z0-9\s&]+)", q)
    if price_match:
        product_name = price_match.group(1).strip()
        product_name = re.sub(r"[\?\.!]", "", product_name)
        product_name = re.sub(r"\b(is|a|the|in|my|shop|today|please|telugu|hindi)\b", "", product_name).strip()
        if len(product_name) >= 2:
            price_info = get_product_price_info(connection, product_name)
            if price_info["found_count"] > 0:
                return {
                    "category": "product_price",
                    "data": price_info,
                    "is_general_advice": False,
                    "is_ambiguous": False
                }

    # 2. Best-selling products
    if any(phrase in q for phrase in [
        "best sell", "top sell", "most sell", "highest sell", "best product",
        "top product", "fast moving", "sold the most", "most sold", "sold most",
        "highest sold", "ఎక్కువ అమ్ముడవుతున్న", "టాప్ సేల్స్", "ఎక్కువ సేల్స్", "బాగా అమ్ముడయ్యే",
        "सबसे ज्यादा बिकने", "ज्यादा बिकने", "बेस्ट सेलर", "सबसे ज्यादा बिक्री", "टॉप सेलिंग"
    ]):
        return {
            "category": "best_selling",
            "data": get_best_selling_products(connection, limit=5),
            "is_general_advice": False,
            "is_ambiguous": False
        }

    # 3. Slow-moving / dead stock products
    if any(phrase in q for phrase in [
        "slow moving", "not selling", "least sell", "dead stock", "unsold",
        "zero sales", "least sold", "low selling",
        "అమ్ముడవని", "తక్కువ అమ్ముడవుతున్న", "సేల్స్ లేని", "సరుకు అమ్ముడవట్లేదు",
        "कम बिकने", "धीमी गति", "अटका हुआ माल", "बिक्री नहीं हो रही", "धीमी बिक्री"
    ]):
        return {
            "category": "slow_moving",
            "data": get_slow_moving_products(connection, limit=5),
            "is_general_advice": False,
            "is_ambiguous": False
        }

    # 4. Low stock / reorder alerts
    if any(phrase in q for phrase in [
        "low stock", "out of stock", "reorder", "restock", "restocking", "running out",
        "running low", "low on stock", "shortage", "need to buy", "need to order",
        "తక్కువ స్టాక్", "నిల్వ తక్కువ", "స్టాక్ అయిపోయింది", "సరుకు అయిపోయింది", "కొనవలసినవి",
        "कम स्टॉक", "स्टॉक कम", "रीऑर्डर", "खत्म होने वाला", "स्टॉक खत्म", "माल खत्म", "सामान मंगाना"
    ]):
        return {
            "category": "low_stock",
            "data": get_low_stock_products(connection),
            "is_general_advice": False,
            "is_ambiguous": False
        }

    # 5. Inventory list & total stock
    if any(phrase in q for phrase in [
        "inventory", "all products", "list products", "stock in my shop",
        "total stock", "what stock", "items in stock",
        "స్టాక్ మొత్తం", "వస్తువుల జాబితా", "ఇన్వెంటరీ", "సరుకు వివరాలు",
        "इन्वेंटरी", "कुल स्टॉक", "सभी उत्पाद", "सामान की लिस्ट", "स्टॉक लिस्ट"
    ]):
        return {
            "category": "inventory",
            "data": get_inventory_summary(connection),
            "is_general_advice": False,
            "is_ambiguous": False
        }

    # 6. Expenses inquiry
    if any(phrase in q for phrase in [
        "expense", "spending", "electricity bill", "rent", "operating cost", "maintenance",
        "ఖర్చులు", "ఖర్చు", "బిల్లులు", "కరెంట్ బిల్లు", "అద్దె",
        "खर्च", "खर्चे", "किराया", "बिजली का बिल", "बिल"
    ]):
        period, start, end = parse_date_period(q)
        return {
            "category": "expenses",
            "data": get_expenses_breakdown(connection, start, end, period),
            "is_general_advice": False,
            "is_ambiguous": False
        }

    # 7. Purchases / Supplier invoices
    if any(phrase in q for phrase in [
        "purchase", "supplier", "vendor", "wholesale", "bought", "dealer", "invoice",
        "కొనుగోళ్లు", "కొన్నవి", "సప్లయర్", "డీలర్",
        "खरीद", "खरीदारी", "सप्लायर", "डीलर", "थोक"
    ]):
        return {
            "category": "purchases",
            "data": get_purchase_history(connection, limit=5),
            "is_general_advice": False,
            "is_ambiguous": False
        }

    # 8. Sales trends
    if any(phrase in q for phrase in [
        "trend", "sales pattern", "growth over time", "performance over time", "weekly pattern",
        "వారం", "ట్రెండ్", "వారపు", "గ్రోత్",
        "ट्रेंड", "पैटर्न", "साप्ताहिक", "दैनिक बिक्री"
    ]):
        return {
            "category": "sales_trends",
            "data": get_sales_trends(connection, days=7),
            "is_general_advice": False,
            "is_ambiguous": False
        }

    # 9. Comprehensive Financial & Performance Inquiries:
    # Captures ANY phrasing asking about sales, profit, earnings, revenue, turnover, money made, business status
    financial_keywords = [
        "sale", "sell", "sold", "profit", "earn", "earned", "earning", "earnings",
        "revenue", "turnover", "margin", "loss", "income", "money", "collection",
        "bill", "bills", "business", "performance", "cogs", "cost of goods",
        "అమ్మకాలు", "అమ్మకం", "లాభం", "నికర లాభం", "ఎంత వచ్చింది", "వ్యాపారం", "డబ్బులు", "కలెక్షన్", "బిల్లులు",
        "बिक्री", "मुनाफा", "लाभ", "कमाई", "व्यापार", "दुकान", "कलेक्शन", "पैसे", "कितना बिका", "कितना मुनाफा", "कितनी बिक्री"
    ]

    colloquial_business_patterns = [
        "how did we do", "how was business", "how did business go", "how did today go",
        "how was today", "how is business", "how is today", "what did we do", "what did we make",
        "what did i make", "how much came in", "any earnings", "how much money",
        "did i make any money", "today business", "todays business", "today's business",
        "आज का काम कैसा रहा", "आज का धंधा", "आज का व्यापार", "ఈ రోజు వ్యాపారం ఎలా జరిగింది"
    ]

    is_financial_inquiry = any(kw in q for kw in financial_keywords) or any(pat in q for pat in colloquial_business_patterns)

    # Check for timeframe reference (today, yesterday, this month, etc.)
    has_timeframe = any(t in q for t in [
        "today", "yesterday", "this month", "this year", "last month", "last year",
        "ఈ రోజు", "నిన్న", "ఈ నెల", "గత నెల", "ఈ సంవత్సరం",
        "आज", "कल", "इस महीने", "पिछले महीने", "इस साल"
    ])
    has_advice_words = any(w in q for w in [
        "how to", "advice", "suggest", "tips", "prevent", "spoilage", "shelf", "display",
        "సలహా", "ఎలా", "सुझाव", "सलाह", "तरीका"
    ])

    if is_financial_inquiry or (has_timeframe and not has_advice_words):
        period, start, end = parse_date_period(q)
        financials = get_financial_summary(connection, start, end, period)
        return {
            "category": "financials",
            "data": financials,
            "is_general_advice": False,
            "is_ambiguous": False
        }

    # 10. General shop management advice (conceptual questions not needing live DB figures)
    if any(phrase in q for phrase in [
        "how to", "how can i", "tip", "tips", "advice", "suggest", "suggestion",
        "customer", "display", "shelf", "arrangement", "spoilage", "shrinkage",
        "expiry", "waste", "marketing", "merchandising",
        "సలహా", "ఎలా పెంచాలి", "పాడవకుండా", "ग्राहकों", "दुकान कैसे चलाएं", "सजावट"
    ]):
        return {
            "category": "general_advice",
            "data": None,
            "is_general_advice": True,
            "is_ambiguous": False
        }

    # 11. Check if any product name is mentioned anywhere in the query
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT product_name FROM products WHERE is_active = 1")
        for prod in cursor.fetchall():
            pname = prod["product_name"].lower()
            if pname in q:
                price_info = get_product_price_info(connection, pname)
                return {
                    "category": "product_price",
                    "data": price_info,
                    "is_general_advice": False,
                    "is_ambiguous": False
                }
    finally:
        cursor.close()

    # 12. Conversational fallback (don't force a financial summary on general chats)
    if any(w in q for w in ["help", "who", "what", "can you", "सहायता", "సహాయం"]):
        return {
            "category": "conversational",
            "data": None,
            "is_general_advice": True,
            "is_ambiguous": False
        }

    # Default fallback: Financial summary
    period, start, end = parse_date_period(q)
    financials = get_financial_summary(connection, start, end, period)
    return {
        "category": "financials",
        "data": financials,
        "is_general_advice": False,
        "is_ambiguous": False
    }
