# 改動紀錄 - 2026-06-16

## 📋 本次 Session 完成項目

### 1. ✅ 點擊紅框 silent-skip 診斷與 stdout 升級

**症狀：**

使用者確認 Chrome 點擊在 5d6b043（area-based DFS）後真的成立，但接著問：「之前點的時候有紅框、現在沒看到，是被刪了嗎？」

**調查：**

逐檔讀過整條鏈，紅框 code 完全沒被動：

- `doro_app/ui/click_warning_overlay.py` 還在，`paintEvent` 也在畫。
- `doro_app/core/automation/manager.py:292-297` wind-up 起手依然會 `self._warning_overlay.begin(bounds)`。
- `doro_app/app.py:590-595, 786-807` 還在把 `ClickWarningOverlay` 包成 `_QtClickWarningOverlayAdapter` 給 manager。
- 最近一筆動 overlay 的 commit 是 `0be4434`（2025-05 底，revert element-id）。本 session 的 5 筆 commit（`5d6b043` / `5bc254e` / `504340f` / `8501e43` / `ac6f3bf`）通通沒碰 overlay 或 bounds_provider。

**根因：**

`bounds_provider`（`_click_target_bounds`）回 `None` 時，`_QtClickWarningOverlayAdapter.begin` 走 `logger.debug` 之後 silent return：

```python
def begin(self, bounds_physical) -> None:
    if bounds_physical is None:
        logger.debug("warning-frame begin: no a11y bounds, frame hidden")
        return
```

預設 INFO level 連 terminal 都不會印出來，使用者沒線索區分以下三種狀態：

1. begin 根本沒被呼叫
2. begin 被呼叫了但 bounds=None
3. begin 被呼叫、bounds 對，但 paint 沒上去

**`bounds=None` 三條成因：**

1. `self._a11y is None`（`A11yService` 初始化失敗）
2. `self._movement.last_target_physical is None`（沒有最近的 `[MOVE:to]` target）
3. `a11y.bounds_at_physical_point(x, y)` 在 `_last_elements` 找不到包含 (x, y) 的元素（tree 沒更新 / 抓到別的視窗 / Chrome 被 session blacklist）

**修法（純 observability，零行為改動）：**

把 `_QtClickWarningOverlayAdapter.begin / end` 跟 `_click_target_bounds` 的「為什麼沒畫」全部升成 `print(..., flush=True)`，與 `[doro click]` / `[doro move]` 風格一致：

- adapter `begin(None)` → `[doro click] warning-frame skipped: bounds=None (no a11y element at the move target — _last_elements may be stale or from a different window)`
- adapter `begin(bounds)` → `[doro click] warning-frame begin: bounds=...`
- adapter `end()` → `[doro click] warning-frame end`
- `_click_target_bounds`：a11y service 缺、沒 `[MOVE:to]` target、`_last_elements` 找不到包含點，三條原因各印一行

**修改檔案：**

- `doro_app/app.py` — `_QtClickWarningOverlayAdapter.begin/end` 與 `_click_target_bounds`

**Commit：**

- `9453759` — `debug(click): mirror warning-frame begin/end/skip reasons to stdout`

**驗證：**

2026-06-16 使用者跑 build，terminal 印出 `warning-frame begin: bounds=(...)` 與 `warning-frame end` 配對、紅框視覺上正常出現，回報「正常了」。

**Follow-up（暫不動）：**

若日後 bounds=None 真的常觸發，再決定要動 `_a11y` setup 或 `ForegroundTracker` / `_last_elements` 更新時機。目前先以 observability 為止。

---
