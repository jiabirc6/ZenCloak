import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable

from cloakbrowser import launch_persistent_context

from .extensions import build_newtab_extension


class SessionError(RuntimeError):
    """Raised when a session cannot be started or controlled."""


_BLANK_URLS = ("about:blank", "chrome://newtab", "chrome://newtab/")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionManager:
    """Owns CloakBrowser sessions, one persistent context per profile."""

    def __init__(
        self,
        data_root: str | Path,
        launcher: Callable[..., Any] = launch_persistent_context,
    ) -> None:
        self.data_root = Path(data_root)
        self._launcher = launcher
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
        with self._lock:
            session = self._sessions.get(profile_id)
            if not session or session["status"] not in {"launching", "running"}:
                raise SessionError("档案未运行")
            session["urls"].put(url)
        return self.status(profile_id)

    def _run_session(self, profile: dict, session: dict[str, Any]) -> None:
        try:
            context = self._launcher(**self._build_launch_kwargs(profile))
            with self._lock:
                session["context"] = context
                session["status"] = "running"
                session["error"] = None
            self._prepare_start_page(context, profile)
            self._open_urls_from_queue(context, session)
            while not session["stop_event"].is_set():
                if not context.browser.is_connected():
                    break
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

    def _open_urls_from_queue(self, context: Any, session: dict[str, Any]) -> None:
        while True:
            try:
                url = session["urls"].get_nowait()
            except Empty:
                return
            self._open_page(context, url)

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

    def stop_all(self) -> None:
        with self._lock:
            profile_ids = list(self._sessions)
        for profile_id in profile_ids:
            self.stop(profile_id)

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

    def _build_launch_kwargs(self, profile: dict) -> dict:
        args = [
            f"--fingerprint={profile['seed']}",
            f"--fingerprint-screen-width={profile['screen_width']}",
            f"--fingerprint-screen-height={profile['screen_height']}",
        ]
        if profile.get("user_agent"):
            args.append(f"--user-agent={profile['user_agent']}")
        kwargs: dict[str, Any] = {
            "user_data_dir": str(self.data_root / profile["id"]),
            "headless": False,
            "args": args,
            "timezone": profile["timezone"],
            "locale": profile["locale"],
            "humanize": profile["humanize"],
            "human_preset": profile["human_preset"],
        }
        if profile.get("start_url"):
            ext_dir = build_newtab_extension(
                profile,
                self.data_root,
                dir_name=f"newtab-{uuid.uuid4().hex[:10]}",
            )
            kwargs["extension_paths"] = [str(ext_dir)]
        proxy = profile.get("proxy")
        if proxy:
            proxy_dict = {
                "server": f"{proxy['type']}://{proxy['host']}:{proxy['port']}"
            }
            if proxy.get("username"):
                proxy_dict["username"] = proxy["username"]
                proxy_dict["password"] = proxy.get("password", "")
            kwargs["proxy"] = proxy_dict
        return kwargs

    def _open_page(self, context: Any, url: str) -> None:
        try:
            context.new_page().goto(url, timeout=60000)
        except Exception:  # noqa: BLE001 - a dead page should not kill session
            pass

    def _close_safely(self, context: Any) -> None:
        try:
            context.close()
        except Exception:  # noqa: BLE001 - already closed by user or crash
            pass
