"""IIntentResolver — interface for converting natural language to Commands.

Design: IntentResolver is an interface, not an implementation. Multiple
resolvers can coexist:

  - RuleIntentResolver   (regex patterns, fast, no dependencies)
  - OllamaIntentResolver (LLM-powered, Phase 3B)
  - CloudIntentResolver  (future)

The IntentResolver plugin subscribes to CLI_INPUT_RECEIVED events and
publishes COMMAND_REQUESTED events. This keeps the CLI, Voice, GUI palette,
and Remote API on the same pipeline.

Intent ≠ Command (1:1). A single intent like "find phone and open its page"
may resolve to multiple commands via a workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


@dataclass
class IntentResult:
    """Result of intent resolution. Maps natural language to command(s).

    Attributes:
        intent:       High-level intent label, e.g. "memory.find", "system.status".
                      May differ from command_name when intents map to workflows.
        command_name: Canonical command name to dispatch, e.g. "memory.recall".
        params:       Parameters extracted from the input.
        confidence:   0.0 (no confidence) to 1.0 (certain match).
        source:       Which resolver produced this: "rule", "llm", "future".
        raw_input:    The original user input string.
    """

    intent: str
    command_name: str
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source: str = "rule"
    raw_input: str = ""


class IIntentResolver(Protocol):
    """Protocol for intent resolvers. Implement this to add a new resolution backend.

    The IntentResolver plugin iterates over registered resolvers in priority order.
    First resolver with confidence >= threshold wins.
    """

    @property
    def resolver_name(self) -> str:
        """Human-readable name for logging, e.g. 'rule_engine', 'ollama'."""
        ...

    @property
    def priority(self) -> int:
        """Lower number = checked first. Rule engine = 10, LLM = 50."""
        ...

    def resolve(self, user_input: str) -> Optional[IntentResult]:
        """Try to resolve user input into a command.

        Returns IntentResult if resolved, None if this resolver can't handle it.
        Confidence below threshold means the result is unreliable.
        """
        ...

    def can_resolve(self, user_input: str) -> bool:
        """Quick check: can this resolver handle the input at all?
        Used for fast-path skipping (e.g. rule engine skips if no regex matches).
        """
        ...
