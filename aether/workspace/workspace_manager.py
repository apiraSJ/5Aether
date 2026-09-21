"""WorkspaceManager — central service for workspace and layout lifecycle.

WorkspaceManager owns:
- Workspace definitions (what panels exist, startup behavior)
- Layout operations (save/load/restore geometry)

Architecture:
    WorkspaceManager
        ├── load_workspace(id)    → load workspace definition + default layout
        ├── save_layout(name)     → save current geometry
        ├── load_layout(name)     → restore geometry
        ├── restore_last()        → restore previous layout on boot
        └── list_workspaces()     → enumerate available workspaces

Workspace ≠ Layout:
    Workspace = what panels exist, startup behavior
    Layout    = where panels are positioned
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from aether.ui.panel.panel_registry import PanelRegistry

logger = logging.getLogger("Aether.WorkspaceManager")

WORKSPACES_DIR = Path(__file__).resolve().parent.parent / "config" / "workspaces"
LAYOUTS_DIR = Path(__file__).resolve().parent.parent / "data" / "layouts"


class WorkspaceManager:
    """Central service for workspace and layout lifecycle.

    Skeleton for Sprint 1 — supports single workspace, save/load/restore.
    Will be extended for multi-workspace switching in future sprints.
    """

    def __init__(
        self,
        panel_registry: PanelRegistry,
        workspaces_dir: Optional[Path] = None,
        layouts_dir: Optional[Path] = None,
    ) -> None:
        self._registry = panel_registry
        self._workspaces_dir = workspaces_dir or WORKSPACES_DIR
        self._layouts_dir = layouts_dir or LAYOUTS_DIR
        self._current_workspace_id: Optional[str] = None
        self._current_layout_name: Optional[str] = None
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self._workspaces_dir.mkdir(parents=True, exist_ok=True)
        self._layouts_dir.mkdir(parents=True, exist_ok=True)

    # ── Workspace operations ────────────────────────────────────────

    def load_workspace(self, workspace_id: str) -> bool:
        """Load a workspace definition from config/workspaces/<id>.yaml.

        Returns True if workspace was loaded successfully.
        """
        yaml_path = self._workspaces_dir / f"{workspace_id}.yaml"
        json_path = self._workspaces_dir / f"{workspace_id}.json"

        path = yaml_path if yaml_path.exists() else json_path
        if not path.exists():
            logger.warning("Workspace '%s' not found at %s", workspace_id, path)
            return False

        try:
            import yaml
            raw = path.read_text(encoding="utf-8")
            if path.suffix == ".yaml":
                data = yaml.safe_load(raw)
            else:
                data = json.loads(raw)
        except Exception as e:
            logger.error("Failed to load workspace '%s': %s", workspace_id, e)
            return False

        if not data:
            logger.warning("Workspace '%s' is empty", workspace_id)
            return False

        self._current_workspace_id = workspace_id

        # Load default layout if specified
        default_layout = data.get("default_layout")
        if default_layout:
            self.load_layout(default_layout)

        # Show panels that should be visible by default
        panels = data.get("panels", [])
        for panel_def in panels:
            panel_id = panel_def.get("id")
            if not panel_id:
                continue
            visible = panel_def.get("visible", True)
            if visible:
                info = self._registry.get(panel_id)
                if info and not info.visible:
                    self._registry.show_panel(panel_id)

        logger.info("Workspace '%s' loaded (%d panels)", workspace_id, len(panels))
        return True

    def list_workspaces(self) -> List[str]:
        """Return sorted list of available workspace IDs."""
        names = []
        for f in self._workspaces_dir.iterdir():
            if f.suffix in (".yaml", ".json") and f.is_file():
                names.append(f.stem)
        names.sort()
        return names

    @property
    def current_workspace(self) -> Optional[str]:
        """ID of the currently active workspace."""
        return self._current_workspace_id

    # ── Layout operations ───────────────────────────────────────────

    def save_layout(self, name: str, description: str = "") -> dict:
        """Save current panel geometry as a named layout.

        Returns the saved layout dict.
        """
        panels = self._registry.list_all()
        layout = {
            "name": name,
            "description": description,
            "workspace": self._current_workspace_id,
            "panels": [
                {
                    "id": p.id,
                    "x": p.x,
                    "y": p.y,
                    "w": p.w,
                    "h": p.h,
                    "z_index": p.z_index,
                    "visible": p.visible,
                }
                for p in panels
            ],
        }
        path = self._layouts_dir / f"{name}.json"
        path.write_text(json.dumps(layout, indent=2, ensure_ascii=False), encoding="utf-8")
        self._current_layout_name = name
        logger.info("Layout '%s' saved to %s (%d panels)", name, path, len(panels))
        return layout

    def load_layout(self, name: str) -> bool:
        """Load a layout and apply geometry to all panels.

        Returns True if layout was found and applied.
        """
        path = self._layouts_dir / f"{name}.json"
        if not path.exists():
            logger.warning("Layout '%s' not found at %s", name, path)
            return False

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load layout '%s': %s", name, e)
            return False

        panels = data.get("panels", [])
        if not isinstance(panels, list):
            logger.error("Layout '%s' has invalid 'panels' type (expected list, got %s)",
                          name, type(panels).__name__)
            return False

        applied = 0
        for entry in panels:
            pid = entry.get("id")
            if not pid:
                continue
            info = self._registry.get(pid)
            if not info:
                logger.warning("Layout references unknown panel '%s', skipping", pid)
                continue
            x = entry.get("x", info.x)
            y = entry.get("y", info.y)
            w = entry.get("w", info.w)
            h = entry.get("h", info.h)
            z = entry.get("z_index", info.z_index)
            vis = entry.get("visible", info.visible)
            self._registry.set_geometry(pid, x, y, w, h)
            self._registry.set_z_index(pid, z)
            if vis and not info.visible:
                self._registry.show_panel(pid)
            elif not vis and info.visible:
                self._registry.hide_panel(pid)
            applied += 1

        self._current_layout_name = name
        logger.info("Layout '%s' loaded (%d/%d panels applied)", name, applied, len(panels))
        return True

    def save_layout_sessions(self, name: str, sessions: list[dict], description: str = "") -> dict:
        """Save panel sessions (WorkspaceScene.serialize()) as a named layout.

        This is the event-driven auto-save path used by WorkspaceScene:
        every layout change serializes the scene's sessions and writes
        <layouts>/<name>.json.

        Returns the saved layout dict.
        """
        layout = {
            "name": name,
            "description": description,
            "workspace": self._current_workspace_id,
            "sessions": sessions,
        }
        path = self._layouts_dir / f"{name}.json"
        path.write_text(json.dumps(layout, indent=2, ensure_ascii=False), encoding="utf-8")
        self._current_layout_name = name
        logger.info("Layout '%s' saved to %s (%d sessions)", name, path, len(sessions))
        return layout

    def load_layout_sessions(self, name: str) -> Optional[list[dict]]:
        """Load a session-based layout.

        Returns the sessions list (for WorkspaceScene.apply_sessions),
        or None if the layout is missing or malformed.
        """
        path = self._layouts_dir / f"{name}.json"
        if not path.exists():
            logger.warning("Layout '%s' not found at %s", name, path)
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load layout '%s': %s", name, e)
            return None
        sessions = data.get("sessions")
        if not isinstance(sessions, list):
            logger.debug("Layout '%s' has no 'sessions' data", name)
            return None
        self._current_layout_name = name
        return sessions

    def last_layout_sessions(self) -> Optional[list[dict]]:
        """Load the most recently saved session layout (auto-save target).

        Returns the sessions list, or None if no session layout exists.
        """
        layouts = sorted(self._layouts_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in layouts:
            sessions = self.load_layout_sessions(path.stem)
            if sessions is not None:
                return sessions
        return None

    def restore_last(self) -> bool:
        """Restore the last saved layout (most recently saved).

        Returns True if a layout was restored.
        """
        layouts = sorted(self._layouts_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not layouts:
            return False
        return self.load_layout(layouts[0].stem)

    def list_layouts(self) -> List[str]:
        """Return sorted list of available layout names."""
        names = []
        for f in self._layouts_dir.iterdir():
            if f.suffix == ".json" and f.is_file():
                names.append(f.stem)
        names.sort()
        return names

    def delete_layout(self, name: str) -> bool:
        """Delete a layout file. Returns True if deleted."""
        path = self._layouts_dir / f"{name}.json"
        if not path.exists():
            return False
        try:
            path.unlink()
            logger.info("Layout '%s' deleted", name)
            if self._current_layout_name == name:
                self._current_layout_name = None
            return True
        except OSError as e:
            logger.error("Failed to delete layout '%s': %s", name, e)
            return False

    @property
    def current_layout(self) -> Optional[str]:
        """Name of the currently active layout."""
        return self._current_layout_name
