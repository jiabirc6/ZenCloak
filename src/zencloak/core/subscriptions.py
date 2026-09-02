import json
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

REGION_KEYWORDS = (
    ("美国", "US"),
    ("洛杉矶", "US"),
    ("LSP", "US"),
    ("US", "US"),
    ("香港", "HK"),
    ("HK", "HK"),
    ("日本", "JP"),
    ("JP", "JP"),
    ("新加坡", "SG"),
    ("狮城", "SG"),
    ("SG", "SG"),
    ("台湾", "TW"),
    ("TW", "TW"),
    ("韩国", "KR"),
    ("KR", "KR"),
    ("德国", "DE"),
    ("DE", "DE"),
    ("英国", "GB"),
    ("UK", "GB"),
)


def infer_region(node_name: str) -> str | None:
    upper = node_name.upper()
    for keyword, region in REGION_KEYWORDS:
        if keyword in upper:
            return region
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_url(url: str, timeout: float = 30.0) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "clash.meta"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def _parse_provider_proxies(text: str) -> list[dict]:
    """Extract proxy dicts from a provider response (clash YAML config)."""
    try:
        data = yaml.safe_load(text)
    except Exception:  # noqa: BLE001 - provider content may be any format
        return []
    if isinstance(data, dict) and isinstance(data.get("proxies"), list):
        return [
            item
            for item in data["proxies"]
            if isinstance(item, dict) and item.get("type") != "direct"
        ]
    return []


def _expand_providers(
    providers: dict, fetch: Callable[[str], str]
) -> tuple[list[dict], dict[str, str]]:
    """Fetch every proxy-provider URL and merge their nodes.

    Applies the provider's ``override.additional-prefix`` to node names so
    nodes from different airports stay distinguishable. Returns the extra
    proxies plus a per-provider status map for diagnostics.
    """
    extra: list[dict] = []
    status: dict[str, str] = {}
    for name, cfg in (providers or {}).items():
        if not isinstance(cfg, dict):
            continue
        url = cfg.get("url")
        if not url:
            status[name] = "skipped: 无 url"
            continue
        prefix = (cfg.get("override") or {}).get("additional-prefix") or ""
        try:
            proxies = _parse_provider_proxies(fetch(str(url)))
        except Exception as exc:  # noqa: BLE001 - one bad provider must not fail import
            status[name] = f"error: {type(exc).__name__}: {exc}"
            continue
        for item in proxies:
            extra.append({**item, "name": f"{prefix}{item.get('name', '')}"})
        status[name] = f"ok: {len(proxies)}"
    return extra, status


def _inline_proxies(data: dict) -> list[dict]:
    return [
        item
        for item in data.get("proxies", [])
        if isinstance(item, dict) and item.get("type") != "direct"
    ]


def _meta_nodes(proxies: list[dict]) -> list[dict]:
    return [
        {
            "name": item.get("name"),
            "type": item.get("type"),
            "server": item.get("server"),
            "port": item.get("port"),
            "region": infer_region(str(item.get("name", ""))),
        }
        for item in proxies
    ]


def _write_subscription(
    sub_dir: Path,
    sub_id: str,
    name: str,
    text: str,
    proxies: list[dict],
    provider_status: dict[str, str],
    imported_at: str | None = None,
) -> dict[str, Any]:
    meta = {
        "id": sub_id,
        "name": name,
        "imported_at": imported_at or _now_iso(),
        "updated_at": _now_iso(),
        "providers": provider_status,
        "nodes": _meta_nodes(proxies),
    }
    (sub_dir / "source.yaml").write_text(text, encoding="utf-8")
    (sub_dir / "resolved.yaml").write_text(
        yaml.safe_dump({"proxies": proxies}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (sub_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return meta


def import_subscription(
    source: str | Path,
    data_root: str | Path,
    name: str | None = None,
    fetch: Callable[[str], str] = _fetch_url,
) -> dict[str, Any]:
    """Import a Clash/Mihomo YAML, expanding inline and provider nodes."""
    if isinstance(source, Path):
        text = Path(source).read_text(encoding="utf-8")
    else:
        text = source
    try:
        data = yaml.safe_load(text)
    except Exception as exc:
        raise ValueError(f"订阅格式错误: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("订阅内容不是有效的 YAML 配置")

    proxies = _inline_proxies(data)
    provider_proxies, provider_status = _expand_providers(
        data.get("proxy-providers") or {}, fetch
    )
    proxies = proxies + provider_proxies
    if not proxies:
        raise ValueError("订阅中没有可用节点")

    root = Path(data_root) / "subscriptions"
    sub_id = uuid.uuid4().hex[:12]
    sub_dir = root / sub_id
    sub_dir.mkdir(parents=True, exist_ok=True)
    return _write_subscription(sub_dir, sub_id, name or "未命名订阅", text, proxies, provider_status)


def refresh_subscription(
    data_root: str | Path,
    sub_id: str,
    fetch: Callable[[str], str] = _fetch_url,
) -> dict[str, Any]:
    """Re-fetch proxy-providers for a stored subscription and rebuild nodes."""
    sub_dir = Path(data_root) / "subscriptions" / sub_id
    source_path = sub_dir / "source.yaml"
    if not source_path.exists():
        raise ValueError("订阅不存在")
    text = source_path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    existing = json.loads((sub_dir / "meta.json").read_text(encoding="utf-8"))
    proxies = _inline_proxies(data)
    provider_proxies, provider_status = _expand_providers(
        data.get("proxy-providers") or {}, fetch
    )
    proxies = proxies + provider_proxies
    if not proxies:
        raise ValueError("订阅中没有可用节点")
    return _write_subscription(
        sub_dir,
        sub_id,
        existing.get("name") or "未命名订阅",
        text,
        proxies,
        provider_status,
        imported_at=existing.get("imported_at"),
    )


def list_subscriptions(data_root: str | Path) -> list[dict[str, Any]]:
    root = Path(data_root) / "subscriptions"
    if not root.exists():
        return []
    items = []
    for child in sorted(root.iterdir()):
        meta_path = child / "meta.json"
        if meta_path.exists():
            try:
                items.append(
                    json.loads(meta_path.read_text(encoding="utf-8"))
                )
            except (OSError, json.JSONDecodeError):
                continue
    return items


def get_subscription(
    data_root: str | Path, sub_id: str
) -> dict[str, Any] | None:
    meta_path = Path(data_root) / "subscriptions" / sub_id / "meta.json"
    if not meta_path.exists():
        return None
    return json.loads(meta_path.read_text(encoding="utf-8"))


def load_nodes(data_root: str | Path, sub_id: str) -> list[dict[str, Any]]:
    """Return full proxy definitions for a stored subscription.

    Prefers ``resolved.yaml`` (inline + expanded providers); falls back to
    ``source.yaml`` for subscriptions imported before provider expansion.
    """
    sub_dir = Path(data_root) / "subscriptions" / sub_id
    resolved_path = sub_dir / "resolved.yaml"
    source_path = sub_dir / "source.yaml"
    if resolved_path.exists():
        path = resolved_path
    elif source_path.exists():
        path = source_path
    else:
        raise ValueError("订阅不存在")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return _inline_proxies(data)
