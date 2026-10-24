
import pymysql
from decimal import Decimal, InvalidOperation
from datetime import date


def connect_db():
    return pymysql.connect(
        host="localhost",
        user="root",
        password="",  # Enter your MySQL password if configured
        database="shopkeeper_ai",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False
    )


def get_decimal(prompt, allow_zero=False):
    while True:
        try:
            value = Decimal(input(prompt).strip())
            if not value.is_finite():
                raise ValueError
            if value < 0 or (value == 0 and not allow_zero):
                print("Enter a valid positive amount.")
                continue
            return value
        except (InvalidOperation, ValueError):
            print("Please enter a valid number.")


def show_products(connection):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT product_id, product_name,
                   selling_price, purchase_price
            FROM products
            ORDER BY product_id
        """)
        products = cursor.fetchall()

    print("\n--- AVAILABLE PRODUCTS ---")
    for p in products:
        print(
            f"ID: {p['product_id']} | "
            f"{p['product_name']} | "
            f"Selling price: Rs. {p['selling_price']}"
        )
    return products


def record_sale(connection):
    products = show_products(connection)

    if not products:
        print("Add products before recording a sale.")
        return

    product_map = {p["product_id"]: p for p in products}
    items = []

    while True:
        try:
            product_id = int(input("\nEnter product ID (0 to finish): "))
            if product_id == 0:
                break
            if product_id not in product_map:
                print("Product ID not found.")
                continue
        except ValueError:
            print("Enter a valid product ID.")
            continue

        quantity = get_decimal("Enter quantity sold: ")
        product = product_map[product_id]

        items.append({
            "product_id": product_id,
            "quantity": quantity,
            "unit_price": Decimal(str(product["selling_price"])),
            "unit_cost": Decimal(str(product["purchase_price"]))
        })

        print("Product added to this sale.")

    if not items:
        print("No items entered. Sale cancelled.")
        return

    subtotal = sum(
        item["quantity"] * item["unit_price"]
        for item in items
    )

    print(f"\nSubtotal: Rs. {subtotal:.2f}")
    discount = get_decimal(
        "Enter discount (enter 0 for none): ", allow_zero=True
    )

    if discount > subtotal:
        print("Discount cannot exceed the subtotal. Sale cancelled.")
        return

    payment = input(
        "Payment method (cash/UPI/card): "
    ).strip().lower() or "cash"

    if payment not in ("cash", "upi", "card"):
        print("Use cash, UPI, or card. Sale cancelled.")
        return

    with connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO sales
                (sale_date, total_amount, discount, payment_method)
            VALUES (NOW(), %s, %s, %s)
        """, (subtotal, discount, payment))

        sale_id = cursor.lastrowid

        for item in items:
            cursor.execute("""
                INSERT INTO sale_items
                    (sale_id, product_id, quantity,
                     unit_price, unit_cost)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                sale_id,
                item["product_id"],
                item["quantity"],
                item["unit_price"],
                item["unit_cost"]
            ))

    connection.commit()
    print(f"\nSale #{sale_id} recorded successfully.")
    print(f"Net sales: Rs. {subtotal - discount:.2f}")


def record_expense(connection):
    print("\n--- RECORD SHOP EXPENSE ---")

    expense_date = input(
        f"Expense date YYYY-MM-DD (default {date.today()}): "
    ).strip()

    if not expense_date:
        expense_date = date.today().isoformat()

    try:
        date.fromisoformat(expense_date)
    except ValueError:
        print("Invalid date. Use YYYY-MM-DD.")
        return

    category = input(
        "Category (rent/electricity/transport/other): "
    ).strip()

    if not category:
        print("Category is required.")
        return

    amount = get_decimal("Enter expense amount in Rs.: ")
    description = input("Description (optional): ").strip()

    with connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO expenses
                (expense_date, category, amount, description)
            VALUES (%s, %s, %s, %s)
        """, (expense_date, category, amount, description))

    connection.commit()
    print("Expense recorded successfully.")


def monthly_report(connection):
    month = input("Enter report month YYYY-MM: ").strip()

    try:
        start = date.fromisoformat(month + "-01")
    except ValueError:
        print("Invalid month. Example: 2026-10")
        return

    if len(month) != 7:
        print("Use YYYY-MM format, for example 2026-10.")
        return

    if start.month == 12:
        next_month = date(start.year + 1, 1, 1)
    else:
        next_month = date(start.year, start.month + 1, 1)

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                COUNT(*) AS sale_count,
                COALESCE(SUM(total_amount - discount), 0)
                    AS revenue,
                COALESCE(SUM(discount), 0) AS discounts
            FROM sales
            WHERE sale_date >= %s AND sale_date < %s
        """, (start, next_month))
        sales = cursor.fetchone()

        cursor.execute("""
            SELECT COALESCE(SUM(si.quantity * si.unit_cost), 0)
                AS cost_of_goods
            FROM sale_items si
            JOIN sales s ON s.sale_id = si.sale_id
            WHERE s.sale_date >= %s AND s.sale_date < %s
        """, (start, next_month))
        costs = cursor.fetchone()

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total_expenses
            FROM expenses
            WHERE expense_date >= %s AND expense_date < %s
        """, (start, next_month))
        expenses = cursor.fetchone()

    revenue = Decimal(str(sales["revenue"]))
    cogs = Decimal(str(costs["cost_of_goods"]))
    expense_total = Decimal(str(expenses["total_expenses"]))
    discounts = Decimal(str(sales["discounts"]))

    gross_profit = revenue - cogs
    net_profit = gross_profit - expense_total

    print("\n" + "=" * 38)
    print(f" MONTHLY BUSINESS REPORT: {month}")
    print("=" * 38)
    print(f"Number of sales:    {sales['sale_count']}")
    print(f"Discounts:          Rs. {discounts:.2f}")
    print(f"Net sales revenue:  Rs. {revenue:.2f}")
    print(f"Cost of goods sold: Rs. {cogs:.2f}")
    print(f"Gross profit:       Rs. {gross_profit:.2f}")
    print(f"Other expenses:     Rs. {expense_total:.2f}")
    print("-" * 38)
    print(f"Estimated net profit: Rs. {net_profit:.2f}")
    print("=" * 38)

    if net_profit < 0:
        print("The shop made an estimated loss.")
    else:
        print("The shop made an estimated profit.")


def main():
    connection = None

    try:
        connection = connect_db()
        print("Connected to shopkeeper_ai!")

        while True:
            print("""
========= AI SHOPKEEPER ASSISTANT =========
1. Record a sale
2. Record an expense
3. Calculate monthly profit
4. View products
5. Exit
===========================================
""")
            choice = input("Choose an option: ").strip()

            try:
                if choice == "1":
                    record_sale(connection)
                elif choice == "2":
                    record_expense(connection)
                elif choice == "3":
                    monthly_report(connection)
                elif choice == "4":
                    show_products(connection)
                elif choice == "5":
                    print("Goodbye!")
                    break
                else:
                    print("Choose an option from 1 to 5.")

            except pymysql.MySQLError as error:
                connection.rollback()
                print("Database operation failed:", error)
            except Exception as error:
                connection.rollback()
                print("Operation failed:", error)

    except pymysql.MySQLError as error:
        print("Could not connect to the database:", error)
        print("Check XAMPP, database name, username and password.")
    finally:
        if connection:
            connection.close()


if __name__ == "__main__":
    main()
