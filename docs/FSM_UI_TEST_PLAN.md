# FSM + UI 層測試計劃

## 🎯 目標

在連接 LLM 之前，先確保狀態機和視覺響應完美配合。

---

## 📋 階段 1：創建基礎狀態集

### 任務 1.1：定義基本情緒狀態

**需要創建的狀態：**

```python
# 基本情緒（最小可用集）
states = {
    "idle":     {"label": "閒置",   "color": "pink"},     # 已存在
    "happy":    {"label": "開心",   "color": "yellow"},
    "sad":      {"label": "難過",   "color": "blue"},
    "excited":  {"label": "興奮",   "color": "orange"},
    "sleeping": {"label": "睡覺",   "color": "purple"},
    "thinking": {"label": "思考",   "color": "cyan"},
}
```

**視覺配置差異：**
| 狀態 | 漸層主色 | 氣泡顯示 | 特殊效果 |
|------|---------|---------|---------|
| idle | 粉紅 | ✓ | 無 |
| happy | 黃色 | ✓ | 臉紅 alpha=255 |
| sad | 藍色 | ✓ | 臉紅 alpha=0 |
| excited | 橘色 | ✓ | bob_amplitude=12 |
| sleeping | 紫色 | ✗ | bubble_visible=False |
| thinking | 青色 | ✓ | scale_amplitude=0.08 |

### 任務 1.2：使用 State Manager Dialog 添加狀態

**步驟：**
1. 啟動應用
2. 右鍵 → States → Edit states
3. 點擊 "Add State" 添加新狀態
4. 為每個狀態設定 GIF（可以先複用 idle.gif）
5. 調整視覺參數（可以用對話框或直接編輯 states.json）

### 任務 1.3：準備測試 GIF

**選項 A：複用現有 GIF**
```bash
# 快速測試：所有狀態先用同一個 GIF
cp res/state/idle.gif res/state/happy.gif
cp res/state/idle.gif res/state/sad.gif
# ... 其他狀態
```

**選項 B：創建不同的 GIF**
- 找不同表情的 GIF 檔案
- 重命名為對應狀態名稱
- 放到 `res/state/` 目錄

---

## 📋 階段 2：手動測試狀態轉換

### 任務 2.1：測試單一狀態切換

**測試清單：**

```markdown
□ 測試 idle → happy
  1. 右鍵 → States → happy
  2. ✓ 檢查：GIF 是否切換
  3. ✓ 檢查：顏色漸層是否改變
  4. ✓ 檢查：臉紅效果是否出現
  5. ✓ 檢查：氣泡是否仍然顯示

□ 測試 happy → sad
  1. 右鍵 → States → sad
  2. ✓ 檢查：顏色變為藍色系
  3. ✓ 檢查：臉紅消失
  4. ✓ 檢查：GIF 切換

□ 測試 idle → sleeping
  1. 右鍵 → States → sleeping
  2. ✓ 檢查：氣泡隱藏
  3. ✓ 檢查：顏色變為紫色
  4. ✓ 檢查：GIF 切換

□ 測試 excited (動畫測試)
  1. 右鍵 → States → excited
  2. ✓ 檢查：bob_amplitude 增大（上下浮動更明顯）
  3. ✓ 檢查：顏色為橘色系

□ 測試 thinking (縮放測試)
  1. 右鍵 → States → thinking
  2. ✓ 檢查：scale_amplitude 增大（呼吸效果）
  3. ✓ 檢查：顏色為青色系
```

### 任務 2.2：測試狀態持久化

```markdown
□ 切換到 happy 狀態
□ 關閉應用
□ 重新啟動應用
□ ✓ 檢查：應該恢復到 happy 狀態（而非 idle）
```

### 任務 2.3：測試移動狀態

```markdown
□ 確認 walking 狀態存在
□ 右鍵 → States → walking
□ ✓ 檢查：是否標記為 movement-only
□ ✓ 檢查：視覺是否正確（如果有對應 GIF）
```

---

## 📋 階段 3：驗證事件流

### 任務 3.1：確認事件觸發順序

**預期流程：**
```
用戶點擊右鍵選單 "happy"
    ↓
window._set_state("happy")
    ↓
StateService.set_state("happy")
    ↓
StateService.on_state_changed 事件觸發
    ↓
DoroWindow._on_state_changed(event)
    ↓
1. 更新 _current_state_key
2. 載入 happy.gif
3. 更新視覺配置
4. 保存到 QSettings
5. 觸發 repaint
```

**驗證方法：**
```python
# 在 _on_state_changed 中添加日誌
def _on_state_changed(self, event: StateChangeEvent) -> None:
    print(f"[FSM] State changed: {event.old_key} → {event.new_key}")
    print(f"[FSM] New state visual config: {event.new_state.visual}")
    # ... 原有邏輯
```

### 任務 3.2：測試邊界情況

```markdown
□ 切換到不存在的狀態
  ✓ 應該：保持當前狀態不變

□ 快速連續切換狀態
  ✓ 應該：每次都正確響應

□ 切換到當前狀態（idle → idle）
  ✓ 應該：仍然觸發更新（重新隨機選擇 GIF 變體）
```

---

## 📋 階段 4：文檔化狀態行為

### 任務 4.1：記錄每個狀態的預期行為

**範例：**
```markdown
## happy 狀態

**視覺效果：**
- 漸層色：黃色系 (#FFEB3B → #FFC107)
- 臉紅：完全顯示 (alpha=255)
- 氣泡：顯示
- 動畫：標準浮動

**使用場景：**
- 收到稱讚時
- 講笑話後
- 完成任務時

**LLM 指令：**
`(STATE: happy)`
```

### 任務 4.2：創建狀態轉換矩陣

**哪些轉換是合理的？**
```
         idle  happy  sad  excited  sleeping  thinking
idle      ✓     ✓     ✓      ✓        ✓         ✓
happy     ✓     ✓     ✗      ✓        ✗         ✓
sad       ✓     ✗     ✓      ✗        ✓         ✓
excited   ✓     ✓     ✗      ✓        ✗         ✗
sleeping  ✓     ✗     ✗      ✗        ✓         ✗
thinking  ✓     ✓     ✓      ✓        ✗         ✓
```

✓ = 允許直接轉換
✗ = 不合理（需要中間狀態）

---

## 🎯 完成標準

**階段 1 完成條件：**
- [ ] 至少有 5 個不同狀態
- [ ] 每個狀態有獨特的視覺配置
- [ ] 每個狀態有對應的 GIF（即使是複用的）

**階段 2 完成條件：**
- [ ] 所有狀態切換都能正確顯示
- [ ] 視覺效果符合預期
- [ ] 狀態持久化正常工作

**階段 3 完成條件：**
- [ ] 事件流程確認無誤
- [ ] 邊界情況處理正確
- [ ] 無錯誤訊息或警告

**階段 4 完成條件：**
- [ ] 所有狀態行為已文檔化
- [ ] 狀態轉換規則明確

---

## ✅ 達成後的好處

完成 FSM + UI 測試後，你將獲得：

1. **穩定的基礎** - 狀態系統經過充分測試
2. **清晰的狀態列表** - 給 LLM 使用的明確指令集
3. **快速 Debug** - 問題出在 LLM 還是狀態機一目了然
4. **更好的 Prompt** - 知道每個狀態的實際效果，可以寫更準確的 prompt

---

## 🚀 下一步：連接 LLM

當 FSM + UI 測試完成後，連接 LLM 就很簡單：

1. 更新 prompt.txt 包含狀態列表
2. 測試 LLM 是否能正確輸出指令
3. 觀察 ChatOrchestrator 是否正確解析
4. 享受智能驅動的桌面寵物！

---

## 📝 測試記錄範本

```markdown
## 測試日期：2025-11-11

### 測試項目：idle → happy 轉換

**步驟：**
1. 啟動應用（當前狀態：idle）
2. 右鍵 → States → happy

**預期結果：**
- GIF 切換到 happy.gif
- 顏色變為黃色系
- 臉紅顯示

**實際結果：**
- [✓] GIF 切換正常
- [✓] 顏色正確
- [✗] 臉紅未顯示 ← 需要檢查 cheeks_alpha 設定

**問題：**
cheeks_alpha 在 VisualConfig 中未正確設定

**解決方案：**
更新 states.json 中 happy 狀態的 visual.cheeks_alpha = 255
```
