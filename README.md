# StormLog: offline storm-damage reports (IEEE AI Hackathon 2026)

**Status: work in progress (hackathon build, Nov 18–20, 2026).**

StormLog runs entirely on one laptop, with no internet. It has two layers:

- **A general multimodal assistant on local open-weight models.** It can:
  - Describe photos and answer questions about them.
  - Transcribe audio, answer questions about it and identify sounds.
  - Answer questions about documents, and say when the answer isn't there.
  - Write and run code.
  - Describe short videos and answer questions about them.
- **StormLog mode, for small-town Maine emergency managers.** Volunteers' photos, voice notes and videos become a draft damage report for the town's Initial Damage Assessment. The report includes:
  - FEMA damage levels.
  - Safety alerts.
  - A link from every field to its evidence.

## Quick start (macOS, Apple Silicon)

```bash
brew install llama.cpp uv
git clone https://github.com/Samuel-Jeromiah/IEEE-Hackathon
cd IEEE-Hackathon
./scripts/setup.sh    # picks a model profile for this Mac, downloads the models (~8 GB) and guide PDFs
uv run pytest
```

On Windows, run `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1`.

More detail:
- [docs/PLAN.md](docs/PLAN.md): the plan and architecture.
- [docs/STATUS.md](docs/STATUS.md): progress.

## Models (planned)

| Job | Model | Runtime |
|---|---|---|
| Images, documents, video frames, text | Qwen3.5-4B (Q4_K_M) | llama.cpp |
| Speech-to-text | faster-whisper `small` | CTranslate2 |
| Sound identification | CLAP `laion/clap-htsat-unfused` | PyTorch |
| Code | Qwen2.5-Coder-3B-Instruct (Q4_K_M) | llama.cpp |

All inference runs locally. AI coding assistants helped write the code, but they are not part of the running system.
