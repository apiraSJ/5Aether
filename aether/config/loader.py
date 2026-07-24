"""
Configuration loader for Aether.

Responsibilities:
    - Load a YAML configuration file from disk.
    - If the file does not exist, write out sane defaults and continue,
      so a fresh checkout can always boot.
    - Deep-merge the file's contents on top of in-code defaults, so partial
      configuration files (only overriding what the user cares about) work
      correctly instead of wiping out unspecified sections.
    - Provide dotted-path access, e.g. config.get("logging.level").

This module intentionally has zero knowledge of what the configuration is
used FOR. It only knows how to load, merge, and serve a dictionary.
"""

from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger("Aether.Config")


class ConfigError(Exception):
    """Raised when the configuration file exists but cannot be parsed,
    or when a required key is missing and no default was supplied."""


class ConfigSchema:
    """Validates that required config keys exist after loading."""

    def __init__(self, required_keys: list[str] | None = None) -> None:
        self.required_keys = required_keys or []

    def validate(self, data: dict[str, Any]) -> list[str]:
        """Check all required keys exist. Returns list of missing keys."""
        missing = []
        for key in self.required_keys:
            parts = key.split(".")
            node = data
            found = True
            for part in parts:
                if isinstance(node, dict) and part in node:
                    node = node[part]
                else:
                    found = False
                    break
            if not found:
                missing.append(key)
        return missing


_DEFAULT_CONFIG: Dict[str, Any] = {
    "app": {
        "name": "Aether",
        "version": "0.1.0-phase-a",
    },
    "logging": {
        "level": "INFO",
        "file": "logs/aether.log",
        "console": True,
    },
    "plugins": [],
}


class ConfigLoader:
    """Loads, merges, and serves Aether's YAML configuration."""

    def __init__(self, path: str = "config/default.yaml", defaults: Optional[Dict[str, Any]] = None):
        self.path = Path(path)
        self._defaults: Dict[str, Any] = copy.deepcopy(defaults if defaults is not None else _DEFAULT_CONFIG)
        self._data: Dict[str, Any] = {}
        self._loaded = False

    def load(self) -> Dict[str, Any]:
        """Load the configuration file, creating it with defaults if missing.

        Returns the fully merged configuration dictionary. Raises ConfigError
        if the file exists but contains invalid YAML or a non-mapping root.
        """
        if not self.path.exists():
            logger.warning(
                "Config file '%s' not found. Creating it with default values.",
                self.path,
            )
            self._write_defaults()
            self._data = copy.deepcopy(self._defaults)
            self._loaded = True
            return self._data

        try:
            raw_text = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"Could not read config file '{self.path}': {exc}") from exc

        try:
            parsed = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Config file '{self.path}' contains invalid YAML: {exc}") from exc

        if parsed is None:
            parsed = {}

        if not isinstance(parsed, dict):
            raise ConfigError(
                f"Config file '{self.path}' must contain a mapping at the root, "
                f"got {type(parsed).__name__} instead."
            )

        self._data = self._deep_merge(self._defaults, parsed)
        self._loaded = True
        logger.info("Loaded configuration from '%s'.", self.path)
        return self._data

    def get(self, key_path: str, default: Any = None) -> Any:
        """Retrieve a value using dotted-path notation, e.g. 'logging.level'."""
        if not self._loaded:
            self.load()

        node: Any = self._data
        for part in key_path.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node

    @property
    def data(self) -> Dict[str, Any]:
        if not self._loaded:
            self.load()
        return self._data

    def validate(self, schema: ConfigSchema) -> list[str]:
        """Validate loaded config against a schema. Returns missing keys."""
        if not self._loaded:
            self.load()
        return schema.validate(self._data)

    def _write_defaults(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8") as fh:
                yaml.safe_dump(self._defaults, fh, sort_keys=False, allow_unicode=True)
        except OSError as exc:
            raise ConfigError(
                f"Could not create default config file at '{self.path}': {exc}"
            ) from exc

    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge `override` on top of `base` without mutating either input."""
        result = copy.deepcopy(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ConfigLoader._deep_merge(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result
