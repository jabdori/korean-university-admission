# 데이터 파이프라인

## 데이터 소스

원천은 대입정보포털 adiga.kr (한국대학교육협의회 운영, 법정 의무공개 입시정보 집계)입니다.

- 심사기준(2027 주요사항): POST /uct/acd/ade/criteriaAndResultItemAjax.do (tsrdCmphSlcnArtclCd=21 종합/31 교과/41 수능)
- 입시결과(전년도 결과): POST /uct/acd/ade/criteriaAndResultNewAjax.do (tsrdCmphSlcnArtclUpCd=20/30/40)
- 추가안내자료·모집요강: 대학별 페이지에서 fileId 추출 후 /cmm/com/file/fileDown.do

연도 규약: 스크립트 인자 연도 N = "N학년도 모집" 기준. 입시결과는 (N-1)학년도 결과를 담습니다.

## 파이프라인 단계

| 단계 | 스크립트 | 설명 |
|---|---|---|
| 1 | 01_univs.py | 대학 목록 갱신 |
| 2 | 02_fetch_items.py | 심사기준+입결 수집 |
| 3 | 03_parse.py | 정규화 |
| 4 | 04_download_attachments.py | 추가안내자료 다운로드 |
| 5 | 05_download_yogang.py | 모집요강 다운로드 |
| 6 | 06_dist_crawler.py | 대학사이트 정적 탐색 |
| 7 | 07_make_manifest.py | 매니페스트 재생성 |
| 8 | 08_extract_docs.py | 문서 구조 보존 추출 |
| 9 | 09_ocr_extract.py | 스캔 PDF OCR |
| 10 | 10_make_agent_tasks.py | AI 정규화 task 생성 |
| 11 | 11_run_agent.py | AI 정규화 실행 |
| 12 | 12_export_d1.py | D1 시드 내보내기 |

## 실행 방법

    # 1~3: 포털 수집·정규화
    uv run python scripts/01_univs.py [연도]
    TIME_LIMIT=100 uv run python scripts/02_fetch_items.py [연도]
    uv run python scripts/03_parse.py [연도]

    # 4~5: 첨부파일 다운로드
    uv run python scripts/04_download_attachments.py
    TIME_LIMIT=100 uv run python scripts/05_download_yogang.py [연도]

    # 6~7: 대학사이트 탐색·매니페스트
    uv run python scripts/06_dist_crawler.py [--only 대학명]
    uv run python scripts/07_make_manifest.py

    # 8~9: 문서 추출·OCR
    uv run --python .venv-ocr/bin/python python scripts/08_extract_docs.py
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
      uv run --python .venv-ocr/bin/python python scripts/09_ocr_extract.py 0 45
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
      uv run --python .venv-ocr/bin/python python scripts/09_ocr_extract.py 45 45

    # 10~11: AI 정규화
    uv run --python .venv-ocr/bin/python python scripts/10_make_agent_tasks.py
    GEMINI_API_KEY=... uv run --python .venv-ocr/bin/python python scripts/11_run_agent.py --workers 2

    # 12: D1 시드
    uv run --python .venv-ocr/bin/python python scripts/12_export_d1.py

## 문서 추출 상세

08번은 원본을 extracted/ 아래 동일 상대경로 + .json으로 저장하고 스캔 PDF는 extracted/_ocr_queue.json에 남깁니다.

09번은 한국어 인식 모델로 페이지를 한 장씩 처리하고 OCR 결과와 PaddleOCR 원 결과(.raw.json)를 함께 저장합니다.

10번은 키워드 블록을 근거 위치(locator)와 함께 최대 12,000자 task로 나눠 normalized/agent_tasks.jsonl과 normalized/agent_prompt.md를 만듭니다.

11번은 Gemini API로 task를 정규화합니다. 성공한 task는 재실행 시 스킵하므로 rate limit으로 중단돼도 같은 명령을 다시 실행하면 이어집니다. 응답은 records 배열 형식, record_type, evidence 존재, locator 일치, quote가 task 원문에 존재하는지 검증합니다.

## 주의사항

- macOS timeout 명령이 없으므로 TIME_LIMIT 환경변수(초)를 사용합니다.
- 스크립트는 캐시 스킵 방식이라 재실행 시 이어서 진행됩니다.
- 12번 스크립트가 만드는 .d1/seed/all.sql은 D1 데이터를 모두 삭제한 뒤 다시 삽입하므로 직접 수정한 데이터가 있으면 먼저 백업해야 합니다.

