import os
import sys
import json
import time

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import mysql.connector
from dotenv import load_dotenv
from google import genai
from google.genai import types

from shop_analytics import (
    get_db_connection,
    resolve_business_data_for_question,
    get_financial_summary,
    get_inventory_summary,
    get_low_stock_products,
    get_best_selling_products,
    get_slow_moving_products,
    get_product_price_info,
    get_expenses_breakdown,
    get_purchase_history,
    get_sales_trends
)

# ==================================================
# 1. CONFIGURATION
# ==================================================

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
PRIMARY_MODEL = "gemma-4-31b-it"
FALLBACK_MODEL = "gemma-4-26b-a4b-it"

if not API_KEY:
    raise ValueError(
        "GEMINI_API_KEY is missing from your .env file."
    )

# Use standard client initialization without custom http_options to avoid SSL handshake timeout
client = genai.Client(api_key=API_KEY)


# ==================================================
# 2. LANGUAGE DETECTOR & PROMPT BUILDER
# ==================================================

def detect_language(text, explicit_lang=None):
    """
    Detect target language.
    If explicit_lang is provided from the UI, it takes 100% precedence.
    """
    if explicit_lang:
        el = str(explicit_lang).lower()
        if "te" in el or "telugu" in el:
            return "Telugu"
        if "hi" in el or "hindi" in el:
            return "Hindi"
        if "en" in el or "english" in el:
            return "English"

    if text:
        for char in text:
            code = ord(char)
            if 0x0C00 <= code <= 0x0C7F:
                return "Telugu"
            if 0x0900 <= code <= 0x097F:
                return "Hindi"

    return "English"


def construct_gemma_prompt(question, context, history=None, language=None):
    """
    Construct a precise, targeted prompt for Gemma based on the resolved context,
    conversation history, and preferred language (English, Telugu, Hindi).
    Strictly forces the AI to reply ONLY in the selected language.
    """
    category = context.get("category", "general")
    data = context.get("data")
    is_advice = context.get("is_general_advice", False)
    is_ambiguous = context.get("is_ambiguous", False)

    lang_name = detect_language(question, language)

    if lang_name == "Telugu":
        lang_instruction = (
            "ABSOLUTE MANDATORY LANGUAGE REQUIREMENT: TELUGU (తెలుగు) ONLY.\n"
            "The shopkeeper has set their application language to TELUGU (తెలుగు).\n"
            "REGARDLESS of what language the user's question was typed or spoken in (even if the user asked in English, e.g. 'How much did I sell today?' or 'Hello'), your ENTIRE response MUST be 100% in natural, respectful, fluent Telugu (తెలుగు) using proper Telugu script (తెలుగు లిపి).\n"
            "DO NOT answer in English. DO NOT output English sentences or Latin transliterations. Everything MUST be in Telugu script.\n"
            "Standard Telugu retail terminology:\n"
            "- Sales = అమ్మకాలు\n"
            "- Profit / Net Profit = లాభం / నికర లాభం\n"
            "- Loss = నష్టం\n"
            "- Expenses = ఖర్చులు\n"
            "- Stock / Inventory = సరుకు / నిల్వలు / ఇన్వెంటరీ\n"
            "- Bills / Invoices = బిల్లులు\n"
            "- Rupees = రూపాయలు (₹)\n"
            "- Low stock = తక్కువ స్టాక్"
        )
    elif lang_name == "Hindi":
        lang_instruction = (
            "ABSOLUTE MANDATORY LANGUAGE REQUIREMENT: HINDI (हिन्दी) ONLY.\n"
            "The shopkeeper has set their application language to HINDI (हिन्दी).\n"
            "REGARDLESS of what language the user's question was typed or spoken in (even if the user asked in English, e.g. 'How much did I sell today?' or 'Hello'), your ENTIRE response MUST be 100% in natural, respectful, fluent Hindi (हिन्दी) using proper Devanagari script (देवनागरी लिपि).\n"
            "DO NOT answer in English. DO NOT output English sentences or Latin transliterations. Everything MUST be in Devanagari script.\n"
            "Standard Hindi retail terminology:\n"
            "- Sales = बिक्री\n"
            "- Profit / Net Profit = मुनाफा / लाभ / कुल लाभ\n"
            "- Loss = नुकसान / घाटा\n"
            "- Expenses = खर्चे\n"
            "- Stock / Inventory = स्टॉक / माल\n"
            "- Bills / Invoices = बिल\n"
            "- Rupees = रुपये (₹)\n"
            "- Low stock = कम स्टॉक"
        )
    else:
        lang_instruction = (
            "MANDATORY LANGUAGE REQUIREMENT: ENGLISH ONLY.\n"
            "The shopkeeper has set their application language to English. Your entire response must be in clear, friendly, conversational English."
        )

    base_rules = f"""
You are an expert AI Shopkeeper Assistant for a local Indian retail shop.
Your role is to understand the shopkeeper's question, explain verified business data, and provide practical retail advice.

CRITICAL RULES:
1. VERIFIED FACTS: When business data is supplied below, explain those exact pre-calculated figures. All arithmetic was performed by MySQL and Python. Never invent, alter, or guess financial figures.
2. MISSING DATA & LIMITATIONS: If the data shows 0 records or states that data has not been entered yet (e.g. no expenses recorded, no purchases recorded, or insufficient sales history for trends), explain this limitation clearly and honestly. Do not make up fake data.
3. GENERAL ADVICE: If the user asks a general retail, merchandising, storage, or store-management question (where no live shop numbers are needed), provide practical, helpful advice tailored for small Indian grocery / retail shopkeepers.
4. CLARIFICATION: If the question is ambiguous or vague, ask a polite clarifying question offering 2-3 specific options (e.g. today's sales, monthly profit, low-stock items).
5. {lang_instruction}
6. CURRENCY: Always use Indian Rupees (₹) for monetary amounts.
7. SECURITY & INTEGRITY: You are a read-only assistant. Never claim to execute database updates or write arbitrary code.
"""

    # Build conversation history block
    history_str = ""
    if history and len(history) > 0:
        recent = history[-4:]
        history_lines = []
        for turn in recent:
            role_label = "Shopkeeper" if turn.get("role") == "user" else "Assistant"
            content = turn.get("text", turn.get("content", ""))
            if content:
                history_lines.append(f"{role_label}: {content}")
        if history_lines:
            history_str = "RECENT CONVERSATION HISTORY:\n" + "\n".join(history_lines) + "\n\n"

    # Greeting / pleasantries
    if category == "greeting":
        return f"""{base_rules}
{history_str}USER GREETING:
"{question}"

TASK:
Greet the shopkeeper warmly, politely, and respectfully EXCLUSIVELY in {lang_name} (native script). Introduce yourself as their AI Shopkeeper Assistant.
Let them know in 1-2 friendly sentences that you are ready to assist with their shop's sales, profit, stock, expenses, or practical store management.
Do NOT force raw database numbers into a simple greeting. Keep it welcoming and conversational.
"""

    # Gratitude / Politeness
    if category == "gratitude":
        return f"""{base_rules}
{history_str}USER MESSAGE:
"{question}"

TASK:
Respond warmly and politely to the shopkeeper's thanks EXCLUSIVELY in {lang_name} (native script). Remind them you are always here to help manage their shop smoothly.
"""

    # Conversational fallback
    if category == "conversational":
        return f"""{base_rules}
{history_str}USER QUESTION:
"{question}"

TASK:
Respond helpfully, politely, and conversationally EXCLUSIVELY in {lang_name} (native script) as their dedicated store assistant.
"""

    if is_ambiguous:
        return f"""{base_rules}
{history_str}CONTEXT:
The user entered an ambiguous or incomplete request: "{question}".

TASK:
Politely ask the shopkeeper to clarify what information they would like to see EXCLUSIVELY in {lang_name} (native script).
Offer helpful options such as:
1. Today's sales and profit
2. This month's financial report
3. Low-stock / reorder alerts
4. Best-selling products

USER QUESTION:
{question}
"""

    if is_advice or data is None:
        return f"""{base_rules}
{history_str}CONTEXT:
The user is asking for general store management or retail advice. No live database figures are required.

TASK:
Provide clear, actionable, friendly advice suitable for an Indian retail shopkeeper EXCLUSIVELY in {lang_name} (native script).

USER QUESTION:
{question}
"""

    # Data-driven query
    data_json = json.dumps(data, ensure_ascii=False, indent=2)

    has_sales = data.get("has_sales", True) if isinstance(data, dict) else True
    bills = data.get("number_of_bills", 1) if isinstance(data, dict) else 1

    extra_instruction = ""
    if not has_sales or bills == 0:
        extra_instruction = "IMPORTANT: The database confirms there are 0 sales transactions recorded for this period. Clearly inform the user that no sales have been recorded yet for this period."
    else:
        extra_instruction = f"IMPORTANT: The database confirms {bills} active sales transaction(s) exist. State the exact sales and profit figures directly from the data. Do NOT claim sales are zero."

    return f"""{base_rules}
{history_str}PRE-CALCULATED BUSINESS DATA FROM MYSQL:
{data_json}

USER QUESTION:
{question}

{extra_instruction}

TASK:
Interpret and explain the above business data directly answering the user's question in a clear, friendly, conversational tone EXCLUSIVELY in {lang_name} (using its native script).
REMINDER: Regardless of what language the question was asked in, your ENTIRE reply MUST be in {lang_name}.
"""


# ==================================================
# 3. ASK GEMMA WITH RESILIENT RETRY
# ==================================================

def ask_gemma(prompt):
    """
    Query gemma-4-31b-it with structured role content and automatic fallback
    to gemma-4-26b-a4b-it if Google's 31B cluster experiences a temporary 500/503 server error.
    Allows up to 30s request timeout per model to accommodate cloud generation latency.
    """
    content = types.Content(
        role="user",
        parts=[types.Part.from_text(text=prompt)]
    )

    call_config = types.GenerateContentConfig(
        http_options={"timeout": 30000}
    )

    models_to_try = [PRIMARY_MODEL, FALLBACK_MODEL]

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[content],
                config=call_config
            )

            if response and response.text:
                return response.text.strip()

        except Exception as e:
            err_str = str(e)
            print(f"[Chatbot] Model '{model_name}' failed ({type(e).__name__}: {err_str[:70]}), trying next model...")
            continue

    return None


# ==================================================
# 4. DIRECT DATABASE FALLBACK (WHEN GEMMA SERVER EXPERIENCES 500/503)
# ==================================================

def format_direct_business_fallback(context, question, language="en-IN"):
    """
    If Google's Gemma server temporarily encounters 500/503 capacity errors,
    format and present the exact, verified MySQL numbers directly to the user
    in their chosen language (Telugu, Hindi, or English).
    """
    lang_name = detect_language(question, language)
    category = context.get("category", "general")
    data = context.get("data")
    is_advice = context.get("is_general_advice", False)
    is_ambiguous = context.get("is_ambiguous", False)

    if lang_name == "Telugu":
        prefix = "(గమనిక: డేటాబేస్ నుండి ధృవీకరించబడిన లైవ్ లెక్కలు నేరుగా అందించబడుతున్నాయి)\n\n"
        if category in ("greeting", "casual", "pleasantry"):
            return (
                "నమస్కారం! నేను మీ AI షాప్‌కీపర్ అసిస్టెంట్‌ని.\n"
                "ఈ రోజు అమ్మకాలు, లాభం, ఖర్చులు లేదా ఇన్వెంటరీ వివరాల గురించి నన్ను అడగండి. మీకు ఎలా సహాయపడగలను?"
            )
        if category in ("gratitude", "thanks"):
            return "మీకు స్వాగతం! మీ వ్యాపారంలో మీకు సహాయం చేయడం నాకు సంతోషం. ఇంకేమైనా వివరాలు కావాలా?"
        if is_ambiguous:
            return (
                "మీరు దేని గురించి తెలుసుకోవాలనుకుంటున్నారో దయచేసి వివరంగా అడగండి:\n"
                "• ఈ రోజు అమ్మకాలు మరియు లాభం\n"
                "• ఈ నెల ఆర్థిక నివేదిక\n"
                "• తక్కువ స్టాక్ ఉన్న వస్తువులు\n"
                "• నిర్దిష్ట వస్తువు ధర (ఉదా: 'బియ్యం ధర ఎంత?')"
            )
        if is_advice or data is None:
            return (
                "గూగుల్ జెమ్మా AI సర్వర్ ప్రస్తుతం ఎక్కువ రద్దీతో ఉంది. "
                "దయచేసి మీ ప్రశ్నను కాసేపటి తర్వాత మళ్లీ అడగండి లేదా స్టాక్ మరియు అమ్మకాల వివరాల గురించి అడగండి."
            )
        if category == "financials":
            period = data.get("period", "ఎంచుకున్న సమయం")
            bills = data.get("number_of_bills", 0)
            has_sales = data.get("has_sales", False)
            if not has_sales or bills == 0:
                return prefix + f"ఆర్థిక నివేదిక ({period}):\n• ఈ సమయంలో ఎలాంటి అమ్మకాలు నమోదు కాలేదు."
            sales = data.get("total_sales_after_discounts", "0.00")
            cogs = data.get("cost_of_goods_sold", "0.00")
            gross = data.get("gross_profit", "0.00")
            exp = data.get("operating_expenses", "0.00")
            net = data.get("net_profit", "0.00")
            is_profitable = data.get("is_profitable", True)
            loss_str = "మీ వ్యాపారం లాభంలో ఉంది!" if is_profitable else "నికర నష్టం నమోదైంది."
            return (
                f"{prefix}ఆర్థిక సారాంశం ({period}):\n"
                f"• స్థితి: {loss_str}\n"
                f"• బిల్లుల సంఖ్య: {bills}\n"
                f"• మొత్తం అమ్మకాలు: {sales}\n"
                f"• కొనుగోలు ఖర్చు (COGS): {cogs}\n"
                f"• స్థూల లాభం: {gross}\n"
                f"• ఇతర ఖర్చులు: {exp}\n"
                f"• నికర లాభం: {net}"
            )
        if category == "inventory":
            total_items = data.get("total_active_products", 0)
            total_stock = data.get("total_stock_units", 0)
            low_count = data.get("low_stock_count", 0)
            valuation = data.get("inventory_cost_value", "0.00")
            return (
                f"{prefix}ప్రస్తుత ఇన్వెంటరీ సారాంశం:\n"
                f"• మొత్తం యాక్టివ్ వస్తువులు: {total_items}\n"
                f"• నిల్వ ఉన్న మొత్తం యూనిట్లు: {total_stock}\n"
                f"• తక్కువ స్టాక్ ఉన్న వస్తువులు: {low_count}\n"
                f"• మొత్తం ఇన్వెంటరీ విలువ: {valuation}"
            )
        if category in ("low_stock", "restock"):
            items = data.get("alerts", []) or data.get("low_stock_products", [])
            if not items:
                return prefix + "మంచి వార్త! ప్రస్తుతం తక్కువ స్టాక్ ఉన్న వస్తువులు ఏవీ లేవు."
            lines = [f"{prefix}తక్కువ స్టాక్ హెచ్చరికలు ({len(items)} వస్తువులు):"]
            for it in items:
                lines.append(f"• {it.get('product_name')}: స్టాక్ {it.get('current_stock')} మిగిలింది (రీఆర్డర్ లెవెల్: {it.get('reorder_level', 'N/A')})")
            return "\n".join(lines)
        if category in ("best_sellers", "best_selling"):
            items = data.get("top_products", []) or data.get("best_selling_products", [])
            if not items:
                return prefix + "అత్యధికంగా అమ్ముడైన వస్తువులను నిర్ణయించడానికి ఇంకా అమ్మకాలు నమోదు కాలేదు."
            lines = [f"{prefix}అత్యధికంగా అమ్ముడైన వస్తువులు:"]
            for it in items:
                lines.append(f"• {it.get('product_name')}: {it.get('quantity_sold', it.get('total_quantity_sold', 0))} అమ్ముడయ్యాయి")
            return "\n".join(lines)
        if category == "price_lookup":
            prod = data.get("product")
            if not prod:
                return prefix + "మీరు అడిగిన వస్తువు వివరాలు దొరకలేదు."
            return (
                f"{prefix}వస్తువు ధర మరియు స్టాక్ వివరాలు:\n"
                f"• పేరు: {prod['product_name']}\n"
                f"• అమ్మకపు ధర: రూ. {prod['selling_price']:.2f} ప్రతి {prod['unit']} కి\n"
                f"• ప్రస్తుత స్టాక్: {prod['current_stock']} {prod['unit']}"
            )
        if category == "expenses":
            total = data.get("total_expenses", "0.00")
            return prefix + f"మొత్తం ఖర్చులు: {total}"
        return prefix + "వివరాలు విజయవంతంగా తీసుకోబడ్డాయి."

    elif lang_name == "Hindi":
        prefix = "(नोट: लाइव डेटाबेस से सत्यापित आंकड़े सीधे प्रस्तुत किए जा रहे हैं)\n\n"
        if category in ("greeting", "casual", "pleasantry"):
            return (
                "नमस्ते! मैं आपका AI शॉपकीपर असिस्टेंट हूँ।\n"
                "आज की बिक्री, मुनाफे, खर्च या इन्वेंटरी के बारे में मुझसे पूछें। मैं आपकी क्या मदद कर सकता हूँ?"
            )
        if category in ("gratitude", "thanks"):
            return "आपका स्वागत है! आपकी दुकान के प्रबंधन में सहायता करना मेरा कर्तव्य है। क्या आपको और कुछ जानना है?"
        if is_ambiguous:
            return (
                "कृपया स्पष्ट करें कि आप क्या जानना चाहते हैं:\n"
                "• आज की बिक्री और मुनाफा\n"
                "• इस महीने का वित्तीय विवरण\n"
                "• कम स्टॉक वाले उत्पाद\n"
                "• किसी उत्पाद की कीमत (जैसे: 'चावल की कीमत क्या है?')"
            )
        if is_advice or data is None:
            return (
                "गूगल जेम्मा AI सेवा वर्तमान में अत्यधिक व्यस्त है। "
                "कृपया कुछ क्षण बाद पुनः प्रयास करें या बिक्री और इन्वेंटरी के बारे में पूछें।"
            )
        if category == "financials":
            period = data.get("period", "चयनित अवधि")
            bills = data.get("number_of_bills", 0)
            has_sales = data.get("has_sales", False)
            if not has_sales or bills == 0:
                return prefix + f"वित्तीय विवरण ({period}):\n• इस अवधि के लिए कोई बिक्री दर्ज नहीं हुई है।"
            sales = data.get("total_sales_after_discounts", "0.00")
            cogs = data.get("cost_of_goods_sold", "0.00")
            gross = data.get("gross_profit", "0.00")
            exp = data.get("operating_expenses", "0.00")
            net = data.get("net_profit", "0.00")
            is_profitable = data.get("is_profitable", True)
            loss_str = "आपकी दुकान मुनाफे में है!" if is_profitable else "शुद्ध घाटा दर्ज किया गया है।"
            return (
                f"{prefix}वित्तीय विवरण ({period}):\n"
                f"• स्थिति: {loss_str}\n"
                f"• बिलों की संख्या: {bills}\n"
                f"• कुल बिक्री: {sales}\n"
                f"• खरीद लागत (COGS): {cogs}\n"
                f"• सकल लाभ: {gross}\n"
                f"• कुल खर्चे: {exp}\n"
                f"• शुद्ध मुनाफा: {net}"
            )
        if category == "inventory":
            total_items = data.get("total_active_products", 0)
            total_stock = data.get("total_stock_units", 0)
            low_count = data.get("low_stock_count", 0)
            valuation = data.get("inventory_cost_value", "0.00")
            return (
                f"{prefix}वर्तमान स्टॉक विवरण:\n"
                f"• सक्रिय उत्पाद: {total_items}\n"
                f"• कुल स्टॉक इकाइयाँ: {total_stock}\n"
                f"• कम स्टॉक वाले उत्पाद: {low_count}\n"
                f"• कुल इन्वेंटरी लागत मूल्य: {valuation}"
            )
        if category in ("low_stock", "restock"):
            items = data.get("alerts", []) or data.get("low_stock_products", [])
            if not items:
                return prefix + "अच्छी खबर! वर्तमान में कोई भी उत्पाद कम स्टॉक सीमा से नीचे नहीं है।"
            lines = [f"{prefix}कम स्टॉक चेतावनी ({len(items)} उत्पाद):"]
            for it in items:
                lines.append(f"• {it.get('product_name')}: {it.get('current_stock')} उपलब्ध है (रीऑर्डर स्तर: {it.get('reorder_level', 'N/A')})")
            return "\n".join(lines)
        if category in ("best_sellers", "best_selling"):
            items = data.get("top_products", []) or data.get("best_selling_products", [])
            if not items:
                return prefix + "सबसे ज्यादा बिकने वाले उत्पाद निर्धारित करने के लिए अभी पर्याप्त बिक्री नहीं है।"
            lines = [f"{prefix}सबसे ज्यादा बिकने वाले उत्पाद:"]
            for it in items:
                lines.append(f"• {it.get('product_name')}: {it.get('quantity_sold', it.get('total_quantity_sold', 0))} बेचे गए")
            return "\n".join(lines)
        if category == "price_lookup":
            prod = data.get("product")
            if not prod:
                return prefix + "उत्पाद नहीं मिला।"
            return (
                f"{prefix}उत्पाद मूल्य और स्टॉक जानकारी:\n"
                f"• नाम: {prod['product_name']}\n"
                f"• बिक्री मूल्य: रु {prod['selling_price']:.2f} प्रति {prod['unit']}\n"
                f"• वर्तमान स्टॉक: {prod['current_stock']} {prod['unit']}"
            )
        if category == "expenses":
            total = data.get("total_expenses", "0.00")
            return prefix + f"कुल खर्चे: {total}"
        return prefix + "विवरण सफलतापूर्वक लोड हुआ।"

    # Default: English
    prefix = "(Note: Displaying verified live database records directly)\n\n"

    if category in ("greeting", "casual", "pleasantry"):
        return (
            "Namaste! I am your AI Shopkeeper Assistant.\n"
            "Ask me about today's sales, profit, expenses, or inventory status. How can I help you today?"
        )

    if category in ("gratitude", "thanks"):
        return "You are welcome! Always happy to assist with your store operations. Let me know if you need anything else!"

    if is_ambiguous:
        return (
            "Please clarify what information you would like to view:\n"
            "• Today's sales and profit\n"
            "• Monthly financial performance\n"
            "• Low-stock items to reorder\n"
            "• Product price lookup (e.g. 'Price of Rice')"
        )

    if is_advice or data is None:
        return (
            "Google Gemma AI is temporarily experiencing high server load. "
            "Please ask your store advice question again in a moment, or inquire about verified sales and stock records."
        )

    if category == "financials":
        period = data.get("period", "Selected Period")
        bills = data.get("number_of_bills", 0)
        has_sales = data.get("has_sales", False)
        if not has_sales or bills == 0:
            return prefix + f"Financial Report ({period}):\n• No sales recorded for this period."

        sales = data.get("total_sales_after_discounts", "Rs. 0.00")
        cogs = data.get("cost_of_goods_sold", "Rs. 0.00")
        gross = data.get("gross_profit", "Rs. 0.00")
        exp = data.get("operating_expenses", "Rs. 0.00")
        net = data.get("net_profit", "Rs. 0.00")
        is_profitable = data.get("is_profitable", True)

        loss_str = "No loss recorded. Your shop is profitable!" if is_profitable else "A net loss was recorded."
        return (
            f"{prefix}Financial Summary ({period}):\n"
            f"• Status: {loss_str}\n"
            f"• Number of Bills: {bills}\n"
            f"• Total Sales: {sales}\n"
            f"• Cost of Goods Sold: {cogs}\n"
            f"• Gross Profit: {gross}\n"
            f"• Expenses: {exp}\n"
            f"• Net Profit: {net}"
        )

    if category == "inventory":
        total_items = data.get("total_active_products", 0)
        total_stock = data.get("total_stock_units", 0)
        low_count = data.get("low_stock_count", 0)
        valuation = data.get("inventory_cost_value", "Rs. 0.00")
        return (
            f"{prefix}Current Inventory Summary:\n"
            f"• Active Products: {total_items}\n"
            f"• Total Units in Stock: {total_stock}\n"
            f"• Low Stock Items: {low_count}\n"
            f"• Total Inventory Cost Value: {valuation}"
        )

    if category in ("low_stock", "restock"):
        items = data.get("alerts", []) or data.get("low_stock_products", [])
        if not items:
            return prefix + "Great news! No products are currently below the low stock threshold."
        lines = [f"{prefix}Low Stock Alerts ({len(items)} items):"]
        for it in items:
            pname = it.get('product_name', 'Product')
            stock = it.get('current_stock', '0')
            reorder = it.get('reorder_level', it.get('min_stock_alert', 'N/A'))
            lines.append(f"• {pname}: {stock} remaining (Reorder: {reorder})")
        return "\n".join(lines)

    if category in ("best_sellers", "best_selling"):
        items = data.get("top_products", []) or data.get("best_selling_products", [])
        if not items:
            return prefix + "No sales recorded yet to determine best-selling items."
        lines = [f"{prefix}Best-Selling Products:"]
        for it in items:
            pname = it.get('product_name', 'Product')
            qty = it.get('quantity_sold', str(it.get('total_quantity_sold', 0)))
            rev = it.get('revenue', f"Rs. {it.get('total_revenue', 0):.2f}" if isinstance(it.get('total_revenue'), (int, float)) else str(it.get('total_revenue', '0.00')))
            lines.append(f"• {pname}: {qty} sold (Revenue: {rev})")
        return "\n".join(lines)

    if category == "slow_moving":
        items = data.get("slow_moving_products", [])
        msg = data.get("message")
        if msg:
            return prefix + msg
        if not items:
            return prefix + "No slow-moving products identified."
        lines = [f"{prefix}Slow-Moving Products:"]
        for it in items:
            lines.append(f"• {it['product_name']}: {it['current_stock']} {it['unit']} in stock (Sales: {it['total_quantity_sold']})")
        return "\n".join(lines)

    if category == "price_lookup":
        prod = data.get("product")
        if not prod:
            return prefix + "Could not find a product matching your query."
        return (
            f"{prefix}Product Price & Stock Info:\n"
            f"• Name: {prod['product_name']}\n"
            f"• Selling Price: Rs. {prod['selling_price']:.2f} per {prod['unit']}\n"
            f"• Current Stock: {prod['current_stock']} {prod['unit']}\n"
            f"• Barcode: {prod.get('barcode', 'N/A')}"
        )

    if category == "expenses":
        total = data.get("total_expenses", "Rs. 0.00")
        items = data.get("breakdown", [])
        if not items:
            return prefix + f"Total Expenses: {total}. (No individual expense entries recorded yet)."
        lines = [f"{prefix}Expenses Breakdown (Total: {total}):"]
        for it in items:
            lines.append(f"• {it['category']}: Rs. {it['category_total']:.2f}")
        return "\n".join(lines)

    if category == "purchases":
        msg = data.get("message", "Purchase tracking not yet active.")
        return prefix + msg

    if category == "trends":
        msg = data.get("message", "Insufficient sales history to detect trends.")
        return prefix + msg

    return "Sorry, the Gemma API is currently experiencing high demand. Please try asking again in a moment."


# ==================================================
# 5. CHATBOT QUERY ENTRY POINT
# ==================================================

def ask_shopkeeper_assistant(question, connection=None, history=None, language=None):
    """
    Complete end-to-end question processing:
    1. Analyzes question intent and resolves targeted business data from MySQL.
    2. Incorporates conversation history for seamless follow-up questions.
    3. Respects regional language preference (Telugu, Hindi, English).
    4. Constructs tailored prompt for Gemma.
    5. Calls Gemma for natural language interpretation with resilient fallback.
    6. Falls back gracefully to verified direct database report if Gemma API encounters temporary server load.
    """
    own_connection = False
    if connection is None:
        connection = get_db_connection()
        own_connection = True

    try:
        # Retrieve only relevant data, taking history into account
        context = resolve_business_data_for_question(connection, question, conversation_history=history)

        # Build prompt with history and language context
        prompt = construct_gemma_prompt(question, context, history=history, language=language)

        # Query Gemma
        response_text = ask_gemma(prompt)
        if not response_text:
            return format_direct_business_fallback(context, question, language=language)
        return response_text

    finally:
        if own_connection and connection and connection.is_connected():
            connection.close()


# ==================================================
# 5. INTERACTIVE CLI CHAT LOOP
# ==================================================

def main():
    print("\n" + "=" * 55)
    print("         AI SHOPKEEPER ASSISTANT")
    print("         Powered by Gemma API (gemma-4-31b-it)")
    print("=" * 55)
    print("Ask about:")
    print(" - Sales & profit (today, yesterday, this month, this year)")
    print(" - Best-selling & slow-moving items")
    print(" - Inventory & low stock alerts")
    print(" - Specific product prices (e.g. 'How much is Rice?')")
    print(" - Expenses & purchases")
    print(" - General retail tips (storage, marketing, customer service)")
    print(" - English and Telugu questions are supported.")
    print("Type 'exit' or 'quit' to close.")
    print("-" * 55)

    connection = None
    try:
        connection = get_db_connection()
    except Exception as e:
        print(f"Warning: Could not connect to MySQL: {e}")

    while True:
        try:
            question = input("\nYou: ").strip()

            if question.lower() in ("exit", "quit", "bye", "సెలవు"):
                print("\nAssistant: Namaste! Have a wonderful and profitable day!")
                break

            if not question:
                continue

            # Ensure DB connection is alive
            if connection is None or not connection.is_connected():
                try:
                    connection = get_db_connection()
                except Exception as err:
                    print(f"Assistant: Database connection lost ({err}). Please check XAMPP MySQL.")
                    continue

            print("\nAssistant: Analyzing your question...")
            answer = ask_shopkeeper_assistant(question, connection)
            print("\nAssistant:\n" + answer)

        except KeyboardInterrupt:
            print("\nAssistant: Goodbye!")
            break
        except Exception as err:
            print(f"\nAssistant: An unexpected error occurred: {err}")

    if connection and connection.is_connected():
        connection.close()


if __name__ == "__main__":
    main()
