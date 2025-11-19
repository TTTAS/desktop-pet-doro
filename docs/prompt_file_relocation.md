# dia_prompt.txt 移動記錄

## 變更摘要

將 `dia_prompt.txt` 從 `res/` 根目錄移動到 `res/chat/` 子目錄，以更好地組織聊天相關檔案。

---

## 檔案移動

### 舊路徑
```
doro_app/res/dia_prompt.txt
```

### 新路徑
```
doro_app/res/chat/dia_prompt.txt
```

---

## 程式碼變更

### 1. doro_app/utils/paths.py

**新增常數**：
```python
CHAT_DIR = RESOURCES_DIR / "chat"
```

**更新路徑**：
```python
# 舊版
PROMPT_PATH = RESOURCES_DIR / "dia_prompt.txt"

# 新版
PROMPT_PATH = CHAT_DIR / "dia_prompt.txt"
```

### 2. 使用 PROMPT_PATH 的檔案（無需修改）

以下檔案從 `paths.py` 導入 `PROMPT_PATH`，自動使用新路徑：

- **doro_app/window.py** (第 40 行導入，第 154 行使用)
  ```python
  from .utils.paths import PROMPT_PATH
  # ...
  self._prompt_file_path = PROMPT_PATH
  ```

- **doro_app/cli.py** (第 13 行導入，第 24 行使用)
  ```python
  from .utils.paths import PROMPT_PATH
  # ...
  prompt_path = PROMPT_PATH
  ```

### 3. 文檔更新

- **docs/chat_architecture_current.md** (第 372 行)
  ```markdown
  舊：`doro_app/res/dia_prompt.txt`
  新：`doro_app/res/chat/dia_prompt.txt`
  ```

---

## 新的資料夾結構

```
doro_app/res/
├── chat/                    ← 新建資料夾
│   └── dia_prompt.txt       ← 移動到這裡
├── state/
│   └── (狀態檔案)
├── ACTION/
│   ├── MOVE/
│   └── TRANSITION/
├── click.txt
└── (未來: companion.txt)
```

---

## 優點

### 1. 更好的組織
- 所有聊天相關檔案集中在 `chat/` 資料夾
- 未來可以添加更多聊天相關檔案（如 `companion.txt`）

### 2. 清晰的結構
```
res/
├── chat/          # 聊天功能
├── state/         # 狀態定義
├── ACTION/        # 動作/動畫
└── *.txt          # 其他配置
```

### 3. 易於維護
- 相關檔案在同一位置
- 減少混亂
- 符合模組化原則

---

## 向後兼容性

✅ **完全兼容**

所有使用 `PROMPT_PATH` 的程式碼都從 `paths.py` 導入，無需修改：
- `window.py` - 自動使用新路徑
- `cli.py` - 自動使用新路徑
- 未來的程式碼只需導入 `PROMPT_PATH`

---

## 驗證

### 測試路徑
```python
from doro_app.utils.paths import PROMPT_PATH
print(PROMPT_PATH)
# 輸出: /path/to/doro_app/res/chat/dia_prompt.txt
print(PROMPT_PATH.exists())
# 輸出: True
```

### 測試應用
```bash
python doro.py
# 應用正常啟動，聊天功能正常
```

---

## Git 歷史保留

使用 `git mv` 移動檔案，保留完整的 git 歷史：
```bash
git mv doro_app/res/dia_prompt.txt doro_app/res/chat/dia_prompt.txt
```

Git 顯示：
```
rename doro_app/res/{ => chat}/dia_prompt.txt (100%)
```

這表示 git 識別為重命名操作，所有歷史記錄都保留。

---

## 提交信息

```
commit 3eabd9b
refactor: move dia_prompt.txt to chat directory

將 dia_prompt.txt 移動到 chat 資料夾並更新所有引用路徑
```

---

## 未來擴展

現在 `chat/` 資料夾已建立，可以輕鬆添加更多聊天相關檔案：

### 計劃中的檔案
```
doro_app/res/chat/
├── dia_prompt.txt          ← 主要系統 prompt
├── companion.txt           ← 陪伴模式 prompts（paths.py 已定義）
├── greetings.txt           ← 問候語範本
├── responses.txt           ← 快速回應範本
└── personality.txt         ← 性格設定
```

### 添加新檔案範例
```python
# 在 paths.py 中添加
GREETINGS_PATH = CHAT_DIR / "greetings.txt"

# 在程式中使用
from doro_app.utils.paths import GREETINGS_PATH
greetings = load_text(GREETINGS_PATH)
```

---

## 總結

✅ 檔案已移動：`res/dia_prompt.txt` → `res/chat/dia_prompt.txt`
✅ 路徑已更新：`paths.py` 中的 `PROMPT_PATH`
✅ 所有引用自動更新（透過 `paths.py` 導入）
✅ 文檔已更新
✅ Git 歷史保留
✅ 向後兼容
✅ 驗證通過

組織結構更清晰，為未來擴展奠定基礎。
