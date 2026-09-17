-- 대학 마스터: 캠퍼스별 고유 코드(unv_cd)를 기본 키로 사용한다.
CREATE TABLE universities (
  unv_cd TEXT PRIMARY KEY,
  display_name TEXT NOT NULL UNIQUE,
  canonical_name TEXT NOT NULL,
  homepage TEXT,
  admission_homepage TEXT,
  extra_material_file_id TEXT,
  criteria_years TEXT,
  result_years TEXT,
  extra_material_count INTEGER NOT NULL DEFAULT 0,
  has_admission_guide INTEGER NOT NULL DEFAULT 0,
  university_site_material_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_universities_canonical_name ON universities(canonical_name);

-- 표시 이름/본교 축약 이름 등 검색용 별칭. 중복 별칭은 의미가 없으므로 무시한다.
CREATE TABLE university_aliases (
  alias TEXT PRIMARY KEY,
  unv_cd TEXT NOT NULL,
  FOREIGN KEY(unv_cd) REFERENCES universities(unv_cd) ON DELETE CASCADE
);

CREATE INDEX idx_university_aliases_unv_cd ON university_aliases(unv_cd);

-- 정규화 결과 필터 컬럼과 원본 payload를 함께 보관한다.
CREATE TABLE admission_records (
  id INTEGER PRIMARY KEY,
  unv_cd TEXT NOT NULL,
  university_name TEXT NOT NULL,
  record_type TEXT NOT NULL,
  admission_year INTEGER,
  admission_round TEXT,
  selection_name TEXT,
  recruitment_unit TEXT,
  confidence REAL,
  source TEXT NOT NULL,
  document_hint TEXT,
  model TEXT,
  payload TEXT NOT NULL,
  FOREIGN KEY(unv_cd) REFERENCES universities(unv_cd) ON DELETE CASCADE
);

CREATE INDEX idx_admission_records_university
  ON admission_records(unv_cd);
CREATE INDEX idx_admission_records_filters
  ON admission_records(unv_cd, record_type, admission_year, admission_round);
