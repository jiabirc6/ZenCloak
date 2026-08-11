import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .fingerprint import default_profile_draft
from .models import Profile


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    def list_profiles(self) -> list[dict]:
        profiles = []
        for path in sorted(self.profiles_dir.glob("*.json")):
            with path.open("r", encoding="utf-8") as handle:
                profiles.append(json.load(handle))
        return sorted(profiles, key=lambda item: item["created_at"])

    def get_profile(self, profile_id: str) -> dict | None:
        path = self._path(profile_id)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def create_profile(self, data: dict) -> dict:
        payload = {
            **data,
            "id": data.get("id") or uuid.uuid4().hex[:12],
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        profile = Profile.model_validate(payload).model_dump()
        with self._path(profile["id"]).open("w", encoding="utf-8") as handle:
            json.dump(profile, handle, ensure_ascii=False, indent=2)
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
        with self._path(profile_id).open("w", encoding="utf-8") as handle:
            json.dump(profile, handle, ensure_ascii=False, indent=2)
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
