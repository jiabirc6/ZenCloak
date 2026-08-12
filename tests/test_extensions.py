import json

from zencloak.core.extensions import (
    clean_newtab_extension_prefs,
    cleanup_stale_newtab_extensions,
)


def test_cleanup_removes_all_old_newtab_dirs(tmp_path):
    profile = {"id": "aaaaaaaaaaaa", "start_url": "https://example.com"}
    ext_root = tmp_path / profile["id"] / "extensions"
    (ext_root / "newtab").mkdir(parents=True)
    (ext_root / "newtab-v2").mkdir(parents=True)
    (ext_root / "other").mkdir()
    cleanup_stale_newtab_extensions(profile, tmp_path, keep_dir="__none__")
    assert [p.name for p in ext_root.iterdir()] == ["other"]


def test_clean_prefs_removes_newtab_override_and_settings(tmp_path):
    profile = {"id": "bbbbbbbbbbbb", "start_url": "https://example.com"}
    prefs_dir = tmp_path / profile["id"] / "Default"
    prefs_dir.mkdir(parents=True)
    prefs_path = prefs_dir / "Preferences"
    prefs_path.write_text(
        json.dumps(
            {
                "extensions": {
                    "chrome_url_overrides": {
                        "newtab": [{"active": True, "entry": "chrome-extension://abc/newtab.html"}]
                    },
                    "settings": {
                        "abc": {"path": str(tmp_path / profile["id"] / "extensions" / "newtab-v2")}
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    clean_newtab_extension_prefs(profile, tmp_path)
    data = json.loads(prefs_path.read_text(encoding="utf-8"))
    assert data["extensions"]["chrome_url_overrides"]["newtab"] == []
    assert "abc" not in data["extensions"]["settings"]
