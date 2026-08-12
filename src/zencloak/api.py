from pathlib import Path
from typing import Any

from cloakbrowser.config import get_binary_path, get_effective_version
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from zencloak.core.fingerprint import default_profile_draft
from zencloak.core.models import normalize_start_url
from zencloak.core.profiles import ProfileStore
from zencloak.core.sessions import SessionError, SessionManager

UI_DIR = Path(__file__).parent / "ui"


def create_app(store: ProfileStore, sessions: SessionManager) -> FastAPI:
    app = FastAPI(title="ZenCloak", version="0.1.0")
    app.state.store = store
    app.state.sessions = sessions

    def profile_or_404(profile_id: str) -> dict:
        try:
            profile = store.get_profile(profile_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if profile is None:
            raise HTTPException(status_code=404, detail="档案不存在")
        return profile

    @app.get("/favicon.ico")
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/profiles")
    def list_profiles() -> list[dict]:
        return store.list_profiles()

    @app.post("/api/profiles")
    def create_profile(payload: dict[str, Any]) -> dict:
        try:
            return store.create_profile({**default_profile_draft(), **payload})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/profiles/{profile_id}")
    def get_profile(profile_id: str) -> dict:
        return profile_or_404(profile_id)

    @app.put("/api/profiles/{profile_id}")
    def update_profile(profile_id: str, payload: dict[str, Any]) -> dict:
        profile_or_404(profile_id)
        try:
            updated = store.update_profile(profile_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if updated is None:
            raise HTTPException(status_code=404, detail="档案不存在")
        return updated

    @app.delete("/api/profiles/{profile_id}")
    def delete_profile(profile_id: str) -> Response:
        try:
            deleted = store.delete_profile(profile_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail="档案不存在")
        return Response(status_code=204)

    @app.get("/api/sessions")
    def list_sessions() -> list[dict]:
        statuses = {
            item["profile_id"]: item
            for item in sessions.status()
            if isinstance(item, dict)
        }
        return [
            statuses.get(
                profile["id"],
                {
                    "profile_id": profile["id"],
                    "status": "stopped",
                    "started_at": None,
                    "stopped_at": None,
                    "error": None,
                },
            )
            for profile in store.list_profiles()
        ]

    @app.post("/api/sessions/{profile_id}/launch")
    def launch_session(profile_id: str) -> dict:
        profile = profile_or_404(profile_id)
        try:
            return sessions.launch(profile)
        except SessionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/sessions/{profile_id}/stop")
    def stop_session(profile_id: str) -> dict:
        profile_or_404(profile_id)
        return sessions.stop(profile_id)

    @app.post("/api/sessions/{profile_id}/open")
    def open_session_url(profile_id: str, payload: dict[str, Any]) -> dict:
        profile_or_404(profile_id)
        url = payload.get("url")
        if not isinstance(url, str) or not url.strip():
            raise HTTPException(status_code=400, detail="url 不能为空")
        try:
            normalized = normalize_start_url(url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if normalized is None:
            raise HTTPException(status_code=400, detail="url 不能为空")
        try:
            return sessions.open_url(profile_id, normalized)
        except SessionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/engine")
    def engine_status() -> dict:
        return _engine_info()

    if (UI_DIR / "index.html").exists():
        app.mount("/", StaticFiles(directory=UI_DIR, html=True), name="ui")
    return app


def _engine_info() -> dict:
    try:
        version = get_effective_version()
        binary = get_binary_path(version)
        if binary.exists():
            return {"available": True, "version": version, "binary": str(binary)}
        return {
            "available": False,
            "version": version,
            "binary": None,
            "error": "CloakBrowser 二进制尚未下载",
        }
    except Exception as exc:  # noqa: BLE001 - engine status should never crash API
        return {
            "available": False,
            "version": None,
            "binary": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
