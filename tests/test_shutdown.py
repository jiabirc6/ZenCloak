"""Tests for the shared shutdown path.

Regression guard: ``POST /api/shutdown`` used to call ``os._exit(0)`` with no
cleanup at all. Because ``os._exit`` skips finally blocks and atexit handlers,
every mihomo child process leaked on that route while the tray Exit path
cleaned up correctly.
"""

import pytest

from zencloak.core import shutdown as shutdown_module
from zencloak.core.shutdown import spawn_hard_exit, stop_everything


class Recorder:
    """Stands in for sessions / proxy_manager / server."""

    def __init__(self, name: str, log: list, explode: bool = False) -> None:
        self.name = name
        self.log = log
        self.explode = explode
        self.wait_value = None

    def stop_all(self, wait: bool | None = None) -> None:
        self.log.append((self.name, "stop_all", wait))
        self.wait_value = wait
        if self.explode:
            raise RuntimeError(f"{self.name} failed")

    @property
    def should_exit(self) -> bool:
        return False

    @should_exit.setter
    def should_exit(self, value: bool) -> None:
        self.log.append((self.name, "should_exit", value))


class ServerStub:
    def __init__(self, log: list, explode: bool = False) -> None:
        self.log = log
        self.explode = explode
        self._should_exit = False

    @property
    def should_exit(self) -> bool:
        return self._should_exit

    @should_exit.setter
    def should_exit(self, value: bool) -> None:
        self.log.append(("server", "should_exit", value))
        if self.explode:
            raise RuntimeError("server failed")
        self._should_exit = value


def test_stop_everything_reaps_all_three():
    log: list = []
    sessions = Recorder("sessions", log)
    proxy = Recorder("proxy", log)
    server = ServerStub(log)

    stop_everything(sessions, proxy, server)

    assert ("sessions", "stop_all", False) in log
    assert ("proxy", "stop_all", None) in log
    assert ("server", "should_exit", True) in log


def test_stop_everything_passes_wait_flag():
    log: list = []
    sessions = Recorder("sessions", log)
    stop_everything(sessions, None, None, wait=True)
    assert sessions.wait_value is True


def test_stop_everything_continues_after_a_failure():
    """One failing step must not skip the others — that is what leaks."""
    log: list = []
    sessions = Recorder("sessions", log, explode=True)
    proxy = Recorder("proxy", log)
    server = ServerStub(log)

    stop_everything(sessions, proxy, server)

    assert ("proxy", "stop_all", None) in log
    assert ("server", "should_exit", True) in log


def test_stop_everything_tolerates_missing_components():
    stop_everything()  # must not raise
    stop_everything(None, None, None)


def _run_hard_exit(monkeypatch, **kwargs) -> list[int]:
    """Run spawn_hard_exit synchronously, capturing the exit code.

    The real helper exits from a daemon thread. Rather than scanning for that
    thread afterwards (which can join unrelated threads and hang), replace the
    thread with one that runs inline.
    """
    exited: list[int] = []
    monkeypatch.setattr(shutdown_module.os, "_exit", exited.append)
    monkeypatch.setattr(shutdown_module.time, "sleep", lambda _: None)

    class InlineThread:
        def __init__(self, target=None, daemon=None, **kw):
            self._target = target

        def start(self) -> None:
            self._target()

    monkeypatch.setattr(shutdown_module.threading, "Thread", InlineThread)
    spawn_hard_exit(**kwargs)
    return exited


def test_spawn_hard_exit_runs_cleanup_before_exit(monkeypatch):
    """The whole point: cleanup happens before os._exit."""
    log: list = []
    sessions = Recorder("sessions", log)
    proxy = Recorder("proxy", log)

    def on_exit() -> None:
        # Whatever is not cleaned up by now leaks when os._exit runs.
        assert ("proxy", "stop_all", None) in log, "退出前未清理 mihomo"
        assert ("sessions", "stop_all", False) in log, "退出前未清理会话"

    exited = _run_hard_exit(
        monkeypatch,
        sessions=sessions,
        proxy_manager=proxy,
        delay=0,
        on_exit=on_exit,
    )
    assert exited == [0]


def test_spawn_hard_exit_invokes_on_exit_hook(monkeypatch):
    calls: list[str] = []
    exited = _run_hard_exit(monkeypatch, delay=0, on_exit=lambda: calls.append("hook"))
    assert calls == ["hook"]
    assert exited == [0]


def test_shutdown_route_cleans_up_before_exiting(monkeypatch):
    """End-to-end guard for the /api/shutdown route itself."""
    import tempfile

    from fastapi.testclient import TestClient

    from zencloak.api import create_app
    from zencloak.core.profiles import ProfileStore
    from zencloak.core.sessions import SessionManager

    log: list = []
    proxy = Recorder("proxy", log)
    store = ProfileStore(tempfile.mkdtemp(), auto_init=False)
    sessions = SessionManager(data_root=store.data_dir)
    app = create_app(store, sessions, proxy_manager=proxy)

    cleaned: list[str] = []

    def fake_spawn_hard_exit(sessions=None, proxy_manager=None, server=None, **kw):
        # Verify the route hands the proxy manager over for cleanup.
        assert proxy_manager is proxy
        if proxy_manager is not None:
            proxy_manager.stop_all()
        cleaned.append("called")

    monkeypatch.setattr("zencloak.api.spawn_hard_exit", fake_spawn_hard_exit)

    client = TestClient(app)
    response = client.post("/api/shutdown")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert cleaned == ["called"]
    assert ("proxy", "stop_all", None) in log
