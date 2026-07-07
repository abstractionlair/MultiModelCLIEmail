import os
import google.generativeai as genai

def check_gemini_api():
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set.")
        return

    print(f"API Key found: {api_key[:5]}...")

    try:
        genai.configure(api_key=api_key)
        print("Gemini API configured successfully.")
    except Exception as e:
        print(f"Error configuring Gemini API: {e}")
        return

    print("\nListing available models...")
    try:
        for m in genai.list_models():
            print(f"  - {m.name}")
    except Exception as e:
        print(f"Error listing models: {e}")
        return

    print("\nAttempting to get 'models/gemini-pro'...")
    try:
        model = genai.get_model("models/gemini-pro")
        print(f"Successfully retrieved model: {model.name}")
    except Exception as e:
        print(f"Error getting 'models/gemini-pro': {e}")

if __name__ == "__main__":
    check_gemini_api()
