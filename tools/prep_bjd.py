# -*- coding: utf-8 -*-
"""법정동코드 전체자료(행정표준코드관리시스템) → geo_data.json 에 현행 코드표·구코드 변환표 추가.

입력: data/법정동코드_전체자료_YYYYMMDD.txt (탭 구분: 법정동코드, 법정동명, 폐지여부 / UTF-8 또는 CP949)
      geo_data.json (prep_geo.py 결과: 2023 시군구·행정동 대표점, 2018 경계)
출력: geo_data.json 의 "bjd" 항목
  s  : {현행 시군구코드: [시도명, 시군구명, 위도, 경도, 상위시 여부]}
  e  : {현행 시군구코드: "끝5자리:읍면동명|끝5자리:읍면동명 리명|..."}
  al : {폐지 시군구코드: [현행 시군구코드, ...]}   (읍면동 이름이 겹치는 정도로 판정 — 통합·분할 대응)
  old: {현행 시군구코드: [대표점·행정동 자료가 있는 2023 시군구코드, ...]}
  ver: 코드표 기준일
실행: python3 prep_bjd.py data/법정동코드_전체자료_20261014.txt
코드표는 행정구역이 바뀔 때마다(연 수회) 새로 받아 다시 실행한다.
"""
import json, re, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
src = Path(sys.argv[1])
raw = src.read_bytes()
try:
    text = raw.decode("utf-8")
except UnicodeDecodeError:
    text = raw.decode("cp949")
rows = [l.split("\t") for l in text.splitlines()[1:] if l.strip()]
T = {c: (n.strip(), st.strip()) for c, n, st in rows}
alive = {c: n for c, (n, st) in T.items() if st == "존재"}

geo = json.loads((HERE / "geo_data.json").read_text(encoding="utf-8"))
G = geo["sgg"]  # 2023 시군구 대표점

sido_name = {c[:2]: n for c, n in alive.items() if c[2:] == "00000000"}
sgg_alive = {c[:5]: n for c, n in alive.items() if c[5:] == "00000" and c[2:5] != "000"}
emd = defaultdict(list)
for c, n in alive.items():
    if c[5:] == "00000":
        continue
    parts = n.split()
    sgg = c[:5]
    base = sgg_alive.get(sgg, "")
    rest = n[len(base):].strip() if base and n.startswith(base) else " ".join(parts[2:])
    emd[sgg].append(f"{c[5:]}:{rest}")

def names_under(prefix5, table):
    out = set()
    for c, (n, st) in table.items():
        if c[:5] == prefix5 and c[5:] != "00000" and c[8:] == "00":
            out.add(n.split()[-1])
    return out

# 폐지 시군구 → 현행 시군구 (읍면동 이름 겹침, 같은 시도 계열 안에서)
FAMILY = {"29": "12", "46": "12", "45": "52", "42": "51"}
dead = [c for c in G if c not in sgg_alive]
for c, (n, st) in T.items():           # 그 밖의 최근 폐지 시군구 (예: 인천 남구 28170)
    if st == "폐지" and c[5:] == "00000" and c[2:5] != "000" and c[:2] in ("28", "41", "29", "46", "45", "42") :
        if c[:5] not in dead and c[:5] not in sgg_alive:
            dead.append(c[:5])
alive_names = {s: names_under(s, {k: (v, "존재") for k, v in alive.items()}) for s in sgg_alive}
al = {}
for o in dead:
    on = names_under(o, T)
    if not on:
        continue
    fam = FAMILY.get(o[:2], o[:2])
    cands = []
    for s, sn in alive_names.items():
        if s[:2] not in (fam, o[:2]) or not sn:
            continue
        ov = len(on & sn)
        if ov and ov / len(on) >= 0.15:
            cands.append((ov, s))
    cands.sort(reverse=True)
    if cands:
        al[o] = [s for _, s in cands]

old = defaultdict(list)
for o, news in al.items():
    if o in G:
        for s in news:
            old[s].append(o)
for s in sgg_alive:
    if s in G:
        old[s].insert(0, s)
    elif not old[s] and s[:4] + "0" in G:            # 신설 구 → 상위 시 (예: 화성시 동탄구 → 화성시)
        old[s].append(s[:4] + "0")
    elif not old[s]:
        kids = [g for g in G if g[:4] == s[:4] and g != s]   # 상위 시 → 소속 구들
        old[s].extend(kids)

S = {}
for s, n in sgg_alive.items():
    sido = sido_name.get(s[:2], n.split()[0])
    sgg_nm = n[len(sido):].strip() if n.startswith(sido) else " ".join(n.split()[1:])
    sgg_nm = sgg_nm or "세종시"                      # 시군구가 없는 세종특별자치시
    pts = [G[o] for o in old.get(s, []) if o in G]
    lat = round(sum(p[2] for p in pts) / len(pts), 4) if pts else None
    lng = round(sum(p[3] for p in pts) / len(pts), 4) if pts else None
    is_city = 1 if any(k[:4] == s[:4] and k != s for k in sgg_alive) and s[4] == "0" else 0
    S[s] = [sido, sgg_nm, lat, lng, is_city]

for s, v in S.items():                 # 상위 시인데 대표점이 없으면 소속 구 평균
    if v[2] is None:
        kids = [S[k] for k in S if k[:4] == s[:4] and k != s and S[k][2] is not None]
        if kids:
            v[2] = round(sum(k[2] for k in kids) / len(kids), 4); v[3] = round(sum(k[3] for k in kids) / len(kids), 4)

geo["bjd"] = {"s": S, "e": {k: "|".join(v) for k, v in emd.items()}, "al": al,
              "old": {k: v for k, v in old.items() if v}, "ver": re.sub(r"\D", "", src.stem)[-8:]}
(HERE / "geo_data.json").write_text(json.dumps(geo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("현행 시군구", len(S), "읍면동·리", sum(len(v) for v in emd.values()), "변환", len(al))
for o in ("29140", "28110", "28170", "45111", "41590"):
    print(" ", o, G.get(o, [None, None])[:2], "→", al.get(o), [S[x][:2] for x in al.get(o, [])])
print("  미대표점", [k for k, v in S.items() if v[2] is None])
