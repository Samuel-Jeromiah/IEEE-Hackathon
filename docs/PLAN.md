# StormLog build plan: offline storm-damage reports, plus the five-input assistant

This file becomes `docs/PLAN.md` in the repo. It is written to stand alone, so a new Claude Code session on the Mac can follow it.

## Context

**The event.** This is the IEEE AI Hackathon 2026 "Multimodal LLM Challenge" at the Roux Institute, Nov 18–20. The task is one interface that handles five kinds of input:
- **Image:** describe a photo and answer questions about it.
- **Audio:** transcribe speech, answer questions about it, and identify sounds.
- **Text:** answer questions about a document, and say so when the answer isn't there.
- **Code:** write working code from a prompt.
- **Video:** describe a short clip and answer questions about it.

The models must be open-weight and run locally. AI coding tools may write the code, but they must not be the system's brain at runtime. "Use any hardware you bring, and list it on your slides."

**Rubric:**

| Weight | Criterion |
|---|---|
| 30 | Multimodal checklist plus our own test results |
| 25 | Real-world usability: a live demo, with a bonus for working on web and mobile |
| 20 | Architecture: which models, why, their limits, and whether it runs well locally |
| 15 | Impact |
| 10 | Judges' questions |

The code is due **Friday, Nov 20**. The exact time is unconfirmed; this plan assumes noon.

**Where we are (Thursday, about 12:15).** No code has been written. About 24 hours remain, including sleep. Decisions so far:
- **Domain:** storm-damage reporting for small-town Maine emergency managers.
- **No interviews with real users are possible.** Impact evidence will come from public records, the published reporting process, and our own measurements.
- **Demo and model machine:** a teammate's MacBook with an Apple M1, 16 GB of RAM and 1 TB of storage. It runs the `mac16` profile.
- **Development:** Claude Code will run on the Mac. This Windows laptop does the repo setup first (Phase 0), and can optionally keep building the frontend afterwards.
- **Repo:** https://github.com/Samuel-Jeromiah/IEEE-Hackathon. It is public, with a `main` branch and one existing commit, so we clone it rather than overwrite it. We ask before every push. Lane A confirms with the organizers that a repo under a personal account counts as "the team's public IEEE GitHub repo".
- **Northeastern HPC:** not used at runtime, and dropped from the critical path to save time.

**The Windows laptop** is a Dell Inspiron 15 with an i7-11390H, Intel Iris Xe graphics (no NVIDIA) and 15.7 GB of RAM, of which only 280 MB was free at 11:41. That's fine for writing code and running unit tests, but not for running the models. Its `python` is 3.14, so uv pins 3.12. The `ffmpeg` on its PATH is ImageMagick's old 4.2 build, so media decoding uses PyAV on every OS.

## Two-machine workflow

### Phase 0, on this Windows laptop (Claude Code, about 45 minutes after approval)

**Push #1 (about 20 minutes), so the Mac can start downloading early:**
1. Run `git clone https://github.com/Samuel-Jeromiah/IEEE-Hackathon` into `Downloads/IEEE/IEEE-Hackathon/` and keep the existing commit.
2. Add these files:
   - `CLAUDE.md`, described below.
   - `docs/PLAN.md` (this file).
   - `docs/STATUS.md`: a running log that every session updates. It records which milestone we're on, what works, what's broken, and what's next.
   - `.gitignore` and `pyproject.toml` (uv, Python 3.12).
   - `serving/models.yaml`, with the profiles below.
   - `serving/download_models.py`: downloads the profile's models with `hf_hub_download` into `local_dir`.
   - `serving/fetch_corpus.py`: downloads the guide PDFs.
   - `scripts/setup.sh` for the Mac and `scripts/setup.ps1` for Windows. Each runs `uv sync`, then the model download for a profile, then the corpus fetch.
   - A short README stub.
3. Commit, ask you, then push.

**Push #2 (about 30 minutes):**
- `contracts/schema.md` and example JSON responses.
- The Pydantic models in `backend/schemas.py`.
- A stub API that serves the examples without needing any models.
- A skeleton `serving/launch.py`. It is OS-aware: it finds `llama-server` on PATH (Homebrew) or in `bin/`, passes arguments as lists, and sets the offline environment variables (`HF_HUB_OFFLINE` and others).
- Schema tests.
- Commit, ask you, then push.

**What `CLAUDE.md` contains:**
- A summary of the project and what the judges score.
- Pointers to `docs/PLAN.md` and `docs/STATUS.md`.
- The commands: `uv sync`, `uv run pytest`, `uv run python -m serving.launch --profile <p>`, and the evaluation commands.
- Conventions:
  - Python 3.12 via uv, and `pathlib` for cross-platform paths.
  - No network calls at runtime, and nothing loaded from a CDN.
  - Model calls with thinking mode off, temperature 0 for JSON, and `max_tokens` caps.
  - Every answer carries evidence, or says it can't tell.
- Folder ownership.
- Git rules: small commits, `git pull --rebase` before every push, ask before pushing, never force-push.
- Update `docs/STATUS.md` at every milestone.

### Phase 1, on the Mac (a person sets it up, in parallel with Phase 0)

1. **Check the hardware.** Run `system_profiler SPHardwareDataType | grep -E "Chip|Memory"` and `df -h ~`, then pick a profile:

   | Mac | Profile |
   |---|---|
   | Apple Silicon, 16 GB or more | `mac16` |
   | Apple Silicon, 8 GB | `mac8` |
   | Intel Mac | Stay on the Windows `cpu` profile and free up RAM there |

2. **Install the tools.** Install Xcode Command Line Tools (`xcode-select --install`) and Homebrew, then `brew install llama.cpp uv`. Homebrew's llama.cpp uses Metal, and installing it that way avoids Gatekeeper blocking a downloaded binary. Install Claude Code and sign in.
3. **After push #1:**
   1. Clone the repo.
   2. Run `./scripts/setup.sh mac16` to start the roughly 8 GB of model downloads.
   3. Run `caffeinate -dims &` and keep the Mac plugged in.
   4. Close other apps.
4. **Start the build.** Run `claude` in the repo and say: "Read CLAUDE.md and docs/PLAN.md, then continue from M1. Log progress in docs/STATUS.md."
5. **Firewall.** When macOS asks, allow incoming connections for Python. `ipconfig getifaddr en0` shows the Mac's LAN address.

### Folder ownership after the handoff

- **Mac session:** `backend/`, `domain/`, `serving/`, `scripts/`, `eval/`, `tests/`.
- **Windows session (optional):** `frontend/`, `demo/` and `slides/` drafts. It builds against the stub API, which needs no models.
- Both sessions pull with rebase before every push, and only edit each other's folders through `contracts/` changes that both agree on.

## The problem, from public evidence

- **Maine's process.** After a storm:
  1. Each town carries out an Initial Damage Assessment and sends it to its county emergency management agency.
  2. The county submits it to MEMA, the state agency.
  3. MEMA compiles the reports to decide whether to ask for federal help.

  MEMA publishes two forms for this: one for public infrastructure (PIIDA) and one for individuals and households (IHIDA).
- **The deadlines are tight.** For the January 2024 storms, MEMA first said it would not extend the assessment timeframes. It later accepted reports through January 31, 2024.
- **The scale is large.** The December 17–21, 2023 storm cut power to about 443,475 properties. The federal major disaster declaration was approved January 31, 2024. The coastal storms of January 10 and 13, 2024 were separate events.
- **Federal money depends on the totals.** FEMA compares damage against dollar thresholds per resident:

  | Threshold per resident | Incidents from Oct 1, 2025 | Incidents from Oct 1, 2026 |
  |---|---|---|
  | County | $4.86 | $5.03 |
  | Statewide | about $1.94 | about $2.01 |

  The statewide figures, and the effective date of the $2.01 figure, still need confirming on fema.gov.
- **Damage levels are standardized.** FEMA's damage-assessment guide (July 2025) rates homes as Affected, Minor, Major or Destroyed, using things an inspector can see, such as how deep the water got in living space.
- **The gap.** Volunteers collect photos, voice notes and videos on their phones, often while power and cell service are down. Someone then types all of it into forms by hand. Existing digital survey forms collect the fields, but they don't read the raw media.

## The solution: StormLog (working name)

A laptop at the town office runs everything offline. Volunteers' phones connect to it over local Wi-Fi with no internet.

1. **Report damage (phone).** The volunteer sends a photo, a voice note, an optional short video, and a location. The location comes from:
   - GPS in the photo, if the phone keeps it (browsers often strip it).
   - The place named in the voice note.
   - A typed address.
   - A house number or road sign read from the photo.
2. **StormLog drafts a site entry.**
   - The model extracts what it can see and hear. **Fixed rules, not the model, then set the FEMA damage level** for homes, or the FEMA Public Assistance category A–G for public infrastructure.
   - Every field links to its evidence: the photo, a quote checked against the transcript with its timestamp, or a video frame.
   - A field with no evidence is marked "needs review", never guessed.
3. **Safety comes first.** Hazards jump to the top of the entry with "call 911" guidance. Sounds that trigger an alert are a beeping smoke or CO alarm, or rushing water, in the audio or video. So do phrases in a voice note like "wires down", "smell gas" or "someone trapped".
4. **Town report (laptop).** It lists all sites, with totals by damage level and category.
   - The director can edit and approve entries, and enter costs.
   - The "Analyze" button uses the code model to check totals against the county threshold.
   - It exports a CSV in the order of MEMA's form fields, plus a printable report.
5. **Ask the guide.** Questions about FEMA's damage guide, MEMA's procedures or the town's emergency plan get an answer with page and quote, or "not in the guide".

**Why local is essential:**
- Storms take out power and internet.
- The reports contain residents' addresses.
- There's no per-request cost for small towns.

**What's unique:**
- It turns raw field media into FEMA-style entries offline, with evidence attached.
- It checks its own claims.
- It uses sound to catch life-safety hazards.

## Two layers in one app

| Layer | What it does | Rubric |
|---|---|---|
| General assistant (five tiles; the default) | Photo: describe and answer questions. Audio: transcript, questions and sounds. Document: questions, with "not in the document" when the answer isn't there. Code from a prompt. Video: describe and answer questions | Checklist (30) |
| StormLog mode | The workflow above, built on the same workers | Impact (15), usability (25) |

**Every answer carries evidence that code checks, or it says it can't tell.** This applies to both layers:
- **Document:** the quoted passage must be found in the source, otherwise the answer is "not in the document".
- **Audio:** answers cite transcript timestamps, checked against the word timings. Sound identification tries several wordings of each label.
- **Code:** the code runs in a sandbox against tests the model writes itself, with one repair attempt.
- **Video:** frames, transcript and sounds are combined, and answers cite frame times that actually exist.
- **Image:** the model reports what it can see in a fixed structure, and says "can't tell" for details it can't see. A second, zoomed-in pass is a stretch goal.
- The evaluation measures each of these as the raw model versus our system.

## Architecture

```
Phone / laptop browser (static web app, vanilla JS, nothing loaded from a CDN)
        │  HTTP over local Wi-Fi, no internet
FastAPI orchestrator (backend/)
  normalize → deterministic router → per-model queue → workers
  workers: image · audio (faster-whisper + CLAP) · document (PyMuPDF/python-docx + BM25)
           · video (PyAV frames + audio) · code (code model + sandbox) · text
  evidence verifier: rapidfuzz checks each quote, then maps it to a page, timestamps or a frame
  storm domain: observations → rules → FEMA level / PA category · hazards · sites (SQLite)
                · report export · questions over the guides
Model servers on 127.0.0.1 (llama-server, Metal on the Mac):
  :8081  vision-language model + mmproj
  :8082  code model
In the orchestrator process: faster-whisper · CLAP htsat-unfused
```

There is no PII redaction step: this domain has no SSNs, and all data stays on the machine.

### Guardrails (`backend/guard/`, `backend/sandbox/`)

All rules live in one file, `backend/guard/policy.yaml`. Each request passes five checkpoints:

1. **Input gate** (`gate.py`): size and length limits, control characters stripped, and a default question per kind when the question is empty.
2. **Safety check** (`safety.py`): checks the question only, never the file. Narrow decline patterns (keyloggers, ransomware, credential stealers, weapons, child sexual content) are always on. A self-harm pattern returns the 988 support message. An optional guard model on `servers.guard` adds a second layer, and any failure lets the request through.
3. **Prompt contract** (`prompts.py`): document excerpts, transcripts and pasted text are wrapped in random-nonce delimiters and labeled as data. Lookalike tags inside the data are neutralized.
4. **Output check** (`outputs.py`): removes thinking text, maps "I cannot determine…" variants to one standard abstain sentence per kind, converts number words to digits for "how many" questions, and caps sentence counts. It sets `CaseFile.policy`.
5. **Code sandbox** (`sandbox/runner.py`): an AST allowlist (stdlib, plus pandas, csv and io for table tasks), then `python -I` in a temp folder with a stripped environment and a 10 s timeout that kills the process group. Output is capped at 20 KB, and on macOS `sandbox-exec` denies network access and writes outside the temp folder.

`eval/run_guardrails.py` runs the red-team set in `eval/redteam/items.json`.

## Model profiles (`serving/models.yaml`)

| | `mac16` (the demo Mac: M1, 16 GB) | `mac8` | `cpu` (Windows fallback) |
|---|---|---|---|
| Vision-language model (images, OCR, frames, text Q&A, extraction) | Qwen3.5-4B Q4_K_M with mmproj-F16. Try Qwen3.5-9B Q4_K_M if the smoke tests show memory and speed are OK | Qwen3.5-2B, or 4B | Qwen3.5-4B |
| Code model | Qwen2.5-Coder-3B-Instruct Q4_K_M, always loaded. Use 7B if the 9B vision model isn't used and memory allows | Coder-3B, started on demand | Coder-3B, started on demand |
| Speech-to-text | faster-whisper `small`, int8 (try `large-v3-turbo`) | `small` | `small` |
| Sound identification | CLAP `laion/clap-htsat-unfused` on CPU | same | same |
| llama.cpp | Homebrew build with Metal | Homebrew build with Metal | Windows CPU zip |
| Image / video limits | 1024 px (1280 px for OCR) · up to 12 frames at 512 px · clips up to 90 s | 768 px · up to 8 frames at 448 px · up to 60 s | same as `mac8` |
| Context window | 16k | 8k | 8k |
| Timeouts: image / doc / audio / video / code | 30 / 45 / 60 / 120 / 60 s | 60 / 90 / 90 / 180 / 90 s | same as `mac8` |

**Fallbacks:**
- If Qwen3.5 has problems in llama.cpp: Qwen3-VL-4B, the handout's pick.
- If the runtime has problems: Ollama, through the same OpenAI-compatible client.

**Settings for every call:**
- Thinking mode off.
- Temperature 0 for extraction and JSON, up to 0.2 otherwise, with a repeat penalty.
- A hard `max_tokens` cap.
- Structured outputs constrained to a JSON schema.

A timeout returns a partial "degraded" result, not an error.

## Storm domain design (`domain/storm/`)

- **`taxonomy.yaml`** holds:
  - **Home damage levels:** FEMA's Affected, Minor, Major and Destroyed, plus "needs inspection".
  - **Public infrastructure categories:** FEMA's A–G: debris, emergency measures, roads and bridges, water control, buildings, utilities, parks and other.
  - **Hazards:** an alarm sounding, downed lines, gas smell, fire, a trapped person, flooding, a road that can't be passed, a medical need.
  - **Incident types.**
- **`levels.py`** maps observations to a damage level. It uses the criteria in FEMA's July 2025 guide: where the water line is and how deep it reached, plus roof, structure and foundation damage. Each rule cites the guide page. If a key observation is unknown, the level is "needs inspection". Lane C checks every rule against the guide.
- **`extract.py`** produces:
  - From a photo: JSON observations covering the scene, water line, roof, structure, debris, downed lines, washout, whether the road can be passed, any visible text, a description, and what the model can't see.
  - From a voice note: fields for location, damage, hazards, people and access. Each field has a quote, which is verified and mapped to timestamps.
  - From a video: frame observations, the transcript and the sounds.
  - Location from photo GPS and time data (HEIC or JPEG), the voice note, typed text, or an address read from the photo.
- **`hazards.py`** combines three sources into alerts, each with its time or place:
  - CLAP sound labels: smoke or CO alarm beeping, generator, rushing water, chainsaw, siren, wind, rain. Each label has its own threshold, tuned on a separate calibration set.
  - **A tone-pattern detector for alarm beeps.** Smoke alarms use a three-beep pattern (T3), CO alarms a four-beep pattern (T4); it's a short numpy routine.
  - A keyword list run over the transcript.
- **`store.py`** uses SQLite from the standard library. It stores incidents, sites, evidence and edits, with each entry marked draft, needs review or approved. Photos and thumbnails stay in the incident folder as evidence.
- **`report.py`:**
  - Totals by level and category.
  - A CSV in the field order of MEMA's PIIDA and IHIDA forms, read from the published instructions.
  - A printable HTML report.
  - `thresholds.yaml`: the per-resident thresholds by fiscal year, and county populations from the 2020 Census (to verify).
- **The guide collection** covers FEMA's damage-assessment guide and pocket guide (July 2025), MEMA's PIIDA procedures, form instructions and IHIDA, and South Portland's emergency-plan recovery annex. It is indexed by page at startup for keyword search (BM25).
- **Costs** are entered or imported by people. The model never estimates them.

## API (contract v1, frozen in Phase 0)

| Endpoint | Purpose |
|---|---|
| `POST /api/analyze` | General mode. Takes `files[]`, `text`, `prompt`, `task_hint` and `request_id`; returns a CaseFile |
| `GET /api/events/{request_id}` | Live updates: progress, answer text as it streams, and a done signal |
| `POST /api/incidents`, `GET /api/incidents/{id}` | Create or list incidents; get the full report |
| `POST /api/incidents/{id}/sites` | Storm report. Takes photo, voice, video and location; returns a Site with evidence and hazards |
| `PATCH /api/sites/{id}` | Edit or approve fields, and enter costs |
| `GET /api/incidents/{id}/export.csv`, `GET /api/incidents/{id}/report.html` | MEMA-style CSV export, and the printable report |
| `POST /api/guide/ask` | A question over the guides. Returns answer, quote, page and `found` |
| `POST /api/incidents/{id}/analyze` | A prompt becomes a script from the code model, run on the incident's CSV. Returns code, output and test results |
| `GET /api/health`, `GET /api/info` | Model status; the LAN URL and a QR code |

**Data shapes:**
- **CaseFile:** `request_id`, `mode`, `status` (ok, degraded or failed), `answer`, `artifacts[]`, `timings_ms`, `degraded[]`, `models{}`.
- **ArtifactResult**, one per uploaded file:
  - `artifact_id`, `kind` (image, audio, document, video, code or text), `filename`, `converted_from`.
  - `answer` and `description`.
  - `extracted_text`.
  - `transcript[{t_start, t_end, text}]` and `sounds[{t_start, t_end, label, score}]`.
  - `frames[{idx, t, caption, thumb_b64}]`.
  - `doc_qa{found, quote, page, match_score, retrieval_score}`.
  - `code{source, stdout, stderr, tests_passed, attempts}`.
  - `model`, `latency_ms`, `status`, `error`.
- **Site:** `id`; `location{text, lat, lon, source}`; `kind` (home or public); a damage `level` or a `category`; `observations[]`; `hazards[]`; `fields{value, evidence_ids}`; `status`.
- **Evidence:** `artifact_id`, `kind`, `quote`, a `locator` (start and end time, frame index and time, or page), `verified` and `match_score`.

**File handling:** uploads go to temp folders, which are deleted after processing. Transcripts and frames are cached by file hash, so a follow-up question on the same file skips re-extraction.

## Repo layout

```
CLAUDE.md   docs/{PLAN.md, STATUS.md}   contracts/
backend/    main.py schemas.py router.py normalize.py jobs.py clients/ workers/ sandbox/
domain/     verify.py docqa.py
            storm/{taxonomy.yaml, levels.py, extract.py, hazards.py, store.py, report.py, thresholds.yaml, corpus/}
frontend/   index.html app.js styles.css icons/
serving/    models.yaml launch.py get_llama_cpp.py download_models.py fetch_corpus.py
scripts/    setup.sh setup.ps1 smoke/ prewarm.py check_offline.py
eval/       fetch_datasets.py common.py run_*.py run_all.py make_report.py results/
demo_data/  photos/ voice/ video/ csv/ licenses.md     demo/  slides/  tests/  README.md
gitignored: .venv/ models/ bin/ data/ logs/ eval/datasets/ and the corpus PDFs (fetched by script)
```

## Timeline (Thursday 12:30 to Friday about 10:30)

### Phase 0 and Mac setup (12:30–13:15), in parallel

As described above: two pushes from Windows. Meanwhile the Mac checks its hardware, installs the tools, clones the repo and starts the downloads.

### M1 — Image, document and audio, on the Mac (13:15–16:00)

**Plumbing:**
- Smoke tests, each model in its own process.
- The model client and the model manager.
- `normalize.py`: HEIC, EXIF rotation, GPS and time, resizing.
- `router.py`: routes on file signature bytes and a PyAV stream probe, plus `task_hint` from the tile.
- `jobs.py`: queues, timeouts that return degraded results, live progress events, and a JSONL log.

**Workers:**
- The image worker.
- The document worker with `docqa.py`: BM25 search, extract-then-answer, quote verification, and "not in the document" when that fails.
- The audio worker:
  - Decodes at 16 kHz for speech and 48 kHz for CLAP.
  - Gets word timestamps, with voice-activity detection.
  - Runs CLAP over windows.
  - Answers questions citing timestamps.
- The text worker.

**Windows, optional:** the frontend shell against the stub API. It has a home screen with Report damage, Town report, Ask the guide and General tools, plus the five general tiles and their result views.

**Done when** image, document (including "not in the document") and audio all work in the browser with real models.

### M2 — Video, code and phone (16:00–19:00), commit `v0.1`

**Video worker:**
- Up to 12 frames, with rotation applied.
- The audio track goes through the audio path.
- One combined call that cites frame times.

**Code worker:**
- An AST allowlist gate checks the generated code before it runs.
- The sandbox runs `python -I` in a temp folder, with a 10 s timeout and the whole process tree killed on timeout.
- Output is capped at 20 KB, and one repair attempt is allowed.

**App, network and evaluation:**
- Answer text streams in, with progress shown.
- LAN access and a QR code for the phone; test it on a real phone.
- Write the evaluation scripts and fetch the datasets while still online.

**Done when** all five general tiles work from a phone over the LAN.

### M3 — StormLog (19:30–23:00), commit `v0.5`

**Backend (Mac):** the `domain/storm/` modules described above.

**UI (Windows, or the Mac if Windows is idle):**
- **Report damage** on the phone, step by step.
- **The site card.** Evidence chips open the photo zoomed, play the audio from the timestamp, or show the frame. The safety banner sits at the top.
- **Town report:**
  - A table and totals.
  - A threshold meter.
  - Approve and edit.
  - Export and print.
- **Ask the guide** and **Analyze**.

**Done when:**
- The three demo sites get the correct levels or categories, with verified evidence.
- The alarm in the basement video raises an alert.
- Analyze runs, and the export opens.

**At 23:00,** start the overnight evaluation on the Mac, plugged in and under `caffeinate`.

### M4 — Results and polish (Friday 06:30–09:30)

- Review the evaluation CSVs and fix the biggest failures. No tuning on the test splits.
- Generate the report and the README tables, then finish the README.
- Write the demo script, and test with no internet connection.
- Rehearse twice. The team records the backup video.

### M5 — Freeze (09:30–10:30)

- Clone fresh onto the Mac, run setup and launch.
- Final commit, tag `v1.0`, and push with your OK.
- If the deadline turns out to be after noon, use the extra time on the stretch items.

## Data

| Use | Source | License and notes |
|---|---|---|
| Demo photos | FEMA's media library (storm damage), plus team photos | Federal works are mostly public domain; check each item |
| Voice notes | Teammates record scripted field reports on their phones (M4A or OGG), some with wind or generator noise behind them | Ours |
| Video | Public-domain flood footage from FEMA, NOAA or USGS, 30 s or less. One clip includes a real smoke-alarm test beep recorded by a teammate | Check each item |
| Guide collection | FEMA damage-assessment guide and pocket guide (July 2025); MEMA's PIIDA procedures, form instructions and IHIDA; South Portland's emergency-plan recovery annex | Public documents, fetched by script |
| Town CSV | A synthetic damage log (about 30 sites, with categories and costs), plus county populations | Synthetic and labeled as such |
| Image evaluation | CrisisMMD v2.0, "damage" set, on Hugging Face (QCRI): little or no damage, mild, severe | CC BY-NC-SA 4.0, research use only; never committed. If access is gated, Lane C accepts the terms |

## Evaluation (overnight on the Mac)

| Area | Dataset | n | Metric | Raw model vs. ours |
|---|---|---|---|---|
| Image | TextVQA validation | 30 | VQA accuracy | — |
| Damage photos | CrisisMMD damage test set (15 per class) | 45 | Accuracy and confusion matrix (FEMA level mapped to 3 classes) | A plain "rate the damage" prompt vs. observations plus rules |
| Documents | SQuAD 2.0 dev | 50 answerable + 50 not | EM/F1, and wrong answers on unanswerable questions | A plain prompt vs. extract-and-verify |
| Guide questions | FEMA/MEMA questions written by Lane C | 40 (25 answerable, 15 not) | Accuracy, abstention, correct page | Plain vs. verified |
| Speech | LibriSpeech test-clean | 30 | WER | — |
| Sounds | ESC-50 | 100 (2 per class) | Top-1 and top-3 accuracy | One label wording vs. several |
| Hazard sounds | Synthetic alarm beeps plus ESC-50 storm sounds | 30 | Detection rate and false alarms | — |
| Voice-note fields | 20 scripted notes | 20 | Field accuracy, and % of quotes verified | — |
| Code | HumanEval | 40 | pass@1 | Single attempt vs. with repair (the benchmark's tests are never shown to the model) |
| Code (storm) | Total and threshold prompts on the town CSV | 10 | Exact numbers | — |
| Video | 10 clips with written Q&A | 10 | Graded by a person | Frames only vs. combined |
| Time study | 5 mock sites, done by hand vs. with StormLog | 5 | Minutes taken, fields completed | — |

**How it runs:**
- The harness sends requests to the real API, with a `--limit` option, and appends to a CSV so runs can resume.
- Results go to `eval/results`, and `make_report` turns them into the README tables.
- Calibration data is kept apart from the reported numbers.
- Median latencies come from the JSONL log on the Mac.
- If the Mac can't stay on overnight, run with `--limit` halved on Friday at 06:30.

## Team, working in parallel with the build

**A (the Mac):**
- Phase 1 setup.
- Keep the Mac plugged in, run `caffeinate` overnight, and close other apps.
- Approve installs and downloads, and watch the smoke tests.
- Confirm the deadline time with the organizers, and confirm that the personal-account repo is acceptable.
- Do the fresh-clone test on Friday.

**B (data and demo):**
- Record 20 scripted voice notes and 3 demo notes on phones.
- Record a smoke-alarm test beep in a short video.
- Pull about 20 FEMA photos and 3 clips, noting the sources.
- Test the phone-to-Mac link over a hotspot or router with no internet.
- Make the slides, rehearse, and record the backup video.

**C (domain and evaluation):**
- Read the damage-level pages of FEMA's guide and the MEMA form fields, then check `levels.yaml` and the export columns.
- Write the 40 guide questions (with pages) and the 10 video questions.
- Build the synthetic town CSV.
- Confirm the per-resident thresholds and county populations.
- Run the time study.
- Write the README's impact and limits sections, and prepare answers for the judges.

## Demo (about 4 minutes)

1. **0:00 — The story.** "In December 2023, 443,475 Maine properties lost power. A small town's volunteer emergency director has days to send damage reports to the county, with no power or internet." Start the first site report now.
2. **0:30 — No internet.** The Mac is on battery, on local Wi-Fi only.
3. **0:45 — A flooded home.** The phone sends a photo and a voice note. The site card comes back:
   - "Major", based on the water line.
   - The volunteer's quote at 0:04–0:09.
   - The location.
4. **1:30 — A basement video.** The frames are described, and an alarm beep is detected at 0:07, raising a red safety banner.
5. **2:00 — The town report.**
   - Show the totals.
   - Analyze runs a script from the code model that compares the totals to the county threshold, and the tests pass.
   - Export the CSV.
6. **2:30 — Ask the guide.** One answerable question gets a page and quote. One that isn't covered gets "not in the guide".
7. **3:00 — General tools.** Show the five-input checklist page, run right before the talk, plus one tile live.
8. **3:30 — Close.** The results slide (raw vs. ours), the limits, and the next step: a pilot with a county emergency management agency.

## Slides (8)

1. The problem and the user: Maine storms, the town → county → MEMA reporting chain, the thresholds.
2. A demo screenshot.
3. The architecture.
4. The models, why we chose them, and the hardware (list the MacBook).
5. The five-input checklist with our results.
6. Evidence first: raw model vs. ours.
7. Offline operation and privacy.
8. Limits and next steps.

## Cut order if behind

Cut in this order:
1. The 9B and 7B model upgrades.
2. HPC.
3. The zoomed second pass for images.
4. Bounding boxes on photos.
5. HTTPS, plus in-browser recording and GPS (these need HTTPS).
6. The printable report (keep CSV only).
7. Per-frame captions.
8. Follow-up questions.

**Never cut:**
- The five general tiles.
- Document "not in the document" with the quote check.
- Whisper plus CLAP.
- Video as frames plus audio.
- Code with the sandbox.
- Storm site entries with evidence and safety alerts.
- Town totals and the CSV export.
- Phone access over the LAN.
- The evaluation tables and the README.

## Risks

| Risk | Plan |
|---|---|
| The Mac is Intel, or has 8 GB | Use the `mac8` profile, or go back to the Windows `cpu` profile after freeing RAM there |
| Claude Code can't run on the Mac | This Windows session writes code and pushes; a person on the Mac pulls and runs the models, and reports results in `docs/STATUS.md` |
| Merge conflicts between the two sessions | Folder ownership, pull with rebase before every push, contract changes only by agreement |
| About 8 GB of downloads on venue Wi-Fi | Push #1 goes out first so downloads start by about 13:00. Fallback: a phone hotspot |
| Qwen3.5 has problems in llama.cpp | Switch to Qwen3-VL-4B. Ollama is the fallback runtime |
| Wrong damage levels | Rules taken from FEMA's guide, "needs inspection" when details can't be seen, and a person approves every entry |
| The phone can't reach the Mac | Test a hotspot or router with no internet on Thursday. Fallback: a laptop-only demo |
| Thin impact evidence | Public records, the time study, and the measured raw-vs-ours results. We say plainly that it hasn't been validated with an emergency management agency yet |
| The deadline is earlier than noon | Confirm it now. The `v0.5` commit is already demoable |

## Verification (on the Mac)

1. **Unit tests.** `uv run pytest` covers the schemas, the router, the sandbox gate, mapping verified quotes to locations, the damage-level rules, the hazard thresholds, "not in the document" (using a fake model), and the store and export.
2. **Smoke tests.** `uv run python scripts/smoke/run_all.py`.
3. **End-to-end.** Run `uv run python -m serving.launch --profile mac16`. On the phone and the Mac, run the five general tiles, the three demo sites, a guide question, Analyze and the export.
4. **No internet.** Use a router with no uplink. The full demo passes, and `scripts/check_offline.py` passes.
5. **Evaluation.** `uv run python eval/run_all.py` produces `eval/report.md`, and its numbers go into the README.
6. **Friday.** Clone fresh, run setup and launch.

## Sources (checked Thursday)

- FEMA damage-assessment guide (July 2025): https://www.fema.gov/sites/default/files/documents/fema_rd_pda-guide_07012025.pdf
- FEMA pocket guide (July 2025): https://www.fema.gov/sites/default/files/documents/fema_rd_pda-pocket-guide_07012025.pdf
- County threshold, fiscal 2026 ($4.86): https://wem.wi.gov/wp-content/uploads/CPI-FRN-countywide-FY-2026.pdf
- Fiscal 2027 threshold notices: https://public-inspection.federalregister.gov/2026-22691.pdf and https://public-inspection.federalregister.gov/2026-22694.pdf
- Governor's disaster request for the December 2023 storm: https://www.maine.gov/governor/mills/sites/maine.gov.governor.mills/files/inline-files/(1)%20State%20of%20Maine%20Declaration%20Request%20Cover%20Letter_Severe%20Storm%20and%20Flood%20Dec%202023.pdf
- Disaster declaration approval: https://www.maine.gov/governor/mills/news/radio_address/federal-disaster-assistance-december-storm-and-flooding-2024-02-02
- MEMA PIIDA procedures: https://www.maine.gov/mema/sites/maine.gov.mema/files/inline-files/PIIDA_SOP.pdf
- MEMA PIIDA form: https://maine.gov/mema/sites/maine.gov.mema/files/inline-files/Public%20Infrastructure%20Initial%20Damage%20Assessment.pdf
- MEMA form instructions: https://maine.gov/mema/sites/maine.gov.mema/files/inline-files/Form%20Instructions.pdf
- MEMA IHIDA form: https://www.maine.gov/mema/sites/maine.gov.mema/files/inline-files/IHIDA_9-14-23.pdf
- MEMA Public Assistance page: https://www.maine.gov/mema/grants/pa
- Island Institute FAQ on the January 2024 storms: https://www.islandinstitute.org/2024/01/19/january-2024-storms-frequently-asked-questions/
- Cumberland County damage assessments: https://www.cumberlandcounty.org/departments/emergency_management_agency/damage_assessments.php
- South Portland emergency-plan recovery annex: https://www.southportland.org/DocumentCenter/View/2963/2023-EOP-Annex-R-Reconstitution-and--Recovery-PDF
- CrisisMMD on Hugging Face: https://huggingface.co/datasets/QCRI/CrisisMMD
- MEDIC, a larger alternative (11 GB): https://crisisnlp.qcri.org/medic/
