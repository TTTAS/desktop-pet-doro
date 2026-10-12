"""Bridge to existing web capabilities on WebRuntime's owning thread."""

import json

from ..web.operator import WebOperator
from ..web.web_actions import valid_web_url
from .tools import PreparedTool, Query, WebGoal, WebURL


class TaskRefused(Exception):
    """Refusing a nested confirmation stops the entire task."""


def add_web_tools(registry, get_session, search_provider, ask_web, confirm, emit, cancelled):
    def read(params):
        if not valid_web_url(params.url):
            raise ValueError("只接受有效的 http(s) 網址。")

        def run():
            session = get_session()
            error = session.ensure_open() or session.goto(params.url)
            if error:
                raise ValueError(error)
            view = session.snapshot()
            if not view.ok:
                raise ValueError(view.error or "無法讀取頁面。")
            return json.dumps(
                {"url": view.url, "title": view.title, "text": view.text[:4500]}, ensure_ascii=False
            )

        return PreparedTool(run)

    registry.add("web.read", "用 Doro 瀏覽器讀取指定 http(s) 頁面。", WebURL, read)

    if search_provider is not None:

        def search(params):
            def run():
                results = search_provider.search(params.query, max_results=3)
                return json.dumps(
                    [
                        {
                            "url": r.url,
                            "title": r.title,
                            "text": (r.content or r.snippet or "")[:1200],
                        }
                        for r in results
                    ],
                    ensure_ascii=False,
                )

            return PreparedTool(run)

        registry.add("web.search", "唯讀搜尋，最多三個來源。", Query, search)

    if ask_web is not None:

        def operate(params):
            def confirm_step(text):
                if not confirm(text):
                    raise TaskRefused()
                return True

            def run():
                notes = []

                def progress(text):
                    notes.append(text)
                    emit(text)

                session = get_session()
                WebOperator(session, ask_web, confirm_step, progress, should_cancel=cancelled).run(
                    params.goal
                )
                view = session.snapshot()
                # A stopped operator is not evidence of completion. Give the planner
                # both its report and an independent final observation.
                return json.dumps(
                    {
                        "operator_reports": notes[-3:],
                        "observation": {
                            "url": view.url,
                            "text": view.text[:3500],
                            "error": view.error,
                        },
                        "notice": "停止不代表完成，請根據 observation 判斷。",
                    },
                    ensure_ascii=False,
                )[:6000]

            return PreparedTool(run)

        registry.add(
            "web.operate",
            "用既有網站操作迴圈完成一個網站子任務；每個敏感動作仍需確認。",
            WebGoal,
            operate,
        )
