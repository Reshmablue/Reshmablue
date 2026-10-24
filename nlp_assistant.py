
import re
from datetime import date, timedelta
from decimal import Decimal

import pymysql


def connect_db():
    return pymysql.connect(
        host="localhost",
        user="root",
        password="",  # Change if you configured a password
        database="shopkeeper_ai",
        cursorclass=pymysql.cursors.DictCursor
    )


def get_month_range(question):
    """Recognize this month, last month, or YYYY-MM."""
    today = date.today()
    match = re.search(r"\b(20\d{2})-(0[1-9]|1[0-2])\b", question)

    if match:
        start = date(int(match.group(1)), int(match.group(2)), 1)
    elif "last month" in question or "previous month" in question:
        start = date(today.year, today.month, 1)
        start = start - timedelta(days=1)
        start = date(start.year, start.month, 1)
    else:
        start = date(today.year, today.month, 1)

    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)

    return start, end


def monthly_profit(connection, question):
    start, end = get_month_range(question)

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                COALESCE(SUM(total_amount - discount), 0) AS revenue,
                COUNT(*) AS sale_count
            FROM sales
            WHERE sale_date >= %s AND sale_date < %s
        """, (start, end))
        sales = cursor.fetchone()

        cursor.execute("""
            SELECT COALESCE(SUM(si.quantity * si.unit_cost), 0)
                   AS product_cost
            FROM sale_items si
            JOIN sales s ON s.sale_id = si.sale_id
            WHERE s.sale_date >= %s AND s.sale_date < %s
        """, (start, end))
        costs = cursor.fetchone()

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS expenses
            FROM expenses
            WHERE expense_date >= %s AND expense_date < %s
        """, (start, end))
        expenses = cursor.fetchone()

    revenue = Decimal(str(sales["revenue"]))
    product_cost = Decimal(str(costs["product_cost"]))
    other_expenses = Decimal(str(expenses["expenses"]))

    gross_profit = revenue - product_cost
    net_profit = gross_profit - other_expenses

    return (
        f"Business report for {start.strftime('%B %Y')}:\n"
        f"Sales transactions: {sales['sale_count']}\n"
        f"Net sales: Rs. {revenue:.2f}\n"
        f"Product costs: Rs. {product_cost:.2f}\n"
        f"Gross profit: Rs. {gross_profit:.2f}\n"
        f"Other expenses: Rs. {other_expenses:.2f}\n"
        f"Estimated net profit: Rs. {net_profit:.2f}"
    )


def sales_today(connection):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) AS count,
                   COALESCE(SUM(total_amount - discount), 0) AS revenue
            FROM sales
            WHERE sale_date >= CURDATE()
              AND sale_date < CURDATE() + INTERVAL 1 DAY
        """)
        result = cursor.fetchone()

    return (
        f"Today's sales transactions: {result['count']}\n"
        f"Today's net sales: Rs. {Decimal(str(result['revenue'])):.2f}"
    )


def show_products(connection):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT product_name, category, selling_price
            FROM products
            ORDER BY product_name
        """)
        products = cursor.fetchall()

    if not products:
        return "No products have been added yet."

    lines = ["Your products:"]
    for p in products:
        lines.append(
            f"- {p['product_name']} ({p['category'] or 'Uncategorized'}): "
            f"Rs. {Decimal(str(p['selling_price'])):.2f}"
        )

    return "\n".join(lines)


def low_stock(connection):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT product_name, opening_stock, reorder_level
            FROM products
            WHERE opening_stock <= reorder_level
            ORDER BY product_name
        """)
        products = cursor.fetchall()

    if not products:
        return "No products are below their opening-stock reorder thresholds."

    lines = ["Products requiring a stock check (opening stock only):"]
    for p in products:
        lines.append(
            f"- {p['product_name']}: stock {p['opening_stock']}, "
            f"reorder threshold {p['reorder_level']}"
        )

    return "\n".join(lines)


def monthly_expenses(connection, question):
    start, end = get_month_range(question)

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT category, SUM(amount) AS total
            FROM expenses
            WHERE expense_date >= %s AND expense_date < %s
            GROUP BY category
            ORDER BY total DESC
        """, (start, end))
        rows = cursor.fetchall()

    if not rows:
        return f"No expenses recorded for {start.strftime('%B %Y')}."

    total = sum(Decimal(str(row["total"])) for row in rows)
    lines = [f"Expenses for {start.strftime('%B %Y')}:"]
    for row in rows:
        lines.append(
            f"- {row['category']}: Rs. {Decimal(str(row['total'])):.2f}"
        )
    lines.append(f"Total expenses: Rs. {total:.2f}")

    return "\n".join(lines)


def understand_question(question):
    """A basic rule-based NLP intent classifier."""
    q = question.lower().strip()

    if any(word in q for word in [
        "profit", "how much did i earn", "business report"
    ]):
        return "profit"

    if any(word in q for word in [
        "low stock", "out of stock", "running out",
        "stock alert", "reorder"
    ]):
        return "stock"

    if any(word in q for word in [
        "list products", "show products", "my products",
        "what products", "product list"
    ]):
        return "products"

    if any(word in q for word in [
        "expense", "expenses", "electricity bill",
        "rent cost", "money did i spend"
    ]):
        return "expenses"

    if any(word in q for word in [
        "sales today", "today's sales", "today sales",
        "sold today", "sales this day"
    ]):
        return "sales_today"

    if any(word in q for word in [
        "sales", "revenue", "turnover"
    ]):
        return "profit"

    return "unknown"


def main():
    print("AI Shopkeeper Assistant")
    print("Ask about profit, sales, expenses, products, or stock.")
    print("Type 'exit' to stop.\n")

    try:
        connection = connect_db()
        print("Database connected successfully!\n")
    except pymysql.MySQLError as error:
        print("Database connection failed:", error)
        return

    try:
        while True:
            question = input("You: ").strip()

            if question.lower() in ("exit", "quit", "bye"):
                print("Assistant: Goodbye! Have a good day.")
                break

            if not question:
                continue

            intent = understand_question(question)

            try:
                if intent == "profit":
                    answer = monthly_profit(connection, question)
                elif intent == "sales_today":
                    answer = sales_today(connection)
                elif intent == "expenses":
                    answer = monthly_expenses(connection, question)
                elif intent == "products":
                    answer = show_products(connection)
                elif intent == "stock":
                    answer = low_stock(connection)
                else:
                    answer = (
                        "I didn't understand that question yet. "
                        "Try asking about monthly profit, today's sales, "
                        "expenses, products, or low stock."
                    )

                print(f"\nAssistant: {answer}\n")

            except pymysql.MySQLError as error:
                print("Could not retrieve the data:", error)

    finally:
        connection.close()


if __name__ == "__main__":
    main()
