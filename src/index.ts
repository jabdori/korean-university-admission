import { OpenAPIHono, createRoute } from '@hono/zod-openapi';
import { swaggerUI } from '@hono/swagger-ui';
import { z } from 'zod';
import { McpServer, WebStandardStreamableHTTPServerTransport } from '@modelcontextprotocol/server';
import { createMcpHonoApp } from '@modelcontextprotocol/hono';

type Env = { DB: D1Database };

const RecordTypeSchema = z.enum(['criteria', 'result', 'other']);
const RoundSchema = z.enum(['수시', '정시', '기타', '미상']);
const SelectionMethodSchema = z.enum(['학생부교과', '학생부종합', '논술', '실기', '수능', '기타']);
const SelectionTargetSchema = z.enum(['일반', '지역인재', '농어촌', '기회균형', '특성화고', '특수교육', '특기자', '재직성인', '기타']);
const QuotaTypeSchema = z.enum(['정원내', '정원외']);

const RequestSchema = z.object({
  universities: z.array(z.string().trim().min(1, '대학 이름은 비워 둘 수 없습니다.'))
    .min(1, '대학 이름을 1개 이상 입력해주세요.')
    .max(10, '대학 이름은 최대 10개까지 조회할 수 있습니다.')
    .describe('대학 표시 이름, 표준 이름, 등록된 별칭. 이름만 넣으면 나머지 조건 없이 해당 대학의 보유 데이터 전체를 조회한다.'),
  record_type: RecordTypeSchema.optional().describe('레코드 종류. criteria=심사기준, result=입시결과, other=기타 안내. 생략하면 전체.'),
  year: z.number().int().min(2018).max(2028).optional().describe('입시 연도(학년도). 생략하면 보유한 전체 연도.'),
  round: RoundSchema.optional().describe('모집시기. 수시, 정시, 기타, 미상. 생략하면 전체.'),
  selection_method: SelectionMethodSchema.optional().describe('주 전형요소 표준 분류. 생략하면 전체.'),
  selection_target: SelectionTargetSchema.optional().describe('선발 대상 표준 분류. 생략하면 전체.'),
  quota_type: QuotaTypeSchema.optional().describe('정원 구분. 정원내, 정원외. 생략하면 전체.'),
}).strict();

const ErrorResponseSchema = z.object({
  error: z.string().describe('사용자에게 표시할 한국어 오류 메시지.'),
  details: z.array(z.object({
    path: z.string().describe('검증에 실패한 요청 필드 경로.'),
    message: z.string().describe('해당 필드의 한국어 오류 메시지.'),
  })).optional().describe('요청 값 검증 실패 상세.'),
});

const UniversitySchema = z.object({
  unv_cd: z.string().describe('대학/캠퍼스 구분 단위의 고유 코드.'),
  display_name: z.string().describe('캠퍼스까지 포함한 표시 이름. 예: 제주대학교[본교].'),
  canonical_name: z.string().describe('캠퍼스 표기를 제거한 표준 대학 이름.'),
  homepage: z.string().nullable().describe('대학 공식 홈페이지 주소.'),
  admission_homepage: z.string().nullable().describe('대학 입학처/입시 홈페이지 주소.'),
  extra_material_file_id: z.string().nullable().describe('수집 자료를 묶은 파일 식별자.'),
  criteria_years: z.string().nullable().describe('보유한 심사기준 연도 목록.'),
  result_years: z.string().nullable().describe('보유한 입시결과 연도 목록.'),
  extra_material_count: z.number().int().describe('수집·보관 중인 입시 자료 파일 수.'),
  has_admission_guide: z.boolean().describe('입시요강 자료 보유 여부.'),
  university_site_material_count: z.number().int().describe('대학 사이트에서 직접 수집한 자료 수.'),
});

const StageElementSchema = z.object({
  name: z.string().describe('전형 요소 이름. 예: 학생부교과, 면접평가.'),
  weight_percent: z.number().nullable().describe('해당 요소의 반영 비율(%). 명시되지 않으면 null.'),
});

const StageSchema = z.object({
  stage: z.string().describe('전형 단계 이름. 예: 일괄, 1단계, 2단계.'),
  method: z.string().describe('단계의 대표 전형 방식.'),
  multiple: z.number().nullable().describe('단계별 선발 인원 배수. 명시되지 않으면 null.'),
  elements: z.array(StageElementSchema).describe('단계에서 반영하는 전형 요소와 비율.'),
});

const EvaluationSchema = z.object({
  element: z.string().describe('평가 요소. 예: 인성, 수학능력시험.'),
  criteria: z.string().describe('평가 기준/산출 방법 설명.'),
  quote: z.string().describe('평가 기준을 근거하는 원문 인용.'),
});

const MetricSchema = z.object({
  name: z.string().describe('수치 이름. 예: 모집인원, 경쟁률, 최초합격자 학생부 등급 평균.'),
  value: z.string().describe('수치 값. 원문 단위를 보존하기 위해 문자열로 반환.'),
  unit: z.string().describe('수치 단위. 예: 명, 점, 등급, :1. 없으면 빈 문자열.'),
});

const EvidenceSchema = z.object({
  locator: z.string().describe('원본 문서 위치. 예: page 4.'),
  quote: z.string().describe('정보 추출 근거가 되는 원문 인용.'),
});

// 정규화 결과 원본이다. 품질 검증과 LLM 활용을 위해 payload 그대로 반환한다.
const PayloadSchema = z.object({
  record_type: RecordTypeSchema.describe('레코드 종류. criteria=심사기준, result=입시결과, other=기타 안내.'),
  university_name: z.string().describe('정규화 당시 파악한 대학 이름.'),
  admission_year: z.number().int().nullable().describe('입시 연도(학년도).'),
  admission_round: z.string().nullable().describe('모집시기. 수시, 정시 등.'),
  selection_name: z.string().nullable().describe('원문에 나온 하위 전형명.'),
  recruitment_unit: z.string().nullable().describe('모집 단위/학과. 예: 소프트웨어학부, 전 모집단위.'),
  eligibility: z.array(z.string()).optional().describe('지원자격 조건 문구.'),
  stages: z.array(StageSchema).optional().describe('전형 단계, 방식, 요소별 반영 비율.'),
  sat_minimum: z.object({
    applies: z.boolean().nullable().describe('수능 최저 적용 여부. 판단할 수 없으면 null.'),
    text: z.string().describe('수능 최저 기준 원문 설명.'),
  }).nullable().optional().describe('수능 최저학력기준 정보.'),
  evaluation: z.array(EvaluationSchema).optional().describe('평가 요소, 기준, 원문 근거.'),
  documents: z.array(z.string()).optional().describe('제출 서류 문구.'),
  metrics: z.array(MetricSchema).optional().describe('모집인원, 경쟁률, 합격자 성적 등 수치.'),
  evidence: z.array(EvidenceSchema).optional().describe('원본 문서 위치와 인용 문구.'),
  confidence: z.number().nullable().describe('추출 신뢰도. 0~1.'),
  notes: z.array(z.string()).optional().describe('원문에서 추출한 참고 사항.'),
}).passthrough();
type Payload = z.infer<typeof PayloadSchema>;

const AdmissionRecordSchema = z.object({
  id: z.number().int().describe('입시 레코드 고유 번호.'),
  unv_cd: z.string().describe('대학/캠퍼스 고유 코드.'),
  university_name: z.string().describe('대학 이름.'),
  record_type: RecordTypeSchema.describe('레코드 종류. criteria=심사기준, result=입시결과, other=기타 안내.'),
  admission_year: z.number().int().nullable().describe('입시 연도(학년도).'),
  admission_round: z.string().nullable().describe('모집시기. 수시, 정시 등.'),
  selection_name: z.string().nullable().describe('원문에 나온 하위 전형명.'),
  selection_method: SelectionMethodSchema.describe('주 전형요소 표준 분류.'),
  selection_target: SelectionTargetSchema.describe('선발 대상 표준 분류.'),
  quota_type: QuotaTypeSchema.nullable().describe('정원 구분. 문서에 근거가 없으면 null.'),
  recruitment_unit: z.string().nullable().describe('모집 단위/학과. 예: 소프트웨어학부, 전 모집단위.'),
  confidence: z.number().nullable().describe('추출 신뢰도. 0~1.'),
  source: z.string().describe('원본 문서 경로.'),
  document_hint: z.string().nullable().describe('추출 작업에 사용한 문서 종류 힌트.'),
  model: z.string().nullable().describe('정규화에 사용한 AI 모델 이름.'),
  payload: PayloadSchema.describe('정규화된 원본 결과. 지원자격, 전형 단계, 평가 기준, 수치, 원문 근거를 포함한다.'),
});

const ResponseSchema = z.object({
  request: RequestSchema.describe('실제 적용된 조회 조건.'),
  universities: z.array(UniversitySchema).describe('이름 조건과 매칭된 대학/캠퍼스 목록.'),
  records: z.array(AdmissionRecordSchema).describe('조건에 맞는 입시 레코드 전체. 정규화 원본 payload를 포함한다.'),
  summaries: z.array(z.object({
    unv_cd: z.string().describe('대학/캠퍼스 고유 코드.'),
    display_name: z.string().describe('대학/캠퍼스 표시 이름.'),
    total: z.number().int().describe('조건에 맞는 전체 레코드 수.'),
    criteria: z.number().int().describe('심사기준 레코드 수.'),
    result: z.number().int().describe('입시결과 레코드 수.'),
    other: z.number().int().describe('기타 안내 레코드 수.'),
    years: z.record(z.string(), z.number().int()).describe('연도별 레코드 수.'),
    rounds: z.record(z.string(), z.number().int()).describe('수시/정시 등 모집시기별 레코드 수.'),
    selection_methods: z.record(z.string(), z.number().int()).describe('주 전형요소별 레코드 수.'),
    selection_targets: z.record(z.string(), z.number().int()).describe('선발 대상별 레코드 수.'),
    quota_types: z.record(z.string(), z.number().int()).describe('정원 구분별 레코드 수.'),
  })).describe('대학별 조회 결과 요약. LLM이 하위 전형 분포를 파악하는 데 사용.'),
  not_found: z.array(z.string()).describe('매칭되지 않은 입력 대학 이름.'),
});

const UniversitiesListResponseSchema = z.object({
  universities: z.array(UniversitySchema).describe('검색 결과 대학 목록.'),
  total: z.number().int().describe('검색 조건에 맞는 전체 대학 수.'),
  page: z.number().int().describe('현재 페이지 번호.'),
  page_size: z.number().int().describe('페이지당 반환 개수.'),
});

const RoundsResponseSchema = z.object({
  university: UniversitySchema.describe('조회한 대학/캠퍼스 정보.'),
  rounds: z.array(z.object({
    admission_year: z.number().int().nullable().describe('입시 연도(학년도).'),
    admission_round: z.string().describe('모집시기. 수시, 정시 등.'),
    record_count: z.number().int().describe('해당 연도·모집시기 레코드 수.'),
    selection_count: z.number().int().describe('서로 다른 하위 전형 수.'),
  })).describe('연도×모집시기별 보유 자료 요약.'),
});

const SelectionsResponseSchema = z.object({
  university: UniversitySchema.describe('조회한 대학/캠퍼스 정보.'),
  selections: z.array(z.object({
    selection_name: z.string().describe('원문에 나온 하위 전형명.'),
    admission_year: z.number().int().nullable().describe('입시 연도(학년도).'),
    admission_round: z.string().describe('모집시기.'),
    selection_method: SelectionMethodSchema.describe('주 전형요소 표준 분류.'),
    selection_target: SelectionTargetSchema.describe('선발 대상 표준 분류.'),
    quota_type: QuotaTypeSchema.nullable().describe('정원 구분. 근거가 없으면 null.'),
    record_count: z.number().int().describe('같은 전형 조합에 속하는 레코드 수.'),
    sample_record_id: z.number().int().describe('상세 조회용 대표 레코드 ID.'),
  })).describe('하위 전형 목록과 표준 분류.'),
});

const RecordResponseSchema = z.object({
  record: AdmissionRecordSchema.describe('입시 레코드 상세 정보. 정규화 원본 payload를 포함한다.'),
});

const app = new OpenAPIHono<{ Bindings: Env }>({
  // 검증 실패도 API 사용자가 바로 이해할 수 있게 한국어로 응답한다.
  defaultHook: (result, c) => {
    if (!result.success) {
      return c.json({
        error: '요청 값이 올바르지 않습니다.',
        details: result.error.issues.map(issue => ({
          path: issue.path.join('.'),
          message: issue.message,
        })),
      }, 400);
    }
  },
});

const healthRoute = createRoute({
  method: 'get',
  path: '/health',
  summary: 'API 상태 확인',
  description: 'Worker와 D1 데이터베이스가 정상적으로 응답하는지 확인합니다.',
  tags: ['시스템'],
  responses: {
    200: {
      description: '정상',
      content: {
        'application/json': {
          schema: z.object({ ok: z.boolean().describe('API와 D1 조회가 정상이면 true.') }),
        },
      },
    },
    500: { description: '데이터베이스 오류', content: { 'application/json': { schema: ErrorResponseSchema } } },
  },
});

app.openapi(healthRoute, async c => {
  try {
    const row = await c.env.DB.prepare('SELECT 1 = 1 AS ok').first('ok');
    if (row !== 1) throw new Error('D1 조회 결과가 예상과 다릅니다.');
    return c.json({ ok: true }, 200);
  } catch {
    return c.json({ error: 'D1 데이터베이스 상태 확인에 실패했습니다.' }, 500);
  }
});

// 대학 목록 조회 — 검색어(q)와 페이지네이션 지원.
const universitiesListRoute = createRoute({
  method: 'get',
  path: '/universities',
  summary: '대학 목록 조회',
  description: '대학 코드, 표시 이름, 캠퍼스별 별칭 대상, 입시 자료 보유 현황을 페이지로 조회합니다. 검색어는 표시 이름·표준 이름·별칭에 부분 일치로 적용됩니다.',
  tags: ['대학'],
  request: {
    query: z.object({
      q: z.string().trim().min(1, '검색어는 비워 둘 수 없습니다.').optional().describe('표시 이름, 표준 이름, 등록 별칭에 부분 일치하는 검색어.'),
      page: z.coerce.number().int().min(1, '페이지는 1 이상이어야 합니다.').default(1).describe('페이지 번호.'),
      page_size: z.coerce.number().int().min(1, '페이지 크기는 1 이상이어야 합니다.').max(100, '페이지 크기는 최대 100까지 가능합니다.').default(20).describe('페이지당 대학 개수.'),
    }),
  },
  responses: {
    200: { description: '대학 목록', content: { 'application/json': { schema: UniversitiesListResponseSchema } } },
    400: { description: '잘못된 요청', content: { 'application/json': { schema: ErrorResponseSchema } } },
    500: { description: '서버 오류', content: { 'application/json': { schema: ErrorResponseSchema } } },
  },
});

app.openapi(universitiesListRoute, async c => {
  const { q, page, page_size } = c.req.valid('query');
  try {
    // LIKE 검색어의 와일드카드 문자를 이스케이프한다.
    const escaped = q?.replace(/[\\%_]/g, m => '\\' + m);
    const where = q
      ? `WHERE u.display_name LIKE ? ESCAPE '\\' OR u.canonical_name LIKE ? ESCAPE '\\' OR EXISTS (SELECT 1 FROM university_aliases a WHERE a.unv_cd = u.unv_cd AND a.alias LIKE ? ESCAPE '\\')`
      : '';
    const like = escaped ? `%${escaped}%` : null;
    const params = like ? [like, like, like] : [];

    const countRow = await c.env.DB.prepare(
      `SELECT COUNT(*) as total FROM universities u ${where}`,
    ).bind(...params).first<{ total: number }>();
    const total = countRow?.total ?? 0;

    const result = await c.env.DB.prepare(
      `SELECT u.* FROM universities u ${where} ORDER BY u.display_name LIMIT ? OFFSET ?`,
    ).bind(...params, page_size, (page - 1) * page_size).all<UniversityRow>();
    const universities = (result.results ?? []).map(({ has_admission_guide, ...row }) => ({
      ...row,
      has_admission_guide: has_admission_guide === 1,
    }));

    return c.json({ universities, total, page, page_size }, 200);
  } catch {
    return c.json({ error: '대학 목록 조회에 실패했습니다.' }, 500);
  }
});

// 대학별 수시/정시 라운드 요약 — 연도 × 모집시기별 레코드/전형 수.
const universityRoundsRoute = createRoute({
  method: 'get',
  path: '/universities/{unvCd}/rounds',
  summary: '대학별 모집시기 요약 조회',
  description: '연도×수시/정시 조합별 레코드 수와 전형 수를 조회합니다.',
  tags: ['모집시기'],
  request: {
    params: z.object({ unvCd: z.string().trim().min(1, '대학 코드는 비워 둘 수 없습니다.').describe('대학/캠퍼스 고유 코드.') }),
    query: z.object({
      year: z.coerce.number().int().min(2018).max(2028).optional().describe('입시 연도(학년도). 생략하면 전체.'),
    }),
  },
  responses: {
    200: { description: '대학의 연도별 수시/정시 요약', content: { 'application/json': { schema: RoundsResponseSchema } } },
    400: { description: '잘못된 요청', content: { 'application/json': { schema: ErrorResponseSchema } } },
    404: { description: '대학 없음', content: { 'application/json': { schema: ErrorResponseSchema } } },
    500: { description: '서버 오류', content: { 'application/json': { schema: ErrorResponseSchema } } },
  },
});

type RoundRow = {
  admission_year: number | null;
  admission_round: string;
  record_count: number;
  selection_count: number;
};

type SelectionClassRow = {
  selection_method: z.infer<typeof SelectionMethodSchema>;
  selection_target: z.infer<typeof SelectionTargetSchema>;
  quota_type: z.infer<typeof QuotaTypeSchema> | null;
};

app.openapi(universityRoundsRoute, async c => {
  const { unvCd } = c.req.valid('param');
  const { year } = c.req.valid('query');
  try {
    const university = await c.env.DB.prepare(
      'SELECT * FROM universities WHERE unv_cd = ?',
    ).bind(unvCd).first<UniversityRow>();
    if (!university) return c.json({ error: '대학을 찾을 수 없습니다.' }, 404);

    const where = year !== undefined ? 'AND admission_year = ?' : '';
    const params = year !== undefined ? [unvCd, year] : [unvCd];
    const result = await c.env.DB.prepare(
      `SELECT admission_year, admission_round, COUNT(*) as record_count,
              COUNT(DISTINCT selection_name) as selection_count
       FROM admission_records
       WHERE unv_cd = ? ${where}
       GROUP BY admission_year, admission_round
       ORDER BY admission_year DESC, admission_round`,
    ).bind(...params).all<RoundRow>();

    const { has_admission_guide, ...u } = university;
    return c.json({
      university: { ...u, has_admission_guide: has_admission_guide === 1 },
      rounds: result.results ?? [],
    }, 200);
  } catch {
    return c.json({ error: '대학 모집시기 정보 조회에 실패했습니다.' }, 500);
  }
});

// 대학별 전형 목록 — 전형명 × 연도 × 모집시기별 레코드 수와 대표 레코드 ID.
const universitySelectionsRoute = createRoute({
  method: 'get',
  path: '/universities/{unvCd}/selections',
  summary: '대학별 전형 목록 조회',
  description: '전형명×연도×모집시기×표준 분류 조합별 레코드 수와 대표 레코드 ID를 조회합니다. 주 전형요소, 선발 대상, 정원 구분으로 좁힐 수 있습니다.',
  tags: ['전형'],
  request: {
    params: z.object({ unvCd: z.string().trim().min(1, '대학 코드는 비워 둘 수 없습니다.').describe('대학/캠퍼스 고유 코드.') }),
    query: z.object({
      year: z.coerce.number().int().min(2018).max(2028).optional().describe('입시 연도(학년도). 생략하면 전체.'),
      round: RoundSchema.optional().describe('모집시기. 수시, 정시, 기타, 미상.'),
      selection_method: SelectionMethodSchema.optional().describe('주 전형요소 표준 분류.'),
      selection_target: SelectionTargetSchema.optional().describe('선발 대상 표준 분류.'),
      quota_type: QuotaTypeSchema.optional().describe('정원 구분. 정원내, 정원외.'),
    }),
  },
  responses: {
    200: { description: '대학의 전형 목록', content: { 'application/json': { schema: SelectionsResponseSchema } } },
    400: { description: '잘못된 요청', content: { 'application/json': { schema: ErrorResponseSchema } } },
    404: { description: '대학 없음', content: { 'application/json': { schema: ErrorResponseSchema } } },
    500: { description: '서버 오류', content: { 'application/json': { schema: ErrorResponseSchema } } },
  },
});

type SelectionRow = {
  selection_name: string;
  admission_year: number | null;
  admission_round: string;
  selection_method: SelectionClassRow['selection_method'];
  selection_target: SelectionClassRow['selection_target'];
  quota_type: SelectionClassRow['quota_type'];
  record_count: number;
  sample_record_id: number;
};

app.openapi(universitySelectionsRoute, async c => {
  const { unvCd } = c.req.valid('param');
  const { year, round, selection_method, selection_target, quota_type } = c.req.valid('query');
  try {
    const university = await c.env.DB.prepare(
      'SELECT * FROM universities WHERE unv_cd = ?',
    ).bind(unvCd).first<UniversityRow>();
    if (!university) return c.json({ error: '대학을 찾을 수 없습니다.' }, 404);

    const where = ['unv_cd = ?', 'selection_name IS NOT NULL'];
    const params: (string | number)[] = [unvCd];
    if (year !== undefined) {
      where.push('admission_year = ?');
      params.push(year);
    }
    if (round) {
      where.push('admission_round = ?');
      params.push(round);
    }
    if (selection_method) {
      where.push('selection_method = ?');
      params.push(selection_method);
    }
    if (selection_target) {
      where.push('selection_target = ?');
      params.push(selection_target);
    }
    if (quota_type) {
      where.push('quota_type = ?');
      params.push(quota_type);
    }
    const result = await c.env.DB.prepare(
      `SELECT selection_name, admission_year, admission_round, selection_method, selection_target, quota_type,
              COUNT(*) as record_count, MIN(id) as sample_record_id
       FROM admission_records
       WHERE ${where.join(' AND ')}
       GROUP BY selection_name, admission_year, admission_round, selection_method, selection_target, quota_type
       ORDER BY admission_year DESC, admission_round, selection_method, selection_target, quota_type, selection_name`,
    ).bind(...params).all<SelectionRow>();

    const { has_admission_guide, ...u } = university;
    return c.json({
      university: { ...u, has_admission_guide: has_admission_guide === 1 },
      selections: result.results ?? [],
    }, 200);
  } catch {
    return c.json({ error: '대학 전형 목록 조회에 실패했습니다.' }, 500);
  }
});

// 단일 레코드 상세 — 정규화 원본 payload를 그대로 반환한다.
const recordDetailRoute = createRoute({
  method: 'get',
  path: '/records/{id}',
  summary: '입시 레코드 상세 조회',
  description: '단일 레코드의 표준 분류와 정규화 원본 payload를 함께 반환합니다. 지원자격, 전형 단계, 수능 최저, 평가 기준, 근거 문구는 payload 안에 있습니다.',
  tags: ['전형'],
  request: {
    params: z.object({ id: z.coerce.number().int().min(1, '레코드 ID는 1 이상이어야 합니다.').describe('입시 레코드 고유 번호.') }),
  },
  responses: {
    200: { description: '입시 레코드 상세', content: { 'application/json': { schema: RecordResponseSchema } } },
    400: { description: '잘못된 요청', content: { 'application/json': { schema: ErrorResponseSchema } } },
    404: { description: '레코드 없음', content: { 'application/json': { schema: ErrorResponseSchema } } },
    500: { description: '서버 오류', content: { 'application/json': { schema: ErrorResponseSchema } } },
  },
});

app.openapi(recordDetailRoute, async c => {
  const { id } = c.req.valid('param');
  try {
    const row = await c.env.DB.prepare(
      'SELECT * FROM admission_records WHERE id = ?',
    ).bind(id).first<AdmissionRecordRow>();
    if (!row) return c.json({ error: '레코드를 찾을 수 없습니다.' }, 404);

    const payload = JSON.parse(row.payload) as Payload;
    return c.json({ record: { ...row, payload } }, 200);
  } catch {
    return c.json({ error: '레코드 조회에 실패했습니다.' }, 500);
  }
});

const universityInfoRoute = createRoute({
  method: 'post',
  path: '/universities/info',
  summary: '대학 입시 정보 통합 조회',
  description: '대학 이름을 최대 10개까지 받아 심사기준·입시결과 레코드와 대학 요약을 반환합니다. 레코드 종류, 연도, 모집시기, 표준 전형 분류로 필터할 수 있습니다.',
  tags: ['대학'],
  request: { body: { required: true, content: { 'application/json': { schema: RequestSchema } } } },
  responses: {
    200: { description: '대학별 입시 정보', content: { 'application/json': { schema: ResponseSchema } } },
    400: { description: '잘못된 요청', content: { 'application/json': { schema: ErrorResponseSchema } } },
    500: { description: '서버 오류', content: { 'application/json': { schema: ErrorResponseSchema } } },
  },
});

type UniversityRow = {
  unv_cd: string;
  display_name: string;
  canonical_name: string;
  homepage: string | null;
  admission_homepage: string | null;
  extra_material_file_id: string | null;
  criteria_years: string | null;
  result_years: string | null;
  extra_material_count: number;
  has_admission_guide: number;
  university_site_material_count: number;
};

type AdmissionRecordRow = {
  id: number;
  unv_cd: string;
  university_name: string;
  record_type: 'criteria' | 'result' | 'other';
  admission_year: number | null;
  admission_round: string | null;
  selection_name: string | null;
  selection_method: SelectionClassRow['selection_method'];
  selection_target: SelectionClassRow['selection_target'];
  quota_type: SelectionClassRow['quota_type'];
  recruitment_unit: string | null;
  confidence: number | null;
  source: string;
  document_hint: string | null;
  model: string | null;
  payload: string;
};

// MCP 도구는 HTTP API와 같은 D1 조회를 사용한다. 응답은 MCP 텍스트 콘텐츠로 감싼다.
function toolJson(value: unknown) {
  return { content: [{ type: 'text' as const, text: JSON.stringify(value, null, 2) }] };
}

function registerAdmissionTools(server: McpServer, db: D1Database) {
  // 통합 조회 도구: 여러 대학/하위 전형을 일일이 조회하지 않고 한 번에 받는다.
  server.registerTool('get_university_info', {
    title: '대학 입시 정보 통합 조회',
    description: '대학 이름 목록과 연도·모집시기·전형 분류 조건으로 일치하는 모든 하위 전형 레코드를 한 번에 반환합니다. 여러 전형을 하나씩 조회할 필요 없이 이 도구를 먼저 사용하세요.',
    inputSchema: RequestSchema.shape,
  }, async input => {
    const response = await app.request('/universities/info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    }, { DB: db });
    const value = await response.json() as Record<string, unknown>;
    return toolJson(value);
  });

  server.registerTool('search_universities', {
    title: '대학 검색',
    description: '이름이나 코드로 대학을 검색하고 캠퍼스 코드, 표준 이름, 입시 자료 보유 현황을 반환합니다.',
    inputSchema: {
      q: z.string().trim().min(1).optional(),
      page: z.number().int().min(1).default(1),
      page_size: z.number().int().min(1).max(100).default(20),
    },
  }, async ({ q, page, page_size }) => {
    const escaped = q?.replace(/[\\%_]/g, m => '\\' + m);
    const like = escaped ? `%${escaped}%` : null;
    const where = like
      ? `WHERE u.display_name LIKE ? ESCAPE '\\' OR u.canonical_name LIKE ? ESCAPE '\\' OR EXISTS (SELECT 1 FROM university_aliases a WHERE a.unv_cd = u.unv_cd AND a.alias LIKE ? ESCAPE '\\')`
      : '';
    const params = like ? [like, like, like] : [];
    const count = await db.prepare(`SELECT COUNT(*) as total FROM universities u ${where}`).bind(...params).first<{ total: number }>();
    const result = await db.prepare(
      `SELECT u.* FROM universities u ${where} ORDER BY u.display_name LIMIT ? OFFSET ?`,
    ).bind(...params, page_size, (page - 1) * page_size).all<UniversityRow>();
    return toolJson({ total: count?.total ?? 0, page, page_size, universities: result.results ?? [] });
  });

  server.registerTool('list_university_selections', {
    title: '대학 전형 목록',
    description: '대학 코드로 전형 목록을 조회합니다. 연도, 모집시기, 주 전형요소, 선발 대상, 정원 구분으로 필터할 수 있습니다.',
    inputSchema: {
      unv_cd: z.string().trim().min(1),
      year: z.number().int().min(2018).max(2028).optional(),
      round: RoundSchema.optional(),
      selection_method: SelectionMethodSchema.optional(),
      selection_target: SelectionTargetSchema.optional(),
      quota_type: QuotaTypeSchema.optional(),
    },
  }, async input => {
    const where = ['unv_cd = ?', 'selection_name IS NOT NULL'];
    const params: (string | number)[] = [input.unv_cd];
    if (input.year !== undefined) { where.push('admission_year = ?'); params.push(input.year); }
    if (input.round) { where.push('admission_round = ?'); params.push(input.round); }
    if (input.selection_method) { where.push('selection_method = ?'); params.push(input.selection_method); }
    if (input.selection_target) { where.push('selection_target = ?'); params.push(input.selection_target); }
    if (input.quota_type) { where.push('quota_type = ?'); params.push(input.quota_type); }
    const result = await db.prepare(
      `SELECT selection_name, admission_year, admission_round, selection_method, selection_target, quota_type,
              COUNT(*) as record_count, MIN(id) as sample_record_id
       FROM admission_records
       WHERE ${where.join(' AND ')}
       GROUP BY selection_name, admission_year, admission_round, selection_method, selection_target, quota_type
       ORDER BY admission_year DESC, admission_round, selection_method, selection_target, quota_type, selection_name`,
    ).bind(...params).all<SelectionRow>();
    return toolJson({ selections: result.results ?? [] });
  });

  server.registerTool('get_admission_record', {
    title: '입시 레코드 상세',
    description: '레코드 ID로 지원자격, 전형 단계, 수능 최저, 평가 기준, 문서 근거까지 반환합니다.',
    inputSchema: { id: z.number().int().min(1) },
  }, async ({ id }) => {
    const row = await db.prepare('SELECT * FROM admission_records WHERE id = ?').bind(id).first<AdmissionRecordRow>();
    if (!row) return toolJson({ error: '레코드를 찾을 수 없습니다.' });
    const payload = JSON.parse(row.payload) as Payload;
    return toolJson({ record: { ...row, payload } });
  });
}

async function handleMcp(raw: Request, parsedBody: unknown, db: D1Database) {
  const server = new McpServer({ name: 'university-admission-api', version: '1.4.0' });
  registerAdmissionTools(server, db);
  const transport = new WebStandardStreamableHTTPServerTransport({ sessionIdGenerator: undefined });
  await server.connect(transport);
  return transport.handleRequest(raw, { parsedBody });
}

const allowedMcpHosts = ['localhost', '127.0.0.1', '[::1]', 'university-admission-api.aside-hazle6287.workers.dev'];
const mcpApp = createMcpHonoApp({ allowedHosts: allowedMcpHosts, allowedOrigins: allowedMcpHosts });
// Host/Origin 검증과 요청 본문 파싱은 /mcp에만 적용한다.
mcpApp.all('/', c => handleMcp(c.req.raw, undefined, (c.env as Env).DB));
app.route('/mcp', mcpApp);

app.openapi(universityInfoRoute, async c => {
  const body = c.req.valid('json');
  try {
    const names = [...new Set(body.universities)];
    const nameMarks = names.map(() => '?').join(',');
    const universityResult = await c.env.DB.prepare(
      `SELECT DISTINCT u.* FROM universities u
       LEFT JOIN university_aliases a ON a.unv_cd = u.unv_cd
       WHERE u.display_name IN (${nameMarks})
          OR u.canonical_name IN (${nameMarks})
          OR a.alias IN (${nameMarks})
       ORDER BY u.unv_cd`,
    ).bind(...names, ...names, ...names).all<UniversityRow>();

    const aliasResult = await c.env.DB.prepare(
      `SELECT alias FROM university_aliases WHERE alias IN (${nameMarks})`,
    ).bind(...names).all<{ alias: string }>();

    const universities = universityResult.results ?? [];
    const displayNames = new Set(universities.map(row => row.display_name));
    const canonicalNames = new Set(universities.map(row => row.canonical_name));
    const aliasNames = new Set((aliasResult.results ?? []).map(row => row.alias));
    const notFound = names.filter(name =>
      !displayNames.has(name) && !canonicalNames.has(name) && !aliasNames.has(name),
    );

    if (universities.length === 0) {
      return c.json({ request: body, universities: [], records: [], summaries: [], not_found: notFound }, 200);
    }

    const codes = universities.map(row => row.unv_cd);
    const codeMarks = codes.map(() => '?').join(',');
    const where = [`r.unv_cd IN (${codeMarks})`];
    const params: (string | number)[] = [...codes];
    if (body.record_type) {
      where.push('r.record_type = ?');
      params.push(body.record_type);
    }
    if (body.year !== undefined) {
      where.push('r.admission_year = ?');
      params.push(body.year);
    }
    if (body.round) {
      where.push('r.admission_round = ?');
      params.push(body.round);
    }
    if (body.selection_method) {
      where.push('r.selection_method = ?');
      params.push(body.selection_method);
    }
    if (body.selection_target) {
      where.push('r.selection_target = ?');
      params.push(body.selection_target);
    }
    if (body.quota_type) {
      where.push('r.quota_type = ?');
      params.push(body.quota_type);
    }

    const recordResult = await c.env.DB.prepare(
      `SELECT r.* FROM admission_records r
       WHERE ${where.join(' AND ')}
       ORDER BY r.unv_cd, r.admission_year DESC, r.admission_round, r.selection_name, r.id`,
    ).bind(...params).all<AdmissionRecordRow>();
    const rows = recordResult.results ?? [];

    const records = rows.map(row => ({
      ...row,
      payload: JSON.parse(row.payload) as Payload,
    }));
    const summaries = universities.map(university => {
      const mine = records.filter(record => record.unv_cd === university.unv_cd);
      const years: Record<string, number> = {};
      const rounds: Record<string, number> = {};
      const methods: Record<string, number> = {};
      const targets: Record<string, number> = {};
      const quotas: Record<string, number> = {};
      const count = (map: Record<string, number>, key: string | null) => {
        if (key !== null) map[key] = (map[key] ?? 0) + 1;
      };
      for (const record of mine) {
        count(years, record.admission_year === null ? null : String(record.admission_year));
        count(rounds, record.admission_round);
        count(methods, record.selection_method);
        count(targets, record.selection_target);
        count(quotas, record.quota_type);
      }
      return {
        unv_cd: university.unv_cd,
        display_name: university.display_name,
        total: mine.length,
        criteria: mine.filter(record => record.record_type === 'criteria').length,
        result: mine.filter(record => record.record_type === 'result').length,
        other: mine.filter(record => record.record_type === 'other').length,
        years,
        rounds,
        selection_methods: methods,
        selection_targets: targets,
        quota_types: quotas,
      };
    });

    return c.json({
      request: body,
      universities: universities.map(({ has_admission_guide, ...row }) => ({
        ...row,
        has_admission_guide: has_admission_guide === 1,
      })),
      records,
      summaries,
      not_found: notFound,
    }, 200);
  } catch {
    return c.json({ error: '대학 입시 정보 조회에 실패했습니다.' }, 500);
  }
});

app.doc('/openapi', {
  openapi: '3.0.0',
  info: {
    title: '대학 입시 정보 통합 API',
    version: '1.4.0',
    description: '대학 이름으로 심사기준·입시결과 등 수집·정규화된 정보를 조회합니다.\n\nMCP 클라이언트는 같은 Worker의 /mcp 엔드포인트에 Streamable HTTP로 연결할 수 있습니다. 대학·모집시기·전형 분류 조건을 한 번에 넘기면 get_university_info 도구가 하위 전형·모집단위·전형 단계·평가 기준·근거를 통째로 반환합니다. search_universities, list_university_selections, get_admission_record는 보조 조회용입니다.',
  },
  servers: [{ url: 'https://university-admission-api.aside-hazle6287.workers.dev' }],
  tags: [
    { name: '시스템', description: '서비스 상태 확인' },
    { name: '대학', description: '대학 목록과 통합 입시 정보 조회' },
    { name: '모집시기', description: '수시/정시 단위 요약 조회' },
    { name: '전형', description: '전형 분류 목록과 레코드 상세 조회' },
  ],
});
app.get('/swagger', swaggerUI({ url: '/openapi' }));
app.get('/', c => c.redirect('/swagger'));

app.notFound(c => c.json({ error: '요청한 경로를 찾을 수 없습니다.' }, 404));
app.onError((_error, c) => c.json({ error: '서버 내부 오류가 발생했습니다.' }, 500));

export default app;
