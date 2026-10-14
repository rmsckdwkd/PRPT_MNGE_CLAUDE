# -*- coding: utf-8 -*-
"""src/app.html → 배포 파일 2종 생성 (Python 표준 라이브러리만 사용).

  ../부동산통합관리시스템_내부망.html : Leaflet·SheetJS·topojson·경계·샘플을 모두 내장한 단일 파일 (외부 요청 0건)
  ../web/부동산통합관리시스템.html    : 라이브러리는 CDN에서 불러오는 웹 버전 (Claude 아티팩트 게시용, 문서 골격 없음)
  ../public/index.html                : 웹 버전 + 문서 골격 (Vercel 배포 · tools/chat_server.py 용, AI 질문 사용 가능)

실행: python3 build.py           (같은 폴더의 geo_data.json, sample_data.json, lib/ 사용)
"""
import json
import re
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "src" / "app.html"
LIB = HERE / "lib"
JS_LIBS = ["leaflet.min.js", "leaflet.markercluster.js", "topojson.min.js", "xlsx.full.min.js"]
CSS_LIBS = ["leaflet.min.css", "MarkerCluster.css", "MarkerCluster.Default.css"]


def script_safe(text):
    return text.replace("</script", "<\\/script").replace("<!--", "<\\!--")


def skeleton(body):
    return ('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '</head>\n<body>\n' + body + '\n</body>\n</html>\n')


def compact_sample(raw):
    """{ym:{sheet:[rec]}} → {ym:{sheet:{c:[컬럼], r:[[값]]}}} (용량 축소)"""
    out = {}
    for ym, sheets in raw.items():
        out[ym] = {}
        for name, recs in sheets.items():
            cols = list(dict.fromkeys(k for r in recs for k in r))
            out[ym][name] = {"c": cols, "r": [[r.get(c) for c in cols] for r in recs]}
    return out


def main():
    html = SRC.read_text(encoding="utf-8")
    geo = json.loads((HERE / "geo_data.json").read_text(encoding="utf-8"))
    sample = compact_sample(json.loads((HERE / "sample_data.json").read_text(encoding="utf-8")))
    built = datetime.now().strftime("%Y-%m-%d %H:%M")
    dump = lambda o: script_safe(json.dumps(o, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("/*__GEO__*/null", dump(geo)).replace("/*__SAMPLE__*/null", dump(sample))
    css = "\n".join((LIB / f).read_text(encoding="utf-8") for f in CSS_LIBS)
    html = html.replace("/*LIBCSS*/", css)

    # 웹 버전: CDN 블록 유지, 내장 표식 제거
    web = re.sub(r"<!--LIB:[^>]+-->", "", html).replace("<!--CDN-->\n", "").replace("<!--/CDN-->\n", "")
    web = web.replace("/*__BUILD__*/{offline:false,built:\"\"}", json.dumps({"offline": False, "built": built}))
    (ROOT / "web").mkdir(exist_ok=True)
    (ROOT / "web" / "부동산통합관리시스템.html").write_text(web, encoding="utf-8")
    # Vercel·로컬 챗봇 서버용: 웹 버전 + 문서 골격 (AI 질문은 /api/chat 이 있을 때만 켜짐)
    (ROOT / "public").mkdir(exist_ok=True)
    (ROOT / "public" / "index.html").write_text(skeleton(web), encoding="utf-8")

    # 내부망 버전: CDN 블록 삭제, 라이브러리 내장, 문서 골격 추가
    off = re.sub(r"<!--CDN-->.*?<!--/CDN-->\n", "", html, flags=re.S)
    for f in JS_LIBS:
        off = off.replace(f"<!--LIB:{f}-->", f"<script>{script_safe((LIB / f).read_text(encoding='utf-8'))}</script>\n")
    off = off.replace("/*__BUILD__*/{offline:false,built:\"\"}", json.dumps({"offline": True, "built": built}))
    # 외부 자원 자동 로드 여부 점검: src/href 로 외부 주소를 부르는 태그가 없어야 함 (배경지도 타일은 사용자가 고를 때만 요청)
    ext = re.findall(r"<(?:script|link|img)[^>]+(?:src|href)=[\"']https?://[^\"']+", off)
    print("내부망 버전 외부 자동 로드:", len(ext), "건", ext[:3])
    off = skeleton(off)
    out = ROOT / "부동산통합관리시스템_내부망.html"
    out.write_text(off, encoding="utf-8")
    for p in (out, ROOT / "web" / "부동산통합관리시스템.html", ROOT / "public" / "index.html"):
        print(f"{p.relative_to(ROOT)}  {p.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
