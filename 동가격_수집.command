#!/bin/bash
# 더블클릭 실행: 국토부 실거래가(data.go.kr) → 동 가격 프록시 csv
# 준비: 같은 폴더의 '인증키_data.go.kr.txt'에 인증키 붙여 넣기, '보유시군구.txt'에 시군구코드(5자리) 한 줄씩
cd "$(dirname "$0")" || exit 1
echo "=== 동 가격 프록시 수집 (국토부 실거래가) ==="
echo "1) 처음 수집: 최근 36개월   (보유 26개 시군구 기준 약 40~60분)"
echo "2) 매월 갱신: 최근 3개월    (늦게 신고된 거래 반영, 약 5분)"
echo "3) 연결 시험: 1개 시군구 · 1개월 · 아파트만 (10초)"
read -r -p "번호를 고르세요 [3]: " M
M=${M:-3}
TO=$(date -v-1m +%Y%m)
STAMP=$(date +%Y%m%d)
case "$M" in
  1) python3 tools/collect_rtms.py --sgg-file 보유시군구.txt --from "$(date -v-36m +%Y%m)" --to "$TO" --out "동가격프록시_실거래_${STAMP}.csv" ;;
  2) python3 tools/collect_rtms.py --sgg-file 보유시군구.txt --from "$(date -v-3m +%Y%m)" --to "$TO" --out "동가격프록시_실거래_${STAMP}_최근3개월.csv" ;;
  *) python3 tools/collect_rtms.py --sgg "$(head -n1 보유시군구.txt)" --types apt --from "$TO" --to "$TO" --out "동가격프록시_연결시험.csv" ;;
esac
echo
echo "끝났습니다. 만들어진 csv를 시스템의 '데이터·내보내기 → 가격지표 월별 업데이트 → 동 가격 프록시 파일'에 올리세요."
read -r -p "Enter를 누르면 창이 닫힙니다."
