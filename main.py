"""
Aether v1 Legacy Entry Point (DEPRECATED)

This file references modules from the old v1 architecture (core/, perception/,
memory/, context/, interface/, interaction/) which have been migrated to the
aether package as plugins.

Use the new entry point instead:
    python -m aether                    # headless boot
    python -m aether --mode tick        # 30Hz tick loop
    python -m aether --mode vision      # vision pipeline (placeholder)
"""

import logging
import sys

logger = logging.getLogger("Aether.Main")


def main() -> int:
    logger.error(
        "main.py is a legacy v1 entry point and can no longer be run directly.\n"
        "Use: python -m aether\n"
        "      python -m aether --mode tick\n"
        "      python -m aether --mode vision"
    )
    print(
        "ERROR: This is a legacy entry point.\n"
        "       Use: python -m aether\n"
        "            python -m aether --mode tick",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
