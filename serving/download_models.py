"""Download the model files for a profile into models/.

Usage:
    uv run python serving/download_models.py --profile mac16
    uv run python serving/download_models.py --profile mac16 --with-optional
    uv run python serving/download_models.py --profile cpu --only vlm,asr
    uv run python serving/download_models.py --profile mac16 --check   # verify names, download nothing

Each model in serving/models.yaml lists candidate repos in order; the first that
downloads wins. Results go to models/resolved.json (which files to load) and
models/profile.txt (the chosen profile), both read by serving/launch.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
from huggingface_hub import file_exists, hf_hub_download, repo_exists, snapshot_download  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "models"
CONFIG_PATH = ROOT / "serving" / "models.yaml"
RESOLVED_PATH = MODELS_DIR / "resolved.json"
ROLES = ("vlm", "coder", "asr", "sound")


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def rel(path: str | Path) -> str:
    return Path(path).resolve().relative_to(ROOT).as_posix()


def check_model(key: str, spec: dict) -> bool:
    """Report whether at least one candidate exists on Hugging Face, without downloading."""
    ok_any = False
    for cand in spec["candidates"]:
        repo = cand["repo"]
        if spec["kind"] == "gguf":
            names = [cand[r] for r in ("file", "mmproj") if cand.get(r)]
            ok = all(file_exists(repo, name) for name in names)
        else:
            ok = repo_exists(repo)
        ok_any = ok_any or ok
        print(f"  [{key}] {'ok     ' if ok else 'MISSING'} {repo}")
    return ok_any


def fetch_model(key: str, spec: dict) -> dict:
    dest = MODELS_DIR / key
    errors = []
    for cand in spec["candidates"]:
        repo = cand["repo"]
        try:
            if spec["kind"] == "gguf":
                out = {"repo": repo, "kind": "gguf"}
                for role in ("file", "mmproj"):
                    name = cand.get(role)
                    if not name:
                        continue
                    print(f"[{key}] {repo} :: {name}", flush=True)
                    path = hf_hub_download(repo_id=repo, filename=name, local_dir=dest)
                    out["model" if role == "file" else "mmproj"] = rel(path)
                return out
            print(f"[{key}] {repo} (all files)", flush=True)
            path = snapshot_download(repo_id=repo, local_dir=dest, allow_patterns=cand.get("allow"))
            return {"repo": repo, "kind": "snapshot", "path": rel(path)}
        except Exception as exc:  # fall through to the next candidate
            errors.append(f"{repo}: {exc}")
            print(f"[{key}] ! {repo} failed: {exc}", flush=True)
    raise RuntimeError(f"every candidate failed for {key}: {errors}")


def main() -> int:
    cfg = load_config()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", required=True, choices=sorted(cfg["profiles"]))
    ap.add_argument("--with-optional", action="store_true", help="also fetch the profile's optional models")
    ap.add_argument("--only", default="", help="comma-separated roles to fetch: vlm,coder,asr,sound")
    ap.add_argument("--check", action="store_true", help="only verify that the files exist on Hugging Face")
    args = ap.parse_args()

    profile = cfg["profiles"][args.profile]
    only = {r.strip() for r in args.only.split(",") if r.strip()}
    keys = [profile[r] for r in ROLES if r in profile and (not only or r in only)]
    if args.with_optional:
        keys += [k for k in profile.get("optional", []) if k not in keys]

    if args.check:
        missing = [k for k in keys if not check_model(k, cfg["models"][k])]
        print("All models available." if not missing else f"No usable candidate for: {missing}")
        return 1 if missing else 0

    MODELS_DIR.mkdir(exist_ok=True)
    resolved = json.loads(RESOLVED_PATH.read_text(encoding="utf-8")) if RESOLVED_PATH.exists() else {}
    failed = []
    for key in keys:
        try:
            resolved[key] = fetch_model(key, cfg["models"][key])
            RESOLVED_PATH.write_text(json.dumps(resolved, indent=2), encoding="utf-8")
        except Exception as exc:
            failed.append(key)
            print(f"[{key}] FAILED: {exc}", file=sys.stderr, flush=True)

    if not failed:
        (MODELS_DIR / "profile.txt").write_text(args.profile + "\n", encoding="utf-8")
    print(f"\nProfile {args.profile}: models/resolved.json")
    for key in keys:
        status = "FAILED" if key in failed else f"ok  {resolved[key]['repo']}"
        print(f"  {key:16s} {status}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
