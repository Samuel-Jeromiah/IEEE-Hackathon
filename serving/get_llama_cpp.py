"""Fetch a prebuilt llama.cpp release into bin/llama/ (Windows and Linux).

On macOS use Homebrew instead, which gives a Metal build on PATH:
    brew install llama.cpp

Usage:
    uv run python serving/get_llama_cpp.py                    # CPU build for this OS
    uv run python serving/get_llama_cpp.py --variant vulkan
    uv run python serving/get_llama_cpp.py --tag b12546 --dry-run
Uses only the standard library.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = ROOT / "bin" / "llama"
API = "https://api.github.com/repos/ggml-org/llama.cpp/releases"
HEADERS = {"User-Agent": "stormlog-setup/0.1", "Accept": "application/vnd.github+json"}


def asset_stem(variant: str) -> str:
    """Asset name fragment for this OS; archives may be .zip or .tar.gz."""
    system, machine = platform.system(), platform.machine().lower()
    arm = machine in ("arm64", "aarch64")
    table = {
        ("Windows", "cpu"): "-bin-win-cpu-arm64." if arm else "-bin-win-cpu-x64.",
        ("Windows", "vulkan"): "-bin-win-vulkan-x64.",
        ("Linux", "cpu"): "-bin-ubuntu-x64.",
        ("Linux", "vulkan"): "-bin-ubuntu-vulkan-x64.",
        ("Darwin", "cpu"): "-bin-macos-arm64." if arm else "-bin-macos-x64.",
    }
    try:
        return table[(system, variant)]
    except KeyError:
        sys.exit(f"No prebuilt mapping for {system}/{variant}. On macOS run: brew install llama.cpp")


def get_json(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=60) as resp:
        return json.load(resp)


def pick_asset(releases: list[dict], stem: str) -> tuple[dict, dict] | None:
    # Numbered builds (bNNNN) are published as pre-releases, and the newest one is
    # sometimes still uploading, so take the newest release that has our archive.
    for release in releases:
        for asset in release.get("assets", []):
            name = asset["name"]
            if stem in name and name.endswith((".zip", ".tar.gz")):
                return release, asset
    return None


def extract(archive: Path, dest: Path) -> None:
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
    else:
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(dest, filter="data")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", default="cpu", choices=["cpu", "vulkan"])
    ap.add_argument("--tag", default="", help="release tag such as b12546 (default: newest build)")
    ap.add_argument("--dry-run", action="store_true", help="show the chosen asset without downloading")
    args = ap.parse_args()

    releases = [get_json(f"{API}/tags/{args.tag}")] if args.tag else get_json(f"{API}?per_page=20")
    stem = asset_stem(args.variant)
    found = pick_asset(releases, stem)
    if not found:
        sys.exit(f"No asset containing '{stem}' in the {len(releases)} newest llama.cpp releases.")
    release, asset = found
    print(f"llama.cpp {release['tag_name']}: {asset['name']} ({asset['size'] // 1_048_576} MB)")
    if args.dry_run:
        return 0

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    archive = BIN_DIR / asset["name"]
    req = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": HEADERS["User-Agent"]})
    with urllib.request.urlopen(req, timeout=600) as resp, open(archive, "wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)
    extract(archive, BIN_DIR)
    archive.unlink()

    if os.name != "nt":  # zipfile drops the executable bit
        for p in BIN_DIR.rglob("*"):
            if p.is_file():
                p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    exe = "llama-server.exe" if os.name == "nt" else "llama-server"
    found = next(BIN_DIR.rglob(exe), None)
    (BIN_DIR / "VERSION").write_text(release["tag_name"] + "\n", encoding="utf-8")
    if not found:
        sys.exit(f"Extracted, but {exe} was not found under {BIN_DIR}")
    print(f"llama-server: {found.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
