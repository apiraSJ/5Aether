"""Unit tests for the RuleBasedIntentClassifier (Phase 3.3).

Covers:
  - All six intent types route correctly.
  - Explicit memory-write is the ONLY path to remember (no auto-save).
  - Confidence is metadata, never a routing threshold (suggested_action is
    deterministic and independent of confidence).
  - Deterministic / no-LLM / explainable behavior.
"""

from __future__ import annotations

from aether.ai.intent import (
    ACT_ASK_CLARIFICATION,
    ACT_MEMORY_SEARCH,
    ACT_MEMORY_WRITE,
    ACT_RUN_AGENT_LOOP,
    IntentType,
    RuleBasedIntentClassifier,
)

c = RuleBasedIntentClassifier()


class TestMemoryWrite:
    def test_english_remember_as(self):
        d = c.classify("remember my name as John")
        assert d.intent == IntentType.MEMORY_WRITE
        assert d.suggested_action == ACT_MEMORY_WRITE
        assert d.extracted_params["memory_key"] == "my name"
        assert d.extracted_params["memory_value"] == "John"

    def test_english_store_as(self):
        d = c.classify("store budget as 5000")
        assert d.intent == IntentType.MEMORY_WRITE
        assert d.extracted_params["memory_value"] == "5000"

    def test_thai_zhum_wai_wa(self):
        d = c.classify("จำไว้ว่าโปรเจกต์ Aether ใช้ PySide6")
        assert d.intent == IntentType.MEMORY_WRITE
        assert d.suggested_action == ACT_MEMORY_WRITE
        assert "PySide6" in d.extracted_params["memory_value"]

    def test_general_statement_never_auto_saves(self):
        # Core safety constraint: general statements must NOT be memory writes.
        for msg in ("I like dark UI", "โปรเจกต์ Aether ใช้ PySide6", "the sky is blue"):
            d = c.classify(msg)
            assert d.suggested_action != ACT_MEMORY_WRITE, f"auto-save on {msg!r}"
            assert d.intent != IntentType.MEMORY_WRITE


class TestMemoryRetrieval:
    def test_what_did_i_say_about(self):
        d = c.classify("what did I say about the budget?")
        assert d.intent == IntentType.MEMORY_RETRIEVAL
        assert d.suggested_action == ACT_MEMORY_SEARCH
        assert d.extracted_params["memory_query"] == "the budget"

    def test_search_memory_about(self):
        d = c.classify("search memory about Aether")
        assert d.intent == IntentType.MEMORY_RETRIEVAL

    def test_thai_what_did_i_say(self):
        d = c.classify("ฉันเคยบอกอะไรเกี่ยวกับ Aether?")
        assert d.intent == IntentType.MEMORY_RETRIEVAL
        assert "Aether" in d.extracted_params["memory_query"]


class TestAction:
    def test_open_panel(self):
        d = c.classify("open the memory panel")
        assert d.intent == IntentType.ACTION
        # ACTION always routes to the agent loop (never executes tools directly).
        assert d.suggested_action == ACT_RUN_AGENT_LOOP

    def test_thai_open(self):
        d = c.classify("เปิด Memory panel")
        assert d.intent == IntentType.ACTION
        assert d.suggested_action == ACT_RUN_AGENT_LOOP


class TestQuestion:
    def test_question_mark(self):
        d = c.classify("What is the capital of France?")
        assert d.intent == IntentType.QUESTION
        assert d.suggested_action == ACT_RUN_AGENT_LOOP

    def test_thai_explain(self):
        d = c.classify("อธิบายว่า EventBus คืออะไร?")
        assert d.intent == IntentType.QUESTION


class TestClarification:
    def test_short_filler_thai(self):
        d = c.classify("เอ่อ")
        assert d.intent == IntentType.CLARIFICATION
        assert d.suggested_action == ACT_ASK_CLARIFICATION

    def test_empty_message(self):
        d = c.classify("   ")
        assert d.intent == IntentType.CLARIFICATION


class TestUnknown:
    def test_gibberish(self):
        d = c.classify("asdfghjkl")
        assert d.intent in (IntentType.UNKNOWN, IntentType.CLARIFICATION)
        # Unknown degrades to the agent loop, never a memory write.
        assert d.suggested_action != ACT_MEMORY_WRITE


class TestDeterminismAndExplanability:
    def test_confidence_is_metadata_not_threshold(self):
        # Routing must be driven by intent, not by confidence thresholds.
        for msg in (
            "remember x as y",
            "what did I say about z?",
            "open the panel",
            "question?",
        ):
            d = c.classify(msg)
            assert d.suggested_action in (
                ACT_MEMORY_WRITE, ACT_MEMORY_SEARCH, ACT_RUN_AGENT_LOOP
            )
            # Reason is always present and human-readable.
            assert d.reason
            assert 0.0 <= d.confidence <= 1.0

    def test_rule_deterministic(self):
        for _ in range(5):
            assert c.classify("open the memory panel").suggested_action == ACT_RUN_AGENT_LOOP

    def test_classify_never_raises_on_bad_input(self):
        for bad in (None, 123, ["x"], object()):
            d = c.classify(bad)
            assert isinstance(d.suggested_action, str)
