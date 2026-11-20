"""Run model-written Python safely: AST allowlist, then an isolated, time-limited subprocess.

Layers: (1) ast_gate rejects imports outside the profile's allowlist and dangerous builtins;
(2) `python -I` in an empty temp dir with a stripped environment; (3) a wall-clock timeout that
kills the whole process group; (4) capped output; (5) on macOS, sandbox-exec denies network
and file writes outside the temp dir.
"""
from __future__ import annotations

import ast
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from backend.guard.policy import load_policy

_MAC_PROFILE = """(version 1)
(allow default)
(deny network*)
(deny file-write*)
(allow file-write* (subpath "{tmp}") (literal "/dev/null"))
"""


@dataclass
class RunResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    blocked: str | None = None  # why ast_gate refused the code


def allowed_modules(profile: str) -> set[str]:
    sb = load_policy().sandbox
    mods = set(sb.pure_modules)
    if profile == "data":
        mods |= set(sb.data_modules)
    return mods


def ast_gate(code: str, profile: str = "pure") -> str | None:
    """Return None if the code may run, else a short reason."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"syntax error: {exc.msg} (line {exc.lineno})"
    allowed = allowed_modules(profile)
    blocked = set(load_policy().sandbox.blocked_names)
    blocked_attrs = set(load_policy().sandbox.blocked_attrs)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in allowed:
                    return f"import not allowed: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level or root not in allowed:
                return f"import not allowed: {node.module}"
        elif isinstance(node, ast.Name) and node.id in blocked:
            return f"name not allowed: {node.id}"
        elif isinstance(node, ast.Attribute) and node.attr in blocked_attrs:
            return f"attribute not allowed: {node.attr}"
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr not in {
            "__init__", "__name__", "__class__", "__repr__", "__str__", "__eq__", "__lt__",
            "__len__", "__iter__", "__next__", "__hash__", "__dict__",
        }:
            return f"attribute not allowed: {node.attr}"
    return None


def _clip(s: str, limit: int) -> str:
    b = s.encode("utf-8", errors="replace")
    return s if len(b) <= limit else b[:limit].decode("utf-8", errors="ignore") + "\n…(output cut)"


def run_python(code: str, test: str = "", *, profile: str = "pure",
               timeout_s: float | None = None) -> RunResult:
    sb = load_policy().sandbox
    timeout = timeout_s or sb.timeout_s
    source = code.rstrip() + "\n\n" + (test or "").strip() + "\n"
    reason = ast_gate(source, profile)
    if reason and reason.startswith("syntax error"):
        return RunResult(False, stderr=reason)
    if reason:
        return RunResult(False, blocked=reason, stderr=reason)

    tmp = Path(tempfile.mkdtemp(prefix="stormlog_sbx_"))
    try:
        script = tmp / "main.py"
        script.write_text(source, encoding="utf-8")
        cmd = [sys.executable, "-I", "-B", str(script)]
        if mac_sandbox_available():
            sb_profile = _MAC_PROFILE.format(tmp=tmp.resolve())
            cmd = ["sandbox-exec", "-p", sb_profile, *cmd]
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONHASHSEED": "0", "HOME": str(tmp),
               "TMPDIR": str(tmp)}
        if sys.platform == "win32":
            env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
        kwargs: dict = {"cwd": tmp, "env": env, "stdin": subprocess.DEVNULL,
                        "stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **kwargs)
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill(proc)
            out, err = proc.communicate()
            return RunResult(False, _clip(out or "", sb.output_bytes),
                             _clip((err or "") + f"\nTimed out after {timeout:g}s.", sb.output_bytes),
                             timed_out=True)
        return RunResult(proc.returncode == 0, _clip(out or "", sb.output_bytes),
                         _clip(err or "", sb.output_bytes))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@lru_cache(maxsize=1)
def mac_sandbox_available() -> bool:
    """sandbox-exec can't nest inside another sandbox, so probe it once."""
    if sys.platform != "darwin" or not shutil.which("sandbox-exec"):
        return False
    try:
        r = subprocess.run(["sandbox-exec", "-p", "(version 1)(allow default)", "/usr/bin/true"],
                           capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def _kill(proc: subprocess.Popen) -> None:
    try:
        if sys.platform == "win32":
            proc.kill()
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()
