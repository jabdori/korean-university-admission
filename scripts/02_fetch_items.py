# -*- coding: utf-8 -*-
"""02: 전 대학 심사기준(2027) + 입시결과(전년도) 조각 수집 → cache/.

심사기준: criteriaAndResultItemAjax.do  tsrdCmphSlcnArtclCd = 21(종합)/31(교과)/41(수능)
입시결과: criteriaAndResultItemNewAjax.do tsrdCmphSlcnArtclUpCd = 20/30/40
사용: python3 02_fetch_items.py [결과연도] [--limit N]
"""
import os
import sys

from adiga import Adiga, PROJECT, cache_path, load_univs, polite_sleep

RESULT_YEAR = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "2027"
LIMIT = None
if "--limit" in sys.argv:
    LIMIT = int(sys.argv[sys.argv.index("--limit") + 1])

CRITERIA = {"20": "21", "30": "31", "40": "41"}  # upCd → artclCd


def fetch_one(a, unv_cd, kind, up_cd):
    if kind == "sirha":
        cache = cache_path("sirha", f"{RESULT_YEAR}", f"{unv_cd}_{CRITERIA[up_cd]}.html")
    else:
        cache = cache_path("result", f"{RESULT_YEAR}", f"{unv_cd}_{up_cd}.html")
    if os.path.exists(cache):
        return "cached"
    if kind == "sirha":
        fields = {"searchSyr": RESULT_YEAR, "unvCd": unv_cd, "searchUnvComp": "0",
                  "tsrdCmphSlcnArtclUpCd": up_cd, "tsrdCmphSlcnArtclCd": CRITERIA[up_cd],
                  "compUnvCd": ""}
        path = "/uct/acd/ade/criteriaAndResultItemAjax.do"
    else:
        fields = {"searchSyr": RESULT_YEAR, "unvCd": unv_cd,
                  "tsrdCmphSlcnArtclUpCd": up_cd, "compUnvCd": ""}
        path = "/uct/acd/ade/criteriaAndResultItemNewAjax.do"
    raw = a.post(path, fields)
    open(cache, "wb").write(raw)
    return len(raw)


def main():
    import time
    t0 = time.time()
    limit = float(os.environ.get("TIME_LIMIT", "0"))  # 초; 0=무제한
    univs = load_univs()
    if not univs:
        print("univs.csv 없음 - 01을 먼저 실행")
        return
    targets = [(u["unvCd"], u["대학명"]) for u in univs]
    if LIMIT:
        targets = targets[:LIMIT]
    a = Adiga()
    done = empty = fail = 0
    total = len(targets) * 6
    i = 0
    stopped = False
    for cd, nm in targets:
        if limit and time.time() - t0 > limit:
            stopped = True
            break
        for kind in ("sirha", "result"):
            for up_cd in ("20", "30", "40"):
                i += 1
                try:
                    size = fetch_one(a, cd, kind, up_cd)
                    if size == "cached":
                        continue
                    done += 1
                    if size < 600:
                        empty += 1  # 해당 전형 없음(빈 조각)
                except Exception as e:
                    fail += 1
                    print(f"  [{cd}] {nm} {kind}/{up_cd} 실패: {e}")
                polite_sleep(i)
        if i % 60 < 6:
            print(f"  진행 {i}/{total} (신규 {done}, 빈조각 {empty}, 실패 {fail})")
    print(f"완료: 신규 {done}, 빈조각 {empty}, 실패 {fail} / 총 {total} 요청" + (" (시간제한 도달, 재실행 시 이어서)" if stopped else ""))


if __name__ == "__main__":
    main()
