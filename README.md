# 한국 대학 입시 데이터·API 플랫폼

대입정보포털(adiga.kr)과 대학 입시 사이트의 공개 자료를 수집하고, 원본 문서 구조를 보존한 추출 결과와 검증된 정규화 결과를 함께 관리하는 프로젝트입니다. 정규화된 대학·전형·심사기준 데이터는 Cloudflare Workers D1에 적재되고, Hono API와 MCP(Model Context Protocol) 서버로 조회할 수 있습니다.

현재 배포된 대학 마스터는 캠퍼스/모집 단위 기준 202행이며, 캠퍼스 표기를 제거한 표준 대학 이름 기준으로 185개 대학입니다. GitHub 저장소에는 코드, 마이그레이션, 실행 스크립트와 수집 리포트만 포함하고, `raw/`, `cache/`, `extracted/`, `normalized/` 같은 대용량 생성물은 커밋하지 않습니다. API 키도 항상 환경 변수로만 전달합니다.

## 빠른 시작

API 코드 검증과 로컬 개발:

    npm install
    npm run typecheck
    npm run dev

데이터 수집·정규화는 uv 격리 환경을 사용합니다. 전체 흐름은 아래 "원본 문서 구조 보존 추출"과 "재실행·확장"을 참고하세요.

## 디렉토리 구조

```
~/projects/university/
├── normalized/            정규화 데이터 (CSV, UTF-8 BOM)
│   ├── univs.csv               대학 마스터 202개 (unvCd, 홈페이지, 입시홈페이지, 추가안내자료 fileId)
│   ├── results_long_{연도}.csv 입결 long 포맷 (대학×전형×모집단위×지표×값)
│   ├── results_jihak_{연도}.csv 학생부(종합/교과) 입결 wide (모집인원/경쟁률/충원인원/환산점수·등급 50/70% 컷/총점)
│   ├── criteria_text_{연도}.csv 심사기준 섹션 텍스트 (전형별 특성/전형요소/반영비율 등)
│   └── coverage.csv            대학별 보유 데이터 요약 (07_make_manifest.py 실행으로 재생성)
├── raw/
│   ├── adiga/{대학명}/     포털 첨부 원본: 추가안내자료 69개 + 모집요강(시행계획/수시/정시) 603건
│   └── univ_dist/{대학명}/ 대학 자체 사이트 입시결과·등급분포 자료 151개 대학
├── cache/
│   ├── result/{연도}/      입시결과 조각 HTML (연도당 606건: 202대학×3전형구분)
│   ├── sirha/{연도}/       심사기준 조각 HTML (동일 구성)
│   ├── popup_detail/       대학별 입시결과 상세 팝업 HTML
│   └── univ_detail/        대학정보 페이지 HTML (모집요강 링크 출처)
├── scripts/                수집·정규화 스크립트 (표준 라이브러리만 사용)
├── src/                    Cloudflare Workers API (Hono + Swagger + MCP)
└── migrations/             D1 스키마 마이그레이션
```

## 데이터 소스와 방법

원천은 대입정보포털 adiga.kr (한국대학교육협의회 운영, 법정 의무공개 입시정보 집계).

- 심사기준(2027 주요사항): POST /uct/acd/ade/criteriaAndResultItemAjax.do (tsrdCmphSlcnArtclCd=21 종합/31 교과/41 수능)
- 입시결과(전년도 결과): POST /uct/acd/ade/criteriaAndResultItemNewAjax.do (tsrdCmphSlcnArtclUpCd=20/30/40)
- 추가안내자료·모집요강: 대학별 페이지에서 fileId 추출 후 /cmm/com/file/fileDown.do
- 연도 규약: 스크립트 인자 연도 N = "N학년도 모집" 기준. 입시결과는 (N-1)학년도 결과를 담는다.
  예: 2027 실행 → 2026 결과. 백필 2026/2025/2024 실행 → 2025/2024/2023 결과.

## 연도별 정규화 결과 (행 수)

| 연도 | results_long | results_jihak | criteria 섹션 |
|---|---|---|---|
| 2027 | 671,818 | 30,636 | 1,221 |
| 2026 | 647,828 | 29,339 | 1,169 |
| 2025 | 674,288 | 32,246 | 1,117 |
| 2024 | 684,636 | 32,376 | 564 |

## 커버리지 요약 (2026-09-16 기준)

- 입결·심사기준: 입결 4개년 전량 보유 194/202. 포털이 빈 조각을 주는 대학은 전 연도 3개(강원대 제3·제4캠퍼스, 경동대 본교, 통합·편제 변경) 외에 연도별 다수 존재.
  - 입결 연도별 빈 조각: 2026 경북대·서경대, 2025 국립순천대, 2024 광주가톨릭대·대구예술대
  - 심사기준: 제2캠퍼스 다수(본교 입시사이트 공유로 조각 자체가 빔) + 2026 성신여대·우송대·전주교대·영산선학대·중앙승가대 등
  - 2026-09-17 검증: 누락은 전부 캐시 조각 HTML이 빈 응답(표 0개)인 경우로, 파싱 실패가 아님.
- 추가안내자료: 69/202 (포털에 파일을 올린 대학만; HWP 44·PDF 11·XLSX 9·HWPX 4·PNG 1)
- 모집요강: 202/202 대학 × 시행계획/수시요강/정시요강 = 603건 (재외국민·외국인·선행학습영향평가 등 부수 파일은 용량 절제를 위해 제외, 필요시 05 스크립트 필터 제거 후 재실행)
- 대학 자체 입시결과·분포 자료: 151/202 확보 (정적 크롤링 28 + 브라우저 탐색 123), 파일 총 300여 건

## 원본 문서 구조 보존 추출 (2026-09-17 기준)

- 유효 추출 789건: 디지털 PDF 660, 구형 HWP 78, XLSX 44, HWPX 6, 확장자 오기 구형 Excel(XLS) 1
- 페이지 24,422개, 표 46,403개를 페이지/시트/표 단위로 보존
- OCR 대기 90건(스캔 PDF 56 + 텍스트 없는 PDF 34)은 PP-StructureV3로 별도 추출 중
- 서울신학대 전년도 입시결과 3959번 파일은 HWPX 확장자를 가진 404 HTML 문서라 데이터 없음

문서 추출·OCR 환경은 uv로 분리한다. 시스템 Python 버전과 무관하게 Python 3.11 가상환경을 사용한다.

    uv venv .venv-ocr --python 3.11
    uv pip install --python .venv-ocr/bin/python \
      "paddleocr==3.7.0" "paddlepaddle==3.3.1" "paddlex[ocr]==3.7.2" \
      "pymupdf==1.28.2" "openpyxl==3.1.5" "pyhwp==0.1b15" "xlrd==2.0.2"

    uv run --python .venv-ocr/bin/python python scripts/08_extract_docs.py
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
      uv run --python .venv-ocr/bin/python python scripts/09_ocr_extract.py 0 45
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
      uv run --python .venv-ocr/bin/python python scripts/09_ocr_extract.py 45 45
    uv run --python .venv-ocr/bin/python python scripts/10_make_agent_tasks.py

08번은 원본을 extracted/ 아래 동일 상대경로 + .json으로 저장하고 스캔 PDF는 extracted/_ocr_queue.json에 남긴다. 09번은 한국어 인식 모델로 페이지를 한 장씩 처리하고 OCR 결과와 PaddleOCR 원 결과(.raw.json)를 함께 저장한다. 10번은 키워드 블록을 근거 위치(locator)와 함께 최대 12,000자 task로 나눠 normalized/agent_tasks.jsonl과 normalized/agent_prompt.md를 만든다. 현재 4,571개 task가 생성되었고, OCR 완료 후 재실행하면 대기 문서가 자동 포함된다.

11번은 Gemini API로 task를 정규화한다. API 키는 GEMINI_API_KEY 환경 변수로만 전달하고 파일·커밋에 저장하지 않는다. 성공한 task는 재실행 시 스킵하므로 rate limit으로 중단되어도 같은 명령을 다시 실행하면 이어진다.
기본 모델은 gemini-3.5-flash-lite이며 --model로 변경할 수 있다.

    GEMINI_API_KEY=... uv run --python .venv-ocr/bin/python python scripts/11_run_agent.py --limit 2
    GEMINI_API_KEY=... uv run --python .venv-ocr/bin/python python scripts/11_run_agent.py --workers 2
    uv run --python .venv-ocr/bin/python python scripts/11_run_agent.py --check

출력은 normalized/agent_results.jsonl(task별 records)과 normalized/agent_errors.jsonl(실패 원인)이다. 응답은 records 배열 형식, record_type, evidence 존재, locator 일치, quote가 task 원문에 존재하는지 검증한다.

## 대학 입시 정보 API

Cloudflare Worker + D1 + Hono로 배포한다. 정규화된 대학 마스터, 검색용 별칭, 심사기준/입시결과 records를 하나의 응답으로 반환한다.

- 배포 주소: https://university-admission-api.aside-hazle6287.workers.dev
- 상태 확인: GET /health
- OpenAPI 문서: GET /openapi
- Swagger UI: GET /swagger
- 통합 조회: POST /universities/info
- 대학 목록: GET /universities
- 모집시기 요약: GET /universities/{unvCd}/rounds
- 전형 목록: GET /universities/{unvCd}/selections
- 레코드 상세: GET /records/{id}
- MCP Streamable HTTP: POST /mcp (기본 도구: get_university_info, 보조 도구: search_universities, list_university_selections, get_admission_record)

대학 목록(GET /universities)은 page, limit 파라미터로 페이지네이션하며 기본 20건, 최대 100건을 반환한다. Swagger UI의 /universities/info 미리보기는 대형 페이로드 렌더링 방지를 위해 records를 화면 표시용 20개로 제한하지만, 실제 API와 MCP 응답은 전체를 반환한다.

전형 표준 분류는 admission_records에 3개 컬럼으로 저장한다.

- 주 전형요소(selection_method): 학생부교과, 학생부종합, 논술, 실기, 수능, 기타
- 선발 대상(selection_target): 일반, 지역인재, 농어촌, 기회균형, 특성화고, 특수교육, 특기자, 재직성인, 기타
- 정원 구분(quota_type): 정원내, 정원외 (문서에 근거가 없으면 NULL)

분류 규칙은 scripts/classify_selection.py 하나에서 관리하며, 전형명과 정규화된 전형 단계(method/elements)를 함께 근거로 사용한다. 혼합형은 실기 > 논술 > 수능 > 학생부교과 > 학생부종합 순서로 주 요소를 정하고, 선발 대상은 특수교육 > 특성화고 > 농어촌 > 기회균형 > 특기자 > 재직성인 > 지역인재 순서를 우선한다. "모집인원 현황", "전형료 안내" 같은 노이즈는 기타로 처리한다.

요청 예시는 다음과 같다. record_type, year, round는 선택 필터다.

    curl -sS -X POST https://university-admission-api.aside-hazle6287.workers.dev/universities/info -H 'Content-Type: application/json' -d '{"universities":["제주대학교","한림대학교"],"record_type":"criteria","year":2027,"round":"수시"}'

요청 정보, 매칭된 대학 목록, 원본 근거 경로가 포함된 records, 대학별 요약(summaries), 찾지 못한 이름(not_found)으로 구성된다. 대학 이름은 최대 10개까지 요청할 수 있다. record_type, year, round 외에 selection_method, selection_target, quota_type로도 필터할 수 있다.

MCP 클라이언트는 같은 배포 주소의 /mcp를 Streamable HTTP 서버로 등록하면 된다. 인증은 걸려 있지 않으며, 요청/응답은 표준 MCP JSON-RPC 2.0을 따른다. LLM은 get_university_info에 대학 이름과 year, round, selection_method 등 조건을 넘겨서 하위 전형·모집단위·전형 단계·평가 기준·근거를 한 번에 받아 판단하고, 개별 코드/레코드 확인이 필요할 때만 보조 도구를 사용한다.

API 개발과 배포:

    npm install
    npm run typecheck
    npx wrangler d1 migrations apply university-admission --remote
    uv run --python .venv-ocr/bin/python python scripts/12_export_d1.py
    npx wrangler d1 execute university-admission --remote --file=.d1/seed/all.sql
    npm run deploy

주의: 12번 스크립트가 만드는 .d1/seed/all.sql은 D1의 admission_records, university_aliases, universities 데이터를 모두 삭제한 뒤 다시 삽입한다. 따라서 D1에 직접 수정한 데이터가 있으면 먼저 백업해야 한다.

## 미확보 51개 대학 요약 (raw/univ_dist 없음)

- 포털 빈 조각 3개: 위 참조
- 정적·브라우저 탐색 모두 실패 48개. 주요 사유:
  - HTML 표로만 공개(파일 없음): 서울교대, 성공회대, 중부대, 호서대, 한국성서대 등
  - 경쟁률 조회 서비스(유웨이/진학어플라이 팝업)로만 제공: 고려대, 고려대(세종), 연세대, 서울기독대 등
  - 결과 메뉴 자체가 없음: 신한대, 칼빈대, 화성의과학대, 대신대 등
  - 사이트 소멸·접속 불가: 을지대(도메인), 중앙승가대, 초당대, 세한대(DNS), 고신대
  - 상세: scripts/dist_report_1~6.json 의 미발견 항목 비고 참조

## 미확보 대학 CSV화 (2026-09-16 2차 작업)

파일을 공개하지 않는 대학 중 데이터가 웹에 존재하는 16개 대학을 CSV 원천데이터로 변환. 총 약 12,000행.

| 대학 | 파일 | 행 수 | 범위 |
|---|---|---|---|
| 고려대 본교 | 고려대학교_본교_경쟁률.csv | 1,588 | 수시 3개년·정시 2개년·편입 2개년·특별 (유웨이 파싱) |
| 고려대 세종 | 고려대학교_세종_경쟁률.csv | 460 | 수시 2개년·정시·편입·추가·특별 |
| 연세대 본교 | 연세대학교_본교_경쟁률.csv | 2,196 | 수시 5개년·정시 4개년·편입 4개년 (진학앤 애드온) |
| 연세대 미래 | 연세대학교(미래)_경쟁률.csv | 2,535 | 수시 2018~2027·정시 2021~2026·편입 (유웨이) |
| 협성대 | 협성대학교_경쟁률.csv | 1,391 | 2022~2026 수시·정시·편입 (유웨이) |
| 부경대 | 국립부경대학교_입시결과.csv | 1,644 | 2024~2026 (진학앤·유웨이 혼용) |
| 호서대 | 호서대학교_입시결과.csv | 1,493 | 2024~2026 (등급·백분위 컷 포함) |
| 중부대 | 중부대학교_입시결과.csv | 347 | 2025~2026 + 편입 (등급·백분위 포함) |
| 성공회대 | 성공회대학교_입시결과.csv | 147 | 2024~2026 (충원·점수·등급 포함) |
| 한국성서대 | 한국성서대학교_입시결과.csv | 194 | 2024~2026 (석차등급 포함) |
| 서울교대 | 서울교육대학교_입시결과.csv | 38 | 2024~2026 (성적 컷 포함) |

참고: 국립대 7곳(경국·군산·목포·목포해양·교통·해양·한밭)은 본문 표 없는 첨부파일형 게시판이라 파일 URL 목록을 같은 폴더에 CSV로 기록했다 (다운로드 대상 목록으로 활용). 창원대는 접속 불가, 고신대는 PDF 뷰어 전용(PDF 원본 URL 패턴은 dist 리포트 참조).

주의: 고려대·연세대 본교 대형 CSV는 셸 장애로 Downloads에 임시 사본이 있었으며, 복사 완료 후 프로젝트 내 파일이 정본이다.

표준 컬럼: `학년도,모집시기,전형명,단과대학,모집단위,모집인원,지원인원,경쟁률` (대학별 추가 지표는 뒤에 덧붙임). 경쟁률은 "5.40 : 1"→"5.40" 정규화. 대학별 스키마 차이는 각 파일 헤더 참조.

## 알려진 한계

- results_long 은 표 구조를 대학별 헤더 그대로 평탄화한 long 포맷이라, 수능위주(40)는 대학마다 지표 조합이 다르다 (백분위 컬럼 구성 상이).
- criteria_text 는 대학 서술형 원문을 섹션 단위 텍스트로 보존한 것이며 완전 구조화가 아니다.
- 일부 대학(가야대, 감리교신학대 등)은 결과를 이미지로만 공개해 이미지로 저장됨. 강남대는 웹페이지를 PDF 인쇄본으로 보관.
- 중복 캠퍼스(건양 제2, 경기 제2, 경동 제3·제4 등)는 본교 사이트를 공유해 동일 자료가 복제되어 있음.

## 재실행·확장

| 작업 | 명령 |
|---|---|
| 대학 목록 갱신 | `uv run python scripts/01_univs.py [결과연도]` |
| 심사기준+입결 수집 | `TIME_LIMIT=100 uv run python scripts/02_fetch_items.py [연도]` 반복 |
| 정규화 | `uv run python scripts/03_parse.py [연도]` |
| 추가안내자료 | `uv run python scripts/04_download_attachments.py` |
| 모집요강 | `TIME_LIMIT=100 uv run python scripts/05_download_yogang.py [연도]` 반복 |
| 대학사이트 정적 탐색 | `uv run python scripts/06_dist_crawler.py [--only 대학명]` |
| 매니페스트 재생성 | `uv run python scripts/07_make_manifest.py` |

주의: macOS timeout 명령이 없으므로 TIME_LIMIT 환경변수(초)를 사용. 스크립트는 캐시 스킵 방식이라 재실행 시 이어서 진행됨.
