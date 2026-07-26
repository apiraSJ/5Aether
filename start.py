#!/usr/bin/env python3
"""
Aether Quick Launcher

Double-click or run from terminal:
    python start.py              # headless boot
    python start.py --tick       # 30Hz tick loop
    python start.py --vision     # vision mode (not yet migrated)

Auto-detects venv and installs if needed.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PYTHON = VENV / "Scripts" / "python.exe" if os.name == "nt" else VENV / "bin" / "python"
ACTIVATE = VENV / "Scripts" / "activate.bat" if os.name == "nt" else VENV / "bin" / "activate"


def ensure_venv():
    """Create venv and install package if not already done."""
    if PYTHON.exists():
        return True

    print("[Aether] Setting up virtual environment...")
    subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)

    print("[Aether] Installing dependencies...")
    subprocess.run(
        [str(PYTHON), "-m", "pip", "install", "-e", ".", "-q"],
        cwd=str(ROOT),
        check=True,
    )
    print("[Aether] Setup complete.\n")
    return True


def run():
    """Run Aether with the venv Python."""
    args = sys.argv[1:]

    # Map shorthand flags
    if "--tick" in args:
        args.remove("--tick")
        args = ["--mode", "tick"] + args
    elif "--vision" in args:
        args.remove("--vision")
        args = ["--mode", "vision"] + args

    cmd = [str(PYTHON), "-m", "aether"] + args
    print(f"[Aether] Running: {' '.join(cmd)}\n")
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    try:
        ensure_venv()
        run()
    except KeyboardInterrupt:
        print("\n[Aether] Interrupted.")
    except subprocess.CalledProcessError as exc:
        print(f"\n[Aether] Error: {exc}", file=sys.stderr)
        raise SystemExit(exc.returncode)
