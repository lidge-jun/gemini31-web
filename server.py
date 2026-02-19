#!/usr/bin/env python3
"""Gemini 3.1 Pro Preview — Web UI server with SSE streaming + thinking + chat history."""
import json, os, sys, uuid, time
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

# Auto-parse project_id from SA JSON if not explicitly set
if not PROJECT:
    try:
        sa_data = json.loads(Path(SA_PATH).read_text())
        PROJECT = sa_data.get("project_id", "")
        if PROJECT:
            print(f"📋 Project ID auto-detected from SA JSON: {PROJECT}")
    except Exception:
        pass

if not PROJECT:
    sys.exit("❌ Project ID를 찾을 수 없습니다. SA JSON에 project_id가 없거나 VERTEX_PROJECT를 설정하세요.")

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SA_PATH

HTML = open(os.path.join(os.path.dirname(__file__), "index.html"), "r").read()

# Chat storage directory
CHATS_DIR = Path(__file__).parent / "chats"
CHATS_DIR.mkdir(exist_ok=True)

# Supported file MIME types for Gemini multimodal
SUPPORTED_MIME = {
    # Images
    "image/png", "image/jpeg", "image/webp", "image/gif", "image/heic", "image/heif",
    # PDF
    "application/pdf",
    # Audio
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/ogg", "audio/flac", "audio/aac",
    "audio/webm", "audio/x-m4a", "audio/mp4",
    # Video
    "video/mp4", "video/mpeg", "video/mov", "video/avi", "video/x-flv",
    "video/mpg", "video/webm", "video/wmv", "video/3gpp", "video/quicktime",
    # Text
    "text/plain", "text/csv", "text/html",
}


def get_token():
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def _build_contents(prompt: str, files: list = None):
    """Build Vertex AI contents array with text and optional files (images, PDF, audio, video)."""
    parts = []
    if files:
        for f in files:
            parts.append({
                "inlineData": {
                    "mimeType": f.get("mimeType", "application/octet-stream"),
                    "data": f["data"],  # base64
                }
            })
    parts.append({"text": prompt})
    return [{"role": "user", "parts": parts}]


def _call_gemini(contents, model, temp, thinking_level, stream=True, web_search=False, system_prompt=None):
    """Make Vertex AI API call. Returns (conn, resp)."""
    host = "aiplatform.googleapis.com"
    endpoint = "streamGenerateContent?alt=sse" if stream else "generateContent"
    path = (
        f"/v1/projects/{PROJECT}"
        f"/locations/global/publishers/google/models/{model}:{endpoint}"
    )
    thinking_cfg = {"includeThoughts": True}
    if "2.5" in model:
        budget_map = {"off": 0, "low": 1024, "medium": 8192, "high": 24576}
        thinking_cfg["thinkingBudget"] = budget_map.get(thinking_level, 24576)
    else:
        thinking_cfg["thinkingLevel"] = thinking_level.upper()

    body_dict = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": MAX_TOKENS,
            "temperature": temp,
            "thinkingConfig": thinking_cfg,
        },
    }

    if web_search:
        body_dict["tools"] = [{"google_search": {}}]

    if system_prompt:
        body_dict["systemInstruction"] = {"parts": [{"text": system_prompt}]}

    body = json.dumps(body_dict).encode()

    token = get_token()
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(host, context=ctx)
    conn.request("POST", path, body=body, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    return conn, conn.getresponse()


def stream_gemini(prompt, model=MODEL, temp=0.7, thinking_level="high",
                  files=None, web_search=False, system_prompt=None):
    """Generator that yields SSE events from Vertex AI streamGenerateContent."""
    contents = _build_contents(prompt, files)
    conn, resp = _call_gemini(contents, model, temp, thinking_level,
                              stream=True, web_search=web_search, system_prompt=system_prompt)

    if resp.status != 200:
        error_body = resp.read().decode()
        yield {"event": "error", "data": f"Vertex API error {resp.status}: {error_body}"}
        conn.close()
        return

    last_usage = None
    last_finish = ""
    last_model = model
    grounding_metadata = None
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
            # Capture grounding metadata
            gm = c.get("groundingMetadata")
            if gm:
                grounding_metadata = gm

        usage = data.get("usageMetadata")
        if usage and usage.get("promptTokenCount"):
            last_usage = usage
        if data.get("modelVersion"):
            last_model = data["modelVersion"]

    meta = {
        "thinking": last_usage.get("thoughtsTokenCount", 0) if last_usage else 0,
        "output": last_usage.get("candidatesTokenCount", 0) if last_usage else 0,
        "input": last_usage.get("promptTokenCount", 0) if last_usage else 0,
        "total": last_usage.get("totalTokenCount", 0) if last_usage else 0,
        "model": last_model,
        "finishReason": last_finish,
    }
    if grounding_metadata:
        meta["grounding"] = grounding_metadata

    yield {"event": "meta", "data": json.dumps(meta)}
    conn.close()
    yield {"event": "done", "data": ""}


def sync_gemini(prompt, model=MODEL, temp=0.7, thinking_level="high",
                files=None, web_search=False, system_prompt=None):
    """Non-streaming call. Returns full response dict."""
    contents = _build_contents(prompt, files)
    conn, resp = _call_gemini(contents, model, temp, thinking_level,
                              stream=False, web_search=web_search, system_prompt=system_prompt)
    body = json.loads(resp.read().decode())
    conn.close()

    result = {"text": "", "thinking": "", "meta": None}
    if resp.status != 200:
        result["text"] = f"Error {resp.status}"
        return result

    candidates = body.get("candidates", [])
    if candidates:
        for part in candidates[0].get("content", {}).get("parts", []):
            text = part.get("text", "")
            if part.get("thought"):
                result["thinking"] += text
            else:
                result["text"] += text

    usage = body.get("usageMetadata", {})
    result["meta"] = {
        "thinking": usage.get("thoughtsTokenCount", 0),
        "output": usage.get("candidatesTokenCount", 0),
        "input": usage.get("promptTokenCount", 0),
        "total": usage.get("totalTokenCount", 0),
        "model": body.get("modelVersion", model),
        "finishReason": candidates[0].get("finishReason", "") if candidates else "",
    }
    gm = candidates[0].get("groundingMetadata") if candidates else None
    if gm:
        result["meta"]["grounding"] = gm
    return result


def generate_title(user_msg: str, ai_msg: str):
    """Generate a short chat title using Gemini."""
    prompt = (
        f"다음 대화의 제목을 한국어로 짧게 만들어줘 (15자 이내, 제목만 출력).\n"
        f"사용자: {user_msg[:200]}\n"
        f"AI: {ai_msg[:200]}"
    )
    try:
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        conn, resp = _call_gemini(contents, MODEL, 0.3, "low", stream=False)
        body = json.loads(resp.read().decode())
        conn.close()
        if resp.status == 200:
            candidates = body.get("candidates", [])
            if candidates:
                for part in candidates[0].get("content", {}).get("parts", []):
                    if not part.get("thought") and part.get("text"):
                        return part["text"].strip().strip('"').strip("'")[:40]
    except Exception:
        pass
    return user_msg[:30]


# ── Chat CRUD helpers ──

def list_chats():
    chats = []
    for f in CHATS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            chats.append({
                "id": f.stem,
                "title": data.get("title", "New Chat"),
                "updated": data.get("updated", 0),
                "messageCount": len(data.get("messages", [])),
            })
        except Exception:
            continue
    chats.sort(key=lambda c: c["updated"], reverse=True)
    return chats


def load_chat(chat_id):
    f = CHATS_DIR / f"{chat_id}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text())


def save_chat(chat_id, data):
    data["updated"] = time.time()
    if not data.get("title") and data.get("messages"):
        for m in data["messages"]:
            if m.get("role") == "user":
                data["title"] = m["text"][:40]
                break
    (CHATS_DIR / f"{chat_id}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))


def delete_chat(chat_id):
    f = CHATS_DIR / f"{chat_id}.json"
    if f.exists():
        f.unlink()


# ── Config helpers ──

def get_config():
    """Read current config from .env and running state."""
    return {
        "saPath": SA_PATH,
        "project": PROJECT,
        "model": MODEL,
        "maxTokens": MAX_TOKENS,
        "port": PORT,
    }


def update_env(updates):
    """Update .env file with new values."""
    env_path = Path(__file__).parent / ".env"
    lines = []
    if env_path.exists():
        lines = env_path.read_text().splitlines()

    # Parse existing lines
    env_dict = {}
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, v = stripped.split("=", 1)
            env_dict[k.strip()] = v.strip()

    # Apply updates
    env_dict.update(updates)

    # Write back
    new_lines = [f"{k}={v}" for k, v in env_dict.items()]
    env_path.write_text("\n".join(new_lines) + "\n")
    return env_dict


class Handler(BaseHTTPRequestHandler):
    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def do_GET(self):
        if self.path == "/api/chats":
            self._json_response(list_chats())
        elif self.path.startswith("/api/chats/"):
            chat_id = self.path.split("/")[-1]
            data = load_chat(chat_id)
            if data:
                self._json_response(data)
            else:
                self._json_response({"error": "not found"}, 404)
        elif self.path == "/api/config":
            self._json_response(get_config())
        elif self.path == "/api/mimetypes":
            self._json_response(sorted(SUPPORTED_MIME))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode())

    def do_POST(self):
        body_raw = self.rfile.read(int(self.headers["Content-Length"]))
        body = json.loads(body_raw)

        # Chat save endpoint
        if self.path.startswith("/api/chats/"):
            chat_id = self.path.split("/")[-1]
            save_chat(chat_id, body)
            self._json_response({"ok": True})
            return

        # Auto-title endpoint
        if self.path == "/api/title":
            title = generate_title(body.get("user", ""), body.get("ai", ""))
            self._json_response({"title": title})
            return

        # Config update endpoint
        if self.path == "/api/config":
            updates = {}
            if "saPath" in body:
                updates["GOOGLE_APPLICATION_CREDENTIALS"] = body["saPath"]
            if "project" in body:
                updates["VERTEX_PROJECT"] = body["project"]
            if "model" in body:
                updates["VERTEX_MODEL"] = body["model"]
            if "maxTokens" in body:
                updates["VERTEX_MAX_TOKENS"] = str(body["maxTokens"])
            if updates:
                update_env(updates)
            self._json_response({"ok": True, "note": "Restart server to apply .env changes"})
            return

        # Chat endpoint
        prompt = body.get("prompt", "")
        model = body.get("model", MODEL)
        temp = body.get("temperature", 0.7)
        thinking_level = body.get("thinking_level", "high")
        files = body.get("files")  # [{mimeType, data}]
        use_stream = body.get("stream", True)
        web_search = body.get("web_search", False)
        system_prompt = body.get("system_prompt")

        if use_stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            try:
                for evt in stream_gemini(prompt, model, temp, thinking_level, files, web_search, system_prompt):
                    payload = json.dumps({"event": evt["event"], "data": evt["data"]}, ensure_ascii=False)
                    self.wfile.write(f"data: {payload}\n\n".encode())
                    self.wfile.flush()
            except Exception as e:
                payload = json.dumps({"event": "error", "data": str(e)}, ensure_ascii=False)
                self.wfile.write(f"data: {payload}\n\n".encode())
                self.wfile.flush()
        else:
            try:
                result = sync_gemini(prompt, model, temp, thinking_level, files, web_search, system_prompt)
                self._json_response(result)
            except Exception as e:
                self._json_response({"error": str(e)}, 500)

    def do_DELETE(self):
        if self.path.startswith("/api/chats/"):
            chat_id = self.path.split("/")[-1]
            delete_chat(chat_id)
            self._json_response({"ok": True})
        else:
            self._json_response({"error": "not found"}, 404)

    def log_message(self, fmt, *args):
        print(f"[gemini31] {args[0]}")


if __name__ == "__main__":
    print(f"🚀 Gemini 3.1 Web UI → http://localhost:{PORT}")
    print(f"   Model: {MODEL} | Project: {PROJECT}")
    print(f"   SA: {SA_PATH}")
    print(f"   Streaming: ON | Thinking: ON | Chat History: chats/")
    HTTPServer(("", PORT), Handler).serve_forever()
