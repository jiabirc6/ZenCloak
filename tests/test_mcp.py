import json

import pytest

from zencloak import mcp as mcp_module
from zencloak.mcp import ApiError, _load_api_config, _request, list_profiles


def test_load_api_config_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_module, "runtime_file", lambda: tmp_path / "absent.json")
    with pytest.raises(ApiError, match="未在运行"):
        _load_api_config()


def test_load_api_config_reads_base_url_and_token(monkeypatch, tmp_path):
    info = tmp_path / "api.json"
    info.write_text(
        json.dumps({"base_url": "http://127.0.0.1:12345", "token": "tok"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(mcp_module, "runtime_file", lambda: info)
    assert _load_api_config() == ("http://127.0.0.1:12345", "tok")


def test_request_sends_bearer_token_and_returns_json(monkeypatch, tmp_path):
    info = tmp_path / "api.json"
    info.write_text(
        json.dumps({"base_url": "http://127.0.0.1:12345", "token": "tok"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(mcp_module, "runtime_file", lambda: info)

    seen = {}

    class FakeResponse:
        status_code = 200
        content = b'{"ok": true}'

        def json(self):
            return {"ok": True}

    def fake_request(method, url, json=None, params=None, headers=None, timeout=None):
        seen.update(method=method, url=url, json=json, headers=headers)
        return FakeResponse()

    monkeypatch.setattr(mcp_module.httpx, "request", fake_request)
    result = _request("POST", "/api/profiles", payload={"name": "x"})
    assert result == {"ok": True}
    assert seen["url"] == "http://127.0.0.1:12345/api/profiles"
    assert seen["headers"]["Authorization"] == "Bearer tok"


def test_request_raises_api_error_with_detail(monkeypatch, tmp_path):
    info = tmp_path / "api.json"
    info.write_text(
        json.dumps({"base_url": "http://127.0.0.1:12345", "token": "tok"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(mcp_module, "runtime_file", lambda: info)

    class FakeResponse:
        status_code = 409
        content = '{"detail": "档案未运行"}'.encode("utf-8")
        text = '{"detail": "档案未运行"}'

        def json(self):
            return {"detail": "档案未运行"}

    monkeypatch.setattr(
        mcp_module.httpx, "request", lambda *a, **kw: FakeResponse()
    )
    with pytest.raises(ApiError, match="档案未运行"):
        list_profiles()


def test_tools_are_registered_on_mcp_server():
    registered = {tool.name for tool in mcp_module.mcp._tool_manager.list_tools()}
    assert {
        "list_profiles",
        "list_sessions",
        "launch_session",
        "stop_session",
        "open_url",
        "list_pages",
        "read_page",
        "screenshot_page",
        "fingerprint_health_check",
        "check_consistency",
    } <= registered
