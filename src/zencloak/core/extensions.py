import html
import json
import shutil
import uuid
from pathlib import Path


_EXTENSION_JS = """function redirectToStart() {
  const redirect = document.getElementById("redirect");
  if (!redirect) return;
  const url = redirect.getAttribute("data-url");
  if (url && !location.href.startsWith(url)) {
    location.replace(url);
  }
}
redirectToStart();
const retryTimer = setInterval(() => {
  if (location.href.startsWith("chrome-extension://")) {
    redirectToStart();
  } else {
    clearInterval(retryTimer);
  }
}, 300);
setTimeout(() => clearInterval(retryTimer), 5000);
"""


def _background_js(start_url: str) -> str:
    encoded = json.dumps(start_url)
    return f"""const START_URL = {encoded};

function shouldRedirect(url) {{
  return url.startsWith("chrome://newtab") || url.startsWith("chrome-extension://");
}}

function redirectTab(tabId) {{
  chrome.tabs.get(tabId, (tab) => {{
    const url = (tab && (tab.url || tab.pendingUrl)) || "";
    if (shouldRedirect(url)) {{
      chrome.tabs.update(tabId, {{ url: START_URL }});
    }}
  }});
}}

function scheduleRedirect(tabId) {{
  redirectTab(tabId);
  [200, 500, 1000, 2000, 3000].forEach((delay) => {{
    setTimeout(() => redirectTab(tabId), delay);
  }});
}}

chrome.tabs.onCreated.addListener((tab) => {{
  const url = (tab && (tab.pendingUrl || tab.url)) || "";
  if (shouldRedirect(url)) {{
    scheduleRedirect(tab.id);
  }}
}});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {{
  const url = (changeInfo && changeInfo.url) || (tab && tab.url) || "";
  if (shouldRedirect(url)) {{
    scheduleRedirect(tabId);
  }}
}});
"""


def build_newtab_extension(
    profile: dict, data_root: str | Path, dir_name: str | None = None
) -> Path:
    """Write a Chrome new-tab override extension that redirects to start_url."""
    url = profile["start_url"]
    dir_name = dir_name or f"newtab-{uuid.uuid4().hex[:10]}"
    ext_dir = Path(data_root) / profile["id"] / "extensions" / dir_name
    ext_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "manifest_version": 3,
        "name": "ZenCloak New Tab",
        "version": "1.0.0",
        "description": "Open the profile start page in new tabs.",
        "chrome_url_overrides": {"newtab": "newtab.html"},
        "background": {"service_worker": "background.js"},
        "permissions": ["tabs"],
    }
    (ext_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    escaped_url = html.escape(url, quote=True)
    newtab_html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>ZenCloak</title>
</head>
<body>
<script id="redirect" data-url="{escaped_url}"></script>
<script src="newtab.js"></script>
</body>
</html>"""
    (ext_dir / "newtab.html").write_text(newtab_html, encoding="utf-8")
    (ext_dir / "newtab.js").write_text(_EXTENSION_JS, encoding="utf-8")
    (ext_dir / "background.js").write_text(
        _background_js(url), encoding="utf-8"
    )
    return ext_dir


def cleanup_stale_newtab_extensions(
    profile: dict, data_root: str | Path, keep_dir: str = "newtab-v2"
) -> None:
    """Remove old generated new-tab extensions, keeping only the active one."""
    ext_root = Path(data_root) / profile["id"] / "extensions"
    if not ext_root.exists():
        return
    for child in ext_root.iterdir():
        if (
            child.is_dir()
            and child.name.startswith("newtab")
            and child.name != keep_dir
        ):
            shutil.rmtree(child, ignore_errors=True)
