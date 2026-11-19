"""Download the public guide documents behind "Ask the guide" into domain/storm/corpus/.

Usage:
    uv run python serving/fetch_corpus.py [--force]

These are public government documents. They are fetched at setup time rather than
committed; domain/storm/corpus/manifest.json records each file's source and checksum.
fema.gov refuses scripted downloads, so the two FEMA guides are marked browser_only:
open their URLs in a browser and save them under the listed file names.
Uses only the standard library so it runs before `uv sync` if needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = ROOT / "domain" / "storm" / "corpus"
USER_AGENT = "Mozilla/5.0 (compatible; stormlog-corpus-fetcher/0.1)"

DOCS = [
    {
        "file": "fema_pda_guide_2025-07.pdf",
        "title": "FEMA Preliminary Damage Assessment Guide (July 2025)",
        "url": "https://www.fema.gov/sites/default/files/documents/fema_rd_pda-guide_07012025.pdf",
        "browser_only": True,
    },
    {
        "file": "fema_pda_pocket_guide_2025-07.pdf",
        "title": "FEMA Preliminary Damage Assessment Pocket Guide (July 2025)",
        "url": "https://www.fema.gov/sites/default/files/documents/fema_rd_pda-pocket-guide_07012025.pdf",
        "browser_only": True,
    },
    {
        "file": "mema_piida_sop.pdf",
        "title": "MEMA Public Infrastructure Initial Damage Assessment: SOP",
        "url": "https://www.maine.gov/mema/sites/maine.gov.mema/files/inline-files/PIIDA_SOP.pdf",
    },
    {
        "file": "mema_piida_form.pdf",
        "title": "MEMA Public Infrastructure Initial Damage Assessment form",
        "url": "https://maine.gov/mema/sites/maine.gov.mema/files/inline-files/"
        "Public%20Infrastructure%20Initial%20Damage%20Assessment.pdf",
    },
    {
        "file": "mema_form_instructions.pdf",
        "title": "MEMA initial damage assessment form instructions",
        "url": "https://maine.gov/mema/sites/maine.gov.mema/files/inline-files/Form%20Instructions.pdf",
    },
    {
        "file": "mema_ihida.pdf",
        "title": "MEMA Individuals & Households Initial Damage Assessment",
        "url": "https://www.maine.gov/mema/sites/maine.gov.mema/files/inline-files/IHIDA_9-14-23.pdf",
    },
    {
        "file": "south_portland_eop_annex_r.pdf",
        "title": "South Portland Emergency Operations Plan, Annex R: Reconstitution and Recovery (2023)",
        "url": "https://www.southportland.org/DocumentCenter/View/2963/"
        "2023-EOP-Annex-R-Reconstitution-and--Recovery-PDF",
    },
]


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return resp.read()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="re-download files that already exist")
    args = ap.parse_args()

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = CORPUS_DIR / "manifest.json"
    manifest = {}
    if manifest_path.exists():
        manifest = {d["file"]: d for d in json.loads(manifest_path.read_text(encoding="utf-8"))}

    failed, manual = [], []
    for doc in DOCS:
        target = CORPUS_DIR / doc["file"]
        if target.exists() and not (args.force and not doc.get("browser_only")):
            print(f"  have  {doc['file']}")
            continue
        if doc.get("browser_only"):
            manual.append(doc)
            continue
        try:
            data = download(doc["url"])
            if not data.startswith(b"%PDF"):
                raise ValueError("response is not a PDF")
            target.write_bytes(data)
            manifest[doc["file"]] = {
                **doc,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            print(f"  got   {doc['file']} ({len(data) // 1024} KB)")
        except Exception as exc:
            failed.append(doc["file"])
            print(f"  FAIL  {doc['file']}: {exc}", file=sys.stderr)

    manifest_path.write_text(json.dumps(list(manifest.values()), indent=2), encoding="utf-8")
    folder = CORPUS_DIR.relative_to(ROOT).as_posix()
    have = len(DOCS) - len(failed) - len(manual)
    print(f"{have}/{len(DOCS)} guide documents in {folder}/")
    if manual:
        print("\nACTION NEEDED: fema.gov blocks scripted downloads. Open each link in a browser")
        print(f"and save the PDF into {folder}/ under the name shown:")
        for doc in manual:
            print(f"  {doc['file']}\n    {doc['url']}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
