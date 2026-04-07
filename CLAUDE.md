# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PDFTextualization converts scanned PDFs to Markdown using OCR (Zhipu GLM-OCR API) and optional LLM-based cleanup. It has two components:
- **Python backend** (`backend/`) — CLI pipeline: PDF batching → OCR → LLM cleanup → Markdown output
- **C# Avalonia frontend** (`frontend/`) — Desktop GUI that spawns the backend as a subprocess and parses its JSON stdout for progress updates

## Commands

### Backend (Python)
```bash
cd backend
pip install -r requirements.txt

# Run with config.yaml
python main.py input.pdf

# Run with explicit options
python main.py input.pdf -o output.md \
  --ocr-api-key "your-glm-key" \
  --llm-api-key "your-llm-key" \
  --llm-provider glm \
  --llm-model glm-4.6 \
  --pages 1-50

# Skip LLM cleanup
python main.py input.pdf --no-llm
```

### Frontend (C# / .NET 9)
```bash
cd frontend
dotnet restore PDFTextualization.sln
dotnet build PDFTextualization.sln -c Debug
dotnet run --project PDFTextualization/ -c Debug

# Cross-platform publish
dotnet publish PDFTextualization/ -c Release -r win-x64
dotnet publish PDFTextualization/ -c Release -r osx-arm64
dotnet publish PDFTextualization/ -c Release -r linux-x64
```

## Architecture

### Backend Pipeline (`backend/`)

```
PDF → pdf_processor.py (iter_batches) → ocr_client.py (async, retries)
    → pipeline.py (sliding-window concurrency, max 3 LLM calls)
    → llm_client.py (async, OpenAI-compatible) → md_generator.py → .md file
```

- `config.py`: Priority order — CLI args > env vars (`OCR_API_KEY`, `LLM_API_KEY`) > `config.yaml` > defaults
- `pipeline.py`: Emits JSON lines to stdout (`{"type": "progress"|"done"|"error", ...}`)
- OCR retries: 0s, 2s, 5s, 15s for 429/5xx. LLM retries: 0s, 20s, 40s, 60s
- OCR endpoint: `POST https://open.bigmodel.cn/api/paas/v4/layout_parsing`, PDF as base64

### Frontend IPC

`MainWindowViewModel.cs` spawns `python backend/main.py` and reads JSON lines from stdout in real-time to update progress bar and status. It searches for Python as `python3` then `python`, and locates the backend directory via relative paths from the executable.

### Configuration

Copy `backend/config.example.yaml` → `backend/config.yaml` and set API keys. All keys can also be passed via CLI or environment variables.

## Key Files

| File | Purpose |
|------|---------|
| `backend/pipeline.py` | Main async orchestrator, concurrency control |
| `backend/ocr_client.py` | GLM-OCR API calls, response parsing, retries |
| `backend/llm_client.py` | OpenAI-compatible LLM cleanup, retries |
| `backend/config.py` | `AppConfig` dataclass, config loading hierarchy |
| `frontend/.../ViewModels/MainWindowViewModel.cs` | All UI logic, process spawning, progress parsing |
| `frontend/.../Views/MainWindow.axaml` | XAML layout |
