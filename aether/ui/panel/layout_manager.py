"""LayoutManager — save, load, and switch panel layouts.

Layouts are JSON files stored in data/layouts/.
Each layout stores panel geometry (x, y, w, h, visible) — NOT panel state.

Design:
    Layout = "where panels are"
    State  = "what panels remember" (separate, in data/state/)

Layout JSON format:
{
    "name": "developer",
    "description": "Default developer workspace",
    "created_at": "2026-07-28T01:00:00",
    "panels": [
        {"id": "memory", "x": 100, "y": 100, "w": 400, "h": 300, "visible": true},
        {"id": "vision", "x": 520, "y": 100, "w": 400, "h": 300, "visible": true},
        {"id": "system", "x": 100, "y": 420, "w": 820, "h": 200, "visible": false}
    ]
}
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from aether.ui.panel.panel_registry import PanelRegistry

logger = logging.getLogger("Aether.LayoutManager")

DEFAULT_LAYOUTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "layouts"


class LayoutManager:
    """Save, load, and switch panel layouts.

    Does NOT own panels — applies geometry to PanelRegistry.
    Layout files are JSON in data/layouts/.
    """

    def __init__(
        self,
        panel_registry: PanelRegistry,
        layouts_dir: Optional[Path] = None,
    ) -> None:
        self._registry = panel_registry
        self._dir = layouts_dir or DEFAULT_LAYOUTS_DIR
        self._current_layout: Optional[str] = None
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Create layouts directory if it doesn't exist."""
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Save ───────────────────────────────────────────────────────

    def save(self, name: str, description: str = "") -> dict:
        """Save current panel geometry as a named layout.

        Returns the saved layout dict.
        """
        panels = self._registry.list_all()
        layout = {
            "name": name,
            "description": description,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "panels": [
                {
                    "id": p.id,
                    "x": p.x,
                    "y": p.y,
                    "w": p.w,
                    "h": p.h,
                    "visible": p.visible,
                }
                for p in panels
            ],
        }
        path = self._file_for(name)
        path.write_text(json.dumps(layout, indent=2, ensure_ascii=False), encoding="utf-8")
        self._current_layout = name
        logger.info("Layout '%s' saved to %s (%d panels)", name, path, len(panels))
        return layout

    # ── Load ───────────────────────────────────────────────────────

    def load(self, name: str) -> bool:
        """Load a layout and apply geometry to all panels.

        Returns True if layout was found and applied.
        """
        path = self._file_for(name)
        if not path.exists():
            logger.warning("Layout '%s' not found at %s", name, path)
            return False

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load layout '%s': %s", name, e)
            return False

        panels = data.get("panels", [])
        applied = 0
        for entry in panels:
            pid = entry.get("id")
            if not pid:
                continue
            info = self._registry.get(pid)
            if not info:
                logger.debug("Layout references unknown panel '%s', skipping", pid)
                continue
            x = entry.get("x", info.x)
            y = entry.get("y", info.y)
            w = entry.get("w", info.w)
            h = entry.get("h", info.h)
            vis = entry.get("visible", info.visible)
            self._registry.set_geometry(pid, x, y, w, h)
            if vis and not info.visible:
                self._registry.show_panel(pid)
            elif not vis and info.visible:
                self._registry.hide_panel(pid)
            applied += 1

        self._current_layout = name
        logger.info("Layout '%s' loaded (%d/%d panels applied)", name, applied, len(panels))
        return True

    # ── List ───────────────────────────────────────────────────────

    def list_layouts(self) -> List[str]:
        """Return sorted list of available layout names."""
        names = []
        for f in self._dir.iterdir():
            if f.suffix == ".json" and f.is_file():
                names.append(f.stem)
        names.sort()
        return names

    def get_layout_info(self, name: str) -> Optional[dict]:
        """Read layout metadata without applying it."""
        path = self._file_for(name)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    @property
    def current_layout(self) -> Optional[str]:
        """Name of the currently active layout."""
        return self._current_layout

    # ── Delete ─────────────────────────────────────────────────────

    def delete(self, name: str) -> bool:
        """Delete a layout file. Returns True if deleted."""
        path = self._file_for(name)
        if not path.exists():
            return False
        try:
            path.unlink()
            logger.info("Layout '%s' deleted", name)
            if self._current_layout == name:
                self._current_layout = None
            return True
        except OSError as e:
            logger.error("Failed to delete layout '%s': %s", name, e)
            return False

    # ── Reset ──────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset all panels to default geometry (no layout applied)."""
        for info in self._registry.list_all():
            self._registry.set_geometry(info.id, 0, 0, 400, 300)
            self._registry.hide_panel(info.id)
        self._current_layout = None
        logger.info("Layout reset to defaults")

    # ── Default layout ─────────────────────────────────────────────

    def save_default(self) -> dict:
        """Save current state as the 'default' layout."""
        return self.save("default", "Default Aether layout")

    def load_default(self) -> bool:
        """Load the 'default' layout if it exists."""
        return self.load("default")

    # ── Internal ───────────────────────────────────────────────────

    def _file_for(self, name: str) -> Path:
        """Get the file path for a layout name."""
        safe_name = name.replace("/", "_").replace("\\", "_").replace("..", "_")
        return self._dir / f"{safe_name}.json"
