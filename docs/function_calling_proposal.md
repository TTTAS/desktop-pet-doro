# 方案 2：Function Calling / Tool Use

## 概念

讓 LLM 調用預定義的「函數」來執行動作，而不是輸出文字指令。

## 函數定義

```python
DORO_FUNCTIONS = [
    {
        "name": "set_state_and_speak",
        "description": "設定 Doro 的情緒狀態並說話",
        "parameters": {
            "type": "object",
            "properties": {
                "state": {
                    "type": "string",
                    "enum": ["HAPPY", "SAD", "EXCITED", "SHY", "SLEEPY", "IDLE", "THINK"],
                    "description": "Doro 當前的情緒狀態"
                },
                "dialogue": {
                    "type": "string",
                    "description": "Doro 說的話（繁體中文，1-2句，可愛活潑語氣）"
                }
            },
            "required": ["state", "dialogue"]
        }
    },
    {
        "name": "move",
        "description": "讓 Doro 移動到指定方向",
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["left", "right", "up", "down", "up-left", "up-right", "down-left", "down-right"],
                    "description": "移動方向（八方向之一）"
                },
                "distance": {
                    "type": "integer",
                    "minimum": 20,
                    "maximum": 300,
                    "description": "移動距離（像素）"
                },
                "speed": {
                    "type": "string",
                    "enum": ["slow", "med", "fast"],
                    "default": "med"
                }
            },
            "required": ["direction", "distance"]
        }
    }
]
```

## API 請求範例

```python
payload = {
    "model": "lmstudio",
    "messages": messages,
    "tools": DORO_FUNCTIONS,
    "tool_choice": "auto"  # LLM 自動決定是否調用函數
}
```

## LLM 回傳範例

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "tool_calls": [
        {
          "id": "call_1",
          "type": "function",
          "function": {
            "name": "set_state_and_speak",
            "arguments": "{\"state\": \"HAPPY\", \"dialogue\": \"人～你回來啦，doro在等你喔～\"}"
          }
        },
        {
          "id": "call_2",
          "type": "function",
          "function": {
            "name": "move",
            "arguments": "{\"direction\": \"right\", \"distance\": 80, \"speed\": \"med\"}"
          }
        }
      ]
    }
  }]
}
```

## 處理邏輯

```python
def handle_tool_calls(tool_calls):
    for call in tool_calls:
        if call.function.name == "set_state_and_speak":
            args = json.loads(call.function.arguments)
            state_service.set_state(args["state"].lower())
            window.set_bubble_text(args["dialogue"])

        elif call.function.name == "move":
            args = json.loads(call.function.arguments)
            movement_manager.move(
                direction=args["direction"],
                distance=args["distance"],
                speed=args.get("speed", "med")
            )
```

## 優點

✅ **最可靠** - LLM 只能調用預定義函數，不可能格式錯誤
✅ **類型安全** - 參數自動驗證
✅ **語義清晰** - 函數名稱明確表達意圖
✅ **易於擴展** - 新增功能只需添加新函數

## 缺點

⚠️ LM Studio 對 Tool Use 的支持可能有限（需要測試）
⚠️ 需要較大幅度重構（~3 小時工作量）
⚠️ 某些舊版 LLM 不支持 function calling

## 實現成本

- **修改文件**：`controller.py`, `orchestrator.py`, `chat.py`
- **工作量**：3-4 小時
- **風險**：中（需要測試 LM Studio 支持程度）

## 兼容性檢查

```bash
# 測試 LM Studio 是否支持 tools/functions
curl http://localhost:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "lmstudio",
    "messages": [{"role": "user", "content": "Move to the right"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "move",
        "parameters": {
          "type": "object",
          "properties": {
            "direction": {"type": "string", "enum": ["left", "right"]}
          }
        }
      }
    }]
  }'
```

如果支持，回應會包含 `tool_calls` 字段。
