import argparse
import socket
import threading
import time
import urllib.request
from pathlib import Path

import uvicorn
import webview

from .api import create_app
from .core.lock import InstanceLock
from .core.profiles import ProfileStore
from .core.sessions import SessionManager


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_ready(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("ZenCloak 本地服务启动超时")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="zencloak", description="ZenCloak 专属指纹浏览器")
    parser.add_argument("--data-dir", type=Path, default=Path.home() / ".zencloak")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument(
        "--headless-ui",
        action="store_true",
        help="只启动本地服务，不打开桌面窗口",
    )
    args = parser.parse_args(argv)

    instance_lock = InstanceLock(args.data_dir / "zencloak.lock")
    if not instance_lock.acquire():
        raise SystemExit("ZenCloak 已在运行")

    store = ProfileStore(args.data_dir, auto_init=True)
    sessions = SessionManager(data_root=store.data_dir)
    app = create_app(store, sessions)
    port = args.port or _free_port()
    url = f"http://127.0.0.1:{port}"

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_until_ready(url)

    try:
        if args.headless_ui:
            print(f"ZenCloak UI: {url}")
            while thread.is_alive():
                time.sleep(1)
        else:
            webview.create_window(
                "ZenCloak",
                url,
                width=1280,
                height=860,
                min_size=(980, 640),
                background_color="#edece6",
            )
            webview.start()
    finally:
        sessions.stop_all()
        server.should_exit = True
        thread.join(timeout=5)
        instance_lock.release()


if __name__ == "__main__":
    main()
