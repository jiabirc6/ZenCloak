"""Give downloads the filename the site intended.

Chromium is handed ``downloads_path``, so it writes the file itself - and
names it with an internal UUID, dropping the name the site supplied. A
downloaded video landed as ``c258c1f1-89fc-4a4f-a13f-50a761c1e10c``, with no
extension, so Windows had no handler for it and double-clicking did nothing.
Adding ``.mp4`` by hand made the very same file play.

The Playwright ``download`` event does carry the intended name in
``suggested_filename`` (verified for ``Content-Disposition`` with ASCII and
UTF-8 names, and for the ``download`` attribute). Saving through it restores
the extension, which is the part that decides whether the file opens.
``suggested_filename`` already includes the extension even when the page's
``download`` attribute omits it, so no MIME guessing is needed.
"""

import re
import shutil
import time
from pathlib import Path
from typing import Any, Callable

# Windows forbids these in filenames; a site may still send them.
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Reserved device names, with or without an extension.
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_MAX_STEM = 120
# Chromium keeps its own handle open briefly after the event fires.
_REMOVE_ATTEMPTS = 6
_REMOVE_DELAY = 0.35


def safe_filename(name: str, fallback: str = "download") -> str:
    """Turn a server-supplied name into something Windows accepts.

    The extension is preserved: it is what decides which program opens the
    file, so losing it makes the download useless.
    """
    candidate = (name or "").replace("\\", "/").split("/")[-1].strip()
    candidate = _ILLEGAL_CHARS.sub("_", candidate)
    # Only strip trailing dots/spaces here; a leading dot is part of the name
    # (dotfiles such as ".gitignore") and must survive.
    candidate = candidate.rstrip(" .")
    if not candidate:
        return fallback
    if candidate == "." * len(candidate):
        return fallback

    stem, dot, suffix = candidate.rpartition(".")
    # "rpartition" finds a dot at index 0 for dotfiles like ".gitignore",
    # which would leave an empty stem; treat those as having no extension.
    if not dot or not stem:
        return candidate[:_MAX_STEM]
    stem = stem[:_MAX_STEM].rstrip(" .") or fallback
    if stem.upper() in _RESERVED_NAMES:
        stem = f"_{stem}"
    return f"{stem}.{suffix}" if suffix else stem


def unique_path(directory: Path, name: str) -> Path:
    """Return a free path in ``directory``, numbering the name like browsers do."""
    target = directory / name
    if not target.exists():
        return target
    stem, dot, suffix = name.rpartition(".")
    if not dot:
        stem, suffix, dot = name, "", ""
    for index in range(1, 1000):
        candidate = (
            directory / f"{stem} ({index}).{suffix}"
            if dot and suffix
            else directory / f"{stem} ({index})"
        )
        if not candidate.exists():
            return candidate
    return directory / (f"{stem} (copy).{suffix}" if suffix else f"{stem} (copy)")


def looks_like_uuid(stem: str) -> bool:
    """True for Chromium's own placeholder names (8-4-4-4-12 hex)."""
    parts = stem.split("-")
    if len(parts) != 5:
        return False
    sizes = (8, 4, 4, 4, 12)
    return all(
        len(part) == size and all(c in "0123456789abcdefABCDEF" for c in part)
        for part, size in zip(parts, sizes)
    )


def remove_placeholder(
    path: Path | None, keep: Path, attempts: int = _REMOVE_ATTEMPTS
) -> None:
    """Delete Chromium's UUID-named copy once the handle is released.

    Best effort: Chromium usually cleans up after itself a moment later, and a
    stray placeholder is cosmetic next to the file the user actually wants.
    """
    if path is None or path == keep or not looks_like_uuid(path.stem):
        return
    for index in range(attempts):
        if not path.exists():
            return
        try:
            path.unlink()
            return
        except OSError:
            if index == attempts - 1:
                return
            time.sleep(_REMOVE_DELAY)


def save_with_real_name(download: Any, downloads_dir: Path) -> Path | None:
    """Save ``download`` under the name the site supplied.

    Returns the path written, or ``None`` when nothing usable could be saved.
    Must never raise: it runs on the session's event delivery path.
    """
    try:
        downloads_dir = Path(downloads_dir)
        downloads_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    suggested = safe_filename(getattr(download, "suggested_filename", "") or "")
    target = unique_path(downloads_dir, suggested)

    placeholder: Path | None = None
    try:
        raw = getattr(download, "path", None)
        if callable(raw):
            raw = raw()
        if raw:
            placeholder = Path(raw)
    except Exception:  # noqa: BLE001 - locating the placeholder is optional
        placeholder = None

    try:
        download.save_as(str(target))
    except Exception:  # noqa: BLE001 - fall back to copying the placeholder
        if placeholder is not None and placeholder.exists():
            try:
                shutil.copy2(placeholder, target)
            except OSError:
                return None
        else:
            return None

    remove_placeholder(placeholder, target)
    return target


def attach_download_handler(
    context: Any,
    downloads_dir: Path,
    on_saved: Callable[[Path], None] | None = None,
) -> None:
    """Give every download in ``context`` its real filename.

    Registered on the context, not a page: users click download links in pages
    they navigate themselves.
    """

    def _handler(download: Any) -> None:
        saved = save_with_real_name(download, downloads_dir)
        if saved is None or on_saved is None:
            return
        try:
            on_saved(saved)
        except Exception:  # noqa: BLE001 - notification is optional
            pass

    try:
        context.on("download", _handler)
    except Exception:  # noqa: BLE001 - older kernels may lack the event
        pass
