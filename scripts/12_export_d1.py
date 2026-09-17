# -*- coding: utf-8 -*-
"""12: 정규화 결과 → D1 seed SQL 내보내기."""
import csv
import json
import re
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
UNIVS = PROJ / "normalized/univs.csv"
COVERAGE = PROJ / "normalized/coverage.csv"
RESULTS = PROJ / "normalized/agent_results.jsonl"
OUT = PROJ / ".d1/seed"
CHUNK = 50


def sql(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def values(rows):
    return ",\n".join("(" + ",".join(sql(v) for v in row) + ")" for row in rows)


def canonical_name(display_name):
    # 마지막 캠퍼스 분류 태그만 제거하고 괄호 캠퍼스명은 유지한다.
    return re.sub(r"\[[^]]+\]$", "", display_name)


def aliases(canonical, display):
    result = {display, canonical + re.sub(r"^.*\[|\]$", "", display)}
    if "(" in canonical:
        name, suffix = canonical.split("(", 1)
        suffix = suffix.rstrip(")")
        result.update((f"{name} {suffix}", f"{name}_{suffix}"))
    result.discard("")
    return result


def load_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    univ_rows = load_csv(UNIVS)
    coverage = {row["unvCd"]: row for row in load_csv(COVERAGE)}
    if len(univ_rows) != 202 or len(coverage) != 202:
        raise ValueError("대학 마스터 또는 커버리지가 202개가 아닙니다")

    universities = []
    alias_rows = []
    by_display = {}
    by_canonical = {}
    by_alias = {}
    for row in univ_rows:
        cov = coverage[row["unvCd"]]
        display = row["대학명"]
        canonical = canonical_name(display)
        if display in by_display:
            raise ValueError(f"대학 표시 이름 중복: {display}")
        universities.append((
            row["unvCd"], display, canonical, row["홈페이지"], row["입시홈페이지"],
            row["추가안내자료_fileId"], cov["심사기준_연도"], cov["입결_연도"],
            int(cov["추가안내자료_파일수"]), 1 if cov["모집요강_포함"] == "Y" else 0,
            int(cov["대학사이트자료_파일수"]),
        ))
        by_display[display] = row["unvCd"]
        by_canonical.setdefault(canonical, []).append(row["unvCd"])
        for alias in aliases(canonical, display):
            alias_rows.append((alias, row["unvCd"]))
            by_alias.setdefault(alias, row["unvCd"])

    def university_code(name):
        if name in by_display:
            return by_display[name]
        codes = by_canonical.get(name, [])
        if len(codes) == 1:
            return codes[0]
        if name in by_alias:
            return by_alias[name]
        # 캠퍼스 미표기 record는 본교 코드로 귀속시킨다. 조회는 canonical_name으로 캠퍼스 전체가 나간다.
        main = [display for display, code in by_display.items()
                if code in codes and display.endswith("[본교]")]
        return by_display[main[0]] if len(main) == 1 else None

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.sql"):
        old.unlink()

    with (OUT / "0000_reset.sql").open("w", encoding="utf-8") as f:
        f.write("DELETE FROM admission_records;\n")
        f.write("DELETE FROM university_aliases;\n")
        f.write("DELETE FROM universities;\n")
        f.write("INSERT INTO universities VALUES\n" + values(universities) + ";\n")
        f.write("INSERT OR IGNORE INTO university_aliases VALUES\n" +
                values(alias_rows) + ";\n")

    records = []
    missing = set()
    with RESULTS.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            task = json.loads(line)
            for record in task["records"]:
                name = str(record.get("university_name", ""))
                code = university_code(name)
                if not code:
                    missing.add(name)
                    continue
                year = record.get("admission_year")
                confidence = record.get("confidence")
                records.append((
                    len(records) + 1, code, name,
                    record.get("record_type", "other"),
                    int(year) if year is not None else None,
                    record.get("admission_round"),
                    record.get("selection_name"), record.get("recruitment_unit"),
                    float(confidence) if confidence is not None else None,
                    task["source"], task.get("document_hint"), task.get("model"),
                    json.dumps(record, ensure_ascii=False, separators=(",", ":")),
                ))

    if missing:
        raise ValueError(f"대학 코드를 찾을 수 없음: {sorted(missing)}")

    for i, start in enumerate(range(0, len(records), CHUNK), 1):
        path = OUT / f"{i:04d}_records.sql"
        with path.open("w", encoding="utf-8") as f:
            f.write("INSERT INTO admission_records VALUES\n" +
                    values(records[start:start + CHUNK]) + ";\n")

    # Wrangler 호출 1회로 전체 seed를 적용할 수 있게 통합 파일도 만든다.
    with (OUT / "all.sql").open("wb") as combined:
        for path in sorted(OUT.glob("*.sql")):
            combined.write(path.read_bytes())

    print(f"내보내기 완료: 대학 {len(universities)}, 별칭 {len(alias_rows)}, records {len(records)}")


if __name__ == "__main__":
    main()
