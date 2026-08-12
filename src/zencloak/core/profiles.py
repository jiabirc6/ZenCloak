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
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if auto_init and not self.list_profiles():
            self.create_profile(default_profile_draft())

    def _path(self, profile_id: str) -> Path:
        return self.profiles_dir / f"{profile_id}.json"

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
            "id": data.get("id") or uuid.uuid4().hex[:12],
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

    def delete_profile(self, profile_id: str) -> bool:
        path = self._path(profile_id)
        if not path.exists():
            return False
        path.unlink()
        shutil.rmtree(self.profile_data_dir(profile_id), ignore_errors=True)
        return True

    def profile_data_dir(self, profile_id: str) -> Path:
        return self.data_dir / profile_id
