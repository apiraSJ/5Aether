"""Contract tests for IReasoningService.

Every adapter that implements IReasoningService must pass these tests.

Run with: pytest tests/contracts/test_reasoning_service.py -v
"""

import pytest
from typing import Optional

from aether.domain.spatial_object import SpatialObject, SpatialRelation
from aether.domain.context_snapshot import ContextSnapshot, InteractionMode
from aether.core.interfaces.i_reasoning_service import IReasoningService, Answer


class ReasoningServiceContract:
    """Mixin class for reasoning service contract tests.

    Subclasses must set self.service in setup_method().
    The underlying memory must be pre-populated with test data.
    """

    service: IReasoningService

    def setup_method(self):
        raise NotImplementedError

    # ── where_is ──────────────────────────────────────────────────

    def test_where_is_found(self):
        answer = self.service.where_is("laptop")
        assert isinstance(answer, Answer)
        assert answer.confidence > 0
        assert len(answer.text) > 0

    def test_where_is_not_found(self):
        answer = self.service.where_is("nonexistent_xyz")
        assert answer.confidence == 0.0
        assert "not found" in answer.text.lower() or "no" in answer.text.lower()

    def test_where_is_with_context(self):
        ctx = ContextSnapshot(interaction_mode=InteractionMode.DEVELOPER)
        answer = self.service.where_is("laptop", context=ctx)
        assert isinstance(answer, Answer)

    # ── what_is_near ──────────────────────────────────────────────

    def test_what_is_near(self):
        answer = self.service.what_is_near("laptop")
        assert isinstance(answer, Answer)
        assert len(answer.text) > 0

    def test_what_is_near_not_found(self):
        answer = self.service.what_is_near("nonexistent_xyz")
        assert isinstance(answer, Answer)

    # ── infer ─────────────────────────────────────────────────────

    def test_infer(self):
        answer = self.service.infer("what objects are in the desk?")
        assert isinstance(answer, Answer)
        assert len(answer.text) > 0

    def test_infer_empty_question(self):
        answer = self.service.infer("")
        assert isinstance(answer, Answer)

    # ── summarize ─────────────────────────────────────────────────

    def test_summarize(self):
        answer = self.service.summarize()
        assert isinstance(answer, Answer)
        assert len(answer.text) > 0

    def test_summarize_with_context(self):
        ctx = ContextSnapshot(interaction_mode=InteractionMode.NORMAL)
        answer = self.service.summarize(context=ctx)
        assert isinstance(answer, Answer)

    # ── get_help ──────────────────────────────────────────────────

    def test_get_help(self):
        help_text = self.service.get_help()
        assert isinstance(help_text, str)
        assert len(help_text) > 0
