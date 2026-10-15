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


def test_profiles_default_to_no_tags_and_no_auto_timezone(store):
    """Both fields are new, so an existing profile file must still load.

    Profiles written before these fields existed have neither key; the
    defaults are what keeps them readable rather than a validation error.
    """
    profile = store.create_profile(_draft())
    assert profile["tags"] == []
    assert profile["auto_timezone"] is False


def test_tags_are_trimmed_and_deduplicated(store):
    profile = store.create_profile(
        _draft() | {"tags": ["  美国  ", "美国", "广告", "", "  "]}
    )
    # First spelling wins, blanks are dropped, order is preserved.
    assert profile["tags"] == ["美国", "广告"]


def test_tags_deduplicate_case_insensitively(store):
    profile = store.create_profile(_draft() | {"tags": ["US", "us", "Us"]})
    assert profile["tags"] == ["US"]


def test_tags_reject_overlong_entries_and_lists(store):
    # A single tag longer than the cap is dropped rather than failing the save,
    # so a stray paste cannot block an unrelated edit.
    profile = store.create_profile(_draft() | {"tags": ["x" * 40, "ok"]})
    assert profile["tags"] == ["ok"]

    with pytest.raises(ValidationError):
        store.create_profile(_draft() | {"tags": [f"t{i}" for i in range(25)]})


def test_auto_timezone_persists(store):
    profile = store.create_profile(_draft() | {"auto_timezone": True})
    assert profile["auto_timezone"] is True
    assert store.get_profile(profile["id"])["auto_timezone"] is True


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


@pytest.mark.parametrize(
    "bad_id",
    [
        "..\\..\\..\\x",
        "../../../x",
        "0123456789ab/../..",
        "a" * 12 + "/../../x",
        "",
        "x",
        "ZZZZZZZZZZZZ",
        "0123456789AB",
        None,
        123,
    ],
)
def test_profile_data_subdir_rejects_invalid_ids(store, bad_id):
    """Derived per-profile paths must not escape the store root.

    ``profile_data_subdir`` backs the screenshot and Downloads locations,
    which previously joined a raw URL path parameter onto the data dir.
    """
    with pytest.raises((ValueError, TypeError)):
        store.profile_data_subdir(bad_id, "screenshots")


def test_profile_data_subdir_accepts_valid_id_and_stays_inside(store, tmp_path):
    profile = store.create_profile(_draft())
    resolved = store.profile_data_subdir(profile["id"], "screenshots").resolve()
    assert resolved.is_relative_to(store.data_dir.resolve())
    assert resolved.name == "screenshots"


def test_profile_data_subdir_does_not_create_directories(store):
    """The helper only resolves paths; callers decide when to mkdir."""
    profile = store.create_profile(_draft())
    subdir = store.profile_data_subdir(profile["id"], "screenshots")
    assert not subdir.exists()


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


def test_reading_an_old_profile_file_fills_in_new_fields(store, tmp_path):
    """A profile file written before a field existed must still read back whole.

    Profiles are loaded from JSON without re-validation, so a field added to
    the model afterwards is simply absent from every existing file. That made
    the API's shape depend on whether a profile had been saved since the
    field was added - the older ones came back without the key at all.
    """
    import json

    profile = store.create_profile(_draft("旧档案"))
    path = store.profiles_dir / f"{profile['id']}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    # Simulate a file written before tags and auto_timezone existed.
    raw.pop("tags", None)
    raw.pop("auto_timezone", None)
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    loaded = store.get_profile(profile["id"])
    assert loaded["tags"] == []
    assert loaded["auto_timezone"] is False
    assert "tags" in loaded and "auto_timezone" in loaded


def test_model_defaults_cover_every_defaulted_field():
    """The fill-in table is derived from the model, so it cannot go stale."""
    from zencloak.core.models import Profile
    from zencloak.core.profiles import _MODEL_DEFAULTS
    from pydantic_core import PydanticUndefined

    for name, field in Profile.model_fields.items():
        if field.default_factory is not None or field.default is not PydanticUndefined:
            assert name in _MODEL_DEFAULTS, f"{name} 有默认值但未纳入补全表"
