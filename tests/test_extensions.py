import json

from zencloak.core.extensions import (
    build_newtab_extension,
    cleanup_stale_newtab_extensions,
)


def _generated(profile: dict, tmp_path, dir_name: str = "newtab-v3"):
    ext_dir = build_newtab_extension(profile, tmp_path, dir_name=dir_name)
    manifest = json.loads((ext_dir / "manifest.json").read_text(encoding="utf-8"))
    background = (ext_dir / "background.js").read_text(encoding="utf-8")
    content_path = ext_dir / "content.js"
    content = content_path.read_text(encoding="utf-8") if content_path.exists() else ""
    return ext_dir, manifest, background, content


def test_build_newtab_extension_default_has_no_content_script(tmp_path):
    profile = {"id": "aaaaaaaaaaaa", "seed": 12345, "start_url": "https://example.com/path?q=1"}
    ext_dir, manifest, background, _ = _generated(profile, tmp_path)
    assert "chrome_url_overrides" not in manifest  # 接管 NTP 会导致点 + 双标签
    assert manifest["background"]["service_worker"] == "background.js"
    assert manifest["name"] == "ZenCloak Helper"
    assert "contextMenus" in manifest["permissions"]
    # 默认不注册 content script：网页侧零 DOM 注入
    assert "content_scripts" not in manifest
    assert not (ext_dir / "content.js").exists()
    assert manifest["commands"]["translate-page"]["suggested_key"]["default"] == "Alt+Shift+T"
    assert not (ext_dir / "newtab.html").exists()
    assert "chrome.contextMenus.create" in background
    assert "chrome.runtime.onStartup" in background
    assert "chrome.commands.onCommand" in background
    assert "chrome.tabs.sendMessage" in background
    assert "{{" not in background
    assert "}}" not in background


def test_translation_happens_in_place_never_in_a_new_tab(tmp_path):
    """Regression guard for the translation rewrite.

    The old implementation opened ``translate.google.com/translate?u=<url>`` in
    a new tab. That reloads the document, so anything the page held in memory
    (half-filled forms, expanded sections, POST results, one-shot tokens) was
    lost. Translation must now mutate the current document only.
    """
    profile = {"id": "aaaaaaaaaaaa", "seed": 12345, "translate_button": True}
    _, _, background, content = _generated(profile, tmp_path)
    both = background + content

    # The new-tab approach must be gone entirely.
    assert "chrome.tabs.create" not in both
    assert "translate.google.com/translate" not in both
    assert "window.location.href" not in both

    # In-place translation markers must be present.
    assert "createTreeWalker" in content, "必须按文本节点翻译以保留 DOM 结构"
    assert "translate.googleapis.com" in content
    assert "MutationObserver" in content, "动态加载的内容也要翻译"


def test_content_script_is_opt_in_via_translate_button(tmp_path):
    profile = {"id": "aaaaaaaaaaaa", "seed": 12345, "translate_button": True}
    ext_dir, manifest, _, content = _generated(profile, tmp_path)
    assert manifest["content_scripts"][0]["js"] == ["content.js"]
    assert (ext_dir / "content.js").exists()
    # 页面侧不得出现任何可关联产品的固定字符串
    assert "zencloak" not in content.lower()


def test_channel_name_differs_per_seed_and_is_not_a_product_string(tmp_path):
    base = {"id": "aaaaaaaaaaaa", "translate_button": True}
    _, _, bg_a, content_a = _generated({**base, "seed": 11111}, tmp_path / "a")
    _, _, bg_b, content_b = _generated({**base, "seed": 22222}, tmp_path / "b")

    channel_a = _extract_channel(bg_a)
    channel_b = _extract_channel(bg_b)
    assert channel_a != channel_b
    assert channel_a.startswith("zc-")
    # 同一个 channel 必须同时用于 background 与 content，否则消息对不上
    assert channel_a in content_a
    assert channel_b in content_b
    assert channel_a not in content_b


def _extract_channel(background: str) -> str:
    line = [l for l in background.splitlines() if "const MSG =" in l][0]
    return line.split('"')[1]


def test_dynamic_content_watch_is_bounded(tmp_path):
    """The observer must be disconnected on restore, not left running."""
    profile = {"id": "aaaaaaaaaaaa", "seed": 12345, "translate_button": True}
    _, _, _, content = _generated(profile, tmp_path)
    assert "observer.disconnect()" in content
    assert "stopWatching" in content


def test_translates_the_whole_page_not_just_the_article(tmp_path):
    """Scope must match Chrome's translate: nav, sidebar and footer too.

    An earlier revision restricted the walk to a main-content selector, which
    left menus and footers in the original language.
    """
    profile = {"id": "aaaaaaaaaaaa", "seed": 12345, "translate_button": True}
    _, _, _, content = _generated(profile, tmp_path)
    assert "collectTextNodes(document.body)" in content
    # The content-area heuristic is gone; nothing may pick a sub-root again.
    assert "pickRoot" not in content
    assert "CONTENT_SELECTORS" not in content


def test_requests_are_batched_not_one_per_node(tmp_path):
    """Text goes out in few batched requests, not one per text node.

    Sending one request per node took ~514 ms each, so a Wikipedia article
    (3918 nodes) would have needed over half an hour. Batching brings it to a
    handful of requests.
    """
    profile = {"id": "aaaaaaaaaaaa", "seed": 12345, "translate_button": True}
    _, _, _, content = _generated(profile, tmp_path)
    assert "translateBatch" in content
    assert "makeBatches" in content
    assert "MAX_CHARS_PER_REQUEST" in content
    assert "MAX_CONCURRENT_REQUESTS" in content
    # Lines are joined with a newline so the endpoint segments them back.
    assert 'texts.join("\\n")' in content


def test_batch_limits_stay_below_the_measured_breaking_point(tmp_path):
    """A 15000-character batch returned truncated results in testing.

    The configured ceiling must leave margin under that, and concurrent
    requests must be bounded so the endpoint is not hammered.
    """
    import re

    profile = {"id": "aaaaaaaaaaaa", "seed": 12345, "translate_button": True}
    _, _, _, content = _generated(profile, tmp_path)
    chars = int(re.search(r"MAX_CHARS_PER_REQUEST = (\d+)", content).group(1))
    concurrency = int(re.search(r"MAX_CONCURRENT_REQUESTS = (\d+)", content).group(1))
    assert chars <= 4000, f"批次上限 {chars} 超出实测可用范围"
    assert 1 <= concurrency <= 8, f"并发数 {concurrency} 不合理"


def test_batch_failure_falls_back_to_per_node(tmp_path):
    """One malformed batch must not silently drop a chunk of the page."""
    profile = {"id": "aaaaaaaaaaaa", "seed": 12345, "translate_button": True}
    _, _, _, content = _generated(profile, tmp_path)
    assert "Fall back to per-node requests" in content
    assert "catch (error)" in content


def test_restore_uses_stored_originals(tmp_path):
    """Toggling back must restore exact originals, not re-translate."""
    profile = {"id": "aaaaaaaaaaaa", "seed": 12345, "translate_button": True}
    _, _, _, content = _generated(profile, tmp_path)
    assert "state.pairs" in content
    assert "remember(node, original)" in content
    assert "for (const [node, original] of state.pairs)" in content


def test_editable_and_code_content_is_skipped(tmp_path):
    """Form fields and <pre>/<code> must never be rewritten."""
    profile = {"id": "aaaaaaaaaaaa", "seed": 12345, "translate_button": True}
    _, _, _, content = _generated(profile, tmp_path)
    for tag in ("TEXTAREA", "INPUT", "CODE", "PRE", "SCRIPT", "STYLE"):
        assert f'"{tag}"' in content, f"{tag} 应列入跳过列表"
    assert "isContentEditable" in content


def test_manifest_grants_translate_host_permission(tmp_path):
    profile = {"id": "aaaaaaaaaaaa", "seed": 12345, "translate_button": True}
    _, manifest, _, _ = _generated(profile, tmp_path)
    assert "https://translate.googleapis.com/*" in manifest["host_permissions"]


def test_build_newtab_extension_never_embeds_start_url(tmp_path):
    profile = {"id": "cccccccccccc", "start_url": None}
    _, _, background, _ = _generated(profile, tmp_path)
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


def test_disabled_translate_button_removes_stale_content_script(tmp_path):
    """Turning the option off must delete a previously generated content.js."""
    profile = {"id": "aaaaaaaaaaaa", "seed": 12345, "translate_button": True}
    ext_dir = build_newtab_extension(profile, tmp_path, dir_name="newtab-v3")
    assert (ext_dir / "content.js").exists()

    build_newtab_extension(
        {**profile, "translate_button": False}, tmp_path, dir_name="newtab-v3"
    )
    manifest = json.loads((ext_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "content_scripts" not in manifest
    assert not (ext_dir / "content.js").exists()
