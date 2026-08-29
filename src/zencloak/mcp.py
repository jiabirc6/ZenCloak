"""MCP server exposing ZenCloak to AI assistants (stdio transport).

Runs as a separate process launched by the MCP client
(``python -m zencloak.mcp`` or the ``zencloak-mcp`` console script).
It discovers the running ZenCloak desktop app through
``~/.zencloak/runtime/api.json`` (base URL + token, written by the app)
and proxies tool calls to the local HTTP API, so AI agents can operate
fingerprint browser profiles: launch/stop sessions, open URLs, list
pages, read page text, take screenshots and run health checks.
"""

import json
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("zencloak")


class ApiError(RuntimeError):
    """Raised when the ZenCloak app cannot be reached or returns an error."""


def runtime_file() -> Path:
    return Path.home() / ".zencloak" / "runtime" / "api.json"


def _load_api_config() -> tuple[str, str]:
    info_path = runtime_file()
    if not info_path.exists():
        raise ApiError(
            "ZenCloak 未在运行（找不到 runtime/api.json）。请先启动 ZenCloak 桌面应用。"
        )
    try:
        data = json.loads(info_path.read_text(encoding="utf-8"))
        return data["base_url"], data["token"]
    except (ValueError, KeyError) as exc:
        raise ApiError(f"runtime/api.json 内容无效: {exc}") from exc


def _request(
    method: str,
    path: str,
    payload: dict | None = None,
    params: dict | None = None,
    timeout: float = 60.0,
):
    base_url, token = _load_api_config()
    try:
        response = httpx.request(
            method,
            base_url + path,
            json=payload,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise ApiError(f"无法连接 ZenCloak 本地服务: {exc}") from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise ApiError(f"ZenCloak API 错误 {response.status_code}: {detail}")
    if response.status_code == 204 or not response.content:
        return {"ok": True}
    return response.json()


def list_profiles() -> list[dict]:
    """列出全部指纹档案（含 id、名称、代理、时区、运行状态摘要所需字段）。"""
    return _request("GET", "/api/profiles")


def list_sessions() -> list[dict]:
    """列出当前会话状态（哪些档案在运行、启动时间、错误信息）。"""
    return _request("GET", "/api/sessions")


def launch_session(profile_id: str) -> dict:
    """启动指定档案的浏览器窗口。"""
    return _request("POST", f"/api/sessions/{profile_id}/launch")


def stop_session(profile_id: str) -> dict:
    """停止指定档案的浏览器窗口。"""
    return _request("POST", f"/api/sessions/{profile_id}/stop")


def open_url(profile_id: str, url: str) -> dict:
    """在指定档案的浏览器里打开一个 http/https 网址（新标签页）。"""
    return _request(
        "POST",
        f"/api/sessions/{profile_id}/open",
        payload={"url": url},
    )


def list_pages(profile_id: str) -> list[dict]:
    """列出指定档案浏览器当前打开的标签页（索引、URL、标题）。"""
    return _request("GET", f"/api/sessions/{profile_id}/pages")


def read_page(profile_id: str, index: int, max_chars: int = 12000) -> dict:
    """读取指定标签页的正文文本（按 index，见 list_pages；内容截断到 max_chars）。"""
    return _request(
        "GET",
        f"/api/sessions/{profile_id}/pages/{index}/content",
        params={"max_chars": max_chars},
        timeout=90.0,
    )


def screenshot_page(profile_id: str, index: int) -> dict:
    """对指定标签页截图，返回保存路径（PNG，可用图片查看工具打开）。"""
    return _request(
        "POST",
        f"/api/sessions/{profile_id}/pages/{index}/screenshot",
        timeout=90.0,
    )


def fingerprint_health_check(profile_id: str) -> dict:
    """对运行中的档案做指纹体检，返回 pass/warn/fail 检查项列表。"""
    return _request(
        "POST",
        f"/api/sessions/{profile_id}/health-check",
        timeout=120.0,
    )


def check_consistency(profile_id: str) -> dict:
    """检查档案时区/语言与代理出口 IP 是否一致，返回警告列表。"""
    return _request("GET", f"/api/sessions/{profile_id}/consistency")


for _tool in (
    list_profiles,
    list_sessions,
    launch_session,
    stop_session,
    open_url,
    list_pages,
    read_page,
    screenshot_page,
    fingerprint_health_check,
    check_consistency,
):
    mcp.tool()(_tool)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
