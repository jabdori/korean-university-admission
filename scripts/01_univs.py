# -*- coding: utf-8 -*-
"""01: 대학 목록 202개 + 대학별 홈페이지/입시홈페이지/추가안내자료 fileId 수집.

출력: normalized/univs.csv, cache/popup_detail/{unvCd}.html
"""
import csv
import html
import os
import re
import sys

from adiga import Adiga, PROJECT, cache_path, polite_sleep

YEAR_RESULT = sys.argv[1] if len(sys.argv) > 1 else "2026"  # 결과연도


def fetch_univ_list(a):
    """대학 선택 팝업 AJAX에서 (unvCd, unvNm) 202쌍 추출."""
    cache = cache_path("univ_picker", f"list_{YEAR_RESULT}.html")
    if os.path.exists(cache):
        raw = open(cache, encoding="utf-8").read()
    else:
        raw = a.post("/uct/acd/ade/criteriaAndResultPopupUnvAjax.do", {
            "searchSyr": "2027", "unvCd": "", "tsrdCmphSlcnArtclUpCd": "20",
            "compUnvCd": "",
        }, referer="/uct/acd/ade/criteriaAndResultView.do?menuId=PCUCTACD2000").decode("utf-8", "replace")
        open(cache, "w", encoding="utf-8").write(raw)
    un = html.unescape(raw)
    pairs = re.findall(r'fnSelUnv\("(\d{7})"\);?\s*">\s*<a[^>]*>([^<]+)</a>', un)
    return [(cd, nm) for cd, nm in pairs]


def fetch_univ_detail(a, unv_cd):
    """대학별 입시결과 상세 팝업: 홈페이지/입시홈페이지/추가안내자료 fileId."""
    cache = cache_path("popup_detail", f"{unv_cd}_{YEAR_RESULT}.html")
    if os.path.exists(cache):
        raw = open(cache, encoding="utf-8").read()
    else:
        raw = a.post("/ucp/cls/uni/classUnivAdmssPopup.do", {
            "searchSyr": YEAR_RESULT, "unvCd": unv_cd, "ruCd": "X", "slcnTypeCd": "02",
        }, referer="/ucp/cls/uni/classUnivAdmssView.do").decode("utf-8", "replace")
        open(cache, "w", encoding="utf-8").write(raw)
    un = html.unescape(raw)
    links = dict((lbl.strip(), url.replace("\\/", "/"))
                 for url, lbl in re.findall(r'fnOpenNewUrl\("([^"]+)"\);?"[^>]*>\s*<span>([^<]+)</span>', un))
    file_ids = re.findall(r'fnFileDownOne\("(\d+)"\s*,\s*"(\d+)"', un)
    return links, file_ids


def main():
    a = Adiga()
    univs = fetch_univ_list(a)
    print(f"대학 목록: {len(univs)}개")
    rows = []
    for i, (cd, nm) in enumerate(univs):
        try:
            links, file_ids = fetch_univ_detail(a, cd)
        except Exception as e:
            print(f"  [{cd}] {nm} 실패: {e}")
            links, file_ids = {}, []
        rows.append({
            "unvCd": cd, "대학명": nm,
            "홈페이지": links.get("홈페이지", ""),
            "입시홈페이지": links.get("입시홈페이지", ""),
            "추가안내자료_fileId": ";".join(f"{fid}:{sn}" for fid, sn in file_ids),
        })
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(univs)} 처리")
        polite_sleep(i)
    out = os.path.join(PROJECT, "normalized", "univs.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    n_file = sum(1 for r in rows if r["추가안내자료_fileId"])
    n_adm = sum(1 for r in rows if r["입시홈페이지"])
    print(f"완료: {len(rows)}개 대학 → {out}")
    print(f"  추가안내자료 보유: {n_file}개 / 입시홈페이지 링크: {n_adm}개")


if __name__ == "__main__":
    main()
