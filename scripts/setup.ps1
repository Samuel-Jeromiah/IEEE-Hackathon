# One-time setup on Windows: Python environment, llama.cpp, guide PDFs, models.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 [-ModelProfile cpu]
param([string]$ModelProfile = "cpu")
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv not found. Install it: https://docs.astral.sh/uv/getting-started/installation/"
}

Write-Host "== Python environment (uv sync)"
uv sync
if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }

if (-not (Get-Command llama-server -ErrorAction SilentlyContinue)) {
    Write-Host "== llama.cpp (prebuilt CPU build into bin\llama)"
    uv run python serving/get_llama_cpp.py --variant cpu
    if ($LASTEXITCODE -ne 0) { throw "llama.cpp download failed" }
}

Write-Host "== Guide documents"
uv run python serving/fetch_corpus.py
if ($LASTEXITCODE -ne 0) { Write-Warning "Some guide PDFs failed to download (see above)." }

Write-Host "== Models for profile $ModelProfile (the long part)"
uv run python serving/download_models.py --profile $ModelProfile
if ($LASTEXITCODE -ne 0) { throw "Model download failed" }

Write-Host "== Done. Next: uv run pytest, then follow docs/PLAN.md."
