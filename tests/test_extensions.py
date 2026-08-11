import json

from zencloak.core.extensions import (
    build_newtab_extension,
    cleanup_stale_newtab_extensions,
)


def test_newtab_html_uses_external_redirect_script(tmp_path):
    profile = {"id": "aaaaaaaaaaaa", "start_url": "https://example.com/path?q=1"}
    ext_dir = build_newtab_extension(profile, tmp_path)
    html = (ext_dir / "newtab.html").read_text(encoding="utf-8")
    js = (ext_dir / "newtab.js").read_text(encoding="utf-8")
    assert 'src="newtab.js"' in html
    assert "https://example.com/path?q=1" in html
    assert "location.replace" in js


def test_newtab_html_escapes_url_in_attribute(tmp_path):
    profile = {"id": "bbbbbbbbbbbb", "start_url": "https://example.com/?a=1&b=2"}
    ext_dir = build_newtab_extension(profile, tmp_path)
    html = (ext_dir / "newtab.html").read_text(encoding="utf-8")
    assert "&amp;" in html


def test_newtab_extension_has_background_redirect_worker(tmp_path):
    profile = {"id": "cccccccccccc", "start_url": "https://example.com"}
    ext_dir = build_newtab_extension(profile, tmp_path)
    manifest = json.loads((ext_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["background"]["service_worker"] == "background.js"
    assert "tabs" in manifest["permissions"]
    background = (ext_dir / "background.js").read_text(encoding="utf-8")
    assert "https://example.com" in background
    assert "chrome.tabs.onCreated" in background


def test_cleanup_keeps_only_current_newtab_extension(tmp_path):
    profile = {"id": "dddddddddddd", "start_url": "https://example.com"}
    ext_root = tmp_path / profile["id"] / "extensions"
    (ext_root / "newtab").mkdir(parents=True)
    (ext_root / "newtab-abc123").mkdir(parents=True)
    current = build_newtab_extension(profile, tmp_path, dir_name="newtab-v2")
    cleanup_stale_newtab_extensions(profile, tmp_path, keep_dir="newtab-v2")
    remaining = sorted(p.name for p in ext_root.iterdir())
    assert remaining == ["newtab-v2"]
    assert current.exists()
