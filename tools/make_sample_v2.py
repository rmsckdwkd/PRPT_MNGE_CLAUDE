# -*- coding: utf-8 -*-
"""시스템 시연용 가상 데이터 2개월분(202608·202609) 생성.

기존 샘플_로우데이터_가상.xlsx 를 바탕으로 기획서 기능을 시연할 수 있게 보강한다.
  - 가격지표: 2023.01~기준월 월별 시계열 + 시도 지수(시군구코드 = 시도 2자리 + "000"). 이천시는 시군구 지수를 빼서 '대체 지수' 시연
  - 주담대 일부: 평가구분 감정평가, 평가일 = 실행일 → 지수조정 가치·LTV 시연
  - 주소정제 시연: 법정동코드·좌표 공란 + 비표준 주소, 좌표만 공란(대표점 표시)
  - 동가격프록시: 법정동×건물유형 ㎡당 평균가·표본수 (숨은 하락 동 2곳, 표본 부족 동 1곳)
  - KB_매매가격지수_가상_시계열.xlsx: 데이터허브식 가로형(행=월, 열=지역), 202610 포함 → 월 업데이트 시연
  - 202609 에만 의도적 오류 3건(법정동코드 9자리, 평가금액 누락, 배분비율 합 130%) → 점검사항 표시 확인용
모든 주소·금액·번호는 가상이다.

실행: python3 make_sample_v2.py   (작업 폴더의 샘플_로우데이터_가상.xlsx, regions.py 사용)
출력: ../샘플데이터/샘플_가상_202608.xlsx, 샘플_가상_202609.xlsx, 동가격프록시_가상_202301-202609.xlsx,
      KB_매매가격지수_가상_시계열.xlsx, sample_data.json(화면 내장용)
"""
import copy, json, math, random, re, sys
from datetime import date, datetime
from pathlib import Path
from openpyxl import load_workbook

HERE = Path(__file__).resolve().parent
WORK = HERE.parent.parent
sys.path.insert(0, str(WORK))
from regions import REGIONS  # noqa: E402
from utmk import to_utmk  # noqa: E402

# 현행 법정동코드표(prep_bjd.py 결과)로 샘플의 동 코드를 실제 코드로 맞춘다
BJ = json.loads((HERE / "geo_data.json").read_text(encoding="utf-8"))["bjd"]
BJE = {k: [x.split(":", 1) for x in v.split("|")] for k, v in BJ["e"].items()}
RENAME = {("41590", "동탄동"): "청계동", ("41117", "광교동"): "이의동"}  # 법정동이 아닌 이름(행정동·생활권) 교정


def real_code(sgg, emd):
    emd = RENAME.get((sgg, emd), emd)
    cands = [sgg] if sgg in BJ["s"] else list(BJ["al"].get(sgg, []))
    cands += [k for k in BJ["s"] if k[:4] == sgg[:4] and k not in cands]
    for c in cands:
        for t, n in BJE.get(c, []):
            if n == emd:
                return c + t, emd
    raise KeyError((sgg, emd))


# ---------------------------------------------------------------- 실제 주소 (OpenStreetMap, ODbL)
# data/osm_buildings.json : 샘플 시군구의 주소 있는 실제 건물(도로명·건물번호·좌표). 법정동은
#   서울 = 법정동 경계(data/서울_법정동경계_2015.json) 안에 드는지, 그 밖 = OSM 법정동 태그 → 가까운 행정동 이름 순으로 정한다.
OSM_PATH, SEOUL_PATH = HERE / "data" / "osm_buildings.json", HERE / "data" / "서울_법정동경계_2015.json"
GEO_EMD = json.loads((HERE / "geo_data.json").read_text(encoding="utf-8"))["emd"]


def _in_ring(x, y, ring):
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


SEOUL = []
if SEOUL_PATH.exists():
    for f in json.loads(SEOUL_PATH.read_text(encoding="utf-8"))["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        xs = [p[0] for poly in polys for p in poly[0]]; ys = [p[1] for poly in polys for p in poly[0]]
        SEOUL.append((f["properties"]["EMD_CD"] + "00", polys, (min(xs), min(ys), max(xs), max(ys))))


ALL_EMD = [(sgg, e[0], e[1], e[2]) for sgg, lst in GEO_EMD.items() for e in lst]   # 2023 행정동 대표점 전체


def seoul_poly(b):
    for code, polys, (x0, y0, x1, y1) in SEOUL:
        if x0 <= b["lng"] <= x1 and y0 <= b["lat"] <= y1 and any(_in_ring(b["lng"], b["lat"], poly[0]) for poly in polys):
            return code
    return None


def nearest_emd(b):
    return min(ALL_EMD, key=lambda e: (e[2] - b["lat"]) ** 2 + (e[3] - b["lng"]) ** 2)


def legal_dong(reg, b):
    """실제 건물 → (법정동코드 10자리, 법정동명) 또는 None.  ① OSM 법정동 태그 ② 서울 법정동 경계 ③ 가장 가까운 행정동 이름"""
    cands = [reg["sgg"]] if reg["sgg"] in BJ["s"] else list(BJ["al"].get(reg["sgg"], []))
    cands += [k for k in BJ["s"] if k[:4] == cands[0][:4] and k not in cands]
    name_of = {c + t: n for c, t2 in ((c, BJE.get(c, [])) for c in cands) for t, n in t2}
    if b.get("sub"):
        hit = [c for c, n in name_of.items() if n == b["sub"]]
        if hit:
            return hit[0], b["sub"]
    if reg["sgg"].startswith("11") and SEOUL:
        code = seoul_poly(b)
        return (code, name_of[code]) if code in name_of else None
    sgg, near = nearest_emd(b)[:2]
    if sgg != reg["sgg"]:
        return None
    base = re.sub(r"[0-9.·]+(?=동$)", "", near)
    hit = [c for c, n in name_of.items() if n == base or n == near]
    return (hit[0], name_of[hit[0]]) if hit else None


def osm_pool(reg):
    toks = reg["sigungu"].split()
    out = []
    for b in OSM.get(reg["sgg"], []):
        city, dist = b.get("city") or "", b.get("district") or ""
        if city or dist:      # 태그가 있으면 이름으로 소속 확인, 없으면 위치(법정동 판정)로 확인
            ok = (city.startswith("세종") if reg["sgg"] == "36110" else
                  (city == toks[0] and (not dist or dist == toks[1])) if len(toks) == 2 else (dist == toks[0] or (not dist and city == toks[0])))
            if not ok:
                continue
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", (b.get("hn") or "").strip())
        if not m or not b.get("street"):
            continue
        ld = legal_dong(reg, b)
        if not ld:
            continue
        nm = b.get("name") or ""
        if not re.search(r"[가-힣]{2,}", nm) or re.fullmatch(r"[0-9A-Za-z가-힣\s-]*\d+\s*동", nm):
            nm = ""                                    # '102', '107동' 같은 동 번호는 단지명으로 쓰지 않음
        b = dict(b, name=nm)
        kind = ("오피스텔" if "오피스텔" in nm else "연립" if b["b"] in ("residential", "terrace") or re.search(r"빌라|맨션|빌$|다세대|연립|하우스", nm)
                else "아파트" if b["b"] == "apartments" else "단독" if b["b"] in ("house", "detached") else "상업")
        out.append(dict(b, main=int(m.group(1)), subn=int(m.group(2) or 0), code=ld[0], emd=ld[1], kind=kind))
    return out


OSM = json.loads(OSM_PATH.read_text(encoding="utf-8")) if OSM_PATH.exists() else {}

random.seed(26)
SRC = WORK / "샘플_로우데이터_가상.xlsx"
OUT = HERE.parent / "샘플데이터"
DATA_SHEETS = ["1_주택담보대출", "2_투자부동산", "3_주택연금"]


def codes(ws):
    return [str(c.value).split("\n")[-1].strip() if c.value else None for c in ws[3]]


def read(ws):
    cs = codes(ws)
    out = []
    for row in ws.iter_rows(min_row=4, values_only=True):
        rec = {k: v for k, v in zip(cs, row) if k and v not in (None, "") and not str(v).startswith("=")}
        if rec.get("EXPO_ID") or rec.get("SGG_CD"):
            out.append(rec)
    return out


def months(y0, m0, y1, m1):
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        yield f"{y}{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


ALL_M = list(months(2023, 1, 2026, 9))

# ---------------------------------------------------------------- 가격지수 시계열
wb0 = load_workbook(SRC, data_only=False)
base = {str(r["SGG_CD"]): r["IDX_VAL"] for r in read(wb0["4_가격지표"]) if str(r["BASE_YM"]) == "202609"}
series = {}
for reg in REGIONS:
    now = base.get(reg["sgg"], 100.0)
    rets = {}
    last12 = ALL_M[-12:]
    rets[last12[-1]] = math.log(1 + reg["mom"])
    rest = math.log(1 + reg["yoy"]) - rets[last12[-1]]
    w = [1 + random.uniform(-0.25, 0.25) for _ in range(11)]
    for ym, wi in zip(last12[:-1], w):
        rets[ym] = rest * wi / sum(w)
    for ym in ALL_M[:-12]:
        rets[ym] = random.gauss(0.002, 0.004)
    v, s = now, {}
    for ym in reversed(ALL_M):
        s[ym] = round(v, 2)
        v = v / math.exp(rets[ym])
    series[reg["sgg"]] = s
SIDO = {}
for reg in REGIONS:
    SIDO.setdefault((reg["sgg"][:2], reg["sido"]), []).append(reg["sgg"])
sido_series = {f"{k[0]}000": (k[1], {ym: round(sum(series[c][ym] for c in v) / len(v), 2) for ym in ALL_M})
               for k, v in SIDO.items()}
NO_SGG_INDEX = {"41500"}  # 이천시: 시군구 지수 미제공 → 경기도 지수로 대체


def price_rows(upto):
    rows = []
    for reg in REGIONS:
        if reg["sgg"] in NO_SGG_INDEX:
            continue
        for ym in ALL_M:
            if ym <= upto:
                rows.append(dict(BASE_YM=ym, SGG_CD=reg["sgg"], SIDO=reg["sido"], SIGUNGU=reg["sigungu"],
                                 IDX_SRC="KB 월간 매매가격지수(가상)", IDX_TYPE="아파트", IDX_VAL=series[reg["sgg"]][ym]))
    for cd, (sido, s) in sido_series.items():
        for ym in ALL_M:
            if ym <= upto:
                rows.append(dict(BASE_YM=ym, SGG_CD=cd, SIDO=sido, SIGUNGU="(시도 전체)",
                                 IDX_SRC="KB 월간 매매가격지수(가상)", IDX_TYPE="아파트", IDX_VAL=s[ym]))
    return rows


# ---------------------------------------------------------------- 202609 보강
data = {s: read(wb0[s]) for s in DATA_SHEETS}
mort = data["1_주택담보대출"]
for r in mort:
    ex = r["EXEC_DT"]
    if isinstance(ex, datetime) and ex.date() >= date(2023, 2, 1) and random.random() < 0.45 and r["BJD_CD"][:5] in series:
        ym = ex.strftime("%Y%m")
        r["APPR_SRC"], r["APPR_DT"] = "감정평가", ex
        r["APPR_AMT"] = int(r["APPR_AMT"] * series[r["BJD_CD"][:5]][ym] / series[r["BJD_CD"][:5]]["202609"] / 1e6) * 1e6

by_id = {r["EXPO_ID"]: r for r in mort}
GEO = ("BJD_CD", "SIDO", "SIGUNGU", "EMD", "LAT", "LNG")
# 주소정제 시연: 법정동코드·좌표 없이 비표준 주소만 있는 건
for eid, addr in (("LN-0030", "서울시 송파구 가상로12길 34 (잠실동) 101동 1203호"),
                  ("LN-0031", "경기 성남시 분당구 정자동 123-4 가상아파트 201동 502호"),
                  ("LN-0032", "부산 해운대구  우동 1407  ")):
    r = by_id[eid]
    for k in GEO:
        r.pop(k, None)
    r["ROAD_ADDR"], r["REMARK"] = addr, "[시연] 법정동코드·좌표 미부여 → 주소정제"
hp_unmatched = data["3_주택연금"][-1]
for k in GEO:
    hp_unmatched.pop(k, None)
hp_unmatched["ROAD_ADDR"], hp_unmatched["REMARK"] = "가상도 가상군 미확인리 12", "[시연] 주소 미매칭"

# 도로명주소만 입력하는 운영 방식 재현: 지역 칸(법정동코드·시도·시군구·읍면동·좌표)은 비우고 도로명주소만 남긴다
ADDR_DICT = []          # 도로명주소 사전 (행안부 주소DB 형식 흉내: 좌표는 UTM-K)
USED = {}               # 담보가 있는 법정동 → (지역, 법정동명) — 동 가격 프록시 생성 대상
NO_NUM = {"LN-0050", "LN-0051", "HP-0010"}   # 사전에 그 건물이 없는 건 → 도로·참고항목으로 처리되는지 시연
LEGACY = {"29140"}                           # 옛 시도명(광주광역시)으로 쓴 주소 → 현행 코드 변환 시연
SKIP = {"LN-0030", "LN-0031", "LN-0032"}     # 주소정제 시연 행(약칭·지번·괄호)은 그대로
WANT = {"아파트": ["아파트", "연립"], "연립·다세대": ["연립", "아파트"], "단독·다가구": ["단독", "연립"], "오피스텔": ["오피스텔", "상업", "아파트"],
        "오피스": ["상업", "오피스텔"], "상가": ["상업"], "물류": ["상업", "단독"], "호텔": ["상업"]}
if OSM:
    pools = {reg["sgg"]: osm_pool(reg) for reg in REGIONS}
    print("실제 주소 건물(법정동 확정)", {k: len(v) for k, v in pools.items()})
    taken = set()
    for sheet in DATA_SHEETS:
        for r in data[sheet]:
            if not r.get("BJD_CD") or r["EXPO_ID"] in SKIP:
                continue
            reg = next(x for x in REGIONS if x["sgg"] == str(r["BJD_CD"])[:5])
            pool = pools[reg["sgg"]]
            cand = []
            for k in WANT.get(r["RE_TYPE"], ["아파트"]):
                cand = [b for b in pool if b["kind"] == k and (b["street"], b["main"], b["subn"]) not in taken]
                if cand:
                    break
            b = random.choice(cand or pool)
            taken.add((b["street"], b["main"], b["subn"]))
            code = b["code"]; sido, sggn = BJ["s"][code[:5]][:2]
            hn = f'{b["main"]}-{b["subn"]}' if b["subn"] else str(b["main"])
            addr_sido, addr_sgg = (reg["sido"], reg["sigungu"]) if reg["sgg"] in LEGACY and random.random() < 0.5 else (sido, sggn)
            ref = ""
            if b["kind"] == "아파트" and random.random() < 0.5:                 # 공동주택 도로명주소의 괄호 참고항목
                ref = f' ({b["emd"]}, {b["name"]})' if b.get("name") else f' ({b["emd"]})'
            r["ROAD_ADDR"] = " ".join(x for x in (addr_sido, "" if code[:5] == "36110" else addr_sgg, b["street"], hn) if x) + ref
            if sheet == "1_주택담보대출" and b.get("name") and b["kind"] == "아파트":
                r["RE_NM"] = f'{b["name"]} {random.randint(101, 115)}동 {random.randint(2, 25)}0{random.randint(1, 4)}호'
            if r["EXPO_ID"] in NO_NUM:
                b["skip"] = True
            r["BJD_CD"], r["EMD"] = code, b["emd"]
            USED[code] = (reg, b["emd"])
    for reg in REGIONS:                                        # 사전 = 받은 실제 건물 전체 (담보 없는 건물 포함)
        for b in pools[reg["sgg"]]:
            if b.get("skip"):
                continue
            x, y = to_utmk(b["lat"], b["lng"])
            ADDR_DICT.append([b["code"][:5], b["code"], *BJ["s"][b["code"][:5]][:2], b["emd"], b["street"], 0, b["main"], b["subn"], round(x, 2), round(y, 2)])
else:
    NO_NUM = {"LN-0050", "LN-0051", "HP-0010"}   # 사전에 건물번호가 없는 건 → 도로 단위로 동 확정
    LEGACY = {"29140"}                           # 옛 시도명(광주광역시)으로 쓴 주소 → 현행 코드 변환 시연
    roads_seen = {}
    for sheet in DATA_SHEETS:
        for r in data[sheet]:
            if not r.get("BJD_CD") or r.get("LAT") is None:
                continue
            old_sgg = str(r["BJD_CD"])[:5]
            code, emdn = real_code(old_sgg, r["EMD"])
            sido, sggn = BJ["s"][code[:5]][:2]
            reg = next(x for x in REGIONS if x["sgg"] == old_sgg)
            ei = [e[0] for e in reg["emd"]].index(r["EMD"])
            road = f"가상로{ei * 30 + random.randint(1, 30)}길"
            num = random.randint(1, 300)
            addr_sido, addr_sgg = (reg["sido"], reg["sigungu"]) if old_sgg in LEGACY and random.random() < 0.5 else (sido, sggn)
            r["ROAD_ADDR"] = " ".join(x for x in (addr_sido, "" if code[:5] == "36110" else addr_sgg, road, str(num)) if x)
            if r["EXPO_ID"] not in NO_NUM:
                x, y = to_utmk(r["LAT"], r["LNG"])
                ADDR_DICT.append([code[:5], code, sido, sggn, emdn, road, 0, num, 0, round(x, 2), round(y, 2)])
            roads_seen.setdefault((code, road), set()).add(num)
            r["BJD_CD"], r["EMD"] = code, emdn
    for (code, road), nums in roads_seen.items():       # 같은 도로의 다른 건물들 (사전에는 있고 담보는 없는 건물)
        for _ in range(3):
            n = random.randint(301, 400)
            x, y = to_utmk(*next((reg["lat"], reg["lng"]) for reg in REGIONS if reg["sgg"][:4] == code[:4] or reg["sgg"] in BJ["old"].get(code[:5], [])))
            ADDR_DICT.append([code[:5], code, *BJ["s"][code[:5]][:2], next(n2 for t, n2 in BJE[code[:5]] if code[:5] + t == code), road, 0, n, 0, round(x + random.uniform(-300, 300), 2), round(y + random.uniform(-300, 300), 2)])
for sheet in DATA_SHEETS:
    for r in data[sheet]:
        if r["EXPO_ID"] in ("LN-0030", "LN-0031", "LN-0032"):
            continue
        for k in ("BJD_CD", "SIDO", "SIGUNGU", "EMD", "LAT", "LNG"):
            r.pop(k, None)
print("도로명주소 사전", "(OSM 실제 주소)" if OSM else "(가상)", len(ADDR_DICT), "건")

sep = copy.deepcopy(data)
m9 = sep["1_주택담보대출"]
b9 = {r["EXPO_ID"]: r for r in m9}
b9["LN-0007"]["BJD_CD"] = "116801010"
b9["LN-0007"]["REMARK"] = "[시연 오류] 법정동코드 9자리"
b9["LN-0015"].pop("APPR_AMT")
b9["LN-0015"]["REMARK"] = "[시연 오류] 평가금액 누락"
extra = copy.deepcopy(b9["LN-0021"])
extra.update(RE_SEQ=2, ALLOC_RATIO=0.3, RE_NM="가상 공동담보 2번 물건", REMARK="[시연 오류] 배분비율 합 130%")
m9.insert(m9.index(b9["LN-0021"]) + 1, extra)

# ---------------------------------------------------------------- 202608 (전월) 스냅샷
aug = copy.deepcopy(data)
NEW_IN_SEP = {f"LN-{n:04d}" for n in range(236, 241)}
aug["1_주택담보대출"] = [r for r in aug["1_주택담보대출"] if r["EXPO_ID"] not in NEW_IN_SEP]
for sheet in aug.values():
    for r in sheet:
        r["BASE_YM"] = "202608"
for r in aug["1_주택담보대출"]:
    r["BAL_AMT"] = int(r["BAL_AMT"] * 1.0035 / 1e5) * 1e5
    if r.get("APPR_SRC") == "KB시세":
        s = series.get(str(r.get("BJD_CD", ""))[:5])
        if s:
            r["APPR_AMT"] = int(r["APPR_AMT"] * s["202608"] / s["202609"] / 1e6) * 1e6
        r["APPR_DT"] = datetime(2026, 8, 31)
for r in aug["3_주택연금"]:
    r["PAID_CUM"] -= r["MONTHLY_PAY"]
    r["INT_CUM"] = int(r["INT_CUM"] * 0.97)
    r["APPR_DT"] = datetime(2026, 8, 31)

# ---------------------------------------------------------------- 저장
OUT.mkdir(exist_ok=True)


def write(ws, recs):
    cs = codes(ws)
    for row in ws.iter_rows(min_row=4, max_row=ws.max_row):
        for c in row:
            if not str(c.value or "").startswith("="):
                c.value = None
    for i, rec in enumerate(recs):
        for j, code in enumerate(cs, start=1):
            if code in rec:
                ws.cell(row=4 + i, column=j).value = rec[code]


bundle = {}
for ym, d in (("202608", aug), ("202609", sep)):
    wb = load_workbook(SRC)
    for s in DATA_SHEETS:
        write(wb[s], d[s])
    pr = price_rows(ym)
    ws = wb["4_가격지표"]
    for row in ws.iter_rows(min_row=4, max_row=ws.max_row, max_col=7):
        for c in row:
            c.value = None
    write(ws, pr)
    p = OUT / f"샘플_가상_{ym}.xlsx"
    wb.save(p)
    bundle[ym] = {**d, "4_가격지표": pr}
    print(p.name, {s: len(d[s]) for s in DATA_SHEETS}, "가격지표", len(pr))


# ---------------------------------------------------------------- 동 단위 가격 프록시 (확정 아님)
# 법정동 × 건물유형별 ㎡당 평균가격 + 표본수. 시군구 지수 흐름에 동별 추세·표본 잡음을 더해 만든다.
# 숨은 하락 시연: 시군구 지수는 오르는데 해당 동만 내리는 곳 2곳, 표본이 적은 동 1곳
PX_TYPES = [("아파트", 1.0, 8, 40), ("연립·다세대", 0.55, 2, 12), ("오피스텔", 0.6, 1, 8), ("단독·다가구", 0.5, 0, 4)]
SPECIAL = {("11710", "문정동", "아파트"): -0.0075, ("41135", "정자동", "아파트"): -0.006, ("11500", "화곡동", "연립·다세대"): -0.012}
dong = []
TARGETS = {}
for reg in REGIONS:
    for emd, _, _, tail in reg["emd"]:
        rc, rn = real_code(reg["sgg"], emd)
        TARGETS[rc] = (reg, rn)
for code, (reg, rn) in USED.items():
    TARGETS.setdefault(code, (reg, rn))
for code, (reg, emd) in sorted(TARGETS.items()):
    s = series.get(reg["sgg"]) or sido_series[f'{reg["sgg"][:2]}000'][1]
    if True:
        for typ, fac, nlo, nhi in PX_TYPES:
            if typ == "단독·다가구" and random.random() < 0.5 or typ == "오피스텔" and random.random() < 0.4:
                continue
            drift = SPECIAL.get((reg["sgg"], emd, typ), random.gauss(0, 0.0012))
            base_ppm = reg["px"] / 84 * fac * random.uniform(0.85, 1.15)
            lo, hi = (1, 4) if (reg["sgg"], emd, typ) == ("11500", "화곡동", "연립·다세대") else (nlo, nhi)
            for i, ym in enumerate(ALL_M):
                n = random.randint(lo, hi)
                if n == 0:
                    continue
                idx = (s[ym] / s["202609"]) ** (0.7 if typ != "아파트" else 1)
                avg = base_ppm * idx * math.exp(drift * (i - len(ALL_M) + 1)) * (1 + random.gauss(0, 0.035 / math.sqrt(n)))
                rc, rn = code, emd
                dong.append(dict(BASE_YM=ym, BJD_CD=rc, SIDO=BJ["s"][rc[:5]][0], SIGUNGU=BJ["s"][rc[:5]][1], EMD=rn,
                                 PX_TYPE=typ, PX_AVG=int(round(avg, -3)), PX_UNIT="원/㎡", PX_CNT=n, PX_SRC="KB시세 단지평균(가상)"))
print("동 프록시", len(dong), "행")

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
HDR = [("기준년월", "BASE_YM"), ("법정동코드", "BJD_CD"), ("시도", "SIDO"), ("시군구", "SIGUNGU"), ("읍면동", "EMD"),
       ("건물유형", "PX_TYPE"), ("평균가격", "PX_AVG"), ("단위", "PX_UNIT"), ("표본수", "PX_CNT"), ("출처", "PX_SRC")]
wb = Workbook(); ws = wb.active; ws.title = "5_동가격프록시"
ws["A1"] = "[동 가격 프록시] 1행 = 기준월 × 법정동 × 건물유형 (확정 시세 아님, ㎡당 평균가 권장 · 표본수 필수)"
ws["A1"].font = Font(bold=True)
ws["A2"] = "평균가격은 같은 단위로 계속 입력(원/㎡ 권장). 표본수가 적은 동은 시스템이 시군구 지수와 섞거나 대체한다."
for j, (kr, en) in enumerate(HDR, 1):
    c = ws.cell(row=3, column=j, value=f"{kr}\n{en}"); c.font = Font(bold=True); c.fill = PatternFill("solid", fgColor="E4DFEC")
for i, r in enumerate(dong, 4):
    for j, (_, en) in enumerate(HDR, 1):
        ws.cell(row=i, column=j, value=r[en])
wb.save(OUT / "동가격프록시_가상_202301-202609.xlsx")

# KB 데이터허브식 가로형 시계열 (행 = 월, 열 = 시도/시군구 2단 머리글). 202610 한 달을 더 넣어 '월 업데이트' 시연
nxt = {cd: round(v["202609"] * (1 + next(r["mom"] for r in REGIONS if r["sgg"] == cd)), 2) for cd, v in series.items()}
wb = Workbook(); wb.remove(wb.active)
for sheet, damp in (("1.매매APT", 1.0), ("2.매매연립", 0.7)):
    ws = wb.create_sheet(sheet)
    ws["A1"] = f"KB 월간 {sheet[2:]} 매매가격지수 (가상, 2022.1=100 아님 · 시연용)"
    cols = []
    last_sido = None
    for reg in REGIONS:
        if reg["sgg"] in NO_SGG_INDEX:
            continue
        cols.append((reg["sido"], reg["sigungu"], reg["sgg"]))
    for cd, (sido, _) in sido_series.items():
        cols.append((sido, "", cd))
    cols.sort(key=lambda c: (c[2][:2], c[1] != "", c[1]))
    short = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주",
             "대전광역시": "대전", "세종특별자치시": "세종", "경기도": "경기", "제주특별자치도": "제주"}
    prev = None
    for j, (sido, sgg, cd) in enumerate(cols, 2):
        if sido != prev:
            ws.cell(row=2, column=j, value=short.get(sido, sido)); prev = sido  # 병합셀처럼 첫 칸에만 시도명
        ws.cell(row=3, column=j, value=sgg or short.get(sido, sido))
    ws.cell(row=3, column=1, value="구분")
    for i, ym in enumerate(ALL_M + ["202610"], 4):
        ws.cell(row=i, column=1, value=f"{ym[:4]}.{ym[4:]}")
        for j, (_, _, cd) in enumerate(cols, 2):
            if cd in series:
                v = nxt[cd] if ym == "202610" else series[cd][ym]
            else:
                ss = sido_series[cd][1]
                v = ss["202609"] * 1.001 if ym == "202610" else ss[ym]
            base = (series.get(cd) or sido_series[cd][1])["202609"]
            ws.cell(row=i, column=j, value=round(base * (v / base) ** damp, 2))
wb.save(OUT / "KB_매매가격지수_가상_시계열.xlsx")


def enc(o):
    return o.strftime("%Y-%m-%d") if isinstance(o, (date, datetime)) else str(o)


bundle["_px"] = {"dong": dong}
bundle["_addr"] = {"rows": [dict(zip(["시군구코드", "법정동코드", "시도명", "시군구명", "법정읍면동명", "도로명", "지하여부", "건물본번", "건물부번", "X좌표", "Y좌표"], r)) for r in ADDR_DICT]}
DICT_NAME = "도로명주소사전_OSM시험용_주소DB형식.txt" if OSM else "도로명주소사전_가상_주소DB형식.txt"
for old in OUT.glob("도로명주소사전_*_주소DB형식.txt"):
    old.unlink()
with open(OUT / DICT_NAME, "w", encoding="cp949", errors="replace") as f:   # 실제 주소DB처럼 머리글 없는 | 구분 · CP949
    for r in ADDR_DICT:
        f.write("|".join(str(v) for v in [r[0], r[1], r[2], r[3], r[4], "", r[5], r[6], r[7], r[8], "", r[9], r[10]]) + "\n")
json.dump(bundle, open(HERE / "sample_data.json", "w", encoding="utf-8"), ensure_ascii=False,
          separators=(",", ":"), default=enc)
