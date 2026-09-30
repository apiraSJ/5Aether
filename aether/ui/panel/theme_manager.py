"""ThemeManager — load, apply, and switch Aether themes.

Themes are JSON files in data/themes/. Each theme defines colors, opacity,
typography, shape, and animation properties.

Usage:
    theme_mgr = ThemeManager()
    theme_mgr.load_theme("cyberpunk")
    theme_mgr.apply_to_registry(panel_registry)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Aether.ThemeManager")

DEFAULT_THEMES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "themes"

# Default theme used when no theme is loaded
DEFAULT_THEME: Dict[str, Any] = {
    "name": "default",
    "description": "Built-in default theme",
    "colors": {
        "background": "#0a0a0a",
        "surface": "#141414",
        "primary": "#00ccff",
        "secondary": "#6366f1",
        "warning": "#f59e0b",
        "error": "#ef4444",
        "success": "#22c55e",
        "text": "#e0e0e0",
        "text_muted": "#888888",
        "border": "rgba(255,255,255,0.12)",
    },
    "opacity": {"panel": 0.92, "overlay": 0.80, "notification": 0.95},
    "typography": {"font": "Consolas", "title_size": 16, "body_size": 12, "mono_size": 11},
    "shape": {"border_radius": 8},
    "animation": {"duration_ms": 150},
}


class ThemeManager:
    """Load, apply, and switch Aether themes.

    Provides:
        - list_themes(): available theme names
        - load_theme(name): load a theme from data/themes/
        - get_theme(): current theme dict
        - apply_to_registry(registry): apply theme to all panels
        - get_color(key): get a color from current theme
    """

    def __init__(self, themes_dir: Optional[Path] = None) -> None:
        self._dir = themes_dir or DEFAULT_THEMES_DIR
        self._current: Dict[str, Any] = dict(DEFAULT_THEME)
        self._name: str = "default"
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── List ───────────────────────────────────────────────────────

    def list_themes(self) -> List[str]:
        """Return sorted list of available theme names."""
        names = ["default"]
        for f in self._dir.iterdir():
            if f.suffix == ".json" and f.is_file():
                names.append(f.stem)
        return sorted(set(names))

    # ── Load ───────────────────────────────────────────────────────

    def load_theme(self, name: str) -> bool:
        """Load a theme by name. Returns True if loaded successfully."""
        if name == "default":
            self._current = dict(DEFAULT_THEME)
            self._name = "default"
            logger.info("Loaded default theme")
            return True

        path = self._dir / f"{name}.json"
        if not path.exists():
            logger.warning("Theme '%s' not found at %s", name, path)
            return False

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load theme '%s': %s", name, e)
            return False

        self._current = self._merge_theme(DEFAULT_THEME, data)
        self._name = name
        logger.info("Loaded theme '%s'", name)
        return True

    def _merge_theme(self, base: dict, override: dict) -> dict:
        """Deep-merge override into base, filling missing keys from base."""
        result = {}
        for key in set(list(base.keys()) + list(override.keys())):
            base_val = base.get(key)
            over_val = override.get(key)
            if isinstance(base_val, dict) and isinstance(over_val, dict):
                result[key] = self._merge_theme(base_val, over_val)
            elif over_val is not None:
                result[key] = over_val
            elif base_val is not None:
                result[key] = base_val
        return result

    # ── Get ────────────────────────────────────────────────────────

    def get_theme(self) -> Dict[str, Any]:
        """Return the current theme dict."""
        return self._current

    @property
    def current_name(self) -> str:
        """Name of the current theme."""
        return self._name

    def get_color(self, key: str, default: str = "#ffffff") -> str:
        """Get a color from the current theme.

        Supports dot notation: 'colors.primary', 'colors.background'.
        """
        parts = key.split(".")
        obj = self._current
        for part in parts:
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                return default
        return obj if isinstance(obj, str) else default

    def get_opacity(self, key: str, default: float = 1.0) -> float:
        """Get an opacity value. e.g. 'panel', 'overlay'."""
        val = self._current.get("opacity", {}).get(key, default)
        return float(val) if val is not None else default

    def get_font_size(self, key: str, default: int = 12) -> int:
        """Get a typography size. e.g. 'title_size', 'body_size'."""
        val = self._current.get("typography", {}).get(key, default)
        return int(val) if val is not None else default

    def get_border_radius(self) -> int:
        """Get the border radius from current theme."""
        return int(self._current.get("shape", {}).get("border_radius", 8))

    def get_animation_duration(self) -> int:
        """Get animation duration in ms."""
        return int(self._current.get("animation", {}).get("duration_ms", 150))

    # ── Apply ──────────────────────────────────────────────────────

    def apply_to_registry(self, registry) -> int:
        """Apply current theme to all panels in a PanelRegistry.

        Returns count of panels themed.
        """
        theme = self._current
        count = 0
        for info in registry.list_all():
            if info.widget and hasattr(info.widget, "set_theme"):
                info.widget.set_theme(theme)
                count += 1
        return count

    # ── Save ───────────────────────────────────────────────────────

    def save_theme(self, name: str, theme: dict, description: str = "") -> bool:
        """Save a theme dict to data/themes/.

        Returns True on success.
        """
        theme["name"] = name
        if description:
            theme["description"] = description
        path = self._dir / f"{name}.json"
        try:
            path.write_text(json.dumps(theme, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.info("Theme '%s' saved to %s", name, path)
            return True
        except OSError as e:
            logger.error("Failed to save theme '%s': %s", name, e)
            return False

    # ── Delete ─────────────────────────────────────────────────────

    def delete_theme(self, name: str) -> bool:
        """Delete a theme file. Cannot delete 'default'."""
        if name == "default":
            return False
        path = self._dir / f"{name}.json"
        if not path.exists():
            return False
        try:
            path.unlink()
            logger.info("Theme '%s' deleted", name)
            return True
        except OSError as e:
            logger.error("Failed to delete theme '%s': %s", name, e)
            return False
