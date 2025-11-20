# Doro 主題聊天對話框設計

## 概述

新的聊天對話框使用與右鍵選單相同的 Doro 主題色，提供更加統一和精緻的用戶體驗。

## 設計特點

### 顏色方案（與 themed_menu.py 一致）

```python
doro_pink = "#FF9BE3"        # 主要粉紅色（doro 的頭髮顏色）
doro_light_pink = "#FFC4F0"  # 淺粉紅色
doro_dark_pink = "#E86BD1"   # 深粉紅色
```

### 背景漸變
```css
background-color: qlineargradient(
    x1:0, y1:0, x2:0, y2:1,
    stop:0 #FFFFFF,      /* 頂部：純白色 */
    stop:0.05 #FFF5FC,   /* 淺粉色 */
    stop:1 #FFE8F7       /* 底部：更深的粉色 */
);
```

### 邊框和圓角
- **外框邊框**: 3px solid #FF9BE3
- **圓角**: 16px（主容器）
- **輸入框圓角**: 8px
- **按鈕圓角**: 8px

## UI 元素

### 1. 標題欄
```
💬 與 Doro 說話
```
- 顏色：深粉紅色 (#E86BD1)
- 字體：16pt, 粗體
- 居中對齊

### 2. 說明文字
```
輸入你想對 doro 說的話：
```
- 顏色：深灰色 (#2D2D2D)
- 字體：10pt

### 3. 多行輸入框
- 白色背景
- 淺粉紅色邊框 (#FFC4F0)
- 焦點時邊框變為主粉紅色 (#FF9BE3)
- 最大高度：120px
- 佔位符文字：「在這裡輸入訊息...」
- 只接受純文本（不接受富文本）

### 4. 字元計數器
```
0 字元
```
- 顏色：灰色 (#666666)
- 字體：9pt
- 右對齊
- 即時更新

### 5. 按鈕組

#### 清除按鈕
- 白色背景
- 灰色文字
- 懸停時變淺灰色背景
- 功能：清空輸入框

#### 取消按鈕
- 白色背景
- 灰色文字
- 懸停時變淺灰色背景
- 功能：關閉對話框（不發送）

#### 發送按鈕 ✉
- 粉紅色漸變背景
- 白色文字
- 粗體
- 懸停時變為深粉紅色
- 按下時變為更深的粉紅色
- 功能：發送訊息
- **預設按鈕**（按 Enter 鍵觸發）

## 互動行為

### 1. 拖曳移動
- 可以點擊對話框任意位置拖曳移動
- 無標題欄（Frameless）設計
- 實現：`mousePressEvent` 和 `mouseMoveEvent`

### 2. 輸入驗證
- 如果輸入為空，點擊發送會顯示警告
- 警告訊息：「請輸入一些文字後再發送。」
- 不會關閉對話框

### 3. 鍵盤快捷鍵
- **Enter 鍵**：發送訊息（因為發送按鈕是 default）
- **Shift+Enter**：換行（QTextEdit 預設行為）
- **Esc 鍵**：取消（QDialog 預設行為）

### 4. 焦點管理
- 對話框開啟時，輸入框自動獲得焦點
- 用戶可以直接開始輸入

## 樣式細節

### 按鈕懸停效果

**一般按鈕（清除、取消）**:
```
正常：白色背景 → 懸停：淺灰色背景 (#F0F0F0)
```

**發送按鈕**:
```
正常：淺粉→粉紅漸變
懸停：粉紅→深粉紅漸變
按下：深粉紅純色
```

### 輸入框焦點效果
```
正常：邊框 #FFC4F0（淺粉紅）
焦點：邊框 #FF9BE3（主粉紅）+ 背景 #FFFCFE（極淺粉）
```

## 程式碼結構

### 文件位置
```
doro_app/ui/dialogs/chat_dialog.py
```

### 主要類別
```python
class DoroChatDialog(QtWidgets.QDialog):
    """Doro-themed chat dialog"""
```

### 輔助函數
```python
def show_chat_dialog(parent) -> tuple[str, bool]:
    """顯示對話框並返回結果"""
    # 返回: (訊息文字, 是否確認)
```

## 使用方法

### 在 ChatUIHelper 中使用
```python
from ..dialogs.chat_dialog import show_chat_dialog

def prompt_chat(self) -> None:
    text, ok = show_chat_dialog(self.window)
    if not ok or not text.strip():
        return

    self.window._chat_orchestrator.send_message(text.strip())
```

### 直接使用
```python
from doro_app.ui.dialogs.chat_dialog import DoroChatDialog

dialog = DoroChatDialog(parent)
if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
    message = dialog.get_message()
    print(f"用戶說：{message}")
```

## 與舊版的比較

### 舊版（QInputDialog）
```python
text, ok = QtWidgets.QInputDialog.getText(
    self.window,
    "與 Doro 對話",
    "輸入訊息:",
)
```
- ❌ 單行輸入
- ❌ 系統預設樣式
- ❌ 不符合 Doro 主題
- ❌ 無字元計數
- ❌ 簡陋的外觀

### 新版（DoroChatDialog）
```python
text, ok = show_chat_dialog(self.window)
```
- ✅ 多行輸入
- ✅ Doro 主題色
- ✅ 與選單樣式一致
- ✅ 字元計數顯示
- ✅ 精緻的外觀
- ✅ 可拖曳移動
- ✅ 清除按鈕
- ✅ 懸停效果

## 尺寸規格

```
最小寬度：400px
最小高度：200px
輸入框最大高度：120px
按鈕最小高度：36px
內邊距：16px
按鈕間距：8px
元素間距：12px
```

## 透明度設置

```python
# 對話框背景透明（用於圓角和陰影）
self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)

# 無邊框（自定義外觀）
self.setWindowFlags(
    QtCore.Qt.WindowType.Dialog |
    QtCore.Qt.WindowType.FramelessWindowHint
)
```

## 未來改進建議

### 1. 歷史記錄顯示
在對話框上方顯示最近的幾條對話記錄，讓用戶可以看到上下文。

### 2. 表情符號選擇器
添加一個表情符號按鈕，讓用戶可以插入表情。

### 3. 語音輸入
如果系統支持，添加語音輸入功能。

### 4. 快速回覆按鈕
預設一些常用問候語（如「嗨」、「在嗎」、「你好」）作為快速按鈕。

### 5. Doro 頭像
在對話框角落添加 Doro 的小頭像（類似右鍵選單）。

### 6. 動畫效果
添加開啟/關閉的淡入淡出動畫。

### 7. 記住位置
記住對話框的位置，下次開啟時在同一位置顯示。

## 測試場景

### 場景 1：正常輸入
1. 右鍵選單 → Chat → Ask Doro
2. 輸入訊息：「你好呀～」
3. 點擊「發送」
4. 對話框關閉，doro 回應

### 場景 2：多行輸入
1. 開啟對話框
2. 輸入多行文字（使用 Shift+Enter 換行）
3. 字元計數即時更新
4. 發送訊息

### 場景 3：清除功能
1. 輸入一些文字
2. 點擊「清除」按鈕
3. 輸入框清空
4. 字元計數重置為 0

### 場景 4：取消操作
1. 輸入文字
2. 點擊「取消」
3. 對話框關閉
4. 訊息未發送

### 場景 5：空輸入驗證
1. 不輸入任何文字（或只輸入空格）
2. 點擊「發送」
3. 顯示警告訊息
4. 對話框保持開啟

### 場景 6：拖曳移動
1. 開啟對話框
2. 點擊對話框任意位置（除按鈕外）
3. 拖曳移動
4. 對話框跟隨滑鼠移動

## 樣式一致性檢查

✅ 使用相同的粉紅色調 (#FF9BE3)
✅ 相同的漸變效果（白色→淺粉色）
✅ 相同的圓角設計（16px 主容器）
✅ 相同的懸停效果（粉紅色高亮）
✅ 相同的邊框樣式（2-3px solid）
✅ 相同的字體大小和顏色
✅ 相同的內邊距和間距風格

## 提交信息

```
commit 152eb1e
feat: add Doro-themed chat dialog interface

新增 Doro 主題色的聊天對話框介面
```
