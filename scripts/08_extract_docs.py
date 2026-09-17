# -*- coding: utf-8 -*-
"""08: 원본 문서(raw/) → 구조 보존 추출 JSON(extracted/).

대상: PDF(디지털), XLSX. 스캔 PDF·HWP/HWPX는 OCR/변환 큐로 분류.
디지털 PDF는 PyMuPDF로 페이지별 텍스트+표(2차원 그리드) 추출.
재실행 시 이미 추출된 파일은 스킵(캐시 방식, 기존 파이프라인 관례).
"""
import json
import os
import sys
import zipfile
import re
import importlib.util
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import pymupdf
import xlrd
from openpyxl import load_workbook

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(PROJ, "raw")
OUT = os.path.join(PROJ, "extracted")
OCR_QUEUE = os.path.join(OUT, "_ocr_queue.json")


def classify_pdf(path):
    """처음 3페이지 텍스트 밀도로 디지털/스캔/빈 문서 분류."""
    doc = pymupdf.open(path)
    chars = sum(len(doc[i].get_text().strip()) for i in range(min(3, len(doc))))
    per_page = chars / max(1, min(3, len(doc)))
    doc.close()
    if per_page > 200:
        return "digital"
    if per_page > 10:
        return "scanned"
    return "empty"


def extract_pdf(path):
    doc = pymupdf.open(path)
    pages = []
    for i, page in enumerate(doc):
        tabs = []
        try:
            for t in page.find_tables().tables:
                grid = [[(c or "").encode("utf-8", "replace").decode("utf-8") for c in row]
                        for row in t.extract()]
                if any(any(c.strip() for c in row) for row in grid):
                    tabs.append(grid)
        except Exception:
            pass
        text = page.get_text().encode("utf-8", "replace").decode("utf-8")
        pages.append({"page": i + 1, "text": text, "tables": tabs})
    doc.close()
    return {"kind": "pdf", "pages": pages}


def extract_xlsx(path):
    # 확장자가 .xlsx여도 실제 구형 OLE2 Excel인 파일이 존재한다.
    with open(path, "rb") as f:
        if f.read(8) == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            wb = xlrd.open_workbook(path)
            sheets = []
            for ws in wb.sheets():
                rows = []
                for r in range(ws.nrows):
                    row = []
                    for c in range(ws.ncols):
                        cell = ws.cell(r, c)
                        if cell.ctype == xlrd.XL_CELL_DATE:
                            row.append(str(xlrd.xldate_as_datetime(cell.value, wb.datemode)))
                        else:
                            row.append("" if cell.value is None else str(cell.value))
                    rows.append(row)
                sheets.append({"sheet": ws.name, "rows": rows})
            return {"kind": "xls", "sheets": sheets}

    wb = load_workbook(path, data_only=True, read_only=True)
    sheets = []
    for ws in wb.worksheets:
        rows = [["" if c is None else str(c) for c in row] for row in ws.iter_rows(values_only=True)]
        sheets.append({"sheet": ws.title, "rows": rows})
    wb.close()
    return {"kind": "xlsx", "sheets": sheets}


def extract_hwpx(path):
    """HWPX(=ZIP+HWPML XML) → 본문 텍스트+표 그리드."""
    texts = []
    tables = []
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not re.fullmatch(r"Contents/section\d+\.xml", name):
                continue
            root = ET.fromstring(z.read(name))
            parents = {child: parent for parent in root.iter() for child in parent}
            local = lambda el: el.tag.rsplit("}", 1)[-1]
            in_table = lambda el: any(local(p) == "tbl" for p in _ancestors(el, parents))
            for el in root.iter():
                if local(el) == "t" and el.text and el.text.strip() and not in_table(el):
                    texts.append(el.text.strip())
            for tbl in root.iter():
                if local(tbl) != "tbl":
                    continue
                grid = []
                for tr in tbl:
                    if local(tr) != "tr":
                        continue
                    row = []
                    for tc in tr:
                        if local(tc) != "tc":
                            continue
                        cell = " ".join(t.text.strip() for t in tc.iter()
                                        if local(t) == "t" and t.text and t.text.strip())
                        row.append(cell)
                    if any(row):
                        grid.append(row)
                if any(any(c.strip() for c in row) for row in grid):
                    tables.append(grid)
    return {"kind": "hwpx", "text": "\n".join(texts), "tables": tables}


def _ancestors(el, parents):
    while el in parents:
        el = parents[el]
        yield el


def _table_parser():
    """03_parse.py의 TableParser 재사용(코드 중복 방지)."""
    spec = importlib.util.spec_from_file_location(
        "parse03", os.path.join(os.path.dirname(__file__), "03_parse.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.TableParser


def extract_hwp(path, venv_python):
    """구형 HWP → hwp5html 변환 → 텍스트+표 그리드 추출."""
    with tempfile.TemporaryDirectory() as td:
        bin_dir = os.path.dirname(venv_python)
        converter = os.path.join(bin_dir, "hwp5html")
        r = subprocess.run([converter, "--output", td, path],
                           capture_output=True, timeout=60)
        xhtml = os.path.join(td, "index.xhtml")
        if not os.path.exists(xhtml):
            raise RuntimeError(r.stderr.decode("utf-8", "replace")[:200])
        raw = open(xhtml, encoding="utf-8").read()
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", raw, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", body)
    text = re.sub(r"\s+", " ", text).strip()
    TP = _table_parser()
    tables = []
    for tbl in re.findall(r"<table.*?</table>", raw, re.S):
        grid = [[c if c is not None else "" for c in row] for row in TP.parse(tbl)]
        if any(any(str(c).strip() for c in row) for row in grid):
            tables.append(grid)
    return {"kind": "hwp", "text": text, "tables": tables}


def rel_out(path):
    rel = os.path.relpath(path, RAW)
    return os.path.join(OUT, rel + ".json")


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    targets, ocr_queue = [], []
    for root, _, files in os.walk(RAW):
        for fn in sorted(files):
            p = os.path.join(root, fn)
            ext = fn.lower().rsplit(".", 1)[-1]
            if ext not in ("pdf", "xlsx", "hwp", "hwpx"):
                continue
            if only and only not in p:
                continue
            targets.append((p, ext))

    n_done = n_skip = 0
    failures = []
    for p, ext in targets:
        out = rel_out(p)
        if os.path.exists(out):
            n_skip += 1
            continue
        try:
            if ext == "pdf":
                cls = classify_pdf(p)
                if cls != "digital":
                    ocr_queue.append({"path": os.path.relpath(p, PROJ), "type": cls})
                    continue
                data = extract_pdf(p)
            elif ext == "xlsx":
                data = extract_xlsx(p)
            elif ext == "hwpx":
                data = extract_hwpx(p)
            else:  # 구형 hwp → hwp5html 변환, 실패 시 큐
                try:
                    data = extract_hwp(p, sys.executable)
                except Exception:
                    ocr_queue.append({"path": os.path.relpath(p, PROJ), "type": "hwp"})
                    continue
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "w", encoding="utf-8") as f:
                json.dump({"source": os.path.relpath(p, PROJ), **data}, f, ensure_ascii=False)
            # 깨진 PDF의 서로게이트 문자 등으로 무효 JSON이 되면 안전 재작성
            try:
                json.load(open(out, encoding="utf-8"))
            except Exception:
                with open(out, "w", encoding="utf-8") as f:
                    json.dump({"source": os.path.relpath(p, PROJ), **data}, f, ensure_ascii=True)
            n_done += 1
        except Exception as e:
            print(f"추출 실패 {p}: {e}")
            failures.append({"path": os.path.relpath(p, PROJ), "error": str(e)})

    # OCR 큐 병합(기존 항목 유지)
    old = []
    if os.path.exists(OCR_QUEUE):
        old = json.load(open(OCR_QUEUE, encoding="utf-8"))
    seen = {x["path"] for x in old}
    merged = old + [x for x in ocr_queue if x["path"] not in seen]
    os.makedirs(OUT, exist_ok=True)
    json.dump(merged, open(OCR_QUEUE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(failures, open(os.path.join(OUT, "_failures.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"추출 완료 {n_done}, 스킵 {n_skip}, OCR/변환 대기 {len(merged)}, 실패 {len(failures)}")


if __name__ == "__main__":
    main()
