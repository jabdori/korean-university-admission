# -*- coding: utf-8 -*-
"""07: 커버리지 매니페스트 재생성. bash 복구 후 1회 실행.

출력: normalized/coverage.csv (대학별 보유 데이터 요약)
"""
import csv
import os
import re

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YEARS = ["2027", "2026", "2025", "2024"]
# 포털이 빈 조각(데이터 없음)을 주는 대학 - 전 연도 공통
EMPTY_UNIVS = {"0003363", "0003364", "0000060"}


def codes_in(path):
    """CSV에서 unvCd 집합 추출(스트리밍)."""
    out = set()
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            m = re.match(r"^(\d{7}),", line)
            if m:
                out.add(m.group(1))
    return out


def safe(nm):
    return re.sub(r'[\\/:*?"<>|]', "_", nm)


def dir_counts(base):
    out = {}
    if os.path.isdir(base):
        for d in os.listdir(base):
            p = os.path.join(base, d)
            if os.path.isdir(p):
                out[d] = len(os.listdir(p))
    return out


def main():
    univs = list(csv.DictReader(open(os.path.join(PROJ, "normalized", "univs.csv"), encoding="utf-8-sig")))
    cov = {}
    for y in YEARS:
        r_path = os.path.join(PROJ, "normalized", f"results_long_{y}.csv")
        s_path = os.path.join(PROJ, "normalized", f"criteria_text_{y}.csv")
        for cd in codes_in(r_path):
            cov.setdefault(cd, {"입결": set(), "심사기준": set()})["입결"].add(y)
        for cd in codes_in(s_path):
            cov.setdefault(cd, {"입결": set(), "심사기준": set()})["심사기준"].add(y)

    add_counts = dir_counts(os.path.join(PROJ, "raw", "adiga"))
    dist_counts = dir_counts(os.path.join(PROJ, "raw", "univ_dist"))

    rows = []
    for u in univs:
        cd = u["unvCd"]
        s = safe(u["대학명"])
        adir = os.path.join(PROJ, "raw", "adiga", s)
        yogang = ""
        if os.path.isdir(adir):
            yogang = "Y" if any(f.startswith("2027_") for f in os.listdir(adir)) else ""
        if cd in EMPTY_UNIVS:
            jy, sy = "", ""
        else:
            jy = ",".join(sorted(cov.get(cd, {}).get("입결", set())))
            sy = ",".join(sorted(cov.get(cd, {}).get("심사기준", set())))
        rows.append({
            "unvCd": cd, "대학명": u["대학명"],
            "심사기준_연도": sy, "입결_연도": jy,
            "추가안내자료_파일수": add_counts.get(s, 0),
            "모집요강_포함": yogang,
            "대학사이트자료_파일수": dist_counts.get(s, 0),
            "입시홈페이지": u.get("입시홈페이지", ""),
        })
    out = os.path.join(PROJ, "normalized", "coverage.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    n_dist = sum(1 for r in rows if int(r["대학사이트자료_파일수"]) > 0)
    n_add = sum(1 for r in rows if int(r["추가안내자료_파일수"]) > 0)
    n4 = sum(1 for r in rows if len(r["입결_연도"].split(",")) >= 4)
    print(f"coverage.csv 생성: 입결4개년 {n4}/202, 대학사이트자료 {n_dist}/202, 추가안내자료 {n_add}/202")


if __name__ == "__main__":
    main()
