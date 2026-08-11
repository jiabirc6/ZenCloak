import html
import json
import uuid
from pathlib import Path


_EXTENSION_JS = """const redirect = document.getElementById("redirect");
if (redirect) {
  const url = redirect.getAttribute("data-url");
  if (url) {
    location.replace(url);
  }
}
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
    return ext_dir
