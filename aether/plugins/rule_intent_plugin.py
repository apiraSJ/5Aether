"""RuleIntentPlugin — rule-based intent resolution via regex patterns.

Implements IIntentResolver with fast, deterministic pattern matching.
No external dependencies. Catches common commands before LLM fallback.

Pattern priority: longer/more specific patterns are checked first.
Each pattern maps to an intent label and a command name.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from aether.core.intent_resolver import IntentResult
from aether.core.plugin import PluginBase, PluginMetadata
from aether.core.service_container import ServiceContainer

logger = logging.getLogger("Aether.Intent.RuleEngine")


@dataclass(frozen=True)
class IntentPattern:
    """A single regex pattern that maps user input to a command."""

    intent: str
    command_name: str
    pattern: re.Pattern[str]
    params_extractor: Optional[str] = None  # named group to extract as params key
    confidence: float = 0.95
    description: str = ""
    examples: tuple[str, ...] = ()


# ── Pattern definitions ────────────────────────────────────────────────

_PATTERNS: list[IntentPattern] = [
    # System commands
    IntentPattern(
        intent="system.help",
        command_name="system.help",
        pattern=re.compile(r"^\s*help\s*(?P<category>\w+)?\s*$", re.I),
        params_extractor="category",
        description="Show help for a command or category",
    ),
    IntentPattern(
        intent="system.status",
        command_name="system.status",
        pattern=re.compile(r"^\s*status\s*$", re.I),
        description="Show system status",
    ),
    IntentPattern(
        intent="system.plugins",
        command_name="system.plugins",
        pattern=re.compile(r"^\s*plugins?\s*$", re.I),
        description="List loaded plugins",
    ),
    IntentPattern(
        intent="system.commands",
        command_name="system.commands",
        pattern=re.compile(r"^\s*commands?\s*$", re.I),
        description="List all registered commands",
    ),
    IntentPattern(
        intent="system.shutdown",
        command_name="system.shutdown",
        pattern=re.compile(r"^\s*(quit|exit|shutdown)\s*$", re.I),
        description="Shutdown Aether",
    ),
    IntentPattern(
        intent="system.ping",
        command_name="system.ping",
        pattern=re.compile(r"^\s*ping\s*$", re.I),
        description="Ping the system",
    ),
    IntentPattern(
        intent="cli.history",
        command_name="cli.history",
        pattern=re.compile(r"^\s*history\s*$", re.I),
        description="Show command history",
    ),
    IntentPattern(
        intent="cli.clear",
        command_name="cli.clear",
        pattern=re.compile(r"^\s*clear\s*$", re.I),
        description="Clear the screen",
    ),

    # Vision commands
    IntentPattern(
        intent="vision.scan",
        command_name="vision.scan",
        pattern=re.compile(r"^\s*scan\s*(?:room)?\s*$", re.I),
        description="Scan the room with camera",
    ),

    # Memory commands — find / recall
    IntentPattern(
        intent="memory.find",
        command_name="memory.recall",
        pattern=re.compile(r"^\s*(?:find|search|where\s+is|look\s+for)\s+(?P<query>.+?)\s*$", re.I),
        params_extractor="query",
        description="Find a remembered object",
        examples=("find phone", "where is my keys"),
    ),
    IntentPattern(
        intent="memory.remember",
        command_name="memory.remember",
        pattern=re.compile(
            r"^\s*(?:remember|save|store)\s+(?P<name>\S+?)(?:\s+(?:at|on|in|near)\s+(?P<location>.+?))?\s*$",
            re.I,
        ),
        description="Remember an object and its location",
        examples=("remember bottle", "save keys at desk"),
    ),
    IntentPattern(
        intent="memory.forget",
        command_name="memory.forget",
        pattern=re.compile(r"^\s*(?:forget|delete|remove)\s+(?P<name>\S+)\s*$", re.I),
        params_extractor="name",
        description="Forget an object from memory",
    ),
    IntentPattern(
        intent="memory.list",
        command_name="memory.list",
        pattern=re.compile(r"^\s*(?:list|show)\s+(?:all|objects|items|memory)\s*$", re.I),
        description="List all remembered objects",
    ),
]


class RuleIntentPlugin(PluginBase):
    """Rule-based intent resolver. Fast, deterministic, no external deps.

    Registers as an intent resolver. The IntentResolver plugin calls
    resolve() on this plugin when CLI_INPUT_RECEIVED fires.
    """

    name = "rule_intent_plugin"

    def __init__(self) -> None:
        self._patterns = list(_PATTERNS)

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="Rule Intent Engine",
            version="1.0",
            category="intent",
            description="Rule-based natural language to command resolution",
        )

    def initialize(self, container: ServiceContainer) -> None:
        """Register this resolver. No dependencies needed."""
        container.register_instance("intent_resolver.rule", self)
        logger.info(
            "RuleIntentEngine loaded with %d patterns", len(self._patterns)
        )

    def resolve(self, user_input: str) -> Optional[IntentResult]:
        """Try to match user input against known patterns.

        Returns IntentResult if matched, None otherwise.
        """
        text = user_input.strip()
        if not text:
            return None

        for pat in self._patterns:
            m = pat.pattern.match(text)
            if m:
                params = {}
                groups = m.groupdict()

                if pat.params_extractor and pat.params_extractor in groups:
                    params["query"] = groups[pat.params_extractor]

                if "name" in groups and groups["name"]:
                    params["name"] = groups["name"]
                if "location" in groups and groups["location"]:
                    params["location"] = groups["location"]
                if "query" in groups and groups["query"]:
                    params["query"] = groups["query"]
                if "category" in groups and groups["category"]:
                    params["category"] = groups["category"]

                return IntentResult(
                    intent=pat.intent,
                    command_name=pat.command_name,
                    params=params,
                    confidence=pat.confidence,
                    source="rule",
                    raw_input=text,
                )

        return None

    def can_resolve(self, user_input: str) -> bool:
        """Quick check: does any pattern match?"""
        return self.resolve(user_input) is not None

    def get_pattern_count(self) -> int:
        return len(self._patterns)
