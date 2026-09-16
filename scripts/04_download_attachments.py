# -*- coding: utf-8 -*-
"""04: 대학별 추가안내자료 원본 파일 다운로드 → raw/adiga/{대학명}/."""
import os
import re
import sys
import time
import urllib.parse

from adiga import Adiga, PROJECT, load_univs, polite_sleep


def sniff_ext(blob, cd_header=""):
    m = re.search(r'filename\*?="?([^";]+)', cd_header or "")
    if m:
        name = urllib.parse.unquote(m.group(1))
        ext = os.path.splitext(name)[1].lower()
        if ext:
            return ext, name
    if blob[:2] == b"PK":
        return ".xlsx", None  # xlsx/docx 계열
    if blob[:4] == b"%PDF":
        return ".pdf", None
    if blob[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return ".xls", None  # 구형 오피스 (hwp일 수도)
    if blob[:2] == b"\x1b\x40" or b"HWP" in blob[:64]:
        return ".hwp", None
    return ".bin", None


def main():
    univs = load_univs()
    a = Adiga()
    n_ok = n_skip = n_fail = 0
    for i, u in enumerate(univs):
        ids = u["추가안내자료_fileId"]
        if not ids:
            continue
        safe_nm = re.sub(r'[\\/:*?"<>|]', "_", u["대학명"])
        for pair in ids.split(";"):
            fid, sn = pair.split(":")
            out_dir = os.path.join(PROJECT, "raw", "adiga", safe_nm)
            existing = [f for f in os.listdir(out_dir) if f.startswith(f"추가안내자료_{fid[-6:]}")] \
                if os.path.isdir(out_dir) else []
            if existing:
                n_skip += 1
                continue
            try:
                req_path = "/cmm/com/file/fileDown.do"
                url = f"https://www.adiga.kr{req_path}?fileId={fid}&fileSn={sn}"
                import urllib.request
                req = urllib.request.Request(url)
                req.add_header("Referer", "https://www.adiga.kr/")
                req.add_header("User-Agent", a.opener.addheaders[0][1])
                with a.opener.open(req, timeout=120) as r:
                    blob = r.read()
                    cd = r.headers.get("Content-Disposition", "")
                ext, fname = sniff_ext(blob, cd)
                label = fname or f"추가안내자료_{fid[-6:]}"
                if label.lower().endswith(ext):
                    out = os.path.join(out_dir, label)
                else:
                    out = os.path.join(out_dir, f"{label}{ext}")
                os.makedirs(out_dir, exist_ok=True)
                with open(out, "wb") as f:
                    f.write(blob)
                n_ok += 1
                print(f"  [{u['대학명']}] {label}{ext} ({len(blob)//1024}KB)")
            except Exception as e:
                n_fail += 1
                print(f"  [{u['대학명']}] 실패: {e}")
        polite_sleep(i, base=0.2)
    print(f"완료: 신규 {n_ok}, 기존 스킵 {n_skip}, 실패 {n_fail}")


if __name__ == "__main__":
    main()
