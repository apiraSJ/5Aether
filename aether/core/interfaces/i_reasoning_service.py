"""IReasoningService — the L3 contract for interpretation.

This is NOT memory. This is NOT perception. This is the layer that:
    1. Takes a question + context + memory
    2. Interprets, infers, and summarizes
    3. Returns an Answer

Design:
    ReasoningService uses IMemoryService (not IMemoryRepository).
    ReasoningService uses IContextProvider (not raw window/mouse data).

    IContextProvider
        ↓
    ContextSnapshot
        ↓
    IReasoningService ← IMemoryService
        ↓
    Answer

Rule from KNOWLEDGE.md:
    "Reasoning should work even when perception is absent."
    (You can ask 'where is my laptop?' without opening the camera)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

from aether.domain.context_snapshot import ContextSnapshot
from aether.domain.spatial_object import SpatialObject


@dataclass(frozen=True)
class Answer:
    """Result of a reasoning operation.

    Contains the answer string, confidence, and supporting evidence.

    Example:
        answer = Answer(
            text="Your laptop is on the desk, left of the charger",
            confidence=0.95,
            evidence=[laptop_object, charger_object],
        )
    """

    text: str = ""
    confidence: float = 0.0
    evidence: list[SpatialObject] = None
    reasoning_chain: list[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.evidence is None:
            object.__setattr__(self, "evidence", [])
        if self.reasoning_chain is None:
            object.__setattr__(self, "reasoning_chain", [])
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})


class IReasoningService(ABC):
    """Interpretation layer between memory and user interaction."""

    @abstractmethod
    def where_is(
        self,
        name: str,
        context: Optional[ContextSnapshot] = None,
    ) -> Answer:
        """Answer 'where is <name>?' using memory + context.

        Uses context to disambiguate:
        - Developer mode: "laptop" might mean "my development laptop"
        - Normal mode: "laptop" might mean "the laptop on the desk"
        """
        ...

    @abstractmethod
    def what_is_near(
        self,
        name: str,
        context: Optional[ContextSnapshot] = None,
    ) -> Answer:
        """Answer 'what is near <name>?' using spatial relations."""
        ...

    @abstractmethod
    def infer(
        self,
        question: str,
        context: Optional[ContextSnapshot] = None,
    ) -> Answer:
        """General inference from question + context + memory.

        This is the extension point for LLM integration in the future.
        """
        ...

    @abstractmethod
    def summarize(
        self,
        context: Optional[ContextSnapshot] = None,
    ) -> Answer:
        """Summarize current spatial memory state.

        Example: "You have 3 objects: laptop (desk), charger (desk),
        monitor (desk). All last seen 2 hours ago."
        """
        ...

    @abstractmethod
    def get_help(self) -> str:
        """Return human-readable help about reasoning capabilities."""
        ...
