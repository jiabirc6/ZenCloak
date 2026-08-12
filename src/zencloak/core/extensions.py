import json
import shutil
from pathlib import Path


def cleanup_stale_newtab_extensions(
    profile: dict, data_root: str | Path, keep_dir: str = "__none__"
) -> None:
    """Remove generated new-tab extension directories from a profile."""
    ext_root = Path(data_root) / profile["id"] / "extensions"
    if not ext_root.exists():
        return
    for child in ext_root.iterdir():
        if child.is_dir() and child.name.startswith("newtab"):
            if child.name == keep_dir:
                continue
            shutil.rmtree(child, ignore_errors=True)


def clean_newtab_extension_prefs(profile: dict, data_root: str | Path) -> None:
    """Remove stale new-tab override registrations from Chrome Preferences."""
    prefs_path = Path(data_root) / profile["id"] / "Default" / "Preferences"
    if not prefs_path.exists():
        return
    try:
        data = json.loads(prefs_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    changed = False
    extensions = data.get("extensions")
    if not isinstance(extensions, dict):
        return
    overrides = extensions.get("chrome_url_overrides")
    if isinstance(overrides, dict) and isinstance(overrides.get("newtab"), list):
        if overrides["newtab"]:
            overrides["newtab"] = []
            changed = True
    settings = extensions.get("settings")
    if isinstance(settings, dict):
        stale_ids = [
            key
            for key, value in settings.items()
            if isinstance(value, dict) and "newtab" in str(value.get("path", ""))
        ]
        for key in stale_ids:
            del settings[key]
            changed = True
    if changed:
        prefs_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
