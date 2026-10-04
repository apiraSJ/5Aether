"""Simulated maintenance component catalog (M1 Deterministic Baseline).

The catalog is deliberately *simulated* data for an undergraduate prototype:
it represents generic industrial/network-facility equipment used to train the
`Camera → Capture → Select component 1..5 → SQLite → UI` data pipeline (M1).

It is NOT a real equipment specification and must never be presented as one.
All numbers, procedures, and manual references are placeholder values used to
exercise the deterministic baseline flow end-to-end (see docs/ROADMAP.md).

Each component record has the fixed sandbox schema:
    id                  – selector used by the baseline buttons (str "1".."5")
    name                – display name
    visual_features     – what to look for when targeting the camera
    specifications      – simulated key values
    inspection_procedure– ordered checklist used by a technician
    troubleshooting     – common symptom → suggested action
    source_manual       – simulated manual reference (clearly labeled)
"""

from __future__ import annotations

from typing import Any, Optional

# Fixed, documented sandbox schema. Extending this field set requires a plan
# change — do NOT add out-of-scope fields inside M1.
COMPONENT_FIELDS = (
    "id",
    "name",
    "visual_features",
    "specifications",
    "inspection_procedure",
    "troubleshooting",
    "source_manual",
)

COMPONENTS: tuple[dict[str, Any], ...] = (
    {
        "id": "1",
        "name": "Circuit Breaker Panel (CB-100)",
        "visual_features": (
            "Gray steel enclosure, hinged front door, 6 black breaker toggles "
            "in 2 rows, red trip indicator lamp on the door."
        ),
        "specifications": {
            "voltage": "240 V AC",
            "current": "100 A max",
            "poles": "2",
            "protection": "thermal-magnetic",
        },
        "inspection_procedure": (
            "1. Verify door closes and latches correctly. "
            "2. Check red trip lamp is off. "
            "3. Confirm all toggles are in the ON position. "
            "4. Note any burn/discoloration marks near terminals."
        ),
        "troubleshooting": {
            "trip lamp on": "Reset breaker ON; if it trips again, defer to manual.",
            "no power downstream": "Verify upstream feed and breaker position.",
        },
        "source_manual": "Tech Sheet CB-100 Rev.2 (SIMULATED)",
    },
    {
        "id": "2",
        "name": "Backup Power Supply (BPS-200)",
        "visual_features": (
            "Rack-mounted 2U unit with 4 LED status indicators, black front "
            "handle, small LCD with charge %, two battery slide-out trays."
        ),
        "specifications": {
            "capacity": "2000 VA",
            "runtime": "15 min at full load",
            "input": "220–240 V AC",
            "output": "220–240 V AC (line / battery)",
        },
        "inspection_procedure": (
            "1. Confirm LCD charge reads above 80%. "
            "2. Verify LED2 (line) is green. "
            "3. Check battery trays are latched. "
            "4. Listen for abnormal fan whine."
        ),
        "troubleshooting": {
            "charge below 80%": "Recharge from line for 2 h and re-test.",
            "LED2 not green": "Check inlet supply; swap to battery for continuity.",
        },
        "source_manual": "Tech Sheet BPS-200 Rev.1 (SIMULATED)",
    },
    {
        "id": "3",
        "name": "Air Cooling Unit (ACU-300)",
        "visual_features": (
            "Wall-mounted white-clad unit, front intake grille, 2 exhaust "
            "louvers, small condensate drip tray, green/amber status LED."
        ),
        "specifications": {
            "cooling": "5,000 BTU/h",
            "airflow": "150 CFM",
            "power": "220–240 V AC, 1.2 A",
            "refrigerant": "R-32 (simulated charge)",
        },
        "inspection_procedure": (
            "1. Confirm status LED is green. "
            "2. Check intake grille is free of dust build-up. "
            "3. Verify condensate tray is not overflowing. "
            "4. Measure outlet air temperature delta."
        ),
        "troubleshooting": {
            "amber LED": "Airflow restriction or high ambient; clean grille.",
            "no cooling": "Check refrigerant charge via service port (licensed only).",
        },
        "source_manual": "Tech Sheet ACU-300 Rev.3 (SIMULATED)",
    },
    {
        "id": "4",
        "name": "Signal Repeater Unit (SR-400)",
        "visual_features": (
            "Compact black DIN-rail module, 4 RJ45 ports, small LED matrix "
            "(PWR/LNK/RX/TX), screw terminal for 24 V DC, metal end plates."
        ),
        "specifications": {
            "ports": "4 x RJ45",
            "rate": "1 Gbps",
            "power": "24 V DC",
            "form": "DIN-rail mount",
        },
        "inspection_procedure": (
            "1. Verify PWR LED is solid green. "
            "2. Confirm LNK LEDs are lit on used ports. "
            "3. Check TX/RX LEDs flicker during traffic. "
            "4. Inspect cable seats in all RJ45 jacks."
        ),
        "troubleshooting": {
            "LNK off on a port": "Reseat cable; test with known-good patch cable.",
            "no PWR": "Check 24 V DC feed and terminal torque.",
        },
        "source_manual": "Tech Sheet SR-400 Rev.1 (SIMULATED)",
    },
    {
        "id": "5",
        "name": "Distribution Box (DBX-500)",
        "visual_features": (
            "Metal junction box with blank cover plate, 10 multi-colored "
            "wiring conduits entering from the top, single grounding lug, "
            "two door fasteners."
        ),
        "specifications": {
            "circuits": "6",
            "voltage": "240 V AC",
            "current": "60 A",
            "ingress": "IP54",
        },
        "inspection_procedure": (
            "1. Remove cover and check for loose terminations by visual scan. "
            "2. Verify grounding lug is tight. "
            "3. Confirm cable gland entry points are sealed. "
            "4. Note any heat/discoloration on insulation."
        ),
        "troubleshooting": {
            "loose cover": "Retighten fasteners; replace gasket if worn.",
            "overheating signs": "De-energize and inspect terminations (qualified staff).",
        },
        "source_manual": "Tech Sheet DBX-500 Rev.2 (SIMULATED)",
    },
)

COMPONENT_IDS: tuple[str, ...] = tuple(c["id"] for c in COMPONENTS)

_CATALOG_BY_ID: dict[str, dict[str, Any]] = {c["id"]: c for c in COMPONENTS}


def get_component(component_id: str) -> Optional[dict[str, Any]]:
    """Return the catalog entry for a component id ("1".."5") or None."""
    return _CATALOG_BY_ID.get(str(component_id))


def validate_catalog() -> list[str]:
    """Return a list of schema violations found in the catalog (empty = valid).

    Used by the seed path and tests to guarantee the sandbox never ships with
    a malformed component record.
    """
    violations: list[str] = []
    for comp in COMPONENTS:
        cid = comp.get("id")
        for field in COMPONENT_FIELDS:
            if field not in comp:
                violations.append(f"component {cid!r}: missing field {field!r}")
            elif not comp[field]:
                violations.append(f"component {cid!r}: empty field {field!r}")
    if len(COMPONENT_IDS) != len(set(COMPONENT_IDS)):
        violations.append("duplicate component ids")
    return violations