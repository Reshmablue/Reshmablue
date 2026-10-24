import os
import sys
import json

# Ensure UTF-8 output
for stream in [sys.stdout, sys.stderr]:
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from web_app import app

def run_tests():
    print("=================================================================")
    print("AI SHOPKEEPER ASSISTANT - COMPREHENSIVE AI & CHATBOT TEST SUITE")
    print("=================================================================")

    client = app.test_client()

    # -------------------------------------------------------------
    # 1. Chatbot: English greeting
    # -------------------------------------------------------------
    print("\n--- Test 1: Chatbot English Greeting ---")
    res = client.post("/api/chat", json={"message": "Hello!", "language": "en-IN"})
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.get_json()
    assert data["status"] == "success"
    print(f"User: Hello!")
    print(f"Bot response:\n{data['response']}\nSpeech text: {data['speech_text']}")

    # -------------------------------------------------------------
    # 2. Chatbot: Today's sales (MySQL Grounded)
    # -------------------------------------------------------------
    print("\n--- Test 2: Chatbot Today's Sales (MySQL Grounded) ---")
    res = client.post("/api/chat", json={"message": "How much did I sell today?", "language": "en-IN"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    print(f"User: How much did I sell today?")
    print(f"Bot response:\n{data['response']}\nSpeech text: {data['speech_text']}")
    # Verify sales figure 2700 is present
    assert "2700" in data["response"] or "2,700" in data["response"] or "2700" in data["speech_text"], "Expected 2700 in sales answer"

    # -------------------------------------------------------------
    # 3. Chatbot: Multi-turn Follow-up ("What about yesterday?")
    # -------------------------------------------------------------
    print("\n--- Test 3: Chatbot Multi-turn Follow-up ---")
    history = [
        {"role": "user", "text": "How much did I sell today?"},
        {"role": "model", "text": data["response"]}
    ]
    res = client.post("/api/chat", json={
        "message": "What about yesterday?",
        "language": "en-IN",
        "history": history
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    print(f"User: What about yesterday?")
    print(f"Bot response:\n{data['response']}")

    # -------------------------------------------------------------
    # 4. Chatbot: Telugu Query ("ఈ రోజు అమ్మకాలు ఎంత?")
    # -------------------------------------------------------------
    print("\n--- Test 4: Chatbot Telugu Query ---")
    res = client.post("/api/chat", json={
        "message": "ఈ రోజు అమ్మకాలు ఎంత?",
        "language": "te-IN"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    print(f"User: ఈ రోజు అమ్మకాలు ఎంత?")
    print(f"Bot response:\n{data['response']}\nSpeech text: {data['speech_text']}")
    # Verify Telugu script returned
    has_telugu = any("\u0C00" <= ch <= "\u0C7F" for ch in data["response"])
    assert has_telugu, "Expected Telugu script in response"

    # -------------------------------------------------------------
    # 5. Chatbot: Hindi Query ("आज की कुल बिक्री कितनी हुई?")
    # -------------------------------------------------------------
    print("\n--- Test 5: Chatbot Hindi Query ---")
    res = client.post("/api/chat", json={
        "message": "आज की कुल बिक्री कितनी हुई?",
        "language": "hi-IN"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    print(f"User: आज की कुल बिक्री कितनी हुई?")
    print(f"Bot response:\n{data['response']}\nSpeech text: {data['speech_text']}")
    # Verify Devanagari script returned
    has_hindi = any("\u0900" <= ch <= "\u097F" for ch in data["response"])
    assert has_hindi, "Expected Hindi script in response"

    # -------------------------------------------------------------
    # 6. Voice Endpoint: Telugu ("ఈ రోజు అమ్మకాలు ఎంత?")
    # -------------------------------------------------------------
    print("\n--- Test 6: Voice Processing Telugu Endpoint ---")
    res = client.post("/api/voice/process", json={
        "transcript": "ఈ రోజు అమ్మకాలు ఎంత?",
        "language": "te-IN"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    print(f"Voice Display Text:\n{data['display_text']}")
    print(f"Voice Speech Text:\n{data['speech_text']}")

    # -------------------------------------------------------------
    # 7. Server-Side TTS Endpoint (/api/tts): Telugu & Hindi Audio Generation
    # -------------------------------------------------------------
    print("\n--- Test 7: /api/tts Regional Audio Generation ---")
    # Telugu TTS
    res_te = client.get("/api/tts?lang=te-IN&text=" + "ఈ రోజు మొత్తం అమ్మకాలు 2700 రూపాయలు.")
    assert res_te.status_code == 200
    assert res_te.mimetype == "audio/mpeg"
    te_bytes = len(res_te.data)
    print(f"Telugu TTS generated: {te_bytes} bytes (audio/mpeg)")
    assert te_bytes > 5000, f"Expected > 5000 bytes, got {te_bytes}"

    # Hindi TTS
    res_hi = client.get("/api/tts?lang=hi-IN&text=" + "आज की कुल बिक्री 2700 रुपये है.")
    assert res_hi.status_code == 200
    assert res_hi.mimetype == "audio/mpeg"
    hi_bytes = len(res_hi.data)
    print(f"Hindi TTS generated: {hi_bytes} bytes (audio/mpeg)")
    assert hi_bytes > 5000, f"Expected > 5000 bytes, got {hi_bytes}"

    # English TTS
    res_en = client.get("/api/tts?lang=en-IN&text=" + "Today's total sales is 2700 Rupees.")
    assert res_en.status_code == 200
    assert res_en.mimetype == "audio/mpeg"
    en_bytes = len(res_en.data)
    print(f"English TTS generated: {en_bytes} bytes (audio/mpeg)")
    assert en_bytes > 5000, f"Expected > 5000 bytes, got {en_bytes}"

    print("\n=================================================================")
    print("ALL AI & VOICE TESTS PASSED SUCCESSFULLY!")
    print("=================================================================")

if __name__ == "__main__":
    run_tests()
