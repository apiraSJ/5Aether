"""Tests for ConfigLoader — load, defaults, deep merge, schema validation."""
import tempfile
from pathlib import Path

import yaml

from aether.config.loader import ConfigError, ConfigLoader, ConfigSchema


class TestConfigLoader:
    def test_load_creates_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config" / "default.yaml"
            loader = ConfigLoader(str(path))
            data = loader.load()
            assert path.exists()
            assert "app" in data
            assert data["app"]["name"] == "Aether"

    def test_load_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(yaml.safe_dump({"app": {"name": "Custom"}}))
            loader = ConfigLoader(str(path))
            data = loader.load()
            assert data["app"]["name"] == "Custom"

    def test_deep_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(yaml.safe_dump({
                "app": {"name": "Custom"},
                "logging": {"level": "DEBUG"},
            }))
            loader = ConfigLoader(str(path))
            data = loader.load()
            assert data["app"]["name"] == "Custom"
            assert data["logging"]["level"] == "DEBUG"
            # Defaults preserved
            assert data["logging"]["console"] is True

    def test_get_dotted_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(yaml.safe_dump({"a": {"b": {"c": 42}}}))
            loader = ConfigLoader(str(path))
            loader.load()
            assert loader.get("a.b.c") == 42
            assert loader.get("a.b.d", "default") == "default"

    def test_invalid_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(": invalid: yaml: {{{}}}}:")
            loader = ConfigLoader(str(path))
            try:
                loader.load()
                assert False, "Should have raised"
            except ConfigError:
                pass

    def test_non_dict_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("just a string")
            loader = ConfigLoader(str(path))
            try:
                loader.load()
                assert False, "Should have raised"
            except ConfigError:
                pass


class TestConfigSchema:
    def test_validate_passes(self):
        schema = ConfigSchema(required_keys=["app.name", "logging.level"])
        data = {"app": {"name": "Aether"}, "logging": {"level": "INFO"}}
        missing = schema.validate(data)
        assert missing == []

    def test_validate_missing(self):
        schema = ConfigSchema(required_keys=["app.name", "app.missing"])
        data = {"app": {"name": "Aether"}}
        missing = schema.validate(data)
        assert missing == ["app.missing"]

    def test_loader_validate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(yaml.safe_dump({"app": {"name": "X"}}))
            loader = ConfigLoader(str(path))
            loader.load()
            schema = ConfigSchema(required_keys=["app.name"])
            missing = loader.validate(schema)
            assert missing == []
