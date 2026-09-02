import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from zencloak.core.fingerprint import default_profile_draft
from zencloak.core.sessions import SessionError, SessionManager


class FakePage:
    def __init__(self, url="about:blank"):
        self.url = url
        self.urls = []
        self.closed = False
        self.fail_on = None
        self.evaluate_result = {"webdriver": False}
        self.evaluate_error = None
        self.title_text = "测试页面"
        self.body_text = "页面正文内容"
        self.screenshots = []

    def goto(self, url, **_):
        if url == self.fail_on:
            raise RuntimeError("goto failed")
        self.url = url
        self.urls.append(url)

    def evaluate(self, script):
        if self.evaluate_error:
            raise self.evaluate_error
        return self.evaluate_result

    def title(self):
        return self.title_text

    def inner_text(self, selector, **_):
        return self.body_text

    def screenshot(self, path=None, **_):
        self.screenshots.append(path)
        Path(path).write_bytes(b"png")

    def close(self):
        self.closed = True


class FakeCDP:
    def __init__(self, context, closes_fail=False):
        self.context = context
        self.closed = []
        self.closes_fail = closes_fail
        self.created = 0
        self._ids = {}

    def _id_for(self, page):
        return self._ids.setdefault(id(page), f"t{len(self._ids)}")

    def send(self, method, params=None):
        if method == "Target.getTargets":
            return {
                "targetInfos": [
                    {"type": "page", "url": page.url, "targetId": self._id_for(page)}
                    for page in self.context.pages
                ]
            }
        if method == "Target.closeTarget":
            if self.closes_fail:
                self.closed.append(params["targetId"])
                return {}
            target = next(
                page
                for page in self.context.pages
                if self._id_for(page) == params["targetId"]
            )
            target.close()
            self.context.pages.remove(target)
            self.closed.append(params["targetId"])
            return {}
        if method == "Target.createTarget":
            self.context.pages.append(FakePage(params["url"]))
            self.created += 1
            return {"targetId": "t-new"}
        raise AssertionError(method)


class FakeBrowser:
    def __init__(self, context=None):
        self.connected = True
        self.context = context

    def is_connected(self):
        return self.connected

    def new_browser_cdp_session(self):
        return FakeCDP(self.context)


class FakeContext:
    def __init__(self):
        self.browser = FakeBrowser(self)
        self.page = None
        self.pages = [FakePage("about:blank")]
        self.closed = False
        self.fail_on = None
        self.evaluate_error = None

    def new_page(self):
        page = FakePage()
        page.fail_on = self.fail_on
        page.evaluate_error = self.evaluate_error
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


class FakeProxyManager:
    def __init__(self):
        self.started = []
        self.stopped = []

    def load_nodes(self, sub_id):
        return [{"name": "美国节点", "type": "vless", "server": "1.2.3.4", "port": 443}]

    def start(self, profile_id, nodes, node_name=None):
        self.started.append((profile_id, node_name))
        return SimpleNamespace(mixed_port=17891)

    def stop(self, profile_id):
        self.stopped.append(profile_id)


def _manager(tmp_path, launcher=None, contexts=None, proxy_manager=None):
    if contexts is None:
        contexts = []

    def default_launcher(**kwargs):
        context = FakeContext()
        contexts.append((kwargs, context))
        return context

    return (
        SessionManager(
            data_root=tmp_path,
            launcher=launcher or default_launcher,
            proxy_manager=proxy_manager,
        ),
        contexts,
    )


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
    assert contexts[0][0]["downloads_path"] == str(
        tmp_path / "aaaaaaaaaaaa" / "Downloads"
    )
    assert contexts[0][0]["accept_downloads"] is True


def test_launch_passes_fingerprint_and_behavior_kwargs(tmp_path):
    manager, contexts = _manager(tmp_path)
    profile = _profile()
    profile.update({"humanize": True, "human_preset": "careful"})
    manager.launch(profile)
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    kwargs = contexts[0][0]
    assert "--fingerprint=12345" in kwargs["args"]
    assert "--lang=zh-CN" in kwargs["args"]
    assert "--fingerprint-locale=zh-CN" in kwargs["args"]
    assert "Asia/Shanghai" in kwargs["timezone"]
    assert kwargs["humanize"] is True
    assert kwargs["human_preset"] == "careful"
    assert kwargs["headless"] is False


def test_launch_lang_follows_profile_locale(tmp_path):
    manager, contexts = _manager(tmp_path)
    profile = _profile()
    profile["locale"] = "en-US"
    manager.launch(profile)
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    kwargs = contexts[0][0]
    assert "--lang=en-US" in kwargs["args"]
    assert "--fingerprint-locale=en-US" in kwargs["args"]
    assert "locale" not in kwargs


def test_launch_re_enables_translate_feature(tmp_path):
    manager, contexts = _manager(tmp_path)
    manager.launch(_profile())
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    args = contexts[0][0]["args"]
    assert "--enable-features=Translate" in args
    disable = next(
        arg for arg in args if arg.startswith("--disable-features=")
    )
    assert ",Translate" not in disable
    import cloakbrowser.browser as cloak_browser

    assert any(
        "--disable-features=" in arg and "Translate" in arg
        for arg in cloak_browser.IGNORE_DEFAULT_ARGS
    )


def test_launch_starts_mihomo_proxy_and_passes_server(tmp_path):
    proxy = FakeProxyManager()
    manager, contexts = _manager(tmp_path, proxy_manager=proxy)
    profile = _profile()
    profile.update(
        {
            "proxy_enabled": True,
            "proxy_mode": "mihomo",
            "proxy_subscription_id": "sub123",
            "proxy_node": "美国节点",
        }
    )
    manager.launch(profile)
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    assert proxy.started == [("aaaaaaaaaaaa", "美国节点")]
    assert contexts[0][0]["proxy"] == {"server": "socks5://127.0.0.1:17891"}
    manager.stop("aaaaaaaaaaaa")
    _wait_status(manager, "aaaaaaaaaaaa", "stopped")
    assert proxy.stopped == ["aaaaaaaaaaaa"]


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


def test_launch_reuses_default_blank_page_for_start_url(tmp_path):
    manager, contexts = _manager(tmp_path)
    manager.launch(_profile(start_url="https://example.com"))
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    assert contexts[0][1].pages[0].urls == ["https://example.com"]
    assert contexts[0][1].pages[0].closed is False


def test_launch_keeps_single_blank_page_when_no_start_url(tmp_path):
    manager, contexts = _manager(tmp_path)
    manager.launch(_profile())
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    assert contexts[0][1].pages[0].closed is False


def test_launch_loads_newtab_extension_when_start_url_set(tmp_path):
    manager, contexts = _manager(tmp_path)
    manager.launch(_profile(start_url="https://example.com/path?q=1"))
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    extension_paths = contexts[0][0]["extension_paths"]
    assert len(extension_paths) == 1
    assert extension_paths[0].endswith("newtab-v3")


def test_launch_always_loads_newtab_extension(tmp_path):
    manager, contexts = _manager(tmp_path)
    manager.launch(_profile())
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    extension_paths = contexts[0][0]["extension_paths"]
    assert len(extension_paths) == 1
    assert extension_paths[0].endswith("newtab-v3")


def test_open_url_after_running_opens_new_page(tmp_path):
    manager, contexts = _manager(tmp_path)
    manager.launch(_profile())
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    result = manager.open_url("aaaaaaaaaaaa", "https://detect.example")
    _wait_url(contexts[0][1], "https://detect.example")
    assert result["opened"] is True


def test_open_url_reports_failure_when_goto_fails(tmp_path):
    manager, contexts = _manager(tmp_path)
    manager.launch(_profile())
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    contexts[0][1].fail_on = "https://broken.example"
    result = manager.open_url("aaaaaaaaaaaa", "https://broken.example")
    assert result["opened"] is False


def test_sweep_replaces_broken_new_tabs(tmp_path):
    manager, contexts = _manager(tmp_path)
    manager.launch(_profile())
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    context = contexts[0][1]
    ntp = context.new_page()
    ntp.url = "chrome://new-tab-page-third-party/loading"
    cdp = FakeCDP(context)
    manager._sweep_new_tabs(cdp)
    assert ntp.closed is True
    assert any(p.url == "about:blank" for p in context.pages)


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


def test_stop_all_closes_all_contexts_and_joins_threads(tmp_path):
    manager, contexts = _manager(tmp_path)
    manager.launch(_profile("aaaaaaaaaaaa"))
    manager.launch(_profile("bbbbbbbbbbbb"))
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    _wait_status(manager, "bbbbbbbbbbbb", "running")
    manager.stop_all()
    _wait_status(manager, "aaaaaaaaaaaa", "stopped")
    _wait_status(manager, "bbbbbbbbbbbb", "stopped")
    assert all(context.closed for _, context in contexts)
    with manager._lock:
        threads = [s["thread"] for s in manager._sessions.values() if s.get("thread")]
    assert all(not thread.is_alive() for thread in threads)


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


def test_run_probe_returns_signals_from_session_thread(tmp_path):
    manager, contexts = _manager(tmp_path)
    manager.launch(_profile())
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    signals = manager.run_probe("aaaaaaaaaaaa")
    assert signals == {"webdriver": False}
    probe_page = contexts[0][1].pages[-1]
    assert probe_page.closed is True


def test_run_probe_wraps_evaluate_failure(tmp_path):
    manager, contexts = _manager(tmp_path)
    manager.launch(_profile())
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    contexts[0][1].evaluate_error = RuntimeError("boom")
    with pytest.raises(SessionError, match="指纹探测失败"):
        manager.run_probe("aaaaaaaaaaaa")


def test_run_probe_requires_running_session(tmp_path):
    manager, _ = _manager(tmp_path)
    with pytest.raises(SessionError, match="档案未运行"):
        manager.run_probe("aaaaaaaaaaaa")


def test_run_page_op_list_read_screenshot(tmp_path):
    manager, _ = _manager(tmp_path)
    manager.launch(_profile())
    _wait_status(manager, "aaaaaaaaaaaa", "running")

    pages = manager.run_page_op("aaaaaaaaaaaa", "list")
    assert len(pages) == 1
    assert pages[0]["index"] == 0
    assert pages[0]["title"] == "测试页面"

    content = manager.run_page_op("aaaaaaaaaaaa", "read", index=0)
    assert content["url"] == "about:blank"
    assert content["title"] == "测试页面"
    assert content["text"] == "页面正文内容"

    trimmed = manager.run_page_op("aaaaaaaaaaaa", "read", index=0, max_chars=2)
    assert trimmed["text"] == "页面"

    shot_path = tmp_path / "shot.png"
    result = manager.run_page_op("aaaaaaaaaaaa", "screenshot", index=0, path=str(shot_path))
    assert result["path"] == str(shot_path)
    assert shot_path.read_bytes() == b"png"


def test_run_page_op_rejects_unknown_op_and_bad_index(tmp_path):
    manager, _ = _manager(tmp_path)
    manager.launch(_profile())
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    with pytest.raises(SessionError, match="未知页面操作"):
        manager.run_page_op("aaaaaaaaaaaa", "delete")
    with pytest.raises(SessionError, match="页面不存在"):
        manager.run_page_op("aaaaaaaaaaaa", "read", index=99)


def test_run_page_op_requires_running_session(tmp_path):
    manager, _ = _manager(tmp_path)
    with pytest.raises(SessionError, match="档案未运行"):
        manager.run_page_op("aaaaaaaaaaaa", "list")


def test_launch_without_proxy_forces_direct_connection(tmp_path):
    manager, contexts = _manager(tmp_path)
    manager.launch(_profile())
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    kwargs = contexts[0][0]
    assert "--no-proxy-server" in kwargs["args"]
    assert "proxy" not in kwargs


def test_launch_with_mihomo_proxy_does_not_force_direct(tmp_path):
    proxy = FakeProxyManager()
    manager, contexts = _manager(tmp_path, proxy_manager=proxy)
    profile = _profile()
    profile.update(
        {
            "proxy_enabled": True,
            "proxy_mode": "mihomo",
            "proxy_subscription_id": "sub123",
            "proxy_node": "美国节点",
        }
    )
    manager.launch(profile)
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    kwargs = contexts[0][0]
    assert "--no-proxy-server" not in kwargs["args"]
    assert kwargs["proxy"] == {"server": "socks5://127.0.0.1:17891"}


def test_launch_with_manual_proxy_does_not_force_direct(tmp_path):
    manager, contexts = _manager(tmp_path)
    profile = _profile()
    profile["proxy"] = {
        "type": "http",
        "host": "proxy.example",
        "port": 8080,
        "username": "",
        "password": "",
    }
    manager.launch(profile)
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    kwargs = contexts[0][0]
    assert "--no-proxy-server" not in kwargs["args"]
    assert kwargs["proxy"]["server"] == "http://proxy.example:8080"


def test_is_broken_new_tab_covers_all_variants():
    from zencloak.core.sessions import SessionManager

    broken = SessionManager._is_broken_new_tab
    assert broken("chrome://new-tab-page-third-party/index.html")
    assert broken("chrome://new-tab-page/")
    assert broken("chrome://newtab")
    assert broken("chrome-extension://abcdef/newtab.html")
    assert not broken("about:blank")
    assert not broken("https://www.google.com/")
    assert not broken("https://example.com/docs/newtab.html")


def test_sweep_covers_plain_ntp_and_extension_variants(tmp_path):
    manager, contexts = _manager(tmp_path)
    manager.launch(_profile())
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    context = contexts[0][1]
    broken = []
    for url in ("chrome://new-tab-page/", "chrome-extension://abc/newtab.html"):
        page = context.new_page()
        page.url = url
        broken.append(page)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("zencloak.core.sessions.time.sleep", lambda s: None)
    manager._sweep_new_tabs(FakeCDP(context))
    monkeypatch.undo()
    assert all(page.closed for page in broken)


def test_sweep_does_not_multiply_when_closes_are_ignored(tmp_path):
    """Crash-restore mode ignores closeTarget; sweep must not then create."""
    manager, contexts = _manager(tmp_path)
    manager.launch(_profile())
    _wait_status(manager, "aaaaaaaaaaaa", "running")
    context = contexts[0][1]
    for url in ("chrome://new-tab-page/", "chrome://new-tab-page-third-party/"):
        page = context.new_page()
        page.url = url
    cdp = FakeCDP(context, closes_fail=True)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("zencloak.core.sessions.time.sleep", lambda s: None)
    for _ in range(5):
        manager._sweep_new_tabs(cdp)
    monkeypatch.undo()
    assert len(context.pages) == 3  # 无增殖（原 1 空白 + 2 NTP 原样保留）
    assert cdp.created == 0  # 一次都没补建
