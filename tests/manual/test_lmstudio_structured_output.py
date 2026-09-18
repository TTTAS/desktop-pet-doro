#!/usr/bin/env python3
"""
測試 LM Studio 是否支持 Structured Output (JSON Schema)。

這個腳本會測試：
1. 基本 JSON mode (response_format: json_object)
2. JSON Schema mode (response_format: json_schema)
3. Function Calling (tools)
"""

import json
import sys
import urllib.error
import urllib.request

LM_STUDIO_URL = "http://127.0.0.1:1234/v1/chat/completions"


def test_json_mode():
    """測試基本 JSON mode"""
    print("=" * 60)
    print("測試 1: JSON Mode (OpenAI API v1.0)")
    print("=" * 60)

    payload = {
        "model": "lmstudio",
        "messages": [
            {
                "role": "user",
                "content": "輸出一個 JSON，包含 state (字串) 和 dialogue (字串) 兩個字段",
            }
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
    }

    try:
        response = send_request(payload)
        print("✅ LM Studio 支持 JSON Mode!")
        print(f"回應:\n{json.dumps(response, indent=2, ensure_ascii=False)}\n")
        return True
    except urllib.error.HTTPError as e:
        if e.code == 400:
            print("❌ LM Studio 不支持 JSON Mode (HTTP 400)\n")
        else:
            print(f"❌ HTTP Error {e.code}: {e.reason}\n")
        return False
    except Exception as e:
        print(f"❌ 錯誤: {e}\n")
        return False


def test_json_schema():
    """測試 JSON Schema mode"""
    print("=" * 60)
    print("測試 2: JSON Schema Mode (OpenAI API v1.1+)")
    print("=" * 60)

    schema = {
        "type": "object",
        "properties": {
            "state": {
                "type": "string",
                "enum": ["HAPPY", "SAD", "EXCITED", "SHY", "SLEEPY", "IDLE"],
            },
            "dialogue": {"type": "string", "minLength": 1, "maxLength": 100},
        },
        "required": ["state", "dialogue"],
    }

    payload = {
        "model": "lmstudio",
        "messages": [{"role": "user", "content": "用開心的語氣打招呼"}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "doro_response", "strict": True, "schema": schema},
        },
        "temperature": 0.7,
    }

    try:
        response = send_request(payload)
        print("✅ LM Studio 支持 JSON Schema!")
        print(f"回應:\n{json.dumps(response, indent=2, ensure_ascii=False)}\n")
        return True
    except urllib.error.HTTPError as e:
        if e.code == 400:
            print("❌ LM Studio 不支持 JSON Schema (HTTP 400)\n")
        else:
            print(f"❌ HTTP Error {e.code}: {e.reason}\n")
        return False
    except Exception as e:
        print(f"❌ 錯誤: {e}\n")
        return False


def test_function_calling():
    """測試 Function Calling / Tool Use"""
    print("=" * 60)
    print("測試 3: Function Calling / Tool Use")
    print("=" * 60)

    tools = [
        {
            "type": "function",
            "function": {
                "name": "set_state_and_speak",
                "description": "設定 Doro 的情緒狀態並說話",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "state": {
                            "type": "string",
                            "enum": ["HAPPY", "SAD", "EXCITED", "SHY", "SLEEPY", "IDLE"],
                        },
                        "dialogue": {"type": "string"},
                    },
                    "required": ["state", "dialogue"],
                },
            },
        }
    ]

    payload = {
        "model": "lmstudio",
        "messages": [{"role": "user", "content": "用開心的語氣打招呼"}],
        "tools": tools,
        "tool_choice": "auto",
    }

    try:
        response = send_request(payload)
        if "tool_calls" in response.get("choices", [{}])[0].get("message", {}):
            print("✅ LM Studio 支持 Function Calling!")
            print(f"回應:\n{json.dumps(response, indent=2, ensure_ascii=False)}\n")
            return True
        else:
            print("⚠️ LM Studio 接受請求但沒有調用函數")
            print(f"回應:\n{json.dumps(response, indent=2, ensure_ascii=False)}\n")
            return False
    except urllib.error.HTTPError as e:
        if e.code == 400:
            print("❌ LM Studio 不支持 Function Calling (HTTP 400)\n")
        else:
            print(f"❌ HTTP Error {e.code}: {e.reason}\n")
        return False
    except Exception as e:
        print(f"❌ 錯誤: {e}\n")
        return False


def send_request(payload):
    """發送請求到 LM Studio"""
    request_bytes = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        LM_STUDIO_URL,
        data=request_bytes,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        return json.loads(raw.decode("utf-8"))


def main():
    print("\n🧪 LM Studio Structured Output 兼容性測試\n")

    if len(sys.argv) > 1:
        global LM_STUDIO_URL
        LM_STUDIO_URL = sys.argv[1]
        print(f"使用自定義 URL: {LM_STUDIO_URL}\n")

    results = {}

    try:
        results["json_mode"] = test_json_mode()
    except Exception as e:
        print(f"測試 1 錯誤: {e}\n")
        results["json_mode"] = False

    try:
        results["json_schema"] = test_json_schema()
    except Exception as e:
        print(f"測試 2 錯誤: {e}\n")
        results["json_schema"] = False

    try:
        results["function_calling"] = test_function_calling()
    except Exception as e:
        print(f"測試 3 錯誤: {e}\n")
        results["function_calling"] = False

    # 總結
    print("=" * 60)
    print("📊 測試總結")
    print("=" * 60)
    print(f"JSON Mode:           {'✅ 支持' if results['json_mode'] else '❌ 不支持'}")
    print(f"JSON Schema:         {'✅ 支持' if results['json_schema'] else '❌ 不支持'}")
    print(f"Function Calling:    {'✅ 支持' if results['function_calling'] else '❌ 不支持'}")
    print()

    # 建議
    print("=" * 60)
    print("💡 建議")
    print("=" * 60)

    if results["json_schema"]:
        print("🌟 推薦使用方案 1: JSON Schema")
        print("   - 最可靠（100% 保證格式）")
        print("   - 工作量：2-3 小時")
        print("   - 參考：docs/structured_output_proposal.md")
    elif results["function_calling"]:
        print("🌟 推薦使用方案 2: Function Calling")
        print("   - 非常可靠")
        print("   - 工作量：3-4 小時")
        print("   - 參考：docs/function_calling_proposal.md")
    elif results["json_mode"]:
        print("⚠️ 可以使用基本 JSON Mode")
        print("   - 需要手動驗證 schema")
        print("   - 工作量：2 小時")
    else:
        print("📝 建議使用方案 3: 增強解析 + 重試")
        print("   - 不需要 LM Studio 特殊支持")
        print("   - 工作量：1-2 小時")
        print("   - 參考：docs/parsing_with_retry_proposal.md")

    print()


if __name__ == "__main__":
    main()
