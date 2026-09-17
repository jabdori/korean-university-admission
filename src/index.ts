import { OpenAPIHono, createRoute } from '@hono/zod-openapi';
import { swaggerUI } from '@hono/swagger-ui';
import { z } from 'zod';

type Env = { DB: D1Database };

const RecordTypeSchema = z.enum(['criteria', 'result', 'other']);
const RoundSchema = z.enum(['수시', '정시', '기타', '미상']);
const PayloadSchema = z.record(z.string(), z.unknown());

const RequestSchema = z.object({
  universities: z.array(z.string().trim().min(1, '대학 이름은 비워 둘 수 없습니다.'))
    .min(1, '대학 이름을 1개 이상 입력해주세요.')
    .max(10, '대학 이름은 최대 10개까지 조회할 수 있습니다.'),
  record_type: RecordTypeSchema.optional(),
  year: z.number().int().min(2018).max(2028).optional(),
  round: RoundSchema.optional(),
}).strict();

const ErrorResponseSchema = z.object({
  error: z.string(),
  details: z.array(z.object({ path: z.string(), message: z.string() })).optional(),
});

const UniversitySchema = z.object({
  unv_cd: z.string(),
  display_name: z.string(),
  canonical_name: z.string(),
  homepage: z.string().nullable(),
  admission_homepage: z.string().nullable(),
  extra_material_file_id: z.string().nullable(),
  criteria_years: z.string().nullable(),
  result_years: z.string().nullable(),
  extra_material_count: z.number().int(),
  has_admission_guide: z.boolean(),
  university_site_material_count: z.number().int(),
});

const AdmissionRecordSchema = z.object({
  id: z.number().int(),
  unv_cd: z.string(),
  record_type: RecordTypeSchema,
  admission_year: z.number().int().nullable(),
  admission_round: z.string().nullable(),
  selection_name: z.string().nullable(),
  recruitment_unit: z.string().nullable(),
  confidence: z.number().nullable(),
  source: z.string(),
  document_hint: z.string().nullable(),
  model: z.string().nullable(),
  payload: PayloadSchema,
});

// 정규화 payload 안의 전형 상세 필드를 최상위로 펼친 스키마.
// 원본 payload도 하위호환을 위해 함께 반환한다.
const DetailSchema = z.object({
  eligibility: z.array(z.string()).optional(),
  stages: z.array(z.record(z.string(), z.unknown())).optional(),
  sat_minimum: z.record(z.string(), z.unknown()).nullable().optional(),
  evaluation: z.array(z.record(z.string(), z.unknown())).optional(),
  documents: z.array(z.record(z.string(), z.unknown())).optional(),
  metrics: z.array(z.record(z.string(), z.unknown())).optional(),
  evidence: z.array(z.record(z.string(), z.unknown())).optional(),
  notes: z.array(z.string()).optional(),
});

const DetailedRecordSchema = AdmissionRecordSchema.merge(DetailSchema);

const ResponseSchema = z.object({
  request: RequestSchema,
  universities: z.array(UniversitySchema),
  records: z.array(DetailedRecordSchema),
  summaries: z.array(z.object({
    unv_cd: z.string(),
    display_name: z.string(),
    total: z.number().int(),
    criteria: z.number().int(),
    result: z.number().int(),
    other: z.number().int(),
    years: z.record(z.string(), z.number().int()),
    rounds: z.record(z.string(), z.number().int()),
  })),
  not_found: z.array(z.string()),
});

const UniversitiesListResponseSchema = z.object({
  universities: z.array(UniversitySchema),
  total: z.number().int(),
  page: z.number().int(),
  page_size: z.number().int(),
});

const RoundsResponseSchema = z.object({
  university: UniversitySchema,
  rounds: z.array(z.object({
    admission_year: z.number().int().nullable(),
    admission_round: z.string(),
    record_count: z.number().int(),
    selection_count: z.number().int(),
  })),
});

const SelectionsResponseSchema = z.object({
  university: UniversitySchema,
  selections: z.array(z.object({
    selection_name: z.string(),
    admission_year: z.number().int().nullable(),
    admission_round: z.string(),
    record_count: z.number().int(),
    sample_record_id: z.number().int(),
  })),
});

const RecordResponseSchema = z.object({
  record: DetailedRecordSchema,
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
  responses: {
    200: { description: '정상', content: { 'application/json': { schema: z.object({ ok: z.boolean() }) } } },
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
  request: {
    query: z.object({
      q: z.string().trim().min(1, '검색어는 비워 둘 수 없습니다.').optional(),
      page: z.coerce.number().int().min(1, '페이지는 1 이상이어야 합니다.').default(1),
      page_size: z.coerce.number().int().min(1, '페이지 크기는 1 이상이어야 합니다.').max(100, '페이지 크기는 최대 100까지 가능합니다.').default(20),
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
  request: {
    params: z.object({ unvCd: z.string().trim().min(1, '대학 코드는 비워 둘 수 없습니다.') }),
    query: z.object({
      year: z.coerce.number().int().min(2018).max(2028).optional(),
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
  request: {
    params: z.object({ unvCd: z.string().trim().min(1, '대학 코드는 비워 둘 수 없습니다.') }),
    query: z.object({
      year: z.coerce.number().int().min(2018).max(2028).optional(),
      round: RoundSchema.optional(),
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
  record_count: number;
  sample_record_id: number;
};

app.openapi(universitySelectionsRoute, async c => {
  const { unvCd } = c.req.valid('param');
  const { year, round } = c.req.valid('query');
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
    const result = await c.env.DB.prepare(
      `SELECT selection_name, admission_year, admission_round, COUNT(*) as record_count, MIN(id) as sample_record_id
       FROM admission_records
       WHERE ${where.join(' AND ')}
       GROUP BY selection_name, admission_year, admission_round
       ORDER BY admission_year DESC, admission_round, selection_name`,
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

// 단일 레코드 상세 — payload의 전형 상세(단계, 지원자격 등)를 최상위로 펼쳐 반환.
const recordDetailRoute = createRoute({
  method: 'get',
  path: '/records/{id}',
  request: {
    params: z.object({ id: z.coerce.number().int().min(1, '레코드 ID는 1 이상이어야 합니다.') }),
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

    const payload = JSON.parse(row.payload) as Record<string, unknown>;
    return c.json({ record: { ...row, payload, ...pickDetail(payload) } }, 200);
  } catch {
    return c.json({ error: '레코드 조회에 실패했습니다.' }, 500);
  }
});

const universityInfoRoute = createRoute({
  method: 'post',
  path: '/universities/info',
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
  record_type: 'criteria' | 'result' | 'other';
  admission_year: number | null;
  admission_round: string | null;
  selection_name: string | null;
  recruitment_unit: string | null;
  confidence: number | null;
  source: string;
  document_hint: string | null;
  model: string | null;
  payload: string;
};

// payload에서 전형 상세 필드만 골라 최상위로 펼친다.
function pickDetail(payload: Record<string, unknown>) {
  const keys = ['eligibility', 'stages', 'sat_minimum', 'evaluation', 'documents', 'metrics', 'evidence', 'notes'] as const;
  const detail: Record<string, unknown> = {};
  for (const key of keys) {
    if (payload[key] !== undefined) detail[key] = payload[key];
  }
  return detail;
}

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

    const recordResult = await c.env.DB.prepare(
      `SELECT r.* FROM admission_records r
       WHERE ${where.join(' AND ')}
       ORDER BY r.unv_cd, r.admission_year DESC, r.admission_round, r.selection_name, r.id`,
    ).bind(...params).all<AdmissionRecordRow>();
    const rows = recordResult.results ?? [];

    const records = rows.map(row => {
      const payload = JSON.parse(row.payload) as Record<string, unknown>;
      return {
      ...row,
      payload,
      ...pickDetail(payload),
      };
    });
    const summaries = universities.map(university => {
      const mine = records.filter(record => record.unv_cd === university.unv_cd);
      const years: Record<string, number> = {};
      const rounds: Record<string, number> = {};
      const count = (map: Record<string, number>, key: string | null) => {
        if (key !== null) map[key] = (map[key] ?? 0) + 1;
      };
      for (const record of mine) {
        count(years, record.admission_year === null ? null : String(record.admission_year));
        count(rounds, record.admission_round);
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
    version: '1.0.0',
    description: '대학 이름으로 심사기준·입시결과 등 수집·정규화된 정보를 조회합니다.',
  },
});
app.get('/swagger', swaggerUI({ url: '/openapi' }));
app.get('/', c => c.redirect('/swagger'));

app.notFound(c => c.json({ error: '요청한 경로를 찾을 수 없습니다.' }, 404));
app.onError((_error, c) => c.json({ error: '서버 내부 오류가 발생했습니다.' }, 500));

export default app;
