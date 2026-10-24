import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

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

    cursor.execute("""
        SELECT
            product_id,
            product_name,
            category,
            unit,
            selling_price,
            current_stock,
            barcode
        FROM products
        WHERE is_active = 1
        ORDER BY product_name
    """)

    products = cursor.fetchall()

    print("\n===== AI SHOPKEEPER: PRODUCT INVENTORY =====\n")

    if products:
        for product in products:
            print(f"Product ID   : {product['product_id']}")
            print(f"Product Name : {product['product_name']}")
            print(f"Category     : {product['category'] or 'Not specified'}")
            print(f"Unit         : {product['unit']}")
            print(f"Selling Price: Rs. {product['selling_price']}")
            print(f"Current Stock: {product['current_stock']}")
            print(f"Barcode      : {product['barcode'] or 'Not added yet'}")
            print("-" * 40)
    else:
        print("No active products found.")

except mysql.connector.Error as error:
    print("Database error:", error)

finally:
    if cursor:
        cursor.close()

    if connection and connection.is_connected():
        connection.close()