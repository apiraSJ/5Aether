"""BaselineService — deterministic component capture via MemoryManager (M1).

M1 Deterministic Baseline pipeline:
    Camera frame → user selects Component 1..5 → snapshot written to disk →
    record stored in SQLite (working table) → UI lists the result.

No AI, no recognition. Supplies the repeatable baseline that later milestones
(M2 voice, M3 context, M4 feedback) build on.

Storage reuse (per project decision):
    - Component records live under key "component:<id>" in the working table
      (MemoryManager, value = JSON). Initial seed stores metadata only.
    - capture() writes the frame to <snapshots_dir>/baseline_snapshots/<id>.png
      and records snapshot_path + captured_at on the component record.
    - Frames are saved as files only — frame data never crosses the EventBus
      (FrameBroker invariant).

All catalog content is SIMULATED training data (see aether/sandbox/catalog.py).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from aether.sandbox.catalog import COMPONENTS, get_component

logger = logging.getLogger("Aether.BaselineService")

SNAPSHOT_SUBDIR = "baseline_snapshots"
SNAPSHOT_SUFFIX = ".png"


def component_key(component_id: str) -> str:
    """Memory key under which a component's baseline record is stored."""
    return f"component:{component_id}"


class BaselineService:
    """Stores/reads baseline component records through MemoryManager.

    The service owns only the MemoryManager reference — lifecycle (open/close)
    stays with MemoryPlugin. Safe to use in headless tests and the GUI panel.
    """

    def __init__(self, memory, snapshots_dir: str = "data") -> None:
        self._memory = memory
        self._snapshots_dir = snapshots_dir

    # ── Seeding ────────────────────────────────────────────────────

    def seed_catalog(self) -> int:
        """Register every catalog component in the working table.

        Idempotent: re-seeding overwrites the same keys. Returns the number of
        components registered.
        """
        count = 0
        for comp in COMPONENTS:
            cid = comp["id"]
            self._memory.store(
                "working",
                component_key(cid),
                {
                    "component_id": cid,
                    "name": comp["name"],
                    "source_manual": comp.get("source_manual", ""),
                    "snapshot_path": None,
                    "captured_at": None,
                },
                context={"domain": "baseline", "simulation": True},
            )
            count += 1
        return count

    # ── Capturing ──────────────────────────────────────────────────

    def capture(self, component_id: str, frame: Any) -> Optional[dict[str, Any]]:
        """Save a camera frame as the component's snapshot and record it.

        Args:
            component_id: Catalog id ("1".."5").
            frame: BGR ndarray as returned by FrameBroker.get_frame().

        Returns:
            The stored record value (with snapshot_path/captured_at) on success,
            or None when the component id is unknown or the frame is unusable.
        """
        comp = get_component(component_id)
        if comp is None or frame is None:
            return None

        import cv2  # bundled dependency; imported lazily for headless tests

        snapshots_dir = Path(self._snapshots_dir) / SNAPSHOT_SUBDIR
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        path = snapshots_dir / f"{component_id}{SNAPSHOT_SUFFIX}"

        ok = cv2.imwrite(str(path), frame)
        if not ok:
            logger.error("cv2.imwrite failed for %s", path)
            return None

        height, width = frame.shape[:2]
        value = {
            "component_id": component_id,
            "name": comp["name"],
            "source_manual": comp.get("source_manual", ""),
            "snapshot_path": str(path),
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "width": int(width),
            "height": int(height),
        }
        self._memory.store(
            "working",
            component_key(component_id),
            value,
            context={"domain": "baseline", "simulation": True},
        )
        logger.info("Baseline snapshot saved: %s", path)
        return value

    # ── Reading ────────────────────────────────────────────────────

    def list_baselines(self) -> list[dict[str, Any]]:
        """Return baseline records in catalog order (id 1..5).

        Each entry mirrors the stored working-memory value and carries a
        `captured` flag so UIs can render captured vs. pending components.
        """
        entries: list[dict[str, Any]] = []
        for comp in COMPONENTS:
            cid = comp["id"]
            record = self._recall(component_key(cid))
            value = record.get("value", {}) if record else {}
            entries.append({
                "component_id": cid,
                "name": comp["name"],
                "snapshot_path": value.get("snapshot_path"),
                "captured_at": value.get("captured_at"),
                "width": value.get("width"),
                "height": value.get("height"),
                "captured": bool(value.get("snapshot_path")),
            })
        return entries

    def baseline_status(self) -> dict[str, Any]:
        """Summary of the baseline store: seeded / captured counts."""
        entries = self.list_baselines()
        return {
            "seeded": len(entries),
            "captured": sum(1 for e in entries if e["captured"]),
        }

    # ── Helpers ────────────────────────────────────────────────────

    def _recall(self, key: str) -> Optional[dict[str, Any]]:
        try:
            result = self._memory.recall(key, "working")
        except Exception:
            return None
        if not result.found or not result.records:
            return None
        record = result.records[0]
        return {
            "key": record.key,
            "value": record.value if isinstance(record.value, dict) else {},
        }