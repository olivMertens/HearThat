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

HearThat takes a PDF, plain-text or Markdown book, extracts and summarises every
chapter with Azure OpenAI, asks a small LLM to label each paragraph
(heading / dialog / narration / action + mood + style) and then narrates it with
**MAI-Voice-1** (preview), **DragonHD / Omni**, or the prompt-steerable
**gpt-4o-mini-tts** model. A small FastAPI + HTMX UI lets you upload books, watch
live progress, and listen to the result. Authentication is passwordless
(Entra ID) in production with an opt-in API-key fallback for local development.

## 🖥️ Web UI — walkthrough

The FastAPI + HTMX UI runs on `http://127.0.0.1:8000` after `uv run hearthat ui`.

### Step 1 — Connect HearThat to your Azure resources

Open **Settings** (top-right). On a fresh install only three fields are visible
under **Essentials** — that's all that's strictly required:

![HearThat — Settings, default view](assets/screenshots/ui-settings.png)

- **Azure OpenAI endpoint** — your Foundry / Azure OpenAI resource URL
- **Azure AI Speech endpoint** — used by Batch Synthesis (MAI-Voice-1, DragonHD)
- **Azure AI Speech region** — `eastus` covers MAI-Voice-1 preview

Authentication uses **Entra ID via `DefaultAzureCredential`** — run `az login`
once and you're done. Click **Test connections** to verify each endpoint
answers (✅ reachable / ⚠️ unexpected status / ❌ unreachable).

Need more? Expand **Advanced** to override deployments and voices, or
**Developer — local API keys** (dev mode only) to paste an API key as a
fallback when Entra ID isn't available:

![HearThat — Settings, all tiers expanded](assets/screenshots/ui-settings-expanded.png)

You can also **Export current settings** as a ready-to-edit `hearthat.env`, or
**Import** an existing `.env` from the bar at the top. Tick *Remember these
values for next time* to persist changes to a local `.env`.

### Step 2 — Pick a book

Go back to **Audiobooks**. The form is intentionally short:

![HearThat — Audiobooks, default form](assets/screenshots/ui-home.png)

- **Source document** — PDF, `.txt` or `.md`, validated client-side against
  the demo size cap shown in the top-right pill
- **Voice style** — *Iris — natural narrator (recommended)* (MAI-Voice-1),
  *Ava — high-definition voice* (DragonHD Omni), or *Alloy — short-form,
  prompt steerable* (gpt-4o-mini-tts)
- **Reading depth** — *Smart* (`gpt-5.4-mini`), *Fast* (`gpt-4.1-mini`) or
  *Deep* (`gpt-5.5`)

### Step 3 — (Optional) Fine-tune the narration

Expand **Advanced voice options** to override the default voice or steer the
overall tone for that specific job:

![HearThat — Audiobooks, ready to synthesise](assets/screenshots/ui-home-ready.png)

- **Voice name (optional)** — e.g. another DragonHD voice
- **Mood instruction (optional)** — e.g. *"calm narrator, slightly amused"*
  (overrides the per-paragraph mood that HearThat already detects)

Once a valid file is picked, the **Synthesise** button enables and the inline
hint switches to *"Ready to synthesise."*

### Step 4 — Watch progress and listen

Click **Synthesise**. HearThat creates a job and inserts a row in the **Jobs**
table below the form. HTMX polls live progress every couple of seconds and the
status cycles through *Reading the document → Understanding chapters →
Narrating*. When the job is complete, the row exposes an inline `<audio>`
player per chapter plus a download link for the full MP3 (and the original
Batch Synthesis ZIP).

> 💡 **Tip:** open the **Settings** page once at the start to confirm
> `DefaultAzureCredential` is happy. From then on, the Audiobooks page is the
> only one you need.

## ✨ Features

- 📄 **Multi-format ingestion** — PDF via **Azure AI Document Intelligence** (`prebuilt-layout`, with `pypdf` fallback), plus native `.txt` and `.md`, with demo upload limits and inline file validation
- 🧠 **Reasoning-grade summaries** — **Azure OpenAI in Microsoft Foundry** with `gpt-5.4-mini` (`reasoning_effort=minimal`)
- 🎬 **Scene-aware narration** — a small LLM step (also Azure OpenAI) labels every paragraph (heading / dialog / narration / action, mood, `mstts:express-as` style, pause and emphasis) **before** SSML is built, with graceful regex-only fallback
- 🎙️ Three TTS backends powered by **Azure AI Speech** and **Azure OpenAI**:
  - **MAI-Voice-1** (Iris, audiobook narrator, preview) — Azure AI Speech Batch Synthesis
  - **DragonHD / Omni** (700+ multilingual voices) — Azure AI Speech Batch Synthesis
  - **gpt-4o-mini-tts** (prompt-steerable) — Azure OpenAI text-to-speech
- 🖼️ **Multimodal vision** — Azure OpenAI vision describes figures so the narrator mentions them naturally
- 🌍 **Batch translation** via **Azure AI Translator** (Document Translation 1.1)
- 📊 **Live progress UI** — phase-aware status (`Reading the document` → `Understanding chapters` → `Narrating`), animated spinner, percentage bar, HTMX polling
- 🎧 **Inline MP3 player + downloads** — completed jobs expose `<audio>` players and download buttons (MP3 is extracted from Batch Synthesis ZIPs automatically)
- ⚙️ **Env-aware Settings page** — endpoints visible everywhere; API-key fields only appear in development mode (`HEARTHAT_ENV != prod`)
- 🔐 **Passwordless first** — `DefaultAzureCredential` everywhere, with optional `AZURE_*_API_KEY` fallback gated to development

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

# 2. Configure endpoints (no API keys needed in production)
copy .env.example .env

# 3. Sign in once — DefaultAzureCredential picks this up
az login

# 4a. Web UI (FastAPI + HTMX)
uv run hearthat ui            # http://127.0.0.1:8000

# 4b. CLI
uv run hearthat run data/samples/screentime/*.pdf --backend azure_speech_mai
uv run hearthat tts-openai "Welcome to HearThat" --instructions "warm storyteller"
```

### Development mode (API keys allowed)

Locally, `HEARTHAT_ENV` defaults to `dev`, which makes the **Settings** page
expose masked key fields when Entra ID sign-in is not convenient:

```env
HEARTHAT_ENV=dev                       # set to "prod" to hide all key fields
AZURE_OPENAI_API_KEY=...               # only used when HEARTHAT_ENV != prod
AZURE_SPEECH_API_KEY=...
AZURE_DOCINTEL_API_KEY=...
AZURE_TRANSLATOR_API_KEY=...
```

In production (`HEARTHAT_ENV=prod`) these fields are hidden in the UI and
ignored on save — only `DefaultAzureCredential` is used.

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
    SRC[PDF · TXT · MD] --> ING[Ingest]
    ING -->|PDF| DI[Document Intelligence]
    ING -->|TXT/MD| TXT[Native parser]
    DI --> CH[Chapters + figures]
    TXT --> CH
    CH --> SUM[gpt-5.4-mini · summary]
    CH --> VIS[gpt-5.4-mini · vision]
    SUM --> SCENE[gpt-5.4-mini · scene plan<br/>kind · mood · style · pause · emphasis]
    VIS --> SCENE
    SCENE --> SSML[SSML builder<br/>mstts:express-as · break · emphasis]
    SSML --> TTS{TTS backend}
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

See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for the full dev setup
(local launch, Service Principal fallback to avoid `az login`, RBAC,
troubleshooting).

```powershell
uv sync --all-extras
uv run pre-commit install
uv run ruff check . ; uv run mypy src ; uv run pytest -q
```

## 📝 License

[MIT](LICENSE) © 2026 Olivier Mertens — provided **as-is** for demo and educational purposes.
"MAI-Voice-1", "DragonHD", "Azure", "Azure OpenAI", "Azure AI Speech", "Azure AI Document Intelligence" and "Microsoft Foundry" are trademarks of Microsoft Corporation; this project is an independent demo and is not affiliated with or endorsed by Microsoft.
