import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class PortAllocationError(RuntimeError):
    """Raised when a free TCP port cannot be allocated."""


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def allocate_ports(count: int = 3) -> list[int]:
    """Return distinct free TCP ports for mixed/controller/DNS listeners."""
    if count < 1:
        raise ValueError("count must be >= 1")
    ports: list[int] = []
    seen: set[int] = set()
    for _ in range(count * 10):
        port = _free_port()
        if port not in seen:
            seen.add(port)
            ports.append(port)
        if len(ports) == count:
            return ports
    raise PortAllocationError("无法分配足够的空闲端口")


@dataclass
class ProxyHandle:
    profile_id: str
    mixed_port: int
    controller_port: int
    dns_port: int
    secret: str
    work_dir: Path
    config_path: Path
    process: Any = None
    node: str | None = None
    status: str = "starting"
    error: str | None = None
    started_at: str = ""
