from __future__ import annotations

import re

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """Remove ANSI color codes Rich/Typer inject into console output.

    Rich's console highlighter can wrap individual tokens (option flags,
    numbers, paths) in their own color spans, which splits a plain substring
    like "--console" or "dispatched=2" across escape codes. Whether that
    happens depends on the runtime's color detection, which differs between
    a local terminal, a CI runner, and an explicit FORCE_COLOR override -- so
    any test asserting on CLI output text should strip ANSI codes first
    rather than depend on a specific environment's color behavior.
    """
    return _ANSI_ESCAPE_RE.sub("", text)
