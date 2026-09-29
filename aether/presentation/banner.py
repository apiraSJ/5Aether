"""Aether boot banner and visual identity.

Non-invasive presentation layer. Does NOT touch core lifecycle,
EventBus, ServiceContainer, or PluginManager.

Usage:
    from aether.presentation.banner import show_banner, print_boot_status
    show_banner()
"""

from __future__ import annotations

import sys
from typing import List, Optional


# ── ASCII Art: AETHER (Calvin S figlet, padded to 42 inner chars) ─

_AETHER_ART = (
    "    _____________   __________",
    "   / ____/ ___/ _ | / __/ __/ ",
    "  / /___/ /  / __ |/ _// _/  ",
    " /____//_/  /_/ |_/___/___/  ",
)

_W = 42  # inner width (matches box)


def _build_banner(version: str) -> str:
    """Assemble the full XR HUD banner with version string."""
    def row(content: str = "") -> str:
        return "|" + content + " " * (_W - len(content)) + "|"

    border = "+" + "=" * _W + "+"
    blank  = row()
    art    = [row(line) for line in _AETHER_ART]

    return "\n".join([
        border,
        blank,
        *art,
        blank,
        row("       SPATIAL INTELLIGENCE AI"),
        blank,
        border,
        row("  BOOT SEQUENCE"),
        blank,
        row("  [OK] Runtime Engine"),
        row("  [OK] Event Architecture"),
        row("  [OK] Vision Perception"),
        row("  [OK] Spatial Memory"),
        row("  [OK] Command Interface"),
        blank,
        border,
        row("          STATUS : ONLINE"),
        border,
    ])


# ── Compact Banner (for default startup) ───────────────────────────

BANNER_COMPACT = """
AETHER v{version}
SPATIAL INTELLIGENCE CORE
"""


# ── Public API ─────────────────────────────────────────────────────

def show_banner(
    version: str = "1.0.0",
    *,
    file: object = None,
) -> None:
    """Print the XR HUD boot banner with ASCII art AETHER to stdout."""
    out = file or sys.stdout
    print(_build_banner(version), file=out)
    print(f"  version : {version}", file=out)
    print(file=out)


def show_compact_banner(
    version: str = "1.0.0",
    *,
    file: object = None,
) -> None:
    """Print a minimal one-line banner."""
    out = file or sys.stdout
    print(BANNER_COMPACT.format(version=version).strip(), file=out)
    print(file=out)


def print_boot_status(
    steps: Optional[List[str]] = None,
    *,
    file: object = None,
) -> None:
    """Print boot progress steps with checkmarks.

    Example:
        print_boot_status([
            ("EventBus", True),
            ("PluginManager", True),
        ])
    """
    out = file or sys.stdout
    if steps is None:
        return

    for step in steps:
        if isinstance(step, tuple):
            label, ok = step
            mark = "[OK]" if ok else "[!!]"
            print(f"  {mark} {label}", file=out)
        else:
            print(f"  .. {step}", file=out)

    print(file=out)
