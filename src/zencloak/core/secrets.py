"""DPAPI-backed encryption for secrets that must persist on this machine.

Proxy passwords are stored as ``CryptProtectData`` ciphertext, which is bound
to the current Windows user account. Decrypting on another machine or user
fails by design; the store falls back to the raw value in that case.

The WinDLL handles are created with ``use_last_error=True`` and get explicit
argtypes/restype, so a failed call can be reported with a meaningful Win32
error code instead of an unrelated, stale one. Without that flag ctypes does
not capture the calling thread's LastError, and ``ctypes.get_last_error()``
returns whatever an earlier unrelated call happened to leave behind.
"""

import base64
import ctypes
from ctypes import wintypes

_CRYPTPROTECT_UI_FORBIDDEN = 0x1


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _load_crypt32() -> ctypes.WinDLL:
    """Load crypt32 with proper error capture and prototypes."""
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    blob_ptr = ctypes.POINTER(DATA_BLOB)
    crypt32.CryptProtectData.argtypes = [
        blob_ptr,  # pDataIn
        wintypes.LPCWSTR,  # szDataDescr
        blob_ptr,  # pOptionalEntropy
        ctypes.c_void_p,  # pvReserved
        ctypes.c_void_p,  # pPromptStruct
        wintypes.DWORD,  # dwFlags
        blob_ptr,  # pDataOut
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        blob_ptr,  # pDataIn
        ctypes.POINTER(wintypes.LPWSTR),  # ppszDataDescr
        blob_ptr,  # pOptionalEntropy
        ctypes.c_void_p,  # pvReserved
        ctypes.c_void_p,  # pPromptStruct
        wintypes.DWORD,  # dwFlags
        blob_ptr,  # pDataOut
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    return crypt32


_crypt32 = _load_crypt32()
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.LocalFree.argtypes = [ctypes.c_void_p]
_kernel32.LocalFree.restype = ctypes.c_void_p


def _free_blob(blob: DATA_BLOB) -> None:
    if blob.pbData:
        _kernel32.LocalFree(ctypes.cast(blob.pbData, ctypes.c_void_p))


def _error_message(prefix: str) -> str:
    """Build an error message from the *current* Win32 last-error value."""
    code = ctypes.get_last_error()
    if not code:
        return prefix
    try:
        detail = ctypes.FormatError(code).strip()
    except Exception:  # noqa: BLE001 - never mask the original failure
        detail = ""
    return f"{prefix} (Win32 错误 {code}: {detail})" if detail else f"{prefix} (Win32 错误 {code})"


def _wipe(buffer: ctypes.Array) -> None:
    """Best-effort scrub of a plaintext buffer before it is released."""
    try:
        ctypes.memset(buffer, 0, ctypes.sizeof(buffer))
    except Exception:  # noqa: BLE001 - scrubbing must never raise
        pass


def encrypt_text(text: str) -> str:
    data = text.encode("utf-8")
    buffer = ctypes.create_string_buffer(data)
    blob = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    out = DATA_BLOB()
    ok = _crypt32.CryptProtectData(
        ctypes.byref(blob),
        None,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out),
    )
    if not ok:
        raise OSError(_error_message("CryptProtectData failed"))
    try:
        encrypted = ctypes.string_at(out.pbData, out.cbData)
        return base64.b64encode(encrypted).decode("ascii")
    finally:
        _free_blob(out)
        _wipe(buffer)


def decrypt_text(encoded: str) -> str:
    data = base64.b64decode(encoded)
    buffer = ctypes.create_string_buffer(data)
    blob = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    out = DATA_BLOB()
    description = wintypes.LPWSTR()
    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(blob),
        ctypes.byref(description),
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out),
    )
    if not ok:
        raise OSError(_error_message("CryptUnprotectData failed"))
    try:
        return ctypes.string_at(out.pbData, out.cbData).decode("utf-8")
    finally:
        _free_blob(out)
        _wipe(buffer)
        # CryptUnprotectData may allocate a description string we do not use;
        # it must be released with the same allocator.
        if description:
            _kernel32.LocalFree(ctypes.cast(description, ctypes.c_void_p))
