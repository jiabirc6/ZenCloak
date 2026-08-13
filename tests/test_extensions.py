import json

from zencloak.core.extensions import build_newtab_extension, cleanup_stale_newtab_extensions


def test_build_newtab_extension_writes_blank_page_and_worker(tmp_path):
    profile = {"id": "aaaaaaaaaaaa", "start_url": "https://example.com/path?q=1"}
    ext_dir = build_newtab_extension(profile, tmp_path, dir_name="newtab-v3")
    manifest = json.loads((ext_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["chrome_url_overrides"]["newtab"] == "newtab.html"
    assert manifest["background"]["service_worker"] == "background.js"
    html = (ext_dir / "newtab.html").read_text(encoding="utf-8")
    assert "newtab.js" not in html
    background = (ext_dir / "background.js").read_text(encoding="utf-8")
    assert '"about:blank"' in background
    assert "chrome.tabs.onCreated" in background
    assert "chrome://new-tab-page-third-party" in background


def test_build_newtab_extension_never_embeds_start_url(tmp_path):
    profile = {"id": "cccccccccccc", "start_url": None}
    ext_dir = build_newtab_extension(profile, tmp_path, dir_name="newtab-v3")
    background = (ext_dir / "background.js").read_text(encoding="utf-8")
    assert '"about:blank"' in background
    assert "https://example.com/path?q=1" not in background


def test_cleanup_keeps_current_newtab_dir(tmp_path):
    profile = {"id": "bbbbbbbbbbbb", "start_url": "https://example.com"}
    ext_root = tmp_path / profile["id"] / "extensions"
    (ext_root / "newtab").mkdir(parents=True)
    (ext_root / "newtab-v2").mkdir(parents=True)
    current = build_newtab_extension(profile, tmp_path, dir_name="newtab-v3")
    cleanup_stale_newtab_extensions(profile, tmp_path, keep_dir="newtab-v3")
    assert [p.name for p in ext_root.iterdir()] == ["newtab-v3"]
    assert current.exists()
