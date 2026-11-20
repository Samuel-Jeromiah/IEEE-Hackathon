# StormLog: instructions for Claude Code

## What this is
A hackathon project for the IEEE AI Hackathon 2026 "Multimodal LLM Challenge". **The code is due Friday, Nov 20.**

It is one local app with two layers:
- **General assistant:**
  - Image: describe a photo and answer questions about it.
  - Audio: transcribe, answer questions and identify sounds.
  - Document: answer questions, and say "not in the document" when the answer isn't there.
  - Code from a prompt.
  - Video: describe a clip and answer questions about it.

  Everything runs on local open-weight models.
- **StormLog mode:** turns volunteers' photos, voice notes and videos into an offline storm-damage report for small-town Maine emergency managers. It uses FEMA damage levels and MEMA's initial-damage-assessment fields, and every field is linked to its evidence.

**Judging:** checklist plus our own test results 30%, usability (live demo, web and mobile) 25%, architecture 20%, impact 15%, judges' questions 10%.

## Read first
- `docs/PLAN.md`: the full plan. It covers the architecture, the API contract, milestones M1–M5, evaluation and the demo.
- `docs/STATUS.md`: where things stand. **Add an entry at the end of every milestone or session.**

## Commands
- `./scripts/setup.sh` (macOS or Linux; auto-picks a profile) or `scripts/setup.ps1 -ModelProfile cpu` (Windows): installs the Python environment, the guide PDFs and the models.
- `uv sync`: Python 3.12 environment from `uv.lock`.
- `uv run pytest`: unit tests. These must pass without any models.
- `uv run python serving/download_models.py --profile mac16 --check`: checks that model names exist on Hugging Face, without downloading.
- `uv run python -m serving.launch --stub`: the API and web app with example responses, no models.
- `uv run python -m serving.launch --profile mac16`: starts llama-server, then the API on port 8000.
  - Add `--dry-run` to print the commands without starting anything.
  - In real mode, `/api/health` checks the real model servers. Every endpoint is real: the general tools, Guide, Report sites, the Town report's FEMA threshold and incident Analyze.
- `uv run python -m scripts.export_examples`: regenerates `contracts/examples/` after any schema change. A test checks they match.
- `uv run ruff check .`: lint. The rule set is pinned in `pyproject.toml`.
- `uv run python eval/run_all.py`: the evaluation. Built in M2/M3.
- `uv run python eval/run_guardrails.py`: the red-team check for the guardrails. Needs the model servers.

## Rules
- **Offline at runtime.**
  - No network calls in `backend/`, `domain/` or `frontend/`, and nothing loaded from a CDN.
  - Models load from local paths in `models/resolved.json`.
  - Downloads happen only in `serving/download_models.py`, `serving/fetch_corpus.py`, `serving/get_llama_cpp.py` and `eval/fetch_datasets.py`.
- **Cross-platform.** Use `pathlib` and argument lists for subprocesses. The demo runs on macOS (Apple Silicon), and Windows must keep working.
- **Model calls.**
  - Thinking mode off: `chat_template_kwargs: {"enable_thinking": false}`.
  - Temperature 0 for extraction and JSON, and at most 0.2 otherwise.
  - Always set `max_tokens`.
  - Use `json_schema` for structured output.
- **Evidence first.**
  - Every answer or field cites evidence that can be checked: a verified quote with its timestamp, page or frame, or the photo itself. Otherwise it says "not in the document", "can't tell" or "needs review".
  - Fixed rules, not the model, set FEMA damage levels.
- **Guardrails.**
 - Every rule lives in `backend/guard/policy.yaml`. Change limits, messages and patterns there, not in workers.
 - Wrap text taken from files with `wrap_untrusted()` before it goes into a prompt.
 - Generated code runs only through `backend/sandbox/runner.py`.
 - Decline patterns must stay narrow. Storm-safety questions like "how do I shut off the gas?" must never be declined, and `tests/test_guardrails.py` checks this.
- **Never commit** model weights, datasets, the corpus PDFs or anything under `data/`. CrisisMMD is licensed CC BY-NC-SA, so never commit its images.
- **The organizers' practice pack** lives in `eval/datasets/practice_pack/`, which git ignores. Code finds it through `STORMLOG_PRACTICE_DIR`, which defaults to that folder. Their rules:
  - Never commit the pack, its answers, or any per-item outputs to this public repo. Only aggregate scores may go in the README.
  - No fine-tuning.
  - The app must never look up answers in the labels of the source datasets (COCO, VizWiz, LibriSpeech, ESC-50, SQuAD, HumanEval).
  - Few-shot examples and retrieval are allowed.
- **Contract files** (`contracts/`, `backend/schemas.py`) change only when both sessions agree.

## Folder ownership (two Claude Code sessions)
- **Mac session:** `backend/`, `domain/`, `serving/`, `scripts/`, `eval/`, `tests/`.
- **Windows session:** `frontend/`, `demo/`, `slides/`.
- **Shared:** `contracts/`, `docs/`, `README.md`. Keep edits there small and coordinated.

## Git
- Make small commits with clear messages.
- Run `git pull --rebase` before every push.
- **Ask the user before pushing.** Never force-push.
- **Don't credit AI tools as commit co-authors.** Commit messages and PR descriptions must not include a `Co-Authored-By: Claude` trailer, or any other AI trailer. The team decided this, and the README's statement on AI coding tools covers disclosure.
- Tags: `v0.1` (the five general tiles work), `v0.5` (StormLog works), `v1.0` (final).

## Gotchas (already found)
- **Windows:** the default `python` is 3.14, so always go through uv, which pins 3.12. The `ffmpeg` on PATH is ImageMagick's old 4.2 build, so decode media with PyAV (`av`), never the ffmpeg command line.
- **llama.cpp on macOS:** use `brew install llama.cpp` (Metal). On GitHub, the numbered builds are pre-releases, and the macOS builds are `.tar.gz`.
- **fema.gov blocks scripted downloads.** `fetch_corpus.py` prints the two FEMA PDFs to save from a browser. Don't try to get around the block.
- **CLAP** (`laion/clap-htsat-unfused`) expects 48 kHz audio, and its weights are `.bin`, which needs torch ≥ 2.6. `transformers` is pinned below 5.
- **CLAP hears some voices as alarms.** It scored plain speech as "CO alarm" at 45–70%. A StormLog alarm hazard also needs the 3 kHz beep check in `domain/storm/tones.py`.
- **Qwen GGUF names:** the fallback vision model is `Qwen/Qwen3-VL-4B-Instruct-GGUF`, with files `Qwen3VL-4B-Instruct-Q4_K_M.gguf` and `mmproj-Qwen3VL-4B-Instruct-F16.gguf`.
