"""Shared shutdown path.

``os._exit`` skips ``finally`` blocks and ``atexit`` handlers, so every exit
route has to reap mihomo children and browser sessions *before* calling it.
There are three such routes — the tray Exit item, ``POST /api/shutdown`` and
the normal ``main()`` teardown — and they used to carry duplicated copies of
this cleanup, which is exactly how one of them ended up leaking.
"""

import os
import threading
import time
from typing import Any, Callable

# Grace period before the hard exit. Long enough for the HTTP response of
# /api/shutdown to reach the caller, short enough not to feel like a hang.
EXIT_DELAY_SECONDS = 0.3


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
    if sessions is not None:
        try:
            sessions.stop_all(wait=wait)
        except Exception:  # noqa: BLE001 - teardown must run to completion
            pass
    if proxy_manager is not None:
        try:
            proxy_manager.stop_all()
        except Exception:  # noqa: BLE001 - teardown must run to completion
            pass
    if server is not None:
        try:
            server.should_exit = True
        except Exception:  # noqa: BLE001 - teardown must run to completion
            pass


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

    def _run() -> None:
        time.sleep(delay)
        stop_everything(sessions, proxy_manager, server)
        if on_exit is not None:
            try:
                on_exit()
            except Exception:  # noqa: BLE001 - last step before os._exit
                pass
        os._exit(0)

    threading.Thread(target=_run, daemon=True).start()
