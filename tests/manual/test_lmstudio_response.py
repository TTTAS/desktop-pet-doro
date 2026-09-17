#!/usr/bin/env python3
"""Test script to verify LM Studio API response format."""

import json
import urllib.request
import sys

# Configuration
LM_STUDIO_URL = "http://127.0.0.1:1234/v1/chat/completions"  # Default LM Studio URL
TEST_MESSAGE = "Hello! Please respond with a simple greeting."


def test_lmstudio_response():
    """Send a test request to LM Studio and analyze the response structure."""

    payload = {
        "model": "lmstudio",  # LM Studio typically uses "lmstudio" as model name
        "messages": [{"role": "user", "content": TEST_MESSAGE}],
        "temperature": 0.7,
        "max_tokens": 50,
    }

    print(f"🔍 Testing LM Studio API at: {LM_STUDIO_URL}")
    print(f"📤 Sending test message: '{TEST_MESSAGE}'")
    print("-" * 60)

    try:
        request_bytes = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            LM_STUDIO_URL,
            data=request_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            response_data = json.loads(raw.decode("utf-8"))

        print("✅ Response received successfully!")
        print("=" * 60)
        print("📋 Full Response Structure:")
        print(json.dumps(response_data, indent=2, ensure_ascii=False))
        print("=" * 60)

        # Analyze structure
        print("\n🔍 Structure Analysis:")
        print(f"  - Has 'choices' field: {('choices' in response_data)}")
        if "choices" in response_data and response_data["choices"]:
            first_choice = response_data["choices"][0]
            print(f"  - choices[0] has 'message': {('message' in first_choice)}")
            if "message" in first_choice:
                message = first_choice["message"]
                print(f"  - message has 'content': {('content' in message)}")
                print(f"  - message has 'role': {('role' in message)}")
                if "content" in message:
                    print(f"\n📝 Assistant Response: \"{message['content']}\"")

        print(f"\n  - Has 'usage' field: {('usage' in response_data)}")
        print(f"  - Has 'model' field: {('model' in response_data)}")
        print(f"  - Has 'stats' field (LM Studio specific): {('stats' in response_data)}")

        # Test with ChatResponseParser
        print("\n" + "=" * 60)
        print("🧪 Testing with ChatResponseParser:")

        # Import the actual parser
        sys.path.insert(0, "/home/user/doro-exp-")
        from doro_app.core.chat.chat import ChatResponseParser

        extracted = ChatResponseParser.extract_assistant_text(response_data)
        if extracted:
            print(f'✅ ChatResponseParser extracted: "{extracted}"')
        else:
            print("❌ ChatResponseParser failed to extract text!")

    except urllib.error.HTTPError as e:
        print(f"❌ HTTP Error {e.code}: {e.reason}")
        try:
            error_body = e.read().decode("utf-8")
            print(f"Error details: {error_body}")
        except Exception:
            pass
    except urllib.error.URLError as e:
        print(f"❌ Connection Error: {e.reason}")
        print("\n💡 Troubleshooting:")
        print("  1. Is LM Studio running?")
        print("  2. Is the server enabled? (Settings → Server)")
        print("  3. Is the URL correct? (Default: http://127.0.0.1:1234)")
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    print("=" * 60)
    print("LM Studio API Response Format Tester")
    print("=" * 60 + "\n")

    if len(sys.argv) > 1:
        LM_STUDIO_URL = sys.argv[1]
        print(f"Using custom URL: {LM_STUDIO_URL}\n")

    test_lmstudio_response()
