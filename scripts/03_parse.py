# -*- coding: utf-8 -*-
"""03: cache/의 조각 HTML → 정규화 CSV.

출력:
  normalized/results_long.csv   - 입결 전체 (long: 대학×전형×모집단위×지표×값)
  normalized/results_jihak.csv  - 학생부(종합/교과) 입결 wide (12컬럼 고정 스키마)
  normalized/criteria_text.csv  - 심사기준 섹션 텍스트
"""
import csv
import html
import os
import re
import sys
from html.parser import HTMLParser

from adiga import PROJECT

YEAR = sys.argv[1] if len(sys.argv) > 1 else "2027"
CACHE_RESULT = os.path.join(PROJECT, "cache", "result", YEAR)
CACHE_SIRHA = os.path.join(PROJECT, "cache", "sirha", YEAR)

KIND_NAME = {"20": "학생부종합", "30": "학생부교과", "40": "수능위주"}


class TableParser(HTMLParser):
    """테이블 → 2차원 그리드. colspan/rowspan 처리."""

    def __init__(self):
        super().__init__()
        self.grid = []
        self._row = None
        self._cell = None
        self._pending = []  # (row_idx, col_idx, rows_left, value)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr":
            self._row = []
            self.grid.append(self._row)
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            colspan = int(a.get("colspan", 1) or 1)
            rowspan = int(a.get("rowspan", 1) or 1)
            self._row.append({"cell": self._cell, "colspan": colspan, "rowspan": rowspan})

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._cell = None
        elif tag == "tr":
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    @staticmethod
    def parse(tbl_html):
        p = TableParser()
        p.feed(tbl_html)
        # rowspan 확장 (표준 알고리즘)
        fill = {}  # (r, c) -> value
        out = []
        for r, row in enumerate(p.grid):
            out_row = []
            c = 0
            for item in row:
                while (r, c) in fill:
                    out_row.append(fill.pop((r, c)))
                    c += 1
                val = clean("".join(item["cell"]))
                for cc in range(item["colspan"]):
                    out_row.append(val)  # 현재 행은 즉시 확장
                    for rr in range(1, item["rowspan"]):
                        fill[(r + rr, c + cc)] = val
                c += item["colspan"]
            while (r, c) in fill:
                out_row.append(fill.pop((r, c)))
                c += 1
            out.append(out_row)
        return out


def clean(s):
    s = html.unescape(s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("\u00a0", " ").replace("\r", "")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\s*\n\s*", "\n", s)
    return s.strip()


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", html.unescape(s))


def split_by_junhyeong(fragment):
    """조각을 h5 전형명 기준으로 분할: [(전형명, 테이블html), ...]"""
    parts = re.split(r"<h5[^>]*>", fragment)
    out = []
    for part in parts[1:]:
        name = strip_tags(part.split("</h5>")[0]).strip()
        tbls = re.findall(r"<table.*?</table>", part, re.S)
        out.append((name, tbls[0] if tbls else None))
    return out


def parse_result_file(path, unv_cd, unv_nm, up_cd):
    rows_long = []
    rows_wide = []
    frag = open(path, encoding="utf-8").read()
    for junhyeong, tbl in split_by_junhyeong(frag):
        if not tbl:
            continue
        grid = TableParser.parse(tbl)
        if len(grid) < 2:
            continue
        # 헤더 행: '구분'로 시작하는 행부터 데이터 시작 직전까지
        h_end = 0
        for i, row in enumerate(grid):
            if row and row[0] in ("수시", "정시", "정시(가)", "정시(나)") or (row and re.match(r"정시", row[0] or "")):
                h_end = i
                break
        else:
            h_end = 3 if len(grid) > 3 else len(grid)
        headers = build_flat_headers(grid[:h_end])
        ncol = len(headers)
        for row in grid[h_end:]:
            if not row or len(row) < 3:
                continue
            if not re.match(r"수시|정시", row[0] or ""):
                continue  # 비고/주석 행
            cells = (row + [""] * ncol)[:ncol]
            # 미제출 사유 캡처: 노트 셀 이후 데이터 열은 '-' 처리
            note = ""
            note_idx = None
            for j, c in enumerate(cells):
                if "미제출" in c:
                    note = c
                    note_idx = j
                    break
            if note_idx is not None:
                cells = [c if j < note_idx else "" for j, c in enumerate(cells)]
            gibu, modan = cells[0], cells[1]
            for j, col in enumerate(headers[2:], start=2):
                v = cells[j]
                if v == "":
                    v = "-"
                elif re.match(r"^0(\.0+)?$", v.strip()) and re.search(r"환산|총점|백분위", col):
                    v = "-"  # 사이트 표시 규칙: 점수/등급 0은 미제공
                rows_long.append({
                    "unvCd": unv_cd, "대학명": unv_nm,
                    "전형구분코드": up_cd, "전형구분": KIND_NAME[up_cd],
                    "전형명": junhyeong, "모집시기": gibu, "모집단위": modan,
                    "지표": col, "값": v,
                })
            if up_cd in ("20", "30") and ncol >= 12:
                cells12 = (cells + ["-"] * 12)[:12]
                for j in range(7, 12):
                    if re.match(r"^0(\.0+)?$", (cells12[j] or "").strip()):
                        cells12[j] = "-"
                rows_wide.append({
                    "unvCd": unv_cd, "대학명": unv_nm, "전형명": junhyeong,
                    "모집시기": gibu, "모집단위": modan,
                    "모집인원_최초A": cells12[2], "모집인원_이월B": cells12[3],
                    "모집인원_최종": cells12[4], "경쟁률": cells12[5], "충원인원": cells12[6],
                    "환산점수_50": cells12[7], "환산점수_70": cells12[8],
                    "환산등급_50": cells12[9], "환산등급_70": cells12[10],
                    "총점": cells12[11], "비고": note,
                })
    return rows_long, rows_wide


def build_flat_headers(header_rows):
    """헤더 행들(2~3단)을 1차원 컬럼명 배열로 평탄화."""
    if not header_rows:
        return []
    ncol = max(len(r) for r in header_rows)
    names = [""] * ncol
    grid = [r + [""] * (ncol - len(r)) for r in header_rows]
    for c in range(ncol):
        parts = []
        for r in range(len(grid)):
            v = grid[r][c].replace("\n", " ").strip()
            if v and (not parts or parts[-1] != v):
                parts.append(v)
        names[c] = " ".join(parts) if parts else f"col{c+1}"
    return names


def parse_sirha_file(path, unv_cd, unv_nm, up_cd):
    """심사기준 조각 → 섹션 텍스트. 섹션 라벨: bold span 라벨들."""
    frag = open(path, encoding="utf-8").read()
    if len(frag) < 600:
        return []
    labels = ["전형별 주요사항", "전형별 특성", "전형별 전형요소", "평가요소 및 평가기준",
              "평가요소", "지원자격", "수능최저학력기준", "전형일정", "제출서류",
              "모집인원", "결과활용", "기타사항"]
    # 라벨 span 위치 기준 분할
    spans = []
    for m in re.finditer(r"<span[^>]*font-weight:\s*bold[^>]*>([^<]{2,20})</span>", frag):
        t = clean(m.group(1))
        if t in labels:
            spans.append((m.start(), t))
    if not spans:
        text = clean(re.sub(r"<script.*?</script>", "", frag, flags=re.S))
        return [{"unvCd": unv_cd, "대학명": unv_nm, "전형구분": KIND_NAME[up_cd],
                 "섹션": "(전체)", "내용": text}]
    rows = []
    for i, (pos, label) in enumerate(spans):
        end = spans[i + 1][0] if i + 1 < len(spans) else len(frag)
        body = frag[pos:end]
        body = re.sub(r"<script.*?</script>", "", body, flags=re.S)
        body = clean(body)
        body = body[len(label):].strip() if body.startswith(label) else body
        rows.append({"unvCd": unv_cd, "대학명": unv_nm, "전형구분": KIND_NAME[up_cd],
                     "섹션": label, "내용": body[:6000]})
    return rows


def write_csv(path, rows):
    if not rows:
        print(f"  (빈 파일 스킵: {path})")
        return
    keys = []
    for r in rows[:200]:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"  {os.path.basename(path)}: {len(rows)}행")


def main():
    univs_file = os.path.join(PROJECT, "normalized", "univs.csv")
    import csv as _csv
    with open(univs_file, encoding="utf-8-sig") as f:
        univs = list(_csv.DictReader(f))
    nm_by_cd = {u["unvCd"]: u["대학명"] for u in univs}

    long_rows, wide_rows, sirha_rows = [], [], []
    files = sorted(os.listdir(CACHE_RESULT)) if os.path.isdir(CACHE_RESULT) else []
    n = 0
    for fn in files:
        if not fn.endswith(".html"):
            continue
        unv_cd, up_cd = fn[:-5].rsplit("_", 1)
        nm = nm_by_cd.get(unv_cd, "")
        try:
            lo, wi = parse_result_file(os.path.join(CACHE_RESULT, fn), unv_cd, nm, up_cd)
            long_rows += lo
            wide_rows += wi
        except Exception as e:
            print(f"  결과 파싱 실패 {fn}: {e}")
        n += 1
        if n % 100 == 0:
            print(f"  결과 {n}/{len(files)}")
    print(f"입결 파싱 완료: {len(files)} 파일")
    write_csv(os.path.join(PROJECT, "normalized", f"results_long_{YEAR}.csv"), long_rows)
    write_csv(os.path.join(PROJECT, "normalized", f"results_jihak_{YEAR}.csv"), wide_rows)

    sfiles = sorted(os.listdir(CACHE_SIRHA)) if os.path.isdir(CACHE_SIRHA) else []
    n = 0
    for fn in sfiles:
        if not fn.endswith(".html"):
            continue
        unv_cd, artcl_cd = fn[:-5].rsplit("_", 1)
        up_cd = {"21": "20", "31": "30", "41": "40"}.get(artcl_cd, artcl_cd)
        nm = nm_by_cd.get(unv_cd, "")
        try:
            sirha_rows += parse_sirha_file(os.path.join(CACHE_SIRHA, fn), unv_cd, nm, up_cd)
        except Exception as e:
            print(f"  심사기준 파싱 실패 {fn}: {e}")
        n += 1
    print(f"심사기준 파싱 완료: {n} 파일")
    write_csv(os.path.join(PROJECT, "normalized", f"criteria_text_{YEAR}.csv"), sirha_rows)


if __name__ == "__main__":
    main()
