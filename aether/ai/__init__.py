"""Aether AI — pluggable assistant backend, service facade, and context building.

Architecture:
    Widget/CLI/Voice → CommandBus(ai.chat) → AIPlugin → AIService → AIProvider
                                        ↓ publishes ai.* events
                                     EventBus

Phase 1 ships the offline EchoProvider so the full pipeline works without
any external API key or model download. Real backends implement AIProvider
and are selected via config `ai.provider`.
"""
