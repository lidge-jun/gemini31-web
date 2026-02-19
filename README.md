# gemini31-web

Gemini 3.1 Pro Preview — Streaming Web UI with Thinking Display

Real-time SSE streaming chat interface for Vertex AI Gemini models. Shows thinking process (thought summaries) live as the model reasons, then streams the response with markdown rendering.

## Features

- **SSE Streaming** — responses stream token-by-token like ChatGPT/Gemini
- **Thinking Display** — collapsible panel shows model's reasoning process in real-time
- **Thinking Level Control** — adjust reasoning depth (High/Medium/Low/Minimal)
- **Multi-model** — switch between Gemini 3.1 Pro, 3 Pro, 2.5 Pro, 2.5 Flash
- **Token Stats** — thinking/output/input/total token counts per response
- **Markdown Rendering** — code blocks, tables, lists rendered properly
- **Zero dependencies** — only `google-auth` (stdlib HTTP server + vanilla JS)

## Setup

1. **Service Account**: Create a Vertex AI service account key (JSON)
2. **Configure `.env`**:

```env
GOOGLE_APPLICATION_CREDENTIALS=~/secure/vertex-sa.json
VERTEX_PROJECT=your-gcp-project-id
VERTEX_MODEL=gemini-3.1-pro-preview
VERTEX_MAX_TOKENS=65536
PORT=3131
```

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
- `meta` — final token statistics
- `done` — stream complete

## License

MIT
