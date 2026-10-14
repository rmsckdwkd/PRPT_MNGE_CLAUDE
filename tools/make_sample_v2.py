# -*- coding: utf-8 -*-
"""시스템 시연용 가상 데이터 2개월분(202608·202609) 생성.

기존 샘플_로우데이터_가상.xlsx 를 바탕으로 기획서 기능을 시연할 수 있게 보강한다.
  - 가격지표: 2023.01~기준월 월별 시계열 + 시도 지수(시군구코드 = 시도 2자리 + "000"). 이천시는 시군구 지수를 빼서 '대체 지수' 시연
  - 주담대 일부: 평가구분 감정평가, 평가일 = 실행일 → 지수조정 가치·LTV 시연
  - 주소정제 시연: 법정동코드·좌표 공란 + 비표준 주소, 좌표만 공란(대표점 표시)
  - 202609 에만 의도적 오류 3건(법정동코드 9자리, 평가금액 누락, 배분비율 합 130%) → 점검사항 표시 확인용
모든 주소·금액·번호는 가상이다.

실행: python3 make_sample_v2.py   (작업 폴더의 샘플_로우데이터_가상.xlsx, regions.py 사용)
출력: ../샘플데이터/샘플_가상_202608.xlsx, 샘플_가상_202609.xlsx, sample_data.json(화면 내장용)
"""
import copy, json, math, random, sys
from datetime import date, datetime
from pathlib import Path
from openpyxl import load_workbook

HERE = Path(__file__).resolve().parent
WORK = HERE.parent.parent
sys.path.insert(0, str(WORK))
from regions import REGIONS  # noqa: E402

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
# 좌표만 없는 건 → 대표점 표시
for eid in ("LN-0040", "LN-0041", "LN-0042", "LN-0043"):
    by_id[eid].pop("LAT"); by_id[eid].pop("LNG")
    by_id[eid]["REMARK"] = "[시연] 좌표 미부여 → 대표점"
hp_unmatched = data["3_주택연금"][-1]
for k in GEO:
    hp_unmatched.pop(k, None)
hp_unmatched["ROAD_ADDR"], hp_unmatched["REMARK"] = "가상도 가상군 미확인리 12", "[시연] 주소 미매칭"

sep = copy.deepcopy(data)
m9 = sep["1_주택담보대출"]
b9 = {r["EXPO_ID"]: r for r in m9}
b9["LN-0007"]["BJD_CD"] = b9["LN-0007"]["BJD_CD"][:9]
b9["LN-0007"]["REMARK"] = "[시연 오류] 법정동코드 9자리"
b9["LN-0015"].pop("APPR_AMT")
b9["LN-0015"]["REMARK"] = "[시연 오류] 평가금액 누락"
extra = copy.deepcopy(b9["LN-0021"])
extra.update(RE_SEQ=2, ALLOC_RATIO=0.3, RE_NM="가상 공동담보 2번 물건", REMARK="[시연 오류] 배분비율 합 130%")
extra["LAT"] = round(extra["LAT"] + 0.004, 6)
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


def enc(o):
    return o.strftime("%Y-%m-%d") if isinstance(o, (date, datetime)) else str(o)


json.dump(bundle, open(HERE / "sample_data.json", "w", encoding="utf-8"), ensure_ascii=False,
          separators=(",", ":"), default=enc)
