"""把「開瀏覽器讀網頁」丟到背景執行緒跑。

``WebPageReader.read`` 會阻塞（等瀏覽器跑完），不能在 Qt 主執行緒直接呼叫，否則
畫面會凍住。這裡用官方建議的 ``QRunnable`` + ``QThreadPool`` 模式（跟聊天的
``ChatWorker`` 一樣），跑完用 signal 把結果送回主執行緒。
"""

from __future__ import annotations

from PySide6 import QtCore

from ...utils.logger import get_logger
from .reader import WebPageReader, WebReadResult

logger = get_logger(__name__)


class WebReadWorkerSignals(QtCore.QObject):
    """``WebReadWorker`` 的 signals（QRunnable 自己不能帶 signal）。"""

    # (request_id, WebReadResult)
    result = QtCore.Signal(str, object)
    finished = QtCore.Signal(str)


class WebReadWorker(QtCore.QRunnable):
    """在背景執行緒用 :class:`WebPageReader` 讀一個網址。"""

    def __init__(self, request_id: str, reader: WebPageReader, url: str) -> None:
        super().__init__()
        self._request_id = request_id
        self._reader = reader
        self._url = url
        self.signals = WebReadWorkerSignals()
        self.setAutoDelete(True)

    @QtCore.Slot()
    def run(self) -> None:
        try:
            result = self._reader.read(self._url)
        except Exception as exc:  # 保底：reader 內部理論上已收斂，這裡再兜一層
            logger.critical(f"WebReadWorker 意外錯誤：{exc}", exc_info=True)
            result = WebReadResult(
                url=self._url,
                title="",
                text="",
                error=f"讀網頁時 doro 出了意外：{exc}",
            )
        try:
            self.signals.result.emit(self._request_id, result)
        finally:
            self.signals.finished.emit(self._request_id)
