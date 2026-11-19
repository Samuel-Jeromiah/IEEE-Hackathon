"""Start StormLog: llama-server processes for the profile, then the API and web app.

Usage (from the repo root):
    uv run python -m serving.launch --stub                # API + web app with example data, no models
    uv run python -m serving.launch --profile mac16       # model servers + API
    uv run python -m serving.launch                       # profile recorded by setup (models/profile.txt)
    uv run python -m serving.launch --profile mac16 --dry-run   # print the commands, start nothing

Model servers bind to 127.0.0.1 only; the API binds to 0.0.0.0 so phones on the same Wi-Fi can reach it.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import load_models_config, repo_path, resolved_models, selected_profile_name  # noqa: E402

LOG_DIR = ROOT / "logs"
OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
}


def find_llama_server() -> str | None:
    exe = shutil.which("llama-server")
    if exe:
        return exe
    name = "llama-server.exe" if os.name == "nt" else "llama-server"
    found = next((ROOT / "bin").rglob(name), None) if (ROOT / "bin").exists() else None
    return str(found) if found else None


def llama_command(exe: str, role: str, model_key: str, profile: dict, cfg: dict) -> list[str]:
    entry = resolved_models().get(model_key)
    model = str(repo_path(entry["model"])) if entry else f"<models/{model_key}/*.gguf not downloaded>"
    srv = cfg["servers"][role]
    cmd = [exe, "-m", model, "--host", srv["host"], "--port", str(srv["port"]),
           "-c", str(profile["limits"]["ctx"]), "-np", "1", "--jinja",
           "--chat-template-kwargs", json.dumps({"enable_thinking": False})]
    if entry and entry.get("mmproj"):
        cmd += ["--mmproj", str(repo_path(entry["mmproj"]))]
    llama = profile.get("llama", {})
    if llama.get("gpu_layers") is not None:
        cmd += ["-ngl", str(llama["gpu_layers"])]
    if llama.get("threads"):
        cmd += ["-t", str(llama["threads"])]
    return cmd


def start_process(cmd: list[str], log_name: str) -> subprocess.Popen:
    LOG_DIR.mkdir(exist_ok=True)
    log = open(LOG_DIR / log_name, "ab")
    kwargs: dict = {"stdout": log, "stderr": subprocess.STDOUT}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def wait_healthy(port: int, proc: subprocess.Popen, label: str, timeout_s: int = 240) -> bool:
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if proc.poll() is not None:
            print(f"  {label} exited early (code {proc.returncode}); see logs/llama-{label}.log")
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass  # still loading (503) or not listening yet
        time.sleep(1.5)
    print(f"  {label} not healthy after {timeout_s}s; see logs/llama-{label}.log")
    return False


def stop_all(procs: list[subprocess.Popen]) -> None:
    for p in procs:
        if p.poll() is None:
            p.terminate()
    for p in procs:
        try:
            p.wait(timeout=8)
        except subprocess.TimeoutExpired:
            p.kill()


def print_urls(port: int) -> None:
    from backend.main import lan_ip

    lan = f"http://{lan_ip()}:{port}"
    print(f"\n  StormLog is starting:\n    this computer: http://127.0.0.1:{port}\n    phone (same Wi-Fi): {lan}\n")
    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(lan)
        qr.print_ascii(invert=True)
    except Exception:
        pass  # some consoles can't draw the QR characters; the URL above is enough


def main() -> int:
    cfg = load_models_config()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stub", action="store_true", help="example data only; no model servers")
    ap.add_argument("--profile", choices=sorted(cfg["profiles"]), help="default: models/profile.txt")
    ap.add_argument("--port", type=int, default=cfg["app"]["port"])
    ap.add_argument("--host", default=cfg["app"]["host"], help="use 127.0.0.1 to stay off the LAN")
    ap.add_argument("--dry-run", action="store_true", help="print the server commands and exit")
    args = ap.parse_args()

    os.environ.update(OFFLINE_ENV)
    os.environ["STORMLOG_PORT"] = str(args.port)
    procs: list[subprocess.Popen] = []

    if args.stub:
        os.environ["STORMLOG_MODE"] = "stub"
    else:
        name = selected_profile_name(args.profile)
        if not name:
            sys.exit("No profile given and none recorded. Run scripts/setup.sh (or pass --profile).")
        profile = cfg["profiles"][name]
        os.environ.update({"STORMLOG_MODE": "real", "STORMLOG_PROFILE": name})
        exe = find_llama_server() or "llama-server"
        roles = ["vlm"] + (["coder"] if profile.get("coder_resident") else [])
        commands = {role: llama_command(exe, role, profile[role], profile, cfg) for role in roles}
        if args.dry_run:
            for role, cmd in commands.items():
                print(f"[{role}] " + " ".join(cmd))
            return 0
        if not find_llama_server():
            sys.exit("llama-server not found. macOS: brew install llama.cpp; Windows: scripts/setup.ps1")
        missing = [profile[r] for r in roles if profile[r] not in resolved_models()]
        if missing:
            sys.exit(f"Models not downloaded: {missing}. Run: uv run python serving/download_models.py "
                     f"--profile {name}")
        print(f"Profile {name}: starting model servers (first load can take a minute)...")
        for role, cmd in commands.items():
            procs.append(start_process(cmd, f"llama-{role}.log"))
        for role, proc in zip(commands, procs, strict=True):
            ok = wait_healthy(cfg["servers"][role]["port"], proc, role)
            print(f"  {role}: {'ready' if ok else 'NOT READY'}")

    try:
        import uvicorn

        print_urls(args.port)
        uvicorn.run("backend.main:create_app", factory=True, host=args.host, port=args.port,
                    log_level="info")
    finally:
        stop_all(procs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
