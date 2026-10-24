import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

barcode = input("Enter product barcode: ").strip()

connection = None
cursor = None

try:
    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "shopkeeper_ai")
    )

    cursor = connection.cursor(dictionary=True)

    query = """
        SELECT
            product_id,
            product_name,
            category,
            unit,
            selling_price,
            current_stock,
            barcode
        FROM products
        WHERE barcode = %s
          AND is_active = 1
    """

    cursor.execute(query, (barcode,))
    product = cursor.fetchone()

    if product:
        print("\n===== PRODUCT FOUND =====")
        print("Product ID:", product["product_id"])
        print("Product:", product["product_name"])
        print("Category:", product["category"])
        print("Price: Rs.", product["selling_price"], "per", product["unit"])
        print("Available stock:", product["current_stock"])
        print("Barcode:", product["barcode"])
    else:
        print("\nProduct not found.")
        print("Check the barcode or register the product first.")

except mysql.connector.Error as error:
    print("Database error:", error)

finally:
    if cursor:
        cursor.close()

    if connection and connection.is_connected():
        connection.close()
