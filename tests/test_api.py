import pytest
from fastapi.testclient import TestClient

from zencloak.api import create_app
from zencloak.core.fingerprint import default_profile_draft
from zencloak.core.profiles import ProfileStore
from zencloak.core.sessions import SessionError


class FakeSessions:
    def __init__(self):
        self.sessions = {}
        self.opened = []

    def status(self, profile_id=None):
        if profile_id is None:
            return [
                self.status(pid)
                for pid, status in sorted(self.sessions.items())
                if status["status"] != "stopped"
            ]
        return self.sessions.get(
            profile_id,
            {
                "profile_id": profile_id,
                "status": "stopped",
                "started_at": None,
                "stopped_at": None,
                "error": None,
            },
        )

    def launch(self, profile):
        profile_id = profile["id"]
        if self.sessions.get(profile_id, {}).get("status") == "running":
            raise RuntimeError("已在运行")
        self.sessions[profile_id] = {
            "profile_id": profile_id,
            "status": "running",
            "started_at": "2026-01-01T00:00:00+00:00",
            "stopped_at": None,
            "error": None,
        }
        return self.status(profile_id)

    def stop(self, profile_id):
        self.sessions[profile_id] = {
            "profile_id": profile_id,
            "status": "stopped",
            "started_at": None,
            "stopped_at": "2026-01-01T00:00:00+00:00",
            "error": None,
        }
        return self.status(profile_id)

    def open_url(self, profile_id, url):
        if self.sessions.get(profile_id, {}).get("status") != "running":
            raise SessionError("档案未运行")
        self.opened.append((profile_id, url))
        return self.status(profile_id)


@pytest.fixture()
def client(tmp_path):
    store = ProfileStore(tmp_path, auto_init=True)
    sessions = FakeSessions()
    api_client = TestClient(create_app(store, sessions, api_token="test-token"))
    api_client.headers.update({"Authorization": "Bearer test-token"})
    return api_client, store, sessions


def _draft(name="新档案"):
    return {**default_profile_draft(), "name": name}


def test_health(client):
    api_client, _, _ = client
    response = api_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_proxy_subscription_import_and_list(client):
    api_client, _, _ = client
    source = """
proxies:
  - {name: 直连, type: direct}
  - name: 美国节点
    type: vless
    server: 1.2.3.4
    port: 443
"""
    response = api_client.post(
        "/api/proxy/subscriptions/import",
        json={"source": source, "name": "测试订阅"},
    )
    assert response.status_code == 200
    meta = response.json()
    assert meta["name"] == "测试订阅"
    assert meta["nodes"][0]["region"] == "US"
    subs = api_client.get("/api/proxy/subscriptions").json()
    assert any(item["id"] == meta["id"] for item in subs)
    nodes = api_client.get(
        f"/api/proxy/subscriptions/{meta['id']}/nodes"
    ).json()
    assert nodes[0]["name"] == "美国节点"


class FakeProxyManager:
    def status(self, profile_id):
        if profile_id == "aaaaaaaaaaaa":
            return {
                "profile_id": profile_id,
                "status": "running",
                "node": "美国节点",
                "mixed_port": 17891,
                "controller_port": 19091,
                "error": None,
                "started_at": "2026-01-01T00:00:00+00:00",
            }
        return {"profile_id": profile_id, "status": "stopped"}

    def detect_exit_ip(self, profile_id):
        return "1.2.3.4"


def test_session_proxy_status(client):
    api_client, store, _ = client
    manager = FakeProxyManager()
    api_client = TestClient(
        create_app(store, FakeSessions(), api_token="test-token", proxy_manager=manager)
    )
    api_client.headers.update({"Authorization": "Bearer test-token"})
    response = api_client.get("/api/sessions/aaaaaaaaaaaa/proxy/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert data["exit_ip"] == "1.2.3.4"


def test_list_profiles_includes_auto_initialized_local_profile(client):
    api_client, _, _ = client
    profiles = api_client.get("/api/profiles").json()
    assert len(profiles) == 1
    assert profiles[0]["name"] == "本地档案"


def test_create_profile_returns_persisted_profile(client):
    api_client, store, _ = client
    response = api_client.post("/api/profiles", json=_draft("工作档案"))
    assert response.status_code == 200
    profile = response.json()
    assert profile["name"] == "工作档案"
    assert store.get_profile(profile["id"]) == profile


def test_create_profile_with_partial_payload_uses_defaults(client):
    api_client, _, _ = client
    response = api_client.post("/api/profiles", json={"name": "简档"})
    assert response.status_code == 200
    profile = response.json()
    assert profile["name"] == "简档"
    assert 10000 <= profile["seed"] <= 99999
    assert profile["timezone"] == "Asia/Shanghai"


def test_create_profile_rejects_invalid_payload(client):
    api_client, _, _ = client
    payload = _draft()
    payload["seed"] = 42
    response = api_client.post("/api/profiles", json=payload)
    assert response.status_code == 400


def test_get_missing_profile_returns_404(client):
    api_client, _, _ = client
    assert api_client.get("/api/profiles/missing").status_code == 404


def test_update_profile(client):
    api_client, _, _ = client
    created = api_client.post("/api/profiles", json=_draft()).json()
    created["name"] = "改名档案"
    created["seed"] = 54321
    response = api_client.put(f"/api/profiles/{created['id']}", json=created)
    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "改名档案"
    assert updated["seed"] == 54321


def test_delete_profile_then_404(client):
    api_client, _, _ = client
    created = api_client.post("/api/profiles", json=_draft()).json()
    assert api_client.delete(f"/api/profiles/{created['id']}").status_code == 204
    assert api_client.get(f"/api/profiles/{created['id']}").status_code == 404


def test_sessions_reports_all_profiles(client):
    api_client, _, _ = client
    sessions = api_client.get("/api/sessions").json()
    assert len(sessions) == 1
    assert sessions[0]["status"] == "stopped"


def test_launch_endpoint_starts_profile(client):
    api_client, _, _ = client
    profile = api_client.post("/api/profiles", json=_draft("启动档案")).json()
    response = api_client.post(f"/api/sessions/{profile['id']}/launch")
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_launch_endpoint_missing_profile_returns_404(client):
    api_client, _, _ = client
    assert api_client.post("/api/sessions/missing/launch").status_code == 404


def test_stop_endpoint_returns_stopped(client):
    api_client, _, _ = client
    profile = api_client.post("/api/profiles", json=_draft()).json()
    api_client.post(f"/api/sessions/{profile['id']}/launch")
    response = api_client.post(f"/api/sessions/{profile['id']}/stop")
    assert response.status_code == 200
    assert response.json()["status"] == "stopped"


def test_open_url_endpoint_requires_running_session(client):
    api_client, _, _ = client
    profile = api_client.post("/api/profiles", json=_draft()).json()
    closed = api_client.post(
        f"/api/sessions/{profile['id']}/open", json={"url": "https://example.com"}
    )
    assert closed.status_code == 409
    api_client.post(f"/api/sessions/{profile['id']}/launch")
    opened = api_client.post(
        f"/api/sessions/{profile['id']}/open", json={"url": "https://example.com"}
    )
    assert opened.status_code == 200


def test_open_url_endpoint_rejects_non_http_scheme(client):
    api_client, _, _ = client
    profile = api_client.post("/api/profiles", json=_draft()).json()
    api_client.post(f"/api/sessions/{profile['id']}/launch")
    response = api_client.post(
        f"/api/sessions/{profile['id']}/open",
        json={"url": "file:///C:/Windows/win.ini"},
    )
    assert response.status_code == 400


def test_engine_endpoint_returns_health_keys(client):
    api_client, _, _ = client
    response = api_client.get("/api/engine")
    assert response.status_code == 200
    assert "available" in response.json()
    assert "version" in response.json()


def test_health_does_not_require_token(client):
    api_client, _, _ = client
    response = api_client.get("/api/health")
    assert response.status_code == 200


def test_api_requires_token(client):
    api_client, _, _ = client
    response = api_client.get("/api/profiles", headers={"Authorization": ""})
    assert response.status_code == 401


def test_export_import_roundtrip(client):
    api_client, _, _ = client
    created = api_client.post("/api/profiles", json=_draft("导出档案")).json()
    exported = api_client.get(f"/api/profiles/{created['id']}/export")
    assert exported.status_code == 200
    data = exported.json()
    assert data["id"] == created["id"]
    imported = api_client.post("/api/profiles/import", json=data)
    assert imported.status_code == 200
    imported_profile = imported.json()
    assert imported_profile["id"] != created["id"]
    assert imported_profile["name"] == created["name"]


def test_duplicate_profile(client):
    api_client, _, _ = client
    created = api_client.post("/api/profiles", json=_draft("原档案")).json()
    duplicated = api_client.post(f"/api/profiles/{created['id']}/duplicate")
    assert duplicated.status_code == 200
    copy = duplicated.json()
    assert copy["id"] != created["id"]
    assert copy["name"] == "原档案 副本"


def test_delete_moves_profile_to_recycle_bin(client):
    api_client, store, _ = client
    created = api_client.post("/api/profiles", json=_draft()).json()
    data_dir = store.profile_data_dir(created["id"])
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "cookies").write_text("x", encoding="utf-8")
    assert api_client.delete(f"/api/profiles/{created['id']}").status_code == 204
    assert api_client.get(f"/api/profiles/{created['id']}").status_code == 404
    recycled = api_client.get("/api/recycle-bin").json()
    assert [p["id"] for p in recycled] == [created["id"]]
    restored = api_client.post(f"/api/recycle-bin/{created['id']}/restore")
    assert restored.status_code == 200
    assert api_client.get(f"/api/profiles/{created['id']}").status_code == 200
    assert store.profile_data_dir(created["id"]).exists()


def test_recycle_bin_permanent_delete(client):
    api_client, _, _ = client
    created = api_client.post("/api/profiles", json=_draft()).json()
    api_client.delete(f"/api/profiles/{created['id']}")
    assert (
        api_client.delete(f"/api/recycle-bin/{created['id']}").status_code == 204
    )
    assert api_client.get("/api/recycle-bin").json() == []


def test_batch_launch_and_stop(client):
    api_client, _, _ = client
    first = api_client.post("/api/profiles", json=_draft("甲")).json()
    second = api_client.post("/api/profiles", json=_draft("乙")).json()
    launched = api_client.post(
        "/api/sessions/batch-launch",
        json={"ids": [first["id"], second["id"]]},
    )
    assert launched.status_code == 200
    assert all(item["ok"] for item in launched.json())
    stopped = api_client.post(
        "/api/sessions/batch-stop",
        json={"ids": [first["id"], second["id"]]},
    )
    assert stopped.status_code == 200
    assert all(item["ok"] for item in stopped.json())


def test_batch_launch_reports_missing_profile(client):
    api_client, _, _ = client
    results = api_client.post(
        "/api/sessions/batch-launch", json={"ids": ["missingprofile"]}
    ).json()
    assert results[0]["ok"] is False


def test_open_downloads_opens_profile_folder(monkeypatch, client):
    api_client, _, _ = client
    created = api_client.post("/api/profiles", json=_draft()).json()
    opened = []
    monkeypatch.setattr("zencloak.api.os.startfile", opened.append)
    response = api_client.post(f"/api/profiles/{created['id']}/open-downloads")
    assert response.status_code == 200
    assert opened and opened[0].endswith("Downloads")
    assert response.json()["opened"] is True



class RunningProxyManager(FakeProxyManager):
    def status(self, profile_id):
        base = super().status(profile_id)
        if "mixed_port" not in base:
            base = {**base, "mixed_port": 17891}
        return {**base, "status": "running"}


def _consistency_client(monkeypatch, tmp_path, geo=None):
    store = ProfileStore(tmp_path, auto_init=True)
    api_client = TestClient(
        create_app(
            store,
            FakeSessions(),
            api_token="test-token",
            proxy_manager=RunningProxyManager(),
        )
    )
    api_client.headers.update({"Authorization": "Bearer test-token"})
    monkeypatch.setattr(
        "zencloak.api.lookup_ip_geo",
        lambda proxy_url=None, timeout=10.0, fetch=None: geo
        or {
            "ip": "5.6.7.8",
            "country": "US",
            "city": "New York",
            "timezone": "America/New_York",
        },
    )
    return api_client, store


def _enable_builtin_proxy(api_client, profile_id):
    profile = api_client.get(f"/api/profiles/{profile_id}").json()
    api_client.put(
        f"/api/profiles/{profile_id}",
        json={**profile, "proxy_enabled": True, "proxy_mode": "mihomo"},
    )


def test_session_consistency_requires_proxy(client):
    api_client, _, _ = client
    created = api_client.post("/api/profiles", json=_draft()).json()
    response = api_client.get(f"/api/sessions/{created['id']}/consistency")
    assert response.status_code == 200
    data = response.json()
    assert data["checked"] is False
    assert "未启用代理" in data["reason"]


def test_session_consistency_reports_timezone_mismatch(monkeypatch, tmp_path):
    api_client, _ = _consistency_client(monkeypatch, tmp_path)
    created = api_client.post("/api/profiles", json=_draft()).json()
    _enable_builtin_proxy(api_client, created["id"])
    response = api_client.get(f"/api/sessions/{created['id']}/consistency")
    assert response.status_code == 200
    data = response.json()
    assert data["checked"] is True
    assert data["ip"] == "5.6.7.8"
    assert data["ip_timezone"] == "America/New_York"
    assert "timezone" in [w["kind"] for w in data["warnings"]]


def test_session_consistency_when_proxy_stopped(client, monkeypatch):
    api_client, _, _ = client  # fixture client has no proxy_manager -> 503 path
    created = api_client.post("/api/profiles", json=_draft()).json()
    profile = api_client.get(f"/api/profiles/{created['id']}").json()
    api_client.put(
        f"/api/profiles/{created['id']}",
        json={**profile, "proxy_enabled": True, "proxy_mode": "mihomo"},
    )
    response = api_client.get(f"/api/sessions/{created['id']}/consistency")
    assert response.status_code == 503


def test_session_apply_ip_timezone(monkeypatch, tmp_path):
    api_client, store = _consistency_client(monkeypatch, tmp_path)
    created = api_client.post("/api/profiles", json=_draft()).json()
    _enable_builtin_proxy(api_client, created["id"])
    assert created["timezone"] == "Asia/Shanghai"
    response = api_client.post(f"/api/sessions/{created['id']}/apply-ip-timezone")
    assert response.status_code == 200
    assert response.json()["timezone"] == "America/New_York"
    assert store.get_profile(created["id"])["timezone"] == "America/New_York"


def test_session_apply_ip_timezone_already_consistent(monkeypatch, tmp_path):
    api_client, _ = _consistency_client(
        monkeypatch,
        tmp_path,
        geo={
            "ip": "5.6.7.8",
            "country": "CN",
            "city": "Shanghai",
            "timezone": "Asia/Shanghai",
        },
    )
    created = api_client.post("/api/profiles", json=_draft()).json()
    _enable_builtin_proxy(api_client, created["id"])
    response = api_client.post(f"/api/sessions/{created['id']}/apply-ip-timezone")
    assert response.status_code == 409
