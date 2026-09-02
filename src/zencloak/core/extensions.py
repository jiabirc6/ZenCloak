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

function createContextMenu() {
  chrome.contextMenus.create({
    id: "zencloak-translate-page",
    title: "ZenCloak 翻译本页",
    contexts: ["page"]
  });
}

createContextMenu();
chrome.runtime.onInstalled.addListener(createContextMenu);
chrome.runtime.onStartup.addListener(createContextMenu);

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

  function translate() {
    const target =
      "https://translate.google.com/translate?sl=auto&tl=zh-CN&u=" +
      encodeURIComponent(window.location.href);
    window.location.href = target;
  }

  const button = document.createElement("button");
  button.id = "zencloakTranslateBtn";
  button.type = "button";
  button.title = "用 Google 翻译打开本页";
  button.textContent = "翻译本页";
  const BOTTOM_GAP = 120;
  Object.assign(button.style, {
    position: "fixed",
    right: "18px",
    bottom: BOTTOM_GAP + "px",
    zIndex: "2147483647",
    padding: "9px 14px",
    border: "0",
    borderRadius: "8px",
    background: "#0f766e",
    color: "#fff",
    font: "500 14px/1.2 'Microsoft YaHei', 'PingFang SC', sans-serif",
    boxShadow: "0 4px 14px rgba(15, 118, 110, 0.35)",
    cursor: "grab",
    opacity: "0.35",
    transition: "opacity 0.2s ease",
    userSelect: "none"
  });

  function layoutFromAnchors() {
    const rect = button.getBoundingClientRect();
    button.style.left = Math.max(window.innerWidth - rect.width - 18, 0) + "px";
    button.style.top = Math.max(window.innerHeight - rect.height - BOTTOM_GAP, 0) + "px";
    button.style.right = "auto";
    button.style.bottom = "auto";
  }

  let dragging = false;
  let moved = false;
  let startX = 0;
  let startY = 0;
  let startLeft = 0;
  let startTop = 0;

  button.addEventListener("mouseenter", () => {
    button.style.opacity = "1";
  });
  button.addEventListener("mouseleave", () => {
    button.style.opacity = "0.35";
  });
  button.addEventListener("mousedown", (event) => {
    if (event.button !== 0) return;
    dragging = true;
    moved = false;
    startX = event.clientX;
    startY = event.clientY;
    const rect = button.getBoundingClientRect();
    startLeft = rect.left;
    startTop = rect.top;
    event.preventDefault();
  });
  document.addEventListener("mousemove", (event) => {
    if (!dragging) return;
    const dx = event.clientX - startX;
    const dy = event.clientY - startY;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) moved = true;
    const left = Math.min(
      Math.max(startLeft + dx, 0),
      Math.max(window.innerWidth - button.offsetWidth, 0)
    );
    const top = Math.min(
      Math.max(startTop + dy, 0),
      Math.max(window.innerHeight - button.offsetHeight, 0)
    );
    button.style.left = left + "px";
    button.style.top = top + "px";
    button.style.right = "auto";
    button.style.bottom = "auto";
  });
  document.addEventListener("mouseup", (event) => {
    if (!dragging) return;
    dragging = false;
    if (moved) return;
    const rect = button.getBoundingClientRect();
    if (
      event.clientX >= rect.left &&
      event.clientX <= rect.right &&
      event.clientY >= rect.top &&
      event.clientY <= rect.bottom
    ) {
      translate();
    }
  });
  window.addEventListener("resize", () => {
    if (!dragging && button.style.right !== "auto") layoutFromAnchors();
  });

  document.documentElement.appendChild(button);
  layoutFromAnchors();
})();
"""


def build_newtab_extension(
    profile: dict, data_root: str | Path, dir_name: str = "newtab-v3"
) -> Path:
    """Write the ZenCloak helper extension: blank new tab plus page translate."""
    ext_dir = Path(data_root) / profile["id"] / "extensions" / dir_name
    ext_dir.mkdir(parents=True, exist_ok=True)

    # 注意：故意不声明 chrome_url_overrides。这个内核里扩展接管 NTP 会让
    # 点 + 同时产生"第三方宿主页 + 扩展页"两个目标（双标签的根源）；转圈
    # 的 NTP 由 SessionManager 的 CDP sweep 统一关掉并补空白页。
    manifest = {
        "manifest_version": 3,
        "name": "ZenCloak Helper",
        "version": "1.2.0",
        "description": "ZenCloak page translation helper.",
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
