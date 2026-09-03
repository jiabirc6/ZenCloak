import argparse
import ctypes
import json
import os
import secrets
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

import uvicorn
import webview

from zencloak.api import create_app
from zencloak.core.lock import InstanceLock
from zencloak.core.mihomo import ProxyManager
from zencloak.core.profiles import ProfileStore
from zencloak.core.sessions import SessionManager


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _bundled_engine_dir() -> Path | None:
    """Return the packaged engine dir when the installer bundled a kernel.

    The personal build ships ``<exe dir>/engine/chromium-<version>/``;
    pointing CLOAKBROWSER_CACHE_DIR there makes cloakbrowser use it instead
    of downloading to ~/.cloakbrowser.
    """
    if not getattr(sys, "frozen", False):
        return None
    engine = Path(sys.executable).resolve().parent / "engine"
    if engine.is_dir() and any(engine.glob("chromium-*")):
        return engine
    return None


def _install_engine() -> None:
    """Download the CloakBrowser kernel (public installer post-install step)."""
    from cloakbrowser.download import ensure_binary

    try:
        path = ensure_binary()
    except Exception as exc:  # noqa: BLE001 - surface failure to installer log
        raise SystemExit(f"内核下载失败: {exc}") from exc
    raise SystemExit(0)


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


def _runtime_info_path(data_dir: Path) -> Path:
    return data_dir / "runtime" / "api.json"


def write_runtime_info(data_dir: Path, url: str, api_token: str) -> Path:
    """Publish base URL + token so the MCP server process can discover them."""
    info_path = _runtime_info_path(data_dir)
    info_path.parent.mkdir(parents=True, exist_ok=True)
    info_path.write_text(
        json.dumps({"base_url": url, "token": api_token}),
        encoding="utf-8",
    )
    return info_path


def _show_already_running() -> None:
    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            "ZenCloak 已在运行，请先关闭旧窗口再启动。",
            "ZenCloak",
            0x40,
        )
    except Exception:
        pass


def _build_tray(window, sessions, server, proxy_manager=None):
    """Create a system-tray icon whose Exit item fully terminates ZenCloak."""
    try:
        import pystray
        from PIL import Image
    except Exception:
        return None

    def _quit() -> None:
        def _force_exit() -> None:
            time.sleep(0.5)
            os._exit(0)

        threading.Thread(target=_force_exit, daemon=True).start()
        try:
            sessions.stop_all(wait=False)
        except Exception:
            pass
        # os._exit skips the session threads' finally blocks, so mihomo
        # children must be reaped synchronously here or they leak.
        if proxy_manager is not None:
            try:
                proxy_manager.stop_all()
            except Exception:
                pass
        try:
            server.should_exit = True
        except Exception:
            pass
        os._exit(0)

    def _show_window() -> None:
        try:
            window.show()
        except Exception:
            pass

    icon_path = Path(__file__).parent / "ui" / "assets" / "zencloak-icon.png"
    try:
        image = Image.open(icon_path)
    except Exception:
        image = Image.new("RGB", (64, 64), "#0f766e")
    menu = pystray.Menu(
        pystray.MenuItem("显示 ZenCloak", lambda: _show_window()),
        pystray.MenuItem("退出 ZenCloak", lambda: _quit()),
    )
    return pystray.Icon("zencloak", image, "ZenCloak", menu)


class ApiBridge:
    """Expose the local API token to the pywebview frontend only."""

    def __init__(self, api_token: str) -> None:
        self._api_token = api_token

    def get_api_token(self) -> str:
        return self._api_token

    def getApiToken(self) -> str:
        return self._api_token


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="zencloak", description="ZenCloak 专属指纹浏览器")
    parser.add_argument("--data-dir", type=Path, default=Path.home() / ".zencloak")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument(
        "--api-token",
        type=str,
        default=None,
        help="本地 API 访问令牌，默认每次启动随机生成",
    )
    parser.add_argument(
        "--headless-ui",
        action="store_true",
        help="只启动本地服务，不打开桌面窗口",
    )
    parser.add_argument(
        "--install-engine",
        action="store_true",
        help="下载 CloakBrowser 内核后退出（安装程序后置步骤）",
    )
    args = parser.parse_args(argv)

    if args.install_engine:
        _install_engine()

    engine_dir = _bundled_engine_dir()
    if engine_dir:
        os.environ.setdefault("CLOAKBROWSER_CACHE_DIR", str(engine_dir))

    instance_lock = InstanceLock(args.data_dir / "zencloak.lock")
    if not instance_lock.acquire():
        _show_already_running()
        raise SystemExit("ZenCloak 已在运行")

    store = ProfileStore(args.data_dir, auto_init=True)
    proxy_manager = ProxyManager(data_root=store.data_dir / "proxy")
    try:
        proxy_manager.sweep_orphans()
    except Exception:
        pass
    sessions = SessionManager(
        data_root=store.data_dir,
        proxy_manager=proxy_manager,
    )
    api_token = args.api_token or secrets.token_urlsafe(32)
    app = create_app(
        store,
        sessions,
        api_token=api_token,
        proxy_manager=proxy_manager,
    )
    port = args.port or _free_port()
    url = f"http://127.0.0.1:{port}"

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_until_ready(url)
    runtime_info = write_runtime_info(args.data_dir, url, api_token)

    try:
        if args.headless_ui:
            print(f"ZenCloak UI: {url}")
            print(f"API token: {api_token}")
            while thread.is_alive():
                time.sleep(1)
        else:
            window = webview.create_window(
                "ZenCloak",
                url,
                width=1280,
                height=860,
                min_size=(980, 640),
                background_color="#edece6",
                js_api=ApiBridge(api_token),
            )

            tray = _build_tray(window, sessions, server, proxy_manager)
            if tray is not None:
                tray.run_detached()

            def _hide_to_tray() -> bool:
                try:
                    window.hide()
                except Exception:
                    pass
                return False

            # Closing the window hides it to the tray; use the tray Exit item
            # to fully stop ZenCloak and release the instance lock.
            window.events.closing += _hide_to_tray
            webview.start()
    finally:
        sessions.stop_all()
        server.should_exit = True
        thread.join(timeout=5)
        try:
            runtime_info.unlink(missing_ok=True)
        except Exception:
            pass
        instance_lock.release()


if __name__ == "__main__":
    main()
