# -*- coding: utf-8 -*-
"""행정구역 보조자료 생성 → geo_data.json

입력(외부망에서 1회 다운로드):
  adm.geojson        : vuski/admdongkor ver20230701 행정동 경계 (시군구코드·행정동명·좌표)
  muni2018.topo.json : southkorea-maps kostat 2018 시군구 경계(topojson, 통계청 SGIS 공공누리 1유형)
출력:
  geo_data.json = {sgg:{코드:[시도,시군구,위도,경도]}, emd:{코드:[[행정동,위도,경도],...]}, topo:<시군구 경계, 속성 c=시군구코드>}
실행: python3 prep_geo.py <adm.geojson> <muni2018.topo.json> <출력 geo_data.json>
"""
import json, re, sys

adm_path, topo_path, out_path = sys.argv[1:4]


def ring_centroid(ring):
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        f = x0 * y1 - x1 * y0
        a += f; cx += (x0 + x1) * f; cy += (y0 + y1) * f
    if abs(a) < 1e-12:
        xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
        return sum(xs) / len(xs), sum(ys) / len(ys), 0.0
    return cx / (3 * a), cy / (3 * a), abs(a / 2)


def geom_centroid(g):
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    tot = sx = sy = 0.0
    for p in polys:
        x, y, a = ring_centroid(p[0])
        tot += a; sx += x * a; sy += y * a
    return (sx / tot, sy / tot, tot) if tot else (x, y, 0.0)


def spaced(n):  # "성남시분당구" → "성남시 분당구"
    return re.sub(r"^(\S+?시)(\S+구)$", r"\1 \2", n)


adm = json.load(open(adm_path, encoding="utf-8"))
sgg, emd, acc = {}, {}, {}
for f in adm["features"]:
    p = f["properties"]
    code = p["sgg"]
    x, y, a = geom_centroid(f["geometry"])
    name = p["adm_nm"].split()[-1]
    emd.setdefault(code, []).append([name, round(y, 4), round(x, 4)])
    s = acc.setdefault(code, [p["sidonm"], spaced(p["sggnm"]), 0.0, 0.0, 0.0])
    s[2] += a; s[3] += y * a; s[4] += x * a
for code, (sido, name, a, sy, sx) in acc.items():
    sgg[code] = [sido, name, round(sy / a, 4), round(sx / a, 4)]

# kostat 2018 시군구 경계 → 행정표준 시군구코드로 매칭 (시도 접두 + 이름)
KOSTAT_SIDO = {"11": "서울특별시", "21": "부산광역시", "22": "대구광역시", "23": "인천광역시", "24": "광주광역시",
               "25": "대전광역시", "26": "울산광역시", "29": "세종특별자치시", "31": "경기도", "32": "강원특별자치도",
               "33": "충청북도", "34": "충청남도", "35": "전라북도", "36": "전라남도", "37": "경상북도",
               "38": "경상남도", "39": "제주특별자치도"}
key = {(v[0], v[1].replace(" ", "")): k for k, v in sgg.items()}
by_name = {}
for k, v in sgg.items():
    by_name.setdefault(v[1].replace(" ", ""), []).append(k)
topo = json.load(open(topo_path, encoding="utf-8"))
obj = next(iter(topo["objects"].values()))
miss = []
for g in obj["geometries"]:
    p = g["properties"]
    n = p["name"].replace(" ", "")
    if p["code"][:2] == "23" and n == "남구":
        n = "미추홀구"  # 2018.7 인천 남구 → 미추홀구
    c = key.get((KOSTAT_SIDO[p["code"][:2]], n))
    if not c and len(by_name.get(n, [])) == 1:
        c = by_name[n][0]  # 예: 군위군(2023 경북→대구 편입)
    if not c:
        miss.append(p["name"])
    g["properties"] = {"c": c or ""}
topo["objects"] = {"sgg": obj}
print("시군구", len(sgg), "행정동", sum(map(len, emd.values())), "경계 미매칭", miss)
json.dump({"sgg": sgg, "emd": emd, "topo": topo}, open(out_path, "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))
