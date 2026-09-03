import json
from pathlib import Path

import pyzipper
import pytest

from zencloak.core.backup import BackupError, create_backup, restore_backup

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