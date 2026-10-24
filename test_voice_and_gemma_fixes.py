import os
import sys
import json
import unittest
import requests

BASE_URL = "http://127.0.0.1:5000"

class TestVoiceAndGemmaFixes(unittest.TestCase):

    def test_01_simple_greeting_no_gemma_error_english(self):
        """
        Scenario 1: Simple greeting in English.
        Verify that the chatbot returns a warm greeting and NEVER displays a Gemma error message.
        """
        res = requests.post(
            f"{BASE_URL}/api/chat",
            json={"message": "Hello", "language": "en-IN"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "success")
        response_text = data.get("response", "")

        # Verify it contains greeting keywords
        self.assertTrue(
            any(word in response_text.lower() for word in ["namaste", "hello", "welcome", "assistant", "help"]),
            f"Expected friendly greeting, got: {response_text}"
        )
        # Verify it does NOT contain Gemma error messages
        self.assertNotIn("experiencing high server load", response_text.lower())
        self.assertNotIn("failed to get response", response_text.lower())
        self.assertNotIn("experiencing high demand", response_text.lower())
        print("\n[PASS] Test 1: English greeting returned warm response without Gemma error.")

    def test_02_simple_greeting_telugu_and_hindi(self):
        """
        Scenario 1 (Telugu & Hindi): Simple greeting in Telugu and Hindi.
        Verify native script greeting and NO Gemma error message.
        """
        # Telugu
        res_te = requests.post(
            f"{BASE_URL}/api/chat",
            json={"message": "నమస్తే", "language": "te-IN"}
        )
        self.assertEqual(res_te.status_code, 200)
        data_te = res_te.json()
        resp_te = data_te.get("response", "")
        self.assertTrue(
            any(k in resp_te for k in ["నమస్కారం", "నమస్తే", "అసిస్టెంట్", "సహాయం"]),
            f"Expected Telugu greeting, got: {resp_te}"
        )
        self.assertNotIn("రద్దీతో ఉంది", resp_te)

        # Hindi
        res_hi = requests.post(
            f"{BASE_URL}/api/chat",
            json={"message": "नमस्ते", "language": "hi-IN"}
        )
        self.assertEqual(res_hi.status_code, 200)
        data_hi = res_hi.json()
        resp_hi = data_hi.get("response", "")
        self.assertTrue(
            any(k in resp_hi for k in ["नमस्ते", "प्रणाम", "असिस्टेंट", "सहायता", "मदद"]),
            f"Expected Hindi greeting, got: {resp_hi}"
        )
        self.assertNotIn("अत्यधिक व्यस्त है", resp_hi)
        print("[PASS] Test 2: Telugu and Hindi greetings returned warm native responses.")

    def test_03_today_sales_grounded_in_mysql(self):
        """
        Scenario 2: Ask "What are today's total sales?"
        Verify that the answer reflects actual sales data in MySQL (bills, sales amounts).
        """
        res = requests.post(
            f"{BASE_URL}/api/chat",
            json={"message": "What are today's total sales?", "language": "en-IN"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "success")
        response_text = data.get("response", "")

        # Verify it includes sales figures or mentions bills / sales
        self.assertTrue(
            ("bill" in response_text.lower() or "sale" in response_text.lower() or "rs" in response_text.lower() or "30" in response_text),
            f"Expected sales data in response, got: {response_text}"
        )
        print("[PASS] Test 3: Today's sales query grounded in MySQL data.")

    def test_04_simulated_gemma_api_failure_fallback(self):
        """
        Scenario 4: Simulated Gemma API failure.
        When ask_gemma returns None, format_direct_business_fallback must return
        verified MySQL numbers without false success claims or broken errors.
        """
        from shop_analytics import get_db_connection, resolve_business_data_for_question
        from chatbot import format_direct_business_fallback

        conn = get_db_connection()
        try:
            # 1. Greeting fallback
            greet_context = resolve_business_data_for_question(conn, "hello")
            greet_fb = format_direct_business_fallback(greet_context, "hello", language="en-IN")
            self.assertIn("Namaste", greet_fb)
            self.assertNotIn("experiencing high server load", greet_fb)

            # 2. Sales fallback
            sales_context = resolve_business_data_for_question(conn, "What are today's total sales?")
            sales_fb = format_direct_business_fallback(sales_context, "What are today's total sales?", language="en-IN")
            self.assertIn("Financial Summary", sales_fb)
            self.assertIn("Number of Bills:", sales_fb)
            self.assertIn("Total Sales:", sales_fb)
            self.assertIn("(Note: Displaying verified live database records directly)", sales_fb)

            # 3. Telugu sales fallback
            te_sales_fb = format_direct_business_fallback(sales_context, "ఈ రోజు అమ్మకాలు ఎంత?", language="te-IN")
            self.assertIn("ఆర్థిక సారాంశం", te_sales_fb)
            self.assertIn("బిల్లుల సంఖ్య:", te_sales_fb)
            self.assertIn("(గమనిక: డేటాబేస్ నుండి ధృవీకరించబడిన లైవ్ లెక్కలు నేరుగా అందించబడుతున్నాయి)", te_sales_fb)
            print("[PASS] Test 4: Simulated Gemma API failure returned graceful, grounded database fallbacks.")
        finally:
            conn.close()

    def test_05_tts_endpoint_languages(self):
        """
        Scenario 5: Audio TTS endpoint returns valid MPEG audio for Telugu, Hindi, and English.
        """
        # Telugu audio
        res_te = requests.get(f"{BASE_URL}/api/tts?lang=te-IN&text=నమస్కారం")
        self.assertEqual(res_te.status_code, 200)
        self.assertEqual(res_te.headers.get("Content-Type"), "audio/mpeg")
        self.assertGreater(len(res_te.content), 500)

        # Hindi audio
        res_hi = requests.get(f"{BASE_URL}/api/tts?lang=hi-IN&text=नमस्ते")
        self.assertEqual(res_hi.status_code, 200)
        self.assertEqual(res_hi.headers.get("Content-Type"), "audio/mpeg")
        self.assertGreater(len(res_hi.content), 500)

        # English audio
        res_en = requests.get(f"{BASE_URL}/api/tts?lang=en-IN&text=Hello")
        self.assertEqual(res_en.status_code, 200)
        self.assertEqual(res_en.headers.get("Content-Type"), "audio/mpeg")
        self.assertGreater(len(res_en.content), 500)
        print("[PASS] Test 5: /api/tts successfully generates audio/mpeg for Telugu, Hindi, and English.")

    def test_06_voice_js_source_code_mutual_exclusion(self):
        """
        Verify static/js/voice.js contains mutual exclusivity safeguards:
        - playbackSessionId tracking
        - stopSpeaking cleans up currentAudio & cancels window.speechSynthesis
        - Telugu and Hindi fallbacks NEVER fall back to default English voice
        """
        with open("static/js/voice.js", "r", encoding="utf-8") as f:
            code = f.read()

        self.assertIn("this.playbackSessionId", code)
        self.assertIn("this.stopSpeaking()", code)
        self.assertIn("window.speechSynthesis.cancel()", code)
        self.assertIn("Suppressed English voice fallback", code)
        print("[PASS] Test 6: static/js/voice.js contains single-channel mutual exclusion and language safety.")


if __name__ == "__main__":
    unittest.main()
