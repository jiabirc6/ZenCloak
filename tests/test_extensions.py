import json

from zencloak.core.extensions import (
    build_newtab_extension,
    cleanup_stale_newtab_extensions,
)


def test_build_newtab_extension_default_has_no_content_script(tmp_path):
    profile = {"id": "aaaaaaaaaaaa", "seed": 12345, "start_url": "https://example.com/path?q=1"}
    ext_dir = build_newtab_extension(profile, tmp_path, dir_name="newtab-v3")
    manifest = json.loads((ext_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "chrome_url_overrides" not in manifest  # 接管 NTP 会导致点 + 双标签
    assert manifest["background"]["service_worker"] == "background.js"
    assert manifest["name"] == "ZenCloak Helper"
    assert "contextMenus" in manifest["permissions"]
    # 默认不注册 content script：网页侧零 DOM 注入
    assert "content_scripts" not in manifest
    assert not (ext_dir / "content.js").exists()
    assert manifest["commands"]["translate-page"]["suggested_key"]["default"] == "Alt+Shift+T"
    assert not (ext_dir / "newtab.html").exists()
    background = (ext_dir / "background.js").read_text(encoding="utf-8")
    assert "chrome.contextMenus.create" in background
    assert "chrome.runtime.onStartup" in background
    assert "chrome.commands.onCommand" in background
    assert "chrome.runtime.onMessage" in background
    assert "{{" not in background
    assert "}}" not in background


def test_translate_button_enabled_uses_seed_derived_shadow_host(tmp_path):
    profile = {"id": "aaaaaaaaaaaa", "seed": 12345, "translate_button": True}
    ext_dir = build_newtab_extension(profile, tmp_path, dir_name="newtab-v3")
    manifest = json.loads((ext_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["content_scripts"][0]["js"] == ["content.js"]
    content = (ext_dir / "content.js").read_text(encoding="utf-8")
    assert "attachShadow" in content
    assert "translate.google.com/translate" in content
    assert "window.location.href" in content
    assert "opacity" in content
    # 页面侧不得出现任何可关联产品的固定字符串
    assert "zencloak" not in content.lower()
    assert "zencloakTranslateBtn" not in content
    host_line = [line for line in content.splitlines() if "HOST_ID =" in line][0]
    assert 'HOST_ID = "zc-' in host_line


def test_translate_host_id_differs_per_seed(tmp_path):
    base = {"id": "aaaaaaaaaaaa", "translate_button": True}
    dir_a = build_newtab_extension({**base, "seed": 11111}, tmp_path / "a")
    dir_b = build_newtab_extension({**base, "seed": 22222}, tmp_path / "b")
    id_a = _extract_host_id((dir_a / "content.js").read_text(encoding="utf-8"))
    id_b = _extract_host_id((dir_b / "content.js").read_text(encoding="utf-8"))
    assert id_a != id_b


def _extract_host_id(content: str) -> str:
    line = [l for l in content.splitlines() if "HOST_ID =" in l][0]
    return line.split('"')[1]


def test_build_newtab_extension_never_embeds_start_url(tmp_path):
    profile = {"id": "cccccccccccc", "start_url": None}
    ext_dir = build_newtab_extension(profile, tmp_path, dir_name="newtab-v3")
    background = (ext_dir / "background.js").read_text(encoding="utf-8")
    assert "chrome.contextMenus" in background
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