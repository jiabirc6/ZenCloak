"""Tests for the shared shutdown path.

Regression guard: ``POST /api/shutdown`` used to call ``os._exit(0)`` with no
cleanup at all. Because ``os._exit`` skips finally blocks and atexit handlers,
every mihomo child process leaked on that route while the tray Exit path
cleaned up correctly.

The exit trace is also covered here: ``os._exit`` leaves no traceback, so when
an exit hangs the log is the only evidence of how far it got.
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


# ── exit trace ────────────────────────────────────────────────────────────


@pytest.fixture()
def traced(tmp_path, monkeypatch):
    """Point the trace at a temp file and restore it afterwards."""
    path = shutdown_module.configure(tmp_path)
    yield path
    monkeypatch.setattr(shutdown_module, "_log_path", None)


def test_trace_is_off_until_configured(tmp_path, monkeypatch):
    """Importing the module must not touch the filesystem."""
    monkeypatch.setattr(shutdown_module, "_log_path", None)
    shutdown_module._trace("should go nowhere")
    assert list(tmp_path.iterdir()) == []


def test_stop_everything_records_each_step(traced):
    log: list = []
    stop_everything(Recorder("sessions", log), Recorder("proxy", log), ServerStub(log))
    text = traced.read_text(encoding="utf-8")
    assert "stop_everything start" in text
    assert "sessions.stop_all begin" in text
    assert "sessions.stop_all done" in text
    assert "proxy_manager.stop_all begin" in text
    assert "proxy_manager.stop_all done" in text
    assert "stop_everything done" in text


def test_trace_names_the_step_that_raised(traced):
    """A raising step is recorded, so a hang after it is distinguishable."""
    log: list = []
    stop_everything(Recorder("sessions", log, explode=True), Recorder("proxy", log))
    text = traced.read_text(encoding="utf-8")
    assert "sessions.stop_all raised RuntimeError" in text
    # Teardown continued past the failure.
    assert "proxy_manager.stop_all done" in text


def test_trace_lines_carry_a_timestamp_and_thread(traced):
    stop_everything()
    line = traced.read_text(encoding="utf-8").strip().split("\n")[0]
    assert line.startswith("[")
    assert "]" in line
    # e.g. [2026-10-15 14:24:48.053] [MainThread] ...
    stamp = line.split("]")[0].lstrip("[")
    assert "." in stamp, f"timestamp lacks milliseconds: {stamp!r}"
    assert "MainThread" in line or "Thread" in line


def test_trace_survives_an_unwritable_path(tmp_path):
    """Tracing must never be the reason shutdown stops."""
    shutdown_module._log_path = tmp_path / "no-such-dir" / "shutdown.log"
    try:
        shutdown_module._trace("must not raise")
        stop_everything()
    finally:
        shutdown_module._log_path = None


def test_hard_exit_traces_then_exits(traced, monkeypatch):
    exited: list[int] = []
    monkeypatch.setattr(shutdown_module.os, "_exit", exited.append)
    shutdown_module.hard_exit()
    assert exited == [0]
    assert "hard_exit called" in traced.read_text(encoding="utf-8")


def test_spawn_hard_exit_traces_the_schedule(traced, monkeypatch):
    """The schedule line proves the route was entered, before any cleanup."""
    monkeypatch.setattr(shutdown_module.os, "_exit", lambda code: None)
    monkeypatch.setattr(shutdown_module.time, "sleep", lambda _: None)

    class InlineThread:
        def __init__(self, target=None, daemon=None, **kw):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr(shutdown_module.threading, "Thread", InlineThread)
    spawn_hard_exit()
    assert "spawn_hard_exit scheduled" in traced.read_text(encoding="utf-8")
