import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from .core.fingerprint import default_profile_draft
from .core.profiles import ProfileStore
from .core.sessions import SessionError, SessionManager

UI_DIR = Path(__file__).parent / "ui"


def create_app(store: ProfileStore, sessions: SessionManager) -> FastAPI:
    app = FastAPI(title="ZenCloak", version="0.1.0")
    app.state.store = store
    app.state.sessions = sessions

    def profile_or_404(profile_id: str) -> dict:
        profile = store.get_profile(profile_id)
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
        if not store.delete_profile(profile_id):
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
            return sessions.open_url(profile_id, url.strip())
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
        result = subprocess.run(
            [sys.executable, "-m", "cloakbrowser", "info"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return {
                "available": False,
                "version": None,
                "binary": None,
                "error": result.stderr.strip() or result.stdout.strip(),
            }
        version = ""
        binary = ""
        for line in result.stdout.splitlines():
            if line.lower().startswith("version:"):
                version = line.split(":", 1)[1].strip()
            if line.lower().startswith("binary:"):
                binary = line.split(":", 1)[1].strip()
        return {"available": True, "version": version, "binary": binary}
    except Exception as exc:  # noqa: BLE001 - engine status should never crash API
        return {
            "available": False,
            "version": None,
            "binary": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
