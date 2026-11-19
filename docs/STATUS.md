# Status log

The newest entry goes on top. Each entry records: date and time, which machine, the milestone, what works, what's broken, and the next step.

---

## 2026-11-19 ~14:45, Windows laptop: the organizers' practice pack (read this first)

**What it is:** the organizers' official practice pack, 100 items:

| Input | Items | Format |
|---|---|---|
| Image | 25 | JPG, long side up to 1280 px |
| Audio | 20 | WAV, 16 kHz mono, up to 60 s; speech or everyday sounds |
| Text | 20 | Questions over 5 documents, each as both TXT and PDF, up to 3 pages |
| Video | 15 | MP4 with **no audio track**, up to 30 s and 720p |
| Code | 20 | HumanEval-style function prompts |

The files:
- `items.json` lists `{id, modality, file, question}`.
- `answers.json` has the reference answers. Document items marked `answerable: false` expect "not in the document". Speech items include a `transcript`, and code items an `entry_point`.
- Each code item's unit tests are in `code/tests/<id>_test.py`.

**Where it is:**
- On Windows: unpacked into `eval/datasets/practice_pack/`, which git ignores. `archive.zip` is ignored too.
- **The Mac must get it by AirDrop or USB, never through GitHub.**

**How judging works (from the pack's README):**
1. Before the demos we receive a new set of items in the same format.
2. Judges pick items at random, and may add surprise items.
3. The app answers live on our laptop **with Wi-Fi off**.

**What this changes for the Mac session:**
1. **The general tools are the priority** (M1–M2). They are what judges test live; storm mode comes after.
2. **Video must work from the picture alone.** The judges' clips have no sound.
3. **Audio must handle both speech and everyday sounds.** Run Whisper and CLAP, then answer from whichever fits the question. Keep the sound labels a broad vocabulary, not tuned to ESC-50.
4. **Documents are TXT or PDF, and several questions share one document.** Unanswerable questions must get "not in the document".
5. **Code items:** `file` is `null`, and the full function prompt is in `question`. Show the code. Running the item's unit tests in the sandbox is a strong demo moment.
6. **Evaluation: write `eval/run_practice.py`.**
   - It runs all 100 items through `/api/analyze` and scores each modality:
     - Image: reference match.
     - Speech: WER against the transcript.
     - Sounds: label match.
     - Documents: EM/F1 plus abstention.
     - Video: reference match.
     - Code: unit tests passing.
   - This becomes the main evaluation. The public-benchmark runs in `docs/PLAN.md` become optional, but keep the storm-specific checks.
   - Keep per-item outputs local; only aggregate scores go in the README.
7. **Judge mode (recommended):** a screen that reads a pack's `items.json` and runs an item with one click. Judges pick items at random, so this makes the live test fast. It needs a small contract addition (list and serve the local pack), so agree on it first.
8. **Wi-Fi off:** the judges' test must run fully at http://127.0.0.1:8000 in the Mac's own browser. Show the phone flow separately.

**Shared one-pager for the team:** the "StormLog: team one-pager" doc (Claude Docs), shared by the repo owner.

---

## 2026-11-19 ~14:15, Windows laptop: Mac specs and git history

**Mac confirmed:** Apple M1, 16 GB of RAM, 1 TB of storage. It uses the `mac16` profile, which `./scripts/setup.sh` picks automatically.

**Git history was rewritten once, at the team's request,** to remove the `Co-Authored-By: Claude` trailers. Only the commit messages changed; the code is byte-for-byte identical, so the commit IDs are new.
- **If you cloned before ~14:15 and have no local work:** run `git fetch origin && git reset --hard origin/main`.
- **If you have local commits:** run `git pull --rebase`. Git will skip the old copies of these commits.
- **From now on:** no AI co-author trailers on commits (see `CLAUDE.md`, Git).

---

## 2026-11-19 ~13:45, Windows laptop: the web app (`frontend/`)

**Done:**
- **The whole web app:** plain ES modules with no build step and nothing from a CDN.
  - Fonts are bundled under the SIL Open Font License: Atkinson Hyperlegible for body text, Barlow Condensed for headings, JetBrains Mono for timestamps and code.
  - There is a light "paper" theme, plus a dark theme that follows the system setting.
- **Home:** a model-status pill. On laptops, a QR code that phones can scan.
- **Report damage** (the phone flow): photo, voice note, video and location, with live progress. When it finishes it opens the new site card.
- **Site card:**
  - Hazard banners, with a "Call 911" link for life-safety hazards.
  - The FEMA damage-level tag, with the reason.
  - Facts with evidence chips.
  - An evidence dialog. It plays this device's own copy of the file from the exact timestamp.
  - Approve and edit buttons (sent as a PATCH).
- **Town report:**
  - Totals and a county threshold meter showing the formula and its source.
  - Filters, and two panes on a laptop.
  - CSV export, a printable report, and Analyze (a script written by the code model).
- **Ask the guide:** an answer with the exact quote and page, or "Not in the guides".
- **The five general tools.** Results show the answer plus:
  - **Image:** what's in the photo, and any text found.
  - **Audio:** a transcript and sounds that jump the player to that moment.
  - **Document:** the quote with its page, or "Not in the document".
  - **Video:** frames that jump to that moment.
  - **Code:** a tests badge and the output.
- **Works over plain HTTP:** none of `crypto.randomUUID`, the clipboard API, `getUserMedia` or service workers is used. File inputs use `capture`.

**Checked:**
- `node --check` passes on all 14 JavaScript files.
- 22 tests pass, including the new `tests/test_frontend_assets.py`. It checks that:
  - Every referenced asset is served.
  - JavaScript is served with a JavaScript content type.
  - There are no external URLs.
  - The fonts are licensed.
- Headless Edge emulating a 390px touch phone, in light and dark themes, on 18 screens: no horizontal overflow, no JavaScript errors, and the full report flow works.

**Changed outside `frontend/` (small; please note):**
- `backend/main.py`: the stub's `delta` events now carry their own spacing (`" is"`), like model tokens.
- `contracts/schema.md`: now states that clients join `delta` chunks exactly as received. **Mac session: stream real tokens raw. The web app joins them as-is.**
- New file `tests/test_frontend_assets.py`. No existing tests were changed.

**What real mode needs to support (Mac session):**
- **Events buffering.** The web app opens `GET /api/events/{request_id}` before it posts. Real mode must buffer each request's events until the client connects, or replay them from the start.
- **Evidence media.** Set `media_url` on photo and video-frame evidence, served from `/api/media/...`. Voice playback uses the file still on the reporting phone.
- **`task_hint`.** It is sent as the tool's input type: `image`, `audio`, `document`, `video` or `code`. A photo sent from the Document tool should go down the document path: OCR, then an answer with a verified quote.

**Next:**
1. The Mac session wires real workers behind the same endpoints.
2. Test on a phone over local Wi-Fi: run `serving.launch` without `--host`, then scan the QR code on the home screen.

---

## 2026-11-19 ~13:00, Windows laptop: Phase 0, push #2

**Done:**
- **Contract v1:** `backend/schemas.py` (Pydantic), `contracts/schema.md`, and 15 example responses in `contracts/examples/`, generated by `scripts/export_examples.py`.
- **Stub API** (`backend/main.py`, with data from `backend/stub_data.py`):
  - Every endpoint works with no models. Start it with `uv run python -m serving.launch --stub`, then open http://127.0.0.1:8000.
  - Stub hook: a document or guide question containing "pizza" returns the "not found" example.
- **Launcher** (`serving/launch.py`):
  1. Starts llama-server for the profile, with `--jinja` and thinking off, bound to 127.0.0.1.
  2. Waits for `/health`.
  3. Starts the API on 0.0.0.0:8000 with the offline environment variables set.
  4. Prints the LAN URL and a QR code.

  `--dry-run` prints the server commands. Logs go to `logs/`.
- **Tests:** 19 passing. They cover the contract, every stub endpoint, and the launcher starting in stub mode. Lint is clean, with the rule set pinned in `pyproject.toml`.
- `frontend/index.html` is a placeholder. The Windows session replaces it.

**Not yet:** real workers. In real mode, `/api/health` checks the actual model servers, but every other endpoint still returns stub data.

**Next, for the Mac session (M1 in `docs/PLAN.md`):**
1. `uv run pytest`.
2. Smoke tests in `scripts/smoke/`, one model per process.
3. `backend/clients/llm.py`, an OpenAI-compatible client for llama-server. It sends images as data URLs, sets `chat_template_kwargs` to turn thinking off, uses `json_schema` for structured output, and supports streaming.
4. `backend/normalize.py` and `backend/router.py`.
5. `backend/jobs.py`, with the progress events.
6. Workers: image, then document plus `domain/docqa.py`, then audio (faster-whisper plus CLAP at 48 kHz). As each worker lands, swap its stub endpoint for the real one in real mode.

**Optional, for the Windows session:** the web app in `frontend/`, built against the stub API.

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
