#!/usr/bin/env python3
"""
Aether — Single Entry Point

Usage:
    python -m aether                    # Phase A: headless boot proof
    python -m aether --mode tick        # Phase B: 30Hz tick loop
    python -m aether --mode headless    # Same as default
    python -m aether --mode web         # Mark-1 web API + UI (127.0.0.1:8765)
    python -m aether --mode vision      # Vision pipeline (camera + hands + objects)
    python -m aether --mode vision --profile --duration 30   # Profile for 30s then print report
    python -m aether --config config/vision.yaml
    python -m aether --strict-plugins

When launched with an interpreter outside the project .venv (e.g. a global
Python on PATH), the process re-launches itself with .venv/Scripts/python —
the project environment is the single source of dependencies.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "default.yaml"
VISION_CONFIG = PROJECT_ROOT / "config" / "vision.yaml"
WEB_CONFIG = PROJECT_ROOT / "config" / "web.yaml"
VENV_PYTHON = (
    PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if os.name == "nt"
    else PROJECT_ROOT / ".venv" / "bin" / "python"
)
REEXEC_ENV = "AETHER_VENV_REEXEC"

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
  python -m aether --mode web         Mark-1 web API + UI on 127.0.0.1:8765
  python -m aether --config config/archive/desktop.yaml
  python -m aether --strict-plugins"""
    )
    parser.add_argument(
        "--mode",
        choices=["headless", "tick", "web", "vision"],
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
    parser.add_argument(
        "--background",
        action="store_true",
        help="start with UI hidden (override gui.start_visible config)"
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


def _run_vision(config_path: str, strict_plugins: bool, profile: bool = False, duration: int = 0, background: bool = False) -> int:
    """Run vision pipeline: camera + hand tracking + object detection + cursor control."""
    from aether.core.application import AetherApplication
    from aether.core.profiler import profiler
    
    logger.info("Starting vision mode with config: %s", config_path)
    app = AetherApplication(config_path=config_path, strict_plugins=strict_plugins, background=background)
    
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


def _reexec_in_venv_if_needed(raw_argv: list) -> None:
    """Re-launch ``python -m aether`` under the project .venv interpreter.

    Any guard hit skips the re-exec and the current interpreter continues:

      1. ``REEXEC_ENV`` is already set — this process IS the re-launched
         child (loop protection). The flag travels only inside the child's
         environment (``env=`` copy); neither the parent's ``os.environ``
         nor the user's shell is ever modified.
      2. Already inside a virtual environment (``sys.prefix != base_prefix``).
      3. The project .venv does not exist yet — ``start.py`` bootstraps it.

    ``PROJECT_ROOT`` comes from ``__file__`` (never the CWD), and the child
    runs with ``cwd=PROJECT_ROOT`` so it resolves the package regardless of
    where the parent was started from.

    The child's exit code is forwarded verbatim. On Ctrl+C the signal reaches
    parent and child together (same console); the child owns graceful
    shutdown, so the parent only collects the child's real exit code —
    escalating to kill + 130 solely when interrupted twice.

    Args:
        raw_argv: Unparsed CLI arguments to forward to the child process.

    Raises:
        SystemExit: Always, with the child's exit code (re-exec terminal).
    """
    if REEXEC_ENV in os.environ:
        return
    if sys.prefix != sys.base_prefix:
        return
    if not VENV_PYTHON.exists():
        return

    child_env = os.environ.copy()
    child_env[REEXEC_ENV] = "1"
    cmd = [str(VENV_PYTHON), "-m", "aether", *raw_argv]
    print(f"[Aether] Re-launching with .venv interpreter: {VENV_PYTHON}", flush=True)
    proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), env=child_env)
    try:
        code = proc.wait()
    except KeyboardInterrupt:
        # Ctrl+C hit both processes — wait for the child's clean shutdown
        # instead of masking its exit code in the parent.
        try:
            code = proc.wait()
        except KeyboardInterrupt:
            proc.kill()
            code = 130
    raise SystemExit(code)


def main(argv: Optional[list] = None) -> int:
    raw_argv = list(sys.argv[1:]) if argv is None else list(argv)
    _reexec_in_venv_if_needed(raw_argv)

    args = _parse_args(argv)
    
    # Auto-select vision config for vision mode
    if args.mode == "vision" and args.config is None:
        config_path = str(VISION_CONFIG)
        print(f"  [auto] Using vision config: {VISION_CONFIG.name}")
    # Auto-select web config for web mode (minimal plugin set, no GUI/AI)
    elif args.mode == "web" and args.config is None:
        config_path = str(WEB_CONFIG)
        print(f"  [auto] Using web config: {WEB_CONFIG.name}")
    else:
        config_path = _resolve_config(args.config)

    print(BANNER)
    print(f"  config : {config_path}")
    print(f"  mode   : {args.mode}")
    print()

    if args.mode == "tick":
        from aether.core.application import AetherApplication
        app = AetherApplication(config_path=config_path, strict_plugins=args.strict_plugins, background=args.background)
        return _run_tick(app)
    elif args.mode == "vision":
        return _run_vision(config_path, args.strict_plugins, args.profile, args.duration, background=args.background)
    else:
        from aether.app import AetherApp, AetherAppBootError
        app = AetherApp(config_path=config_path, strict_plugins=args.strict_plugins, background=args.background)
        try:
            app.boot()
        except AetherAppBootError as exc:
            print(f"[Aether] FATAL: {exc}", file=sys.stderr)
            logging.getLogger("Aether.Main").critical("Boot failed: %s", exc)
            return 1
        if args.mode == "web":
            from aether.api.server import run as run_web
            return run_web(app)
        return _run_headless(app)


if __name__ == "__main__":
    sys.exit(main())
