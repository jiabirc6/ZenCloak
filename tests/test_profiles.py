import pytest
from pydantic import ValidationError

from zencloak.core.fingerprint import default_profile_draft
from zencloak.core.profiles import ProfileStore


@pytest.fixture()
def store(tmp_path):
    return ProfileStore(tmp_path, auto_init=False)


def _draft(name="测试档案"):
    return {**default_profile_draft(), "name": name}


def test_create_profile_persists_and_generates_id(store):
    profile = store.create_profile(_draft())
    assert len(profile["id"]) == 12
    assert profile["name"] == "测试档案"
    assert profile["created_at"] == profile["updated_at"]
    assert store.get_profile(profile["id"]) == profile


def test_create_profile_ignores_client_supplied_id(store):
    profile = store.create_profile({**_draft(), "id": "..\\..\\..\\x"})
    assert len(profile["id"]) == 12
    assert all(c in "0123456789abcdef" for c in profile["id"])


def test_rejects_traversal_profile_id_on_read(store):
    with pytest.raises(ValueError):
        store.get_profile("..\\..\\..\\x")


def test_rejects_traversal_profile_id_on_delete(store):
    with pytest.raises(ValueError):
        store.delete_profile("..\\..\\..\\x")


def test_list_profiles_returns_copies(store):
    first = store.create_profile(_draft("甲档案"))
    second = store.create_profile(_draft("乙档案"))
    profiles = store.list_profiles()
    assert [p["id"] for p in profiles] == [first["id"], second["id"]]
    profiles[0]["name"] = "篡改"
    assert store.get_profile(first["id"])["name"] == "甲档案"


def test_update_profile_changes_updated_at_only(store):
    profile = store.create_profile(_draft())
    original_created = profile["created_at"]
    payload = {**profile, "name": "新名字", "seed": 55555}
    updated = store.update_profile(profile["id"], payload)
    assert updated["name"] == "新名字"
    assert updated["seed"] == 55555
    assert updated["created_at"] == original_created
    assert updated["updated_at"] >= original_created


def test_update_missing_profile_returns_none(store):
    assert store.update_profile("missing", _draft()) is None


def test_delete_profile_moves_file_and_data_to_recycle_bin(store):
    profile = store.create_profile(_draft())
    data_dir = store.profile_data_dir(profile["id"])
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "cookies").write_text("x", encoding="utf-8")
    assert store.delete_profile(profile["id"]) is True
    assert store.get_profile(profile["id"]) is None
    assert not data_dir.exists()
    recycled = store.list_recycle_bin()
    assert [p["id"] for p in recycled] == [profile["id"]]
    restored = store.restore_profile(profile["id"])
    assert restored is not None
    assert store.get_profile(profile["id"])["name"] == profile["name"]
    assert store.profile_data_dir(profile["id"]).exists()


def test_delete_missing_profile_returns_false(store):
    assert store.delete_profile("missing") is False


def test_restore_missing_recycle_item_returns_none(store):
    assert store.restore_profile("missingprofile") is None


def test_permanent_delete_removes_recycle_item(store):
    profile = store.create_profile(_draft())
    store.delete_profile(profile["id"])
    assert store.permanent_delete_profile(profile["id"]) is True
    assert store.list_recycle_bin() == []


def test_duplicate_profile_creates_copy(store):
    profile = store.create_profile(_draft("工作号"))
    duplicate = store.duplicate_profile(profile["id"])
    assert duplicate is not None
    assert duplicate["id"] != profile["id"]
    assert duplicate["name"] == "工作号 副本"
    assert store.get_profile(duplicate["id"]) is not None


def test_auto_init_creates_default_profile(tmp_path):
    initialized = ProfileStore(tmp_path, auto_init=True)
    profiles = initialized.list_profiles()
    assert len(profiles) == 1
    assert profiles[0]["name"] == "本地档案"
    assert profiles[0]["start_url"] == "https://www.baidu.com"


def test_invalid_proxy_type_rejected(store):
    payload = {**_draft(), "proxy": {"type": "ftp", "host": "x", "port": 1}}
    with pytest.raises(ValidationError):
        store.create_profile(payload)


def test_invalid_proxy_port_rejected(store):
    payload = {**_draft(), "proxy": {"type": "socks5", "host": "x", "port": 70000}}
    with pytest.raises(ValidationError):
        store.create_profile(payload)


def test_invalid_screen_rejected(store):
    with pytest.raises(ValueError):
        store.create_profile({**_draft(), "screen_width": 999, "screen_height": 999})


def test_invalid_human_preset_rejected(store):
    with pytest.raises(ValidationError):
        store.create_profile({**_draft(), "human_preset": "robot"})


def test_start_url_without_scheme_is_normalized_to_https(store):
    profile = store.create_profile({**_draft(), "start_url": "google.com"})
    assert store.get_profile(profile["id"])["start_url"] == "https://google.com"


def test_start_url_with_http_scheme_kept(store):
    profile = store.create_profile({**_draft(), "start_url": "http://example.com"})
    assert store.get_profile(profile["id"])["start_url"] == "http://example.com"


def test_start_url_localhost_uses_http(store):
    profile = store.create_profile({**_draft(), "start_url": "localhost:8080"})
    assert store.get_profile(profile["id"])["start_url"] == "http://localhost:8080"


def test_start_url_loopback_uses_http(store):
    profile = store.create_profile({**_draft(), "start_url": "127.0.0.1:5666"})
    assert store.get_profile(profile["id"])["start_url"] == "http://127.0.0.1:5666"


def test_empty_start_url_becomes_none(store):
    profile = store.create_profile({**_draft(), "start_url": "   "})
    assert store.get_profile(profile["id"])["start_url"] is None


def test_start_url_rejects_file_scheme(store):
    with pytest.raises(ValidationError):
        store.create_profile({**_draft(), "start_url": "file:///C:/Windows/win.ini"})


def test_proxy_password_is_encrypted_on_disk(store):
    profile = store.create_profile(
        {
            **_draft(),
            "proxy": {
                "type": "http",
                "host": "proxy.example",
                "port": 8080,
                "username": "user",
                "password": "secret",
            },
        }
    )
    raw = store._path(profile["id"]).read_text(encoding="utf-8")
    assert "secret" not in raw
    loaded = store.get_profile(profile["id"])
    assert loaded["proxy"]["password"] == "secret"
