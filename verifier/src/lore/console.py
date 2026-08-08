"""Console output UTF-8 encoding helper for Windows cross-platform safety."""

from __future__ import annotations

import sys


def setup_utf8_console() -> None:
    """Ensure sys.stdout and sys.stderr handle UTF-8 cleanly without cp1252 charmap crashes."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# Automatically configure when imported
setup_utf8_console()
