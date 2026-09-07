# VERIFY 查證管線重構計畫（verify-refactor-plan）

> 狀態：**階段 1 已核准（帶條件）** ｜ 日期：2026-09-06（已納入對 `TTTAS/doro-exp-` 現況的審核回饋）
> 範圍：`doro_app/core/web/verify.py`、`runtime.py`（`_do_verify`）、`config` schema、設定對話框、`tests/core/web/test_verify.py`
> 決策已定：搜尋改走 **Tavily API**（主）＋ **ddgs** 免 key 備援；**保留 Playwright reader** 當補讀後援。

---

## 0. 核准條件（施工前必讀，違反即驗收失敗）

1. **別在搜尋階段啟動 Playwright**：現在 `run()` 一進來就 `ensure_open()`、`WebRuntime._do_verify` 會先
   `_get_session()`。必須把「開瀏覽器」延後到「真的要補讀」才做，否則「有 key 時全程不開瀏覽器」過不了。
2. **Tavily 的 `content` 是 snippet，不是全文**：預設是依 `search_depth` 生的短摘要。階段 1 拿它當初判/夠用就直接答；
   要接近全文得另開 `raw_content`（更大更慢更貴）。不可在計畫裡把預設 `content` 當「已抽好主文」。
3. **Tavily key 是新欄位**：走同一套 `ConfigManager` / 設定對話框，但**不得複用聊天的 `ChatSettings.api_key`**（那是 LLM 端點金鑰）。
4. **範圍不含操作層**：`WebOperator` 仍會叫模型自己 `goto bing.com/search`，本次不動它。改完**不代表**整個 Doro 不再爬 Bing。

---

## 1. 背景與根源

現行 `VerifyPipeline` 流程骨架正確（`搜尋 → 讀多源 → 比對 → 誠實回報`），但**搜尋這一環是用瀏覽器爬 Bing 的 HTML 結果頁**
（`build_search_url` → `session.collect_links` → `resolve_redirect` 拆 `ck/a?u=a1<base64>` → `pick_result_links`），
是在維護一個會自己腐爛的爬蟲：Bing 改版型/改轉址就無聲壞掉，跳 CAPTCHA 就 `looks_like_captcha` 放棄。
`collect_links` 還只收「看得見、文字 ≥ 4 字」的 `<a>`，結果被 JS 藏起來就空。

**根源結論：把「爬給人看的網頁」換成「呼叫給程式用的搜尋 API」。**

## 2. 現況診斷（依影響排序）

1. 🔴 **搜尋靠爬 SERP HTML**：最脆，Bing 一動就壞。
2. 🔴 **內容抽取＝整頁純文字砍前段**：見 §3「已確認事實」——`snapshot().text` 是 `inner_text("body")`，
   查證再砍 `_PER_SOURCE_CHARS = 2000`，頁首選單/cookie 橫幅佔配額。診斷成立。
3. 🟠 **選來源無品質觀念**：每網域第一個湊 3 個，SEO 農場可能贏權威站。
4. 🟠 **全程序列、阻塞、慢**：桌寵體感差。
5. 🟡 **只搜原句、單發**：不拆關鍵字、不多查、不換句重試。
6. 🟡 **卡關就整個放棄**：無備援搜尋、無重試。
7. 🟡 **來源不透明**：泡泡看不到也點不到實際來源。
8. 🟡 **注入面**：整頁文字直接進 LLM，可污染答案可信度（此路未掛 a11y，炸不到桌面）。

## 3. 已確認事實（原「待確認 3 題」，已對程式解掉）

**① `session.snapshot().text` ＝ 全頁可見純文字，非主內容。**
`WebSession.snapshot()`：`page.inner_text("body")` → `_collapse_whitespace` → 依 `_max_chars`（預設沿用
`reader.DEFAULT_MAX_CHARS = 6000`）**從開頭截斷**。無 readability / trafilatura。查證路徑再砍 `_PER_SOURCE_CHARS = 2000`。
→ **階段 2 的抽取層放在 verify 自己的「來源整理」，不要改 `snapshot()`**（操作循環還需要整頁文字＋可點元件，目標不同）。

**② `resolve_redirect` 沒有被 operator 共用。**
只活在 `verify.py`＋`tests/core/web/test_verify.py`；`operator.py` 不 import、不走 `collect_links`。
→ 查證路徑可**整段刪** `build_search_url` / `resolve_redirect` / `pick_result_links`。

**③ Tavily 實際欄位（以官方 Search API 最終文件為準）。**
每個 result 大致 `title` / `url` / `content` / `score`，可選 `raw_content`。

| 你要的 | 怎麼拿 | 注意 |
|---|---|---|
| 標題＋網址＋排序 | 預設就有；`max_results` 預設 10、上限 20 | 夠挑 3~5 個 |
| `content` | 依 `search_depth` 的短 snippet（每源數段、每段數百字） | **不是全文** |
| 接近主文 | `include_raw_content` / markdown / text → `raw_content` | 更大更貴更慢 |
| 現成 LLM 答案 | `include_answer` | **不要開**：會繞過 `build_verify_prompt` 的 grounded 比對 |

## 4. 目標流程

「搜尋」與「讀取」拆開，各用對的工具：

| 步驟 | 現在（仿造） | 目標 |
|---|---|---|
| ① 搜尋 | 爬 Bing HTML、拆轉址 | **搜尋 API**：回「標題＋網址＋摘要＋排序」，刪 `resolve_redirect`/`pick_result_links` |
| ② 選來源 | 每網域第一個湊 3 個 | 依 Tavily `score` ＋ 沿用 `_SKIP_DOMAINS` ＋ 每網域一個 ＋ 取前 3~5（信任表→階段 3） |
| ③ 讀內容 | 整頁砍前段 | 優先用 API 的 snippet；**不足才補讀**，補讀走主內容抽取＋依問題選段（階段 2，放 verify 側） |
| ④ 讀取方式 | 逐一開瀏覽器 | 夠用免開瀏覽器；只有不足/JS 重/未收錄才落到 Playwright reader |
| ⑤ 比對 | 3 頁塞進 LLM | 維持 grounded＋標一致/衝突＋不足就老實說（`build_verify_prompt` **不動**） |
| ⑥ 回報 | 只有泡泡 | 泡泡結論（~150 字）＋可點來源清單（階段 3，需改 signal 形狀） |

## 5. 介面設計（沿用注入式、維持可測）

`VerifyPipeline` 已注入 `session / ask_llm / emit`，再塞一個 `SearchProvider` 縫即可，`run()` 骨架大改動只在「取得來源」段。

```
# 概念草圖（非最終簽名）
class SearchResult(Protocol):
    url: str; title: str; snippet: str
    content: str | None      # 夠用就用；None/不足 → 補讀

class SearchProvider(Protocol):
    def search(self, query: str, max_results: int) -> list[SearchResult]: ...

class TavilyProvider: ...     # 主：Tavily，回排序結果＋snippet
class DdgsProvider:   ...     # 備援：免 key，只有 title/url/snippet，content=None → 一律補讀
class FakeSearchProvider: ... # 測試替身（比照現有 fakes）
```

- **Provider factory**：有 Tavily key → `TavilyProvider`，否則 `DdgsProvider`；由 **runtime / orchestrator** 組裝後注入。
  **`VerifyPipeline` 本身不讀 `ConfigManager`**（維持純邏輯好測）。

## 6. 開瀏覽器的時機（階段 1 驗收關鍵）

現況（eager）：
```text
VerifyPipeline.run → session.ensure_open() → goto Bing → …
WebRuntime._do_verify → _get_session() → VerifyPipeline(...)
```
目標（lazy）：
1. `search_provider.search(...)`（純 HTTP，不碰 Playwright）
2. `content` / snippet 夠用 → 直接組 `build_verify_prompt`
3. **只有不足 / `None` 才** `ensure_open` + `goto` + `snapshot`（保留 `looks_like_captcha/login_wall` skip）
4. `WebRuntime._do_verify` **不要在 API-only 路徑預先建 session**

查證仍佔同一條 `doro-web` 執行緒；API-only 排隊沒關係，但**不要為了搜尋去暖機瀏覽器**，免得卡住讀頁/操作。

## 7. Tavily 使用建議（階段 1）

- `search_depth=basic`、`max_results=5~8`；`content` 當 snippet / 初判。
- `raw_content` **不預設開**（或只對選中的 3 個再開，看額度）。
- `include_answer` **不開**。
- **設 `language` / `country` 偏台灣繁中**，否則排序偏英文站。
- `ddgs`：通常只有 title/url/snippet，`content=None` → 一律補讀。

## 8. 設定與依賴

- `pyproject.toml`：`tavily-python` + `ddgs` 併入 `web` extra 或另開 `verify` extra；
  **沒裝時給安裝指引、不崩**（比照 `reader.py` 延遲 import Playwright 的套路）。
- 金鑰：`config` schema + 設定對話框新增「Tavily API key」欄位；空 → `DdgsProvider`。**不寫進聊天的 `api_key`。**

## 9. 分階段落地

- **階段 1（本次核准）｜換搜尋 + lazy open**
  - 加 `SearchProvider` 縫 ＋ `TavilyProvider` ＋ `DdgsProvider` ＋ factory（runtime/orchestrator 注入）。
  - 查證路徑刪 `build_search_url` / `resolve_redirect` / `pick_result_links` 及對 `collect_links` 的依賴。
  - `run()` 改 lazy open（§6）；`WebRuntime._do_verify` 不預建 session。
  - 選來源：Tavily `score` ＋ `_SKIP_DOMAINS` ＋ 每網域一個 ＋ 前 3~5。
  - 設定欄位 + extra + 延遲 import。
  - 測試改寫（§10）。
  - 極小注入防護（可選）：對來源文字剝「忽略以上指令」一類行即可，完整工程留階段 3。
- **階段 2｜內容品質**：優先用 snippet；不足才補讀，補讀走主內容抽取（放 verify 側）＋依問題選段，取代 `[:2000]`。
- **階段 3｜體感/信任/UI**：來源清單可見可點（改 `emit_final` / `verify_finished` signal 形狀，附 `sources`）、
  換關鍵字/切備援重試、網域信任表、完整來源消毒。

## 10. 測試（`tests/core/web/test_verify.py` 會整檔改寫）

- 現有 `TestHelpers` 全在測 Bing URL / 轉址 / 挑連結 → 移除。
- 新增：`FakeSearchProvider` 回固定結果、content 足夠**不 goto**、content 不足才 **fallback 補讀**、Tavily 空 → 「找不到」文案。
- **保留**：happy path、空 query、全被擋文案；全程假物件、零網路。

## 11. 階段 1 驗收標準

- **有 Tavily key**：一次查證過程 **0 次** `session.goto` / `ensure_open`；答案仍走現行 `build_verify_prompt`。
- **沒 key**：走 ddgs → 才開瀏覽器補讀（速度與現在相近，但搜尋更穩，Bing 改版不影響搜尋）。
  → 明確寫入驗收，避免被理解成「沒 key 也秒回」。
- `operator` 與 `collect_links` 行為不變。
- `tests/core/web/test_verify.py` 全假物件、零網路、文案分支全綠。

## 12. 決策紀錄

- 搜尋來源：Tavily（主，需 key＋連外，`content`=snippet）；ddgs（備援，免 key，一律補讀）。
- 瀏覽器讀頁：保留為「不足/JS 重/未收錄/無 key」時的補讀後援。
- 未採用：Brave（要 key 但內容仍需自讀）；`include_answer`（繞過比對）；繼續爬 SERP（根源）。
- 明確不在本次範圍：`WebOperator` 的 Bing 搜尋、來源 UI（階段 3）、完整注入消毒（階段 3）。
