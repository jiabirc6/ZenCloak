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


def test_delete_profile_removes_file_and_data_dir(store):
    profile = store.create_profile(_draft())
    data_dir = store.profile_data_dir(profile["id"])
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "cookies").write_text("x", encoding="utf-8")
    assert store.delete_profile(profile["id"]) is True
    assert store.get_profile(profile["id"]) is None
    assert not data_dir.exists()


def test_delete_missing_profile_returns_false(store):
    assert store.delete_profile("missing") is False


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
