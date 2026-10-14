# ZenCloak

[![Homepage](https://img.shields.io/badge/Homepage-GitHub%20Pages-black)](https://zc.190003.xyz/)

中文文档：[README.zh.md](README.zh.md)

A personal anti-detect browser desktop client powered by a stealth Chromium kernel.

ZenCloak manages multiple browser identities through "profiles": every profile owns an isolated fingerprint seed, proxy, persistent session and human-like behavior settings, and launches a real browser window with one click.

## 📦 Release highlights

**v0.4.0**
- Pluggable browser kernels: CloakBrowser (default), experimental Camoufox (Firefox stealth), and vanilla Chromium as a no-stealth fallback
- Encrypted full backup / restore: profiles + login state in an AES-256 passphrase-protected archive; running profiles are safely skipped
- TTS voice-pack spoofing: voice lists follow the profile language, eliminating “voice-pack country vs IP country” flags
- CDP attach: external Playwright / Selenium scripts can attach to a running profile browser
- Timezones expanded to 56 and locales to 39 (incl. zh-TW / zh-HK traditional), fully redesigned UI

**v0.3.0**
- Built-in Mihomo proxy: subscription import / refresh / delete, airport node expansion, concurrent real-latency tests, egress IP detection
- Fingerprint health report: one-click deep check of webdriver, WebRTC leaks, Canvas noise, UA and applied settings
- Egress IP consistency pre-check with one-click timezone fix
- MCP server: AI assistants (ZCode / Claude Desktop / Cursor) drive the browser directly
- Recycle bin, batch start/stop, profile import / export / duplicate

Full changelog: [CHANGELOG.md](CHANGELOG.md).

## Download

Latest release: [ZenCloak Setup](https://github.com/jiabirc6/ZenCloak/releases/latest)

Every release ships **two installers**. Both install the same application and need no admin rights — the only difference is how the app is packaged:

| Asset | Startup | Packaged as | Good for |
|---|---|---|---|
| `ZenCloak-Setup-<version>-dir.exe` | **~1–2 s** | A folder | Everyday use |
| `ZenCloak-Setup-<version>.exe` | ~20 s | A single file | Copying to a USB stick |

The single-file build unpacks its dependencies to a temp folder on every start, which is what costs the extra ~18 s. The folder build keeps them on disk and starts immediately. Not sure? Either is fine — you can switch later by installing the other one.

On first browser launch, if the CloakBrowser kernel is missing, ZenCloak downloads the ~200 MB stealth Chromium binary automatically and caches it under `~/.cloakbrowser/`.

## Features

- Multiple fingerprint profiles: seed, timezone, locale, screen, CPU cores, device memory, User-Agent
- Pluggable browser kernels: CloakBrowser (default), experimental Camoufox (Firefox stealth), vanilla Chromium as a no-stealth fallback
- Built-in Mihomo proxy: subscription import / refresh / delete, airport node expansion, region filtering, concurrent latency tests (real proxy delay), egress IP detection
- Manual HTTP / SOCKS5 proxy with username & password; passwords encrypted at rest via Windows DPAPI
- Consistency pre-check: compares egress IP geolocation against the profile timezone / locale, warns on mismatch and fixes the timezone in one click
- TTS voice spoofing: rewrites the speechSynthesis voice list to match the profile locale, fixing "voice pack country vs IP country" anomalies
- Fingerprint health report: one-click deep check of webdriver traces, WebRTC leaks, Canvas noise, UA and applied settings
- Human-like mouse, keyboard and scrolling behavior (`humanize`)
- Isolated persistent profiles: cookies, login state and history per profile
- One-click launch / stop, batch start/stop, recycle bin, profile import / export / duplicate
- Encrypted full backup: all profiles + login state into an AES-256 passphrase-protected archive
- Built-in entries to BrowserScan, FingerprintJS, BrowserLeaks and Incolumitas
- MCP server: let AI assistants (ZCode / Claude Desktop / Cursor) drive the browser directly (see [docs/mcp.md](docs/mcp.md))
- CDP attach mode: external Playwright / Selenium scripts can attach to a running profile (see [docs/attach.md](docs/attach.md))
- Local API bound to `127.0.0.1` on a random port, Bearer-token protected
- First run auto-creates a "Local" profile matching your machine (Windows / Asia/Shanghai / zh-CN)

## Requirements

- Windows 10 / 11 (x64)
- Python 3.12 (development mode only)
- No Node.js needed; a working CloakBrowser binary is fetched automatically

## Install (development)

```powershell
python -m pip install -e .
python -m cloakbrowser install   # download the stealth Chromium binary
```

## Run

Packaged users: launch ZenCloak from the Start Menu shortcut the installer created (no console window).

Development mode:

```powershell
python -m zencloak
```

> Keep the terminal open while `python -m zencloak` runs. To build your own installers, including the fast-start onedir variant (~1–2 s vs ~20 s), see [docs/packaging.md](docs/packaging.md).

## Usage

1. After first launch, a "Local" profile appears in the sidebar.
2. Click "新建档案" (New profile) to create an identity; configure fingerprint, proxy and behavior as needed.
3. "保存" (Save) writes the profile to `~/.zencloak/profiles/`.
4. "启动" (Launch) opens the profile's CloakBrowser window; browser data lives in `~/.zencloak/data/<profile-id>/`.
5. While running, use the detection-site buttons to open fingerprint check pages inside the stealth browser.

## Data directory

```
~/.zencloak/
├── profiles/          # fingerprint profile JSON files
├── data/              # persistent browser data per profile
└── backups/           # encrypted backup archives
```

## Project structure

```
src/zencloak/
├── app.py             # desktop entry: uvicorn + pywebview
├── api.py             # local FastAPI
├── mcp.py             # MCP server for AI assistants
├── core/
│   ├── fingerprint.py # fingerprint parameters & default profile
│   ├── models.py      # profile schema & validation
│   ├── profiles.py    # profile JSON storage
│   ├── sessions.py    # CloakBrowser session management
│   ├── mihomo.py      # built-in Mihomo proxy & real latency tests
│   ├── subscriptions.py # subscription import / node expansion / refresh
│   ├── consistency.py # egress IP vs fingerprint pre-check
│   ├── health.py      # fingerprint health probes & report
│   ├── backup.py      # encrypted backup / restore
│   └── secrets.py     # DPAPI encryption
└── ui/                # desktop UI (HTML / CSS / JS)
```

## AI assistant integration (MCP)

ZenCloak ships an MCP server so ZCode / Claude Desktop / Cursor can launch profiles, open URLs, read pages, take screenshots and run health checks. Setup and tool list: [docs/mcp.md](docs/mcp.md).

## Tests

```powershell
python -m pytest
```

Includes real CloakBrowser smoke tests verifying `navigator.webdriver=false`, a clean User-Agent and a sane plugin list.

## FAQ

**Why does opening `src/zencloak/ui/index.html` directly show "not connected"?**

The UI needs the local API. Always start via `dist\ZenCloak.exe` or `python -m zencloak`.

**What is the `Update available: cloakbrowser ...` message?**

It is CloakBrowser's upgrade notice and does not affect operation. The current v146 kernel is free and login-less; newer kernels may require a CloakBrowser account.

**Where are proxy passwords stored?**

Encrypted with Windows DPAPI inside the profile JSON — decryptable only by the current user on this machine. Never commit `~/.zencloak/` or exported profiles to a public repository. After restoring a backup on a different machine, re-enter proxy passwords once per profile.

## License

This wrapper and client code are MIT licensed, see [LICENSE](LICENSE). The CloakBrowser binary is subject to its own license, see [CloakBrowser BINARY-LICENSE](https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md). Use this tool only for lawful, authorized purposes.