"""The system's own «choose a folder» window — how a person grants a folder without typing a path.

The daemon runs on the user's desktop, so it can open the native dialog the browser cannot: a web page never learns
a real folder path (`<input webkitdirectory>` hands over file names, not the folder's place on disk). The chosen
folder still goes through `roots.grant`, so the dialog adds a way IN and no way AROUND the permission circuit.

Standard library only, like the rest of the daemon: each platform's dialog is a subprocess of a tool the OS ships.
A cancel, a missing tool or a timeout all return "" — the caller then simply has no folder, never an error.
"""
from __future__ import annotations

import shutil
import subprocess
import sys

#: Long enough for a person to browse; bounded so an abandoned dialog never holds a worker thread forever.
TIMEOUT_S = 300.0


def _clean(prompt: str) -> str:
    """The dialog's title, from the engine. Quotes, backslashes and line breaks are dropped: it is spliced into an
    AppleScript / PowerShell string, and a caller must never be able to close that string."""
    text = "".join(ch for ch in str(prompt or "") if ch not in "\"'\\`$\r\n")
    return " ".join(text.split())[:120] or "Choose a folder"


def _command(prompt: str) -> list[str] | None:
    p = _clean(prompt)
    if sys.platform == "darwin":
        return ["osascript", "-e", f'POSIX path of (choose folder with prompt "{p}")']
    if sys.platform.startswith("win"):
        script = ("Add-Type -AssemblyName System.Windows.Forms; "
                  "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                  f"$d.Description = '{p}'; "
                  "if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath }")
        return ["powershell", "-NoProfile", "-STA", "-Command", script]
    tool = shutil.which("zenity")
    return [tool, "--file-selection", "--directory", f"--title={p}"] if tool else None


def choose_folder(prompt: str = "") -> str:
    """The folder the person picked, or "" (cancelled, no dialog on this system, or timed out)."""
    cmd = _command(prompt)
    if not cmd:
        return ""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    if out.returncode != 0:
        return ""
    path = (out.stdout or "").strip()
    return path.rstrip("/") if len(path) > 1 else path
