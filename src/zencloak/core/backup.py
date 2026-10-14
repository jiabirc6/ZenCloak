"""Encrypted full backup / restore of profiles and browser data.

The archive is an AES-256 zip (passphrase-derived key) containing every
profile JSON plus, optionally, the persistent browser data directories
(login state, cookies) minus disposable cache folders.

Note on proxy passwords: profile JSONs store DPAPI ciphertext, which is
bound to the source machine/user. Restoring on the same machine works
transparently; restoring on a different machine keeps login state but the
proxy password must be re-entered once per profile.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import pyzipper

from .identifiers import is_valid_id

BACKUP_VERSION = 1
MANIFEST_NAME = "backup-manifest.json"
MIN_PASSPHRASE = 8

# Chromium cache dirs are disposable; login state lives in Cookies,
# "Login Data", Local Storage etc. Excluding caches keeps archives small.
_EXCLUDE_DIR_NAMES = {
    "Cache",
    "Code Cache",
    "GPUCache",
    "Crashpad",
    "Service Worker",
    "blob_storage",
}


class BackupError(RuntimeError):
    """Raised for invalid passphrase, corrupt archives or unsafe members."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_excluded(relative: PurePosixPath) -> bool:
    return any(part in _EXCLUDE_DIR_NAMES for part in relative.parts[:-1])


def _safe_member(name: str) -> tuple[str, str] | None:
    """Validate a zip member; return ("profile"|"data", profile_id) or None."""
    parts = PurePosixPath(name).parts
    if len(parts) < 2 or ".." in parts or PurePosixPath(name).is_absolute():
        return None
    if parts[0] == "profiles" and len(parts) == 2:
        stem = parts[1]
        if not stem.endswith(".json"):
            return None
        pid = stem[:-5]
        return ("profile", pid) if is_valid_id(pid) else None
    if parts[0] == "data" and len(parts) >= 3:
        pid = parts[1]
        return ("data", pid) if is_valid_id(pid) else None
    return None


def create_backup(
    store_root: str | Path,
    passphrase: str,
    include_data: bool = True,
    running_ids: tuple[str, ...] | list[str] = (),
    dest_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Pack profiles (+ data) into an encrypted zip. Running profiles are skipped."""
    if len(passphrase) < MIN_PASSPHRASE:
        raise BackupError(f"口令至少 {MIN_PASSPHRASE} 位")
    root = Path(store_root)
    profiles_dir = root / "profiles"
    data_dir = root / "data"
    backups_dir = Path(dest_dir) if dest_dir else root / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    running = set(running_ids)

    archive_path = backups_dir / f"zencloak-backup-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    manifest: dict[str, Any] = {
        "version": BACKUP_VERSION,
        "created_at": _utc_now(),
        "include_data": include_data,
        "profiles": [],
        "skipped_running": [],
    }
    with pyzipper.AESZipFile(
        archive_path, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
    ) as zf:
        zf.setpassword(passphrase.encode("utf-8"))
        for json_file in sorted(profiles_dir.glob("*.json")):
            pid = json_file.stem
            if not is_valid_id(pid):
                continue
            if pid in running:
                manifest["skipped_running"].append(pid)
                continue
            zf.write(json_file, f"profiles/{json_file.name}")
            entry: dict[str, Any] = {"id": pid}
            try:
                entry["name"] = json.loads(json_file.read_text(encoding="utf-8")).get("name")
            except (OSError, ValueError):
                pass
            if include_data and (data_dir / pid).is_dir():
                profile_dir = data_dir / pid
                for file in sorted(profile_dir.rglob("*")):
                    if not file.is_file():
                        continue
                    relative = PurePosixPath(file.relative_to(profile_dir).as_posix())
                    if _is_excluded(relative):
                        continue
                    zf.write(file, f"data/{pid}/{relative}")
                entry["data"] = True
            manifest["profiles"].append(entry)
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
    return {
        "path": str(archive_path),
        "profiles": [p["id"] for p in manifest["profiles"]],
        "skipped_running": manifest["skipped_running"],
        "size_bytes": archive_path.stat().st_size,
    }


def _plan_restore(
    names: list[str],
    existing_ids: set[str],
    running: set[str],
    overwrite: bool,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[str], list[str], list[str]]:
    """Validate every member and decide the full plan before touching disk.

    Returns ``(profile_writes, data_writes, restored, skipped_existing,
    skipped_running)`` where the write lists hold ``(member_name, profile_id)``
    pairs. Raising here means nothing has been written yet, so a rejected
    archive can never leave a half-imported store behind.
    """
    profile_writes: list[tuple[str, str]] = []
    data_writes: list[tuple[str, str]] = []
    restored: list[str] = []
    skipped_existing: list[str] = []
    skipped_running: list[str] = []
    # Data members are dropped for any profile that is not actually being
    # (re)written, so the skip decisions made below govern both kinds.
    decided_skip: set[str] = set()

    for name in names:
        member = _safe_member(name)
        if member is None:
            raise BackupError(f"备份包含非法路径：{name}")
        kind, pid = member
        if kind == "profile":
            if pid in existing_ids and not overwrite:
                skipped_existing.append(pid)
                decided_skip.add(pid)
                continue
            if pid in running:
                skipped_running.append(pid)
                decided_skip.add(pid)
                continue
            profile_writes.append((name, pid))
            restored.append(pid)
        else:
            data_writes.append((name, pid))

    data_writes = [
        (name, pid) for name, pid in data_writes if pid not in decided_skip
    ]
    return (
        profile_writes,
        data_writes,
        restored,
        skipped_existing,
        skipped_running,
    )


def restore_backup(
    archive_path: str | Path,
    passphrase: str,
    store_root: str | Path,
    running_ids: tuple[str, ...] | list[str] = (),
    overwrite: bool = False,
) -> dict[str, Any]:
    """Decrypt an archive back into the store. Existing profiles are skipped
    unless overwrite=True; data of running profiles is never touched.

    The archive is validated in full before anything is written, so a rejected
    or corrupt archive cannot leave a partially restored store.
    """
    root = Path(store_root)
    profiles_dir = root / "profiles"
    data_dir = root / "data"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    running = set(running_ids)

    try:
        zf = pyzipper.AESZipFile(Path(archive_path))
    except OSError as exc:
        raise BackupError(f"无法打开备份文件：{exc}") from exc
    with zf:
        zf.setpassword(passphrase.encode("utf-8"))
        try:
            manifest = json.loads(zf.read(MANIFEST_NAME))
        except Exception as exc:
            raise BackupError("口令错误或备份文件已损坏") from exc
        if manifest.get("version") != BACKUP_VERSION:
            raise BackupError(f"不支持的备份版本：{manifest.get('version')}")

        # Read every member once, up front: a truncated or tampered archive
        # must fail here rather than midway through the writes below.
        payloads: dict[str, bytes] = {}
        member_names = [n for n in zf.namelist() if n != MANIFEST_NAME]
        for name in member_names:
            try:
                payloads[name] = zf.read(name)
            except Exception as exc:
                raise BackupError(f"备份成员无法读取：{name}（{exc}）") from exc

    existing_ids = {path.stem for path in profiles_dir.glob("*.json")}
    (
        profile_writes,
        data_writes,
        restored,
        skipped_existing,
        skipped_running,
    ) = _plan_restore(member_names, existing_ids, running, overwrite)

    data_restored: list[str] = []
    for name, pid in profile_writes:
        (profiles_dir / f"{pid}.json").write_bytes(payloads[name])

    data_pids: set[str] = set()
    for name, pid in data_writes:
        relative = PurePosixPath(name).parts[2:]
        target = data_dir / pid / Path(*relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payloads[name])
        data_pids.add(pid)
    data_restored = sorted(data_pids)

    return {
        "restored": restored,
        "skipped_existing": skipped_existing,
        "skipped_running": skipped_running,
        "data_restored": data_restored,
    }