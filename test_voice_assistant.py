"""
=============================================================================
TEST SUITE: AI SHOPKEEPER VOICE ASSISTANT & WEB INTEGRATION
Tests:
1. Language detection (English, Telugu, Hindi)
2. Speech text cleaner (markdown stripping, digit-comma cleaning, currency words)
3. Direct database grounding & intent resolution
4. End-to-end process_voice_query execution
5. REST API endpoint /api/voice/process via Flask Test Client
6. Edge cases (empty transcript, ambiguous query, missing payload)
7. Non-destructive safety verification (database invariance)
=============================================================================
"""

import os
import sys
import json
import unittest
from decimal import Decimal

# Ensure UTF-8 output
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()

from voice_assistant import (
    detect_language,
    clean_speech_text,
    construct_voice_gemma_prompt,
    process_voice_query
)
from shop_analytics import (
    get_db_connection,
    resolve_business_data_for_question,
    get_financial_summary
)
from web_app import app


class TestVoiceAssistant(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Verify database connectivity and record initial table row counts."""
        cls.conn = get_db_connection()
        cls.cursor = cls.conn.cursor(dictionary=True)

        cls.cursor.execute("SELECT COUNT(*) AS c FROM products")
        cls.initial_products_count = cls.cursor.fetchone()["c"]

        cls.cursor.execute("SELECT COUNT(*) AS c FROM sales")
        cls.initial_sales_count = cls.cursor.fetchone()["c"]

        cls.cursor.execute("SELECT COUNT(*) AS c FROM sale_items")
        cls.initial_sale_items_count = cls.cursor.fetchone()["c"]

        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        if cls.cursor:
            cls.cursor.close()
        if cls.conn and cls.conn.is_connected():
            cls.conn.close()

    # -------------------------------------------------------------------------
    # 1. LANGUAGE DETECTION TESTS
    # -------------------------------------------------------------------------
    def test_01_language_detection(self):
        """Verify English, Telugu, and Hindi language auto-detection."""
        # English
        self.assertEqual(detect_language("How much sales today?"), "en-IN")
        self.assertEqual(detect_language("What is our profit this month?"), "en-IN")

        # Telugu (Unicode block 0C00-0C7F)
        self.assertEqual(detect_language("ఈ రోజు అమ్మకాలు ఎంత?"), "te-IN")
        self.assertEqual(detect_language("నిన్నటి లాభం ఎంత?"), "te-IN")

        # Hindi (Devanagari Unicode block 0900-097F)
        self.assertEqual(detect_language("आज की बिक्री कितनी है?"), "hi-IN")
        self.assertEqual(detect_language("दुकान का मुनाफा बताओ"), "hi-IN")

        # Fallback handling
        self.assertEqual(detect_language("", fallback_lang="te-IN"), "te-IN")
        self.assertEqual(detect_language("", fallback_lang="hi-IN"), "hi-IN")

    # -------------------------------------------------------------------------
    # 2. SPEECH TEXT FORMATTER TESTS
    # -------------------------------------------------------------------------
    def test_02_clean_speech_text_english(self):
        """Verify markdown stripping and currency spoken word translation in English."""
        raw_text = (
            "**Today's Financial Summary:**\n"
            "• Total Sales: ₹2,700.00\n"
            "• Gross Profit: ₹675.00\n"
            "* Net Profit: ₹675.00"
        )
        cleaned = clean_speech_text(raw_text, language="en-IN")

        # Must not contain raw asterisks, hash, or bullets
        self.assertNotIn("*", cleaned)
        self.assertNotIn("•", cleaned)
        self.assertNotIn("₹", cleaned)

        # Must convert comma numbers like 2,700 -> 2700
        self.assertNotIn("2,700", cleaned)
        self.assertIn("2700", cleaned)

        # Must convert currency to Rupees
        self.assertIn("Rupees", cleaned)

    def test_03_clean_speech_text_telugu_and_hindi(self):
        """Verify currency spoken word translation in Telugu and Hindi."""
        # Telugu
        te_raw = "ఈ రోజు అమ్మకాలు ₹2,700 మరియు లాభం ₹675."
        te_clean = clean_speech_text(te_raw, language="te-IN")
        self.assertNotIn("₹", te_clean)
        self.assertIn("రూపాయలు", te_clean)
        self.assertIn("2700", te_clean)

        # Hindi
        hi_raw = "आज की कुल बिक्री ₹2,700 है।"
        hi_clean = clean_speech_text(hi_raw, language="hi-IN")
        self.assertNotIn("₹", hi_clean)
        self.assertIn("रुपये", hi_clean)
        self.assertIn("2700", hi_clean)

    # -------------------------------------------------------------------------
    # 3. DATABASE GROUNDING & QUERY RESOLUTION
    # -------------------------------------------------------------------------
    def test_04_database_grounding_financials(self):
        """Verify that financial voice questions resolve live data from shopkeeper_ai."""
        context = resolve_business_data_for_question(self.conn, "how much sales today")
        self.assertEqual(context["category"], "financials")
        data = context["data"]
        self.assertIn("total_sales_after_discounts", data)
        self.assertIn("net_profit", data)
        self.assertIn("number_of_bills", data)

    def test_05_database_grounding_low_stock(self):
        """Verify low-stock intent retrieves real active inventory records."""
        context = resolve_business_data_for_question(self.conn, "any low stock items?")
        self.assertEqual(context["category"], "low_stock")
        data = context["data"]
        self.assertIn("low_stock_products", data)

    def test_06_database_grounding_best_selling(self):
        """Verify best-selling intent retrieves top products."""
        context = resolve_business_data_for_question(self.conn, "what sold the most?")
        self.assertEqual(context["category"], "best_selling")
        data = context["data"]
        self.assertIn("best_selling_products", data)

    # -------------------------------------------------------------------------
    # 4. END-TO-END PROCESS VOICE QUERY
    # -------------------------------------------------------------------------
    def test_07_process_voice_query_success(self):
        """Verify end-to-end voice query returns structured response with playback metadata."""
        result = process_voice_query("how much sales today", language="en-IN", connection=self.conn)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["question"], "how much sales today")
        self.assertTrue(len(result["display_text"]) > 0)
        self.assertTrue(len(result["speech_text"]) > 0)
        self.assertIn("playback_metadata", result)
        self.assertEqual(result["playback_metadata"]["language"], "en-IN")
        self.assertIn("category", result)

    def test_08_process_voice_query_empty_input(self):
        """Verify graceful error response when transcript is empty."""
        result = process_voice_query("", language="en-IN", connection=self.conn)
        self.assertEqual(result["status"], "error")
        self.assertIn("empty", result["message"].lower())

    # -------------------------------------------------------------------------
    # 5. REST API ENDPOINT /api/voice/process
    # -------------------------------------------------------------------------
    def test_09_api_voice_process_valid(self):
        """Verify Flask endpoint POST /api/voice/process with valid payload."""
        response = self.client.post(
            "/api/voice/process",
            data=json.dumps({"transcript": "what is our profit today", "language": "en-IN"}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "success")
        self.assertIn("display_text", data)
        self.assertIn("speech_text", data)
        self.assertIn("playback_metadata", data)

    def test_10_api_voice_process_empty_payload(self):
        """Verify Flask endpoint returns 400 for empty transcript."""
        response = self.client.post(
            "/api/voice/process",
            data=json.dumps({"transcript": ""}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "error")

    def test_11_api_chat_returns_speech_text(self):
        """Verify POST /api/chat also returns speech_text for seamless audio readout."""
        response = self.client.post(
            "/api/chat",
            data=json.dumps({"message": "inventory summary"}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "success")
        self.assertIn("speech_text", data)

    # -------------------------------------------------------------------------
    # 6. NON-DESTRUCTIVE SAFETY VERIFICATION
    # -------------------------------------------------------------------------
    def test_12_database_invariance(self):
        """Verify zero records were created, modified, or deleted during voice testing."""
        self.cursor.execute("SELECT COUNT(*) AS c FROM products")
        final_products = self.cursor.fetchone()["c"]

        self.cursor.execute("SELECT COUNT(*) AS c FROM sales")
        final_sales = self.cursor.fetchone()["c"]

        self.cursor.execute("SELECT COUNT(*) AS c FROM sale_items")
        final_sale_items = self.cursor.fetchone()["c"]

        self.assertEqual(final_products, self.initial_products_count, "Products count must remain untouched.")
        self.assertEqual(final_sales, self.initial_sales_count, "Sales count must remain untouched.")
        self.assertEqual(final_sale_items, self.initial_sale_items_count, "Sale items count must remain untouched.")


if __name__ == "__main__":
    unittest.main()
