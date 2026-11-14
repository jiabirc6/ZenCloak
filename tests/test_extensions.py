import base64
import hashlib
import io
import json
import pathlib
import zipfile

import pytest

from zencloak.core.extensions import (
    build_newtab_extension,
    cleanup_stale_newtab_extensions,
    import_user_extension,
    list_user_extensions,
    remove_user_extension,
    _pinned_key_from_crx,
    _store_id_for_key,
    user_extension_dirs,
)


def _generated(profile: dict, tmp_path, dir_name: str = "newtab-v3"):
    ext_dir = build_newtab_extension(profile, tmp_path, dir_name=dir_name)
    manifest = json.loads((ext_dir / "manifest.json").read_text(encoding="utf-8"))
    background = (ext_dir / "background.js").read_text(encoding="utf-8")
    content_path = ext_dir / "content.js"
    content = content_path.read_text(encoding="utf-8") if content_path.exists() else ""
    return ext_dir, manifest, background, content


def test_content_script_is_always_registered(tmp_path):
    """The content script must exist on every profile, including the default.

    It is the only receiver for the context-menu and shortcut messages. An
    earlier revision made it opt-in via ``translate_button``, whose default is
    off - so a default profile registered no content script, the menu posted
    to a tab with no receiver, and the error is swallowed by design
    (``void chrome.runtime.lastError``). Translation was silently dead.
    """
    profile = {"id": "aaaaaaaaaaaa", "seed": 12345, "start_url": "https://example.com/path?q=1"}
    ext_dir, manifest, background, content = _generated(profile, tmp_path)
    assert "chrome_url_overrides" not in manifest  # 接管 NTP 会导致点 + 双标签
    assert manifest["background"]["service_worker"] == "background.js"
    assert manifest["name"] == "ZenCloak Helper"
    assert "contextMenus" in manifest["permissions"]
    # 默认档案也必须注册 content script，否则翻译收不到消息
    assert manifest["content_scripts"], "默认档案必须注册 content script"
    assert manifest["content_scripts"][0]["js"] == ["content.js"]
    assert (ext_dir / "content.js").exists()
    assert manifest["commands"]["translate-page"]["suggested_key"]["default"] == "Alt+Shift+T"
    assert not (ext_dir / "newtab.html").exists()
    assert "chrome.contextMenus.create" in background
    assert "chrome.runtime.onStartup" in background
    assert "chrome.commands.onCommand" in background
    assert "chrome.tabs.sendMessage" in background
    assert "{{" not in background
    assert "}}" not in background


def test_translate_button_does_not_gate_the_content_script(tmp_path):
    """Toggling translate_button must not change whether translation works."""
    off = {"id": "aaaaaaaaaaaa", "seed": 12345, "translate_button": False}
    on = {"id": "aaaaaaaaaaaa", "seed": 12345, "translate_button": True}
    _, manifest_off, _, content_off = _generated(off, tmp_path / "off")
    _, manifest_on, _, content_on = _generated(on, tmp_path / "on")

    assert manifest_off["content_scripts"] == manifest_on["content_scripts"]
    assert content_off == content_on


def test_default_profile_injects_no_dom(tmp_path):
    """R1 still holds: with the option off, pages see zero injected elements.

    Translation runs entirely by rewriting text nodes; the floating button was
    the only DOM injection and it is gone.
    """
    off = {"id": "aaaaaaaaaaaa", "seed": 12345, "translate_button": False}
    _, _, _, content = _generated(off, tmp_path)
    for injection in ("attachShadow", "createElement", "appendChild", "insertBefore"):
        assert injection not in content, f"默认档案不应出现 {injection}"


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


def test_content_script_never_names_the_product(tmp_path):
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


def test_content_script_survives_toggling_the_option_off(tmp_path):
    """Turning the option off must NOT remove the content script.

    It used to delete content.js and drop the manifest entry, which killed
    translation outright. The option now only affects the floating button.
    """
    profile = {"id": "aaaaaaaaaaaa", "seed": 12345, "translate_button": True}
    ext_dir = build_newtab_extension(profile, tmp_path, dir_name="newtab-v3")
    assert (ext_dir / "content.js").exists()

    build_newtab_extension(
        {**profile, "translate_button": False}, tmp_path, dir_name="newtab-v3"
    )
    manifest = json.loads((ext_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["content_scripts"], "关闭选项后仍须注册 content script"
    assert (ext_dir / "content.js").exists(), "关闭选项后仍须保留 content.js"


# ---------------------------------------------------------------------------
# User-imported extensions
# ---------------------------------------------------------------------------

_PROFILE_ID = "aaaaaaaaaaaa"


def _write_ext_dir(root, name="Foo", version="1.0.0", manifest_name=None, default_locale=None):
    """Create an unpacked extension folder; returns its path."""
    ext = root / name
    ext.mkdir(parents=True)
    manifest = {"manifest_version": 3, "name": manifest_name or name, "version": version}
    if default_locale:
        manifest["default_locale"] = default_locale
    (ext / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if manifest_name:
        locale_dir = ext / "_locales" / (default_locale or "en")
        locale_dir.mkdir(parents=True)
        (locale_dir / "messages.json").write_text(
            json.dumps({"extensionName": {"message": name}}), encoding="utf-8"
        )
    return ext


def _make_crx(path, src_dir):
    """Pack an extension directory into a minimal CRX3-shaped file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as bundle:
        for file in src_dir.rglob("*"):
            bundle.write(file, file.relative_to(src_dir))
    path.write_bytes(b"Cr24" + b"\x00" * 16 + buf.getvalue())
    return path


def test_import_user_extension_from_dir(tmp_path):
    src = _write_ext_dir(tmp_path / "src", name="Muse", version="2.0.65")
    result = import_user_extension(tmp_path / "data", _PROFILE_ID, src)
    assert result["name"] == "Muse"
    assert result["version"] == "2.0.65"
    assert result["id"].startswith("user-")
    listed = list_user_extensions(tmp_path / "data", _PROFILE_ID)
    assert [item["name"] for item in listed] == ["Muse"]


def test_import_resolves_msg_manifest_name(tmp_path):
    src = _write_ext_dir(
        tmp_path / "src",
        name="Muse from Meta",
        manifest_name="__MSG_extensionName__",
        default_locale="en",
    )
    result = import_user_extension(tmp_path / "data", _PROFILE_ID, src)
    assert result["name"] == "Muse from Meta"


def test_import_crx_strips_header(tmp_path):
    src = _write_ext_dir(tmp_path / "src", name="Packed", version="3.2.1")
    crx = _make_crx(tmp_path / "packed.crx", src)
    result = import_user_extension(tmp_path / "data", _PROFILE_ID, crx)
    assert result["name"] == "Packed"
    assert result["version"] == "3.2.1"
    dest = tmp_path / "data" / _PROFILE_ID / "extensions" / result["id"]
    assert (dest / "manifest.json").exists()


def test_import_rejects_duplicate(tmp_path):
    src = _write_ext_dir(tmp_path / "src")
    import_user_extension(tmp_path / "data", _PROFILE_ID, src)
    with pytest.raises(ValueError, match="已存在"):
        import_user_extension(tmp_path / "data", _PROFILE_ID, src)


def test_import_rejects_invalid_sources(tmp_path):
    empty = tmp_path / "notext"
    empty.mkdir()
    with pytest.raises(ValueError, match="manifest"):
        import_user_extension(tmp_path / "data", _PROFILE_ID, empty)
    with pytest.raises(ValueError, match="路径不存在"):
        import_user_extension(tmp_path / "data", _PROFILE_ID, tmp_path / "missing")
    bad_crx = tmp_path / "bad.crx"
    bad_crx.write_bytes(b"PK\x03\x04zipzip")
    with pytest.raises(ValueError, match="Cr24"):
        import_user_extension(tmp_path / "data", _PROFILE_ID, bad_crx)
    other = tmp_path / "other.txt"
    other.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="未打包扩展目录"):
        import_user_extension(tmp_path / "data", _PROFILE_ID, other)


def test_remove_user_extension_roundtrip(tmp_path):
    src = _write_ext_dir(tmp_path / "src")
    result = import_user_extension(tmp_path / "data", _PROFILE_ID, src)
    ext_id = result["id"]
    assert user_extension_dirs(tmp_path / "data", _PROFILE_ID)
    remove_user_extension(tmp_path / "data", _PROFILE_ID, ext_id)
    assert user_extension_dirs(tmp_path / "data", _PROFILE_ID) == []
    with pytest.raises(ValueError, match="不存在"):
        remove_user_extension(tmp_path / "data", _PROFILE_ID, ext_id)


def test_remove_rejects_traversal_and_managed_dirs(tmp_path):
    with pytest.raises(ValueError):
        remove_user_extension(tmp_path / "data", _PROFILE_ID, "../escape")
    with pytest.raises(ValueError):
        remove_user_extension(tmp_path / "data", _PROFILE_ID, "newtab-v3")


def test_crx_import_pins_store_extension_id(tmp_path):
    # Real-world known answer: muse.ai CSP frame-ancestors whitelists the
    # store ID of "Muse from Meta". A CRX import must pin the signing key
    # from the CRX3 header so the unpacked copy keeps that exact ID.
    muse_key = (
        "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAud+Kpoe4Ju0njwgICKHHmEBG"
        "/pBR8F0jbTuUWDSmnWsiS002BE7FFhBoXVet4HEhAAIDdJYjanKN3G9rgOb/bf3NZPTA"
        "MrENViMGysmN9GefzbdAjcKrHI/3lABUemmRRM0OSjQ7Gs5Nsi11Y7VpA619XQjtrpqOX"
        "cT+nXKJ6l3GhWdBTyxaGy00snjrpV7G9TMk9IIV0TF8vgmyoxYCyR66ZGj6zzwnhyAtuO"
        "hK1bo6EpCDGLw58885DA/g2YSLuW47R7EeNL6yX9gap2XwNy7kBGe27VvzcHZDvRdN5zn"
        "rVTo1YjZoJX46V2wl/T1RyS56QWDoc0n6+vo/vHYyJwIDAQAB"
    )
    muse_store_id = "jnakhhjmpmoohbjgfccbccfoifnmbdjd"
    assert _store_id_for_key(base64.b64decode(muse_key)) == muse_store_id

    der = base64.b64decode(muse_key)
    def _varint(n):
        out = b""
        while True:
            b = n & 0x7F
            n >>= 7
            out += bytes([b | 0x80]) if n else bytes([b])
            if not n:
                return out
    # Proper CRX3 header: field 2 = signature entry carrying the key,
    # field 3 = signed_header_data embedding SignedData.crx_id (field 1).
    crx_id = hashlib.sha256(der).digest()[:16]
    signed_data = b"\x0a" + _varint(len(crx_id)) + crx_id
    header = (
        b"\x12" + _varint(len(der)) + der
        + b"\x1a" + _varint(len(signed_data)) + signed_data
    )
    crx = (
        b"Cr24"
        + (3).to_bytes(4, "little")
        + len(header).to_bytes(4, "little")
        + header
        + b"PK\x03\x04zipdata"
    )
    crx_path = tmp_path / "muse.crx"
    crx_path.write_bytes(crx)
    # A CRX whose zip part has no manifest is rejected; build a valid one.
    src_dir = _write_ext_dir(tmp_path / "src", name="Muse from Meta", version="2.0.65")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as bundle:
        for file in src_dir.rglob("*"):
            bundle.write(file, file.relative_to(src_dir))
    crx_path.write_bytes(crx[: 12 + len(header)] + buf.getvalue())

    result = import_user_extension(
        tmp_path / "data", _PROFILE_ID, crx_path, store_id=muse_store_id
    )
    stored = json.loads(
        (pathlib.Path(result["dir"]) / "manifest.json").read_text(encoding="utf-8")
    )
    assert stored["key"] == muse_key


def test_crx_import_without_store_id_skips_pinning(tmp_path):
    # The CRX file does not record its own ID; without an externally known
    # store ID there is no safe selector, so no key must be pinned.
    der = base64.b64decode(
        "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAud+Kpoe4Ju0njwgICKHHmEBG"
        "/pBR8F0jbTuUWDSmnWsiS002BE7FFhBoXVet4HEhAAIDdJYjanKN3G9rgOb/bf3NZPTA"
        "MrENViMGysmN9GefzbdAjcKrHI/3lABUemmRRM0OSjQ7Gs5Nsi11Y7VpA619XQjtrpqOX"
        "cT+nXKJ6l3GhWdBTyxaGy00snjrpV7G9TMk9IIV0TF8vgmyoxYCyR66ZGj6zzwnhyAtuO"
        "hK1bo6EpCDGLw58885DA/g2YSLuW47R7EeNL6yX9gap2XwNy7kBGe27VvzcHZDvRdN5zn"
        "rVTo1YjZoJX46V2wl/T1RyS56QWDoc0n6+vo/vHYyJwIDAQAB"
    )
    def _varint(n):
        out = b""
        while True:
            b = n & 0x7F
            n >>= 7
            out += bytes([b | 0x80]) if n else bytes([b])
            if not n:
                return out
    crx_id = hashlib.sha256(der).digest()[:16]
    signed_data = b"\x0a" + _varint(len(crx_id)) + crx_id
    header = (
        b"\x12" + _varint(len(der)) + der
        + b"\x1a" + _varint(len(signed_data)) + signed_data
    )
    src_dir = _write_ext_dir(tmp_path / "src", name="Muse from Meta", version="2.0.65")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as bundle:
        for file in src_dir.rglob("*"):
            bundle.write(file, file.relative_to(src_dir))
    crx = (
        b"Cr24" + (3).to_bytes(4, "little") + len(header).to_bytes(4, "little")
        + header + buf.getvalue()
    )
    crx_path = tmp_path / "muse.crx"
    crx_path.write_bytes(crx)
    result = import_user_extension(tmp_path / "data", _PROFILE_ID, crx_path)
    stored = json.loads(
        (pathlib.Path(result["dir"]) / "manifest.json").read_text(encoding="utf-8")
    )
    assert "key" not in stored


def test_parse_store_extension_id_accepts_url_or_bare_id():
    from zencloak.core.extensions import parse_store_extension_id
    url = "https://chromewebstore.google.com/detail/muse-from-meta/jnakhhjmpmoohbjgfccbccfoifnmbdjd"
    assert parse_store_extension_id(url) == "jnakhhjmpmoohbjgfccbccfoifnmbdjd"
    assert parse_store_extension_id("jnakhhjmpmoohbjgfccbccfoifnmbdjd") == "jnakhhjmpmoohbjgfccbccfoifnmbdjd"
    assert parse_store_extension_id("不是链接") is None
    assert parse_store_extension_id("") is None
    assert parse_store_extension_id(None) is None
