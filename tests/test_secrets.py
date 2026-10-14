"""Tests for the DPAPI helpers.

Regression guards for two defects fixed here:

1. ``ctypes.windll`` is built with ``use_last_error=False``, so a failed
   CryptProtectData/CryptUnprotectData reported a stale, unrelated error code.
   The DLL handles are now loaded with ``use_last_error=True``, so the code in
   the raised OSError must reflect the call that actually failed.
2. The plaintext input buffer was never scrubbed after use.
"""

import base64
import ctypes

import pytest

from zencloak.core import secrets as secrets_module
from zencloak.core.secrets import decrypt_text, encrypt_text


def test_encrypt_decrypt_roundtrip():
    encrypted = encrypt_text("my-proxy-password")
    assert encrypted != "my-proxy-password"
    assert decrypt_text(encrypted) == "my-proxy-password"


@pytest.mark.parametrize(
    "text",
    ["简单密码", "p@ss:word/with#chars", "", "a" * 300, "emoji-🔐-ok"],
)
def test_roundtrip_edge_cases(text: str):
    assert decrypt_text(encrypt_text(text)) == text


def test_ciphertext_is_not_plaintext():
    encrypted = encrypt_text("secret-value")
    decoded = base64.b64decode(encrypted)
    assert b"secret-value" not in decoded


def test_failure_reports_fresh_win32_error():
    """A failing call must refresh the last-error value, not reuse a stale one.

    ``ctypes.set_last_error`` only takes effect for DLLs loaded with
    ``use_last_error=True``; with the old code the sentinel below would survive
    the failing call and end up in the exception message.
    """
    sentinel = 4242
    ctypes.set_last_error(sentinel)
    with pytest.raises(OSError) as excinfo:
        decrypt_text(base64.b64encode(b"not-a-dpapi-ciphertext").decode("ascii"))

    message = str(excinfo.value)
    assert "CryptUnprotectData failed" in message
    # The real error must have replaced the sentinel.
    assert str(sentinel) not in message
    assert "Win32 错误" in message
    assert ctypes.get_last_error() != sentinel


def test_crypt32_handles_capture_last_error():
    """The module must not use the bare ``ctypes.windll`` lazy loader."""
    assert secrets_module._crypt32._name == "crypt32"
    assert secrets_module._kernel32._name == "kernel32"


def test_function_prototypes_are_declared():
    """Explicit argtypes/restype prevent pointer truncation on 64-bit hosts."""
    assert len(secrets_module._crypt32.CryptProtectData.argtypes) == 7
    assert len(secrets_module._crypt32.CryptUnprotectData.argtypes) == 7
    assert secrets_module._crypt32.CryptProtectData.restype is not None
    assert secrets_module._crypt32.CryptUnprotectData.restype is not None


def test_wipe_zeroes_buffer():
    buffer = ctypes.create_string_buffer(b"top-secret")
    secrets_module._wipe(buffer)
    assert buffer.raw == b"\x00" * len(buffer.raw)


def test_encrypt_handles_unicode_description():
    """Non-ASCII passwords survive the LPCWSTR description parameter."""
    password = "密码-ünïcode"
    assert decrypt_text(encrypt_text(password)) == password
