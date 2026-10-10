"""設定持久化測試(04 號:記住上次的輸出資料夾)。"""

from doro_app.core.gif_factory.config import DEFAULTS, load_config, save_config


def test_missing_file_returns_defaults(tmp_path):
    config = load_config(tmp_path / "nope.json")
    assert config == DEFAULTS


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "cfg.json"
    save_config({"output_dir": "D:/my_output", "fmt": "apng"}, path)

    config = load_config(path)
    assert config["output_dir"] == "D:/my_output"
    assert config["fmt"] == "apng"


def test_corrupt_file_returns_defaults(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{ not valid json", encoding="utf-8")

    assert load_config(path) == DEFAULTS


def test_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "cfg.json"
    save_config({"output_dir": "D:/x", "fmt": "webp", "junk": "ignore me"}, path)

    config = load_config(path)
    assert "junk" not in config
