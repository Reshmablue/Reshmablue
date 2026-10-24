"""
=============================================================================
AI SHOPKEEPER ASSISTANT - VOICE-TO-VOICE MODULE (voice_assistant.py)
Powered by Gemma API (gemma-4-31b-it) & Web Speech API
Supports English (en-IN), Telugu (te-IN), and Hindi (hi-IN)
=============================================================================
"""

import os
import sys
import re
import json
from decimal import Decimal

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
from google import genai
from google.genai import types

from shop_analytics import (
    get_db_connection,
    resolve_business_data_for_question
)
from chatbot import (
    ask_gemma,
    format_direct_business_fallback,
    PRIMARY_MODEL,
    FALLBACK_MODEL
)

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
client = None
if API_KEY:
    try:
        client = genai.Client(api_key=API_KEY)
    except Exception as e:
        client = None


# =============================================================================
# 1. LANGUAGE DETECTION AND NORMALIZATION
# =============================================================================

def detect_language(text, fallback_lang="en-IN"):
    """
    Detect whether the input transcript contains Telugu, Hindi (Devanagari), or English.
    Returns language code: 'te-IN', 'hi-IN', or 'en-IN'.
    """
    if not text:
        return fallback_lang

    # Check for Telugu Unicode block (0C00 - 0C7F)
    if re.search(r"[\u0C00-\u0C7F]", text):
        return "te-IN"

    # Check for Devanagari / Hindi Unicode block (0900 - 097F)
    if re.search(r"[\u0900-\u097F]", text):
        return "hi-IN"

    # Normalize incoming fallback
    norm = fallback_lang.lower().strip()
    if "te" in norm:
        return "te-IN"
    elif "hi" in norm:
        return "hi-IN"
    return "en-IN"


# =============================================================================
# 2. SPEECH TEXT OPTIMIZATION (TEXT-TO-SPEECH FORMATTING)
# =============================================================================

def clean_speech_text(text, language="en-IN"):
    """
    Transforms formatted markdown and symbols into natural, spoken text for TTS.
    - Strips markdown asterisks, hashes, backticks, bullet characters.
    - Converts currency symbols (₹, Rs., INR) to spoken words:
        * en-IN: 'Rupees'
        * te-IN: 'రూపాయలు'
        * hi-IN: 'रुपये'
    - Strips internal commas in digits (e.g. 2,700 -> 2700) so synthesizers don't say 'comma'.
    - Replaces newlines and bullet lines with smooth spoken pauses.
    """
    if not text:
        return ""

    speech = text

    # Currency word mappings
    lang_code = detect_language(speech, language)
    if lang_code == "te-IN":
        curr_word = "రూపాయలు"
    elif lang_code == "hi-IN":
        curr_word = "रुपये"
    else:
        curr_word = "Rupees"

    # 1. Clean numbers with commas: e.g. 2,700 -> 2700, 10,000 -> 10000
    speech = re.sub(r"(\d+),(\d+)", r"\1\2", speech)

    # 2. Currency transformations:
    # Pattern: ₹ 2700 or ₹2700 or Rs. 2700 or Rs 2700
    if lang_code in ("te-IN", "hi-IN"):
        # In Telugu and Hindi, amount often precedes currency: "2700 రూపాయలు" / "2700 रुपये"
        speech = re.sub(r"(?:₹|Rs\.?|INR)\s*(\d+(?:\.\d+)?)", rf"\1 {curr_word}", speech, flags=re.IGNORECASE)
    else:
        # In English: "2700 Rupees" is very naturally spoken by web TTS
        speech = re.sub(r"(?:₹|Rs\.?|INR)\s*(\d+(?:\.\d+)?)", rf"\1 {curr_word}", speech, flags=re.IGNORECASE)

    # Any standalone currency symbol leftover
    speech = re.sub(r"[₹]", f" {curr_word} ", speech)

    # 3. Strip Markdown headers, bold, italics, code blocks
    speech = re.sub(r"```[\s\S]*?```", "", speech)
    speech = re.sub(r"`[^`]*`", "", speech)
    speech = re.sub(r"#{1,6}\s*", "", speech)
    speech = re.sub(r"[*_~]+", "", speech)
    speech = re.sub(r"^>\s*", "", speech, flags=re.MULTILINE)

    # 4. Strip bullet markers: •, -, * at start of lines
    speech = re.sub(r"^\s*[•\-\*]\s*", ". ", speech, flags=re.MULTILINE)

    # 5. Normalize newlines to sentence pauses
    speech = re.sub(r"\n+", ". ", speech)

    # 6. Clean up repeated punctuation and whitespace
    speech = re.sub(r"\.\s*\.+", ".", speech)
    speech = re.sub(r":\s*", ": ", speech)
    speech = re.sub(r"\s+", " ", speech)
    speech = speech.strip()

    # Trim leading punctuation
    speech = re.sub(r"^[\.\,\;\:\s]+", "", speech)

    return speech


# =============================================================================
# 3. VOICE-OPTIMIZED PROMPT BUILDER
# =============================================================================

def construct_voice_gemma_prompt(question, context, language="en-IN"):
    """
    Constructs a Gemma prompt specifically tuned for spoken dialogue.
    Instructions prioritize concise, conversational answers (2-3 sentences)
    grounded 100% in verified MySQL data.
    """
    category = context.get("category", "general")
    data = context.get("data")
    is_advice = context.get("is_general_advice", False)
    is_ambiguous = context.get("is_ambiguous", False)

    lang_code = detect_language(question, language)
    if lang_code == "te-IN":
        lang_rule = "Respond in natural, respectful, spoken Telugu (తెలుగు). Use polite shopkeeper conversational tone."
    elif lang_code == "hi-IN":
        lang_rule = "Respond in natural, respectful, spoken Hindi (हिन्दी). Use polite shopkeeper conversational tone."
    else:
        lang_rule = "Respond in clear, natural, spoken Indian English."

    base_instructions = f"""
You are an expert AI Shopkeeper Voice Assistant for a local Indian retail shop.
Your response will be spoken aloud to the shopkeeper via text-to-speech.

CRITICAL VOICE & DATA RULES:
1. VERIFIED FACTS: Ground all sales, profits, expenses, stock, and prices strictly on the pre-calculated database data below. All arithmetic was calculated by MySQL and Python. Never invent, guess, or modify financial numbers.
2. SPOKEN CONCISENESS: Keep your spoken answer concise, friendly, and direct (2 to 4 sentences). Do NOT include markdown headers, ASCII tables, asterisks, or long bulleted lists.
3. ZERO SALES ACCURACY: If the data confirms 0 sales transactions, explicitly state that no sales were recorded for this period.
4. LANGUAGE: {lang_rule}
5. CURRENCY: Refer to amounts in Rupees (₹).
"""

    if category == "greeting":
        return f"""{base_instructions}
CONTEXT: The shopkeeper is greeting you: "{question}".
TASK: Greet them warmly and respectfully in 1-2 spoken sentences in {lang_rule}. Introduce yourself and say you are ready to answer questions about their shop's sales, profit, stock, or expenses.
"""

    if category == "gratitude":
        return f"""{base_instructions}
CONTEXT: The shopkeeper is saying thanks: "{question}".
TASK: Respond with a polite, warm welcome in 1 spoken sentence in {lang_rule}.
"""

    if is_ambiguous:
        return f"""{base_instructions}
CONTEXT: The shopkeeper asked a vague voice question: "{question}".
TASK: Briefly ask them to clarify what they want to know (for example: today's sales, monthly profit, or low stock). Keep it to 1-2 spoken sentences.
"""

    if is_advice or data is None:
        return f"""{base_instructions}
CONTEXT: The shopkeeper is asking for general retail advice: "{question}".
TASK: Give 2-3 practical, spoken retail tips suitable for a busy Indian shopkeeper.
"""

    data_json = json.dumps(data, ensure_ascii=False, indent=2)

    has_sales = data.get("has_sales", True) if isinstance(data, dict) else True
    bills = data.get("number_of_bills", 1) if isinstance(data, dict) else 1

    extra_note = ""
    if not has_sales or bills == 0:
        extra_note = "NOTICE: Database records show 0 sales for this period. Clearly state that no sales were recorded yet."
    else:
        extra_note = f"NOTICE: Database confirms {bills} active sales bills. State the exact sales and profit figures provided."

    return f"""{base_instructions}

PRE-CALCULATED BUSINESS DATA FROM MYSQL:
{data_json}

SHOPKEEPER'S SPOKEN QUESTION:
{question}

{extra_note}

TASK:
Provide a spoken, natural summary of the above figures directly answering the question in 2 to 3 friendly sentences.
"""


# =============================================================================
# 4. MAIN VOICE QUERY PROCESSOR
# =============================================================================

def process_voice_query(transcript, language="en-IN", connection=None, history=None):
    """
    End-to-end voice query pipeline:
    1. Receives transcribed question string.
    2. Detects or confirms spoken language (en-IN, te-IN, hi-IN).
    3. Retrieves verified business figures via safe parameterized functions in shop_analytics.py.
    4. Generates a grounded response using Gemma API (or verified database fallback if API busy).
    5. Cleans and formats response into both display text and audio-optimized speech text.
    6. Returns structured response with playback metadata.
    """
    clean_q = str(transcript or "").strip()
    if not clean_q:
        return {
            "status": "error",
            "message": "Spoken question was empty. Please speak clearly into the microphone.",
            "question": "",
            "display_text": "",
            "speech_text": "",
            "language": language
        }

    detected_lang = detect_language(clean_q, fallback_lang=language)

    own_conn = False
    if connection is None:
        try:
            connection = get_db_connection()
            own_conn = True
        except Exception as err:
            return {
                "status": "error",
                "message": f"Database connection failed: {err}",
                "question": clean_q,
                "display_text": "Could not connect to shop database. Please check MySQL.",
                "speech_text": "Could not connect to shop database. Please check MySQL.",
                "language": detected_lang
            }

    try:
        # Step 1: Pre-resolve verified database facts with history
        context = resolve_business_data_for_question(connection, clean_q, conversation_history=history)

        # Step 2: Build voice-optimized prompt
        prompt = construct_voice_gemma_prompt(clean_q, context, detected_lang)

        # Step 3: Query Gemma API with fallback
        display_text = None
        try:
            display_text = ask_gemma(prompt)
        except Exception:
            display_text = None

        if not display_text:
            # Fall back to verified direct database report
            display_text = format_direct_business_fallback(context, clean_q)

        # Step 4: Generate audio-optimized speech text
        speech_text = clean_speech_text(display_text, language=detected_lang)

        # Playback rate & pitch recommendations
        rate = 1.0
        pitch = 1.0

        return {
            "status": "success",
            "question": clean_q,
            "display_text": display_text,
            "speech_text": speech_text,
            "language": detected_lang,
            "playback_metadata": {
                "rate": rate,
                "pitch": pitch,
                "language": detected_lang
            },
            "category": context.get("category", "general"),
            "grounded_data": context.get("data")
        }

    except Exception as e:
        err_msg = f"Voice processing error: {str(e)}"
        return {
            "status": "error",
            "message": err_msg,
            "question": clean_q,
            "display_text": err_msg,
            "speech_text": "An error occurred while analyzing your request.",
            "language": detected_lang
        }
    finally:
        if own_conn and connection and connection.is_connected():
            connection.close()


# =============================================================================
# 5. CLI INTERACTIVE TESTING
# =============================================================================

def main():
    print("=" * 60)
    print("   AI SHOPKEEPER VOICE ASSISTANT - CLI TEST MODE")
    print("   Powered by Gemma API (gemma-4-31b-it)")
    print("=" * 60)

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"\nProcessing query: {query}")
        result = process_voice_query(query)
        print("\n--- Display Text ---")
        print(result.get("display_text"))
        print("\n--- Speech Text (Clean for TTS) ---")
        print(result.get("speech_text"))
        print("\n--- Metadata ---")
        print(f"Language: {result.get('language')}")
        print(f"Category: {result.get('category')}")
        return

    print("Enter questions in English, Telugu, or Hindi (type 'exit' to quit):")
    while True:
        try:
            q = input("\nShopkeeper Voice > ").strip()
            if not q:
                continue
            if q.lower() in ("exit", "quit", "bye"):
                break

            result = process_voice_query(q)
            print("\n[AI Display Response]:")
            print(result.get("display_text"))
            print("\n[Spoken Audio Output]:")
            print(f'"{result.get("speech_text")}"')
            print(f"[Language: {result.get('language')} | Category: {result.get('category')}]")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
