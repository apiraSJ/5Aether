"""Tests for VoiceIntentParser — M2 locked Thai/EN intent set (ADR-AETHER-2026-002)."""

from __future__ import annotations

import pytest

from aether.voice.intent_parser import VoiceIntentParser


@pytest.fixture
def parser():
    return VoiceIntentParser()


VALID_CASES = [
    # phrase, intent, command, component_id (None = not required)
    ("เลือก component 1", "voice.select", "baseline.select", "1"),
    ("เลือก component 3", "voice.select", "baseline.select", "3"),
    ("เลือก 5", "voice.select", "baseline.select", "5"),
    ("component 2", "voice.select", "baseline.select", "2"),
    ("select component 2", "voice.select", "baseline.select", "2"),
    ("select 4", "voice.select", "baseline.select", "4"),
    ("choose 3", "voice.select", "baseline.select", "3"),
    ("ถ่ายภาพ", "voice.capture", "baseline.capture", None),
    ("ถ่ายภาพ component 2", "voice.capture", "baseline.capture", "2"),
    ("capture", "voice.capture", "baseline.capture", None),
    ("capture component 3", "voice.capture", "baseline.capture", "3"),
    ("ถ่าย 1", "voice.capture", "baseline.capture", "1"),
    ("แสดงข้อมูล", "voice.info", "baseline.info", None),
    ("แสดงข้อมูล component 2", "voice.info", "baseline.info", "2"),
    ("show info", "voice.info", "baseline.info", None),
    ("ข้อมูล", "voice.info", "baseline.info", None),
    ("แสดงข้อมูลที่ 2", "voice.info", "baseline.info", "2"),
    ("สถานะ", "voice.status", "baseline.status", None),
    ("สถานะ baseline", "voice.status", "baseline.status", None),
    ("status", "voice.status", "baseline.status", None),
    ("บันทึก", "voice.save", "baseline.capture", None),
    ("บันทึก component 3", "voice.save", "baseline.capture", "3"),
    ("save", "voice.save", "baseline.capture", None),
    ("save component 1", "voice.save", "baseline.capture", "1"),
]

INVALID_CASES = [
    "",
    "   ",
    "zebra",
    "unknown stuff",
    "เลือก",            # select without a number
    "เลือก component 6",  # 6 is outside the 1..5 catalog
    "select 9",
    "แสดงข้อมูล component 8",
    "ถ่ายภาพ 0",
    "บันทึก 12",
    "123",
]


@pytest.mark.parametrize("phrase,intent,command,component_id", VALID_CASES)
def test_valid_utterances(parser, phrase, intent, command, component_id):
    result = parser.resolve(phrase)
    assert result is not None
    assert result.intent == intent
    assert result.command_name == command
    assert result.source == "voice"
    assert result.confidence == 1.0
    assert result.raw_input == phrase.strip()
    if component_id is None:
        assert "component_id" not in result.params
    else:
        assert result.params["component_id"] == component_id


@pytest.mark.parametrize("phrase", INVALID_CASES)
def test_invalid_utterances_return_none(parser, phrase):
    assert parser.resolve(phrase) is None


def test_whitespace_and_case_are_normalized(parser):
    result = parser.resolve("  SELECT COMPONENT 2  ")
    assert result is not None
    assert result.command_name == "baseline.select"
    assert result.params["component_id"] == "2"
    assert result.raw_input == "SELECT COMPONENT 2"


def test_more_specific_intent_wins_over_select(parser):
    # "แสดงข้อมูล component 2" must resolve to info, not select.
    result = parser.resolve("แสดงข้อมูล component 2")
    assert result.intent == "voice.info"
    assert result.command_name == "baseline.info"
    assert result.params["component_id"] == "2"


def test_bare_capture_has_no_component(parser):
    result = parser.resolve("ถ่ายภาพ")
    assert result.command_name == "baseline.capture"
    assert "component_id" not in result.params