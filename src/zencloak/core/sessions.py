import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable
from urllib.parse import urlsplit

import cloakbrowser.browser as _cloakbrowser_browser
from cloakbrowser import launch_persistent_context

from .extensions import build_newtab_extension, cleanup_stale_newtab_extensions
from .health import PROBE_JS


class SessionError(RuntimeError):
    """Raised when a session cannot be started or controlled."""


_BLANK_URLS = ("about:blank", "chrome://newtab", "chrome://newtab/")
_NEWTAB_EXTENSION_DIR = "newtab-v3"

# Playwright injects Translate into its default --disable-features list,
# which overrides --enable-features=Translate. Ignore that default arg and
# re-supply the same list without Translate so browser translation works.
# Keep this list in sync with the installed Playwright version if it changes.
_PLAYWRIGHT_DEFAULT_DISABLE_FEATURES = (
    "AvoidUnnecessaryBeforeUnloadCheckSync,"
    "BoundaryEventDispatchTracksNodeRemoval,"
    "DestroyProfileOnBrowserClose,"
    "DialMediaRouteProvider,"
    "GlobalMediaControls,"
    "HttpsUpgrades,"
    "LensOverlay,"
    "MediaRouter,"
    "PaintHolding,"
    "ThirdPartyStoragePartitioning,"
    "Translate,"
    "AutoDeElevate,"
    "RenderDocument,"
    "OptimizationHints,"
    "msForceBrowserSignIn,"
    "msEdgeUpdateLaunchServicesPreferredVersion"
)
_DISABLE_FEATURES_WITHOUT_TRANSLATE = _PLAYWRIGHT_DEFAULT_DISABLE_FEATURES.replace(
    ",Translate", ""
)

if (
    f"--disable-features={_PLAYWRIGHT_DEFAULT_DISABLE_FEATURES}"
    not in _cloakbrowser_browser.IGNORE_DEFAULT_ARGS
):
    _cloakbrowser_browser.IGNORE_DEFAULT_ARGS = [
        *_cloakbrowser_browser.IGNORE_DEFAULT_ARGS,
        f"--disable-features={_PLAYWRIGHT_DEFAULT_DISABLE_FEATURES}",
    ]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionManager:
    """Owns CloakBrowser sessions, one persistent context per profile."""

    def __init__(
        self,
        data_root: str | Path,
        launcher: Callable[..., Any] = launch_persistent_context,
        proxy_manager: Any = None,
    ) -> None:
        self.data_root = Path(data_root)
        self._launcher = launcher
        self._proxy_manager = proxy_manager
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def launch(self, profile: dict) -> dict:
        profile_id = profile["id"]
        with self._lock:
            existing = self._sessions.get(profile_id)
            if existing and existing["status"] in {"launching", "running", "stopping"}:
                raise SessionError(f"档案 {profile['name']} 已在运行")
            session = {
                "profile_id": profile_id,
                "status": "launching",
                "started_at": _now_iso(),
                "stopped_at": None,
                "error": None,
                "stop_event": threading.Event(),
                "urls": Queue(),
                "context": None,
                "thread": None,
            }
            self._sessions[profile_id] = session
        thread = threading.Thread(
            target=self._run_session, args=(profile, session), daemon=True
        )
        session["thread"] = thread
        thread.start()
        return {
            "profile_id": profile_id,
            "status": "launching",
            "started_at": session["started_at"],
            "stopped_at": None,
            "error": None,
        }

    def open_url(self, profile_id: str, url: str) -> dict:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            raise SessionError("仅支持 http/https URL")
        with self._lock:
            session = self._sessions.get(profile_id)
            if not session or session["status"] not in {"launching", "running"}:
                raise SessionError("档案未运行")
            item = {"url": url, "event": threading.Event(), "opened": False}
            session["urls"].put(item)
        item["event"].wait(timeout=15)
        result = self.status(profile_id)
        if isinstance(result, dict):
            result = {**result, "opened": item["opened"]}
        return result

    def run_probe(self, profile_id: str, timeout: float = 30.0) -> dict:
        """Run the fingerprint probe inside the profile's browser.

        Playwright sync objects must be used from the thread that created
        them, so the probe is queued and executed by the session loop.
        """
        with self._lock:
            session = self._sessions.get(profile_id)
            if not session or session["status"] not in {"launching", "running"}:
                raise SessionError("档案未运行")
            item = {"kind": "probe", "event": threading.Event(), "result": None}
            session["urls"].put(item)
        if not item["event"].wait(timeout):
            raise SessionError("指纹探测超时")
        result = item["result"]
        if isinstance(result, Exception):
            raise SessionError(f"指纹探测失败: {result}")
        return result

    def run_page_op(
        self,
        profile_id: str,
        op: str,
        index: int | None = None,
        max_chars: int | None = None,
        path: str | None = None,
        timeout: float = 30.0,
    ) -> dict:
        """Run a page operation (list/read/screenshot) in the session thread.

        Same threading constraint as run_probe: the session loop owns the
        Playwright context, so operations go through the work queue.
        """
        if op not in {"list", "read", "screenshot"}:
            raise SessionError(f"未知页面操作: {op}")
        with self._lock:
            session = self._sessions.get(profile_id)
            if not session or session["status"] not in {"launching", "running"}:
                raise SessionError("档案未运行")
            item = {
                "kind": "page_op",
                "op": op,
                "index": index,
                "max_chars": max_chars,
                "path": path,
                "event": threading.Event(),
                "result": None,
            }
            session["urls"].put(item)
        if not item["event"].wait(timeout):
            raise SessionError("页面操作超时")
        result = item["result"]
        if isinstance(result, Exception):
            raise SessionError(f"页面操作失败: {result}")
        return result

    def _run_session(self, profile: dict, session: dict[str, Any]) -> None:
        try:
            proxy_server = self._start_proxy(profile)
            context = self._launcher(
                **self._build_launch_kwargs(profile, proxy_server)
            )
            with self._lock:
                session["context"] = context
                session["status"] = "running"
                session["error"] = None
            self._prepare_start_page(context, profile)
            self._open_urls_from_queue(context, session)
            while not session["stop_event"].is_set():
                if not context.browser.is_connected():
                    break
                self._redirect_broken_new_tabs(context)
                self._open_urls_from_queue(context, session)
                time.sleep(0.3)
            self._close_safely(context)
            with self._lock:
                session["status"] = "stopped"
                session["stopped_at"] = _now_iso()
        except Exception as exc:  # noqa: BLE001 - surface any launcher failure to UI
            with self._lock:
                session["status"] = "error"
                session["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            self._stop_proxy(profile["id"])

    def _open_urls_from_queue(self, context: Any, session: dict[str, Any]) -> None:
        while True:
            try:
                item = session["urls"].get_nowait()
            except Empty:
                return
            if item.get("kind") == "probe":
                item["result"] = self._execute_probe(context)
            elif item.get("kind") == "page_op":
                item["result"] = self._execute_page_op(context, item)
            else:
                item["opened"] = self._open_page(context, item["url"])
            item["event"].set()

    def _prepare_start_page(self, context: Any, profile: dict) -> None:
        start_url = profile.get("start_url")
        try:
            pages = list(context.pages)
            blank_pages = [p for p in pages if p.url in _BLANK_URLS]
            if start_url:
                if len(pages) == 1 and blank_pages:
                    blank_pages[0].goto(start_url, timeout=60000)
                else:
                    self._open_page(context, start_url)
                    for blank in blank_pages:
                        if len(context.pages) > 1:
                            blank.close()
            else:
                for blank in blank_pages[1:]:
                    if len(context.pages) > 1:
                        blank.close()
        except Exception:  # noqa: BLE001 - never let page setup kill the session
            if start_url:
                try:
                    if not any(p.url == start_url for p in context.pages):
                        self._open_page(context, start_url)
                except Exception:  # noqa: BLE001 - best effort fallback
                    pass

    def stop(self, profile_id: str) -> dict:
        with self._lock:
            session = self._sessions.get(profile_id)
            if not session or session["status"] not in {"launching", "running"}:
                return self.status(profile_id)
            session["stop_event"].set()
            session["status"] = "stopping"
        return self.status(profile_id)

    def stop_all(self, wait: bool = True) -> None:
        with self._lock:
            profile_ids = list(self._sessions)
        for profile_id in profile_ids:
            self.stop(profile_id)
        if wait:
            with self._lock:
                threads = [
                    s["thread"]
                    for s in self._sessions.values()
                    if s.get("thread") is not None
                ]
            for thread in threads:
                thread.join(timeout=5)

    def status(self, profile_id: str | None = None) -> dict | list[dict]:
        with self._lock:
            if profile_id is not None:
                session = self._sessions.get(profile_id)
                return self._snapshot(session, profile_id)
            return [self._snapshot(s, s["profile_id"]) for s in self._sessions.values()]

    def _snapshot(self, session: dict[str, Any] | None, profile_id: str) -> dict:
        if session is None:
            return {
                "profile_id": profile_id,
                "status": "stopped",
                "started_at": None,
                "stopped_at": None,
                "error": None,
            }
        return {
            "profile_id": profile_id,
            "status": session["status"],
            "started_at": session["started_at"],
            "stopped_at": session["stopped_at"],
            "error": session["error"],
        }

    def _build_launch_kwargs(
        self, profile: dict, proxy_server: str | None = None
    ) -> dict:
        args = [
            f"--fingerprint={profile['seed']}",
            f"--fingerprint-screen-width={profile['screen_width']}",
            f"--fingerprint-screen-height={profile['screen_height']}",
            f"--lang={profile['locale']}",
            f"--fingerprint-locale={profile['locale']}",
            f"--disable-features={_DISABLE_FEATURES_WITHOUT_TRANSLATE}",
            "--enable-features=Translate",
        ]
        if profile.get("user_agent"):
            args.append(f"--user-agent={profile['user_agent']}")
        kwargs: dict[str, Any] = {
            "user_data_dir": str(self.data_root / profile["id"]),
            "headless": False,
            "args": args,
            "timezone": profile["timezone"],
            "humanize": profile["humanize"],
            "human_preset": profile["human_preset"],
            "accept_downloads": True,
        }
        downloads_dir = self.data_root / profile["id"] / "Downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        kwargs["downloads_path"] = str(downloads_dir)
        cleanup_stale_newtab_extensions(
            profile, self.data_root, keep_dir=_NEWTAB_EXTENSION_DIR
        )
        ext_dir = build_newtab_extension(
            profile, self.data_root, dir_name=_NEWTAB_EXTENSION_DIR
        )
        kwargs["extension_paths"] = [str(ext_dir)]
        proxy = profile.get("proxy")
        if proxy_server:
            kwargs["proxy"] = {"server": proxy_server}
        elif proxy:
            proxy_dict = {
                "server": f"{proxy['type']}://{proxy['host']}:{proxy['port']}"
            }
            if proxy.get("username"):
                proxy_dict["username"] = proxy["username"]
                proxy_dict["password"] = proxy.get("password", "")
            kwargs["proxy"] = proxy_dict
        else:
            # Without this Chromium would silently inherit the Windows
            # system proxy; profiles with no built-in proxy must go direct.
            args.append("--no-proxy-server")
        return kwargs

    def _start_proxy(self, profile: dict) -> str | None:
        if not profile.get("proxy_enabled") or profile.get("proxy_mode") != "mihomo":
            return None
        if self._proxy_manager is None:
            raise SessionError("内置代理未启用")
        sub_id = profile.get("proxy_subscription_id")
        if not sub_id:
            raise SessionError("请先为档案选择代理订阅")
        nodes = self._proxy_manager.load_nodes(sub_id)
        handle = self._proxy_manager.start(
            profile["id"],
            nodes,
            profile.get("proxy_node"),
        )
        return f"socks5://127.0.0.1:{handle.mixed_port}"

    def _stop_proxy(self, profile_id: str) -> None:
        if self._proxy_manager is None:
            return
        try:
            self._proxy_manager.stop(profile_id)
        except Exception:  # noqa: BLE001 - cleanup must never break session stop
            pass

    @staticmethod
    def _is_broken_new_tab(url: str) -> bool:
        """URLs that should never sit in a visible tab.

        Covers the built-in NTP, the third-party NTP host page (which can
        hang on "加载中…" when the override fails to render), and our own
        newtab.html when the extension page itself fails to load.
        """
        return (
            url.startswith("chrome://new-tab-page")
            or url.startswith("chrome://newtab")
            or (
                url.startswith("chrome-extension://")
                and url.endswith("/newtab.html")
            )
        )

    def _redirect_broken_new_tabs(self, context: Any) -> None:
        """Repair new-tab pages that spin instead of loading."""
        target = "about:blank"
        try:
            for page in list(context.pages):
                try:
                    if self._is_broken_new_tab(page.url):
                        page.goto(target, timeout=8000)
                except Exception:  # noqa: BLE001 - keep sweeping other pages
                    pass
        except Exception:  # noqa: BLE001 - context may be closing
            pass

    def _open_page(self, context: Any, url: str) -> bool:
        try:
            context.new_page().goto(url, timeout=60000)
            return True
        except Exception:  # noqa: BLE001 - a dead page should not kill session
            return False

    def _execute_probe(self, context: Any) -> Any:
        try:
            page = context.new_page()
        except Exception as exc:  # noqa: BLE001 - surfaced to run_probe caller
            return exc
        try:
            return page.evaluate(PROBE_JS)
        except Exception as exc:  # noqa: BLE001 - surfaced to run_probe caller
            return exc
        finally:
            try:
                page.close()
            except Exception:  # noqa: BLE001 - page may already be gone
                pass

    def _execute_page_op(self, context: Any, item: dict[str, Any]) -> Any:
        op = item["op"]
        try:
            pages = list(context.pages)
            if op == "list":
                return [
                    {"index": position, "url": page.url, "title": page.title()}
                    for position, page in enumerate(pages)
                ]
            index = item["index"]
            if index is None or index < 0 or index >= len(pages):
                raise SessionError(f"页面不存在（共 {len(pages)} 个，索引 {index}）")
            page = pages[index]
            if op == "read":
                text = page.inner_text("body", timeout=10000)
                limit = item["max_chars"] or 12000
                return {
                    "url": page.url,
                    "title": page.title(),
                    "text": text[:limit],
                }
            # op == "screenshot"
            if not item["path"]:
                raise SessionError("缺少截图保存路径")
            page.screenshot(path=item["path"], full_page=False)
            return {"path": item["path"]}
        except Exception as exc:  # noqa: BLE001 - surfaced to run_page_op caller
            return exc

    def _close_safely(self, context: Any) -> None:
        try:
            context.close()
        except Exception:  # noqa: BLE001 - already closed by user or crash
            pass
