"""Post-launch window normalization.

Chromium only honours --start-maximized on a profile's first run; after
that the persisted window placement wins. A placement saved against a
stale work area (taskbar height, monitor change) then resurfaces on every
launch with the page bottom behind the Windows taskbar. After each launch
the profile window is re-maximized so Windows recomputes the bounds from
the *current* work area.

The fixup runs entirely inside a PowerShell child process on purpose: an
in-process ctypes EnumWindows callback needs the GIL, and a leaked session
thread spinning pure-Python loops can starve it indefinitely. A child
process touches the window without ever taking the GIL.
"""

import subprocess
import time
from pathlib import Path

_PS_SHOW = r"""
$ps = Get-CimInstance Win32_Process | Where-Object {
  $_.Name -eq 'chrome.exe' -and
  $_.CommandLine -match 'fingerprint=%(seed)d' -and
  $_.CommandLine -notmatch '--type='
}
foreach ($p in $ps) {
  $proc = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
  if ($proc -and $proc.MainWindowHandle -ne 0) {
    Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public class ZW { [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd); }'
    [ZW]::ShowWindow($proc.MainWindowHandle, 3) | Out-Null
    Write-Output $proc.MainWindowHandle
  }
}
"""


def _show_window_via_powershell(seed: int) -> str:
    """Spawn the PowerShell fixup; returns the window handle text or ''."""
    script = _PS_SHOW.replace("%(seed)d", str(seed))
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=20,
        )
    except Exception:  # noqa: BLE001 - window fixup must never break launch
        return ""
    return (out.stdout or "").strip()


def maximize_profile_window(seed: int, timeout: float = 8.0) -> bool:
    """Maximize the profile browser's main window into the work area.

    The window handle appears a moment after launch, so poll until the
    deadline. Returns True once a window was found and maximized.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _show_window_via_powershell(seed):
            return True
        time.sleep(0.5)
    return False


def fixup_script_path() -> Path:
    """Location of the embedded PowerShell snippet (for diagnostics)."""
    return Path(__file__)
