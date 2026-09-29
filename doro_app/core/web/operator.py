"""網頁操作的「大腦循環」（第 3 層核心）。

一句話：**你給目標 → 看目前頁面 → 問 AI 下一步 → （送出類先問你）→ 執行 → 再看
→ 直到完成。**

為了好測、也為了不把「瀏覽器 / AI / 你的確認」三種非同步東西攪在一起，這個循環把
它們都用**注入**的方式接進來（跟專案裡 fakes.py 的風格一致）：

- ``session``：一個像 :class:`~doro_app.core.web.session.WebSession` 的物件
  （``ensure_open`` / ``snapshot`` / ``execute``）。
- ``ask_step(prompt) -> WebStep | None``：把提示丟給模型、拿回驗證過的下一步
  （工具決策，ADR 0005）；模型回不出合格格式就是 ``None``，循環會停手。
- ``confirm(desc) -> bool``：送出類動作前問使用者、等他回覆（正式接線時會橋接到聊天
  「打字回覆好/不要」；測試時是假的）。
- ``emit(text)``：把進度／最終結果顯示出來（正式接線時是泡泡框）。

這樣 ``WebOperator.run(goal)`` 就是一段可以用假物件完整測試的純邏輯。實際的執行緒、
把 ``confirm`` 橋接到聊天、把 ``emit`` 接到泡泡框，都在薄薄的接線層做。
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Protocol

from ...utils.logger import get_logger
from .session import PageView
from .web_actions import WebAction, WebStep, needs_confirmation

logger = get_logger(__name__)

# 設 DORO_WEB_DEBUG=1 就把每一步的決策印到終端機（跟 LLM 回傳一起看）。
_DEBUG = os.environ.get("DORO_WEB_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")


def _dbg(msg: str) -> None:
    if _DEBUG:
        print(f"[doro web-op] {msg}", flush=True)


# 一次操作任務最多做幾步，避免模型鬼打牆一直點。
DEFAULT_MAX_STEPS = 12
# 偵測到打轉後，最多「提醒模型換做法」幾次才放棄（先自己想辦法脫困）。
_MAX_NUDGES = 2
# 提示詞裡最多列幾個可互動元件、每個名稱多長、整頁文字多少、留幾步歷史——
# 都是為了壓低每一步送給模型的 token（尤其 Bing 圖片網址超長）。
_MAX_ELEMENTS_IN_PROMPT = 30
_MAX_ELEMENT_NAME = 50
_MAX_PAGE_TEXT = 800
_MAX_HISTORY = 6
_MAX_URL_LEN = 120


def _short_url(url: str) -> str:
    """把超長網址縮短（Bing 圖片網址常常 700+ 字），省 token。"""
    u = (url or "").strip()
    return u if len(u) <= _MAX_URL_LEN else u[:_MAX_URL_LEN] + "…"


# 人機驗證（CAPTCHA）/ 機器人偵測 的特徵字。碰到這些 doro 要停手交給人——
# 安全底線：doro 不解驗證碼、不繞過機器人偵測。
_CAPTCHA_MARKERS = (
    "recaptcha",
    "captcha",
    "hcaptcha",
    "/sorry/",
    "unusual traffic",
    "not a robot",
    "are you human",
    "verify you are human",
    "verifying you are human",
    "cf-challenge",
    "just a moment",
    "attention required",
    "我不是機器人",
    "異常流量",
    "人機驗證",
    "驗證你是真人",
    "請完成驗證",
    "安全驗證",
)


# 「被網站擋下來 / 需要登入」的特徵：像蝦皮 verify/traffic、強制登入頁、拒絕存取。
# 這類頁面代表「任務沒成功、doro 自己過不去」，要停手誠實回報，別謊報成功。
_BLOCK_MARKERS = (
    "verify/traffic",
    "/verify/",
    "/sorry/",
    "尚未登入",
    "登入以繼續",
    "請先登入",
    "please log in",
    "please sign in",
    "sign in to continue",
    "log in to continue",
    "access denied",
    "forbidden",
    "403 forbidden",
    "拒絕存取",
    "沒有權限",
    "無法存取",
)


def _haystack(view: PageView) -> str:
    return " ".join(
        [
            (view.url or ""),
            (view.title or ""),
            (view.text or "")[:600],
        ]
    ).lower()


def looks_like_captcha(view: PageView) -> bool:
    """目前頁面看起來是人機驗證 / 機器人偵測嗎？（保守偵測）"""
    return any(m in _haystack(view) for m in _CAPTCHA_MARKERS)


def looks_like_login_wall(view: PageView) -> bool:
    """目前頁面看起來是「被擋／強制登入」牆嗎？（代表任務沒成功、過不去）"""
    return any(m in _haystack(view) for m in _BLOCK_MARKERS)


def _norm_url(url: str) -> str:
    """網址正規化（去尾巴斜線/空白），用來比對「是不是同一頁」。"""
    return (url or "").strip().rstrip("/")


def _action_signature(action: WebAction) -> tuple:
    """動作的指紋，用來偵測「一直重複同一動作」的打轉。"""
    if action.verb == "goto":
        return ("goto", _norm_url(action.params.get("url", "")))
    if action.verb in ("click", "type"):
        return (action.verb, action.index(), action.params.get("text", ""))
    if action.verb == "press":
        return ("press", action.params.get("key", "").lower())
    if action.verb == "scroll":
        return ("scroll", action.params.get("dir", "down"))
    return (action.verb,)


class SessionLike(Protocol):
    """``WebOperator`` 需要 session 提供的最小介面。"""

    def ensure_open(self) -> str | None: ...
    def snapshot(self) -> PageView: ...
    def execute(self, action: WebAction) -> str | None: ...


AskStep = Callable[[str], WebStep | None]
Confirm = Callable[[str], bool]
Emit = Callable[[str], None]


def describe_action(action: WebAction, element_names: dict[int, str]) -> str:
    """把一個要「先問你」的動作，講成一句人看得懂的話。"""
    if action.verb == "press" and action.params.get("key", "").lower() == "enter":
        return "按下 Enter（可能會送出表單或搜尋）"
    if action.verb == "click":
        idx = action.index()
        name = element_names.get(idx, "") if idx is not None else ""
        target = f"「{name}」" if name else f"第 {idx} 個元件"
        return f"點擊 {target}"
    return f"執行 {action.verb}"


def build_operate_prompt(
    goal: str,
    view: PageView,
    history: list[str],
    *,
    step: int,
    max_steps: int,
    warning: str = "",
) -> str:
    """組出「請 AI 決定下一步」的提示。``warning`` 是偵測到打轉時要模型換做法的提醒。"""
    lines: list[str] = []
    lines.append("你正在操作一個瀏覽器幫使用者達成目標。以下是目前的頁面狀況。")
    if warning:
        lines.append("")
        lines.append(f"⚠️ {warning}")
        lines.append("")
    lines.append(f"使用者的目標：{goal}")
    lines.append(f"目前網址：{_short_url(view.url) or '(空白頁)'}")
    if view.title:
        lines.append(f"頁面標題：{view.title[:80]}")

    if view.elements:
        lines.append("")
        lines.append("頁面上可操作的元件（用編號指定）：")
        for el in view.elements[:_MAX_ELEMENTS_IN_PROMPT]:
            name = (str(el.get("name", "")).strip() or "(無文字)")[:_MAX_ELEMENT_NAME]
            lines.append(f"  [{el.get('idx')}] {el.get('tag')}：{name}")
        if len(view.elements) > _MAX_ELEMENTS_IN_PROMPT:
            lines.append(f"  …（還有 {len(view.elements) - _MAX_ELEMENTS_IN_PROMPT} 個沒列出）")

    if view.text:
        lines.append("")
        lines.append("頁面文字（節錄）：")
        lines.append(view.text[:_MAX_PAGE_TEXT])

    if history:
        lines.append("")
        lines.append("到目前為止做過的步驟（最近幾步）：")
        for h in history[-_MAX_HISTORY:]:
            lines.append(f"  - {h}")

    lines.append("")
    lines.append(f"這是第 {step + 1} / {max_steps} 步。請只決定「一個」下一步 action。")
    lines.append("")
    lines.append("重要：")
    lines.append("- 你【一定】要給一個 action 來推進，除非真的完成了才用 done。")
    lines.append("- 如果現在是空白頁 / 還沒開始，第一步幾乎一定是 goto 打開要用的網站。")
    lines.append("- 要用搜尋引擎，就直接開搜尋結果頁。優先用 Bing（比較不會跳人機驗證）：")
    lines.append(
        "  goto https://www.bing.com/search?q=關鍵字（關鍵字換成要搜尋的內容，空白用 + 連接）"
    )
    lines.append(
        "- 在搜尋結果頁只點『真正的外部網站結果連結』（通常是標題連結）；不要點圖片結果、相關搜尋、篩選或廣告，"
        "也不要點會停在 bing.com 自己頁面的東西（例如圖片檢視），那會卡住。"
    )
    lines.append("- 一次只給一個動作；line 用純文字不要 Markdown；編號只能用上面列出的。")
    lines.append(
        "- 【誠實很重要】用 done 收尾前，先確認頁面上『真的』出現了目標結果"
        "（例如真的看到搜尋結果清單、真的完成了那件事）。如果現在是登入頁、驗證頁、"
        "錯誤頁、或根本沒看到預期結果，就【不要謊稱成功】——在 line 老實說卡在哪"
        "（例如「被要求登入」「沒找到結果」），再 done。"
    )
    return "\n".join(lines)


class WebOperator:
    """跑「看→想→（問）→做」的操作循環。"""

    def __init__(
        self,
        session: SessionLike,
        ask_step: AskStep,
        confirm: Confirm,
        emit: Emit,
        *,
        max_steps: int = DEFAULT_MAX_STEPS,
        should_cancel: Callable[[], bool] | None = None,
        emit_reply: Emit | None = None,
    ) -> None:
        self._session = session
        self._ask_step = ask_step
        self._confirm = confirm
        self._emit = emit
        self._max_steps = max(1, int(max_steps))
        # 使用者打「停/取消」時會讓這個回 True；每步之間檢查，讓中止最慢下一步生效。
        self._should_cancel = should_cancel or (lambda: False)
        self._emit_reply = emit_reply

    def run(self, goal: str) -> None:
        """對 *goal* 跑完整個操作循環（阻塞，需在專屬背景執行緒呼叫）。"""
        goal = (goal or "").strip()
        if not goal:
            self._emit("人要doro做什麼呀？再說清楚一點嘛～")
            return

        err = self._session.ensure_open()
        if err:
            self._emit(err)
            return

        logger.info(f"開始網頁操作任務：{goal}")
        history: list[str] = []
        prev_sig: tuple | None = None
        nudge_count = 0  # 偵測到打轉後、已經提醒模型換做法幾次
        warning = ""  # 下一輪要塞給模型的「你在重複、換做法」提醒

        for step in range(self._max_steps):
            if self._should_cancel():
                self._emit("好，doro停下來囉～")
                return

            view = self._session.snapshot()
            _dbg(f"step {step+1}/{self._max_steps} url={view.url!r} elements={len(view.elements)}")
            if not view.ok:
                self._emit(view.error or "doro看不到目前的頁面…")
                return

            # 碰到人機驗證：doro 停手，交給你本人在那個瀏覽器視窗完成（安全底線：
            # doro 不解驗證碼、不繞過機器人偵測）。完成後再重新叫 doro 一次即可。
            # 碰到人機驗證：暫停，請使用者在視窗自己過驗證（doro 不代按），完成回
            # 「好」就接著做同一個任務；回「不要」才放棄。
            if looks_like_captcha(view):
                logger.info("偵測到人機驗證，暫停等使用者處理")
                _dbg("→ 暫停：人機驗證，等使用者")
                if self._confirm(
                    "嗚嗚…這頁跳出人機驗證了～doro不能代按喔（會被當成壞壞機器人）。\n"
                    "人幫我在那個瀏覽器視窗自己把驗證過一下，完成後回我「好」，doro就接著做；不想做了就回「不要」～"
                ):
                    continue  # 使用者說弄好了 → 重新看頁面、接著做
                self._emit("好，那doro先不做囉～")
                return

            # 被網站擋下來 / 要登入（像蝦皮 verify/traffic 頁）：任務還沒成功、doro
            # 自己過不去。暫停等使用者登入，完成回「好」就續做。
            if looks_like_login_wall(view):
                logger.info(f"偵測到被擋/登入牆，暫停等使用者：{view.url}")
                _dbg("→ 暫停：被擋/需要登入，等使用者")
                if self._confirm(
                    "唔…這個網站要登入才能繼續（這不是搜尋結果喔，doro還沒成功）。\n"
                    "人在那個瀏覽器視窗裡登入一下，完成後回我「好」，doro就接著幫你；不想做了就回「不要」～"
                ):
                    continue
                self._emit("好，那doro先不做囉～")
                return

            prompt = build_operate_prompt(
                goal, view, history, step=step, max_steps=self._max_steps, warning=warning
            )
            decision = self._ask_step(prompt)
            if self._should_cancel():
                self._emit("好，doro停下來囉～")
                return
            if decision is None:
                # 工具決策嚴格：重問後仍不合格就停手，不猜著執行（ADR 0005）。
                _dbg("→ 停手：模型回不出合格的下一步")
                self._emit("doro這一步沒想清楚，先停下來囉～人要不要換個說法再叫我一次？")
                return
            action = decision.to_action()

            _dbg(f"decided action = {action.raw}")
            if action.verb == "done":
                _dbg("→ 收尾（done）")
                if self._emit_reply is not None:
                    self._emit_reply(decision.line)
                else:
                    self._emit(decision.line)
                return

            # 防打轉：只盯 goto / click（會「狂重開同一頁 / 狂點同一顆」的兩種）。
            # scroll、type、press、back 連續重複是正常的（例如一直往下捲），不算打轉。
            sig = _action_signature(action)
            is_repeat = False
            if action.verb in ("goto", "click"):
                same_page_goto = action.verb == "goto" and _norm_url(
                    action.params.get("url", "")
                ) == _norm_url(view.url)
                is_repeat = same_page_goto or (sig == prev_sig)

            if is_repeat:
                # 不馬上放棄：先自己想辦法脫困——回頭「提醒模型換個做法」再試。
                nudge_count += 1
                _dbg(f"→ 偵測到重複 {sig}，第 {nudge_count} 次提醒換做法")
                if nudge_count > _MAX_NUDGES:
                    logger.info(f"提醒 {_MAX_NUDGES} 次仍原地打轉（{sig}），停手")
                    _dbg("→ 停手：提醒無效、仍在打轉")
                    self._emit(
                        "doro試著換方法還是卡在同一步…先停下來囉～要不要換個說法、"
                        "直接給我網址、或分兩次做呀？"
                    )
                    return
                warning = (
                    "你剛剛重複了同一個動作、而且沒有讓進度前進。請【務必換一個不一樣的動作】："
                    "往下捲看更多（scroll down）、點畫面上『別的』元件、回上一頁（back）、"
                    "或如果其實已經完成就用 done 收尾。千萬不要再重複剛剛那個動作。"
                )
                continue  # 這個重複動作不執行，帶著提醒重來一輪

            # 有進展（非重複）→ 清掉提醒、重置計數，正常往下做。
            warning = ""
            nudge_count = 0
            prev_sig = sig if action.verb in ("goto", "click") else None

            names = view.element_names()
            page_context = f"{view.url} {view.title}"
            target = next((el for el in view.elements if el.get("idx") == action.index()), {})
            if action.verb == "type" and target.get("sensitive"):
                self._emit("密碼或驗證碼請人自己輸入，doro不代填喔。")
                return
            if needs_confirmation(action, names, page_context, view.elements):
                confirm_text = (
                    f"doro 要{describe_action(action, names)}，可以嗎？回「好」或「不要」～"
                )
                if not self._confirm(confirm_text):
                    self._emit("好，那這一步doro就不動囉～")
                    return

            if self._should_cancel():
                self._emit("好，doro停下來囉～")
                return
            exec_err = self._session.execute(action)
            # 歷史用精簡描述（goto 的原始標記含超長網址，改用短網址省 token）。
            if action.verb == "goto":
                step_note = f"開啟 {_short_url(action.params.get('url', ''))}"
            elif action.verb in ("click", "press"):
                step_note = describe_action(action, names)
            elif action.verb == "type":
                step_note = f"在第 {action.index()} 個欄位輸入（內容不記錄）"
            else:
                step_note = action.raw
            history.append(step_note + (f"（失敗：{exec_err}）" if exec_err else "（完成）"))
            if exec_err:
                # 失敗不立即中止：回報給模型，讓它下一步換做法。但同一步別無限卡。
                logger.info(f"操作步驟失敗：{exec_err}")

        self._emit("步驟有點多，doro先停下來喘口氣～人要不要換個說法，或分兩次做？")
