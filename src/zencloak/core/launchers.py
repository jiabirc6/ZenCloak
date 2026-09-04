"""Pluggable browser kernel adapters (R2).

CloakBrowser stays the default; two extra kernels hedge the single-upstream
risk:

- ``chromium``: vanilla Playwright Chromium. No stealth patches at all - a
  degraded continuity mode that keeps the product alive if CloakBrowser
  disappears (same engine, so profile data directories stay compatible).
- ``camoufox``: Firefox-based stealth fork (MPL-2.0). Optional dependency
  (``pip install "zencloak[camoufox]"`` + ``python -m camoufox fetch``).
  Experimental: upstream had a year-long maintenance gap.

Each adapter returns ``(context, closer)``; the session loop treats the
context as a plain Playwright BrowserContext (open_url/probe/page ops all
work across kernels).
"""

from typing import Any, Callable

KERNELS: list[dict[str, str]] = [
    {"id": "cloak", "label": "CloakBrowser（默认·Chromium stealth）", "stealth": "full"},
    {"id": "camoufox", "label": "Camoufox（实验性·Firefox stealth）", "stealth": "experimental"},
    {"id": "chromium", "label": "标准 Chromium（无隐身·保底）", "stealth": "none"},
]


def _installed(module: str) -> bool:
    """Import metadata check only - never execute the package import.

    ``import camoufox`` has side effects (data cleanup) and costs ~0.7s;
    availability checks must stay cheap because they run on the API path.
    """
    import importlib.util

    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def kernel_availability() -> dict[str, tuple[bool, str | None]]:
    return {
        "cloak": (_installed("cloakbrowser"), None if _installed("cloakbrowser") else "未安装 cloakbrowser"),
        "camoufox": (
            _installed("camoufox"),
            None
            if _installed("camoufox")
            else "未安装：pip install \"zencloak[camoufox]\" 后执行 python -m camoufox fetch",
        ),
        "chromium": (_installed("playwright"), None if _installed("playwright") else "未安装 playwright"),
    }


def _chromium_kwargs(
    profile: dict,
    user_data_dir: str,
    proxy_server: str | None,
    cdp_port: int | None,
    ext_dir: str | None,
) -> dict:
    args = [f"--lang={profile['locale']}"]
    if profile.get("user_agent"):
        args.append(f"--user-agent={profile['user_agent']}")
    if cdp_port:
        args.append(f"--remote-debugging-port={cdp_port}")
    if ext_dir:
        args.append(f"--load-extension={ext_dir}")
    proxy = profile.get("proxy")
    kwargs: dict[str, Any] = {
        "user_data_dir": user_data_dir,
        "headless": False,
        "args": args,
        "accept_downloads": True,
        "locale": profile["locale"],
        "timezone_id": profile["timezone"],
    }
    if proxy_server:
        kwargs["proxy"] = {"server": proxy_server}
    elif proxy:
        server = f"{proxy['type']}://{proxy['host']}:{proxy['port']}"
        entry: dict[str, str] = {"server": server}
        if proxy.get("username"):
            entry["username"] = proxy["username"]
            entry["password"] = proxy.get("password", "")
        kwargs["proxy"] = entry
    else:
        args.append("--no-proxy-server")
    return kwargs


def launch_chromium(
    profile: dict,
    data_root: Any,
    proxy_server: str | None,
    cdp_port: int | None,
    ext_dir: str | None = None,
) -> tuple[Any, Callable[[], None]]:
    from playwright.sync_api import sync_playwright

    kwargs = _chromium_kwargs(
        profile,
        str(data_root / profile["id"]),
        proxy_server,
        cdp_port,
        ext_dir,
    )
    pw = sync_playwright().start()
    try:
        context = pw.chromium.launch_persistent_context(**kwargs)
    except Exception:
        pw.stop()
        raise
    return context, lambda: (context.close(), pw.stop())


def launch_camoufox(
    profile: dict,
    data_root: Any,
    proxy_server: str | None,
    cdp_port: int | None,
    ext_dir: str | None = None,
) -> tuple[Any, Callable[[], None]]:
    try:
        from camoufox.sync_api import Camoufox
    except Exception as exc:
        raise RuntimeError(
            "Camoufox 未安装：pip install \"zencloak[camoufox]\" 后执行 "
            "python -m camoufox fetch"
        ) from exc
    options: dict[str, Any] = {
        "headless": False,
        "persistent_context": True,
        "user_data_dir": str(data_root / profile["id"]),
        "os": "windows",
        "locale": profile["locale"],
        "timezone": profile["timezone"],
        "humanize": bool(profile.get("humanize")),
        "exclude_addons": [],
    }
    proxy = profile.get("proxy")
    if proxy_server:
        options["proxy"] = {"server": proxy_server}
    elif proxy:
        options["proxy"] = {
            "server": f"{proxy['type']}://{proxy['host']}:{proxy['port']}",
            "username": proxy.get("username", ""),
            "password": proxy.get("password", ""),
        }
    cam = Camoufox(**options)
    try:
        context = cam.start()
    except Exception:
        try:
            cam.stop()
        except Exception:  # noqa: BLE001 - best effort cleanup
            pass
        raise
    return context, lambda: (context.close(), cam.stop())


ADAPTERS: dict[str, Callable[..., tuple[Any, Callable[[], None]]]] = {
    "camoufox": launch_camoufox,
    "chromium": launch_chromium,
}


def launch_extra_kernel(
    kernel: str,
    profile: dict,
    data_root: Any,
    proxy_server: str | None,
    cdp_port: int | None,
    ext_dir: str | None = None,
) -> tuple[Any, Callable[[], None]]:
    adapter = ADAPTERS.get(kernel)
    if adapter is None:
        raise RuntimeError(f"未知内核：{kernel}")
    return adapter(profile, data_root, proxy_server, cdp_port, ext_dir)