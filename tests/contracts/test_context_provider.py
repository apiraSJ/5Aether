"""Contract tests for IContextProvider.

Every adapter that implements IContextProvider must pass these tests.

Run with: pytest tests/contracts/test_context_provider.py -v
"""

import pytest
from typing import Optional

from aether.domain.context_snapshot import ContextSnapshot, InteractionMode
from aether.core.interfaces.i_context_provider import IContextProvider


class ContextProviderContract:
    """Mixin class for context provider contract tests.

    Subclasses must set self.provider in setup_method().
    """

    provider: IContextProvider

    def setup_method(self):
        raise NotImplementedError

    # ── snapshot ──────────────────────────────────────────────────

    def test_snapshot_returns_context(self):
        ctx = self.provider.snapshot()
        assert isinstance(ctx, ContextSnapshot)

    def test_snapshot_has_timestamp(self):
        ctx = self.provider.snapshot()
        assert ctx.timestamp is not None

    def test_snapshot_has_mode(self):
        ctx = self.provider.snapshot()
        assert isinstance(ctx.interaction_mode, InteractionMode)

    def test_snapshot_is_immutable(self):
        ctx = self.provider.snapshot()
        with pytest.raises(AttributeError):
            ctx.interaction_mode = InteractionMode.DEVELOPER

    # ── current_mode ──────────────────────────────────────────────

    def test_current_mode(self):
        mode = self.provider.current_mode()
        assert isinstance(mode, InteractionMode)

    # ── active_target ─────────────────────────────────────────────

    def test_active_target_returns_string_or_none(self):
        target = self.provider.active_target()
        assert target is None or isinstance(target, str)

    # ── session_id ────────────────────────────────────────────────

    def test_session_id(self):
        sid = self.provider.session_id()
        assert isinstance(sid, str)
        assert len(sid) > 0

    # ── invalidate ────────────────────────────────────────────────

    def test_invalidate_does_not_crash(self):
        self.provider.invalidate()
        ctx = self.provider.snapshot()
        assert isinstance(ctx, ContextSnapshot)
