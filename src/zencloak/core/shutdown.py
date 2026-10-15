"""Shared shutdown path.

``os._exit`` skips ``finally`` blocks and ``atexit`` handlers, so every exit
route has to reap mihomo children and browser sessions *before* calling it.
There are three such routes — the tray Exit item, ``POST /api/shutdown`` and
the normal ``main()`` teardown — and they used to carry duplicated copies of
this cleanup, which is exactly how one of them ended up leaking.

Every step writes a timestamped line to ``shutdown.log`` under the data root
before it runs. The process can be killed at any point and ``os._exit``
leaves no traceback, so the log is the only way to tell how far a stuck exit
got: the last line written names the step that never returned.
"""

import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

# Grace period before the hard exit. Long enough for the HTTP response of
# /api/shutdown to reach the caller, short enough not to feel like a hang.
EXIT_DELAY_SECONDS = 0.3

#: Where the exit trace goes. Set by ``configure``; until then logging is off
#: so the module stays usable from tests without touching the filesystem.
_log_path: Path | None = None
_log_lock = threading.Lock()


def configure(data_dir: str | Path) -> Path:
    """Point the shutdown trace at ``<data_dir>/shutdown.log``."""
    global _log_path
    _log_path = Path(data_dir) / "shutdown.log"
    return _log_path


def _trace(message: str) -> None:
    """Append one line, flushed immediately.

    Deliberately synchronous and unbuffered: the whole point is to survive a
    kill, and a buffered line would be lost exactly when it matters. Any
    failure here is ignored - logging must never be the reason shutdown stops.
    """
    if _log_path is None:
        return
    try:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        thread = threading.current_thread().name
        with _log_lock:
            with open(_log_path, "a", encoding="utf-8") as handle:
                handle.write(f"[{stamp}] [{thread}] {message}\n")
                handle.flush()
                os.fsync(handle.fileno())
    except Exception:  # noqa: BLE001 - tracing must never break shutdown
        pass


def stop_everything(
    sessions: Any = None,
    proxy_manager: Any = None,
    server: Any = None,
    wait: bool = False,
) -> None:
    """Best-effort teardown of sessions, proxy children and the web server.

    Every step is individually guarded: a failure while shutting down must
    never prevent the remaining steps from running, because whatever is
    skipped here leaks a child process.
    """
    _trace(f"stop_everything start (wait={wait})")
    if sessions is not None:
        _trace("sessions.stop_all begin")
        try:
            sessions.stop_all(wait=wait)
        except Exception as exc:  # noqa: BLE001 - teardown must run to completion
            _trace(f"sessions.stop_all raised {type(exc).__name__}: {exc}")
        _trace("sessions.stop_all done")
    if proxy_manager is not None:
        _trace("proxy_manager.stop_all begin")
        try:
            proxy_manager.stop_all()
        except Exception as exc:  # noqa: BLE001 - teardown must run to completion
            _trace(f"proxy_manager.stop_all raised {type(exc).__name__}: {exc}")
        _trace("proxy_manager.stop_all done")
    if server is not None:
        _trace("server.should_exit = True")
        try:
            server.should_exit = True
        except Exception as exc:  # noqa: BLE001 - teardown must run to completion
            _trace(f"server.should_exit raised {type(exc).__name__}: {exc}")
    _trace("stop_everything done")


def spawn_hard_exit(
    sessions: Any = None,
    proxy_manager: Any = None,
    server: Any = None,
    delay: float = EXIT_DELAY_SECONDS,
    on_exit: Callable[[], None] | None = None,
) -> None:
    """Clean up, then hard-exit from a daemon thread.

    Runs off the calling thread so an HTTP handler can return its response
    before the process disappears.
    """
    _trace(f"spawn_hard_exit scheduled (delay={delay}s)")

    def _run() -> None:
        time.sleep(delay)
        stop_everything(sessions, proxy_manager, server)
        if on_exit is not None:
            _trace("on_exit hook begin")
            try:
                on_exit()
            except Exception:  # noqa: BLE001 - last step before os._exit
                _trace("on_exit hook raised (ignored)")
        _trace("calling os._exit(0)")
        os._exit(0)

    threading.Thread(target=_run, daemon=True).start()


def hard_exit(
    sessions: Any = None,
    proxy_manager: Any = None,
    server: Any = None,
) -> None:
    """Synchronous cleanup, then exit. Used by the tray Exit item."""
    _trace("hard_exit called (tray exit)")
    stop_everything(sessions, proxy_manager, server)
    _trace("calling os._exit(0)")
    os._exit(0)
