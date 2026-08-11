import time

import pytest

from zencloak.core.fingerprint import default_profile_draft
from zencloak.core.sessions import SessionError, SessionManager


class FakePage:
    def __init__(self):
        self.urls = []

    def goto(self, url, **_):
        self.urls.append(url)


class FakeBrowser:
    def __init__(self):
        self.connected = True

    def is_connected(self):
        return self.connected


class FakeContext:
    def __init__(self):
        self.browser = FakeBrowser()
        self.page = None
        self.pages = []
        self.closed = False

    def new_page(self):
        page = FakePage()
        self.pages.append(page)
        if self.page is None:
            self.page = page
        return page

    def close(self):
        self.closed = True
        self.browser.connected = False


def _profile(profile_id="aaaaaaaaaaaa", seed=12345, start_url=None):
    draft = default_profile_draft()
    draft.update(
        {
            "id": profile_id,
            "name": f"档案-{profile_id}",
            "seed": seed,
            "start_url": start_url,
        }
    )
    return draft


def _manager(tmp_path, launcher=None, contexts=None):
    if contexts is None:
        contexts = []

    def default_launcher(**kwargs):
        context = FakeContext()
        contexts.append((kwargs, context))
        return context

    return SessionManager(data_root=tmp_path, launcher=launcher or default_launcher), contexts


def _wait_status(manager, profile_id, target, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if manager.status(profile_id)["status"] == target:
            return
        time.sleep(0.02)
    raise AssertionError(f"status != {target}: {manager.status(profile_id)}")


def _wait_url(context, url, timeout=3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if any(url in page.urls for page in context.pages):
            return
        time.sleep(0.02)
    raise AssertionError(f"url not opened: {url}")


def test_launch_reaches_running_and_uses_profile_data_dir(tmp_path):
    manager, contexts = _manager(tmp_path)
    info = manager.launch(_profile())
    assert info["status"] == "launching"
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    assert contexts[0][0]["user_data_dir"] == str(tmp_path / "aaaaaaaaaaaa")


def test_launch_passes_fingerprint_and_behavior_kwargs(tmp_path):
    manager, contexts = _manager(tmp_path)
    profile = _profile()
    profile.update({"humanize": True, "human_preset": "careful"})
    manager.launch(profile)
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    kwargs = contexts[0][0]
    assert "--fingerprint=12345" in kwargs["args"]
    assert "Asia/Shanghai" in kwargs["timezone"]
    assert kwargs["locale"] == "zh-CN"
    assert kwargs["humanize"] is True
    assert kwargs["human_preset"] == "careful"
    assert kwargs["headless"] is False


def test_launch_builds_proxy_dict(tmp_path):
    manager, contexts = _manager(tmp_path)
    profile = _profile()
    profile["proxy"] = {
        "type": "http",
        "host": "proxy.example",
        "port": 8080,
        "username": "user",
        "password": "pass",
    }
    manager.launch(profile)
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    assert contexts[0][0]["proxy"] == {
        "server": "http://proxy.example:8080",
        "username": "user",
        "password": "pass",
    }


def test_launch_opens_start_url_after_running(tmp_path):
    manager, contexts = _manager(tmp_path)
    manager.launch(_profile(start_url="https://example.com"))
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    assert contexts[0][1].page.urls == ["https://example.com"]


def test_open_url_after_running_opens_new_page(tmp_path):
    manager, contexts = _manager(tmp_path)
    manager.launch(_profile())
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    manager.open_url("aaaaaaaaaaaa", "https://detect.example")
    _wait_url(contexts[0][1], "https://detect.example")


def test_open_url_when_stopped_raises(tmp_path):
    manager, _ = _manager(tmp_path)
    with pytest.raises(SessionError):
        manager.open_url("aaaaaaaaaaaa", "https://detect.example")


def test_second_launch_while_running_raises(tmp_path):
    manager, _ = _manager(tmp_path)
    manager.launch(_profile())
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    with pytest.raises(SessionError):
        manager.launch(_profile())


def test_stop_reaches_stopped_and_closes_context(tmp_path):
    manager, contexts = _manager(tmp_path)
    manager.launch(_profile())
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    info = manager.stop("aaaaaaaaaaaa")
    assert info["status"] == "stopping"
    _wait_status(manager, "aaaaaaaaaaaa", "stopped")
    assert contexts[0][1].closed is True


def test_launcher_error_records_error(tmp_path):
    def broken_launcher(**_):
        raise RuntimeError("boom")

    manager, _ = _manager(tmp_path, launcher=broken_launcher)
    manager.launch(_profile())
    _wait_status(manager, "aaaaaaaaaaaa", "error")
    assert "boom" in manager.status("aaaaaaaaaaaa")["error"]


def test_status_for_unknown_profile_is_stopped(tmp_path):
    manager, _ = _manager(tmp_path)
    assert manager.status("missing")["status"] == "stopped"


def test_stop_all_closes_all_contexts(tmp_path):
    manager, contexts = _manager(tmp_path)
    manager.launch(_profile("aaaaaaaaaaaa"))
    manager.launch(_profile("bbbbbbbbbbbb"))
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    _wait_status(manager, "bbbbbbbbbbbb", "running")
    manager.stop_all()
    _wait_status(manager, "aaaaaaaaaaaa", "stopped")
    _wait_status(manager, "bbbbbbbbbbbb", "stopped")
    assert all(context.closed for _, context in contexts)
