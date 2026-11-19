"""Write contracts/examples/*.json from backend/stub_data.py.

Usage: uv run python -m scripts.export_examples
Run it after any change to backend/schemas.py or backend/stub_data.py; a test checks the files match.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import stub_data  # noqa: E402


def main() -> int:
    out = ROOT / "contracts" / "examples"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    examples = stub_data.examples()
    for name, obj in examples.items():
        (out / f"{name}.json").write_text(obj.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(examples)} examples to {out.relative_to(ROOT).as_posix()}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
