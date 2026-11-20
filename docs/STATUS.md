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

---

## 2026-11-19 ~18:40, Mac (Honey): Phase 1 machine setup

**Done:**
- Homebrew installed; PATH in `~/.zprofile`; `brew install llama.cpp uv gh`.
- GitHub: `gh` logged in as `honeyN1` with WRITE on the repo; git identity set.
- Clone at `~/code/IEEE-Hackathon` (not Desktop/Documents).
- `caffeinate -dims ./scripts/setup.sh` completed for profile `mac16` (vlm, coder, whisper, clap).
- Both FEMA PDFs in `domain/storm/corpus/` with the expected names (gitignored).
- `uv run pytest`: 22 passed.
- Stub launch OK (pill: Stub data); `--profile mac16` OK (pill: Local models ready). Health: vlm/coder up.

**Not yet:**
- `archive.zip` / `eval/datasets/practice_pack/` — zip not found on this machine.

**Next:** unpack the practice pack when available; start M1 workers on the Mac session.

---

## 2026-11-19 ~18:55, Mac (Honey): M1 workers wired

**Done:**
- Plumbing: `backend/clients/llm.py`, `normalize.py`, `router.py`, `jobs.py` (SSE event buffer + replay), `manager.py` (lazy Whisper + CLAP).
- Domain: `domain/verify.py`, `domain/docqa.py` (BM25 → answer → rapidfuzz ≥ 90 or abstain).
- Workers: image, document (incl. photo-via-document OCR), audio (16 kHz Whisper + 48 kHz CLAP), text.
- Real mode: `POST /api/analyze` and `GET /api/events/{id}` use workers; stub mode unchanged.
- Smoke scripts under `scripts/smoke/` (vlm, whisper, clap).
- Tests: `tests/test_m1_plumbing.py`; full suite **27 passed**.
- Live checks on mac16: image ("The image is red."), document found + not-found, audio (asr/sound load to **up**). Health: all four model slots up after first audio call.

**Not yet (M2+):** video worker, code sandbox, storm site extraction, guide corpus Q&A, practice pack unzip.

**Next:** M2 video + code; or tune CLAP thresholds; unpack `archive.zip` when available.

---

## 2026-11-19 ~19:10, Mac (Honey): M2 video worker

**Done:**
- `backend/workers/video.py`: PyAV frame sampling (≤12 @ 512px, ≤90s), rotation metadata, thumbnails; Whisper + CLAP on the audio track; one VLM call citing frame times.
- Wired into `jobs.py` (replaces M2 stub).
- Test: `tests/test_video_frames.py`. Full suite green.
- Live smoke: 2s red→blue mp4 → “Yes, the color changes from red to blue at 0:01.” with frame thumbs.

**Still stubbed:** code sandbox, storm site extraction, guide corpus Q&A.

---

## 2026-11-19 ~19:25, Mac (Honey): Unified Chat replaces Tools

**Done:**
- Frontend: `#/chat` multimodal composer (multi-attach + prompt), thread UI, SSE progress, `renderCaseFile` replies.
- Infers `task_hint` from attachments/prompt; mixed files omit hint so the router sniffs each.
- Nav “Tools” → “Chat”; home slab points to Chat; `#/tools` and `#/tools/:kind` redirect.
- CSS for thread/composer; `chat` icon. Tests: `tests/test_chat_routing.py`. Suite green.

**Still stubbed:** code sandbox worker; storm site extraction; guide corpus Q&A.

---

## 2026-11-19 ~19:30, Mac (Honey): ChatGPT-inspired Chat UI

**Done:**
- Restyled `#/chat` toward a ChatGPT-like layout: centered “How can I help?” empty state, suggestion cards, avatars + bubbles, sticky rounded composer with + / send, full-bleed chat mode (`body.chat-mode`).
- Fixed a missing paren in `showEmpty` that broke the JS bundle.
- Verified in browser; chat routing tests still pass.

---

## 2026-11-19 ~19:35, Mac (Honey): Global ChatGPT palette + blue accent

**Done:**
- Rethemed `:root` / dark tokens to ChatGPT-like cool grays/whites; `--signal` is now blue (`#2563eb` / `#3b82f6`).
- Top bar light, active tabs blue, brand mark + favicon blue; primary buttons/slabs/chat bubbles/send use blue.
- FEMA placard colors left semantic. Applied across all pages via shared tokens.

---

## 2026-11-19 ~19:45, Mac (Honey): Manrope + plain tool UI

**Done:**
- Bundled Manrope (400–700) offline; body/display use Manrope. Dropped heavy uppercase/display bolding.
- Flat light gray background (`#f3f4f6`); removed hero/chat gradients and AI-style empty state/suggestion cards.
- Trimmed home/chat/report/guide/town copy; quieter inputs and buttons. Backend unchanged.

Correction: the ChatGPT-style chat (with the "How can I help?" empty state, suggestion cards and bubbles) was restored after this entry, at the user's request. It keeps Manrope and the flat gray background.

---

## 2026-11-19 ~20:30, Mac (Honey): Guardrails + real code worker

**Done:**
- `backend/guard/`. All rules are in `policy.yaml`, and the checkpoints are:
  - `gate.py`: limits and default questions.
  - `safety.py`: narrow decline patterns, a 988 support message, and an optional guard model that lets requests through if it fails.
  - `prompts.py`: nonce-delimited untrusted text with lookalike tags neutralized. Used by the document, audio, video and text workers.
  - `outputs.py`: a standard abstain sentence, thinking text stripped, digits for "how many" answers, and a sentence cap.
- `backend/sandbox/runner.py`: AST allowlist, `python -I` in a temp folder, a timeout that kills the process group, a 20 KB output cap, and macOS `sandbox-exec` with no network and no writes outside the temp folder. The sandbox was verified to block both.
- The code worker is real (`backend/workers/code.py`):
  - The coder writes code plus its own asserts, which run in the sandbox, with one repair attempt.
  - It replies in fenced blocks, not JSON, because the 3B model cut off JSON strings that contained quotes.
  - It adds missing imports from the allowlist, and falls back to the VLM if the coder isn't running.
- Contract: `CaseFile.policy = {action: answered|abstained|declined, reason, message}`, plus the `casefile_declined` example. In stub mode, "keylogger" returns declined. `contracts/schema.md` has a new Guardrails section.
- Frontend: declined requests show a neutral "Can't help with that" notice. Abstained answers outside the document tool show a "Can't tell" block.
- Tests: `tests/test_guardrails.py` and `tests/test_sandbox.py`. The whole suite passes (81), and so does ruff.
- `eval/run_guardrails.py` with `eval/redteam/items.json` passes **15/15** on mac16:
  - harmful requests 5/5 declined
  - everyday and storm questions 5/5 answered
  - document abstain 2/2
  - prompt injection 2/2
  - size limit 1/1
- Code spot check on coder-3b: 3 of 5 passed. In the 2 failures the code was correct but the model's own expected test values were wrong, and the UI says the tests didn't pass.

**Not done:** the guard model isn't downloaded or launched. `servers.guard` isn't in `models.yaml`, so only the pattern layer is active. The practice pack is still missing, so accuracy isn't measured yet.

---

## 2026-11-19 ~20:25, Mac (Honey): Guide Q&A and Document to JSON

**Done:**
- Guide is real:
  - `domain/storm/guide.py` runs BM25 over all 222 corpus pages and verifies quotes.
  - `backend/workers/guide.py` asks the VLM for an answer plus a verbatim quote. If the quote can't be verified, the answer is "not covered".
  - The "county deadline" example was swapped for an answerable question.
- Removed the timing, model and request-ID line under chat replies.
- Chat has a fifth card, "Document to JSON". It fills in the prompt and opens the file picker.
  - `domain/extract.py` and the document worker's extraction mode turn the model's (path, value, quote) fields into nested JSON. Every value's quote is checked.
  - The UI shows the JSON with a Copy button and an evidence list marking each field verified or needs review.
- Contract: `ArtifactResult.extraction` (`Extraction`, `ExtractedField`), plus the `casefile_document_extract` example.
- Tests: `test_guide.py` and `test_extract.py`. The suite passes (87).
- Live: a sample lease gave 14 of 14 fields verified. A sample damage report gave 3 site objects, with the 2 missing costs marked needs review.

Update (~20:30): removed Document to JSON (the Chat card, `domain/extract.py`, the document worker's extraction mode, `ArtifactResult.extraction` and its stub example) at the user's request. Chat is back to four cards.
