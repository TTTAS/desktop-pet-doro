"""把 Doro 的本機對話紀錄匯出成 LoRA 訓練資料（ShareGPT 格式）。

輸出可直接給 LLaMA-Factory（附 dataset_info.json）或 Unsloth 使用，
完整流程見 docs/lora-training.md。

    python scripts/export_lora_dataset.py                     # 預設讀 ~/.doro/chat_log.sqlite3
    python scripts/export_lora_dataset.py --out data/doro_lora --target line
    python scripts/export_lora_dataset.py --stats             # 只看筆數

在 Doro 的 venv 裡執行（會 import doro_app）。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from doro_app.core.chat.chat_log import ChatLog, LoggedTurn
from doro_app.utils.paths import chat_log_path

DATASET_NAME = "doro_chat"


def assistant_text(turn: LoggedTurn, target: str) -> str | None:
    """``json``：完整結構化回覆（練出來的模型照樣能驅動動作）；``line``：只留台詞。"""
    if target == "json":
        return turn.reply_json
    try:
        line = json.loads(turn.reply_json).get("line", "")
    except (ValueError, AttributeError):
        return None
    return line.strip() or None


def system_text(turn: LoggedTurn, mode: str) -> str:
    if mode == "persona":
        return turn.persona.strip()
    if mode == "full":
        return turn.system.strip()
    return ""


def build_samples(
    turns: Iterable[LoggedTurn],
    *,
    target: str = "json",
    system: str = "persona",
    max_turns: int = 8,
    include_auto: bool = False,
    include_web: bool = False,
) -> list[dict]:
    """同一 session 的連續輪次拼成多輪對話，每 ``max_turns`` 輪切一筆。

    system 取該段第一輪的設定；``full`` 模式每輪 system 都不同（含當下狀態），
    此時每輪各自成一筆，避免後面輪次看到錯的情境。
    """
    if system == "full":
        max_turns = 1
    samples: list[dict] = []
    current: list[dict] = []
    current_session: str | None = None
    current_system = ""

    def flush() -> None:
        if current:
            sample: dict = {"conversations": list(current)}
            if current_system:
                sample["system"] = current_system
            samples.append(sample)
            current.clear()

    for turn in turns:
        if turn.excluded:
            continue
        if turn.is_auto and not include_auto:
            continue
        if turn.kind != "chat" and not include_web:
            continue
        answer = assistant_text(turn, target)
        if not answer or not turn.user.strip():
            continue
        if turn.session_id != current_session or len(current) >= max_turns * 2:
            flush()
            current_session = turn.session_id
            current_system = system_text(turn, system)
        current.append({"from": "human", "value": turn.user.strip()})
        current.append({"from": "gpt", "value": answer})
    flush()
    return samples


def dataset_info() -> dict:
    """LLaMA-Factory 的 dataset_info.json 片段。"""
    return {
        DATASET_NAME: {
            "file_name": f"{DATASET_NAME}.json",
            "formatting": "sharegpt",
            "columns": {"messages": "conversations", "system": "system"},
            "tags": {
                "role_tag": "from",
                "content_tag": "value",
                "user_tag": "human",
                "assistant_tag": "gpt",
            },
        }
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=chat_log_path(), help="對話紀錄 SQLite 檔")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "doro_lora", help="輸出資料夾")
    parser.add_argument(
        "--target",
        choices=["json", "line"],
        default="json",
        help="json＝完整結構化回覆（預設，可直接接回 Doro）；line＝只練台詞語氣",
    )
    parser.add_argument(
        "--system",
        choices=["persona", "full", "none"],
        default="persona",
        help="system prompt 用人設、當下完整 prompt，或不放",
    )
    parser.add_argument("--max-turns", type=int, default=8, help="每筆最多幾輪對話")
    parser.add_argument("--include-auto", action="store_true", help="包含 Doro 自己開口的輪次")
    parser.add_argument("--include-web", action="store_true", help="包含讀網頁後的回答")
    parser.add_argument("--stats", action="store_true", help="只印統計，不寫檔")
    args = parser.parse_args(argv)

    if not args.db.exists():
        print(f"找不到對話紀錄：{args.db}（先用 Doro 聊幾句，或用 --db 指定）", file=sys.stderr)
        return 1

    turns = list(ChatLog(args.db).iter_turns())
    samples = build_samples(
        turns,
        target=args.target,
        system=args.system,
        max_turns=max(1, args.max_turns),
        include_auto=args.include_auto,
        include_web=args.include_web,
    )
    pairs = sum(len(s["conversations"]) // 2 for s in samples)
    print(f"紀錄 {len(turns)} 輪 → 匯出 {len(samples)} 筆對話、{pairs} 組問答")
    if args.stats:
        return 0
    if not samples:
        print("沒有可匯出的對話。", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    data_path = args.out / f"{DATASET_NAME}.json"
    data_path.write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")
    info_path = args.out / "dataset_info.json"
    info_path.write_text(json.dumps(dataset_info(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"寫入 {data_path}\n寫入 {info_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
