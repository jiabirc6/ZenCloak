import json
import os
import sys

from zencloak.app import _runtime_info_path, write_runtime_info


def test_write_runtime_info_publishes_base_url_and_token(tmp_path):
    info_path = write_runtime_info(tmp_path, "http://127.0.0.1:12345", "tok-1")
    assert info_path == _runtime_info_path(tmp_path)
    data = json.loads(info_path.read_text(encoding="utf-8"))
    assert data == {"base_url": "http://127.0.0.1:12345", "token": "tok-1"}


def test_bundled_engine_dir_none_when_not_frozen(tmp_path, monkeypatch):
    from zencloak.app import _bundled_engine_dir

    monkeypatch.delattr(sys, "frozen", raising=False)
    assert _bundled_engine_dir() is None


def test_bundled_engine_dir_detects_packaged_kernel(tmp_path, monkeypatch):
    from zencloak.app import _bundled_engine_dir

    (tmp_path / "engine" / "chromium-146.0.7680.177.5").mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "ZenCloak.exe"))
    assert _bundled_engine_dir() == tmp_path / "engine"


def test_bundled_engine_dir_ignores_empty_engine(tmp_path, monkeypatch):
    from zencloak.app import _bundled_engine_dir

    (tmp_path / "engine").mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "ZenCloak.exe"))
    assert _bundled_engine_dir() is None


def test_install_engine_invokes_ensure_binary(monkeypatch):
    from zencloak import app as app_module

    calls = []
    import cloakbrowser.download as download

    monkeypatch.setattr(
        download, "ensure_binary", lambda *a, **k: calls.append("go")
    )
    try:
        app_module._install_engine()
    except SystemExit as exc:
        assert exc.code == 0
    assert calls == ["go"]
