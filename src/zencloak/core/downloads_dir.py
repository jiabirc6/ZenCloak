"""Native folder picker and download-dir resolution.

The browser writes downloads wherever it is told, and the per-profile default
lives deep under the data root where users do not find it. Profiles may point
at any folder on the machine instead, and picking one uses the standard
Windows dialog so the choice feels native.
"""

import threading
from pathlib import Path
from typing import Any


def download_dir_for(store: Any, profile: dict) -> Path:
    """Resolve where a profile's downloads go.

    A custom folder wins; otherwise the per-profile directory under the store's
    data root. Kept in one place so the API, the open-folder action and the
    session launcher cannot drift apart.
    """
    custom = profile.get("download_dir")
    if custom:
        candidate = Path(custom)
        if candidate.is_absolute():
            return candidate
    return store.profile_data_subdir(profile["id"], "Downloads")


def ask_directory(initial: str | Path | None = None, title: str = "选择下载目录") -> str | None:
    """Show the OS folder picker; return the path, or None if cancelled.

    tkinter is used rather than the Win32 shell API because it ships with
    Python and needs no extra dependency. It must own its main loop, so the
    dialog runs in a worker thread with a hidden root window; when the process
    is headless the call degrades to returning None rather than raising.
    """
    result: dict[str, str | None] = {"path": None}
    error: dict[str, BaseException | None] = {"exc": None}

    def _run() -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            try:
                start = None
                if initial:
                    candidate = Path(initial)
                    if candidate.is_dir():
                        start = str(candidate)
                chosen = filedialog.askdirectory(
                    title=title, initialdir=start, mustexist=False
                )
                result["path"] = chosen or None
            finally:
                root.destroy()
        except BaseException as exc:  # noqa: BLE001 - reported to the caller
            error["exc"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=300)

    if thread.is_alive():
        # The dialog is still open; do not pretend it succeeded.
        return None
    if error["exc"] is not None:
        raise error["exc"]
    chosen = result["path"]
    return str(Path(chosen)) if chosen else None
