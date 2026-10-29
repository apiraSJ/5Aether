"""Deterministic temporal extraction for Phase 4 (Mark 1).

Pure functions: text -> List[Candidate]. No DB access.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Tuple

from aether.task.models import DEFAULT_TZ, ItemKind


@dataclass(frozen=True)
class Candidate:
    kind: ItemKind
    title: str
    description: str = ""
    due_date: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    all_day: bool = False
    tz: Optional[str] = None
    confidence: float = 0.5
    rule_id: str = ""
    raw_excerpt: str = ""
    needs_review: bool = False
    review_reason: Optional[str] = None
    review_payload: Dict[str, Any] = field(default_factory=dict)
    missing_fields: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtractionResult:
    source_text: str
    content_hash: str
    candidates: Tuple[Candidate, ...]
    analyzed_at: float
    tz: str


_TIME_ONLY_RE = re.compile(
    r"\b(?:(?:1[0-2]|0?[1-9])(?::([0-5][0-9]))?\s*(?:am|pm)|([01]?\d|2[0-3]):([0-5][0-9]))\b",
    re.IGNORECASE,
)
_TIME_THAI_RE = re.compile(r"(?:เช้า|สาย|บ่าย|เย็น|ค่ำ|ดึก|เที่ยง|เที่ยงคืน)", re.IGNORECASE)

_DATE_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DATE_SLASH_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b")
_DATE_DOT_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\b")

_TZ_NAME_RE = re.compile(r"\b([A-Z][A-Za-z_]+/[A-Z][A-Za-z_]+)\b")

_WEEKDAYS_THAI = {
    "จันทร์": 0,
    "อังคาร": 1,
    "พุธ": 2,
    "พฤหัสบดี": 3,
    "ศุกร์": 4,
    "เสาร์": 5,
    "อาทิตย์": 6,
}

_WEEKDAYS_EN = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
    "mon": 0,
    "tue": 1,
    "tues": 1,
    "wed": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}

_DEADLINE_MARKERS = re.compile(r"(ก่อน|ภายใน|ส่ง|กำหนด|due|by|deadline|submit|finish|complete|report)", re.IGNORECASE)
_BULLET_SPLIT_RE = re.compile(r"[\n\r]+|\s*[-•*]\s+|(?<![\d:])\d+\.\s+(?!\d)|\s*\d+\)\s+")
_CLEAN_TITLE_RE = re.compile(r"(ต้อง|ช่วย|ด้วย|นะ|ครับ|ค่ะ|แล้ว)\b", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")

_SUPPORTED_TZ = {"Asia/Bangkok", "UTC"}


def _normalize_text(text: str) -> str:
    return _WS_RE.sub(" ", (text or "").strip())


def _content_hash(text: str) -> str:
    return hashlib.sha256(_normalize_text(text).encode("utf-8")).hexdigest()


def _has_date(text: str) -> bool:
    if _DATE_ISO_RE.search(text):
        return True
    if _DATE_SLASH_RE.search(text):
        return True
    if _DATE_DOT_RE.search(text):
        return True
    # relative days/weekdays count as date references (Thai)
    if re.search(r"(วันนี้|พรุ่งนี้|มะรืนนี้|เมื่อวาน)", text):
        return True
    for wd in _WEEKDAYS_THAI:
        if wd in text:
            return True
    if re.search(r"(สัปดาห์หน้า|อาทิตย์หน้า|จันทร์หน้า|อังคารหน้า|พุธหน้า|พฤหัสบดีหน้า|ศุกร์หน้า|เสาร์หน้า)", text):
        return True
    # relative days/weekdays count as date references (English)
    low = text.lower()
    if re.search(r"\b(today|tomorrow|yesterday|day after tomorrow)\b", low):
        return True
    for wd in _WEEKDAYS_EN:
        if re.search(rf"\b{re.escape(wd)}\b", low):
            return True
    if re.search(r"\bnext\s+(week|monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b", low):
        return True
    if re.search(r"\bthis\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b", low):
        return True
    return False


def _is_date_context_numeric(m: re.Match) -> bool:
    # Avoid false positives like "1/2 ถ้วย" by requiring surrounding date context or year
    if m.group(3):  # has year
        return True
    # check if near date markers
    start, end = m.span()
    ctx = m.string[max(0, start - 10): min(len(m.string), end + 10)]
    if re.search(r"(วันที่|วัน|ก่อน|ภายใน|เมื่อ|on|by)", ctx):
        return True
    # if both numbers small and no units like ถ้วย/ช้อน/เมตร it's risky; be conservative
    return False


def _extract_date(text: str, now: datetime) -> Tuple[Optional[str], str]:
    # ISO
    m = _DATE_ISO_RE.search(text)
    if m:
        try:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return datetime(y, mo, d).date().isoformat(), "iso_date"
        except Exception:
            pass
    # slash/dot with year or date context
    for pat in (_DATE_SLASH_RE, _DATE_DOT_RE):
        for m in pat.finditer(text):
            if pat is _DATE_SLASH_RE and not _is_date_context_numeric(m) and not m.group(3):
                continue
            if pat is _DATE_DOT_RE and not m.group(3):
                # be conservative for dot without year
                pass
            try:
                g1, g2 = int(m.group(1)), int(m.group(2))
                if m.group(3):
                    y = int(m.group(3))
                    # try day/month first
                    try:
                        return datetime(y, g2, g1).date().isoformat(), "numeric_date"
                    except Exception:
                        try:
                            return datetime(y, g1, g2).date().isoformat(), "numeric_date"
                        except Exception:
                            pass
                else:
                    # no year - try to interpret as day/month in context
                    try:
                        return datetime(now.year, g2, g1).date().isoformat(), "numeric_date"
                    except Exception:
                        try:
                            return datetime(now.year, g1, g2).date().isoformat(), "numeric_date"
                        except Exception:
                            pass
            except Exception:
                continue
    # relative (Thai)
    if re.search(r"เมื่อวาน", text):
        return (now - timedelta(days=1)).date().isoformat(), "relative_day"
    if re.search(r"มะรืนนี้", text):
        return (now + timedelta(days=2)).date().isoformat(), "relative_day"
    if re.search(r"พรุ่งนี้", text):
        return (now + timedelta(days=1)).date().isoformat(), "relative_day"
    if re.search(r"วันนี้", text):
        return now.date().isoformat(), "relative_day"
    # relative (English, case-insensitive)
    low = text.lower()
    if re.search(r"\bday after tomorrow\b", low):
        return (now + timedelta(days=2)).date().isoformat(), "relative_day"
    if re.search(r"\btomorrow\b", low):
        return (now + timedelta(days=1)).date().isoformat(), "relative_day"
    if re.search(r"\byesterday\b", low):
        return (now - timedelta(days=1)).date().isoformat(), "relative_day"
    if re.search(r"\btoday\b", low):
        return now.date().isoformat(), "relative_day"
    # weekday (Thai)
    for wd_th, wd_idx in _WEEKDAYS_THAI.items():
        if wd_th in text:
            # check if next week
            is_next_week = bool(re.search(rf"{wd_th}หน้า", text)) or ("สัปดาห์หน้า" in text and wd_th in text)
            delta = (wd_idx - now.weekday()) % 7
            if delta == 0:
                delta = 7  # strictly after today
            if re.search(rf"{wd_th}หน้า", text):
                if delta < 7:
                    delta += 7
            elif "สัปดาห์หน้า" in text and wd_th in text:
                pass  # already handled
            elif "สัปดาห์หน้า" in text and wd_th not in text:
                return None, "week_ambiguous"
            rule = "weekday_next_week" if delta >= 7 else "weekday_next"
            return (now + timedelta(days=delta)).date().isoformat(), rule
    if "สัปดาห์หน้า" in text:
        return None, "week_ambiguous"
    # weekday (English, case-insensitive)
    # "next week" alone (without a weekday) is ambiguous
    has_next_week_alone = bool(re.search(r"\bnext\s+week\b", low)) and not re.search(
        r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b", low
    ) and not re.search(
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\s+next\s+week\b", low
    )
    # (removed: "next <weekday>" no longer adds a week; handled by generic weekday match below)
    # try "<weekday> next week"
    m_wd_next = re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\s+next\s+week\b", low)
    if m_wd_next:
        wd_key = m_wd_next.group(1)
        if wd_key in _WEEKDAYS_EN:
            wd_idx = _WEEKDAYS_EN[wd_key]
            delta = (wd_idx - now.weekday()) % 7
            if delta == 0:
                delta = 7
            if delta < 7:
                delta += 7
            return (now + timedelta(days=delta)).date().isoformat(), "weekday_next_week"
    # try "this <weekday>"
    m_this = re.search(r"\bthis\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b", low)
    if m_this:
        wd_key = m_this.group(1)
        if wd_key in _WEEKDAYS_EN:
            wd_idx = _WEEKDAYS_EN[wd_key]
            delta = (wd_idx - now.weekday()) % 7
            if delta == 0:
                delta = 7  # strictly after today
            return (now + timedelta(days=delta)).date().isoformat(), "weekday_next"
    # plain weekday mention (English)
    for wd_en, wd_idx in _WEEKDAYS_EN.items():
        # match whole word
        if re.search(rf"\b{re.escape(wd_en)}\b", low):
            # avoid matching "mon" inside "monday" handled by longer keys first? 
            # We iterate dict in insertion order; longer keys first would be better but dict order is fixed.
            # To avoid partial matches, prefer longer matches: check if a longer key also matches.
            pass
    # Do a proper pass: find the longest matching weekday token
    best_match = None
    best_len = 0
    for wd_en, wd_idx in _WEEKDAYS_EN.items():
        if re.search(rf"\b{re.escape(wd_en)}\b", low) and len(wd_en) > best_len:
            best_match = (wd_en, wd_idx)
            best_len = len(wd_en)
    if best_match:
        wd_en, wd_idx = best_match
        delta = (wd_idx - now.weekday()) % 7
        if delta == 0:
            delta = 7  # strictly after today
        rule = "weekday_next"
        return (now + timedelta(days=delta)).date().isoformat(), rule
    if has_next_week_alone:
        return None, "week_ambiguous"
    return None, ""


def _extract_time(text: str) -> Tuple[Optional[str], str]:
    # thai period + numeral
    m = re.search(r"บ่าย\s*(สอง|สาม|สี่|ห้า|หก|หนึ่ง|เอ็ด|1|2|3|4|5|6)", text)
    if m:
        num = m.group(1)
        mapping = {"หนึ่ง": 1, "เอ็ด": 1, "1": 1, "สอง": 2, "2": 2, "สาม": 3, "3": 3, "สี่": 4, "4": 4, "ห้า": 5, "5": 5, "หก": 6, "6": 6}
        h = mapping.get(num, 2)
        if h < 12:
            h += 12
        return f"{h:02d}:00", "thai_period_numeral"
    m = re.search(r"บ่าย\s*(\d+)(?:\s*โมง)?", text)
    if m:
        h = int(m.group(1))
        if h < 12:
            h += 12
        return f"{h:02d}:00", "thai_period_numeral"
    m = re.search(r"เช้า\s*(\d+)(?:\s*โมง)?", text)
    if m:
        h = int(m.group(1))
        if h == 12:
            h = 0
        return f"{h:02d}:00", "thai_period_numeral"
    m = re.search(r"เย็น\s*(\d+)(?:\s*โมง)?", text)
    if m:
        h = int(m.group(1))
        if h < 12:
            h += 12
        return f"{h:02d}:00", "thai_period_numeral"
    if re.search(r"เที่ยงคืน", text):
        return "00:00", "thai_noon"
    if re.search(r"เที่ยง\b", text):
        return "12:00", "thai_noon"
    # period only
    if re.search(r"(เช้า|บ่าย|เย็น|สาย|ค่ำ|ดึก)\b", text) and not _TIME_ONLY_RE.search(text) and not re.search(r"(บ่าย\s*(สอง|สาม|สี่|ห้า|หก))", text):
        return None, "thai_period_only"
    # numeric time (HH:MM / H:MM, 24h or am/pm)
    m24 = re.search(r"([01]?\d|2[0-3]):([0-5][0-9])", text)
    if m24:
        return f"{int(m24.group(1)):02d}:{m24.group(2)}", "explicit_time"
    m12 = re.search(r"([1-9]|1[0-2])\s*(am|pm)", text, re.IGNORECASE)
    if m12:
        h = int(m12.group(1))
        if re.search(r"pm", text, re.IGNORECASE) and h < 12:
            h += 12
        if re.search(r"am", text, re.IGNORECASE) and h == 12:
            h = 0
        return f"{h:02d}:00", "explicit_time"
    return None, ""


def _parse_hhmm(s: str) -> Optional[Tuple[int, int]]:
    m = re.search(r"([01]?\d|2[0-3]):([0-5][0-9])", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"([1-9]|1[0-2])\s*(?:นาฬิกา|โมง)", s)
    if m:
        return int(m.group(1)), 0
    return None


def _extract_time_range(text: str, start_time: Optional[str]) -> Tuple[Optional[str], str, bool]:
    # range with -
    m = re.search(r"(?:^|\s)(\d{1,2})(?::(\d{2}))?\s*[-–—]\s*(\d{1,2})(?::(\d{2}))?", text)
    if m:
        sh = int(m.group(1))
        sm = int(m.group(2)) if m.group(2) else 0
        eh = int(m.group(3))
        em = int(m.group(4)) if m.group(4) else 0
        if eh * 60 + em < sh * 60 + sm:
            return None, "time_range", True  # ambiguous cross midnight
        return f"{eh:02d}:{em:02d}", "time_range", False
    # ถึง
    m = re.search(r"(?:ถึง|จนถึง)\s*(\d{1,2})(?::(\d{2}))?\s*(?:นาฬิกา|โมง)?", text)
    if m:
        eh = int(m.group(1))
        em = int(m.group(2)) if m.group(2) else 0
        if start_time:
            sh, sm = map(int, start_time.split(":"))
            if eh * 60 + em < sh * 60 + sm:
                return None, "time_range", True
        return f"{eh:02d}:{em:02d}", "time_range", False
    # duration hours
    m = re.search(r"(?:เป็นเวลา|นาน)\s*(\d+(?:\.\d+)?)\s*(?:ชั่วโมง|ชม\.)", text)
    if m and start_time:
        sh, sm = map(int, start_time.split(":"))
        hours = float(m.group(1))
        total_m = int(sh * 60 + sm + hours * 60)
        eh, em = total_m // 60 % 24, total_m % 60
        return f"{eh:02d}:{em:02d}", "duration_hours", False
    # duration minutes
    m = re.search(r"(?:เป็นเวลา|อีก)\s*(\d+)\s*(?:นาที|นาที)", text)
    if m and start_time:
        sh, sm = map(int, start_time.split(":"))
        mins = int(m.group(1))
        total_m = sh * 60 + sm + mins
        eh, em = total_m // 60 % 24, total_m % 60
        return f"{eh:02d}:{em:02d}", "duration_minutes", False
    if re.search(r"(?:เป็นเวลา|นาน)\s*\d+", text) and not start_time:
        return None, "duration_without_start", False
    return None, "", False
    # numeric time
    m = _TIME_ONLY_RE.search(text)
    if m:
        # try to parse
        s = m.group(0)
        # simple parse
        try:
            # handle am/pm
            if re.search(r"am|pm", s, re.I):
                # basic
                pass
            # 24h
            m24 = re.search(r"([01]?\d|2[0-3]):([0-5][0-9])", s)
            if m24:
                return f"{int(m24.group(1)):02d}:{m24.group(2)}", "explicit_time"
            # 12h without minutes
            m12 = re.search(r"([1-9]|1[0-2])\s*(?:am|pm)", s, re.I)
            if m12:
                h = int(m12.group(1))
                if re.search(r"pm", s, re.I) and h < 12:
                    h += 12
                if re.search(r"am", s, re.I) and h == 12:
                    h = 0
                return f"{h:02d}:00", "explicit_time"
        except Exception:
            pass
    return None, ""


def _clean_title(text: str, date_stripped: str) -> str:
    t = text
    # remove date/time patterns crudely
    t = _DATE_ISO_RE.sub("", t)
    t = _DATE_SLASH_RE.sub("", t)
    t = _DATE_DOT_RE.sub("", t)
    t = re.sub(r"(พรุ่งนี้|วันนี้|มะรืนนี้|เมื่อวาน|สัปดาห์หน้า)", "", t)
    for wd in _WEEKDAYS_THAI:
        t = t.replace(wd + "หน้า", "").replace(wd, "")
    # strip English relative/weekday words (case-insensitive)
    t = re.sub(r"(?i)\b(day after tomorrow|tomorrow|yesterday|today|next week|this week)\b", "", t)
    for wd in _WEEKDAYS_EN:
        t = re.sub(rf"(?i)\b{re.escape(wd)}\b", "", t)
    t = re.sub(r"(?i)\bnext\b", "", t)
    t = re.sub(r"(?i)\bthis\b", "", t)
    t = re.sub(r"(บ่าย|เช้า|เย็น|สาย|ค่ำ|ดึก|เที่ยง|เที่ยงคืน)\s*\d*\s*โมง?", "", t)
    t = _TIME_ONLY_RE.sub("", t)
    t = _CLEAN_TITLE_RE.sub("", t)
    t = _WS_RE.sub(" ", t).strip(" -,:;.")
    if not t:
        t = text.strip()[:80]
    if len(t) > 120:
        t = t[:120].rstrip()
    return t


def _split_segments(text: str) -> List[str]:
    parts = _BULLET_SPLIT_RE.split(text)
    segs = []
    for p in parts:
        p2 = _normalize_text(p)
        if p2:
            segs.append(p2)
    if not segs:
        segs = [_normalize_text(text)]
    return segs


def extract(text: str) -> List[Candidate]:
    """Extract candidates from free text. Deterministic rules only."""
    candidates: List[Candidate] = []
    if not text or not text.strip():
        return candidates

    tz_hints = _TZ_NAME_RE.findall(text)

    if _TIME_ONLY_RE.search(text) or _TIME_THAI_RE.search(text):
        if not _has_date(text):
            payload = {
                "raw_time": text.strip(),
                "excerpt": text.strip(),
                "rule_id": "time_only_no_date",
                "kind": "extraction",
            }
            if tz_hints:
                payload["tz"] = tz_hints[0]
                payload["timezone"] = tz_hints[0]
                payload["raw_tz"] = tz_hints[0]
                payload["timezones"] = list(tz_hints)
            candidates.append(
                Candidate(
                    kind=ItemKind.EVENT,
                    title=text.strip()[:200],
                    confidence=0.6,
                    rule_id="time_only_no_date",
                    raw_excerpt=text.strip(),
                    needs_review=True,
                    review_reason="ambiguous time: missing date",
                    review_payload=payload,
                    missing_fields=("date",),
                )
            )
            return candidates

    return candidates


def analyze(
    text: str,
    *,
    now: Optional[datetime] = None,
    tz: str = DEFAULT_TZ,
) -> ExtractionResult:
    """Analyze free text into extraction result with draft-ready candidates."""
    if now is None:
        now = datetime.now()
    # normalize tz
    tz_use = tz if tz in _SUPPORTED_TZ else tz
    source_norm = _normalize_text(text)
    candidates: List[Candidate] = []
    if not source_norm:
        return ExtractionResult(
            source_text=text or "",
            content_hash=_content_hash(text or ""),
            candidates=(),
            analyzed_at=time.time(),
            tz=tz_use,
        )

    tz_hints = _TZ_NAME_RE.findall(text)
    segments = _split_segments(text)

    for seg in segments:
        seg_norm = seg
        has_deadline = bool(_DEADLINE_MARKERS.search(seg_norm))
        date_str, date_rule = _extract_date(seg_norm, now)
        time_str, time_rule = _extract_time(seg_norm)
        missing: List[str] = []

        payload: Dict[str, Any] = {
            "excerpt": seg_norm,
            "rule_id": date_rule or time_rule or "unknown",
            "kind": "extraction",
        }
        if tz_hints:
            payload["tz"] = tz_hints[0]
            payload["timezone"] = tz_hints[0]
            payload["raw_tz"] = tz_hints[0]
            payload["timezones"] = list(dict.fromkeys(tz_hints))
        if tz_hints and tz_hints[0] not in _SUPPORTED_TZ:
            missing.append("tz")

        if date_rule == "week_ambiguous":
            missing.append("date")
        if time_rule == "thai_period_only":
            missing.append("time")
        if not date_str and (time_rule in ("explicit_time", "thai_period_numeral", "thai_noon") or time_str):
            missing.append("date")
            payload["raw_time"] = seg_norm
        if not date_str and not time_str and not has_deadline:
            # try to be conservative
            pass

        title = _clean_title(seg_norm, seg_norm)
        if not title:
            title = seg_norm[:80]

        if has_deadline:
            if date_str:
                cand = Candidate(
                    kind=ItemKind.TASK,
                    title=title,
                    due_date=date_str,
                    tz=tz_use,
                    confidence=0.8,
                    rule_id=date_rule or "deadline_marker",
                    raw_excerpt=seg_norm,
                    needs_review=bool(missing),
                    review_reason="needs confirmation" if missing else None,
                    review_payload=payload,
                    missing_fields=tuple(sorted(set(missing))),
                )
                candidates.append(cand)
                continue
            else:
                missing.append("date")
                cand = Candidate(
                    kind=ItemKind.TASK,
                    title=title,
                    tz=tz_use,
                    confidence=0.6,
                    rule_id="deadline_marker",
                    raw_excerpt=seg_norm,
                    needs_review=True,
                    review_reason="ambiguous time: missing date",
                    review_payload=payload,
                    missing_fields=tuple(sorted(set(missing))),
                )
                candidates.append(cand)
                continue
        if date_str and not time_str and not has_deadline:
            # check if meeting with range but time parsed differently
            time_str2, time_rule2 = _extract_time(seg_norm)
            if not time_str2:
                m = re.search(r"(?:^|\s)(\d{1,2})(?::([0-5][0-9]))?\s*ถึง", seg_norm)
                if not m:
                    m = re.search(r"(?:^|\s)(\d{1,2})(?::([0-5][0-9]))?\s*[-–—]", seg_norm)
                if m:
                    h = int(m.group(1))
                    mi = int(m.group(2)) if m.group(2) else 0
                    time_str2 = f"{h:02d}:{mi:02d}"
            if time_str2 and date_str:
                start_at = f"{date_str}T{time_str2}:00"
                end_time, erule, eamb = _extract_time_range(seg_norm, time_str2)
                end_at = None
                if end_time and not eamb:
                    end_at = f"{date_str}T{end_time}:00"
                elif eamb:
                    missing.append("end_at")
                    payload["end_ambiguous"] = True
                cand = Candidate(
                    kind=ItemKind.EVENT,
                    title=title,
                    start_at=start_at,
                    end_at=end_at,
                    tz=tz_use,
                    confidence=0.9,
                    rule_id=erule or date_rule,
                    raw_excerpt=seg_norm,
                    needs_review=True,
                    review_reason="needs confirmation",
                    review_payload=payload,
                    missing_fields=tuple(sorted(set(missing))),
                )
                candidates.append(cand)
                continue
        if date_str and time_str and not has_deadline:
            # Event
            start_at = f"{date_str}T{time_str}:00"
            end_time, erule, eamb = _extract_time_range(seg_norm, time_str)
            end_at = None
            if end_time and not eamb:
                end_at = f"{date_str}T{end_time}:00"
            elif eamb:
                missing.append("end_at")
                payload["end_ambiguous"] = True
            if erule == "duration_without_start":
                missing.append("time")
            cand = Candidate(
                kind=ItemKind.EVENT,
                title=title,
                start_at=start_at,
                end_at=end_at,
                tz=tz_use,
                confidence=0.9,
                rule_id=erule or date_rule,
                raw_excerpt=seg_norm,
                needs_review=bool(missing),
                review_reason="needs confirmation" if missing else None,
                review_payload=payload,
                missing_fields=tuple(sorted(set(missing))),
            )
            candidates.append(cand)
            continue
        if date_str and not time_str and not has_deadline:
            # has date but no time - appointment-like without time -> needs time
            if re.search(r"(นัด|ประชุม|พบ|คุย|สัมภาษณ์)", seg_norm):
                missing.append("time")
                end_time, erule, eamb = _extract_time_range(seg_norm, None)
                if erule == "duration_without_start":
                    missing.append("time")
                cand = Candidate(
                    kind=ItemKind.EVENT,
                    title=title,
                    tz=tz_use,
                    confidence=0.7,
                    rule_id=date_rule,
                    raw_excerpt=seg_norm,
                    needs_review=True,
                    review_reason="needs confirmation",
                    review_payload=payload,
                    missing_fields=tuple(sorted(set(missing))),
                )
                candidates.append(cand)
                continue
            # default task
            cand = Candidate(
                kind=ItemKind.TASK,
                title=title,
                due_date=date_str,
                tz=tz_use,
                confidence=0.75,
                rule_id=date_rule,
                raw_excerpt=seg_norm,
                needs_review=bool(missing),
                review_reason="needs confirmation" if missing else None,
                review_payload=payload,
                missing_fields=tuple(sorted(set(missing))),
            )
            candidates.append(cand)
            continue
        if time_str and not date_str:
            # time only
            payload["raw_time"] = seg_norm
            end_time, erule, eamb = _extract_time_range(seg_norm, time_str)
            if end_time or eamb or erule == "duration_without_start":
                payload["raw_end"] = seg_norm
            cand = Candidate(
                kind=ItemKind.EVENT,
                title=title,
                tz=tz_use,
                confidence=0.6,
                rule_id=time_rule or "time_only_no_date",
                raw_excerpt=seg_norm,
                needs_review=True,
                review_reason="ambiguous time: missing date",
                review_payload=payload,
                missing_fields=("date",),
            )
            candidates.append(cand)
            continue
        # fallback
        cand = Candidate(
            kind=ItemKind.TASK,
            title=title,
            tz=tz_use,
            confidence=0.4,
            rule_id="fallback",
            raw_excerpt=seg_norm,
            needs_review=True,
            review_reason="needs confirmation",
            review_payload=payload,
            missing_fields=tuple(sorted(set(missing))) or ("date",),
        )
        candidates.append(cand)

    return ExtractionResult(
        source_text=text or "",
        content_hash=_content_hash(text or ""),
        candidates=tuple(candidates),
        analyzed_at=time.time(),
        tz=tz_use,
    )
