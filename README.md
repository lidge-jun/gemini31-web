# gemini31-web

Gemini 3.1 Pro Preview — Streaming Web UI with Thinking Display

Real-time SSE streaming chat interface for Vertex AI Gemini models. Shows thinking process (thought summaries) live as the model reasons, then streams the response with markdown rendering.

## Features

- **SSE Streaming** — responses stream token-by-token (with on/off toggle)
- **Thinking Display** — collapsible panel shows model's reasoning in real-time
- **Thinking Level Control** — adjust reasoning depth (High/Medium/Low/Minimal)
- **Multi-model** — Gemini 3.1 Pro, 3 Pro, 2.5 Pro, 2.5 Flash
- **Chat History** — conversations saved as JSON in `chats/` with sidebar navigation
- **AI Auto-Title** — first exchange auto-generates a chat title via Gemini
- **System Prompt** — modal editor for custom AI instructions (persisted in localStorage)
- **🔍 Web Search** — Google Search grounding toggle for real-time web results
- **Multimodal Input** — drag-and-drop / paste images, PDF, audio, video files
- **Code Highlighting** — highlight.js + language labels + copy button
- **KaTeX Math** — inline `$...$` and block `$$...$$` math rendering
- **Token Stats** — thinking/output/input/total token counts per response
- **Markdown Rendering** — code blocks, tables, lists, blockquotes
- **Collapsible Sidebars** — left (chat list) and right (settings) independently toggle
- **Settings Sidebar** — session settings (instant) + .env config (save to disk)
- **Zero dependencies** — only `google-auth` (stdlib HTTP server + vanilla JS)

## Setup

1. **Service Account**: Create a Vertex AI service account key (JSON)
2. **Configure `.env`**:

```env
GOOGLE_APPLICATION_CREDENTIALS=~/secure/vertex-sa.json
VERTEX_MODEL=gemini-3.1-pro-preview
VERTEX_MAX_TOKENS=65536
PORT=3131
```

> **Note**: `VERTEX_PROJECT` is auto-detected from the SA JSON file's `project_id` field. Set it manually only if you need to override.

3. **Install & Run**:

```bash
pip install google-auth
python3 server.py
# → http://localhost:3131
```

## Architecture

```
Browser ←SSE→ server.py ←SSE→ Vertex AI streamGenerateContent
                              (includeThoughts: true)
```

Server relays Vertex AI SSE stream to browser with event types:
- `thinking` — thought summary chunks
- `text` — response text chunks
- `meta` — final token statistics + grounding sources
- `done` — stream complete

API endpoints:
- `GET /` — serve UI
- `POST /` — chat (streaming or sync)
- `GET/POST /api/config` — read/update .env settings
- `GET /api/chats` — list saved chats
- `GET/POST/DELETE /api/chats/:id` — CRUD individual chat
- `POST /api/title` — AI-generated chat title

## License

MIT
