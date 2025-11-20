# 方案 1：Structured Output (JSON Schema)

## 概念

LM Studio 和大多數現代 LLM API 支持 **Structured Output** 或 **JSON mode**，強制 LLM 輸出符合指定 schema 的 JSON。

## JSON Schema 定義

```json
{
  "type": "object",
  "properties": {
    "state": {
      "type": "string",
      "enum": ["HAPPY", "SAD", "EXCITED", "SHY", "SLEEPY", "IDLE", "THINK"],
      "description": "Doro 的情緒狀態"
    },
    "dialogue": {
      "type": "string",
      "minLength": 1,
      "maxLength": 100,
      "description": "Doro 說的話（繁體中文，1-2句）"
    },
    "movement": {
      "type": "object",
      "properties": {
        "enabled": {
          "type": "boolean",
          "description": "是否需要移動"
        },
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
          "default": "med",
          "description": "移動速度"
        }
      },
      "required": ["enabled"]
    }
  },
  "required": ["state", "dialogue", "movement"]
}
```

## API 請求範例

```python
payload = {
    "model": "lmstudio",
    "messages": messages,
    "temperature": 0.7,
    "response_format": {
        "type": "json_schema",
        "json_schema": {
            "name": "doro_response",
            "strict": True,  # OpenAI compatible strict mode
            "schema": DORO_RESPONSE_SCHEMA
        }
    }
}
```

## LLM 保證回傳格式

```json
{
  "state": "HAPPY",
  "dialogue": "人～你回來啦，doro在等你喔～",
  "movement": {
    "enabled": true,
    "direction": "right",
    "distance": 80,
    "speed": "med"
  }
}
```

## 優點

✅ **100% 保證格式正確** - API 層面強制，不可能偏離
✅ **不需要正則解析** - 直接讀取 JSON
✅ **類型安全** - state 只能是預定義的枚舉值
✅ **自動驗證** - distance 自動限制在 20-300 之間
✅ **無需重試** - 第一次就正確

## 缺點

⚠️ 需要確認 LM Studio 版本支持（OpenAI API v1.0+ 功能）
⚠️ 需要修改 ChatController 的 payload 構建邏輯（~1 小時工作量）

## 實現成本

- **修改文件**：`controller.py`, `orchestrator.py`, `chat.py`
- **工作量**：2-3 小時
- **風險**：低（向下兼容，可以保留 fallback）

## 兼容性檢查

```bash
# 測試 LM Studio 是否支持 response_format
curl http://localhost:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "lmstudio",
    "messages": [{"role": "user", "content": "Say hello"}],
    "response_format": {"type": "json_object"}
  }'
```

如果支持，回應會是 JSON 格式而非純文字。
