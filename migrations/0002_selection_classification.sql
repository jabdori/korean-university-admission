-- 전형 분류 체계: 주 전형요소, 선발 대상, 정원 구분.
-- quota_type은 문서에 근거가 없으면 NULL을 허용한다.
ALTER TABLE admission_records ADD COLUMN selection_method TEXT;
ALTER TABLE admission_records ADD COLUMN selection_target TEXT;
ALTER TABLE admission_records ADD COLUMN quota_type TEXT;

CREATE INDEX idx_admission_records_selection_method
  ON admission_records(unv_cd, selection_method);
CREATE INDEX idx_admission_records_selection_target
  ON admission_records(unv_cd, selection_target);
CREATE INDEX idx_admission_records_quota_type
  ON admission_records(unv_cd, quota_type);
