# HearThat — Copilot / agent instructions

This repository turns PDF books into audiobooks via Azure OpenAI + Azure Speech.
When generating code, follow these conventions:

## Stack
- Python **3.13**, packaging with **uv** (`uv sync`, `uv run …`). No `pip install`, no `requirements.txt`.
- **FastAPI 0.115+** with **HTMX 2.x** + Tailwind CDN. No SPA framework, no custom JS bundle.
- **Pydantic v2** + **pydantic-settings** for config. All settings via `Settings` in `src/hearthat/config.py`.
- **Async first**. Use `httpx.AsyncClient`, `aiosqlite`, `AsyncAzureOpenAI`. Never mix sync clients in async paths.

## Azure auth — passwordless only
- Use `DefaultAzureCredential` / `AsyncDefaultAzureCredential` via helpers in `src/hearthat/auth.py`.
- Cognitive Services scope constant: `COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"`.
- **Never** add API-key fallbacks. **Never** hardcode endpoints. **Never** read from `keys.env`.

## Azure OpenAI model rules
- Use `max_completion_tokens` (not `max_tokens`) for gpt-4.1+/gpt-5 families.
- Reasoning models (`o1`, `o3`, `o4`, `gpt-5*`): pass `reasoning_effort` (`minimal` for fast paths, `low` for vision). **Do not** pass `temperature`.
- Non-reasoning models (`gpt-4.1-*`, `gpt-4o-*`): use `temperature` (0.2–0.4 typical). **Do not** pass `reasoning_effort`.
- Default summary model: `gpt-5.4-mini`. Fallback: `gpt-4.1-mini`. Premium: `gpt-5.5`.

## TTS rules
- Default voice: **`en-us-Iris:MAI-Voice-1`** (preview, narration). Fallback: `en-US-Ava:DragonHDOmniLatestNeural`.
- Three backends in `src/hearthat/tts.py`: `azure_speech_mai`, `azure_speech_hd`, `openai_tts`.
- MAI + HD voices both go through **Batch Synthesis** (`api-version=2024-04-01`, output `audio-24khz-160kbitrate-mono-mp3`).
- `gpt-4o-mini-tts` accepts an `instructions=` parameter — wire it from `VoiceSpec.style`.

## Retry policy (LLM Speech doc standard)
All async Azure HTTP calls use:
- 5 attempts, exponential backoff `2/4/8/16/32 s` (`tenacity.wait_exponential(multiplier=2, min=2, max=32)`)
- Retry only on `httpx.HTTPStatusError`, `httpx.TransportError`, `httpx.TimeoutException`
- Reset request streams on retry (multipart uploads must reopen the file handle)

## Live availability — always cross-check
- https://model-availability.azurewebsites.net/ (updated every 10 min)
- https://learn.microsoft.com/en-us/azure/ai-services/speech-service/mai-voices
- https://learn.microsoft.com/en-us/azure/ai-services/speech-service/llm-speech?tabs=new-foundry%2Cwindows&pivots=ai-foundry
- https://learn.microsoft.com/en-us/azure/ai-services/speech-service/high-definition-voices
- https://learn.microsoft.com/en-us/azure/ai-services/speech-service/batch-synthesis
- https://learn.microsoft.com/en-us/azure/ai-services/openai/text-to-speech-quickstart

## Style
- 100-char line length, ruff + mypy strict on `src/`, asyncio mode auto in pytest.
- Prefer `pathlib.Path`, `enum.StrEnum`, dataclass-like Pydantic models.
- No print statements in library code — use `logging.getLogger(__name__)`.
- Don't add features, refactors, or comments that weren't requested.

## Docker
- Plain `docker build` only — **no BuildKit `--mount` features** (ACR Tasks compatibility).
- Cache layers via `COPY pyproject.toml uv.lock` → `uv sync` → `COPY src`.
- Non-root user `hearthat` (uid 1001), healthcheck on `/healthz`.

## CI / GitHub Actions
- **CI is currently disabled** for this demo (`.github/workflows/ci.yml` runs on
  `workflow_dispatch` only). Do **not** re-enable the `push` / `pull_request`
  triggers, and do **not** add new workflows (deploy, release, scheduled jobs,
  etc.) unless explicitly asked.
- Local checks before pushing: `uv run ruff check . ; uv run ruff format --check . ; uv run mypy src ; uv run pytest -q`.

## Repo layout
- Source: `src/hearthat/` (package), UI in `src/hearthat/ui/`.
- Notebooks: `notebooks/` (3 demos using the same package, kernel `hearthat`).
- Samples: `data/samples/`. Runtime output: `data/out/`. Both gitignored.
- **Never commit** anything under `data/`, `*.env`, or `hearthat.db`.
