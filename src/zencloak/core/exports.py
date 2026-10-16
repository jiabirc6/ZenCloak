"""Write exported files to disk on the backend.

The panel used to hand files to the browser with a Blob and an ``<a download>``.
Inside pywebview that silently does nothing: its EdgeChromium backend cancels
every download unless ``webview.settings['ALLOW_DOWNLOADS']`` is set, and the
default is False. No dialog, no error, no file - clicking 导出 looked like it
worked and produced nothing. The same path was used by the older profile
export, so that had silently never worked either.

Writing on the backend avoids the whole question. It behaves the same in a
packaged build, does not depend on a webview setting, and can put the file
somewhere predictable instead of wherever the browser's download folder
happens to be.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

#: Characters Windows forbids in a filename. A profile name is user input and
#: may contain any of them.
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

#: Reserved device names, which cannot be used even with an extension.
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

_MAX_STEM = 80


class ExportError(RuntimeError):
    """Raised when an export cannot be written."""


def safe_stem(name: str, fallback: str = "export") -> str:
    """Reduce a user-supplied name to something usable as a filename stem.

    Keeps it recognisable rather than hashing it: the point of the export is
    for a person to find the file later by name.
    """
    text = _ILLEGAL.sub("_", str(name or "")).strip()
    # Trailing dots and spaces are stripped by Windows itself, which turns a
    # name ending in "." into a different name than requested.
    text = text.strip(" .")
    if not text:
        return fallback
    if text.split(".")[0].upper() in _RESERVED:
        text = f"_{text}"
    return text[:_MAX_STEM]


def export_dir(store_root: str | Path) -> Path:
    """Where exports land: ``<data root>/exports``.

    Alongside ``backups/``, which already works this way, so a user looking for
    something ZenCloak saved has one place to look.
    """
    path = Path(store_root) / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def unique_path(directory: Path, stem: str, suffix: str) -> Path:
    """Pick a filename that is free to write.

    Exports of the same profile are expected to repeat, and overwriting the
    previous one silently would lose the file the user still wanted.

    A directory counts as taken: it cannot be written to, and skipping it here
    means the caller gets the name it asked for instead of a numbered variant
    that then fails.
    """
    candidate = directory / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate
    for index in range(2, 1000):
        candidate = directory / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
    # Falling back to a timestamp keeps the write from failing outright.
    return directory / f"{stem}-{time.strftime('%Y%m%d-%H%M%S')}{suffix}"


def _split_suffix(name: str) -> tuple[str, str]:
    """Split ``name`` into stem and extension, keeping a leading dot.

    ``Path.stem``/``suffix`` treat ".gitignore" as having no extension and
    ".txt" as a bare extension, which would mangle the cookie export's
    "profile-cookies.txt" when the caller passes the whole name.
    """
    text = str(name or "")
    dot = text.rfind(".")
    if dot <= 0 or dot == len(text) - 1:
        return text, ""
    return text[:dot], text[dot:]


def write_export(
    store_root: str | Path, name: str, content: str, suffix: str
) -> dict[str, object]:
    """Write ``content`` under the export directory and describe the result.

    ``name`` may either be a bare stem with ``suffix`` supplied separately, or
    a complete filename with an empty ``suffix`` - the cookie export writes
    "profile-cookies.txt" and "profile-cookies.json", which differ in more than
    an extension.

    Returns the absolute path so the UI can show where the file went and offer
    to open the folder - the complaint that started this was not knowing where
    an export had gone.
    """
    directory = export_dir(store_root)
    if suffix:
        stem = safe_stem(name)
        if not suffix.startswith("."):
            suffix = f".{suffix}"
    else:
        # The caller's string already carries its extension; sanitise the stem
        # and keep the extension verbatim rather than letting safe_stem's
        # trailing-dot trim move it.
        raw_stem, suffix = _split_suffix(name)
        stem = safe_stem(raw_stem) + suffix
        suffix = ""
    target = unique_path(directory, stem, suffix)
    try:
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise ExportError(f"写入失败: {exc}") from exc
    return {
        "path": str(target),
        "directory": str(directory),
        "name": target.name,
        "bytes": target.stat().st_size,
    }
