# -*- coding: utf-8 -*-
"""국토교통부 실거래가 API → 동 가격 프록시 파일(csv) — 외부망 PC에서 매월 실행.

공공데이터포털(data.go.kr)에서 아래 API를 활용신청해 받은 '일반 인증키'를 사용한다.
  아파트 매매       RTMSDataSvcAptTrade
  연립다세대 매매   RTMSDataSvcRHTrade
  오피스텔 매매     RTMSDataSvcOffiTrade
  단독/다가구 매매  RTMSDataSvcSHTrade
결과는 법정동 × 건물유형 × 계약월별 ㎡당 중위가격과 표본수이고, 시스템의
'가격지표 월별 업데이트 → 동 가격 프록시 파일'에 그대로 올린다.
보내는 값은 시군구코드와 계약년월뿐이며 고객·담보 정보는 쓰지 않는다.

실행 예:
  python3 collect_rtms.py --key 발급받은키 --sgg 11710,41135,12240 --from 202401 --to 202609
  python3 collect_rtms.py --key 발급받은키 --sgg-file 보유시군구.txt --from 202609 --to 202609 --out 동가격프록시_202609.csv
  python3 collect_rtms.py --selftest          # 인터넷 없이 해석·집계 로직만 점검
  DATA_GO_KR_KEY 환경변수로 키를 줘도 된다.

표준 라이브러리만 사용(Python 3.8+).
"""
import argparse
import csv
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "https://apis.data.go.kr/1613000/"
# 서비스 주소는 공공데이터포털 활용신청 화면의 '요청주소'와 같아야 한다. 다르면 여기만 고친다.
APIS = {
    "apt":  ("아파트",      "RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"),
    "rh":   ("연립·다세대", "RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade"),
    "offi": ("오피스텔",    "RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade"),
    "sh":   ("단독·다가구", "RTMSDataSvcSHTrade/getRTMSDataSvcSHTrade"),
}
# 응답 항목 이름: 개편된 영문 태그와 이전 한글 태그를 모두 받는다
F = {
    "price":  ["dealAmount", "거래금액"],
    "area":   ["excluUseAr", "전용면적"],
    "area_sh": ["totalFloorAr", "연면적", "plottageAr", "대지면적"],
    "umd":    ["umdNm", "법정동"],
    "year":   ["dealYear", "년"],
    "month":  ["dealMonth", "월"],
    "cancel": ["cdealType", "해제여부"],
    "dtype":  ["dealingGbn", "거래유형"],
    "sgg":    ["sggCd", "지역코드"],
}


def pick(item, keys):
    for k in keys:
        el = item.find(k)
        if el is not None and el.text is not None and el.text.strip() != "":
            return el.text.strip()
    return None


def months(a, b):
    y, m = int(a[:4]), int(a[4:])
    while f"{y}{m:02d}" <= b:
        yield f"{y}{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def load_bjd(path):
    """법정동코드 전체자료 → {(시군구코드, 읍면동[ 리]): (10자리, 시도, 시군구, 읍면동)}"""
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp949")
    alive = {}
    for line in text.splitlines()[1:]:
        p = line.split("\t")
        if len(p) >= 3 and p[2].strip() == "존재":
            alive[p[0]] = p[1].strip()
    sgg_nm = {c[:5]: n for c, n in alive.items() if c[5:] == "00000"}
    out = {}
    for c, n in alive.items():
        if c[5:] == "00000":
            continue
        base = sgg_nm.get(c[:5], "")
        rest = n[len(base):].strip() if base and n.startswith(base) else " ".join(n.split()[2:])
        sido = n.split()[0]
        out[(c[:5], rest)] = (c, sido, base[len(sido):].strip() or base, rest)
    return out


def http_get(url, timeout=30):
    """urllib 로 받고, 인증서 검증 실패(macOS python.org 설치본에서 흔함)면 시스템 curl 로 받는다."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read().decode("utf-8")
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" not in str(e):
            raise
    r = subprocess.run(["curl", "-sS", "-m", str(timeout), url], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("curl 실패: " + r.stderr.strip())
    return r.stdout


def fetch(key, path, lawd, ym, page, timeout=30):
    k = key if "%" in key else urllib.parse.quote(key, safe="")   # 인코딩된 키는 그대로, 디코딩 키는 인코딩
    q = urllib.parse.urlencode({"LAWD_CD": lawd, "DEAL_YMD": ym, "pageNo": page, "numOfRows": 1000})
    url = f"{BASE}{path}?serviceKey={k}&{q}"
    for attempt in range(3):
        try:
            return http_get(url, timeout)
        except Exception:  # noqa: BLE001
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))


def parse(xml_text):
    root = ET.fromstring(xml_text)
    if root.find(".//cmmMsgHeader") is not None:          # 게이트웨이 오류 형식 (키 미등록·트래픽 초과 등)
        raise RuntimeError(f"API 오류 {root.findtext('.//returnReasonCode')}: {root.findtext('.//returnAuthMsg') or root.findtext('.//errMsg')}"
                           " — 키가 아직 승인 전이면 활용신청 후 1~2시간 뒤 다시 시도하세요.")
    code = (root.findtext(".//resultCode") or "").strip()
    if code not in ("", "00", "000"):
        raise RuntimeError(f"API 오류 {code}: {root.findtext('.//resultMsg')}")
    total = int(root.findtext(".//totalCount") or 0)
    return root.findall(".//item"), total


def to_records(items, kind, lawd):
    recs = []
    for it in items:
        if (pick(it, F["cancel"]) or "").upper() in ("O", "Y"):      # 해제된 거래 제외
            continue
        price = pick(it, F["price"])
        area = pick(it, F["area_sh"] if kind == "sh" else F["area"])
        umd = pick(it, F["umd"])
        if not price or not area or not umd:
            continue
        try:
            won = float(price.replace(",", "")) * 1e4
            m2 = float(area)
        except ValueError:
            continue
        if m2 <= 0:
            continue
        y, mo = pick(it, F["year"]), pick(it, F["month"])
        recs.append({"ym": f"{int(y)}{int(mo):02d}" if y and mo else None, "sgg": pick(it, F["sgg"]) or lawd,
                     "umd": " ".join(umd.split()), "ppm": won / m2, "direct": (pick(it, F["dtype"]) or "") == "직거래"})
    return recs


def aggregate(recs, kind, bjd, exclude_direct):
    groups = {}
    for r in recs:
        if exclude_direct and r["direct"]:
            continue
        groups.setdefault((r["ym"], r["sgg"], r["umd"]), []).append(r["ppm"])
    rows, miss = [], set()
    for (ym, sgg, umd), v in sorted(groups.items()):
        v.sort()
        if len(v) >= 10:                                   # 표본이 충분하면 위아래 5% 잘라 극단치 제거
            cut = max(1, len(v) // 20)
            v = v[cut:-cut]
        hit = bjd.get((sgg, umd)) or bjd.get((sgg, umd.split()[0])) if bjd else None
        if bjd and not hit:
            miss.add(f"{sgg} {umd}")
        rows.append({"기준년월": ym, "법정동코드": hit[0] if hit else "", "시도": hit[1] if hit else "",
                     "시군구": hit[2] if hit else sgg, "읍면동": hit[3] if hit else umd, "건물유형": APIS[kind][0],
                     "평균가격": round(statistics.median(v), -3), "단위": "원/㎡", "표본수": len(v),
                     "출처": "국토부 실거래가(㎡당 중위값)"})
    return rows, miss


def run(args):
    key = args.key or os.environ.get("DATA_GO_KR_KEY")
    if not key:
        sys.exit("인증키가 필요합니다: --key 또는 DATA_GO_KR_KEY")
    sggs = [s.strip() for s in (args.sgg or "").split(",") if s.strip()]
    if args.sgg_file:
        sggs += [l.strip()[:5] for l in Path(args.sgg_file).read_text(encoding="utf-8").splitlines() if l.strip()]
    if not sggs:
        sys.exit("--sgg 또는 --sgg-file 로 시군구코드(5자리)를 주세요.")
    bjd = load_bjd(args.bjd) if args.bjd and Path(args.bjd).exists() else {}
    if not bjd:
        print("※ 법정동코드표가 없어 법정동코드 칸을 비웁니다(시스템이 시군구+읍면동 이름으로 연결).")
    out_rows, misses = [], set()
    for kind in args.types.split(","):
        label, path = APIS[kind]
        for lawd in sggs:
            for ym in months(args.frm, args.to):
                page, got, recs = 1, 0, []
                while True:
                    items, total = parse(fetch(key, path, lawd, ym, page))
                    recs += to_records(items, kind, lawd)
                    got += len(items)
                    if got >= total or not items:
                        break
                    page += 1
                    time.sleep(args.sleep)
                for r in recs:
                    r["ym"] = r["ym"] or ym
                rows, miss = aggregate(recs, kind, bjd, args.exclude_direct)
                out_rows += rows
                misses |= miss
                print(f"{label} {lawd} {ym}: 거래 {got}건 → 동 {len(rows)}곳")
                time.sleep(args.sleep)
    out = Path(args.out)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["기준년월", "법정동코드", "시도", "시군구", "읍면동", "건물유형", "평균가격", "단위", "표본수", "출처"])
        w.writeheader()
        w.writerows(out_rows)
    print(f"저장: {out}  ({len(out_rows)}행)")
    if misses:
        print("법정동코드를 찾지 못한 동(이름으로 연결됨):", ", ".join(sorted(misses)[:20]))


def selftest():
    new = """<response><header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header><body><items>
      <item><dealAmount>120,000</dealAmount><excluUseAr>84.9</excluUseAr><umdNm>문정동</umdNm><dealYear>2026</dealYear><dealMonth>9</dealMonth><sggCd>11710</sggCd></item>
      <item><dealAmount>100,000</dealAmount><excluUseAr>59.9</excluUseAr><umdNm>문정동</umdNm><dealYear>2026</dealYear><dealMonth>9</dealMonth><sggCd>11710</sggCd></item>
      <item><dealAmount>99,000</dealAmount><excluUseAr>84.9</excluUseAr><umdNm>문정동</umdNm><dealYear>2026</dealYear><dealMonth>9</dealMonth><cdealType>O</cdealType></item>
      <item><dealAmount>150,000</dealAmount><excluUseAr>84.9</excluUseAr><umdNm>잠실동</umdNm><dealYear>2026</dealYear><dealMonth>9</dealMonth><dealingGbn>직거래</dealingGbn></item>
    </items><totalCount>4</totalCount></body></response>"""
    old = """<response><header><resultCode>00</resultCode></header><body><items>
      <item><거래금액> 45,000</거래금액><전용면적>42.5</전용면적><법정동> 봉담읍 수영리</법정동><년>2026</년><월>9</월><지역코드>41593</지역코드></item>
    </items><totalCount>1</totalCount></body></response>"""
    bjd = load_bjd(HERE / "data" / "법정동코드_전체자료_20261014.txt")
    items, total = parse(new)
    recs = to_records(items, "apt", "11710")
    rows, _ = aggregate(recs, "apt", bjd, exclude_direct=True)
    assert total == 4 and len(recs) == 3, (total, len(recs))                       # 해제 1건 제외
    mj = [r for r in rows if r["읍면동"] == "문정동"][0]
    assert mj["법정동코드"] == "1171010800" and mj["표본수"] == 2, mj
    assert abs(mj["평균가격"] - round(statistics.median([1.2e9 / 84.9, 1e9 / 59.9]), -3)) < 1, mj
    assert not [r for r in rows if r["읍면동"] == "잠실동"]                          # 직거래 제외
    items, _ = parse(old)
    rows, miss = aggregate(to_records(items, "rh", "41593"), "rh", bjd, False)
    assert rows[0]["법정동코드"] == "4159325023" and rows[0]["건물유형"] == "연립·다세대", (rows, miss)
    try:
        parse("<response><header><resultCode>30</resultCode><resultMsg>SERVICE KEY IS NOT REGISTERED ERROR.</resultMsg></header></response>")
        raise AssertionError("오류 응답을 놓침")
    except RuntimeError:
        pass
    try:
        parse("<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</errMsg><returnAuthMsg>등록되지 않은 서비스키</returnAuthMsg><returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>")
        raise AssertionError("게이트웨이 오류를 놓침")
    except RuntimeError:
        pass
    print("selftest OK — 영문·한글 태그 해석, 해제·직거래 제외, ㎡당 중위가, 법정동코드(읍면 리 포함) 연결, 오류 응답 처리")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key")
    ap.add_argument("--sgg", help="시군구코드 5자리, 쉼표 구분 (예: 11710,41135)")
    ap.add_argument("--sgg-file", help="한 줄에 시군구코드 하나")
    ap.add_argument("--from", dest="frm", default=None, help="시작 계약년월 YYYYMM")
    ap.add_argument("--to", default=None, help="끝 계약년월 YYYYMM")
    ap.add_argument("--types", default="apt,rh,offi,sh", help="apt,rh,offi,sh 중 선택")
    ap.add_argument("--bjd", default=str(HERE / "data" / "법정동코드_전체자료_20261014.txt"), help="법정동코드 전체자료 txt")
    ap.add_argument("--exclude-direct", action="store_true", help="직거래 제외(특수관계 거래 영향 축소)")
    ap.add_argument("--sleep", type=float, default=0.2, help="호출 간격(초)")
    ap.add_argument("--out", default="동가격프록시_실거래.csv")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    else:
        if not (a.frm and a.to):
            sys.exit("--from, --to 계약년월(YYYYMM)을 주세요.")
        run(a)
