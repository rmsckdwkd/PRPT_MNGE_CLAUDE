# -*- coding: utf-8 -*-
"""로컬·사내용 챗봇 중계 서버 — api/chat.js(Vercel)와 같은 일을 PC나 사내 서버에서 한다.

화면(html)을 제공하고 /api/chat 요청을 OpenAI 호환 모델 서버로 전달한다(스트리밍).
키는 환경변수로만 받는다. 표준 라이브러리만 사용.

  OPENROUTER_API_KEY 또는 CHAT_API_KEY   모델 서버 키 (사내 설치 모델이 키를 안 쓰면 아무 값)
  CHAT_BASE_URL     기본 https://openrouter.ai/api/v1  → 사내 설치 시 예: http://gpu-server:8000/v1
  NEMOTRON_MODEL    기본 nvidia/nemotron-3.5-lightning:free
  APP_PASSCODE      화면 접속 암호(선택)

실행:  python3 tools/chat_server.py            → http://localhost:8800
       python3 tools/chat_server.py --port 9000 --html 부동산통합관리시스템_내부망.html
외부 모델(OpenRouter)로 보내는 것은 가상 데이터일 때만. 실데이터는 CHAT_BASE_URL 을 사내 모델로.
"""
import argparse
import json
import os
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = os.environ.get("CHAT_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
MODEL = os.environ.get("NEMOTRON_MODEL", "nvidia/nemotron-3.5-lightning:free")
KEY = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("CHAT_API_KEY") or ""
PASS = os.environ.get("APP_PASSCODE", "")
MAX_CHARS, MAX_MSGS = 80000, 40


class Handler(SimpleHTTPRequestHandler):
    html = "public/index.html"

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def _json(self, status, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.split("?")[0] == "/api/chat":
            return self._json(200, {"ok": bool(KEY), "model": MODEL, "passcode": bool(PASS)})
        if self.path in ("/", "/index.html"):
            self.path = "/" + self.html
        return super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0] != "/api/chat":
            return self._json(404, {"error": "없는 주소입니다."})
        if not KEY:
            return self._json(500, {"error": "OPENROUTER_API_KEY(또는 CHAT_API_KEY) 환경변수가 없습니다."})
        if PASS and self.headers.get("x-app-passcode") != PASS:
            return self._json(401, {"error": "접속 암호가 맞지 않습니다."})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            msgs = body["messages"]
            assert isinstance(msgs, list) and 0 < len(msgs) <= MAX_MSGS
            assert all(m.get("role") in ("system", "user", "assistant") and isinstance(m.get("content"), str) for m in msgs)
        except Exception:  # noqa: BLE001
            return self._json(400, {"error": "메시지 형식이 올바르지 않습니다."})
        total = sum(len(m["content"]) for m in msgs)
        if total > MAX_CHARS:
            return self._json(413, {"error": f"입력이 너무 깁니다({total}자). 보낼 데이터 범위를 줄이세요."})
        req = urllib.request.Request(
            f"{BASE}/chat/completions", method="POST",
            data=json.dumps({"model": MODEL, "messages": msgs, "stream": True, "temperature": 0.2, "max_tokens": 2000}).encode("utf-8"),
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json", "X-Title": "RE Exposure Hub"})
        try:
            up = urllib.request.urlopen(req, timeout=120)
        except urllib.error.HTTPError as e:
            msg = {401: "API 키가 올바르지 않습니다.", 429: "무료 사용 한도에 걸렸습니다. 잠시 뒤 다시 시도하세요.",
                   404: f"모델을 찾지 못했습니다({MODEL})."}.get(e.code, f"모델 호출 실패({e.code}): {e.read()[:300].decode('utf-8', 'ignore')}")
            return self._json(e.code, {"error": msg})
        except Exception as e:  # noqa: BLE001
            return self._json(502, {"error": f"모델 서버에 연결하지 못했습니다: {e}"})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        with up:
            for chunk in iter(lambda: up.read1(4096) if hasattr(up, "read1") else up.read(4096), b""):
                self.wfile.write(chunk)
                self.wfile.flush()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8800)
    ap.add_argument("--host", default="127.0.0.1", help="사내 서버로 열 때 0.0.0.0")
    ap.add_argument("--html", default="public/index.html", help="제공할 화면 파일(시스템 폴더 기준)")
    a = ap.parse_args()
    Handler.html = a.html
    print(f"http://localhost:{a.port}  · 모델 {MODEL} · {BASE} · 키 {'있음' if KEY else '없음'} · 암호 {'있음' if PASS else '없음'}")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
