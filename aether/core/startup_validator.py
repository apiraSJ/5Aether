"""StartupDependencyValidator — validates plugin dependencies before boot.

Prevents silent degraded-mode failures by checking that every required
service is registered in the DI container before plugins start.

Usage:
    validator = StartupDependencyValidator(container)
    validator.register("interaction_plugin", PluginDependency("input_router", "InputRouter"))
    validator.validate()
    # Raises DependencyError with full report if any dependency is missing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List

from aether.core.service_container import ServiceContainer

logger = logging.getLogger("Aether.StartupValidator")


class DependencyError(Exception):
    """Raised when one or more plugin dependencies are not satisfied."""


@dataclass
class PluginDependency:
    """A single dependency requirement for a plugin.

    Attributes:
        service_name: Name in the DI container (e.g. 'input_router').
        description: Human-readable description for error messages.
    """

    service_name: str
    description: str = ""


@dataclass
class DependencyReport:
    """Result of a full validation run."""

    passed: bool = True
    total: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)


class StartupDependencyValidator:
    """Validates that all required services are registered in the DI container.

    Call register() for each plugin during initialize(), then call validate()
    before start() to fail fast with clear error messages.
    """

    def __init__(self, container: ServiceContainer) -> None:
        self._container = container
        self._dependencies: Dict[str, List[PluginDependency]] = {}

    def register(
        self,
        plugin_name: str,
        *dependencies: PluginDependency,
    ) -> None:
        """Register dependencies for a plugin.

        Args:
            plugin_name: Plugin name (e.g. 'interaction_plugin').
            dependencies: Required services for this plugin.
        """
        if plugin_name not in self._dependencies:
            self._dependencies[plugin_name] = []
        self._dependencies[plugin_name].extend(dependencies)

    def validate(self) -> DependencyReport:
        """Check all registered dependencies against the container.

        Returns:
            DependencyReport with pass/fail status and error details.

        Raises:
            DependencyError if any dependency is missing.
        """
        report = DependencyReport()

        for plugin_name, deps in sorted(self._dependencies.items()):
            for dep in deps:
                report.total += 1
                if not self._container.has(dep.service_name):
                    report.failed += 1
                    msg = (
                        f"Plugin '{plugin_name}' requires '{dep.service_name}'"
                        f" ({dep.description}) — not found in container."
                    )
                    report.errors.append(msg)
                    logger.error(msg)

        if report.failed > 0:
            report.passed = False
            summary = (
                f"Dependency validation FAILED: {report.failed}/{report.total}"
                f" dependencies missing. "
                f"Errors:\n  " + "\n  ".join(report.errors)
            )
            raise DependencyError(summary)

        logger.info(
            "Dependency validation PASSED: %d dependencies checked.",
            report.total,
        )
        return report

    def clear(self) -> None:
        """Remove all registered dependencies."""
        self._dependencies.clear()