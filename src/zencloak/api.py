import os
import socket
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from cloakbrowser.config import get_binary_path, get_effective_version
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from zencloak.core.consistency import ConsistencyError, check_consistency, lookup_ip_geo
from zencloak.core.fingerprint import default_profile_draft
from zencloak.core.health import build_report
from zencloak.core.mihomo import MihomoError, ProxyManager
from zencloak.core.models import normalize_start_url
from zencloak.core.profiles import ProfileStore
from zencloak.core.sessions import SessionError, SessionManager
from zencloak.core.subscriptions import (
    delete_subscription,
    get_subscription,
    import_subscription,
    list_subscriptions,
    load_nodes,
    refresh_subscription,
)

UI_DIR = Path(__file__).parent / "ui"


def create_app(
    store: ProfileStore,
    sessions: SessionManager,
    api_token: str | None = None,
    proxy_manager: ProxyManager | None = None,
) -> FastAPI:
    app = FastAPI(title="ZenCloak", version="0.2.0")
    app.state.store = store
    app.state.sessions = sessions
    app.state.proxy_manager = proxy_manager

    def proxy_root() -> Path:
        return store.data_dir / "proxy"

    def require_proxy_manager() -> ProxyManager:
        if proxy_manager is None:
            raise HTTPException(status_code=503, detail="内置代理未启用")
        return proxy_manager

    @app.middleware("http")
    async def require_api_token(request: Request, call_next):
        if api_token is None:
            return await call_next(request)
        if not request.url.path.startswith("/api/") or request.method == "OPTIONS":
            return await call_next(request)
        if request.url.path == "/api/health":
            return await call_next(request)
        if request.headers.get("authorization") != f"Bearer {api_token}":
            return JSONResponse(status_code=401, content={"detail": "未授权"})
        return await call_next(request)

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

    @app.post("/api/profiles/import")
    def import_profile(payload: dict[str, Any]) -> dict:
        try:
            return store.create_profile(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/profiles/{profile_id}")
    def get_profile(profile_id: str) -> dict:
        return profile_or_404(profile_id)

    @app.get("/api/profiles/{profile_id}/export")
    def export_profile(profile_id: str) -> dict:
        return profile_or_404(profile_id)

    @app.post("/api/profiles/{profile_id}/duplicate")
    def duplicate_profile(profile_id: str) -> dict:
        profile_or_404(profile_id)
        try:
            duplicated = store.duplicate_profile(profile_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if duplicated is None:
            raise HTTPException(status_code=404, detail="档案不存在")
        return duplicated

    @app.post("/api/profiles/{profile_id}/open-downloads")
    def open_profile_downloads(profile_id: str) -> dict:
        profile_or_404(profile_id)
        downloads_dir = store.data_dir / profile_id / "Downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(downloads_dir))
        except Exception as exc:  # noqa: BLE001 - surface OS errors to the UI
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"opened": True, "path": str(downloads_dir)}

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

    @app.get("/api/recycle-bin")
    def list_recycle_bin() -> list[dict]:
        return store.list_recycle_bin()

    @app.post("/api/recycle-bin/{profile_id}/restore")
    def restore_profile(profile_id: str) -> dict:
        try:
            restored = store.restore_profile(profile_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if restored is None:
            raise HTTPException(status_code=404, detail="回收站中没有该档案")
        return restored

    @app.delete("/api/recycle-bin/{profile_id}")
    def permanent_delete_profile(profile_id: str) -> Response:
        try:
            deleted = store.permanent_delete_profile(profile_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail="回收站中没有该档案")
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

    @app.post("/api/sessions/batch-launch")
    def batch_launch(payload: dict[str, Any]) -> list[dict]:
        results: list[dict] = []
        for profile_id in payload.get("ids") or []:
            try:
                profile = profile_or_404(profile_id)
                results.append(
                    {"profile_id": profile_id, "ok": True, **sessions.launch(profile)}
                )
            except HTTPException as exc:
                results.append(
                    {"profile_id": profile_id, "ok": False, "error": str(exc.detail)}
                )
            except SessionError as exc:
                results.append({"profile_id": profile_id, "ok": False, "error": str(exc)})
        return results

    @app.post("/api/sessions/batch-stop")
    def batch_stop(payload: dict[str, Any]) -> list[dict]:
        results: list[dict] = []
        for profile_id in payload.get("ids") or []:
            try:
                profile_or_404(profile_id)
                results.append(
                    {"profile_id": profile_id, "ok": True, **sessions.stop(profile_id)}
                )
            except HTTPException as exc:
                results.append(
                    {"profile_id": profile_id, "ok": False, "error": str(exc.detail)}
                )
            except SessionError as exc:
                results.append({"profile_id": profile_id, "ok": False, "error": str(exc)})
        return results

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

    @app.post("/api/proxy/subscriptions/import")
    def proxy_import_subscription(payload: dict[str, Any]) -> dict:
        source = payload.get("source")
        url = payload.get("url")
        if url:
            source = _fetch_text(str(url))
        if not isinstance(source, str) or not source.strip():
            raise HTTPException(status_code=400, detail="订阅内容不能为空")
        try:
            return import_subscription(
                source,
                proxy_root(),
                name=payload.get("name"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/proxy/subscriptions")
    def proxy_list_subscriptions() -> list[dict]:
        return list_subscriptions(proxy_root())

    @app.get("/api/proxy/subscriptions/{sub_id}/nodes")
    def proxy_subscription_nodes(sub_id: str) -> list[dict]:
        meta = get_subscription(proxy_root(), sub_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="订阅不存在")
        return meta["nodes"]

    @app.post("/api/proxy/subscriptions/{sub_id}/refresh")
    def proxy_refresh_subscription(sub_id: str) -> dict:
        try:
            return refresh_subscription(proxy_root(), sub_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - network failures surface to UI
            raise HTTPException(status_code=502, detail=f"刷新失败: {exc}") from exc

    @app.delete("/api/proxy/subscriptions/{sub_id}")
    def proxy_delete_subscription(sub_id: str) -> dict:
        if get_subscription(proxy_root(), sub_id) is None:
            raise HTTPException(status_code=404, detail="订阅不存在")
        users = [
            profile["name"]
            for profile in store.list_profiles()
            if profile.get("proxy_subscription_id") == sub_id
        ]
        if users:
            raise HTTPException(
                status_code=409,
                detail=f"该订阅正被 {len(users)} 个档案使用：{'、'.join(users)}",
            )
        delete_subscription(proxy_root(), sub_id)
        return {"ok": True}

    @app.post("/api/proxy/nodes/test")
    def proxy_test_node(payload: dict[str, Any]) -> dict:
        sub_id = payload.get("subscription_id")
        node_name = payload.get("node")
        if not sub_id or not node_name:
            raise HTTPException(status_code=400, detail="缺少订阅或节点")
        nodes = load_nodes(proxy_root(), sub_id)
        node = next((item for item in nodes if item.get("name") == node_name), None)
        if node is None:
            raise HTTPException(status_code=404, detail="节点不存在")
        server = node.get("server")
        port = node.get("port")
        if not server or not port:
            raise HTTPException(status_code=400, detail="节点缺少 server/port")
        started = time.perf_counter()
        try:
            with socket.create_connection((server, int(port)), timeout=6):
                latency_ms = round((time.perf_counter() - started) * 1000, 1)
        except OSError as exc:
            raise HTTPException(status_code=502, detail=f"节点连接失败: {exc}") from exc
        return {"node": node_name, "latency_ms": latency_ms}

    @app.get("/api/sessions/{profile_id}/proxy/status")
    def session_proxy_status(profile_id: str) -> dict:
        manager = require_proxy_manager()
        status = manager.status(profile_id)
        if status.get("status") == "running":
            try:
                status["exit_ip"] = manager.detect_exit_ip(profile_id)
            except Exception:  # noqa: BLE001 - exit IP is best effort
                status["exit_ip"] = None
        return status

    def _consistency_report(profile: dict) -> dict:
        """Resolve the egress geo through the profile's proxy and compare."""
        if not profile.get("proxy_enabled"):
            return {"checked": False, "reason": "未启用代理"}
        if profile.get("proxy_mode") == "mihomo":
            if proxy_manager is None:
                raise HTTPException(status_code=503, detail="内置代理未启用")
            status = proxy_manager.status(profile["id"])
            if status.get("status") != "running":
                return {"checked": False, "reason": "代理未运行"}
            proxy_url = f"http://127.0.0.1:{status['mixed_port']}"
        else:
            manual = profile.get("proxy") or {}
            if manual.get("type") != "http":
                return {"checked": False, "reason": "SOCKS5 手动代理暂不支持自动检测"}
            auth = ""
            if manual.get("username"):
                auth = f"{manual['username']}:{manual.get('password', '')}@"
            proxy_url = f"http://{auth}{manual['host']}:{manual['port']}"
        try:
            geo = lookup_ip_geo(proxy_url)
        except ConsistencyError as exc:
            return {"checked": False, "reason": str(exc)}
        return {
            "checked": True,
            "ip": geo.get("ip"),
            "country": geo.get("country"),
            "city": geo.get("city"),
            "ip_timezone": geo.get("timezone"),
            "profile_timezone": profile.get("timezone"),
            "warnings": check_consistency(profile, geo),
        }

    @app.get("/api/sessions/{profile_id}/consistency")
    def session_consistency(profile_id: str) -> dict:
        profile = profile_or_404(profile_id)
        return _consistency_report(profile)

    @app.post("/api/sessions/{profile_id}/apply-ip-timezone")
    def session_apply_ip_timezone(profile_id: str) -> dict:
        profile = profile_or_404(profile_id)
        report = _consistency_report(profile)
        if not report.get("checked"):
            raise HTTPException(
                status_code=409, detail=report.get("reason") or "无法检测出口 IP"
            )
        suggested = next(
            (
                w.get("suggested_timezone")
                for w in report.get("warnings", [])
                if w.get("kind") == "timezone"
            ),
            None,
        )
        if not suggested:
            raise HTTPException(status_code=409, detail="时区已一致，无需修改")
        updated = store.update_profile(profile_id, {"timezone": suggested})
        if updated is None:
            raise HTTPException(status_code=404, detail="档案不存在")
        return {"ok": True, "timezone": suggested, "profile": updated}

    def _geo_for_health(profile: dict) -> dict | None:
        """Egress geo for the health report; None when it cannot be resolved."""
        if profile.get("proxy_enabled"):
            report = _consistency_report(profile)
            if not report.get("checked"):
                return None
            return {
                "ip": report.get("ip"),
                "country": report.get("country"),
                "timezone": report.get("ip_timezone"),
            }
        try:
            return lookup_ip_geo(None)
        except ConsistencyError:
            return None

    @app.post("/api/sessions/{profile_id}/health-check")
    def session_health_check(profile_id: str) -> dict:
        profile = profile_or_404(profile_id)
        try:
            signals = sessions.run_probe(profile_id)
        except SessionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return build_report(signals, profile, _geo_for_health(profile))

    def _page_op_or_409(profile_id: str, **kwargs) -> Any:
        try:
            return sessions.run_page_op(profile_id, **kwargs)
        except SessionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/sessions/{profile_id}/pages")
    def session_pages(profile_id: str) -> list[dict]:
        return _page_op_or_409(profile_id, op="list")

    @app.get("/api/sessions/{profile_id}/pages/{index}/content")
    def session_page_content(
        profile_id: str, index: int, max_chars: int = 12000
    ) -> dict:
        return _page_op_or_409(
            profile_id, op="read", index=index, max_chars=max_chars
        )

    @app.post("/api/sessions/{profile_id}/pages/{index}/screenshot")
    def session_page_screenshot(profile_id: str, index: int) -> dict:
        shots_dir = (
            sessions.data_root / profile_id / "screenshots"
        )
        shots_dir.mkdir(parents=True, exist_ok=True)
        path = shots_dir / f"{time.strftime('%Y%m%d-%H%M%S')}.png"
        return _page_op_or_409(
            profile_id, op="screenshot", index=index, path=str(path)
        )

    @app.post("/api/shutdown")
    def shutdown() -> dict:
        def _exit_later() -> None:
            time.sleep(0.2)
            os._exit(0)

        threading.Thread(target=_exit_later, daemon=True).start()
        return {"ok": True}

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


def _fetch_text(url: str) -> str:
    proxies: list[str | None] = [None]
    env_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if env_proxy:
        proxies.append(env_proxy)
    else:
        proxies.append("http://127.0.0.1:7890")
    last_error: Exception | None = None
    for proxy in proxies:
        try:
            handlers = (
                [urllib.request.ProxyHandler({"http": proxy, "https": proxy})]
                if proxy
                else []
            )
            opener = urllib.request.build_opener(*handlers)
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 ZenCloak"},
            )
            with opener.open(request, timeout=30) as response:
                return response.read().decode("utf-8")
        except Exception as exc:
            last_error = exc
    raise HTTPException(
        status_code=400,
        detail=f"订阅下载失败: {last_error}",
    ) from last_error
