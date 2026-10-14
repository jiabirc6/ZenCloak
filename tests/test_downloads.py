"""Tests for restoring the real filename on downloads.

Chromium writes the file itself when ``downloads_path`` is configured, naming
it with an internal UUID and dropping the site's filename. The extension goes
with it, and the extension is what decides which program opens the file: a
downloaded video arrived as ``c258c1f1-89fc-4a4f-a13f-50a761c1e10c``, and
double-clicking it did nothing until ``.mp4`` was added by hand.
"""

from pathlib import Path

import pytest

from zencloak.core.downloads import (
    looks_like_uuid,
    remove_placeholder,
    safe_filename,
    unique_path,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("movie.mp4", "movie.mp4"),
        ("report.pdf", "report.pdf"),
        ("archive.tar.gz", "archive.tar.gz"),
        # The extension is the whole point, so a name must keep it.
        ("My Video.MP4", "My Video.MP4"),
        ("../escape.mp4", "escape.mp4"),
        ("..\\escape.mp4", "escape.mp4"),
        ("/abs/path/clip.mp4", "clip.mp4"),
        ("bad<>:x?.mp4", "bad___x_.mp4"),
        ("CON.mp4", "_CON.mp4"),
        ("nul.txt", "_nul.txt"),
        ("trailing.  ", "trailing"),
        ("", "download"),
        ("   ", "download"),
        ("noext", "noext"),
        (".hidden", ".hidden"),
    ],
)
def test_safe_filename_keeps_the_extension(raw, expected):
    assert safe_filename(raw) == expected


def test_long_names_are_truncated_but_keep_the_extension():
    result = safe_filename("a" * 400 + ".mp4")
    assert result.endswith(".mp4")
    assert len(result) <= 130


def test_unique_path_numbers_like_a_browser(tmp_path):
    assert unique_path(tmp_path, "a.mp4").name == "a.mp4"
    (tmp_path / "a.mp4").write_text("x", encoding="utf-8")
    assert unique_path(tmp_path, "a.mp4").name == "a (1).mp4"
    (tmp_path / "a (1).mp4").write_text("x", encoding="utf-8")
    assert unique_path(tmp_path, "a.mp4").name == "a (2).mp4"


def test_unique_path_handles_names_without_extension(tmp_path):
    (tmp_path / "plain").write_text("x", encoding="utf-8")
    assert unique_path(tmp_path, "plain").name == "plain (1)"


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("c258c1f1-89fc-4a4f-a13f-50a761c1e10c", True),
        ("0aa18444-dfa7-4ff1-a9bd-69f3f9ae5e28", True),
        ("movie", False),
        ("c258c1f1-89fc-4a4f-a13f", False),
        ("zzzzzzzz-89fc-4a4f-a13f-50a761c1e10c", False),
        ("", False),
    ],
)
def test_looks_like_uuid(stem, expected):
    assert looks_like_uuid(stem) is expected


def test_remove_placeholder_deletes_uuid_named_file(tmp_path):
    placeholder = tmp_path / "c258c1f1-89fc-4a4f-a13f-50a761c1e10c"
    placeholder.write_text("x", encoding="utf-8")
    keep = tmp_path / "movie.mp4"
    keep.write_text("y", encoding="utf-8")

    remove_placeholder(placeholder, keep, attempts=1)

    assert not placeholder.exists()
    assert keep.exists()


def test_remove_placeholder_never_touches_the_saved_file(tmp_path):
    """A real file that happens to look like a UUID must survive."""
    keep = tmp_path / "report.pdf"
    keep.write_text("content", encoding="utf-8")
    remove_placeholder(keep, keep, attempts=1)
    assert keep.exists()


def test_remove_placeholder_ignores_non_uuid_names(tmp_path):
    other = tmp_path / "unrelated.txt"
    other.write_text("x", encoding="utf-8")
    remove_placeholder(other, tmp_path / "keep.txt", attempts=1)
    assert other.exists()


def test_remove_placeholder_tolerates_missing_file(tmp_path):
    remove_placeholder(tmp_path / "a1b2c3d4-1111-2222-3333-444455556666", tmp_path / "k", attempts=1)


def test_remove_placeholder_accepts_none(tmp_path):
    remove_placeholder(None, tmp_path / "k", attempts=1)


class _FakeDownload:
    """Minimal stand-in for a Playwright Download object."""

    def __init__(self, suggested, payload, placeholder: Path | None = None):
        self.suggested_filename = suggested
        self._payload = payload
        self._placeholder = placeholder

    def path(self):
        return str(self._placeholder) if self._placeholder else None

    def save_as(self, target):
        Path(target).write_bytes(self._payload)


def test_save_with_real_name_writes_the_extension(tmp_path):
    from zencloak.core.downloads import save_with_real_name

    download = _FakeDownload("movie.mp4", b"VIDEO")
    saved = save_with_real_name(download, tmp_path)
    assert saved is not None
    assert saved.name == "movie.mp4"
    assert saved.suffix == ".mp4"
    assert saved.read_bytes() == b"VIDEO"


def test_save_with_real_name_creates_missing_directory(tmp_path):
    from zencloak.core.downloads import save_with_real_name

    target_dir = tmp_path / "not" / "there"
    saved = save_with_real_name(_FakeDownload("a.mp4", b"x"), target_dir)
    assert saved is not None and saved.exists()


def test_save_with_real_name_avoids_overwriting(tmp_path):
    from zencloak.core.downloads import save_with_real_name

    first = save_with_real_name(_FakeDownload("clip.mp4", b"one"), tmp_path)
    second = save_with_real_name(_FakeDownload("clip.mp4", b"two"), tmp_path)
    assert first.name == "clip.mp4"
    assert second.name == "clip (1).mp4"
    assert first.read_bytes() == b"one"
    assert second.read_bytes() == b"two"


def test_save_with_real_name_falls_back_when_save_as_fails(tmp_path):
    """A failing save_as copies the placeholder instead of losing the file."""
    from zencloak.core.downloads import save_with_real_name

    placeholder = tmp_path / "c258c1f1-89fc-4a4f-a13f-50a761c1e10c"
    placeholder.write_bytes(b"PAYLOAD")

    class Failing(_FakeDownload):
        def save_as(self, target):
            raise OSError("save_as unavailable")

    download = Failing("movie.mp4", b"", placeholder)
    saved = save_with_real_name(download, tmp_path)
    assert saved is not None
    assert saved.name == "movie.mp4"
    assert saved.read_bytes() == b"PAYLOAD"


def test_save_with_real_name_returns_none_without_any_source(tmp_path):
    from zencloak.core.downloads import save_with_real_name

    class Broken(_FakeDownload):
        def save_as(self, target):
            raise OSError("nope")

    assert save_with_real_name(Broken("x.mp4", b"", None), tmp_path) is None


def test_attach_download_handler_registers_on_context(tmp_path):
    from zencloak.core.downloads import attach_download_handler

    recorded = {}

    class FakeContext:
        def on(self, event, handler):
            recorded[event] = handler

    attach_download_handler(FakeContext(), tmp_path)
    assert "download" in recorded


def test_attach_download_handler_survives_missing_event(tmp_path):
    """Older kernels may not expose the download event; that must not raise."""
    from zencloak.core.downloads import attach_download_handler

    class NoDownloadEvent:
        def on(self, event, handler):
            raise ValueError("unknown event")

    attach_download_handler(NoDownloadEvent(), tmp_path)


def test_attach_download_handler_saves_and_notifies(tmp_path):
    from zencloak.core.downloads import attach_download_handler

    saved_names = []

    class FakeContext:
        def __init__(self):
            self.handler = None

        def on(self, event, handler):
            self.handler = handler

    context = FakeContext()
    attach_download_handler(context, tmp_path, on_saved=lambda p: saved_names.append(p.name))
    context.handler(_FakeDownload("clip.mp4", b"data"))

    assert (tmp_path / "clip.mp4").read_bytes() == b"data"
    assert saved_names == ["clip.mp4"]
