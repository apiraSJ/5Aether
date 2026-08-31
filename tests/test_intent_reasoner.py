"""Unit tests for IntentReasoner routing (Phase 3.3).

Covers:
  - reason() returns the classifier decision (routing, not a second agent).
  - remember() only stores explicit memory writes; never infers/auto-saves.
  - remember() degrades gracefully when the retriever is missing.
  - clarify_text() returns a follow-up prompt.
  - Any classifier failure degrades to UNKNOWN / run_agent_loop.
"""

from __future__ import annotations

from aether.ai.intent import (
    ACT_MEMORY_SEARCH,
    ACT_MEMORY_WRITE,
    ACT_RUN_AGENT_LOOP,
    IntentReasoner,
    IntentType,
    RuleBasedIntentClassifier,
    StrategyMetrics,
)


class _FakeRetriever:
    def __init__(self) -> None:
        self.saved: list = []
        self.saved_id: str = "rec-1"

    def remember(self, key, value, importance=0.5, **kw):
        self.saved.append((key, value, importance))
        return self.saved_id


class _RaisingClassifier(RuleBasedIntentClassifier):
    def classify(self, *a, **k):
        raise RuntimeError("boom")


def test_reason_routes_via_classifier():
    r = IntentReasoner(memory_retriever=_FakeRetriever())
    d = r.reason("open the memory panel")
    assert d.intent == IntentType.ACTION
    assert d.suggested_action == ACT_RUN_AGENT_LOOP  # not executed by intent layer


def test_reason_memory_write_action():
    r = IntentReasoner(memory_retriever=_FakeRetriever())
    d = r.reason("remember project as aether")
    assert d.suggested_action == ACT_MEMORY_WRITE


def test_remember_explicit_write():
    retriever = _FakeRetriever()
    r = IntentReasoner(memory_retriever=retriever)
    rid = r.remember({"memory_key": "project", "memory_value": "aether", "importance": 0.8})
    assert rid == "rec-1"
    assert retriever.saved == [("project", "aether", 0.8)]


def test_remember_empty_key_degraded():
    retriever = _FakeRetriever()
    r = IntentReasoner(memory_retriever=retriever)
    assert r.remember({"memory_key": "  "}) is None
    assert retriever.saved == []


def test_remember_no_retriever_degrades():
    r = IntentReasoner(memory_retriever=None)
    assert r.remember({"memory_key": "x", "memory_value": "y"}) is None


def test_no_auto_remember_on_general_statement():
    # The reasoner must not remember() for non-memory-write messages.
    r = IntentReasoner(memory_retriever=_FakeRetriever())
    d = r.reason("I like dark UI")
    assert d.suggested_action != ACT_MEMORY_WRITE


def test_classifier_failure_degrades_to_agent_loop():
    r = IntentReasoner(classifier=_RaisingClassifier())
    d = r.reason("anything")
    assert d.suggested_action == ACT_RUN_AGENT_LOOP


def test_clarify_text_returns_prompt():
    r = IntentReasoner()
    d = StrategyMetrics.default_decision(IntentType.CLARIFICATION, "ambiguous")
    assert isinstance(r.clarify_text(d), str)
    assert r.clarify_text(d)


def test_default_classifier_and_properties():
    r = IntentReasoner()
    assert isinstance(r.classifier, RuleBasedIntentClassifier)
    assert r.max_clarification_turns == 2
    assert r.memory_retriever is None
