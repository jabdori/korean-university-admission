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


# raw/univ_dist 디렉터리명은 생성 시점별 치환 규칙이 섞임(대괄호 유지형 / 언더스코어형 / 캠퍼스 실명형).
# 특수문자를 제거한 키로 정확 일치 → 접두사(최장) 매칭. 예외는 캠퍼스 실명 디렉터리만 수동 지정.
DROP = '\\\\/:*?"<>|[]()_ '
# univ_dist 전용 예외: 캠퍼스 실명 디렉터리. adiga는 기본 규칙 그대로.
UNIV_DIST_ALIAS = {"상명대학교[본교]": "상명대학교_서울", "상명대학교[제2캠퍼스]": "상명대학교_천안"}


def dir_key(s):
    return "".join(ch for ch in s if ch not in DROP)


def match_dir(counts, nm):
    if nm in UNIV_DIST_ALIAS:
        return UNIV_DIST_ALIAS[nm]
    k = dir_key(nm)
    for d in counts:
        if dir_key(d) == k:
            return d
    best = ""
    for d in counts:
        dk = dir_key(d)
        if dk and (k.startswith(dk) or dk.startswith(k)) and len(dk) > len(best):
            best = d
    return best or None


def dir_counts(base, exclude_prefix=None):
    out = {}
    if os.path.isdir(base):
        for d in os.listdir(base):
            p = os.path.join(base, d)
            if os.path.isdir(p):
                files = os.listdir(p)
                if exclude_prefix:
                    files = [f for f in files if not f.startswith(exclude_prefix)]
                out[d] = len(files)
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

    add_counts = dir_counts(os.path.join(PROJ, "raw", "adiga"), exclude_prefix="2027_")  # 모집요강 제외
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
        dist_dir = match_dir(dist_counts, u["대학명"])
        rows.append({
            "unvCd": cd, "대학명": u["대학명"],
            "심사기준_연도": sy, "입결_연도": jy,
            "추가안내자료_파일수": add_counts.get(s, 0),
            "모집요강_포함": yogang,
            "대학사이트자료_파일수": dist_counts.get(dist_dir, 0) if dist_dir else 0,
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
