"""Identifier formats and validation, in one place.

Profile and subscription IDs are 12 lowercase hex characters. That format is
load-bearing for security, not just for looks: IDs come from URL path
parameters and get joined onto filesystem paths, so every module that builds a
path from one has to reject anything else.

This module exists because the pattern had been copy-pasted into six places in
three different styles (``^[0-9a-f]{12}$``, a bare ``[0-9a-f]{12}`` used with
``fullmatch``, and an inline ``re.fullmatch`` call). Changing the ID format
meant finding all six; missing one would silently drop a validation. Import
from here instead of re-declaring the pattern.
"""

import re
from pathlib import Path
from typing import Any

#: Anchored pattern for use with ``re.match``/``search``.
ID_PATTERN = r"^[0-9a-f]{12}$"

#: Same format, unanchored, for use with ``fullmatch`` or Pydantic ``pattern``.
ID_PATTERN_BARE = r"[0-9a-f]{12}"

_ID_RE = re.compile(ID_PATTERN)

#: Human-readable description reused in error messages.
ID_DESCRIPTION = "12 位小写十六进制字符"


def is_valid_id(value: Any) -> bool:
    """Return True when ``value`` is a well-formed 12-hex-character ID."""
    return isinstance(value, str) and _ID_RE.match(value) is not None


def require_id(value: Any, label: str = "ID") -> str:
    """Return ``value`` unchanged when valid, else raise ``ValueError``."""
    if not is_valid_id(value):
        raise ValueError(f"非法{label}: {value!r}")
    return value


def resolve_within(root: str | Path, *parts: str) -> Path:
    """Join ``parts`` onto ``root``, refusing to escape it.

    Resolves symlinks and ``..`` before comparing, so a value that only looks
    contained (``a/../../b``) is still rejected. Callers should validate the ID
    with :func:`require_id` first; this is the backstop that also covers names
    that are not IDs.
    """
    base = Path(root).resolve()
    candidate = base.joinpath(*parts).resolve()
    if not candidate.is_relative_to(base):
        raise ValueError(f"路径越界: {'/'.join(parts)!r}")
    return candidate
