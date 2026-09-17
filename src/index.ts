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

const ResponseSchema = z.object({
  request: RequestSchema,
  universities: z.array(UniversitySchema),
  records: z.array(AdmissionRecordSchema),
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

    const records = rows.map(row => ({
      ...row,
      payload: JSON.parse(row.payload) as Record<string, unknown>,
    }));
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
