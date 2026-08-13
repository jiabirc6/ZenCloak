import json
import shutil
from pathlib import Path


def _background_js(start_url: str) -> str:
    encoded = json.dumps(start_url)
    return f"""const START_URL = {encoded};

function shouldRedirect(url) {{
  return (
    url.startsWith("chrome://newtab") ||
    url.startsWith("chrome-extension://") ||
    url.startsWith("chrome://new-tab-page-third-party")
  );
}}

function redirectTab(tabId) {{
  chrome.tabs.get(tabId, (tab) => {{
    const url = (tab && (tab.url || tab.pendingUrl)) || "";
    if (shouldRedirect(url)) chrome.tabs.update(tabId, {{ url: START_URL }});
  }});
}}

chrome.tabs.onCreated.addListener((tab) => {{
  const url = (tab && (tab.pendingUrl || tab.url)) || "";
  if (shouldRedirect(url)) {{
    redirectTab(tab.id);
    setTimeout(() => redirectTab(tab.id), 300);
    setTimeout(() => redirectTab(tab.id), 800);
    setTimeout(() => redirectTab(tab.id), 1500);
  }}
}});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {{
  const url = (changeInfo && changeInfo.url) || (tab && tab.url) || "";
  if (shouldRedirect(url)) {{
    redirectTab(tabId);
    setTimeout(() => redirectTab(tabId), 300);
  }}
}});
"""


def build_newtab_extension(
    profile: dict, data_root: str | Path, dir_name: str = "newtab-v3"
) -> Path:
    """Write a stable new-tab extension backed by a blank page plus a worker."""
    url = profile.get("start_url") or "about:blank"
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
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ext_dir / "newtab.html").write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>ZenCloak</title></head><body></body></html>",
        encoding="utf-8",
    )
    (ext_dir / "background.js").write_text(_background_js(url), encoding="utf-8")
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
