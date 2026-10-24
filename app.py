
import pymysql
import pandas as pd

# Connect Python to the XAMPP database
try:
    connection = pymysql.connect(
        host="localhost",
        user="root",
        password="",  # Change if you configured a password
        database="shopkeeper_ai",
        cursorclass=pymysql.cursors.DictCursor
    )

    print("Connected to shopkeeper_ai successfully!")

    # Retrieve product details
    query = """
        SELECT product_id, product_name, category,
               opening_stock, selling_price,
               purchase_price, reorder_level
        FROM products
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        products = cursor.fetchall()

    if products:
        df = pd.DataFrame(products)

        print("\n--- SHOP PRODUCTS ---")
        print(df.to_string(index=False))

        # Initial stock alert
        low_stock = df[
            df["opening_stock"] <= df["reorder_level"]
        ]

        print("\n--- LOW STOCK ALERT ---")

        if not low_stock.empty:
            print(
                low_stock[
                    ["product_name", "opening_stock",
                     "reorder_level"]
                ].to_string(index=False)
            )
        else:
            print("No products below the reorder level.")

    else:
        print("No products found. Add sample products in phpMyAdmin.")

except pymysql.MySQLError as error:
    print("Database connection error:", error)

finally:
    if "connection" in locals() and connection.open:
        connection.close()
        print("\nDatabase connection closed.")
