"""
ANSI color/style theme for pathkeeper.

Usage:
    from pathkeeper.theme import t        # module-level singleton
    print(t.ok("All good"))
    print(t.error("Something broke"))
    print(t.dim("(internal detail)"))

Color is suppressed when:
  - NO_COLOR env var is set (https://no-color.org)
  - TERM=dumb
  - stdout is not a TTY
  - display.color = false in config
  - --no-color flag is passed (call Theme.disable())
"""
from __future__ import annotations

import os
import sys


class Theme:
    # ANSI escape sequences
    _RESET = "\x1b[0m"
    _BOLD = "\x1b[1m"
    _DIM = "\x1b[2m"
    _UNDERLINE = "\x1b[4m"

    _BLACK = "\x1b[30m"
    _RED = "\x1b[31m"
    _GREEN = "\x1b[32m"
    _YELLOW = "\x1b[33m"
    _BLUE = "\x1b[34m"
    _MAGENTA = "\x1b[35m"
    _CYAN = "\x1b[36m"
    _WHITE = "\x1b[37m"
    _BRIGHT_WHITE = "\x1b[97m"

    _BRIGHT_RED = "\x1b[91m"
    _BRIGHT_GREEN = "\x1b[92m"
    _BRIGHT_YELLOW = "\x1b[93m"
    _BRIGHT_CYAN = "\x1b[96m"

    def __init__(self) -> None:
        self._enabled = self._autodetect()

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    @staticmethod
    def _autodetect() -> bool:
        if "NO_COLOR" in os.environ:
            return False
        if os.environ.get("TERM") == "dumb":
            return False
        if not sys.stdout.isatty():
            return False
        return True

    def apply_config(self, color: bool) -> None:
        """Called once config is loaded; config can further disable color."""
        if not color:
            self._enabled = False

    def disable(self) -> None:
        self._enabled = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _wrap(self, codes: str, text: str) -> str:
        if not self._enabled:
            return text
        return f"{codes}{text}{self._RESET}"

    # ------------------------------------------------------------------
    # Semantic API — call these from print sites
    # ------------------------------------------------------------------

    def ok(self, text: str) -> str:
        """A valid / successful item."""
        return self._wrap(self._BRIGHT_GREEN, text)

    def error(self, text: str) -> str:
        """Error, missing, invalid."""
        return self._wrap(self._BOLD + self._BRIGHT_RED, text)

    def warn(self, text: str) -> str:
        """Warning or duplicate."""
        return self._wrap(self._BRIGHT_YELLOW, text)

    def dim(self, text: str) -> str:
        """Secondary info, metadata."""
        return self._wrap(self._DIM, text)

    def bold(self, text: str) -> str:
        return self._wrap(self._BOLD, text)

    def header(self, text: str) -> str:
        """Section / command header."""
        return self._wrap(self._BOLD + self._BRIGHT_CYAN, text)

    def label(self, text: str) -> str:
        """Menu key label like [1]."""
        return self._wrap(self._CYAN, text)

    def accent(self, text: str) -> str:
        """Accent / highlight — paths found, chosen items."""
        return self._wrap(self._BRIGHT_WHITE, text)

    def category(self, text: str) -> str:
        """Category headers in populate output."""
        return self._wrap(self._BOLD + self._BLUE, text)

    def prompt(self, text: str) -> str:
        """Interactive prompt character."""
        return self._wrap(self._CYAN, text)

    def dry_run(self, text: str) -> str:
        """Dry-run notice."""
        return self._wrap(self._DIM + self._YELLOW, text)

    def path_entry(self, text: str, *, exists: bool, duplicate: bool, empty: bool, is_file: bool) -> str:
        if empty:
            return self._wrap(self._DIM, text)
        if duplicate:
            return self._wrap(self._BRIGHT_YELLOW, text)
        if not exists or is_file:
            return self._wrap(self._BRIGHT_RED, text)
        return text  # valid entries — no color needed, let contrast come from markers

    def marker(self, text: str, *, ok: bool, warn: bool) -> str:
        if ok:
            return self._wrap(self._BRIGHT_GREEN, text)
        if warn:
            return self._wrap(self._BRIGHT_YELLOW, text)
        return self._wrap(self._BRIGHT_RED, text)


# Module-level singleton — import this everywhere
t = Theme()
