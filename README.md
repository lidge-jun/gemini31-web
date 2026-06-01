# gemini31-web

[![CI](https://github.com/lidge-jun/gemini31-web/actions/workflows/ci.yml/badge.svg)](https://github.com/lidge-jun/gemini31-web/actions/workflows/ci.yml)
[![Pages](https://github.com/lidge-jun/gemini31-web/actions/workflows/pages.yml/badge.svg)](https://github.com/lidge-jun/gemini31-web/actions/workflows/pages.yml)
![Python](https://img.shields.io/badge/python-3.x-111827)
![License pending](https://img.shields.io/badge/license-pending-6b7280)

Streaming Web UI for Vertex AI Gemini models with live thinking display.

This is a local Python + vanilla JavaScript experiment. `server.py` serves `index.html`, calls Vertex AI `streamGenerateContent`, relays SSE events to the browser, and stores chat history as local JSON files under `chats/`.

## Public Surface

| Area | Current status |
| --- | --- |
| Repository | Public repo, GitHub reports 2 stars / 0 forks |
| Runtime | Python stdlib HTTP server + vanilla JS frontend |
| Required package | `google-auth` |
| Default port | `3131` |
| Default model config | `VERTEX_MODEL=gemini-3.1-pro-preview` in `server.py` |
| Local data | Chat JSON files under `chats/` |
| GitHub Pages | Prepared from `/docs` after an authorized push |
| CI | Prepared in `.github/workflows/ci.yml`; no remote runs yet |
| License | No root `LICENSE` file is declared in this repository |

## Features

- SSE streaming responses with a stream on/off toggle.
- Collapsible thinking panel for model thought-summary chunks.
- Thinking level control: high, medium, low, minimal.
- Model selector for Gemini 3.1 Pro, 3 Pro, 2.5 Pro, and 2.5 Flash-style config strings.
- Chat history sidebar backed by local `chats/*.json`.
- AI auto-title endpoint for the first exchange.
- System prompt modal saved in localStorage.
- Google Search grounding toggle.
- Multimodal drag/drop and paste handling for image, PDF, audio, video, and text files.
- Markdown rendering, code highlighting, KaTeX math, and token statistics.

## Setup

1. Create a Vertex AI service account JSON key.
2. Create `.env`:

```env
GOOGLE_APPLICATION_CREDENTIALS=~/secure/vertex-sa.json
VERTEX_MODEL=gemini-3.1-pro-preview
VERTEX_MAX_TOKENS=65536
PORT=3131
```

`VERTEX_PROJECT` is auto-detected from the service account JSON `project_id`. Set it manually only when you need to override that value.

3. Install and run:

```bash
pip install google-auth
python3 server.py
```

Then open `http://localhost:3131`.

## Verification

```bash
python3 -m py_compile server.py
```

Full live testing requires valid Vertex AI credentials and a model name available to the configured Google Cloud project. Static public-surface validation does not require secrets.

## Architecture

```text
Browser
  <- server-sent events ->
server.py
  <- Vertex AI streamGenerateContent ->
Gemini model configured by VERTEX_MODEL
```

Server event types:

| Event | Meaning |
| --- | --- |
| `thinking` | Thought summary chunk |
| `text` | Response text chunk |
| `meta` | Token statistics and grounding sources |
| `done` | Stream completed |

API endpoints:

| Endpoint | Purpose |
| --- | --- |
| `GET /` | Serve UI |
| `POST /` | Chat, streaming or sync |
| `GET/POST /api/config` | Read or update `.env` settings |
| `GET /api/chats` | List saved chats |
| `GET/POST/DELETE /api/chats/:id` | Chat history CRUD |
| `POST /api/title` | AI-generated chat title |

## Security & Privacy

- Do not commit `.env`, service account JSON, chat history, or generated uploads.
- `GOOGLE_APPLICATION_CREDENTIALS` should point to a private file outside the repository.
- The app stores chat history locally in `chats/`; those files may contain private prompts, uploaded-file metadata, or model outputs.
- `/api/config` can write `.env` values to disk. Run this app only on a trusted local machine/network.
- GitHub Pages hosts documentation only, not the credentialed Vertex UI.

## License

This repository currently has no root `LICENSE` file. Add an explicit license before redistributing or depending on the project externally.
