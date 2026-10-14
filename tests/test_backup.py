import json
from pathlib import Path

import pyzipper
import pytest

from zencloak.core.backup import BackupError, create_backup, restore_backup
from zencloak.core.profiles import ProfileStore

PASS = "correct-horse-battery"


def _make_store(root: Path):
    profiles = root / "profiles"
    data = root / "data"
    profiles.mkdir(parents=True)
    (data / "aaaaaaaaaaaa" / "Default").mkdir(parents=True)
    (data / "aaaaaaaaaaaa" / "Default" / "Cookies").write_bytes(b"cookie-db")
    (data / "aaaaaaaaaaaa" / "Default" / "Cache").mkdir()
    (data / "aaaaaaaaaaaa" / "Default" / "Cache" / "f1").write_bytes(b"x" * 100)
    (data / "bbbbbbbbbbbb").mkdir(parents=True)
    (data / "bbbbbbbbbbbb" / "Preferences").write_text('{"a":1}', encoding="utf-8")
    (profiles / "aaaaaaaaaaaa.json").write_text(
        json.dumps({"id": "aaaaaaaaaaaa", "name": "一号"}), encoding="utf-8"
    )
    (profiles / "bbbbbbbbbbbb.json").write_text(
        json.dumps({"id": "bbbbbbbbbbbb", "name": "二号"}), encoding="utf-8"
    )
    return profiles, data


def test_backup_restore_roundtrip(tmp_path):
    src = tmp_path / "src"
    _make_store(src)
    result = create_backup(src, PASS)
    assert Path(result["path"]).exists()
    assert set(result["profiles"]) == {"aaaaaaaaaaaa", "bbbbbbbbbbbb"}

    dst = tmp_path / "dst"
    dst.mkdir()
    restored = restore_backup(result["path"], PASS, dst)
    assert sorted(restored["restored"]) == ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]
    assert (dst / "profiles" / "aaaaaaaaaaaa.json").read_bytes() == (
        src / "profiles" / "aaaaaaaaaaaa.json"
    ).read_bytes()
    assert (dst / "data" / "aaaaaaaaaaaa" / "Default" / "Cookies").read_bytes() == b"cookie-db"
    assert (dst / "data" / "bbbbbbbbbbbb" / "Preferences").exists()
    # 缓存目录不进备份
    assert not (dst / "data" / "aaaaaaaaaaaa" / "Default" / "Cache").exists()


def test_wrong_passphrase_raises(tmp_path):
    src = tmp_path / "src"
    _make_store(src)
    result = create_backup(src, PASS)
    with pytest.raises(BackupError):
        restore_backup(result["path"], "wrong-passphrase", tmp_path / "dst")


def test_short_passphrase_rejected(tmp_path):
    src = tmp_path / "src"
    _make_store(src)
    with pytest.raises(BackupError):
        create_backup(src, "short")


def test_running_profiles_skipped_on_backup_and_restore(tmp_path):
    src = tmp_path / "src"
    _make_store(src)
    result = create_backup(src, PASS, running_ids=["aaaaaaaaaaaa"])
    assert result["skipped_running"] == ["aaaaaaaaaaaa"]
    assert result["profiles"] == ["bbbbbbbbbbbb"]

    dst = tmp_path / "dst"
    dst.mkdir()
    full = create_backup(src, PASS)
    restored = restore_backup(full["path"], PASS, dst, running_ids=["bbbbbbbbbbbb"])
    assert restored["skipped_running"] == ["bbbbbbbbbbbb"]
    assert not (dst / "profiles" / "bbbbbbbbbbbb.json").exists()
    assert not (dst / "data").exists() or not any((dst / "data").glob("bbbbbbbbbbbb/**"))


def test_existing_profiles_not_overwritten_by_default(tmp_path):
    src = tmp_path / "src"
    _make_store(src)
    result = create_backup(src, PASS)
    dst = tmp_path / "dst"
    _make_store(dst)
    marker = dst / "profiles" / "aaaaaaaaaaaa.json"
    marker.write_text('{"id":"aaaaaaaaaaaa","name":"本机已有"}', encoding="utf-8")
    restored = restore_backup(result["path"], PASS, dst)
    assert sorted(restored["skipped_existing"]) == ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]
    assert restored["restored"] == []
    assert "本机已有" in marker.read_text(encoding="utf-8")


def test_restore_rejects_path_traversal(tmp_path):
    src = tmp_path / "src"
    _make_store(src)
    archive = src / "evil.zip"
    with pyzipper.AESZipFile(
        archive, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
    ) as zf:
        zf.setpassword(PASS.encode("utf-8"))
        zf.writestr(
            "backup-manifest.json",
            json.dumps({"version": 1, "include_data": True, "profiles": []}),
        )
        zf.writestr("data/aaaaaaaaaaaa/../../evil.txt", b"pwned")
    with pytest.raises(BackupError):
        restore_backup(archive, PASS, tmp_path / "dst")
    assert not (tmp_path / "dst" / "evil.txt").exists()


def test_restore_is_all_or_nothing_on_illegal_member(tmp_path):
    """A rejected archive must not leave a partially restored store.

    Regression guard: the old implementation walked members and wrote each
    valid one as it went, so an illegal member appearing later raised after
    earlier profiles had already been written to disk.
    """
    dst = tmp_path / "dst"
    ProfileStore(dst, auto_init=False)
    archive = tmp_path / "mixed.zip"
    victim_id = "111111111111"
    good_profile = {
        "id": victim_id,
        "name": "部分导入测试",
        "color": "#ffffff",
        "seed": 12345,
        "timezone": "UTC",
        "locale": "zh-CN",
        "platform": "windows",
        "screen_width": 1920,
        "screen_height": 1080,
        "hardware_concurrency": 8,
        "device_memory": 8,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    with pyzipper.AESZipFile(
        archive, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
    ) as zf:
        zf.setpassword(PASS.encode("utf-8"))
        zf.writestr(
            "backup-manifest.json",
            json.dumps({"version": 1, "include_data": True, "profiles": []}),
        )
        # Valid member first, illegal member second: the old code wrote the
        # first one before discovering the second.
        zf.writestr(f"profiles/{victim_id}.json", json.dumps(good_profile))
        zf.writestr("profiles/../../evil.json", "{}")

    with pytest.raises(BackupError):
        restore_backup(archive, PASS, dst)

    assert not (dst / "profiles" / f"{victim_id}.json").exists()
    assert not (tmp_path / "evil.json").exists()


def test_restore_rejects_unreadable_member_before_writing(tmp_path):
    """A corrupt member fails the pre-pass, before any write happens."""
    dst = tmp_path / "dst"
    ProfileStore(dst, auto_init=False)
    archive = tmp_path / "truncated.zip"
    with pyzipper.AESZipFile(
        archive, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
    ) as zf:
        zf.setpassword(PASS.encode("utf-8"))
        zf.writestr(
            "backup-manifest.json",
            json.dumps({"version": 1, "include_data": True, "profiles": []}),
        )
        zf.writestr("profiles/222222222222.json", json.dumps({"id": "222222222222"}))

    # Wrong passphrase: the manifest cannot be decrypted, so nothing is written.
    with pytest.raises(BackupError):
        restore_backup(archive, "wrong-passphrase", dst)
    assert list((dst / "profiles").glob("*.json")) == []