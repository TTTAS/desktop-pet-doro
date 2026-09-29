"""網頁操作（第 3 層）的「動作指令」+ 安全分級。

模型看完目前頁面後，回一個 :class:`WebStep`（工具決策，ADR 0005，由共用層驗證），
轉成 :class:`WebAction` 執行，再把新頁面回報給模型，一步一步做。

``WebAction.raw`` 與 :func:`parse_web_action` 仍用下列文字寫法，供歷史紀錄、
除錯與測試建構動作（一次一個）：
- ``[web:goto;url=網址]``      打開網址
- ``[web:click;n=編號]``       點畫面上第 n 個可點元件（編號來自 snapshot）
- ``[web:type;n=編號;text=文字]`` 在第 n 個輸入框打字
- ``[web:press;key=Enter]``    按某個鍵（Enter/Tab/Escape…）
- ``[web:scroll;dir=down|up]`` 捲動
- ``[web:back]``               上一頁
- ``[web:done]``               做完了，接著正式回答使用者

**安全分級**（對應 grilling 決定 Q9＝甲）：只有「不可逆／送出類」動作需要先問使用
者才做。這裡用保守的關鍵字判斷——寧可多問，不可亂送出。判斷不了的一律當成要問。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..llm.zh import to_traditional

# 「送出類 / 不可逆」關鍵字：點到名稱含這些字的按鈕，或按 Enter，都要先問使用者。
COMMIT_KEYWORDS = (
    "送出",
    "提交",
    "購買",
    "下單",
    "付款",
    "結帳",
    "刪除",
    "移除",
    "清空",
    "登入",
    "登出",
    "註冊",
    "發布",
    "發佈",
    "發表",
    "發送",
    "傳送",
    "確認",
    "同意",
    "接受",
    "訂閱",
    "儲存",
    "保存",
    "轉帳",
    "匯款",
    "捐款",
    "submit",
    "buy",
    "pay",
    "checkout",
    "order",
    "delete",
    "remove",
    "sign in",
    "log in",
    "login",
    "sign up",
    "signup",
    "register",
    "post",
    "send",
    "confirm",
    "agree",
    "accept",
    "subscribe",
    "save",
)

_KV_PATTERN = re.compile(r"([a-zA-Z_]+)\s*=\s*(.*?)(?:;|$)")
# 抓一整條 [web:...]。用非貪婪，容忍中間有分號與等號。
_WEB_ACTION_PATTERN = re.compile(r"\[\s*web\s*[:：]\s*([^\]]+)\]", re.IGNORECASE)

VALID_VERBS = {"goto", "click", "type", "press", "scroll", "back", "done"}


@dataclass(frozen=True)
class WebAction:
    """一個解析好的網頁操作指令。

    Attributes:
        verb: goto / click / type / press / scroll / back / done。
        params: 參數字典（url / n / text / key / dir…）。原始字串，未轉型。
        raw: 原始標記文字（記錄用）。
    """

    verb: str
    params: dict[str, str] = field(default_factory=dict)
    raw: str = ""

    def index(self) -> int | None:
        """把 ``n`` 參數轉成整數；沒有或不合法回 ``None``。"""
        n = self.params.get("n")
        if n is None:
            return None
        try:
            return int(str(n).strip())
        except ValueError:
            return None


# 每種動作必填的參數。
_REQUIRED_PARAMS = {
    "goto": ("url",),
    "click": ("n",),
    "type": ("n", "text"),
    "press": ("key",),
    "scroll": ("dir",),
}


class WebStep(BaseModel):
    """工具決策：網站操作的下一步（ADR 0005）。

    與角色回覆相反，這裡**不容錯**：缺參數、網址不是 http(s) 就整個不合格，
    交給共用層附錯誤重問；仍不合格就停止操作，絕不猜著執行。
    """

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    action: Literal["goto", "click", "type", "press", "scroll", "back", "done"] = Field(
        description=(
            "下一步：goto 開網址、click 點元件、type 在輸入框打字、press 按鍵、"
            "scroll 捲動、back 上一頁、done 目標已達成或卡住而收尾"
        )
    )
    url: str | None = Field(default=None, description="goto 要開的完整網址（http 或 https）")
    n: int | None = Field(default=None, description="click／type 的元件編號，只能用頁面列出的")
    text: str | None = Field(default=None, description="type 要輸入的文字")
    key: str | None = Field(default=None, description="press 的按鍵，例如 Enter、Tab、Escape")
    dir: Literal["up", "down"] | None = Field(default=None, description="scroll 的方向")
    line: str = Field(
        default="",
        description="doro 對使用者說的一句話（繁體中文）；done 時必填，老實說結果或卡在哪",
    )

    @field_validator("line", mode="after")
    @classmethod
    def _traditional_line(cls, value: str) -> str:
        return to_traditional(value.strip())

    @model_validator(mode="after")
    def _params_match_action(self):
        missing = [
            name
            for name in _REQUIRED_PARAMS.get(self.action, ())
            if getattr(self, name) in (None, "")
        ]
        if missing:
            raise ValueError(f"{self.action} 需要 {'、'.join(missing)}")
        if self.action == "goto" and not self.url.strip().lower().startswith(
            ("http://", "https://")
        ):
            raise ValueError("goto 的 url 必須是 http 或 https 開頭的完整網址")
        if self.action == "done" and not self.line:
            raise ValueError("done 時 line 必須說明結果")
        return self

    def to_action(self) -> WebAction:
        """轉成既有的 :class:`WebAction`，沿用安全分級與執行路徑。"""
        params = {
            name: str(getattr(self, name)).strip()
            for name in ("url", "n", "text", "key", "dir")
            if getattr(self, name) is not None
        }
        raw = "[web:" + ";".join([self.action, *(f"{k}={v}" for k, v in params.items())]) + "]"
        return WebAction(verb=self.action, params=params, raw=raw)


def parse_web_action(text: str) -> WebAction | None:
    """從 AI 回覆抓第一個 ``[web:...]`` 指令，解析成 :class:`WebAction`。

    無法辨識的動詞回 ``None``（呼叫端就不會亂執行）。
    """
    if not text:
        return None
    match = _WEB_ACTION_PATTERN.search(text)
    if not match:
        return None
    body = match.group(1).strip()

    # 第一段（到第一個 ; 為止、且不含 =）通常是動詞，例如 "click;n=3" -> "click"。
    verb_part = body.split(";", 1)[0].strip()
    verb = verb_part.split("=", 1)[0].strip().lower()
    if verb not in VALID_VERBS:
        return None

    params: dict[str, str] = {}
    for key, value in _KV_PATTERN.findall(body):
        params[key.lower()] = value.strip()

    return WebAction(verb=verb, params=params, raw=match.group(0))


def _looks_like_commit(name: str) -> bool:
    low = (name or "").strip().lower()
    if not low:
        return False
    return any(kw in low for kw in COMMIT_KEYWORDS)


# 「敏感頁」特徵：在這種頁面上，連按 Enter 都要先問（可能真的送出訂單/付款/登入）。
# 一般頁（搜尋、逛網頁）按 Enter 只是搜尋/換頁，無害又可逆，就不用問。
_SENSITIVE_PAGE_MARKERS = (
    "checkout",
    "payment",
    "/pay",
    "cart",
    "order",
    "billing",
    "purchase",
    "login",
    "signin",
    "sign-in",
    "logon",
    "結帳",
    "付款",
    "購物車",
    "下單",
    "訂單",
    "登入",
    "信用卡",
    "刷卡",
    "帳單",
    "轉帳",
    "匯款",
)


def needs_confirmation(
    action: WebAction,
    element_names: dict[int, str] | None = None,
    page_context: str = "",
    elements: list[dict] | None = None,
) -> bool:
    """這個動作是不是「送出類／不可逆」、執行前必須先問使用者？

    Args:
        action: 要執行的動作。
        element_names: snapshot 的「編號→元件名稱」對照（判斷點擊用）。
        page_context: 目前頁面的網址＋標題（判斷是不是結帳/付款/登入等敏感頁）。

    規則：
    - ``press``：已聚焦搜尋框且非敏感頁的普通 Enter 免問；複合／未知鍵需問。
      Tab、Escape、方向與頁面導覽鍵免問。
    - ``click``：送出關鍵字、表單提交、空名稱或未知編號都要問。
    - ``goto`` / ``scroll`` / ``back`` / ``type`` / ``done``：不用問。
    """
    verb = action.verb
    if verb == "press":
        key = action.params.get("key", "").strip().lower()
        if key in {
            "tab",
            "shift+tab",
            "escape",
            "arrowup",
            "arrowdown",
            "arrowleft",
            "arrowright",
            "pageup",
            "pagedown",
            "home",
            "end",
        }:
            return False
        # Only a plain Enter in an explicitly focused search input is known
        # to be a search. URL/title guesses cannot distinguish chat/form submit.
        ctx = (page_context or "").lower()
        focused = next((el for el in (elements or []) if el.get("focused")), {})
        return not (
            key == "enter"
            and focused.get("input_type") == "search"
            and not any(m in ctx for m in _SENSITIVE_PAGE_MARKERS)
        )
    if verb == "click":
        idx = action.index()
        if idx is None:
            return True  # 連要點哪個都說不清，保守起見先問
        name = (element_names or {}).get(idx)
        if not name or not name.strip():
            return True  # 編號對不上目前畫面 → 先問
        element = next((el for el in (elements or []) if el.get("idx") == idx), {})
        if element.get("is_submit"):
            return True
        return _looks_like_commit(name)
    return False
