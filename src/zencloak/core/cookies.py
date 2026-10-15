"""Cookie import and export for a profile.

Chromium keeps its jar in a SQLite database at
``<user_data_dir>/Default/Network/Cookies``. Moving a login between profiles
means reading and writing rows in that file.

Values are not stored in the clear on Windows. Chromium wraps each one with
AES-256-GCM under a per-installation key, and that key is itself protected
with DPAPI, so only the same Windows user on the same machine can unwrap it.
Both layers are handled here - :func:`decrypt_value` - because without them an
export would produce hundreds of empty strings, which is worse than useless.

Two interchange formats are supported, chosen because they are what people
actually have:

* **Netscape / cookies.txt** - what "Get cookies.txt"-style extensions and
  ``curl --cookie-jar`` produce. Tab-separated, one cookie per line.
* **JSON** - the array-of-objects shape those same extensions export.

No new dependency is needed for the database (``sqlite3`` is stdlib); the AES
layer uses ``cryptography``, which is declared in pyproject.toml.
"""

from __future__ import annotations

import base64
import ctypes
import json
import sqlite3
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any, Iterable

#: Where Chromium keeps the jar inside a user-data dir. The ``Default``
#: profile name is fixed because ZenCloak never creates a second one.
COOKIE_DB_PARTS = ("Default", "Network", "Cookies")

#: Chromium's ``cookies.samesite`` column: -1 unset, 0 none, 1 lax, 2 strict.
_SAMESITE_TO_COLUMN = {"no_restriction": 0, "unspecified": -1, "lax": 1, "strict": 2}
_COLUMN_TO_SAMESITE = {-1: "unspecified", 0: "no_restriction", 1: "lax", 2: "strict"}

#: Seconds between 1601-01-01 (Chromium's epoch) and 1970-01-01.
_WINDOWS_EPOCH_OFFSET = 11_644_473_600

#: Chromium seals v10 values with a 32-byte hash bound to the cookie's domain.
#: The plaintext value follows it, so it has to be skipped on the way out. It
#: cannot be recomputed here (that needs the app-bound key), but it does not
#: need to be: writes go through the unencrypted ``value`` column, which
#: Chromium reads in preference to ``encrypted_value``.
_DOMAIN_BINDING_PREFIX = 32


class CookieError(RuntimeError):
    """Raised when a jar cannot be read, parsed or written."""


def cookie_db_path(user_data_dir: str | Path) -> Path:
    """Return the cookie database path for a profile's user-data dir."""
    return Path(user_data_dir).joinpath(*COOKIE_DB_PARTS)


# --------------------------------------------------------------------------
# Chromium's own encryption
# --------------------------------------------------------------------------


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _dpapi_unprotect(data: bytes) -> bytes:
    """Strip DPAPI protection from raw bytes.

    ``core.secrets`` exposes the same call, but it decodes the result as UTF-8
    because it is built for password strings. The cookie key is raw binary, so
    the primitive is repeated here rather than mangled through a text API.
    """
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]

    buffer = ctypes.create_string_buffer(data)
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    out = _DataBlob()
    description = wintypes.LPWSTR()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(blob),
        ctypes.byref(description),
        None,
        None,
        None,
        1,  # CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(out),
    )
    if not ok:
        raise CookieError(
            f"DPAPI 解密失败 (错误码 {ctypes.get_last_error()})；"
            "该密钥由当前 Windows 用户绑定，换机器或换用户后无法解开"
        )
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))
        if description:
            kernel32.LocalFree(ctypes.cast(description, ctypes.c_void_p))


def master_key(user_data_dir: str | Path) -> bytes:
    """Return the AES key Chromium uses for this user-data dir.

    It lives in ``Local State`` under ``os_crypt.encrypted_key``, prefixed with
    the literal ``DPAPI`` marker that must be stripped before unwrapping.
    """
    state_path = Path(user_data_dir) / "Local State"
    if not state_path.exists():
        raise CookieError("找不到 Local State，无法取得解密密钥")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CookieError(f"Local State 读取失败: {exc}") from exc
    encoded = (state.get("os_crypt") or {}).get("encrypted_key")
    if not encoded:
        raise CookieError("Local State 中没有 os_crypt.encrypted_key")
    raw = base64.b64decode(encoded)
    if raw[:5] != b"DPAPI":
        raise CookieError("加密密钥不是 DPAPI 封装（可能是其他平台或已损坏）")
    return _dpapi_unprotect(raw[5:])


def decrypt_value(blob: bytes, key: bytes) -> str:
    """Decrypt one ``encrypted_value`` cell into its plaintext string.

    Handles the ``v10`` layout (3-byte version + 12-byte nonce + ciphertext).
    Older Chromium wrote ``v20`` with app-bound encryption; those cannot be
    unwrapped without the app's own key, so they raise rather than silently
    yielding an empty string.
    """
    if not blob:
        return ""
    if blob[:3] == b"v20":
        raise CookieError("该 Cookie 使用 v20 (app-bound) 加密，无法在外部解密")
    if blob[:3] != b"v10":
        raise CookieError(f"未知的 Cookie 加密格式: {blob[:3]!r}")
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise CookieError("缺少 cryptography 依赖，无法解密 Cookie") from exc
    nonce, payload = blob[3:15], blob[15:]
    try:
        plain = AESGCM(key).decrypt(nonce, payload, None)
    except Exception as exc:  # noqa: BLE001 - any failure is "cannot decrypt"
        raise CookieError(f"Cookie 解密失败: {exc}") from exc
    return strip_domain_binding(plain)


def strip_domain_binding(plain: bytes) -> str:
    """Drop Chromium's 32-byte domain-binding prefix and decode what follows.

    Every v10 value carries this prefix: measured across a real 221-cookie jar,
    the prefix was identical for every cookie on a given host, and one cookie's
    entire plaintext was exactly the 32 bytes with nothing after it. So this is
    a fixed offset, not something to detect.

    The prefix is arbitrary binary, which is why it cannot be spotted by trying
    to decode it - roughly one byte in eight is valid UTF-8 by chance, and one
    real prefix contained a ``\\n``. Assuming the offset is what makes the
    decode deterministic.
    """
    body = plain[_DOMAIN_BINDING_PREFIX:] if len(plain) > _DOMAIN_BINDING_PREFIX else b""
    return body.decode("utf-8", "replace")


# --------------------------------------------------------------------------
# Read / write the jar
# --------------------------------------------------------------------------


def _windows_epoch(expires: Any) -> float:
    """Normalise an expiry to a unix timestamp.

    Chromium stores ``expires_utc`` as microseconds since 1601-01-01, while
    every export format uses unix seconds. Accept either, and treat nonsense
    (0, negative, unparseable) as a session cookie.
    """
    if expires in (None, "", 0):
        return 0.0
    try:
        value = float(expires)
    except (TypeError, ValueError):
        return 0.0
    if value <= 0:
        return 0.0
    # Anything past year 3000 in unix seconds must be the 1601-based value.
    if value > 10_000_000_000:
        return value / 1_000_000 - _WINDOWS_EPOCH_OFFSET
    return value


def read_cookies(
    user_data_dir: str | Path, *, decrypt: bool = True
) -> list[dict[str, Any]]:
    """Read the jar as plain dicts.

    Opens read-only so a running browser is not disturbed. When ``decrypt`` is
    set (the default) encrypted values are unwrapped; if the key is
    unavailable the cookies are still returned, with ``decrypted: False`` and
    an empty value, rather than failing the whole read.
    """
    path = cookie_db_path(user_data_dir)
    if not path.exists():
        return []
    try:
        # Immutable mode avoids taking a write lock on a jar a browser may
        # still have open.
        uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True, timeout=5)
    except sqlite3.Error as exc:
        raise CookieError(f"无法打开 Cookie 数据库: {exc}") from exc

    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT host_key, path, name, value, encrypted_value, expires_utc,
                   is_secure, is_httponly, samesite
            FROM cookies
            """
        ).fetchall()
    except sqlite3.Error as exc:
        raise CookieError(f"无法读取 Cookie 表: {exc}") from exc
    finally:
        connection.close()

    key: bytes | None = None
    if decrypt:
        try:
            key = master_key(user_data_dir)
        except CookieError:
            key = None

    cookies: list[dict[str, Any]] = []
    for row in rows:
        value = row["value"] or ""
        decrypted = True
        if not value and row["encrypted_value"]:
            if key is not None:
                try:
                    value = decrypt_value(bytes(row["encrypted_value"]), key)
                except CookieError:
                    value, decrypted = "", False
            else:
                decrypted = False
        cookies.append(
            {
                "domain": row["host_key"],
                "path": row["path"],
                "name": row["name"],
                "value": value,
                "expires": _windows_epoch(row["expires_utc"]),
                "secure": bool(row["is_secure"]),
                "http_only": bool(row["is_httponly"]),
                "same_site": _COLUMN_TO_SAMESITE.get(row["samesite"], "unspecified"),
                "decrypted": decrypted,
            }
        )
    return cookies


def write_cookies(user_data_dir: str | Path, cookies: list[dict[str, Any]]) -> int:
    """Merge cookies into the profile's jar; returns how many rows were written.

    Existing rows with the same (host, path, name) are replaced, which is what
    a browser does on an updated Set-Cookie. Cookies already present that this
    import does not mention are left alone.

    Values go into the plaintext column and ``encrypted_value`` is cleared, so
    Chromium reads what was written without needing the key. That means the
    jar on disk holds these particular values in the clear until the browser
    next rewrites them, which is the same trade-off every cookie-import tool
    makes.
    """
    path = cookie_db_path(user_data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        connection = sqlite3.connect(path, timeout=5)
    except sqlite3.Error as exc:
        raise CookieError(f"无法打开 Cookie 数据库: {exc}") from exc

    written = 0
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cookies (
                creation_utc INTEGER NOT NULL DEFAULT 0,
                host_key TEXT NOT NULL,
                top_frame_site_key TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL,
                value TEXT NOT NULL DEFAULT '',
                encrypted_value BLOB NOT NULL DEFAULT X'',
                path TEXT NOT NULL DEFAULT '/',
                expires_utc INTEGER NOT NULL DEFAULT 0,
                is_secure INTEGER NOT NULL DEFAULT 0,
                is_httponly INTEGER NOT NULL DEFAULT 0,
                last_access_utc INTEGER NOT NULL DEFAULT 0,
                has_expires INTEGER NOT NULL DEFAULT 0,
                is_persistent INTEGER NOT NULL DEFAULT 0,
                priority INTEGER NOT NULL DEFAULT 1,
                samesite INTEGER NOT NULL DEFAULT -1,
                source_scheme INTEGER NOT NULL DEFAULT 0,
                source_port INTEGER NOT NULL DEFAULT -1,
                last_update_utc INTEGER NOT NULL DEFAULT 0,
                source_type INTEGER NOT NULL DEFAULT 0,
                has_cross_site_ancestor INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # Chromium does not declare the cookie key as a table constraint; it
        # creates a separate index over seven columns:
        #   (host_key, top_frame_site_key, has_cross_site_ancestor, name, path,
        #    source_scheme, source_port)
        # An ON CONFLICT clause naming only four of them does not match any
        # constraint, and SQLite rejects the statement outright - which is what
        # happened against a real jar. Create the same index and let the
        # delete-then-insert below do the replacing, so this does not depend on
        # guessing the conflict target.
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS cookies_unique_index
            ON cookies(host_key, top_frame_site_key, has_cross_site_ancestor,
                       name, path, source_scheme, source_port)
            """
        )
        now = int(time.time() * 1_000_000) + _WINDOWS_EPOCH_OFFSET * 1_000_000
        for cookie in cookies:
            expires = _windows_epoch(cookie.get("expires"))
            expires_utc = (
                int(expires * 1_000_000) + _WINDOWS_EPOCH_OFFSET * 1_000_000
                if expires
                else 0
            )
            host_key = str(cookie.get("domain") or "")
            name = str(cookie.get("name") or "")
            path = str(cookie.get("path") or "/")
            # Delete on the name and path alone, and let the unique index
            # decide what "the same cookie" means. Matching on the other
            # four index columns would mean guessing their values: a real jar
            # has rows with has_cross_site_ancestor = 1 and source_scheme = 2,
            # while an insert with the defaults writes 0 and 1, so a delete
            # that spelled those out removed nothing and the insert added a
            # duplicate row instead of replacing.
            connection.execute(
                "DELETE FROM cookies WHERE host_key = ? AND name = ? AND path = ?",
                (host_key, name, path),
            )
            try:
                connection.execute(
                    """
                    INSERT INTO cookies (
                        creation_utc, host_key, top_frame_site_key, name, value,
                        encrypted_value, path, expires_utc, is_secure, is_httponly,
                        last_access_utc, has_expires, is_persistent, priority,
                        samesite, source_scheme, source_port, last_update_utc,
                        source_type, has_cross_site_ancestor
                    ) VALUES (?, ?, '', ?, ?, X'', ?, ?, ?, ?, ?, ?, ?, 1, ?, 1, 443, ?, 0, 0)
                    """,
                    (
                        now,
                        host_key,
                        name,
                        str(cookie.get("value") or ""),
                        path,
                        expires_utc,
                        1 if cookie.get("secure") else 0,
                        1 if cookie.get("http_only") else 0,
                        now,
                        1 if expires else 0,
                        1 if expires else 0,
                        _SAMESITE_TO_COLUMN.get(
                            str(cookie.get("same_site") or "").lower(), -1
                        ),
                        now,
                    ),
                )
            except sqlite3.IntegrityError:
                # A row differing only in the columns this import does not set
                # (a partitioned or non-https variant) still exists. Replace it
                # in place rather than failing the whole import.
                connection.execute(
                    """
                    UPDATE cookies
                    SET value = ?, encrypted_value = X'', expires_utc = ?,
                        is_secure = ?, is_httponly = ?, samesite = ?,
                        last_update_utc = ?
                    WHERE host_key = ? AND name = ? AND path = ?
                    """,
                    (
                        str(cookie.get("value") or ""),
                        expires_utc,
                        1 if cookie.get("secure") else 0,
                        1 if cookie.get("http_only") else 0,
                        _SAMESITE_TO_COLUMN.get(
                            str(cookie.get("same_site") or "").lower(), -1
                        ),
                        now,
                        host_key,
                        name,
                        path,
                    ),
                )
            written += 1
        connection.commit()
    except sqlite3.Error as exc:
        connection.rollback()
        raise CookieError(
            f"写入 Cookie 失败: {exc}（档案正在运行时会占用数据库，请先停止）"
        ) from exc
    finally:
        connection.close()
    return written


# --------------------------------------------------------------------------
# Interchange formats
# --------------------------------------------------------------------------


def _one_line(value: str) -> str:
    """Make a value safe for the tab-separated, one-cookie-per-line format.

    A cookie value is arbitrary bytes, and Chromium's jar does contain values
    with newlines and tabs in them. Writing those raw would split one record
    across lines and shift every field of the next, which is how a single bad
    cookie turned into a parse error 30 lines later. They are percent-encoded,
    which is what the format's own escaping looks like.
    """
    return (
        value.replace("%", "%25")
        .replace("\t", "%09")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
    )


def cookies_to_netscape(cookies: Iterable[dict[str, Any]]) -> str:
    """Render cookies as a Netscape cookies.txt file."""
    lines = [
        "# Netscape HTTP Cookie File",
        "# Exported by ZenCloak",
        "",
    ]
    for cookie in cookies:
        domain = str(cookie.get("domain") or "")
        # The second column is TRUE when the cookie applies to subdomains,
        # which is what a leading dot encodes.
        include_sub = "TRUE" if domain.startswith(".") else "FALSE"
        expires = int(_windows_epoch(cookie.get("expires")) or 0)
        lines.append(
            "\t".join(
                [
                    domain,
                    include_sub,
                    str(cookie.get("path") or "/"),
                    "TRUE" if cookie.get("secure") else "FALSE",
                    str(expires),
                    str(cookie.get("name") or ""),
                    _one_line(str(cookie.get("value") or "")),
                ]
            )
        )
    return "\n".join(lines) + "\n"


def cookies_to_json(cookies: Iterable[dict[str, Any]]) -> str:
    """Render cookies in the array-of-objects shape the common extensions use."""
    payload = []
    for cookie in cookies:
        payload.append(
            {
                "domain": cookie.get("domain") or "",
                "path": cookie.get("path") or "/",
                "name": cookie.get("name") or "",
                "value": cookie.get("value") or "",
                "expirationDate": _windows_epoch(cookie.get("expires")) or None,
                "secure": bool(cookie.get("secure")),
                "httpOnly": bool(cookie.get("http_only")),
                "sameSite": cookie.get("same_site") or "unspecified",
            }
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_cookies(text: str, fmt: str = "auto") -> list[dict[str, Any]]:
    """Parse a cookies.txt or JSON export into the dicts :func:`read_cookies` gives.

    ``fmt`` of ``auto`` sniffs the content, which is what the UI uses: users
    should not have to say which format a file is in.
    """
    # Only newlines and a leading BOM may be trimmed. A blanket strip() would
    # eat the trailing tab of a final cookie whose value is empty, turning a
    # valid 7-column line into 6 and failing the parse.
    body = (text or "").lstrip("\ufeff").strip("\r\n")
    if not body.strip():
        raise CookieError("文件内容为空")
    if fmt == "auto":
        fmt = "json" if body.lstrip()[0] in "[{" else "netscape"
    if fmt == "json":
        return _parse_json(body)
    return _parse_netscape(body)


def _parse_json(body: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise CookieError(f"JSON 解析失败: {exc}") from exc
    if isinstance(data, dict):
        # Some exports wrap the array under a key.
        for key in ("cookies", "data", "items"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise CookieError("JSON 结构不是 Cookie 数组")

    cookies: list[dict[str, Any]] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise CookieError(f"第 {index + 1} 项不是对象")
        name = str(item.get("name") or "").strip()
        domain = str(item.get("domain") or item.get("host") or "").strip()
        if not name or not domain:
            raise CookieError(f"第 {index + 1} 项缺少 name 或 domain")
        cookies.append(
            {
                "domain": domain,
                "path": str(item.get("path") or "/"),
                "name": name,
                "value": str(item.get("value") or ""),
                "expires": _windows_epoch(
                    item.get("expirationDate", item.get("expires"))
                ),
                "secure": bool(item.get("secure")),
                "http_only": bool(item.get("httpOnly", item.get("http_only"))),
                "same_site": str(
                    item.get("sameSite", item.get("same_site")) or "unspecified"
                ).lower(),
            }
        )
    if not cookies:
        raise CookieError("没有解析到任何 Cookie")
    return cookies


def _unescape_one_line(value: str) -> str:
    """Reverse :func:`_one_line`."""
    return (
        value.replace("%0A", "\n")
        .replace("%0D", "\r")
        .replace("%09", "\t")
        .replace("%25", "%")
    )


def _parse_netscape(body: str) -> list[dict[str, Any]]:
    cookies: list[dict[str, Any]] = []
    for lineno, raw in enumerate(body.splitlines(), start=1):
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        # Tab-separated per the format. Splitting on tabs without stripping
        # trailing ones keeps an empty value as the 7th field instead of
        # collapsing it away, which is why this does not use str.split().
        parts = line.split("\t")
        if len(parts) < 7:
            # Tolerate files an editor re-saved with spaces instead of tabs,
            # but only when that interpretation actually yields 7 columns.
            collapsed = line.split(maxsplit=6)
            if len(collapsed) == 7:
                parts = collapsed
        if len(parts) < 7:
            raise CookieError(f"第 {lineno} 行字段不足（需要 7 列，实际 {len(parts)}）")
        domain, _include_sub, path, secure, expires, name, value = parts[:7]
        if not name.strip() or not domain.strip():
            raise CookieError(f"第 {lineno} 行缺少 name 或 domain")
        cookies.append(
            {
                "domain": domain.strip(),
                "path": path.strip() or "/",
                "name": name.strip(),
                "value": _unescape_one_line(value),
                "expires": _windows_epoch(expires),
                "secure": secure.strip().upper() == "TRUE",
                "http_only": False,
                "same_site": "unspecified",
            }
        )
    if not cookies:
        raise CookieError("没有解析到任何 Cookie")
    return cookies
