"""ChatLog（本機對話紀錄）與 LoRA 資料匯出。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from doro_app.core.chat.chat_log import ChatLog

ROOT = Path(__file__).resolve().parents[3]


def _load_exporter():
    spec = importlib.util.spec_from_file_location(
        "export_lora_dataset", ROOT / "scripts" / "export_lora_dataset.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _reply(line: str) -> str:
    return json.dumps({"state": "idle", "line": line}, ensure_ascii=False)


def test_records_turns_and_reads_them_back(tmp_path):
    log = ChatLog(tmp_path / "sub" / "log.sqlite3")
    log.record(user="早安", reply_json=_reply("早安呀"), persona="你是Doro", model="m")

    turns = list(ChatLog(log.path).iter_turns())

    assert len(turns) == 1
    assert turns[0].user == "早安"
    assert turns[0].persona == "你是Doro"
    assert turns[0].model == "m"
    assert turns[0].is_auto is False
    assert turns[0].kind == "chat"


def test_new_session_changes_session_id(tmp_path):
    log = ChatLog(tmp_path / "log.sqlite3")
    first = log.session_id
    log.new_session()
    assert log.session_id != first


def test_record_failure_does_not_raise(tmp_path):
    log = ChatLog(tmp_path / "log.sqlite3")
    log.path.unlink()
    log.path.mkdir()  # 路徑變成資料夾，sqlite 開不了
    log.record(user="hi", reply_json=_reply("hi"))


class TestBuildSamples:
    def _turns(self, tmp_path):
        log = ChatLog(tmp_path / "log.sqlite3")
        log.record(user="早安", reply_json=_reply("早安呀"), persona="你是Doro")
        log.record(user="自己講", reply_json=_reply("哼"), is_auto=True)
        log.record(user="吃什麼", reply_json=_reply("歐根"), persona="你是Doro")
        log.record(user="讀網頁", reply_json=_reply("網頁說…"), kind="web_answer")
        log.new_session()
        log.record(user="晚安", reply_json=_reply("晚安"), persona="新人設")
        return list(log.iter_turns())

    def test_groups_sessions_and_skips_auto_and_web(self, tmp_path):
        exporter = _load_exporter()
        samples = exporter.build_samples(self._turns(tmp_path), target="line")

        assert len(samples) == 2
        convs = {s["system"]: [m["value"] for m in s["conversations"]] for s in samples}
        assert convs["你是Doro"] == ["早安", "早安呀", "吃什麼", "歐根"]
        assert convs["新人設"] == ["晚安", "晚安"]

    def test_json_target_keeps_structured_reply(self, tmp_path):
        exporter = _load_exporter()
        samples = exporter.build_samples(self._turns(tmp_path), target="json", system="none")

        first = samples[0]["conversations"][1]["value"]
        assert json.loads(first)["state"] == "idle"
        assert "system" not in samples[0]

    def test_max_turns_splits_long_sessions(self, tmp_path):
        exporter = _load_exporter()
        samples = exporter.build_samples(
            self._turns(tmp_path), target="line", max_turns=1, include_auto=True
        )
        assert all(len(s["conversations"]) == 2 for s in samples)
        assert len(samples) == 4

    def test_main_writes_llama_factory_files(self, tmp_path, capsys):
        exporter = _load_exporter()
        self._turns(tmp_path)
        out = tmp_path / "out"

        code = exporter.main(["--db", str(tmp_path / "log.sqlite3"), "--out", str(out)])

        assert code == 0
        data = json.loads((out / "doro_chat.json").read_text(encoding="utf-8"))
        info = json.loads((out / "dataset_info.json").read_text(encoding="utf-8"))
        assert len(data) == 2
        assert info["doro_chat"]["formatting"] == "sharegpt"
