"""聽懂「讀網頁」指令。

設計約定（對應 grilling 決定的 Q3＝你明講才做）：doro **不會**看到網址就自
己上網。只有當使用者的訊息**同時**滿足：

1. 句子裡有一個明確的讀取動詞（讀、讀取、摘要、看這頁、read…），而且
2. 句子裡有一個 http(s) 網址，

才會被判定為「讀網頁」指令。純聊天（就算裡面剛好有網址）不會被攔截。

``parse_web_read_command`` 回傳 :class:`WebReadRequest`（含網址與使用者的問
題）或 ``None``（代表這不是讀網頁指令，讓正常聊天流程處理）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 抓第一個 http(s) 網址。結尾的標點（。，、）不算網址的一部分。
_URL_PATTERN = re.compile(r"https?://[^\s，。、）)】」』]+", re.IGNORECASE)

# 讀取意圖的關鍵詞。刻意選「和讀網頁強相關」的詞，避免把普通聊天的「看」誤判。
# 例如「你看我很棒吧」不含網址，不會被誤攔；而「幫我看這頁 <網址>」會命中。
_READ_INTENT_PATTERN = re.compile(
    r"("
    r"讀取|讀這頁|讀這個網頁|讀這個網址|讀網頁|讀一下|讀|"
    r"看這頁|看這個網頁|看這個網址|看一下這頁|"
    r"打開這頁|打開網頁|開這頁|開網頁|"
    r"摘要|幫我唸|唸這頁|"
    r"read|open"
    r")",
    re.IGNORECASE,
)


# AI 主動要求讀網頁的動作標記：``[read:https://...]``。
# 這是「讓 LLM 自己判斷要不要讀」的路：模型看完使用者訊息後，如果覺得需要看某個
# 網頁才能回答，就在回覆結尾吐這個標記，doro 讀完再把內容餵回去讓它作答。
_READ_ACTION_PATTERN = re.compile(r"\[\s*read\s*[:：]\s*(https?://[^\]\s]+)\s*\]", re.IGNORECASE)


def parse_read_action(text: str) -> str | None:
    """從 AI 回覆裡抓 ``[read:網址]`` 動作標記，回傳網址；沒有就回 ``None``。"""
    if not text:
        return None
    match = _READ_ACTION_PATTERN.search(text)
    return match.group(1) if match else None


@dataclass(frozen=True)
class WebReadRequest:
    """一次「讀網頁」請求。

    Attributes:
        url: 要讀的網址。
        question: 使用者附帶的問題／指令（可能為空字串，代表「請摘要」）。
        raw_text: 使用者原始那句話（保留給記錄用）。
    """

    url: str
    question: str
    raw_text: str


def _extract_url(text: str) -> str | None:
    match = _URL_PATTERN.search(text)
    return match.group(0) if match else None


def _extract_question(text: str, url: str) -> str:
    """把網址從句子裡拿掉，剩下的當作使用者的問題／指令。

    只是盡量清乾淨，讓 AI 讀起來順；抓不出明確問題也沒關係，回空字串即可
    （呼叫端會改用「請摘要」當預設）。
    """
    without_url = text.replace(url, " ")
    # 收掉多餘空白
    cleaned = re.sub(r"\s+", " ", without_url).strip()
    # 把開頭常見的招呼／指令語氣詞削掉，剩下真正的問題。純招呼就會變空字串。
    cleaned = re.sub(
        r"^(幫我|請|麻煩你?|doro|嘿|欸|然後)\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    return cleaned


# ── 操作（第 3 層）觸發與確認用語 ────────────────────────────────────────────

# 只認明講（grilling Q9=甲）：這些片語才會啟動「操作網頁」。
_OPERATE_INTENT_PATTERN = re.compile(
    r"("
    r"幫我操作|操作網頁|幫我在|幫我去|幫我到|幫我點|幫我按|幫我填|幫我輸入|"
    r"幫我搜尋|幫我搜|幫我查詢|幫我登入|幫我下單|幫我訂|幫我報名|幫我留言|"
    r"去.{0,12}幫我|到.{0,12}幫我"
    r")"
)

# 確認時算「好」的字（其餘一律當「不做」）。
_AFFIRM_PATTERN = re.compile(
    r"^(好|好的|好啊|好喔|可以|可以的|是|是的|對|嗯+|行|沒問題|同意|ok|okay|yes|y|go|做|去做|確認)$",
    re.IGNORECASE,
)

# 中止整個操作的字。
_STOP_PATTERN = re.compile(
    r"(停|停下|停下來|別動|不要動|中止|取消|算了|stop|cancel|abort)",
    re.IGNORECASE,
)


def parse_operate_command(text: str) -> str | None:
    """（舊）關鍵字判斷「操作網頁」；已改由 LLM 吐 [operate:] 判斷，這個保留備用。"""
    if not text:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    if _OPERATE_INTENT_PATTERN.search(stripped):
        return stripped
    return None


# AI 主動要求「操作網頁」的動作標記：``[operate: 一句話目標]``。
# 這是「讓 LLM 自己判斷」的路：模型覺得使用者要的是「在網站上辦事」時吐這個，
# doro 就開自己的瀏覽器一步步做（區別於「點桌面/工具列」用 [mouse:click]）。
_OPERATE_ACTION_PATTERN = re.compile(r"\[\s*operate\s*[:：]\s*([^\]]*)\]", re.IGNORECASE)


# 登入助手動作標記：``[login:網址]``。使用者想自己登入某站時，模型吐這個，doro
# 只把站開著停在那讓使用者本人登入（不操作），登入狀態存進專屬設定檔。
_LOGIN_ACTION_PATTERN = re.compile(r"\[\s*login\s*[:：]\s*(https?://[^\]\s]+)\s*\]", re.IGNORECASE)


def parse_login_action(text: str) -> str | None:
    """從 AI 回覆抓 ``[login:網址]``，回傳網址；沒有就回 ``None``。"""
    if not text:
        return None
    match = _LOGIN_ACTION_PATTERN.search(text)
    return match.group(1) if match else None


# 查證動作標記：``[verify: 要查證/查的問題]``。使用者想「查證、比對來源、查資料」
# 時模型吐這個，doro 會搜尋、讀幾個來源、比對後回報。
_VERIFY_ACTION_PATTERN = re.compile(r"\[\s*verify\s*[:：]\s*([^\]]*)\]", re.IGNORECASE)


def parse_verify_action(text: str) -> str | None:
    """從 AI 回覆抓 ``[verify: 問題]``，回傳問題字串（可能為空字串）。

    沒有這個標記回 ``None``（呼叫端用 ``is not None`` 判斷；空字串代表「就查使用者
    剛剛那句」）。
    """
    if not text:
        return None
    match = _VERIFY_ACTION_PATTERN.search(text)
    if not match:
        return None
    return match.group(1).strip()


def parse_operate_action(text: str) -> str | None:
    """從 AI 回覆抓 ``[operate: 目標]``，回傳目標字串（可能為空字串）。

    沒有這個標記回 ``None``。注意：呼叫端要用 ``is not None`` 判斷（空目標 ""
    也算命中，代表「就照使用者剛剛那句去操作」）。
    """
    if not text:
        return None
    match = _OPERATE_ACTION_PATTERN.search(text)
    if not match:
        return None
    return match.group(1).strip()


def is_affirmative(text: str) -> bool:
    """確認時，這句算「好、去做」嗎？（只認明確肯定，其餘都不算）"""
    return bool(_AFFIRM_PATTERN.match((text or "").strip()))


def is_stop(text: str) -> bool:
    """這句是要中止整個操作嗎？（停/取消/算了…）"""
    return bool(_STOP_PATTERN.search(text or ""))


# ── 讀「目前這頁」（doro 自己開著的那頁，不用給網址）─────────────────────────

# 指「目前這頁 / 你剛剛開的那頁」的說法。
_PAGE_REFERENT_PATTERN = re.compile(
    r"(我正在看的分頁|我現在看的分頁|正在看的分頁|這個分頁|目前分頁|這頁|這一頁|這個網頁|這個頁面|這篇|目前這?頁|目前的?網?頁|現在這?頁|"
    r"剛剛?那?頁|剛剛?開的|你(剛剛?)?(開|打開)的?(那)?(頁|網頁|頁面)?)"
)
# 想知道內容 / 讀取的說法（比一般讀取動詞再寬一點，因為已經有「這頁」當referent）。
_ABOUT_PATTERN = re.compile(
    r"(讀|看|唸|念|瀏覽|在說|說什麼|說啥|講什麼|寫什麼|內容|重點|摘要|大意|翻譯|整理)"
)


def parse_read_current_command(text: str) -> str | None:
    """判斷是不是「讀目前這頁」（doro 已開著的頁，無網址）。

    命中回傳整句（當作要問 AI 的問題），否則 ``None``。有網址的走
    :func:`parse_web_read_command`，不歸這裡。
    """
    if not text:
        return None
    stripped = text.strip()
    if not stripped or _extract_url(stripped):
        return None
    if not _PAGE_REFERENT_PATTERN.search(stripped):
        return None
    if _READ_INTENT_PATTERN.search(stripped) or _ABOUT_PATTERN.search(stripped):
        return stripped
    return None


def parse_web_read_command(text: str) -> WebReadRequest | None:
    """判斷 *text* 是不是「讀網頁」指令。

    Returns:
        命中時回傳 :class:`WebReadRequest`；否則回傳 ``None``（讓正常聊天處理）。
    """
    if not text:
        return None
    stripped = text.strip()
    if not stripped:
        return None

    url = _extract_url(stripped)
    if not url:
        return None

    if not _READ_INTENT_PATTERN.search(stripped):
        return None

    question = _extract_question(stripped, url)
    return WebReadRequest(url=url, question=question, raw_text=stripped)
