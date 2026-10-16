"""Backend file exports.

These exist because the panel used to hand files to the browser instead. Inside
pywebview that silently cancelled them, so 导出档案 had never produced a file
and neither did the newer cookie export.
"""

from pathlib import Path

import pytest

from zencloak.core.exports import (
    ExportError,
    export_dir,
    safe_stem,
    unique_path,
    write_export,
)


def test_writes_the_content_and_reports_the_path(tmp_path):
    result = write_export(tmp_path, "我的档案", "hello", ".json")
    path = Path(result["path"])
    assert path.exists()
    assert path.read_text(encoding="utf-8") == "hello"
    assert result["bytes"] == 5
    assert Path(result["directory"]) == export_dir(tmp_path)


def test_export_dir_sits_beside_backups(tmp_path):
    """One predictable place, matching how backups already work."""
    directory = export_dir(tmp_path)
    assert directory == tmp_path / "exports"
    assert directory.is_dir()


def test_illegal_filename_characters_are_replaced(tmp_path):
    result = write_export(tmp_path, 'a/b\\c:d*e?f"g<h>i|j', "x", ".json")
    name = Path(result["path"]).name
    for char in '/\\:*?"<>|':
        assert char not in name, f"{char!r} 仍在文件名中: {name}"
    assert name.endswith(".json")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("CON", "_CON"),
        ("nul.txt", "_nul.txt"),
        ("COM1", "_COM1"),
        ("   ", "export"),
        ("...", "export"),
        ("trailing.", "trailing"),
        ("  padded  ", "padded"),
    ],
)
def test_safe_stem_handles_windows_reserved_and_blank_names(raw, expected):
    assert safe_stem(raw) == expected


def test_safe_stem_shortens_a_very_long_name():
    assert len(safe_stem("x" * 500)) == 80


def test_a_second_export_does_not_overwrite_the_first(tmp_path):
    """Exporting twice is normal; silently losing the first file is not."""
    first = write_export(tmp_path, "档案", "one", ".json")
    second = write_export(tmp_path, "档案", "two", ".json")
    assert first["path"] != second["path"]
    assert Path(first["path"]).read_text(encoding="utf-8") == "one"
    assert Path(second["path"]).read_text(encoding="utf-8") == "two"
    assert "(2)" in Path(second["path"]).name


def test_unique_path_keeps_counting_past_two(tmp_path):
    directory = export_dir(tmp_path)
    (directory / "a.json").write_text("1", encoding="utf-8")
    (directory / "a (2).json").write_text("2", encoding="utf-8")
    assert unique_path(directory, "a", ".json").name == "a (3).json"


def test_suffix_is_normalised(tmp_path):
    with_dot = write_export(tmp_path, "a", "x", ".json")
    without_dot = write_export(tmp_path, "b", "x", "json")
    assert Path(with_dot["path"]).suffix == ".json"
    assert Path(without_dot["path"]).suffix == ".json"


def test_suffix_can_be_empty_for_a_full_name(tmp_path):
    """The cookie export passes the whole name, extension included."""
    result = write_export(tmp_path, "档案-cookies.txt", "x", "")
    assert Path(result["path"]).name == "档案-cookies.txt"


def test_a_directory_in_the_way_is_skipped_not_reused(tmp_path):
    """A directory cannot be written to, so it counts as taken.

    Reusing the name would raise IsADirectoryError; taking the next number
    keeps the export working and leaves the directory alone.
    """
    blocked = export_dir(tmp_path)
    (blocked / "taken.json").mkdir()
    result = write_export(tmp_path, "taken", "x", ".json")
    assert Path(result["path"]).name == "taken (2).json"
    assert Path(result["path"]).is_file()
    assert (blocked / "taken.json").is_dir(), "不应破坏同名目录"


def test_write_failure_is_reported_as_an_export_error(tmp_path, monkeypatch):
    """An OS-level failure surfaces as ExportError, not a traceback."""
    import zencloak.core.exports as exports_module

    def boom(self, *args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(exports_module.Path, "write_text", boom, raising=False)
    with pytest.raises(ExportError):
        write_export(tmp_path, "whatever", "x", ".json")
