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
    return TestClient(create_app(store, sessions)), store, sessions


def _draft(name="新档案"):
    return {**default_profile_draft(), "name": name}


def test_health(client):
    api_client, _, _ = client
    response = api_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


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


def test_engine_endpoint_returns_health_keys(client):
    api_client, _, _ = client
    response = api_client.get("/api/engine")
    assert response.status_code == 200
    assert "available" in response.json()
    assert "version" in response.json()
