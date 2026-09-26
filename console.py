"""
console.py

Console encoding setup, imported first by every entry point.

The project prints emoji and Persian text. On Windows the default console
codepage is cp1256, which cannot encode those characters and raises
UnicodeEncodeError. Forcing UTF-8 on the standard streams keeps the CLI, the
Gradio UI, the API server and the test suite from crashing on print.
"""

import sys


def setup_console() -> bool:
    """Force UTF-8 on stdout/stderr. Returns True if a change was applied."""
    changed = False
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            if (stream.encoding or "").lower().replace("-", "") not in ("utf8", "utf_8"):
                reconfigure(encoding="utf-8", errors="replace")
                changed = True
        except (ValueError, OSError):
            # Stream already detached or not reconfigurable — ignore.
            pass
    return changed


setup_console()
