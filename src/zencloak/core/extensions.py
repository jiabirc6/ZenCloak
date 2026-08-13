import json
import shutil
from pathlib import Path


def _background_js() -> str:
    return """function translateUrl(url) {
  return (
    "https://translate.google.com/translate?sl=auto&tl=zh-CN&u=" +
    encodeURIComponent(url || "")
  );
}

function translateActiveTab() {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs && tabs[0];
    if (tab && tab.url && tab.url.startsWith("http")) {
      chrome.tabs.create({ url: translateUrl(tab.url) });
    }
  });
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "zencloak-translate-page",
    title: "ZenCloak 翻译本页",
    contexts: ["page"]
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "zencloak-translate-page" && tab && tab.url) {
    chrome.tabs.create({ url: translateUrl(tab.url) });
  }
});

chrome.commands.onCommand.addListener((command) => {
  if (command === "translate-page") {
    translateActiveTab();
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message && message.type === "zencloak-translate" && message.url) {
    chrome.tabs.create({ url: message.url });
    sendResponse({ ok: true });
    return true;
  }
});
"""


def _content_js() -> str:
    return """(() => {
  if (window.__zencloakTranslateButton) return;
  window.__zencloakTranslateButton = true;

  const button = document.createElement("button");
  button.id = "zencloakTranslateBtn";
  button.type = "button";
  button.title = "用 Google 翻译打开本页";
  button.textContent = "翻译本页";
  Object.assign(button.style, {
    position: "fixed",
    right: "18px",
    bottom: "18px",
    zIndex: "2147483647",
    padding: "9px 14px",
    border: "0",
    borderRadius: "8px",
    background: "#0f766e",
    color: "#fff",
    font: "500 14px/1.2 'Microsoft YaHei', 'PingFang SC', sans-serif",
    boxShadow: "0 4px 14px rgba(15, 118, 110, 0.35)",
    cursor: "pointer"
  });

  button.addEventListener("click", () => {
    const target =
      "https://translate.google.com/translate?sl=auto&tl=zh-CN&u=" +
      encodeURIComponent(window.location.href);
    window.location.href = target;
  });

  document.documentElement.appendChild(button);
})();
"""


def build_newtab_extension(
    profile: dict, data_root: str | Path, dir_name: str = "newtab-v3"
) -> Path:
    """Write the ZenCloak helper extension: blank new tab plus page translate."""
    ext_dir = Path(data_root) / profile["id"] / "extensions" / dir_name
    ext_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "manifest_version": 3,
        "name": "ZenCloak Helper",
        "version": "1.1.0",
        "description": "ZenCloak new-tab and page translation helper.",
        "chrome_url_overrides": {"newtab": "newtab.html"},
        "background": {"service_worker": "background.js"},
        "content_scripts": [
            {
                "matches": ["http://*/*", "https://*/*"],
                "exclude_matches": [
                    "https://*.translate.goog/*",
                    "https://translate.google.com/*",
                ],
                "js": ["content.js"],
                "run_at": "document_idle",
            }
        ],
        "permissions": ["tabs", "contextMenus"],
        "commands": {
            "translate-page": {
                "suggested_key": {"default": "Alt+Shift+T"},
                "description": "翻译当前页面",
            }
        },
    }
    (ext_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ext_dir / "newtab.html").write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>ZenCloak</title></head><body></body></html>",
        encoding="utf-8",
    )
    (ext_dir / "background.js").write_text(_background_js(), encoding="utf-8")
    (ext_dir / "content.js").write_text(_content_js(), encoding="utf-8")
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
