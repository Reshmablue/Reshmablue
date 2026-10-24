import os
import mysql.connector
from dotenv import load_dotenv
from datetime import date, datetime
from decimal import Decimal

load_dotenv()


def get_connection():
    """Connect to the existing MySQL database."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "shopkeeper_ai")
    )


def choose_period():
    """Ask the user which report they want."""

    print("\n===== SHOPKEEPER REPORT MENU =====")
    print("1. Daily report")
    print("2. Monthly report")
    print("3. Yearly report")

    choice = input("Choose a report (1/2/3): ").strip()

    if choice == "1":
        date_text = input(
            "Enter date (YYYY-MM-DD), or press Enter for today: "
        ).strip()

        if date_text:
            selected_date = datetime.strptime(
                date_text, "%Y-%m-%d"
            ).date()
        else:
            selected_date = date.today()

        start_date = selected_date
        end_date = date.fromordinal(
            selected_date.toordinal() + 1
        )

        title = f"DAILY REPORT - {selected_date}"

    elif choice == "2":
        month_text = input(
            "Enter month (YYYY-MM), or press Enter for this month: "
        ).strip()

        if month_text:
            selected_month = datetime.strptime(
                month_text, "%Y-%m"
            ).date()
        else:
            today = date.today()
            selected_month = date(today.year, today.month, 1)

        start_date = date(
            selected_month.year, selected_month.month, 1
        )

        if selected_month.month == 12:
            end_date = date(selected_month.year + 1, 1, 1)
        else:
            end_date = date(
                selected_month.year,
                selected_month.month + 1,
                1
            )

        title = (
            f"MONTHLY REPORT - "
            f"{start_date.strftime('%B %Y')}"
        )

    elif choice == "3":
        year_text = input(
            "Enter year (YYYY), or press Enter for this year: "
        ).strip()

        if year_text:
            selected_year = int(year_text)
            if not 1000 <= selected_year <= 9998:
                raise ValueError("Enter a year between 1000 and 9998.")
        else:
            selected_year = date.today().year

        start_date = date(selected_year, 1, 1)
        end_date = date(selected_year + 1, 1, 1)

        title = f"YEARLY REPORT - {selected_year}"

    else:
        raise ValueError("Invalid choice. Please select 1, 2, or 3.")

    return start_date, end_date, title


def calculate_financial_report(cursor, start_date, end_date):
    """
    Calculate sales, discounts, COGS, gross profit, expenses, and net profit
    for the selected date range. Reusable across daily_report.py and chatbot.py.
    """
    sales_query = """
        SELECT
            COUNT(*) AS number_of_bills,
            COALESCE(SUM(total_amount), 0) AS total_sales,
            COALESCE(SUM(discount), 0) AS total_discount
        FROM sales
        WHERE sale_date >= %s
          AND sale_date < %s
    """
    cursor.execute(sales_query, (start_date, end_date))
    sales = cursor.fetchone()

    cost_query = """
        SELECT
            COALESCE(
                SUM(si.quantity * si.unit_cost), 0
            ) AS cost_of_goods
        FROM sale_items AS si
        INNER JOIN sales AS s
            ON si.sale_id = s.sale_id
        WHERE s.sale_date >= %s
          AND s.sale_date < %s
    """
    cursor.execute(cost_query, (start_date, end_date))
    cost_result = cursor.fetchone()

    expenses_query = """
        SELECT
            COALESCE(SUM(amount), 0) AS total_expenses
        FROM expenses
        WHERE expense_date >= %s
          AND expense_date < %s
    """
    cursor.execute(expenses_query, (start_date, end_date))
    expense_result = cursor.fetchone()

    total_sales = Decimal(str(sales["total_sales"]))
    total_discount = Decimal(str(sales["total_discount"]))
    cost_of_goods = Decimal(str(cost_result["cost_of_goods"]))
    total_expenses = Decimal(str(expense_result["total_expenses"]))

    gross_profit = total_sales - cost_of_goods
    net_profit = gross_profit - total_expenses
    number_of_bills = int(sales["number_of_bills"])

    return {
        "number_of_bills": number_of_bills,
        "total_sales": total_sales,
        "total_discount": total_discount,
        "cost_of_goods": cost_of_goods,
        "gross_profit": gross_profit,
        "total_expenses": total_expenses,
        "net_profit": net_profit,
        "has_sales": number_of_bills > 0
    }


def show_report(start_date, end_date, title):
    """Calculate and display business results for the chosen period."""

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        report = calculate_financial_report(cursor, start_date, end_date)
        sales = {"number_of_bills": report["number_of_bills"]}
        total_sales = report["total_sales"]
        total_discount = report["total_discount"]
        cost_of_goods = report["cost_of_goods"]
        total_expenses = report["total_expenses"]
        gross_profit = report["gross_profit"]
        net_profit = report["net_profit"]

        # 4. Find products that currently need restocking
        low_stock_query = """
            SELECT
                product_name,
                current_stock,
                reorder_level,
                unit
            FROM products
            WHERE is_active = 1
              AND current_stock <= reorder_level
            ORDER BY current_stock ASC
        """

        cursor.execute(low_stock_query)
        low_stock_products = cursor.fetchall()

        # 5. Display report
        print("\n" + "=" * 48)
        print(title.center(48))
        print("=" * 48)

        print(f"Report start date      : {start_date}")
        print(f"Report end date        : {end_date} (exclusive)")
        print("-" * 48)

        print(f"Number of bills        : {sales['number_of_bills']}")
        print(f"Sales after discounts  : Rs. {total_sales:.2f}")
        print(f"Total discounts        : Rs. {total_discount:.2f}")
        print(f"Cost of goods sold     : Rs. {cost_of_goods:.2f}")
        print(f"Gross profit/loss      : Rs. {gross_profit:.2f}")
        print(f"Operating expenses     : Rs. {total_expenses:.2f}")

        print("-" * 48)

        if net_profit > 0:
            print(f"NET PROFIT             : Rs. {net_profit:.2f}")
        elif net_profit < 0:
            print(f"NET LOSS               : Rs. {abs(net_profit):.2f}")
        else:
            print("NET PROFIT/LOSS        : Rs. 0.00")

        print("-" * 48)
        print("CURRENT LOW-STOCK ALERTS")
        print("-" * 48)

        if low_stock_products:
            for product in low_stock_products:
                print(
                    f"{product['product_name']}: "
                    f"{product['current_stock']} "
                    f"{product['unit']} available "
                    f"(reorder at {product['reorder_level']})"
                )
        else:
            print("No products currently need restocking.")

        print("=" * 48)

    except mysql.connector.Error as error:
        print("Database error:", error)

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    try:
        start_date, end_date, title = choose_period()
        show_report(start_date, end_date, title)

    except ValueError as error:
        print("Input error:", error)

    except Exception as error:
        print("Unexpected error:", error)

