# VERIFY 階段 1 開工清單（verify-stage1-checklist）

> 狀態：階段 1 已實作（PR #51） ｜ 日期：2026-09-07 ｜ 搭配 `docs/verify-refactor-plan.md`（設計/為什麼）
> 本檔＝「改哪些檔、門檻定多少、失敗怎麼退」的可執行清單。所有 `或`／模糊處已釘死。

## 0. 已定案
- **`search_depth` 預設 `basic`**（省額度、較快）；`advanced` 為設定可覆寫。
  驗收敘事：**「有 key 且來源夠料 → 0 goto；basic 預設下多數仍會開頁補讀」**——不追帳面上的 0 goto。
- **`SEARCH_TIMEOUT_S = 30`**（對齊 OpenClaw Tavily plugin）。

## 1. 釘死的常數（放新 module 或 `verify.py` 頂部）
```
MIN_SNIPPET_CHARS = 250   # 每來源 snippet ≥ 此字數 → 視為「有料」
MIN_GOOD_SOURCES  = 2     # 選中來源裡有料數 ≥ 此值 → 免補讀（0 goto）
TARGET_SOURCES    = 3     # 需補讀時，湊到幾個有料來源為止
MAX_RESULTS       = 6     # 跟 Tavily 要幾筆（挑來源前）
SEARCH_TIMEOUT_S  = 30    # 搜尋 API 硬逾時（對齊 OpenClaw Tavily plugin）
TAVILY_SEARCH_DEPTH = "basic"      # 見 §0；advanced 為設定可覆寫
TAVILY_COUNTRY    = "taiwan"        # 小寫國名；language/locale 查官方 enum 再決定是否加
```

## 2. 「夠用 → 免補讀」判定（解你 #1，最大的洞）
```
picked = 依 score 排序後：跳過 _SKIP_DOMAINS、每網域取一個、取前 MAX_RESULTS 挑到 3~5
good   = [s for s in picked if len((s.content or s.snippet).strip()) >= MIN_SNIPPET_CHARS]

if len(good) >= MIN_GOOD_SOURCES:
    sources = good                     # 0 goto，直接比對
else:
    sources = list(good)
    for s in picked_without_content:   # 只補讀「不夠料」的
        補讀(s)  # session_provider() → goto → snapshot → sanitize
        若補到 → sources.append；len(sources) >= TARGET_SOURCES 就停
```
字數以「字元」計（中文友善），非 bytes。

## 3. 失敗降級順序（解你 #2）
固定階梯，任何一層失敗只往下走，**永不 raise 打穿 runtime**：
1. 有 Tavily key → 試 Tavily（`SEARCH_TIMEOUT_S` 逾時）。auth 錯／quota 用盡／逾時／網路錯／回空 → 記 log，落 ddgs。
2. ddgs 搜尋（同逾時）。失敗／空 → 視為 0 來源。
3. 有結果但不夠料 → 補讀（Playwright）。**Playwright 沒裝** → 用 snippet 硬答，並在來源標注「內容可能不完整」。
4. 單來源補讀失敗／被擋 → skip（沿用現行）。
5. 最終 0 個有料來源 → 沿用現有「找不到來源／讀不到」友善文案。
實作：每個 provider 的 `search()` 內部 try/except → 失敗回 `[]`，由 `FallbackSearchProvider` 依序試。

## 4. 介面與組裝（解你 #3）
- **新檔 `doro_app/core/web/search_providers.py`**：
  - `SearchResult`（`url/title/snippet/content|None`）、`SearchProvider` Protocol
  - `TavilyProvider`、`DdgsProvider`、`FallbackSearchProvider(list[SearchProvider])`（依序試、逐層降級）
  - `build_search_provider(config) -> SearchProvider`：有 key → `Fallback([Tavily, Ddgs])`；無 key → `Ddgs` 單獨
  - `sanitize_source_text(text) -> text`（見 §5）
- **`VerifyPipeline.__init__` 簽名改**：收 `search_provider` ＋ `session_provider: Callable[[], SessionLike]`
  （**不是 live session**）。真的要補讀才呼叫 `session_provider()`，內部做 `ensure_open`。→ 結構上擋掉提前開瀏覽器。
- **`runtime.py::_do_verify`**：呼叫 `build_search_provider(config)`、把「開 session 的 callable」而非 session 傳進去；
  **API-only 成功路徑完全不建 session**。
- **pipeline 不讀 `ConfigManager`**（維持純邏輯好測）。

## 5. 注入防護（解你 #6，改硬規則、不再可選）
`sanitize_source_text`：逐行刪掉命中 denylist 的行後才進 LLM。denylist（大小寫/繁簡不敏感）：
`忽略(以上|前面|先前).{0,6}(指示|指令|要求)`、`ignore (all )?previous`、`system prompt`、`you are now`、`disregard the above`。
補讀與 API content 都要過。完整 prompt-injection 工程仍留階段 3。

## 6. 驗收標準（收斂版）
- **有 key（advanced）**：典型查證 **0 次** `goto`/`ensure_open`；測試斷言 `session_provider` **未被呼叫**；答案走現行 `build_verify_prompt`。
- **有 key 但來源不夠料**：只對「不夠料」來源補讀，湊到 `TARGET_SOURCES`。
- **無 key**：ddgs → 才開瀏覽器補讀。
- **Tavily 掛（逾時/quota/網路）**：自動落 ddgs，不 crash。
- **全空**：友善文案，無例外。
- **sanitize**：含「忽略以上指示」的來源行被剝掉（單元測試涵蓋）。
- `tests/core/web/test_verify.py` 全假物件、零網路、文案分支全綠。

## 7. 要改／不改的檔（解你 #7）
**新增**
- `doro_app/core/web/search_providers.py`

**修改**
- `doro_app/core/web/verify.py`：刪 `build_search_url`/`resolve_redirect`/`pick_result_links` 及對 `collect_links` 依賴；
  加 §2 判定、§3 降級呼叫、§5 sanitize、lazy `session_provider`。
- `doro_app/core/web/runtime.py`：`_do_verify` 組 provider、傳 callable、不預建 session。
- `doro_app/utils/config_schema.py`（＋ `config_defaults.py`）：新增 `tavily_api_key`（空字串預設）＋（可選）search_depth 覆寫。
- 設定對話框：加「Tavily API key」欄位。**先開檔確認**是掛在 `ui/dialogs/chat_settings_dialog.py`
  還是另立 verify/web 設定區；**不得複用聊天 `api_key`**。
- `pyproject.toml`：`web` extra 併入 `tavily-python`、`ddgs`（延遲 import，未裝不崩，比照 `reader.py`）。
- `tests/core/web/test_verify.py`：整檔改寫（見 §8）。

**不改**
- `operator.py`（`WebOperator` 仍走 Bing，範圍外）、`session.py::snapshot()`、`build_verify_prompt` 文案、
  `web_actions.py`、a11y 相關。

## 8. 測試改寫要點
- 移除 `TestHelpers` 對 Bing URL／轉址／挑連結的測試。
- 新增：`FakeSearchProvider`（回固定結果）＋ `FakeSessionProvider`（記錄是否被呼叫）。
  - content 夠 → 斷言 session_provider 未被呼叫、答案正常。
  - content 不足 → 斷言有補讀、湊到 `TARGET_SOURCES`。
  - Tavily 失敗 → 落 ddgs。
  - 全空 → 「找不到」文案。
  - sanitize → 惡意行被剝。
- 保留：happy path、空 query、全被擋文案。

## 9. 兩個已知但階段 1 先不解的痛（解你 #8，明列以免預期落差）
- **有 key/無 key 體感差很大**：無 key 仍開多分頁補讀，會被覺得「改了還是慢」。已寫進 §6 驗收，對外預期要顧。
- **搜尋仍排在 `doro-web` 執行緒**：純 HTTP 其實不必跟 Playwright 排隊。階段 1 先留原執行緒＋10s 硬逾時擋長堵；
  若 Tavily 實測慢，階段 1.5 再把「純搜尋」移出該執行緒。
