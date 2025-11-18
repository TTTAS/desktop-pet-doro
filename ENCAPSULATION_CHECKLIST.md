# 封裝完整性檢查清單

## 🎯 檢查目標
確認 `StateService` 的 `gif_repo` 是否真正封裝，還是只是「假封裝」。

---

## ✅ 檢查步驟

### 1️⃣ 檢查：外部是否能直接訪問內部物件
```bash
# 找出所有外部訪問 .gif_repo 的程式碼（排除 StateService 和 StateRepository 內部）
grep -rn "\.gif_repo\." doro_app/ --include="*.py" | \
  grep -v "self\._gif_repo\." | \
  grep -v "^doro_app/state_service.py:" | \
  grep -v "^doro_app/state_repository.py:"
```

**判斷標準：**
- ✅ **無結果** = 外部無法直接訪問（好）
- ❌ **有結果** = 外部仍能繞過封裝（壞）

**實際結果：** ✅ 無外部直接訪問

---

### 2️⃣ 檢查：StateService 是否暴露 property
```bash
# 找出 StateService 中所有 @property 裝飾器
grep -n "@property" doro_app/state_service.py
```

**判斷標準：**
- ✅ **無 `gif_repo` property** = 不暴露內部物件（好）
- ❌ **有 `@property def gif_repo`** = 假封裝（壞）

**實際結果：** ✅ 無 gif_repo property

---

### 3️⃣ 檢查：StateService 是否將內部物件傳給其他類
```bash
# 找出 StateService 傳遞 gif_repo 的地方
grep -n "self._gif_repo," doro_app/state_service.py
```

**判斷標準：**
- ✅ **無結果** = 沒有洩漏（好）
- ❌ **有結果** = 將內部物件傳出去，破壞封裝（壞）

**實際結果：** ⚠️ **發現問題！**
```
644:            self._gif_repo,    # 傳給 StateListWriter
```

**為什麼這是問題？**
- `StateListWriter.write()` 收到 `gif_repo` 後能直接調用它的方法
- 如果我們要替換 `gif_repo` 實作，還要改 `StateListWriter`
- 這就是「假封裝」：表面上私有，實際上到處洩漏

---

### 4️⃣ 檢查：StateService 是否訪問內部物件的屬性
```bash
# 找出訪問 gif_repo 內部屬性的程式碼（例如 .storage_dir）
grep -n "self._gif_repo\." doro_app/state_service.py | grep -v "self._gif_repo\.get\|self._gif_repo\.store\|self._gif_repo\.delete\|self._gif_repo\.sanitize"
```

**判斷標準：**
- ✅ **只調用方法** = 符合封裝（好）
- ❌ **訪問屬性** = 知道太多內部細節（壞）

**實際結果：** ⚠️ **發現問題！**
```
359:  walk_gif_path = self._gif_repo.storage_dir.parent / "ACTION" / "MOVE" / "walking.gif"
```

**為什麼這是問題？**
- 直接訪問 `.storage_dir.parent` 表示 StateService 知道 gif_repo 的目錄結構
- 如果 gif_repo 改用資料庫儲存（沒有 storage_dir），這行會爆炸
- 應該問 gif_repo「給我 walking.gif 的預設路徑」，而不是自己拼路徑

---

### 5️⃣ 檢查：外部是否使用封裝方法
```bash
# 找出外部使用封裝方法的地方
grep -rn "service\.get_gif_path\|service\.store_gif\|service\.delete_gif" doro_app/ --include="*.py" | grep -v "def "
```

**判斷標準：**
- ✅ **有很多結果** = 外部都透過封裝 API（好）
- ❌ **無結果** = 外部不知道怎麼用（壞）

**實際結果：** ✅ 12 處使用封裝方法

---

### 6️⃣ 檢查：方法鏈（Law of Demeter）
```bash
# 找出兩個點以上的調用（違反 Law of Demeter）
grep -rn "\\..*\\..*(" doro_app/ --include="*.py" | grep -v "self\._" | grep -v "#" | head -20
```

**判斷標準：**
- ✅ **最多 1 個點** = 符合 Law of Demeter（好）
  ```python
  service.get_gif_path(id)  # ✅ 1 個點
  ```
- ❌ **2 個點以上** = 違反（壞）
  ```python
  service.gif_repo.get_path(id)  # ❌ 2 個點
  ```

**實際結果：** ✅ 外部無方法鏈

---

## 📊 總結：當前封裝狀態

| 檢查項目 | 狀態 | 說明 |
|---------|------|------|
| 1. 外部直接訪問 | ✅ 通過 | 外部無法直接訪問 .gif_repo |
| 2. Property 暴露 | ✅ 通過 | 無 gif_repo property |
| 3. 傳遞給其他類 | ❌ **未通過** | line 644: 傳給 StateListWriter |
| 4. 訪問內部屬性 | ❌ **未通過** | line 359: 訪問 .storage_dir.parent |
| 5. 使用封裝方法 | ✅ 通過 | 12 處使用 |
| 6. Law of Demeter | ✅ 通過 | 無方法鏈 |

**封裝完整度：66%（4/6）**

---

## 🔧 需要修復的問題

### 問題 1：state_service.py:644
```python
# ❌ 現在：傳遞內部物件
def write_state_list(self) -> str:
    return self._state_list_writer.write(
        self._states._items,
        self._move_states._items,
        self._gif_repo,  # ← 洩漏！
        self._move_states._movement_only_keys,
    )
```

**修復方案：** StateService 應該自己調用 gif_repo，然後傳結果給 StateListWriter
```python
# ✅ 修復：只傳資料，不傳物件
def write_state_list(self) -> str:
    # StateService 負責獲取 GIF 資訊
    gif_paths = {
        key: self._gif_repo.get_path(state.gif_id) if state.gif_id else None
        for key, state in self._states._items.items()
    }

    return self._state_list_writer.write(
        self._states._items,
        self._move_states._items,
        gif_paths,  # 傳資料，不是物件
        self._move_states._movement_only_keys,
    )
```

### 問題 2：state_service.py:359
```python
# ❌ 現在：訪問內部屬性
walk_gif_path = self._gif_repo.storage_dir.parent / "ACTION" / "MOVE" / "walking.gif"
```

**修復方案：** 讓 gif_repo 提供這個路徑
```python
# 在 GifRepository 添加方法：
def get_default_walking_gif_path(self) -> Path:
    return self.storage_dir.parent / "ACTION" / "MOVE" / "walking.gif"

# StateService 調用方法：
walk_gif_path = self._gif_repo.get_default_walking_gif_path()
```

---

## 🎓 記住這個原則

**「如果我要把 gif_repo 從檔案系統改成資料庫，需要改幾個檔案？」**

- **真封裝：** 只改 1 個檔案（GifRepository 內部）
- **假封裝：** 要改 N 個檔案（StateService、StateListWriter、Window...）

當前狀態：還需要改 2 個地方（StateListWriter、_ensure_walking_state），所以還不是真封裝。

---

## 🚀 下次檢查時執行

```bash
# 一鍵完整檢查
echo "=== 1. 外部直接訪問 ===" && \
grep -rn "\.gif_repo\." doro_app/ --include="*.py" | grep -v "self\._gif_repo\." | grep -v "^doro_app/state_service.py:" | grep -v "^doro_app/state_repository.py:" && \
echo "" && \
echo "=== 2. 暴露 property ===" && \
grep -n "def gif_repo" doro_app/state_service.py && \
echo "" && \
echo "=== 3. 傳遞給其他類 ===" && \
grep -n "self._gif_repo," doro_app/state_service.py && \
echo "" && \
echo "=== 4. 訪問內部屬性 ===" && \
grep -n "self._gif_repo\." doro_app/state_service.py | grep -v "self._gif_repo\.\(get\|store\|delete\|sanitize\)" && \
echo "" && \
echo "✅ 如果以上都無結果 = 封裝完整"
```
