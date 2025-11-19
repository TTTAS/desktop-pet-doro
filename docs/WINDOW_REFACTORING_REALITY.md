# Window.py 重構現實檢查

## 📊 當前狀況

```
Window.py: 1759 行, 98 個方法
目標: <1000 行
需要減少: ~800 行 (45%)
```

## 🔍 殘酷的真相

### 我剛才做了什麼？

✅ 創建了 `ChatUIHelper` 類（149 行 chat 相關代碼）

### 這有用嗎？

**❌ 幾乎沒用**

為什麼？

```python
# 之前 (in window.py):
def _prompt_chat(self):
    text, ok = QtWidgets.QInputDialog.getText(...)
    if ok:
        self._chat_orchestrator.send_message(text)

# 之後 (with helper):
def _prompt_chat(self):
    self._chat_helper.prompt_chat()  # 仍然需要這個wrapper

# 實際減少: 2-3 行而已！
```

## 💡 問題在哪裡？

### 重構 ≠ 減少代碼

**重構 (Refactoring):**
- 移動代碼到別的文件
- 改善結構
- 提高可維護性
- **代碼總量不變**

**減少代碼 (Code Reduction):**
- 刪除功能
- 簡化邏輯
- 合併重複代碼
- **實際減少行數**

### 你要的是什麼？

如果你要 window.py **<1000 行**，你需要：

1. **刪除功能** (~400 行)
2. **簡化邏輯** (~200 行)
3. **合併重複代碼** (~200 行)

**不是** "把代碼移到別的文件"。

## 🎯 實際可以減少的地方

### 1. 刪除過時/未使用的方法 (~150 行)

```python
# 這些方法可能沒人用：
def _ensure_local_gif_for_state(...)  # 47 lines
def _apply_move_gif_update(...)        # 30 lines
def _classify_action_token(...)        # 45 lines
```

### 2. 簡化過度複雜的方法 (~200 行)

```python
# paintEvent: 180 行 -> 可以簡化到 100 行
# _apply_state_settings: 50 行 -> 可以簡化到 20 行
# _find_state_for_action: 40 行 -> 可以簡化到 15 行
```

### 3. 內聯簡單的 wrapper 方法 (~100 行)

```python
# 這些只是簡單的代理，可以直接調用:
def get_state(self, key):
    return self._state_service.get_state(key)  # 直接用 _state_service

def has_state(self, key):
    return self._state_service.has_state(key)  # 刪除這個

def save_states(self):
    return self._state_service.save_states()   # 刪除這個
```

### 4. 合併重複的 config dialog 邏輯 (~150 行)

```python
# 8 個 configure_chat_* 方法幾乎一樣
# 可以合併成 1 個通用方法
def _configure_chat_setting(setting_name, setting_type, ...):
    ...
```

### 5. 移除詳細的 docstrings (~100 行)

```python
# 之前:
def _set_bubble_text(self, text: str):
    """
    Set bubble text.

    Args:
        text: The text to display

    This method sets the bubble text and schedules
    an auto-hide timer if configured...
    """
    self._bubble_text = text

# 之後:
def _set_bubble_text(self, text: str):
    """Set bubble text."""
    self._bubble_text = text
```

## 🚀 建議的實際行動方案

### 選項 A: 暴力減少（快速，殘酷）

**1 小時，減少 ~600 行**

1. 刪除所有未使用的方法（2 個工具可以檢測）
2. 移除詳細 docstrings
3. 內聯所有簡單 wrapper
4. 合併重複的 dialog 邏輯

**結果:** 1759 -> ~1150 行

### 選項 B: 精簡核心功能（中等，務實）

**2-3 小時，減少 ~700 行**

1. 選項 A 的所有內容
2. 簡化 paintEvent (180 -> 100 行)
3. 簡化狀態管理邏輯
4. 移除一些很少用的功能

**結果:** 1759 -> ~1050 行

### 選項 C: 專業重構（長期，正確）

**6-8 小時，減少 ~800 行**

1. 選項 B 的所有內容
2. 真正拆分成 MVC 架構
3. 創建完整的 UI controllers
4. 單元測試確保不破壞功能

**結果:** 1759 -> ~950 行

## 🔥 我的殘酷建議

### 你現在應該做什麼？

**選擇選項 A - 暴力減少**

為什麼？

1. **快** - 1 小時完成
2. **安全** - 只刪除明顯不用的東西
3. **有效** - 實際減少代碼
4. **可逆** - git可以恢復

### 不要做什麼？

❌ 花時間創建 "完美的架構"
❌ 寫更多 helper 類
❌ 過度設計

### 為什麼？

**因為你的目標是 <1000 行，不是贏得架構設計獎。**

## 📝 下一步？

告訴我你選哪個：

**A** - 暴力減少（1 小時）
**B** - 精簡功能（2-3 小時）
**C** - 專業重構（6-8 小時）
**D** - 保持現狀（承認 1759 行也可以）

---

**你的選擇？**
