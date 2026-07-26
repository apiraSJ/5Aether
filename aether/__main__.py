#!/usr/bin/env python3
"""
Aether — Single Entry Point

Usage:
    python -m aether                    # Phase A: headless boot proof
    python -m aether --mode tick        # Phase B: 30Hz tick loop
    python -m aether --mode headless    # Same as default
    python -m aether --mode vision      # Vision pipeline (camera + hands + objects)
    python -m aether --mode vision --profile --duration 30   # Profile for 30s then print report
    python -m aether --config config/vision.yaml
    python -m aether --strict-plugins
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "default.yaml"
VISION_CONFIG = PROJECT_ROOT / "config" / "vision.yaml"

BANNER = r"""
   ___    __      __  ___          __
  / _ |  / /  ___/ / / _ )___  ___/ /__
 / __ | / /__/ _  / / _  / _ \/ _  (_-<
/_/ |_|/____/\_,_/_/_/ /_//_/\_,_/___/
"""

logger = logging.getLogger("Aether.Main")
_shutdown_requested = False


def _parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="aether",
        description="Aether — Command-Driven Spatial AI Operating System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""project root: {PROJECT_ROOT}

examples:
  python -m aether                    boot + dispatch demo commands
  python -m aether --mode tick        30Hz tick loop with plugins
  python -m aether --mode headless    same as default (no tick loop)
  python -m aether --mode vision      camera + hand tracking + object detection
  python -m aether --config config/desktop.yaml
  python -m aether --strict-plugins"""
    )
    parser.add_argument(
        "--mode",
        choices=["headless", "tick", "vision"],
        default="headless",
        help="run mode (default: headless)"
    )
    parser.add_argument(
        "--config",
        default=None,
        help=f"path to YAML config (default: {DEFAULT_CONFIG})"
    )
    parser.add_argument(
        "--strict-plugins",
        action="store_true",
        help="abort boot if any plugin fails"
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="run in profiling mode (records metrics, prints report at exit)"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=0,
        help="profiling duration in seconds (0 = run until Ctrl+C)"
    )
    return parser.parse_args(argv)


def _resolve_config(config_arg: Optional[str]) -> str:
    """Resolve config path: if None, use project default. Otherwise resolve relative to project root."""
    if config_arg is None:
        return str(DEFAULT_CONFIG)
    p = Path(config_arg)
    if p.is_absolute():
        return str(p)
    # Relative path — resolve from project root first, then CWD
    from_root = PROJECT_ROOT / p
    if from_root.exists():
        return str(from_root)
    return str(p.resolve())


def _install_signal_handlers(app) -> None:
    def _handle_signal(signum: int, frame) -> None:
        global _shutdown_requested
        logger.info("Received signal %s, requesting shutdown...", signum)
        _shutdown_requested = True
        if hasattr(app, 'request_shutdown'):
            app.request_shutdown()

    signal.signal(signal.SIGINT, _handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_signal)


def _sleep_fallback() -> None:
    import time
    time.sleep(0.25)


def _run_headless(app) -> int:
    try:
        _run_boot_proof(app)
        _install_signal_handlers(app)
        logger.info("Aether running (headless). Press Ctrl+C to stop.")
        while not _shutdown_requested:
            signal.pause() if hasattr(signal, "pause") else _sleep_fallback()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received.")
    finally:
        app.shutdown()
    return 0


def _run_tick(app) -> int:
    if not app.is_booted:
        app.boot()
    _install_signal_handlers(app)
    return app.run()


def _run_vision(config_path: str, strict_plugins: bool, profile: bool = False, duration: int = 0) -> int:
    """Run vision pipeline: camera + hand tracking + object detection + cursor control."""
    from aether.core.application import AetherApplication
    from aether.core.profiler import profiler
    
    logger.info("Starting vision mode with config: %s", config_path)
    app = AetherApplication(config_path=config_path, strict_plugins=strict_plugins)
    
    # Run boot proof first to verify plugins loaded
    try:
        app.boot()
        _run_boot_proof(app)
    except Exception as exc:
        logger.error("Vision boot failed: %s", exc)
        print(f"[Aether] Vision boot failed: {exc}", file=sys.stderr)
        return 1
    
    if profile:
        profiler.start_recording()
        logger.info("Profiling mode enabled (duration=%ds, Ctrl+C to stop)", duration)
    
    _install_signal_handlers(app)

    # If duration is set, schedule auto-shutdown
    if profile and duration > 0:
        import threading
        def _auto_shutdown():
            import time
            time.sleep(duration)
            report = profiler.stop_recording(save_to="profile_results.txt")
            print(profiler.format_report(report))
            app.request_shutdown()
        t = threading.Thread(target=_auto_shutdown, daemon=True)
        t.start()

    result = app.run()

    if profile and duration == 0:
        profiler.stop_recording(save_to="profile_results.txt")
        print(profiler.format_report())

    return result


def _run_boot_proof(app) -> None:
    from aether.core.command import Command
    if app.command_bus is None:
        return

    ping_result = app.command_bus.dispatch_sync(
        Command(name="system.ping", source="boot_proof", params={"hello": "aether"})
    )
    if hasattr(ping_result, "success"):
        logger.info("Boot proof 'system.ping' -> success=%s message=%s", ping_result.success, ping_result.message)
    elif isinstance(ping_result, dict):
        logger.info("Boot proof 'system.ping' -> result=%s", ping_result)
    else:
        logger.info("Boot proof 'system.ping' -> no handler registered (command=%s)", ping_result.name)

    if app.command_bus.is_registered("system.info"):
        info_result = app.command_bus.dispatch_sync(Command(name="system.info", source="boot_proof"))
        if hasattr(info_result, "success"):
            logger.info("Boot proof 'system.info' -> success=%s data=%s", info_result.success, info_result.data)
        elif isinstance(info_result, dict):
            logger.info("Boot proof 'system.info' -> result=%s", info_result)
        else:
            logger.info("Boot proof 'system.info' -> no handler registered")


def main(argv: Optional[list] = None) -> int:
    args = _parse_args(argv)
    
    # Auto-select vision config for vision mode
    if args.mode == "vision" and args.config is None:
        config_path = str(VISION_CONFIG)
        print(f"  [auto] Using vision config: {VISION_CONFIG.name}")
    else:
        config_path = _resolve_config(args.config)

    print(BANNER)
    print(f"  config : {config_path}")
    print(f"  mode   : {args.mode}")
    print()

    if args.mode == "tick":
        from aether.core.application import AetherApplication
        app = AetherApplication(config_path=config_path, strict_plugins=args.strict_plugins)
        return _run_tick(app)
    elif args.mode == "vision":
        return _run_vision(config_path, args.strict_plugins, args.profile, args.duration)
    else:
        from aether.app import AetherApp, AetherAppBootError
        app = AetherApp(config_path=config_path, strict_plugins=args.strict_plugins)
        try:
            app.boot()
        except AetherAppBootError as exc:
            print(f"[Aether] FATAL: {exc}", file=sys.stderr)
            logging.getLogger("Aether.Main").critical("Boot failed: %s", exc)
            return 1
        return _run_headless(app)


if __name__ == "__main__":
    sys.exit(main())
