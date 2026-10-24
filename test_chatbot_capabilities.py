import os
import sys
import time

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.append(r'c:\Users\HP\OneDrive\Desktop\ai_shopkeeper')

from shop_analytics import get_db_connection, resolve_business_data_for_question
from chatbot import ask_shopkeeper_assistant

def test_chatbot():
    print("=" * 60)
    print("TESTING AI SHOPKEEPER ASSISTANT (CHATBOT)")
    print("=" * 60)

    connection = get_db_connection()

    test_queries = [
        # Group 1: Differently worded sales questions requesting the same information
        ("Sales Wording 1", "How much did I sell today?"),
        ("Sales Wording 2", "What is today's turnover?"),
        ("Sales Wording 3", "How did business go today?"),

        # Group 2: Profit & Margins
        ("Profit Query", "What was my gross and net profit this month?"),

        # Group 3: Best-Selling Products
        ("Best Sellers", "Which product is my top seller?"),

        # Group 4: Slow-Moving Products
        ("Slow Moving", "What products are not selling well?"),

        # Group 5: Low-Stock Products
        ("Low Stock", "What do I need to reorder?"),

        # Group 6: Specific Product Price Lookup
        ("Price Check", "What is the price of Rice?"),

        # Group 7: Missing Data Handling (Honest Limitation)
        ("Missing Purchases", "Show my purchase history from suppliers."),
        ("Missing Expenses", "What were my electricity expenses this month?"),

        # Group 8: General Retail Management Advice
        ("General Advice", "How should I arrange impulse-buy snacks near the checkout counter?"),

        # Group 9: Ambiguous Request (Clarification)
        ("Ambiguous Query", "report"),

        # Group 10: Multilingual (Telugu)
        ("Telugu Sales", "ఈ రోజు అమ్మకాలు ఎంత?"),
    ]

    results = []

    for label, query in test_queries:
        print(f"\n--- Testing [{label}]: '{query}' ---")
        try:
            # Check analytics resolution first
            res = resolve_business_data_for_question(connection, query)
            cat = res["category"]
            print(f"  [Intent Category]: {cat}")

            # Get Gemma's response
            reply = ask_shopkeeper_assistant(query, connection)
            print(f"  [Assistant Reply]:\n{reply}\n")
            results.append((label, query, cat, "PASS", reply))

            # Small pause between API calls to prevent quota spikes
            time.sleep(2)

        except Exception as err:
            print(f"  [Error]: {err}\n")
            results.append((label, query, "error", "FAIL", str(err)))

    connection.close()

    print("\n" + "=" * 60)
    print("CHATBOT CAPABILITY TEST SUMMARY")
    print("=" * 60)
    for label, q, cat, status, _ in results:
        print(f"[{status:4}] {label:20} (Cat: {cat:15}) : '{q}'")
    print("=" * 60)

if __name__ == "__main__":
    test_chatbot()
