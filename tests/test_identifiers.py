"""Tests for the shared identifier helpers.

These exist so the ID format lives in one place. It had been copy-pasted into
six modules in three styles, meaning a format change required finding all six
and missing one would silently drop a validation.
"""

from pathlib import Path

import pytest

from zencloak.core.identifiers import (
    ID_PATTERN,
    ID_PATTERN_BARE,
    is_valid_id,
    require_id,
    resolve_within,
)


@pytest.mark.parametrize(
    "value",
    [
        "0123456789ab",
        "abcdefabcdef",
        "000000000000",
        "ffffffffffff",
    ],
)
def test_accepts_twelve_lowercase_hex(value):
    assert is_valid_id(value)
    assert require_id(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "x",
        "0123456789a",  # 11
        "0123456789abc",  # 13
        "0123456789AB",  # uppercase
        "0123456789ag",  # non-hex
        "../../etc",
        "..\\..\\etc",
        "0123456789ab/../..",
        " 0123456789ab",
        "0123456789ab ",  # trailing space
        None,
        123,
        b"0123456789ab",
        ["0123456789ab"],
    ],
)
def test_rejects_everything_else(value):
    assert not is_valid_id(value)
    with pytest.raises(ValueError, match="ID"):
        require_id(value)


def test_require_id_includes_label_in_message():
    with pytest.raises(ValueError, match="档案 ID"):
        require_id("nope", "档案 ID")


def test_pattern_constants_agree():
    """The anchored and bare forms must describe the same format."""
    import re

    sample = "0123456789ab"
    assert re.match(ID_PATTERN, sample)
    assert re.fullmatch(ID_PATTERN_BARE, sample)
    assert not re.fullmatch(ID_PATTERN_BARE, sample + "c")


def test_resolve_within_allows_nested_parts(tmp_path):
    resolved = resolve_within(tmp_path, "aaaaaaaaaaaa", "Downloads")
    assert resolved == (tmp_path / "aaaaaaaaaaaa" / "Downloads").resolve()
    assert resolved.is_relative_to(tmp_path.resolve())


@pytest.mark.parametrize(
    "parts",
    [
        ("..",),
        ("../..",),
        ("../../escaped",),
        ("aaaaaaaaaaaa", "..", "..", "escaped"),
        ("a/b/../../../escaped",),
    ],
)
def test_resolve_within_rejects_escapes(tmp_path, parts):
    with pytest.raises(ValueError, match="路径越界"):
        resolve_within(tmp_path, *parts)


def test_resolve_within_accepts_path_objects(tmp_path):
    resolved = resolve_within(Path(tmp_path), "aaaaaaaaaaaa")
    assert resolved.is_relative_to(Path(tmp_path).resolve())
