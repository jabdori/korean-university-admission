# -*- coding: utf-8 -*-
"""05: 대학별 모집요강 PDF 다운로드 → raw/adiga/{대학명}/.

univDetail.do 페이지에서 fnUnvFileDownOne(fileId, sn, 'Y', unvCd, year) 항목을
파싱해 시행계획/수시요강/정시요강 등을 내려받는다.
"""
import html as _html
import os
import re
import sys
import urllib.parse

from adiga import Adiga, PROJECT, cache_path, load_univs, polite_sleep

YEAR = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "2027"


def sniff_ext(blob, cd_header=""):
    m = re.search(r'filename\*?="?([^";]+)', cd_header or "")
    if m:
        ext = os.path.splitext(urllib.parse.unquote(m.group(1)))[1].lower()
        if ext:
            return ext
    if blob[:2] == b"PK":
        return ".xlsx"
    if blob[:4] == b"%PDF":
        return ".pdf"
    if blob[:2] == b"\x1b\x40":
        return ".hwp"
    return ".bin"


def fetch_items(a, unv_cd):
    cache = cache_path("univ_detail", f"{unv_cd}_{YEAR}.html")
    if os.path.exists(cache):
        raw = open(cache, encoding="utf-8").read()
    else:
        raw = a.get("/ucp/uvt/uni/univDetail.do",
                    {"menuId": "PCUVTINF2000", "searchSyr": YEAR, "unvCd": unv_cd}).decode("utf-8", "replace")
        open(cache, "w", encoding="utf-8").write(raw)
    un = _html.unescape(raw)
    out = []
    for m in re.finditer(
            r"fnUnvFileDownOne\('(\d+)',\s*'(\d+)'[^)]*\)[^>]*>\s*<span>(.*?)</span>", un, re.S):
        fid, sn, label = m.group(1), m.group(2), re.sub(r"<[^>]+>", "", m.group(3)).strip()
        out.append((fid, sn, label))
    if not out:  # 백업 패턴: &#39; 인코딩이 남아있는 경우
        for m in re.finditer(r"fnUnvFileDownOne\(&#39;(\d+)&#39;,\s*&#39;(\d+)&#39;[^)]*?\)[^>]*>\s*<span>(.*?)</span>", raw, re.S):
            fid, sn, label = m.group(1), m.group(2), re.sub(r"<[^>]+>", "", _html.unescape(m.group(3))).strip()
            out.append((fid, sn, label))
    return out


def main():
    import time
    t0 = time.time()
    limit = float(os.environ.get("TIME_LIMIT", "0"))
    univs = load_univs()
    a = Adiga()
    n_ok = n_skip = n_fail = n_nofile = 0
    for i, u in enumerate(univs):
        if limit and time.time() - t0 > limit:
            print(f"(시간제한 도달 {i}/{len(univs)})")
            break
        safe_nm = re.sub(r'[\\/:*?"<>|]', "_", u["대학명"])
        out_dir = os.path.join(PROJECT, "raw", "adiga", safe_nm)
        try:
            items = fetch_items(a, u["unvCd"])
        except Exception as e:
            print(f"  [{u['대학명']}] 페이지 실패: {e}")
            n_fail += 1
            continue
        if not items:
            n_nofile += 1
            polite_sleep(i, base=0.15)
            continue
        for fid, sn, label in items:
            # 핵심 3종만: 시행계획/수시모집요강/정시모집요강 (재외국민·외국인·선행학습 등은 제외해 용량 절제)
            core = re.sub(r"\s|<br\s*/?>", "", label)
            if not any(k in core for k in ("시행계획", "수시모집요강", "정시모집요강")):
                continue
            label = label.replace("\n", "").replace(" ", "_")[:40] or "파일"
            existing = [f for f in os.listdir(out_dir) if f.startswith(f"{YEAR}_{label}")] \
                if os.path.isdir(out_dir) else []
            if existing:
                n_skip += 1
                continue
            try:
                url = f"https://www.adiga.kr/cmm/com/file/fileDown.do?fileId={fid}&fileSn={sn}"
                import urllib.request
                req = urllib.request.Request(url)
                req.add_header("Referer", "https://www.adiga.kr/")
                req.add_header("User-Agent", a.opener.addheaders[0][1])
                with a.opener.open(req, timeout=300) as r:
                    blob = r.read()
                    cd = r.headers.get("Content-Disposition", "")
                ext = sniff_ext(blob, cd)
                os.makedirs(out_dir, exist_ok=True)
                out = os.path.join(out_dir, f"{YEAR}_{label}{ext}")
                with open(out, "wb") as f:
                    f.write(blob)
                n_ok += 1
                print(f"  [{u['대학명']}] {label}{ext} ({len(blob)//1024}KB)")
            except Exception as e:
                n_fail += 1
                print(f"  [{u['대학명']}] {label} 실패: {e}")
            time.sleep(0.15)
        polite_sleep(i, base=0.15)
    print(f"모집요강 완료: 신규 {n_ok}, 스킵 {n_skip}, 파일없음 {n_nofile}, 실패 {n_fail}")


if __name__ == "__main__":
    main()
