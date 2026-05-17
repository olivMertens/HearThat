<div align="center">
  <img src="assets/logo.svg" alt="HearThat logo" width="96" />
  <h1>HearThat</h1>
  <p><strong>Turn PDF books into multi-voice audiobooks with Azure Speech &amp; Azure OpenAI.</strong></p>
  <p>
    <img alt="Python" src="https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white" />
    <img alt="uv" src="https://img.shields.io/badge/packaged_with-uv-261230" />
    <img alt="License" src="https://img.shields.io/badge/license-MIT-blue" />
  </p>
</div>

---

HearThat takes a PDF book, extracts and summarises every chapter with Azure OpenAI,
then narrates it using **MAI-Voice-1** (preview), **DragonHD / Omni**, or the
prompt-steerable **gpt-4o-mini-tts** model. A small FastAPI + HTMX UI lets you
upload books and listen to the result; everything authenticates through
Entra ID — no API keys at runtime.

## ✨ Features

- 📄 **Document Intelligence** (`prebuilt-layout`) ingestion with `pypdf` fallback
- 🧠 **Reasoning-grade summaries** with `gpt-5.4-mini` (`reasoning_effort=minimal`)
- 🎙️ Three TTS backends: **MAI-Voice-1** (Iris, narration), **DragonHDOmni** (700+ voices), **gpt-4o-mini-tts** (prompt-steerable)
- 🖼️ **Multimodal vision** describes figures so the narrator mentions them naturally
- 🌍 **Batch translation** via Azure AI Translation Document
- 🔐 Passwordless — `DefaultAzureCredential` everywhere

## 🌍 Regions & models (snapshot 17 May 2026)

> Recommended deployment: Azure OpenAI in `swedencentral` + Azure Speech in `eastus`
> (covers MAI-Voice-1 preview). Live availability:
> https://model-availability.azurewebsites.net/

| Service | Model / Voice | Role | Region | Status |
|---|---|---|---|---|
| Azure OpenAI | `gpt-5.4-mini` | Summaries (reasoning) + vision | `swedencentral`, `eastus2` | GA |
| Azure OpenAI | `gpt-4.1-mini` | Non-reasoning fallback | `swedencentral`, `francecentral`, `westeurope` | GA |
| Azure OpenAI | `gpt-4o-mini-tts` | Prompt-steerable TTS | `swedencentral`, `eastus2` | GA |
| Azure OpenAI | `whisper` / `gpt-4o-mini-transcribe` | STT (notebooks) | `swedencentral`, `eastus2` | GA |
| Azure Speech | **`en-us-Iris:MAI-Voice-1`** ⭐ | Default audiobook narrator | `eastus` | Preview |
| Azure Speech | `en-US-Ava:DragonHDOmniLatestNeural` | Multilingual fallback | `eastus2`, `westus2`, `westeurope` | GA |
| Azure Speech | LLM Speech (transcription + translation) | Bonus `transcribe` module | Foundry Speech regions | Preview |
| Document Intelligence | `prebuilt-layout` | PDF extraction | `swedencentral` (co-loc) | GA |
| Translator | Document Translation 1.1 | Notebook 03 | `swedencentral` | GA |

## 🚀 Quickstart

```powershell
# 1. Install (uv: https://docs.astral.sh/uv/)
uv sync

# 2. Configure endpoints (no API keys!)
copy .env.example .env

# 3. Sign in once — DefaultAzureCredential picks this up
az login

# 4a. Web UI (FastAPI + HTMX)
uv run hearthat ui            # http://127.0.0.1:8000

# 4b. CLI
uv run hearthat run data/samples/screentime/*.pdf --backend azure_speech_mai
uv run hearthat tts-openai "Welcome to HearThat" --instructions "warm storyteller"
```

## 🐳 Docker

```powershell
docker compose build
docker compose up                              # UI on :8000
docker compose --profile notebooks up          # UI + Jupyter Lab on :8888
```

`~/.azure` is mounted read-only so `DefaultAzureCredential` works inside the
container without copying credentials.

## 📓 Notebooks

The `notebooks/` folder contains three runnable demos sharing the same package:

1. [`01_ingest_and_summarize.ipynb`](notebooks/01_ingest_and_summarize.ipynb) — PDF → chapters → summaries
2. [`02_text_to_speech.ipynb`](notebooks/02_text_to_speech.ipynb) — MAI-Voice-1 vs DragonHDOmni vs gpt-4o-mini-tts
3. [`03_translate.ipynb`](notebooks/03_translate.ipynb) — Document Translation

Register the kernel once:

```powershell
uv run python -m ipykernel install --user --name hearthat --display-name "HearThat (uv)"
```

## 🏗️ Architecture

```mermaid
flowchart LR
    PDF[PDF book] --> DI[Document Intelligence]
    DI --> CH[Chapters + figures]
    CH --> SUM[gpt-5.4-mini]
    CH --> VIS[Vision: gpt-5.4-mini]
    SUM --> NAR[Narration text]
    VIS --> NAR
    NAR --> TTS{TTS backend}
    TTS -->|MAI-Voice-1| MAI[Iris audiobook]
    TTS -->|DragonHDOmni| HD[Multilingual]
    TTS -->|gpt-4o-mini-tts| OAI[Prompt-steerable]
```

## 📚 Resources

- Live model availability: https://model-availability.azurewebsites.net/
- [MAI-Voice-1 (preview)](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/mai-voices)
- [LLM Speech (preview)](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/llm-speech?tabs=new-foundry%2Cwindows&pivots=ai-foundry)
- [HD voices (DragonHD / Omni / Flash)](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/high-definition-voices)
- [Batch Synthesis API](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/batch-synthesis)
- [Azure OpenAI TTS quickstart](https://learn.microsoft.com/en-us/azure/ai-services/openai/text-to-speech-quickstart)

## 🤝 Contributing

```powershell
uv sync --all-extras
uv run pre-commit install
uv run ruff check . ; uv run mypy src ; uv run pytest -q
```

## 📝 License

MIT
