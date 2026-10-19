# -*- coding: utf-8 -*-
"""웹앱 핵심 로직 추출 → 텍스트 파일 1개 (Python 표준 라이브러리만 사용).

  대상 : src/app.html 의 인라인 <script> 블록(화면 계산·처리 로직 전체) + api/chat.js(AI 질문 중계 서버 함수)
  제외 : <style> 블록(화면 디자인/스타일), HTML 화면 골격, 외부 라이브러리(Leaflet·SheetJS·topojson),
         빌드 때 끼워 넣는 내장 자료(행정구역 경계·샘플 — 원본에는 자리표시자만 있음)
  원칙 : 코드는 새로 쓰거나 고치거나 줄이지 않고 원본 그대로 옮긴다.
         인증정보로 보이는 문자열이 있으면 실제 값만 [인증정보 제외]로 바꾸고 바꾼 위치를 머리말에 남긴다.

실행: python3 tools/extract_logic.py                 → 저장소 최상단에 핵심로직_추출_YYYYMMDD.txt
      python3 tools/extract_logic.py --out 파일명.txt
"""
import argparse
import hashlib
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = [
    ("src/app.html", "html"),   # 인라인 <script>만 추출
    ("api/chat.js", "js"),      # 파일 전체
]
# 인증정보로 보이는 실제 값 (환경변수 이름·빈 기본값은 해당 없음)
SECRET_PATTERNS = [
    re.compile(r"sk-or-v1-[0-9a-f]{20,}"),                       # OpenRouter
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),                   # Anthropic
    re.compile(r"(?<![0-9A-Za-z])[0-9a-f]{64}(?![0-9A-Za-z])"),  # data.go.kr Decoding 키 등 64자리 16진
    re.compile(r"[A-Za-z0-9%+/]{80,}={0,2}"),                    # data.go.kr Encoding 키 등 긴 토큰
    re.compile(r"(?i)(serviceKey|api[_-]?key|passcode|password)\s*[=:]\s*[\"']([^\"'\s]{8,})[\"']"),
]
MASK = "[인증정보 제외]"


def scripts_of(html):
    """src 속성이 없는 <script> 블록의 안쪽 내용을 원문 그대로, 시작 줄 번호와 함께."""
    out = []
    for m in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S):
        out.append((html.count("\n", 0, m.start(1)) + 1, m.group(1)))
    return out


def mask(text):
    hits = []
    def sub(m):
        if m.re.groups >= 2:     # 키=값 꼴은 값만 가림
            hits.append(m.group(2)[:4] + "…")
            return m.group(0).replace(m.group(2), MASK)
        hits.append(m.group(0)[:4] + "…")
        return MASK
    for p in SECRET_PATTERNS:
        text = p.sub(sub, text)
    return text, hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / f"핵심로직_추출_{datetime.now():%Y%m%d}.txt"))
    a = ap.parse_args()
    parts, report = [], []
    for rel, kind in SOURCES:
        src = (ROOT / rel).read_text(encoding="utf-8")
        blocks = scripts_of(src) if kind == "html" else [(1, src)]
        for line, code in blocks:
            body, hits = mask(code)
            report.append(f"  - {rel} (원본 {line}행부터, {code.count(chr(10)) + 1}줄, SHA-256 {hashlib.sha256(code.encode('utf-8')).hexdigest()[:16]})"
                          + (f" · 인증정보 {len(hits)}곳 제외" if hits else " · 인증정보 없음"))
            parts.append(f"{'=' * 78}\n# 파일: {rel}  (원본 {line}행부터)\n{'=' * 78}\n{body.strip(chr(10))}\n")
    head = (f"부동산 통합 익스포저 관리 — 핵심 로직 추출본\n"
            f"추출 일시: {datetime.now():%Y-%m-%d %H:%M}\n"
            f"추출 도구: tools/extract_logic.py (원본 코드를 고치지 않고 그대로 옮김, 화면 디자인/스타일·외부 라이브러리·내장 자료 제외)\n"
            f"수록 범위:\n" + "\n".join(report) + "\n\n")
    Path(a.out).write_text(head + "\n".join(parts), encoding="utf-8")
    print(f"{a.out}\n" + "\n".join(report))


if __name__ == "__main__":
    main()
