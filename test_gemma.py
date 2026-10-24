import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY is missing from .env")

client = genai.Client(api_key=api_key)

try:
    content = types.Content(
        role="user",
        parts=[types.Part.from_text(text="Reply with exactly: API is working.")]
    )
    response = client.models.generate_content(
        model="gemma-4-31b-it",
        contents=[content]
    )
    print("API test successful!")
    print(response.text)

except Exception as error:
    print("API test failed:")
    print(error)
