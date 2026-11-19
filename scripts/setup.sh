#!/usr/bin/env bash
# One-time setup on macOS or Linux: Python environment, guide PDFs, models.
# Usage: ./scripts/setup.sh [auto|mac16|mac8|cpu]      (default: auto-detect from this machine)
set -euo pipefail
cd "$(dirname "$0")/.."

PROFILE="${1:-auto}"
OS="$(uname -s)"
ARCH="$(uname -m)"

echo "== Hardware"
if [[ "$OS" == "Darwin" ]]; then
  system_profiler SPHardwareDataType 2>/dev/null | grep -E "Chip|Processor Name|Memory:" || true
  MEM_GB=$(( $(sysctl -n hw.memsize) / 1073741824 ))
else
  MEM_GB=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1048576 ))
fi
df -h . | tail -1 | awk '{print "  Free disk: " $4}'

if [[ "$PROFILE" == "auto" ]]; then
  if [[ "$OS" == "Darwin" && "$ARCH" == "arm64" ]]; then
    if (( MEM_GB >= 15 )); then PROFILE=mac16; else PROFILE=mac8; fi
  else
    PROFILE=cpu
    echo "  NOTE: not an Apple Silicon Mac, so using the slow 'cpu' profile (see docs/PLAN.md, Risks)."
  fi
fi
echo "== Profile: $PROFILE  (RAM ${MEM_GB} GB, $OS $ARCH)"

command -v uv >/dev/null 2>&1 || { echo "uv not found. macOS: brew install uv"; exit 1; }
NEED_LLAMA_ZIP=0
if ! command -v llama-server >/dev/null 2>&1; then
  if [[ "$OS" == "Darwin" ]]; then
    echo "  WARNING: llama-server not on PATH. Run: brew install llama.cpp"
  else
    NEED_LLAMA_ZIP=1
  fi
fi

echo "== Python environment (uv sync)"
uv sync

if [[ "$NEED_LLAMA_ZIP" == "1" ]]; then
  echo "== llama.cpp (prebuilt release into bin/llama)"
  uv run python serving/get_llama_cpp.py
fi

echo "== Guide documents"
uv run python serving/fetch_corpus.py || echo "  WARNING: some guide PDFs failed to download (see above)."

echo "== Models for profile $PROFILE (the long part: about 8 GB)"
uv run python serving/download_models.py --profile "$PROFILE"

echo "== Done. Next: uv run pytest, then follow docs/PLAN.md (Phase 1, step 4)."
