"""VoiceIntentParser — deterministic Thai/EN rule mapping to baseline.* commands.

M2 locked intent set (ADR-AETHER-2026-002):

    phrase                      → command                params
    เลือก component 1..5         → baseline.select        {component_id}
    ถ่ายภาพ [component N]       → baseline.capture       {component_id?}
    แสดงข้อมูล [component N]    → baseline.info          {component_id?}
    สถานะ                       → baseline.status        {}
    บันทึก [component N]        → baseline.capture       {component_id?}  (save alias)
    English aliases             → baseline.*             (select/capture/info/status/save)

The parser is a pure, dependency-free rule engine: it returns the shared
`IntentResult` (aether.core.intent_resolver) so M3 can reuse the same result
type while M2 stays free of any LLM/semantic layer.

Rules are matched in priority order: status → info → capture → save → select,
so "แสดงข้อมูล component 2" resolves to info, not select. Component ids are
validated against the M1 sandbox catalog (1..5); any other number invalidates
the utterance (returns None).
"""

from __future__ import annotations

import re
from typing import Optional

from aether.core.intent_resolver import IntentResult
from aether.sandbox.catalog import COMPONENT_IDS

_FIVE = "[1-5]"

# Component-id extraction: "component 2" / "comp 2" / "คอม 2" / "ข้อมูลที่ 2" / "ที่ 2"
_ID_LABEL = (
    r"(?:component|comp|คอม|ข้อมูลที่|ข้อมูล|อันที่|ตัวที่|ที่)"
    r"\s*[#]?\s*(" + _FIVE + r")\b"
)
_BARE_ID = r"\b(" + _FIVE + r")\b"

# (intent, command, patterns) — checked in order; first match wins.
_INTENT_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("status", "baseline.status", (r"สถานะ\s*baseline|\bbaseline\s*status\b|\bstatus\b|สถานะ",)),
    ("info", "baseline.info", (r"แสดงข้อมูล|show\s*info|\binfo\b|\bdetails?\b|ข้อมูล",)),
    ("capture", "baseline.capture", (r"ถ่ายภาพ|ถ่ายรูป|ถ่าย|\bcapture\b|take\s*photo|\bsnapshot\b",)),
    ("save", "baseline.capture", (r"บันทึก|\bsave\b|\brecord\b",)),
    ("select", "baseline.select", (r"เลือก|select|choose|\bcomponent\b|" + _BARE_ID,)),
)

_ID_RE = re.compile(_ID_LABEL, re.I)
_BARE_ID_RE = re.compile(_BARE_ID, re.I)
_NUMBER_RE = re.compile(r"\d+")


class VoiceIntentParser:
    """Rule-based voice intent resolver (Thai/EN, deterministic)."""

    def __init__(self) -> None:
        self._rules: tuple[tuple[str, str, tuple[re.Pattern[str], ...]], ...] = tuple(
            (intent, command, tuple(re.compile(p, re.I) for p in patterns))
            for intent, command, patterns in _INTENT_RULES
        )

    def resolve(self, user_input: str) -> Optional[IntentResult]:
        """Map voice text to a command (None when unrecognized/invalid)."""
        text = (user_input or "").strip()
        if not text:
            return None

        matched_intent: Optional[str] = None
        matched_command: Optional[str] = None
        for intent, command, patterns in self._rules:
            if any(p.search(text) for p in patterns):
                matched_intent = intent
                matched_command = command
                break

        if matched_intent is None:
            return None

        # Any number outside the 1..5 sandbox catalog invalidates the utterance.
        numbers = _NUMBER_RE.findall(text)
        if numbers and any(n not in COMPONENT_IDS for n in numbers):
            return None

        component_id = self._extract_id(text)

        # Selecting needs an explicit component id ("เลือก" with no number is invalid).
        if matched_intent == "select" and component_id is None:
            return None

        params: dict[str, str] = {}
        if component_id:
            params["component_id"] = component_id

        return IntentResult(
            intent=f"voice.{matched_intent}",
            command_name=matched_command,
            params=params,
            confidence=1.0,
            source="voice",
            raw_input=text,
        )

    @staticmethod
    def _extract_id(text: str) -> Optional[str]:
        m = _ID_RE.search(text)
        if m:
            return m.group(1)
        m = _BARE_ID_RE.search(text)
        return m.group(1) if m else None