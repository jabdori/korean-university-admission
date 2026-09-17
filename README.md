# Korean University Admission Data & API

한국 대학 입시 공개 자료를 수집·정규화하고, Cloudflare Workers D1과 Hono API로 조회할 수 있는 프로젝트입니다.

대입정보포털(adiga.kr)과 대학 입시 사이트의 공개 자료를 수집해 구조화된 데이터로 변환하고, MCP(Model Context Protocol) 서버를 통해 LLM이 활용할 수 있는 형태로 제공합니다.

## 기능

- **데이터 수집**: 대입정보포털 심사기준·입시결과·모집요강, 대학 자체 입시결과 자료 크롤링
- **문서 추출**: PDF·HWP·XLSX 원본에서 페이지/시트/표 단위 구조 보존 추출, 스캔 PDF는 PaddleOCR PP-StructureV3 처리
- **데이터 정규화**: 대학·전형·모집단위·전형 단계별 표준 스키마로 변환, AI 정규화 에이전트 근거 검증
- **API 제공**: Cloudflare Workers D1 + Hono + Swagger + OpenAPI
- **MCP 서버**: LLM 도구로 대학 입시 정보 조회 (Streamable HTTP)

## 빠른 시작

API 로컬 개발:

    npm install
    npm run typecheck
    npm run dev

데이터 수집·정규화 환경:

    uv venv .venv-ocr --python 3.11
    uv pip install --python .venv-ocr/bin/python \
      "paddleocr==3.7.0" "paddlepaddle==3.3.1" "paddlex[ocr]==3.7.2" \
      "pymupdf==1.28.2" "openpyxl==3.1.5" "pyhwp==0.1b15" "xlrd==2.0.2"

## API

**배포 주소**: https://university-admission-api.aside-hazle6287.workers.dev

**문서**:

- [Swagger UI](https://university-admission-api.aside-hazle6287.workers.dev/swagger) — 대화형 API 문서, 직접 요청 테스트 가능
- [OpenAPI 스펙](https://university-admission-api.aside-hazle6287.workers.dev/openapi) — 기계 판독용 OpenAPI 3.0 JSON

로컬 개발 시: npm run dev 실행 후 http://localhost:8787/swagger 접속

| 엔드포인트 | 설명 |
|---|---|
| GET /health | 상태 확인 |
| GET /openapi | OpenAPI 스펙 |
| GET /swagger | Swagger UI |
| POST /universities/info | 대학 통합 정보 조회 |
| GET /universities | 대학 목록 (페이지네이션) |
| GET /universities/{unvCd}/rounds | 모집시기 요약 |
| GET /universities/{unvCd}/selections | 전형 목록 |
| GET /records/{id} | 레코드 상세 |
| POST /mcp | MCP Streamable HTTP |

`POST /universities/info` 요청 예시:

    curl -sS -X POST https://university-admission-api.aside-hazle6287.workers.dev/universities/info \
      -H 'Content-Type: application/json' \
      -d '{"universities":["서울대학교"],"record_type":"criteria","year":2027,"round":"수시"}'

`GET /universities`는 `page`, `limit` 파라미터로 페이지네이션하며 기본 20건, 최대 100건을 반환합니다.

MCP 클라이언트는 같은 배포 주소의 `/mcp`를 Streamable HTTP 서버로 등록하면 됩니다. 기본 도구는 `get_university_info`이고, 보조 도구로 `search_universities`, `list_university_selections`, `get_admission_record`가 있습니다.

## 전형 표준 분류

`admission_records` 테이블에 3개 컬럼으로 전형을 표준 분류합니다.

| 컬럼 | 분류 값 |
|---|---|
| selection_method | 학생부교과, 학생부종합, 논술, 실기, 수능, 기타 |
| selection_target | 일반, 지역인재, 농어촌, 기회균형, 특성화고, 특수교육, 특기자, 재직성인, 기타 |
| quota_type | 정원내, 정원외 (근거 없으면 NULL) |

분류 규칙은 `scripts/classify_selection.py`에서 관리합니다.

## 프로젝트 구조

    ├── scripts/          수집·추출·정규화 스크립트
    ├── src/              Cloudflare Workers API (Hono + Swagger + MCP)
    ├── migrations/       D1 스키마 마이그레이션
    ├── docs/             상세 문서
    ├── raw/              수집 원본 (Git 제외)
    ├── extracted/        문서 추출 결과 (Git 제외)
    └── normalized/       정규화 데이터 (Git 제외)

대용량 생성물(`raw/`, `extracted/`, `normalized/`, `cache/`)은 Git에 포함하지 않습니다. API 키는 항상 환경 변수로만 전달합니다.

## 문서

- [데이터 파이프라인](docs/data-pipeline.md): 수집·추출·정규화 단계별 안내
- [데이터 커버리지](docs/data-coverage.md): 확보 현황과 통계
- [알려진 한계](docs/known-limitations.md): 데이터 품질 주의사항

## 배포

    npm install
    npm run typecheck
    npx wrangler d1 migrations apply university-admission --remote
    uv run --python .venv-ocr/bin/python python scripts/12_export_d1.py
    npx wrangler d1 execute university-admission --remote --file=.d1/seed/all.sql
    npm run deploy
