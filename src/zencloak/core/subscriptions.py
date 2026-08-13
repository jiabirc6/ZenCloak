import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def import_subscription(
    source: str | Path,
    data_root: str | Path,
    name: str | None = None,
) -> dict[str, Any]:
    """Import a Clash/Mihomo YAML and persist its inline proxy nodes."""
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

    proxies = [
        item
        for item in data.get("proxies", [])
        if isinstance(item, dict) and item.get("type") != "direct"
    ]
    if not proxies:
        raise ValueError("订阅中没有可用节点")

    root = Path(data_root) / "subscriptions"
    sub_id = uuid.uuid4().hex[:12]
    sub_dir = root / sub_id
    sub_dir.mkdir(parents=True, exist_ok=True)
    (sub_dir / "source.yaml").write_text(text, encoding="utf-8")
    meta = {
        "id": sub_id,
        "name": name or "未命名订阅",
        "imported_at": _now_iso(),
        "nodes": [
            {
                "name": item.get("name"),
                "type": item.get("type"),
                "server": item.get("server"),
                "port": item.get("port"),
                "region": infer_region(str(item.get("name", ""))),
            }
            for item in proxies
        ],
    }
    (sub_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return meta


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
    """Return full proxy definitions for a stored subscription."""
    sub_dir = Path(data_root) / "subscriptions" / sub_id
    source_path = sub_dir / "source.yaml"
    if not source_path.exists():
        raise ValueError("订阅不存在")
    data = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    return [
        item
        for item in data.get("proxies", [])
        if isinstance(item, dict) and item.get("type") != "direct"
    ]
