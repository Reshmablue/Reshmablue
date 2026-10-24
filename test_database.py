import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

try:
    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "shopkeeper_ai")
    )

    print("Database connected successfully!")

    cursor = connection.cursor()
    cursor.execute("SHOW TABLES")

    print("\nTables in shopkeeper database:")
    for table in cursor.fetchall():
        print("-", table[0])

    cursor.close()
    connection.close()

except mysql.connector.Error as error:
    print("Database connection failed:", error)