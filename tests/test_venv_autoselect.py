"""Auto-venv selection at the `python -m aether` entry point.

Covers:
    - Interpreter selection: outside-venv launch re-execs with .venv python
    - Argument forwarding to the child, order preserved verbatim
    - Loop guards: re-exec env flag, already-in-venv, missing .venv
    - Exit code forwarding + Ctrl+C (KeyboardInterrupt) handling
    - PROJECT_ROOT derived from __file__, independent of the CWD
    - start.py: web-mode passthrough, shorthand mapping, bootstrap extras
      (and no reinstall when an environment already exists)
"""

import os
import sys
from pathlib import Path

import pytest

import aether.__main__ as amain
import start


# ── Helpers ─────────────────────────────────────────────────────────


class _FakeProcess:
    """Stands in for subprocess.Popen with scripted wait() results."""

    def __init__(self, cmd, cwd=None, env=None):
        self.cmd = list(cmd)
        self.cwd = cwd
        self.env = env
        self.wait_results = [0]
        self.wait_calls = 0
        self.killed = False

    def wait(self):
        self.wait_calls += 1
        result = (
            self.wait_results.pop(0)
            if len(self.wait_results) > 1
            else self.wait_results[0]
        )
        if isinstance(result, BaseException):
            raise result
        return result

    def kill(self):
        self.killed = True


class _SpawnRecorder(list):
    """Records spawned fake processes; scripts wait() results for the next one."""

    def __init__(self):
        super().__init__()
        self.scripted = [0]  # default wait() result for each new fake process

    def spawn(self, cmd, cwd=None, env=None):
        proc = _FakeProcess(cmd, cwd=cwd, env=env)
        proc.wait_results = list(self.scripted)
        self.append(proc)
        return proc


@pytest.fixture
def spawn(monkeypatch, tmp_path):
    """Simulate a non-venv interpreter + present project .venv.

    Returns the recorder (a list of spawned processes; empty = no re-exec).
    Set ``recorder.scripted`` before invoking to script the child's wait()
    results (e.g. ``[7]`` or ``[KeyboardInterrupt(), 0]``).
    """
    monkeypatch.setattr(sys, "prefix", sys.base_prefix)
    monkeypatch.delenv(amain.REEXEC_ENV, raising=False)

    fake_venv_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    fake_venv_python.parent.mkdir(parents=True)
    fake_venv_python.touch()
    monkeypatch.setattr(amain, "VENV_PYTHON", fake_venv_python)

    recorder = _SpawnRecorder()
    monkeypatch.setattr(amain.subprocess, "Popen", recorder.spawn)
    return recorder


# ── Interpreter selection ───────────────────────────────────────────


def test_reexec_launches_venv_python_with_cwd_and_guard_env(spawn, monkeypatch, tmp_path):
    """Outside .venv → child is the project .venv python, rooted at the repo."""
    monkeypatch.chdir(tmp_path)  # prove CWD plays no part in the decision

    with pytest.raises(SystemExit) as exc:
        amain._reexec_in_venv_if_needed(["--mode", "web"])

    assert len(spawn) == 1
    proc = spawn[0]
    assert proc.cmd[0] == str(amain.VENV_PYTHON)
    assert proc.cmd[1:3] == ["-m", "aether"]
    # Child exit code forwarded verbatim (default scripted result: 0)
    assert exc.value.code == 0
    # PROJECT_ROOT comes from __file__, not the (now foreign) CWD
    assert Path(proc.cwd) == amain.PROJECT_ROOT
    assert amain.PROJECT_ROOT == Path(amain.__file__).resolve().parent.parent
    # Guard flag exists ONLY in the child's environment...
    assert proc.env[amain.REEXEC_ENV] == "1"
    assert set(os.environ) <= set(proc.env)  # ...on top of a full copy
    # ...and never leaks into this process (nor the user's shell)
    assert amain.REEXEC_ENV not in os.environ


def test_reexec_forwards_child_exit_code(spawn):
    """Non-zero child status reaches the parent unchanged."""
    spawn.scripted = [7]

    with pytest.raises(SystemExit) as exc:
        amain._reexec_in_venv_if_needed(["--mode", "web"])

    assert exc.value.code == 7


def test_reexec_forwards_arguments_verbatim_in_order(spawn):
    """Every flag survives untouched, in the original order."""
    argv = ["--mode", "web", "--config", "config/web.yaml", "--strict-plugins"]

    with pytest.raises(SystemExit):
        amain._reexec_in_venv_if_needed(argv)

    assert spawn[0].cmd == [str(amain.VENV_PYTHON), "-m", "aether", *argv]


# ── Loop guards ─────────────────────────────────────────────────────


def test_reexec_skipped_when_guard_env_already_set(spawn, monkeypatch):
    """The re-launched child must never re-launch again (loop protection)."""
    monkeypatch.setenv(amain.REEXEC_ENV, "1")

    amain._reexec_in_venv_if_needed(["--mode", "web"])

    assert spawn == []


def test_reexec_skipped_inside_venv(spawn, monkeypatch):
    """Already on the project interpreter → nothing to do."""
    monkeypatch.setattr(sys, "prefix", r"C:\some\other\venv")
    monkeypatch.setattr(sys, "base_prefix", r"C:\Python314")

    amain._reexec_in_venv_if_needed(["--mode", "web"])

    assert spawn == []


def test_reexec_skipped_when_project_venv_missing(spawn, monkeypatch, tmp_path):
    """No .venv yet → start.py owns bootstrapping; run in current interpreter."""
    monkeypatch.setattr(amain, "VENV_PYTHON", tmp_path / "nope" / "python.exe")

    amain._reexec_in_venv_if_needed(["--mode", "web"])

    assert spawn == []


# ── Ctrl+C / process lifecycle ──────────────────────────────────────


def test_keyboard_interrupt_collects_child_exit_code(spawn):
    """One Ctrl+C: wait again for the child's graceful shutdown, keep its code."""
    spawn.scripted = [KeyboardInterrupt(), 0]

    with pytest.raises(SystemExit) as exc:
        amain._reexec_in_venv_if_needed([])

    assert exc.value.code == 0
    assert spawn[0].wait_calls == 2
    assert spawn[0].killed is False


def test_double_keyboard_interrupt_kills_child_and_exits_130(spawn):
    """Repeated Ctrl+C: never leave the parent hanging — kill + SIGINT code."""
    spawn.scripted = [KeyboardInterrupt(), KeyboardInterrupt()]

    with pytest.raises(SystemExit) as exc:
        amain._reexec_in_venv_if_needed([])

    assert exc.value.code == 130
    assert spawn[0].killed is True


# ── Call site: re-exec happens before anything else ─────────────────


def test_main_reexecs_before_banner_or_argument_parsing(spawn, capsys):
    """main() routes through re-exec first — no banner, no boot, raw args."""
    with pytest.raises(SystemExit):
        amain.main(["--mode", "web"])

    out = capsys.readouterr().out
    assert "Re-launching with .venv interpreter" in out
    assert "config :" not in out  # banner/config block never reached
    assert spawn[0].cmd == [str(amain.VENV_PYTHON), "-m", "aether", "--mode", "web"]


# ── start.py launcher ───────────────────────────────────────────────


def test_start_runs_web_mode_with_venv_python(monkeypatch):
    """`python start.py --mode web` → venv python, all args passed through."""
    calls = []

    def _call(cmd):
        calls.append(cmd)
        return 0

    monkeypatch.setattr(start.subprocess, "call", _call)
    monkeypatch.setattr(
        start.sys,
        "argv",
        ["start.py", "--mode", "web", "--config", "config/web.yaml", "--strict-plugins"],
    )

    with pytest.raises(SystemExit) as exc:
        start.run()

    assert exc.value.code == 0
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[0] == str(start.PYTHON)
    assert start.PYTHON.exists() and str(start.PYTHON).startswith(str(start.VENV))
    assert cmd[1:3] == ["-m", "aether"]
    assert cmd[3:] == ["--mode", "web", "--config", "config/web.yaml", "--strict-plugins"]


def test_start_shorthand_mapping_leaves_web_args_alone(monkeypatch):
    """--tick/--vision shorthands map; plain `--mode web` is never rewritten."""
    captured = {}

    def _call(cmd):
        captured["cmd"] = cmd
        return 0

    monkeypatch.setattr(start.subprocess, "call", _call)

    with pytest.raises(SystemExit):
        monkeypatch.setattr(start.sys, "argv", ["start.py", "--mode", "web"])
        start.run()
    assert captured["cmd"][3:] == ["--mode", "web"]

    with pytest.raises(SystemExit):
        monkeypatch.setattr(start.sys, "argv", ["start.py", "--tick", "--strict-plugins"])
        start.run()
    assert captured["cmd"][3:] == ["--mode", "tick", "--strict-plugins"]
    assert "--tick" not in captured["cmd"]

    with pytest.raises(SystemExit):
        monkeypatch.setattr(start.sys, "argv", ["start.py", "--vision", "--duration", "5"])
        start.run()
    assert captured["cmd"][3:] == ["--mode", "vision", "--duration", "5"]
    assert "--vision" not in captured["cmd"]


def test_ensure_venv_is_noop_when_environment_exists(monkeypatch, tmp_path):
    """Existing envs (e.g. .[full]) are never touched — no reinstall, no loss."""
    fake_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    fake_python.parent.mkdir(parents=True)
    fake_python.touch()
    monkeypatch.setattr(start, "PYTHON", fake_python)

    def _fail(*args, **kwargs):
        pytest.fail("bootstrap must not run when the environment exists")

    monkeypatch.setattr(start.subprocess, "run", _fail)

    assert start.ensure_venv() is True


def test_ensure_venv_installs_server_extras_for_new_environment(monkeypatch, tmp_path):
    """A fresh venv gets `pip install -e ".[server]"` so --mode web works."""
    calls = []
    venv_python = tmp_path / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    monkeypatch.setattr(start, "VENV", tmp_path / ".venv")
    monkeypatch.setattr(start, "PYTHON", venv_python)
    monkeypatch.setattr(
        start.subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw))
    )

    assert start.ensure_venv() is True

    assert len(calls) == 2
    venv_cmd, _ = calls[0]
    assert venv_cmd[1:3] == ["-m", "venv"]
    pip_cmd, pip_kw = calls[1]
    assert pip_cmd[0] == str(venv_python)
    assert pip_cmd[-4:] == ["install", "-e", ".[server]", "-q"]
    assert pip_kw["cwd"] == str(start.ROOT)
    assert pip_kw["check"] is True
