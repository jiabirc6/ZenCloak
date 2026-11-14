import base64
import hashlib
import io
import json
import re
import shutil
import zipfile
from pathlib import Path

# Translate endpoint used by the extension. The free ``gtx`` client needs no
# API key and returns the same segmentation Chrome's own UI uses. Requests go
# out from the page itself, which is why this works without extra permissions:
# the host is already in ``host_permissions``.
TRANSLATE_ENDPOINT = "https://translate.googleapis.com/translate_a/single"

# Elements whose text must never be touched. Chrome's translate leaves these
# alone too: rewriting a script or a form field would break the page.
_SKIP_TAGS = (
    "SCRIPT",
    "STYLE",
    "NOSCRIPT",
    "CODE",
    "PRE",
    "TEXTAREA",
    "INPUT",
    "SELECT",
    "OPTION",
    "svg",
    "SVG",
    "CANVAS",
    "IFRAME",
)


def _background_js(host_id: str) -> str:
    """Service worker: context menu and shortcut drive in-place translation.

    ``host_id`` is the message channel name derived from the profile seed. The
    page never sees it; using a per-profile constant keeps the extension free
    of any fixed string that could correlate profiles.
    """
    return """const MSG = "%(msg)s";

function sendToTab(tabId, payload) {
  chrome.tabs.sendMessage(tabId, payload, () => {
    // Swallow "no receiver" errors: the tab may be a chrome:// page or a
    // document the content script cannot run in. Nothing to act on.
    void chrome.runtime.lastError;
  });
}

function toggleOnActiveTab() {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs && tabs[0];
    if (!tab || !tab.id || !tab.url || !/^https?:/.test(tab.url)) return;
    sendToTab(tab.id, { type: MSG, action: "toggle" });
  });
}

function createContextMenu() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: MSG,
      title: "翻译本页（原地）",
      contexts: ["page"]
    });
  });
}

createContextMenu();
chrome.runtime.onInstalled.addListener(createContextMenu);
chrome.runtime.onStartup.addListener(createContextMenu);

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === MSG && tab && tab.id) {
    sendToTab(tab.id, { type: MSG, action: "toggle" });
  }
});

chrome.commands.onCommand.addListener((command) => {
  if (command === "translate-page") toggleOnActiveTab();
});
""" % {"msg": host_id}


def _content_js(host_id: str, endpoint: str) -> str:
    """In-place full-page translation.

    Runs entirely inside the current document: it walks every translatable
    text node in the page, replaces its text with the translated string and
    keeps the original so toggling back is lossless. Nothing is reloaded, so
    form input, scroll position and any state a page holds in memory survive
    - which is exactly what the old "open translate.google.com in a new tab"
    approach destroyed.

    Scope is the whole document, matching Chrome's own translate: navigation,
    sidebars, buttons and footers are translated too, not just the article
    body. Only text nodes are rewritten, so ``<b>``/``<a>``/``<img>``
    structure stays intact and links keep working.

    Throughput: the endpoint accepts newline-separated lines and returns one
    segment per line, so a whole page goes out in a handful of requests
    instead of one per node. Measured limits (see tests): 4000 characters per
    request is safe, 15000 fails partway, so batches stay well under the
    breaking point. Batches are then issued a few at a time.
    """
    return """(() => {
  const CHANNEL = "%(msg)s";
  const ENDPOINT = "%(endpoint)s";
  const ORIG_ATTR = "data-%(attr)s";
  const STATE_KEY = "__%(attr)s_state";
  const SKIP_TAGS = new Set(%(skip_tags)s);

  // Measured against the live endpoint: a 4000-character batch always came
  // back complete; 15000 truncated. 3500 leaves margin for multi-byte text.
  const MAX_CHARS_PER_REQUEST = 3500;
  // Requests in flight at once. Four concurrent batches measured ~780 ms
  // total, so this is where most of the wall-clock win comes from.
  const MAX_CONCURRENT_REQUESTS = 4;
  // Nodes longer than this are sent alone so one huge paragraph cannot
  // overflow a batch.
  const MAX_SINGLE_NODE_CHARS = 3000;

  if (window[STATE_KEY] && window[STATE_KEY].installed) return;

  const state = {
    installed: true,
    translated: false,
    busy: false,
    observer: null,
    pairs: [],
    total: 0,
    done: 0,
  };
  window[STATE_KEY] = state;

  function shouldSkip(node) {
    let parent = node.parentElement;
    while (parent) {
      if (SKIP_TAGS.has(parent.tagName)) return true;
      if (parent.isContentEditable) return true;
      // Skip our own overlays and anything explicitly marked untranslatable.
      if (parent.hasAttribute && parent.hasAttribute(ORIG_ATTR)) return true;
      parent = parent.parentElement;
    }
    return false;
  }

  function collectTextNodes(root) {
    const out = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (!node.nodeValue || !node.nodeValue.trim()) {
          return NodeFilter.FILTER_REJECT;
        }
        return shouldSkip(node)
          ? NodeFilter.FILTER_REJECT
          : NodeFilter.FILTER_ACCEPT;
      },
    });
    let node;
    while ((node = walker.nextNode())) out.push(node);
    return out;
  }

  // One request for many lines. The endpoint returns a segment array whose
  // entries correspond to the input lines in order, each keeping its own
  // trailing newline, so the translation of line i is segments[i].
  async function translateBatch(texts) {
    const joined = texts.join("\\n");
    const url =
      ENDPOINT +
      "?client=gtx&sl=auto&tl=zh-CN&dt=t&q=" +
      encodeURIComponent(joined);
    const response = await fetch(url);
    if (!response.ok) throw new Error("HTTP " + response.status);
    const data = await response.json();
    if (!Array.isArray(data) || !Array.isArray(data[0])) {
      throw new Error("unexpected response shape");
    }
    const segments = data[0].map((segment) =>
      Array.isArray(segment) ? segment[0] || "" : ""
    );
    if (texts.length === 1) {
      return [segments.join("")];
    }
    // Rebuild one string per input line. A segment may itself contain
    // newlines (the engine sometimes splits a long line), so accumulate until
    // the count of consumed segments matches the input length.
    const rebuilt = [];
    let buffer = "";
    for (const segment of segments) {
      buffer += segment;
      if (buffer.endsWith("\\n") || rebuilt.length === texts.length - 1) {
        rebuilt.push(buffer.replace(/\\n$/, ""));
        buffer = "";
      }
    }
    if (buffer) rebuilt.push(buffer.replace(/\\n$/, ""));
    while (rebuilt.length < texts.length) rebuilt.push(texts[rebuilt.length]);
    return rebuilt.slice(0, texts.length);
  }

  function makeBatches(nodes) {
    const batches = [];
    let current = [];
    let size = 0;
    const flush = () => {
      if (current.length) {
        batches.push(current);
        current = [];
        size = 0;
      }
    };
    for (const node of nodes) {
      const text = node.nodeValue;
      if (text.length > MAX_SINGLE_NODE_CHARS) {
        flush();
        batches.push([node]);
        continue;
      }
      if (size + text.length > MAX_CHARS_PER_REQUEST) flush();
      current.push(node);
      size += text.length;
    }
    flush();
    return batches;
  }

  function remember(node, original) {
    state.pairs.push([node, original]);
  }

  async function runBatch(batch) {
    const texts = batch.map((node) => node.nodeValue);
    let translated;
    try {
      translated = await translateBatch(texts);
    } catch (error) {
      void error;
      // Fall back to per-node requests so one bad batch does not lose text.
      translated = [];
      for (const text of texts) {
        try {
          translated.push((await translateBatch([text]))[0]);
        } catch (inner) {
          void inner;
          translated.push(null);
        }
      }
    }
    batch.forEach((node, index) => {
      const value = translated[index];
      if (typeof value !== "string" || !value) return;
      // The subtree may have been replaced while the request was in flight.
      if (!node.parentElement) return;
      const original = node.nodeValue;
      try {
        node.nodeValue = value;
        remember(node, original);
        state.done += 1;
      } catch (error) {
        void error;
      }
    });
  }

  async function translatePage() {
    if (state.busy) return;
    state.busy = true;
    state.pairs = [];
    state.done = 0;
    try {
      const nodes = collectTextNodes(document.body);
      state.total = nodes.length;
      const batches = makeBatches(nodes);
      for (let i = 0; i < batches.length; i += MAX_CONCURRENT_REQUESTS) {
        const slice = batches.slice(i, i + MAX_CONCURRENT_REQUESTS);
        await Promise.all(slice.map((batch) => runBatch(batch)));
      }
      state.translated = true;
      watchDynamic();
    } finally {
      state.busy = false;
    }
  }

  function restorePage() {
    stopWatching();
    for (const [node, original] of state.pairs) {
      try {
        node.nodeValue = original;
      } catch (error) {
        void error;
      }
    }
    state.pairs = [];
    state.translated = false;
    state.done = 0;
  }

  // Content added after the initial pass (infinite scroll, "load more") is
  // translated too, matching what Chrome's own translate does.
  function watchDynamic() {
    stopWatching();
    const observer = new MutationObserver((records) => {
      if (!state.translated || state.busy) return;
      const fresh = [];
      for (const record of records) {
        record.addedNodes.forEach((node) => {
          if (node.nodeType === Node.TEXT_NODE) {
            if (node.nodeValue && node.nodeValue.trim() && !shouldSkip(node)) {
              fresh.push(node);
            }
          } else if (node.nodeType === Node.ELEMENT_NODE) {
            fresh.push(...collectTextNodes(node));
          }
        });
      }
      if (!fresh.length) return;
      state.busy = true;
      (async () => {
        try {
          for (const batch of makeBatches(fresh)) {
            await runBatch(batch);
          }
        } finally {
          state.busy = false;
        }
      })();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    state.observer = observer;
  }

  function stopWatching() {
    if (state.observer) {
      state.observer.disconnect();
      state.observer = null;
    }
  }

  function toggle() {
    if (state.translated) restorePage();
    else translatePage();
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message || message.type !== CHANNEL) return false;
    if (message.action === "toggle") toggle();
    else if (message.action === "translate" && !state.translated) translatePage();
    else if (message.action === "restore") restorePage();
    sendResponse({ ok: true, translated: state.translated });
    return true;
  });
})();
""" % {
        "msg": host_id,
        "endpoint": endpoint,
        "attr": host_id,
        "skip_tags": json.dumps(list(_SKIP_TAGS)),
    }


def _channel_id(profile: dict) -> str:
    """Per-profile message channel / storage attribute name.

    Derived from the seed so no fixed string is observable from a page, which
    keeps the R1 property: nothing in the DOM may name this product or be
    constant across profiles.
    """
    seed = profile.get("seed") or profile["id"]
    digest = hashlib.sha1(f"{seed}:{profile['id']}".encode("utf-8")).hexdigest()
    return f"zc-{digest[:8]}"


def build_newtab_extension(
    profile: dict, data_root: str | Path, dir_name: str = "newtab-v3"
) -> Path:
    """Write the ZenCloak helper extension: blank new tab plus page translate.

    The content script is always registered. It is what receives the context
    menu and Alt+Shift+T messages, so without it translation cannot run at
    all - the menu items would post to a tab with no receiver and the error is
    swallowed by design. It is also what injects the floating button, and that
    button is the only thing ``translate_button`` still controls (default off,
    so pages see no injected DOM unless the user asks for it).
    """
    ext_dir = Path(data_root) / profile["id"] / "extensions" / dir_name
    ext_dir.mkdir(parents=True, exist_ok=True)

    # 注意：故意不声明 chrome_url_overrides。这个内核里扩展接管 NTP 会让
    # 点 + 同时产生"第三方宿主页 + 扩展页"两个目标（双标签的根源）；转圈
    # 的 NTP 由 SessionManager 的 CDP sweep 统一关掉并补空白页。
    channel = _channel_id(profile)
    manifest = {
        "manifest_version": 3,
        "name": "ZenCloak Helper",
        "version": "2.1.0",
        "description": "ZenCloak in-place page translation helper.",
        "background": {"service_worker": "background.js"},
        "permissions": ["tabs", "contextMenus"],
        # The content script fetches the translate endpoint, so the page's own
        # origin must be allowed to reach it.
        "host_permissions": ["https://translate.googleapis.com/*"],
        "content_scripts": [
            {
                "matches": ["http://*/*", "https://*/*"],
                "js": ["content.js"],
                "run_at": "document_idle",
            }
        ],
        "commands": {
            "translate-page": {
                "suggested_key": {"default": "Alt+Shift+T"},
                "description": "翻译当前页面（原地）",
            }
        },
    }
    (ext_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ext_dir / "background.js").write_text(
        _background_js(channel), encoding="utf-8"
    )
    # Always written: the manifest above always registers it, and a registered
    # content script with no file would break the whole extension load.
    (ext_dir / "content.js").write_text(
        _content_js(channel, TRANSLATE_ENDPOINT), encoding="utf-8"
    )
    return ext_dir


def cleanup_stale_newtab_extensions(
    profile: dict, data_root: str | Path, keep_dir: str = "newtab-v3"
) -> None:
    """Remove generated new-tab extension directories, keeping the current one."""
    ext_root = Path(data_root) / profile["id"] / "extensions"
    if not ext_root.exists():
        return
    for child in ext_root.iterdir():
        if child.is_dir() and child.name.startswith("newtab"):
            if child.name == keep_dir:
                continue
            shutil.rmtree(child, ignore_errors=True)


# ---------------------------------------------------------------------------
# User-imported extensions
# ---------------------------------------------------------------------------

USER_EXTENSION_PREFIX = "user-"


def user_extensions_root(data_root: str | Path, profile_id: str) -> Path:
    """Directory holding user-imported extensions for one profile."""
    return Path(data_root) / profile_id / "extensions"


def _safe_dir_name(raw: str) -> str:
    """Turn an arbitrary source name into a safe ``user-`` folder name."""
    kept = "".join(c if c.isalnum() or c in "._-" else "-" for c in raw.strip())
    kept = kept.strip(".-") or "extension"
    return f"{USER_EXTENSION_PREFIX}{kept[:60]}"


def _resolve_display_name(manifest: dict, ext_dir: Path) -> str:
    """Resolve a ``__MSG_xxx__`` manifest name against the bundled locales."""
    name = str(manifest.get("name", "")).strip()
    match = re.fullmatch(r"__MSG_(\w+)__", name)
    if not match:
        return name or "未命名扩展"
    default_locale = str(manifest.get("default_locale", "en")).replace("-", "_")
    for locale in (default_locale, "en"):
        messages = ext_dir / "_locales" / locale / "messages.json"
        if not messages.exists():
            continue
        try:
            table = json.loads(messages.read_text(encoding="utf-8-sig"))
        except ValueError:
            continue
        entry = table.get(match.group(1)) if isinstance(table, dict) else None
        message = entry.get("message") if isinstance(entry, dict) else None
        if message:
            return str(message)
    return name


def _collect_leaves(buf: bytes, leaves: list) -> None:
    """Collect every length-delimited leaf from a protobuf, bounds-safely."""
    pos, end = 0, len(buf)
    while pos < end:
        try:
            key = buf[pos]
            pos += 1
            wire = key & 0x07
            if wire == 0:
                while pos < end and buf[pos] & 0x80:
                    pos += 1
                pos += 1
            elif wire == 1:
                pos += 8
            elif wire == 5:
                pos += 4
            elif wire == 2:
                length = 0
                shift = 0
                while True:
                    b = buf[pos]
                    pos += 1
                    length |= (b & 0x7F) << shift
                    shift += 7
                    if not b & 0x80:
                        break
                if pos + length > end:
                    return
                leaves.append(buf[pos:pos + length])
                _collect_leaves(buf[pos:pos + length], leaves)
                pos += length
            else:
                return
        except IndexError:
            return


def _store_id_for_key(key_der: bytes) -> str:
    """Chromium extension ID for a public key: SHA256[:16] hex-mapped a-p."""
    digest = hashlib.sha256(key_der).digest()[:16]
    return "".join(
        chr(ord("a") + (b >> 4)) + chr(ord("a") + (b & 0x0F)) for b in digest
    )


def _proto_fields(buf: bytes) -> list[tuple[int, bytes]]:
    """Top-level protobuf fields as (field_number, value); bounds-safely."""
    out: list[tuple[int, bytes]] = []
    pos, end = 0, len(buf)
    while pos < end:
        try:
            key = buf[pos]
            pos += 1
            field, wire = key >> 3, key & 0x07
            if wire == 2:
                length = 0
                shift = 0
                while True:
                    b = buf[pos]
                    pos += 1
                    length |= (b & 0x7F) << shift
                    shift += 7
                    if not b & 0x80:
                        break
                if pos + length > end:
                    return out
                out.append((field, buf[pos:pos + length]))
                pos += length
            elif wire == 0:
                while pos < end and buf[pos] & 0x80:
                    pos += 1
                pos += 1
            elif wire == 1:
                pos += 8
            elif wire == 5:
                pos += 4
            else:
                return out
        except IndexError:
            return out
    return out


_STORE_ID_RE = re.compile(r"\b[a-p]{32}\b")


def parse_store_extension_id(value: str | None) -> str | None:
    """Accept a bare extension ID or a store URL; return the 32-char ID."""
    if not value:
        return None
    match = _STORE_ID_RE.search(value)
    return match.group(0) if match else None


def _pinned_key_from_crx(crx: bytes, store_id: str) -> str | None:
    """Pick the CRX3 proof key whose SHA256 reproduces ``store_id``.

    The CRX ID is NOT stored in the file: Chromium's verifier matches an
    externally known ID (the store listing URL) against the public keys of
    the header's proofs (field 2 = sha256_with_rsa, field 3 =
    sha256_with_ecdsa). A store CRX may carry several proofs — the developer
    key alongside infra keys — so the externally known ID is the only
    reliable selector. Returns the base64 DER key, or None on no match.
    """
    if len(crx) < 12 or crx[:4] != b"Cr24" or int.from_bytes(crx[4:8], "little") != 3:
        return None
    header = crx[12:12 + int.from_bytes(crx[8:12], "little")]
    # Proof keys sit one level deep: sha256_with_rsa / sha256_with_ecdsa
    # entries are AsymmetricKeyProof messages {signature, public_key}.
    candidates = [v for _, v in _proto_fields(header)]
    candidates += [v for _, value in _proto_fields(header)
                   for _, v in _proto_fields(value)]
    for value in candidates:
        if value[:1] == b"\x00":
            value = value[1:]
        if value[:1] != b"\x30" or len(value) < 64:
            continue
        if _store_id_for_key(value) == store_id:
            return base64.b64encode(value).decode("ascii")
    return None


def import_user_extension(
    data_root: str | Path,
    profile_id: str,
    source: str | Path,
    store_id: str | None = None,
) -> dict:
    """Import an unpacked extension folder or a .crx file into a profile.

    The extension is copied (never referenced in place) into the profile's
    extensions area under a ``user-`` prefix, so the launcher can merge it
    into ``--load-extension``. Raises ValueError with a user-facing message
    when the source is unusable or already imported.
    """
    src = Path(source).expanduser()
    if not src.exists():
        raise ValueError("路径不存在")
    ext_root = user_extensions_root(data_root, profile_id)
    ext_root.mkdir(parents=True, exist_ok=True)

    crx_bytes: bytes | None = None
    if src.is_dir():
        if not (src / "manifest.json").exists():
            raise ValueError("所选目录没有 manifest.json，不是有效的未打包扩展")
        dest = ext_root / _safe_dir_name(src.name)
        if dest.exists():
            raise ValueError(f"扩展 {dest.name} 已存在，请先删除旧版本再导入")
        shutil.copytree(src, dest)
    elif src.suffix.lower() == ".crx":
        crx_bytes = src.read_bytes()
        if not crx_bytes.startswith(b"Cr24"):
            raise ValueError("不是有效的 .crx 文件（缺少 Cr24 头）")
        zip_start = crx_bytes.find(b"PK\x03\x04")
        if zip_start < 0:
            raise ValueError(".crx 内没有找到安装包数据")
        dest = ext_root / _safe_dir_name(src.stem)
        if dest.exists():
            raise ValueError(f"扩展 {dest.name} 已存在，请先删除旧版本再导入")
        with zipfile.ZipFile(io.BytesIO(crx_bytes[zip_start:])) as bundle:
            bundle.extractall(dest)
        if not (dest / "manifest.json").exists():
            shutil.rmtree(dest, ignore_errors=True)
            raise ValueError(".crx 解压后没有 manifest.json，无法导入")
    else:
        raise ValueError("请选择未打包扩展目录或 .crx 文件")

    try:
        manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8-sig"))
    except ValueError:
        manifest = None
    if not isinstance(manifest, dict):
        shutil.rmtree(dest, ignore_errors=True)
        raise ValueError("manifest.json 内容无效")

    # Pin the store extension ID when the caller knows it (store URL or bare
    # ID). The CRX file does not record its own ID — Chromium matches an
    # externally known ID against the header's proof keys — and without a pin
    # the unpacked copy gets a path-hash ID, which breaks on sites that CSP-
    # whitelist the store ID (e.g. muse.ai frame-ancestors).
    if "key" not in manifest and crx_bytes is not None:
        expected = parse_store_extension_id(store_id)
        if expected:
            pinned = _pinned_key_from_crx(crx_bytes, expected)
            if pinned:
                manifest["key"] = pinned
                (dest / "manifest.json").write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

    return {
        "id": dest.name,
        "name": _resolve_display_name(manifest, dest),
        "version": str(manifest.get("version", "")),
        "manifest_version": manifest.get("manifest_version"),
        "dir": str(dest),
    }


def list_user_extensions(data_root: str | Path, profile_id: str) -> list[dict]:
    """Summaries of the extensions imported into a profile, sorted by id."""
    ext_root = user_extensions_root(data_root, profile_id)
    if not ext_root.exists():
        return []
    items: list[dict] = []
    for child in sorted(ext_root.iterdir()):
        if not (child.is_dir() and child.name.startswith(USER_EXTENSION_PREFIX)):
            continue
        manifest_path = child / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except ValueError:
            continue
        if not isinstance(manifest, dict):
            continue
        items.append(
            {
                "id": child.name,
                "name": _resolve_display_name(manifest, child),
                "version": str(manifest.get("version", "")),
                "dir": str(child),
            }
        )
    return items


def remove_user_extension(data_root: str | Path, profile_id: str, ext_id: str) -> None:
    """Delete one imported extension directory. Raises ValueError if invalid."""
    if not ext_id.startswith(USER_EXTENSION_PREFIX) or "/" in ext_id or "\\" in ext_id:
        raise ValueError("无效的扩展 ID")
    dest = user_extensions_root(data_root, profile_id) / ext_id
    if not dest.is_dir():
        raise ValueError("扩展不存在")
    shutil.rmtree(dest)


def user_extension_dirs(data_root: str | Path, profile_id: str) -> list[str]:
    """Absolute paths of imported extensions, for --load-extension merging."""
    return [item["dir"] for item in list_user_extensions(data_root, profile_id)]
