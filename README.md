# PRPT_MNGE_CLAUDE — 부동산 통합 익스포저 관리 시스템

주택담보대출·투자부동산·주택연금의 부동산을 **도로명주소 → 법정동** 기준으로 묶어 동 단위로 관리하고, KB 지수·동 가격 프록시와 연계해 지도·집중도·스트레스·조기경보로 보는 시스템입니다. (1안 상세기획서 1단계 범위)

> 저장소의 주소·금액·가격 데이터는 모두 **가상**입니다. 실데이터와 API 키는 절대 커밋하지 마세요.

## 실행 방식 3가지

| 방식 | 파일 | 용도 |
|---|---|---|
| 내부망 단일 파일 | `부동산통합관리시스템_내부망.html` | 라이브러리·경계·법정동코드표 내장, 서버 불필요, 외부 자동 요청 0건. 실데이터 운영용 |
| Vercel 배포 | `public/index.html` + `api/chat.js` | 브라우저로 접속하는 시연용. **AI 질문(네모트론)** 사용 가능 |
| 로컬·사내 챗봇 서버 | `tools/chat_server.py` | PC나 사내 서버에서 화면 + AI 질문. 사내 설치 모델로 주소만 바꿔 연결 |

## Vercel 배포 (AI 질문 포함)

1. vercel.com 에 GitHub 계정으로 로그인 → **Add New → Project** → 이 저장소 선택
2. Framework Preset: **Other** (빌드 명령 없음, `vercel.json`이 `public/`을 화면으로 지정) → **Deploy**
3. **Settings → Environment Variables** 에 등록 후 **Redeploy**

   | 이름 | 값 |
   |---|---|
   | `OPENROUTER_API_KEY` | OpenRouter 키 (필수) |
   | `APP_PASSCODE` | 화면에서 AI 질문할 때 넣는 암호 (권장 — 주소가 공개되므로 무료 사용량 보호) |
   | `NEMOTRON_MODEL` | 선택. 기본 `nvidia/nemotron-3.5-lightning:free` |

4. 배포 주소로 접속 → 상단 **AI 질문**. 이후 `main`에 push 하면 자동 재배포됩니다.

AI 질문은 화면이 계산한 **집계 요약**(시군구·동 집계, 조기경보, 스트레스, 점검 건수)만 보내고 관리번호·고객번호·상세주소는 보내지 않습니다. 보낼 내용은 패널의 '보낼 내용 보기'로 확인할 수 있습니다. Vercel·OpenRouter는 외부 서비스이므로 **가상 데이터 시연에만** 쓰고, 실데이터는 사내에 설치한 모델(`CHAT_BASE_URL`)로 연결하세요. Vercel 무료(Hobby) 요금제의 이용 범위는 약관을 확인하세요.

## 로컬·사내 챗봇 서버

```bash
export OPENROUTER_API_KEY="키"          # 사내 모델이면 CHAT_BASE_URL=http://모델서버:8000/v1
python3 tools/chat_server.py             # → http://localhost:8800
```

## 매월·분기 데이터 갱신

| 자료 | 받는 곳 | 시스템에 넣는 곳 |
|---|---|---|
| 원천 로우데이터(xlsx) | SAP 여신·자산운용·상품 시스템 → 표준 양식 | 상단 '엑셀 불러오기' |
| 도로명주소 DB (건물별 법정동코드·좌표) | 행정안전부 도로명주소 개발자센터 주소DB(위치정보요약DB 등), 보유 시도분 | 데이터 → 도로명주소 사전 |
| KB 월간 매매가격지수 | KB부동산 데이터허브 시계열 엑셀 | 데이터 → 가격지표 → KB 매매가격지수 파일 |
| 동 가격 프록시 | 국토부 실거래가 API → `tools/collect_rtms.py` (외부망) | 데이터 → 가격지표 → 동 가격 프록시 파일 |
| 법정동코드표 | 행정표준코드관리시스템 '법정동코드 전체자료' | `tools/prep_bjd.py` 후 `tools/build.py` |

```bash
python3 tools/collect_rtms.py --key 공공데이터포털키 --sgg 11710,41135 --from 202609 --to 202609
```

## 폴더

| 경로 | 내용 |
|---|---|
| `src/app.html` | 화면·계산 로직 원본 |
| `tools/build.py` | 원본 → 내부망 html · 웹(아티팩트) · `public/index.html` 생성 |
| `tools/prep_geo.py`, `tools/prep_bjd.py`, `tools/data/` | 행정구역 경계·대표점, 법정동코드표(2026.10.14)와 옛 코드 변환표 |
| `tools/collect_rtms.py` | 실거래가 수집 → 동 가격 프록시 csv (`--selftest`로 점검) |
| `tools/chat_server.py`, `api/chat.js` | AI 질문 중계 (로컬·사내 / Vercel) |
| `tools/make_sample_v2.py`, `tools/utmk.py` | 가상 샘플 생성, UTM-K↔위경도 변환 |
| `샘플데이터/` | 로우데이터 양식, 가상 로우데이터 2개월, 주소DB 형식 가상 사전, KB 시계열, 동 프록시 |

## 유의사항
- 행정구역 개편(전남광주통합특별시, 인천 구 재편, 화성·부천 구 신설 등)은 내장 법정동코드표 기준으로 처리하며 옛 코드·옛 이름도 현행 코드로 연결합니다.
- 브라우저 저장소(IndexedDB)에 쌓인 데이터는 해당 PC 브라우저에만 남습니다. 여러 사람이 함께 쓰려면 서버 저장소 전환이 필요합니다.
- 조기경보 기준값·스트레스 하락률·동 프록시 가중치는 예시값이며 설정 화면에서 바꿀 수 있습니다.
- 행정구역 경계: 통계청 SGIS 2018(공공누리 1유형), 행정동 대표점: vuski/admdongkor 2023.07.
