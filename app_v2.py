#!/usr/bin/env python3
"""
Aether — Phase B Entry Point

Boot → Tick Loop → Shutdown with MemoryService + KeyboardInputPlugin.
Proves the Application Lifecycle works end-to-end.
"""

from __future__ import annotations

import sys

from aether.core.application import AetherApplication


def main() -> int:
    app = AetherApplication(config_path="config/default.yaml")
    return app.run()


if __name__ == "__main__":
    sys.exit(main())