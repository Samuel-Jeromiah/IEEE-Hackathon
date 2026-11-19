# Status log

The newest entry goes on top. Each entry records: date and time, which machine, the milestone, what works, what's broken, and the next step.

---

## 2026-11-19 ~12:30, Windows laptop: Phase 0, push #1

**Done:**
- Repo scaffold, `CLAUDE.md`, `docs/PLAN.md` and this log.
- `pyproject.toml` and `uv.lock`: 106 packages, Python 3.12, resolved for macOS and Windows.
- Model profiles in `serving/models.yaml`: `mac16`, `mac8` and `cpu`.
- Download scripts:
  - `serving/download_models.py` (has a `--check` option).
  - `serving/fetch_corpus.py`.
  - `serving/get_llama_cpp.py`.
- Setup scripts: `scripts/setup.sh` auto-detects the Mac profile; `scripts/setup.ps1` is for Windows.

**Checked:**
- Every model file named in `models.yaml` exists on Hugging Face, and none needs a login.
- 5 of the 7 guide PDFs download.
- The two FEMA PDFs must be saved from a browser; the script prints the links.

**Not yet:** the contract, the stub API, the launcher and the schema tests. These come in push #2.

**Next, on the Mac (Phase 1 in `docs/PLAN.md`):**
1. Run `brew install llama.cpp uv`.
2. Clone the repo.
3. Run `./scripts/setup.sh` (about 8 GB of downloads).
4. Save the two FEMA PDFs from a browser.
5. After push #2: run `uv run pytest`, then start Claude Code and continue from M1.
