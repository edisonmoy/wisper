import json

import config as config_module
from config import Config


def test_defaults():
    cfg = Config()
    assert cfg.model == "base.en"
    assert cfg.history_limit == 20


def test_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "APP_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")

    cfg = Config(model="tiny.en", history_limit=5)
    cfg.save()
    loaded = Config.load()

    assert loaded.model == "tiny.en"
    assert loaded.history_limit == 5


def test_load_ignores_removed_auto_paste_field(tmp_path, monkeypatch):
    """Old config files containing auto_paste load without error; field is silently dropped."""
    cf = tmp_path / "config.json"
    cf.write_text(json.dumps({"model": "tiny.en", "auto_paste": True}))
    monkeypatch.setattr(config_module, "CONFIG_FILE", cf)
    cfg = Config.load()
    assert cfg.model == "tiny.en"
    assert not hasattr(cfg, "auto_paste")


def test_load_unknown_keys_ignored(tmp_path, monkeypatch):
    cf = tmp_path / "config.json"
    cf.write_text(json.dumps({"model": "small.en", "future_key": 42}))
    monkeypatch.setattr(config_module, "CONFIG_FILE", cf)

    cfg = Config.load()
    assert cfg.model == "small.en"
    assert cfg.history_limit == 20  # default preserved


def test_load_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "missing.json")
    assert Config.load() == Config()


def test_load_corrupt_file(tmp_path, monkeypatch):
    cf = tmp_path / "config.json"
    cf.write_text("not json{{{")
    monkeypatch.setattr(config_module, "CONFIG_FILE", cf)
    assert Config.load() == Config()


def test_repo_dir_is_project_root():
    assert (config_module.REPO_DIR / "app.py").exists()


def test_post_init_corrects_invalid_model():
    cfg = Config(model="gpt-4-invalid")
    assert cfg.model == "base.en"


def test_post_init_corrects_invalid_cleanup_mode():
    cfg = Config(cleanup_mode="bad-mode")
    assert cfg.cleanup_mode == "regex"


def test_post_init_corrects_out_of_range_history_limit():
    cfg = Config(history_limit=999)
    assert cfg.history_limit == 20


def test_mic_name_defaults_to_empty_string():
    cfg = Config()
    assert cfg.mic_name == ""


def test_post_init_corrects_invalid_mic_name():
    cfg = Config(mic_name=42)
    assert cfg.mic_name == ""


def test_post_init_corrects_invalid_hotkey_vk():
    cfg = Config(hotkey_vk="not_an_int")
    assert cfg.hotkey_vk == 63


def test_post_init_corrects_negative_hotkey_vk():
    cfg = Config(hotkey_vk=-1)
    assert cfg.hotkey_vk == 63


def test_post_init_corrects_invalid_hotkey_key():
    cfg = Config(hotkey_key=42)
    assert cfg.hotkey_key == ""


def test_mic_name_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "APP_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")

    cfg = Config(mic_name="AirPods Pro")
    cfg.save()
    loaded = Config.load()
    assert loaded.mic_name == "AirPods Pro"
