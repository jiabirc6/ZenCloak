import json
import os
import secrets
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .proxy_runtime import ProxyHandle, allocate_ports
from .subscriptions import load_nodes

MIHOMO_VERSION = "v1.19.29"
MIHOMO_DOWNLOAD_URL = (
    "https://github.com/MetaCubeX/mihomo/releases/download/"
    f"{MIHOMO_VERSION}/mihomo-windows-amd64-{MIHOMO_VERSION}.zip"
)


class MihomoError(RuntimeError):
    """Raised when the mihomo core cannot be prepared or started."""


def _default_bin_dir() -> Path:
    return Path.home() / ".zencloak" / "bin"


def _find_existing_binary(bin_dir: Path) -> Path | None:
    override = os.environ.get("ZENCLOAK_MIHOMO_BINARY")
    if override:
        path = Path(override)
        if path.exists():
            return path
    for name in ("mihomo.exe", "mihomo-windows-amd64.exe"):
        candidate = bin_dir / name
        if candidate.exists():
            if candidate.name != "mihomo.exe":
                target = bin_dir / "mihomo.exe"
                if not target.exists():
                    candidate.rename(target)
                return target
            return candidate
    return None


def _download_binary(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    handlers = (
        [urllib.request.ProxyHandler({"http": proxy, "https": proxy})]
        if proxy
        else []
    )
    opener = urllib.request.build_opener(*handlers)
    zip_path = bin_dir / "mihomo-download.zip"
    try:
        with opener.open(MIHOMO_DOWNLOAD_URL, timeout=60) as response:
            with zip_path.open("wb") as handle:
                shutil.copyfileobj(response, handle)
        with zipfile.ZipFile(zip_path) as archive:
            exe_names = [
                name
                for name in archive.namelist()
                if name.lower().endswith(".exe")
            ]
            if not exe_names:
                raise MihomoError("mihomo 压缩包中未找到可执行文件")
            target = bin_dir / "mihomo.exe"
            with archive.open(exe_names[0]) as source, target.open("wb") as handle:
                shutil.copyfileobj(source, handle)
        return target
    except Exception as exc:
        if isinstance(exc, MihomoError):
            raise
        raise MihomoError(f"mihomo 下载失败: {exc}") from exc
    finally:
        zip_path.unlink(missing_ok=True)


def ensure_binary(bin_dir: Path | None = None) -> Path:
    """Return a usable mihomo executable, downloading it when missing."""
    bin_dir = bin_dir or _default_bin_dir()
    existing = _find_existing_binary(bin_dir)
    if existing:
        return existing
    return _download_binary(bin_dir)


def generate_runtime_config(
    nodes: list[dict[str, Any]],
    ports: list[int],
    secret: str,
) -> dict[str, Any]:
    """Build a minimal global-mode mihomo config for one profile."""
    if len(ports) < 3:
        raise ValueError("需要 mixed/controller/dns 三个端口")
    mixed_port, controller_port, dns_port = ports
    names = [node["name"] for node in nodes]
    return {
        "mixed-port": mixed_port,
        "allow-lan": False,
        "mode": "global",
        "log-level": "silent",
        "external-controller": f"127.0.0.1:{controller_port}",
        "secret": secret,
        "dns": {
            "enable": True,
            "listen": f"127.0.0.1:{dns_port}",
            "nameserver": ["https://dns.alidns.com/dns-query"],
            "fallback": ["https://dns.google/dns-query"],
            "fallback-filter": {"geoip": False},
        },
        "proxies": nodes,
        "proxy-groups": [
            {"name": "GLOBAL", "type": "select", "proxies": names}
        ],
        "rules": ["MATCH,GLOBAL"],
    }


class ProxyManager:
    """Owns one mihomo process per running profile."""

    def __init__(self, data_root: str | Path, binary: Path | None = None) -> None:
        self.data_root = Path(data_root)
        self.binary = binary
        self._handles: dict[str, ProxyHandle] = {}

    def start(
        self,
        profile_id: str,
        nodes: list[dict[str, Any]],
        node_name: str | None = None,
    ) -> ProxyHandle:
        if profile_id in self._handles:
            return self._handles[profile_id]

        binary = self.binary or ensure_binary()
        ports = allocate_ports(3)
        secret = secrets.token_urlsafe(16)
        work_dir = self.data_root / "runtime" / profile_id
        work_dir.mkdir(parents=True, exist_ok=True)
        config = generate_runtime_config(nodes, ports, secret)
        config_path = work_dir / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        log_path = work_dir / "mihomo.log"
        log_handle = log_path.open("a", encoding="utf-8")
        process = subprocess.Popen(
            [
                str(binary),
                "-d",
                str(work_dir),
                "-f",
                str(config_path),
            ],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=0x08000000,
        )
        handle = ProxyHandle(
            profile_id=profile_id,
            mixed_port=ports[0],
            controller_port=ports[1],
            dns_port=ports[2],
            secret=secret,
            work_dir=work_dir,
            config_path=config_path,
            process=process,
            node=node_name,
            status="starting",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self._handles[profile_id] = handle

        try:
            self._wait_ready(handle)
            if node_name:
                self._select_node(handle, node_name)
            handle.status = "running"
            handle.error = None
        except Exception as exc:
            handle.status = "error"
            handle.error = f"{type(exc).__name__}: {exc}"
            self.stop(profile_id)
            raise MihomoError(handle.error) from exc
        return handle

    def stop(self, profile_id: str) -> None:
        handle = self._handles.pop(profile_id, None)
        if handle is None:
            return
        process = handle.process
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    def status(self, profile_id: str) -> dict[str, Any]:
        handle = self._handles.get(profile_id)
        if handle is None:
            return {"profile_id": profile_id, "status": "stopped"}
        return {
            "profile_id": profile_id,
            "status": handle.status,
            "node": handle.node,
            "mixed_port": handle.mixed_port,
            "controller_port": handle.controller_port,
            "error": handle.error,
            "started_at": handle.started_at,
        }

    def load_nodes(self, sub_id: str) -> list[dict[str, Any]]:
        return load_nodes(self.data_root, sub_id)

    def _controller_request(
        self,
        handle: ProxyHandle,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"http://127.0.0.1:{handle.controller_port}{path}"
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {handle.secret}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.status == 204:
                return None
            return json.loads(response.read().decode("utf-8"))

    def _wait_ready(self, handle: ProxyHandle, timeout: float = 10.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if handle.process and handle.process.poll() is not None:
                raise MihomoError(
                    f"mihomo 进程提前退出，code={handle.process.returncode}"
                )
            try:
                self._controller_request(handle, "GET", "/version")
                return
            except Exception:
                time.sleep(0.2)
        raise MihomoError("mihomo 控制器启动超时")

    def _select_node(self, handle: ProxyHandle, node_name: str) -> None:
        self._controller_request(
            handle,
            "PUT",
            "/proxies/GLOBAL",
            {"name": node_name},
        )

    def detect_exit_ip(self, profile_id: str, timeout: float = 15.0) -> str:
        handle = self._handles.get(profile_id)
        if handle is None or handle.status != "running":
            raise MihomoError("代理未运行")
        proxy_handler = urllib.request.ProxyHandler(
            {
                "http": f"http://127.0.0.1:{handle.mixed_port}",
                "https": f"http://127.0.0.1:{handle.mixed_port}",
            }
        )
        opener = urllib.request.build_opener(proxy_handler)
        with opener.open("http://api.ipify.org", timeout=timeout) as response:
            return response.read().decode("utf-8").strip()

    SPEEDTEST_ID = "__speedtest__"

    def test_nodes(
        self,
        nodes: list[dict[str, Any]],
        url: str = "http://www.gstatic.com/generate_204",
        timeout_ms: int = 5000,
        workers: int = 16,
    ) -> list[dict[str, Any]]:
        """Measure real proxy latency for nodes via a temporary mihomo core.

        Uses the controller's ``/proxies/{name}/delay`` endpoint — the same
        mechanism Clash-family clients use — so the number reflects a full
        HTTP round trip through the proxy, not a local TCP handshake.
        """
        if not nodes:
            return []
        handle = self.start(self.SPEEDTEST_ID, nodes)
        try:
            def probe(node: dict[str, Any]) -> dict[str, Any]:
                name = str(node.get("name"))
                path = (
                    f"/proxies/{urllib.parse.quote(name, safe='')}/delay"
                    f"?url={urllib.parse.quote(url, safe=':/?=&')}&timeout={timeout_ms}"
                )
                try:
                    data = self._controller_request(handle, "GET", path)
                    return {"node": name, "delay_ms": data.get("delay"), "error": None}
                except Exception as exc:  # noqa: BLE001 - per-node failures are data
                    return {"node": name, "delay_ms": None, "error": str(exc)}

            with ThreadPoolExecutor(max_workers=min(workers, max(1, len(nodes)))) as pool:
                return list(pool.map(probe, nodes))
        finally:
            self.stop(self.SPEEDTEST_ID)
