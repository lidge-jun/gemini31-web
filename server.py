#!/usr/bin/env python3
"""Gemini 3.1 Pro Preview — Web UI server with SSE streaming + thinking."""
import json, os, sys, re
from http.server import HTTPServer, BaseHTTPRequestHandler
import google.auth
import google.auth.transport.requests
import http.client
import ssl
from pathlib import Path

# Load .env if present
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

SA_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", os.path.expanduser("~/secure/vertex-sa.json"))
PROJECT = os.environ.get("VERTEX_PROJECT", "")
MODEL = os.environ.get("VERTEX_MODEL", "gemini-3.1-pro-preview")
MAX_TOKENS = int(os.environ.get("VERTEX_MAX_TOKENS", "65536"))
PORT = int(os.environ.get("PORT", "3131"))

if not PROJECT:
    sys.exit("❌ VERTEX_PROJECT is required. Set it in .env or as an environment variable.")

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SA_PATH

HTML = open(os.path.join(os.path.dirname(__file__), "index.html"), "r").read()


def get_token():
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def stream_gemini(prompt: str, model: str = MODEL, temp: float = 0.7, thinking_level: str = "high"):
    """Generator that yields SSE events from Vertex AI streamGenerateContent."""
    host = "aiplatform.googleapis.com"
    path = (
        f"/v1/projects/{PROJECT}"
        f"/locations/global/publishers/google/models/{model}:streamGenerateContent?alt=sse"
    )
    # Build thinkingConfig based on model family
    thinking_cfg = {"includeThoughts": True}
    if "2.5" in model:
        # Gemini 2.5 uses thinkingBudget (token count). Map levels to budgets.
        budget_map = {"off": 0, "low": 1024, "medium": 8192, "high": 24576}
        thinking_cfg["thinkingBudget"] = budget_map.get(thinking_level, 24576)
    else:
        # Gemini 3+ uses thinkingLevel enum
        thinking_cfg["thinkingLevel"] = thinking_level.upper()

    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": MAX_TOKENS,
            "temperature": temp,
            "thinkingConfig": thinking_cfg,
        },
    }).encode()

    token = get_token()
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(host, context=ctx)
    conn.request("POST", path, body=body, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    resp = conn.getresponse()

    if resp.status != 200:
        error_body = resp.read().decode()
        yield {"event": "error", "data": f"Vertex API error {resp.status}: {error_body}"}
        conn.close()
        return

    # Read SSE stream line-by-line (readline works with chunked TE; read() blocks)
    last_usage = None
    last_finish = ""
    last_model = model
    while True:
        line = resp.readline()
        if not line:
            break
        decoded = line.decode("utf-8", errors="replace").strip()
        if not decoded.startswith("data: "):
            continue
        try:
            data = json.loads(decoded[6:])
        except json.JSONDecodeError:
            continue

        candidates = data.get("candidates", [])
        if candidates:
            c = candidates[0]
            parts = c.get("content", {}).get("parts", [])
            for part in parts:
                text = part.get("text", "")
                if not text:
                    continue
                is_thought = part.get("thought", False)
                evt_type = "thinking" if is_thought else "text"
                yield {"event": evt_type, "data": text}
            if c.get("finishReason"):
                last_finish = c["finishReason"]

        # Track usageMetadata (final chunk has the full counts)
        usage = data.get("usageMetadata")
        if usage and usage.get("promptTokenCount"):
            last_usage = usage
        if data.get("modelVersion"):
            last_model = data["modelVersion"]

    # Emit final meta event
    if last_usage:
        yield {
            "event": "meta",
            "data": json.dumps({
                "thinking": last_usage.get("thoughtsTokenCount", 0),
                "output": last_usage.get("candidatesTokenCount", 0),
                "input": last_usage.get("promptTokenCount", 0),
                "total": last_usage.get("totalTokenCount", 0),
                "model": last_model,
                "finishReason": last_finish,
            }),
        }

    conn.close()
    yield {"event": "done", "data": ""}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.encode())

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = body.get("prompt", "")
        model = body.get("model", MODEL)
        temp = body.get("temperature", 0.7)
        thinking_level = body.get("thinking_level", "high")

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        try:
            for evt in stream_gemini(prompt, model, temp, thinking_level):
                sse_line = f"event: {evt['event']}\ndata: {evt['data']}\n\n"
                self.wfile.write(sse_line.encode())
                self.wfile.flush()
        except Exception as e:
            err = f"event: error\ndata: {str(e)}\n\n"
            self.wfile.write(err.encode())
            self.wfile.flush()

    def log_message(self, fmt, *args):
        print(f"[gemini31] {args[0]}")


if __name__ == "__main__":
    print(f"🚀 Gemini 3.1 Web UI → http://localhost:{PORT}")
    print(f"   Model: {MODEL} | Project: {PROJECT}")
    print(f"   Streaming: ON | Thinking: ON")
    HTTPServer(("", PORT), Handler).serve_forever()
