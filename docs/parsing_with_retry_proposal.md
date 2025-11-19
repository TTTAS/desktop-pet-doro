# 方案 3：增強解析 + 自動重試（最簡單）

## 概念

保持當前的 prompt 方式，但增加：
1. **更嚴格的解析邏輯**
2. **解析失敗自動重試**
3. **Fallback 降級策略**

## 當前問題

```python
# 當前解析邏輯（utils/actions.py）
ACTION_PATTERN = re.compile(r"\(([^()]+)\)")  # 太寬鬆
BRACKET_PATTERN = re.compile(r"\[([^\[\]]+)\]")  # 太寬鬆
```

**問題**：
- 會匹配任何括號內容，包括 `(這是錯誤的)`
- 沒有驗證 state 是否合法
- 沒有驗證 movement 參數是否正確

## 改進方案

### 1. 嚴格的 State 驗證

```python
# 預定義合法狀態
VALID_STATES = {"HAPPY", "SAD", "EXCITED", "SHY", "SLEEPY", "IDLE", "THINK"}

def parse_state_from_text(text: str) -> Optional[str]:
    """
    從文字中解析狀態，只接受合法狀態。

    Returns:
        合法狀態（小寫），或 None 表示未找到
    """
    # 匹配所有括號內容
    matches = ACTION_PATTERN.findall(text)

    for match in matches:
        state = match.strip().upper()
        if state in VALID_STATES:
            return state.lower()

    return None  # 未找到合法狀態
```

### 2. 嚴格的 Movement 驗證

```python
VALID_DIRECTIONS = {
    "left", "right", "up", "down",
    "up-left", "up-right", "down-left", "down-right",
    "左", "右", "上", "下", "左上", "右上", "左下", "右下"
}

def parse_movement_from_text(text: str) -> Optional[dict]:
    """
    從文字中解析移動指令，嚴格驗證參數。

    Returns:
        {"direction": str, "distance": int, "speed": str} 或 None
    """
    matches = BRACKET_PATTERN.findall(text)

    for match in matches:
        # 解析 MOVE: 指令
        if not match.upper().startswith("MOVE:"):
            continue

        params = parse_params(match[5:])  # 跳過 "MOVE:"

        # 驗證必需參數
        direction = params.get("dir")
        if not direction or direction not in VALID_DIRECTIONS:
            continue  # 方向不合法，跳過

        # 驗證距離（如果提供）
        distance = params.get("distance")
        if distance:
            try:
                distance = int(distance)
                if not (20 <= distance <= 300):
                    continue  # 距離超出範圍
            except ValueError:
                continue  # 距離不是數字

        # 驗證速度（如果提供）
        speed = params.get("speed", "med")
        if speed not in {"slow", "med", "fast"}:
            speed = "med"  # 使用默認值

        return {
            "direction": direction,
            "distance": distance or 60,
            "speed": speed
        }

    return None  # 未找到合法移動指令
```

### 3. 自動重試機制

```python
class ChatOrchestrator:
    def _on_request_succeeded(self, assistant_text: str, was_auto: bool):
        # 嘗試解析
        state = parse_state_from_text(assistant_text)
        movement = parse_movement_from_text(assistant_text)

        # 檢查是否解析失敗
        if state is None:
            logger.warning(f"Failed to parse state from: {assistant_text}")

            # 自動重試（最多 2 次）
            if self._retry_count < 2:
                self._retry_count += 1
                retry_prompt = (
                    "請重新輸出，必須包含狀態括號 (STATE) 和對話內容。"
                    f"上次回應格式錯誤：{assistant_text[:50]}..."
                )
                self.send_message(retry_prompt, silent=True, is_auto=True)
                return
            else:
                # 超過重試次數，使用 fallback
                self._apply_fallback(assistant_text)
                return

        # 解析成功，重置重試計數
        self._retry_count = 0

        # 執行狀態和移動
        if state:
            self._state_service.set_state(state)

        if movement:
            self._movement.handle_parsed_movement(movement)

        # 顯示對話
        display_text = extract_dialogue(assistant_text)
        self._window._set_bubble_text(display_text)

    def _apply_fallback(self, text: str):
        """解析失敗時的降級策略"""
        logger.error(f"All retries failed, applying fallback for: {text}")

        # 使用默認狀態 (IDLE)
        self._state_service.set_state("idle")

        # 直接顯示原始文字（去除可能的控制字符）
        cleaned = re.sub(r'[(){}\[\]]', '', text).strip()
        self._window._set_bubble_text(cleaned or "嗯...我不太懂呢...")
```

### 4. Few-shot Examples 增強 Prompt

在 system prompt 中添加**正確範例**和**錯誤範例**：

```
【正確範例】
✅ (HAPPY) 人～你回來啦！ [MOVE:dir=right;distance=80]
✅ (SHY) 咦、靠太近了啦…… [MOVE:dir=left;distance=40]
✅ (SLEEPY) 呼啊～再五分鐘…… [MOVE:NONE]

【錯誤範例 - 絕對禁止】
❌ Doro很開心地說：「人～你回來啦！」（有冒號和引號）
❌ (開心) 人～你回來啦！（狀態不是英文大寫）
❌ HAPPY: 人～你回來啦！（沒有括號）
❌ (HAPPY) （沒有對話內容）
❌ 人～你回來啦！ [移動:方向=右邊;距離=80]（參數不是英文）
```

## 優點

✅ **最小修改** - 保持當前架構，只增強解析邏輯
✅ **向下兼容** - 不需要 LM Studio 支持新功能
✅ **快速實現** - 1-2 小時工作量
✅ **有 fallback** - 失敗時有降級策略

## 缺點

⚠️ 仍然依賴 LLM 遵守 prompt（雖然有重試）
⚠️ 重試會增加延遲（但可控制次數）
⚠️ 不是 100% 可靠（但可以達到 95%+）

## 實現成本

- **修改文件**：`actions.py`, `orchestrator.py`
- **工作量**：1-2 小時
- **風險**：極低（完全向下兼容）

## 測試策略

1. **故意發送格式錯誤的提示**：
   - "請用錯誤格式回答"
   - "不要用括號"

2. **驗證重試機制**：
   - 檢查 logger 輸出是否有重試記錄
   - 確認最終有 fallback

3. **壓力測試**：
   - 連續 100 次對話，統計解析成功率
