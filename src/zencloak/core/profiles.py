import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .fingerprint import default_profile_draft
from .models import Profile
from .secrets import decrypt_text, encrypt_text


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_profile(profile: dict) -> dict:
    data = dict(profile)
    proxy = data.get("proxy")
    if proxy and proxy.get("password"):
        data["proxy"] = {**proxy, "password": encrypt_text(proxy["password"])}
    return data


def _deserialize_profile(data: dict) -> dict:
    profile = dict(data)
    proxy = profile.get("proxy")
    if proxy and proxy.get("password"):
        try:
            password = decrypt_text(proxy["password"])
        except Exception:
            password = proxy["password"]
        profile["proxy"] = {**proxy, "password": password}
    return profile


class ProfileStore:
    """JSON-backed profile repository rooted at ``root``."""

    def __init__(self, root: str | Path, auto_init: bool = True) -> None:
        self.root = Path(root)
        self.profiles_dir = self.root / "profiles"
        self.data_dir = self.root / "data"
        self.recycle_bin_dir = self.root / "recycle-bin"
        self.recycle_data_dir = self.recycle_bin_dir / "data"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.recycle_bin_dir.mkdir(parents=True, exist_ok=True)
        self.recycle_data_dir.mkdir(parents=True, exist_ok=True)
        if auto_init and not self.list_profiles():
            self.create_profile(default_profile_draft())

    def _path(self, profile_id: str) -> Path:
        return self._resolve_within(self.profiles_dir, f"{profile_id}.json")

    def _recycle_path(self, profile_id: str) -> Path:
        return self._resolve_within(self.recycle_bin_dir, f"{profile_id}.json")

    def _recycle_data_dir(self, profile_id: str) -> Path:
        return self._resolve_within(self.recycle_data_dir, profile_id)

    def _resolve_within(self, root: Path, name: str) -> Path:
        candidate = root / name
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root.resolve()):
            raise ValueError(f"非法档案 ID: {name!r}")
        return resolved

    def _write(self, profile: dict) -> None:
        with self._path(profile["id"]).open("w", encoding="utf-8") as handle:
            json.dump(_serialize_profile(profile), handle, ensure_ascii=False, indent=2)

    def _read(self, profile_id: str) -> dict | None:
        path = self._path(profile_id)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return _deserialize_profile(json.load(handle))

    def list_profiles(self) -> list[dict]:
        profiles = []
        for path in sorted(self.profiles_dir.glob("*.json")):
            with path.open("r", encoding="utf-8") as handle:
                profiles.append(_deserialize_profile(json.load(handle)))
        return sorted(profiles, key=lambda item: item["created_at"])

    def get_profile(self, profile_id: str) -> dict | None:
        return self._read(profile_id)

    def create_profile(self, data: dict) -> dict:
        payload = {
            **data,
            "id": uuid.uuid4().hex[:12],
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        profile = Profile.model_validate(payload).model_dump()
        self._write(profile)
        return profile

    def update_profile(self, profile_id: str, data: dict) -> dict | None:
        existing = self.get_profile(profile_id)
        if existing is None:
            return None
        payload = {
            **existing,
            **data,
            "id": existing["id"],
            "created_at": existing["created_at"],
            "updated_at": _now_iso(),
        }
        profile = Profile.model_validate(payload).model_dump()
        self._write(profile)
        return profile

    def duplicate_profile(self, profile_id: str) -> dict | None:
        existing = self.get_profile(profile_id)
        if existing is None:
            return None
        suffix = " 副本"
        name = existing["name"] + suffix
        if len(name) > 32:
            name = name[: 32 - len(suffix)] + suffix
        return self.create_profile({**existing, "name": name})

    def delete_profile(self, profile_id: str) -> bool:
        path = self._path(profile_id)
        if not path.exists():
            return False
        profile = _deserialize_profile(
            json.loads(path.read_text(encoding="utf-8"))
        )
        profile["deleted_at"] = _now_iso()
        with self._recycle_path(profile_id).open("w", encoding="utf-8") as handle:
            json.dump(_serialize_profile(profile), handle, ensure_ascii=False, indent=2)
        path.unlink()
        data_dir = self.profile_data_dir(profile_id)
        if data_dir.exists():
            shutil.move(str(data_dir), str(self._recycle_data_dir(profile_id)))
        return True

    def list_recycle_bin(self) -> list[dict]:
        items = []
        for path in sorted(self.recycle_bin_dir.glob("*.json")):
            with path.open("r", encoding="utf-8") as handle:
                items.append(_deserialize_profile(json.load(handle)))
        return sorted(items, key=lambda item: item.get("deleted_at", ""), reverse=True)

    def restore_profile(self, profile_id: str) -> dict | None:
        recycle_path = self._recycle_path(profile_id)
        if not recycle_path.exists():
            return None
        profile = _deserialize_profile(
            json.loads(recycle_path.read_text(encoding="utf-8"))
        )
        profile.pop("deleted_at", None)
        self._write(profile)
        recycle_path.unlink()
        recycle_data = self._recycle_data_dir(profile_id)
        if recycle_data.exists():
            target = self.profile_data_dir(profile_id)
            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(recycle_data), str(target))
        return self.get_profile(profile_id)

    def permanent_delete_profile(self, profile_id: str) -> bool:
        recycle_path = self._recycle_path(profile_id)
        if not recycle_path.exists():
            return False
        recycle_path.unlink()
        shutil.rmtree(self._recycle_data_dir(profile_id), ignore_errors=True)
        return True

    def profile_data_dir(self, profile_id: str) -> Path:
        return self._resolve_within(self.data_dir, profile_id)
