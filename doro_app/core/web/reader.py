"""用「真的瀏覽器」把一個網址讀成文字。

門：:class:`WebPageReader`。呼叫 ``read(url)`` 會用 Playwright 開一個**看得見
的** Chromium 視窗，打開網址、等頁面載入、把可見文字抽出來（上限約 6000 字），
再關掉。這是 grilling 決定的 Q4＝b（真瀏覽器）+ Q7＝Playwright + Q10＝專屬設定檔。

重點設計：
- **Playwright 是延遲載入**（在 ``read`` 裡才 import）。所以就算使用者還沒
  ``pip install playwright``，import 這個模組、開 doro 都不會壞——只有真的叫
  doro 讀網頁時才會回一個友善的「請先安裝」訊息。
- **這個函式會阻塞**（等瀏覽器跑完），所以**一定要在背景執行緒跑**，不要在 Qt
  主執行緒直接呼叫，否則畫面會凍住。見 ``worker.py``。
- **專屬瀏覽器設定檔**：用 ``launch_persistent_context(user_data_dir=...)``，登
  入狀態會留在那個資料夾，跟你平常的 Chrome 分開。密碼一律你本人手動輸入。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ...utils.logger import get_logger

logger = get_logger(__name__)

# 一次最多抓多少字給 AI（grilling 決定的小設定：約 6000 字）。太長會爆 context、
# 也會變慢。超過就截斷。
DEFAULT_MAX_CHARS = 6000

# 頁面載入 / 讀取的逾時（毫秒）。
DEFAULT_NAV_TIMEOUT_MS = 30_000

# 沒裝 Playwright 時，回給使用者的安裝指引（doro 口吻，繁中）。
_PLAYWRIGHT_MISSING_MSG = (
    "doro 還不會開瀏覽器啦～要先安裝「Playwright」才行。\n"
    "請在終端機依序執行這兩行：\n"
    "  pip install playwright\n"
    "  playwright install chromium\n"
    "裝好再重開 doro，我就能幫你讀網頁了！"
)


@dataclass(frozen=True)
class WebReadResult:
    """讀網頁的結果。

    成功：``error`` 為 ``None``，``text`` 是網頁內容，``title``/``url`` 有值。
    失敗：``error`` 是給使用者看的錯誤訊息，``text`` 為空字串。
    """

    url: str
    title: str
    text: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _collapse_whitespace(text: str) -> str:
    """把連續空行 / 空白收乾淨，讓內容更精簡好讀。"""
    # 每行去頭尾空白
    lines = [line.strip() for line in text.splitlines()]
    # 丟掉全空行，但保留段落感（連續多空行縮成一個）
    out: list[str] = []
    blank = False
    for line in lines:
        if line:
            out.append(line)
            blank = False
        elif not blank:
            out.append("")
            blank = True
    return "\n".join(out).strip()


class WebPageReader:
    """用 Playwright 開真瀏覽器讀網頁。

    Args:
        user_data_dir: doro 專屬瀏覽器設定檔資料夾（登入狀態留在這）。
        max_chars: 一次最多回傳幾個字。
        headless: 預設 ``False``（看得見的視窗，符合 grilling 決定 Q7）。
        nav_timeout_ms: 頁面載入逾時（毫秒）。
    """

    def __init__(
        self,
        user_data_dir: Path,
        *,
        max_chars: int = DEFAULT_MAX_CHARS,
        headless: bool = False,
        nav_timeout_ms: int = DEFAULT_NAV_TIMEOUT_MS,
    ) -> None:
        self._user_data_dir = Path(user_data_dir)
        self._max_chars = max(500, int(max_chars))
        self._headless = bool(headless)
        self._nav_timeout_ms = int(nav_timeout_ms)

    def read(self, url: str) -> WebReadResult:
        """打開 *url*、讀出文字。**會阻塞**，請在背景執行緒呼叫。"""
        url = (url or "").strip()
        if not url:
            return WebReadResult(url=url, title="", text="", error="沒有給我網址耶。")

        # 延遲載入 Playwright：沒裝也不會讓 import 這個模組壞掉。
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("Playwright 未安裝，無法讀網頁")
            return WebReadResult(
                url=url, title="", text="", error=_PLAYWRIGHT_MISSING_MSG
            )

        logger.info(f"開始讀網頁：{url}")
        try:
            self._user_data_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error(f"建立瀏覽器設定檔資料夾失敗：{exc}")
            return WebReadResult(
                url=url, title="", text="",
                error=f"doro 建不出瀏覽器資料夾：{exc}",
            )

        try:
            with sync_playwright() as pw:
                context = pw.chromium.launch_persistent_context(
                    user_data_dir=str(self._user_data_dir),
                    headless=self._headless,
                )
                try:
                    page = context.new_page()
                    page.set_default_timeout(self._nav_timeout_ms)
                    page.goto(url, wait_until="domcontentloaded",
                              timeout=self._nav_timeout_ms)
                    # 給吃 JavaScript 的頁面一點時間把內容渲染出來。
                    try:
                        page.wait_for_load_state("networkidle", timeout=5_000)
                    except Exception:
                        # networkidle 等不到很常見（一直有背景請求），不當錯誤。
                        pass
                    title = (page.title() or "").strip()
                    body_text = page.inner_text("body")
                finally:
                    context.close()
        except Exception as exc:  # Playwright 的錯誤型別很多，統一收斂成訊息
            message = self._friendly_error(url, exc)
            logger.error(f"讀網頁失敗（{url}）：{exc}")
            return WebReadResult(url=url, title="", text="", error=message)

        cleaned = _collapse_whitespace(body_text or "")
        truncated = False
        if len(cleaned) > self._max_chars:
            cleaned = cleaned[: self._max_chars]
            truncated = True

        if not cleaned:
            return WebReadResult(
                url=url, title=title, text="",
                error="這頁 doro 讀不到內容（可能需要登入、或整頁都是圖片/影片）。",
            )

        if truncated:
            cleaned += "\n\n……（內容太長，doro 只讀了前面這一段）"

        logger.info(f"讀網頁成功（{url}）：標題「{title}」，{len(cleaned)} 字")
        return WebReadResult(url=url, title=title, text=cleaned, error=None)

    @staticmethod
    def _friendly_error(url: str, exc: Exception) -> str:
        """把 Playwright 的技術錯誤翻成使用者看得懂的話。"""
        text = str(exc)
        low = text.lower()
        if "executable doesn't exist" in low or "playwright install" in low:
            return (
                "瀏覽器核心還沒裝好。請在終端機執行：\n"
                "  playwright install chromium\n"
                "裝好再重開 doro 就可以了。"
            )
        if "timeout" in low or "timed out" in low:
            return f"打開「{url}」太久沒回應（可能太慢或網址怪怪的），doro 先放棄囉。"
        if re.search(r"net::|name_not_resolved|err_", low):
            return f"連不上「{url}」，網址對嗎？或是沒網路？"
        return f"讀「{url}」的時候出錯了：{text[:200]}"
