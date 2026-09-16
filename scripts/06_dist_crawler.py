# -*- coding: utf-8 -*-
"""06: 대학 자체 입시홈페이지에서 등급분포/입시결과 자료 탐색·다운로드 → raw/univ_dist/{대학명}/.

각 입시홈페이지를 2 depth까지 탐색해 키워드(입시결과/등급분포/결과공개 등) 링크를 찾고,
문서 파일(pdf/hwp/hwpx/xls(x)/doc(x)/zip/CSV) 링크를 수집해 다운로드한다.

사용: python3 06_dist_crawler.py [--limit N] [--only 대학명부분]
"""
import html as _html
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request

from adiga import PROJECT, UA, load_univs

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

DOC_EXT = (".pdf", ".hwp", ".hwpx", ".xls", ".xlsx", ".doc", ".docx", ".zip", ".csv")
KEY_LINK = re.compile(r"입시결과|결과공개|등급분포|입시정보공개|전형결과|입시통계|경쟁률|커트라인|입결|모집결과|합격자|분포|입시자료|자료실|주요입시|전형안내|모집요강|입시정보|통계자료|결과자료")
KEY_DOC = re.compile(r"입시결과|결과공개|등급분포|입시정보공개|전형결과|입시통계|경쟁률|커트라인|입결|모집결과|합격자|추가안내|결과자료|분포|통계|입시자료|자료실|주요입시|입시정보")
SKIP_EXT = (".jpg", ".png", ".gif", ".css", ".js", ".ico", ".woff", ".mp4")


def fetch(url, timeout=15):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Accept-Language", "ko-KR,ko;q=0.9")
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
        return r.read()


def norm_url(base, href):
    href = _html.unescape(href).strip()
    if href.startswith(("javascript:", "mailto:", "tel:", "#")):
        return None
    return urllib.parse.urljoin(base, href)


def extract_links(url, body_bytes):
    """(링크URL, 텍스트) 목록. a 태그 + JS 소스 내 키워드×URL 조합."""
    try:
        text = body_bytes.decode("utf-8", "replace")
    except Exception:
        return []
    if "euc-kr" in text[:600].lower():
        try:
            text = body_bytes.decode("euc-kr", "replace")
        except Exception:
            pass
    out = []
    seen = set()
    for m in re.finditer(r"<a\b([^>]*)>(.*?)</a>", text, re.S | re.I):
        attrs, inner = m.group(1), m.group(2)
        hm = re.search(r'href=["\']([^"\']+)["\']', attrs, re.I)
        if not hm:
            continue
        u = norm_url(url, hm.group(1))
        if not u or u in seen:
            continue
        seen.add(u)
        label = re.sub(r"<[^>]+>", " ", inner)
        label = re.sub(r"\s+", " ", _html.unescape(label)).strip()
        title = re.search(r'title=["\']([^"\']+)', attrs, re.I)
        out.append((u, label or (title.group(1) if title else "")))
    # JS 소스: 키워드와 URL이 같은 줄에 있는 경우 (메뉴 배열 등)
    for line in text.split("\n"):
        if not KEY_LINK.search(line):
            continue
        kw = KEY_LINK.search(line).group(0)
        for um in re.finditer(r'["\']([^"\']*(?:\.do|\.asp|\.jsp|\.html?|\.php)[^"\']*)["\']', line):
            u = norm_url(url, um.group(1))
            if u and u not in seen:
                seen.add(u)
                out.append((u, kw))
    # iframe도 후보로
    for m in re.finditer(r'<iframe[^>]*src=["\']([^"\']+)["\']', text, re.I):
        u = norm_url(url, m.group(1))
        if u and u != "about:blank" and u not in seen:
            seen.add(u)
            out.append((u, "iframe"))
    return out


def score_and_pick(univ_nm, base_url, pages):
    """pages: [(url, label)] 후보 중 키워드 스코어 상위 페이지 반환."""
    picked = []
    for u, label in pages:
        blob = label + " " + urllib.parse.unquote(u)
        if KEY_DOC.search(blob) or label == "iframe":
            picked.append((u, label))
    return picked[:6]


def find_docs(url, body_bytes):
    """본문에서 문서 파일 링크 추출 (a 태그 + JS 문자열 모두)."""
    try:
        text = body_bytes.decode("utf-8", "replace")
    except Exception:
        return []
    if "euc-kr" in text[:600].lower():
        try:
            text = body_bytes.decode("euc-kr", "replace")
        except Exception:
            pass
    docs = set()
    for m in re.finditer(r'href=["\']([^"\']+)["\']', text, re.I):
        u = norm_url(url, m.group(1))
        if u and u.lower().split("?")[0].endswith(DOC_EXT):
            docs.add(u)
    for m in re.finditer(r'["\']([^"\']+\.(?:pdf|hwp|hwpx|xlsx?|docx?|zip|csv))["\']', text, re.I):
        u = norm_url(url, m.group(1))
        if u:
            docs.add(u)
    return docs


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    univs = load_univs()
    targets = [(u["unvCd"], u["대학명"], u["입시홈페이지"]) for u in univs if u["입시홈페이지"]]
    if only:
        targets = [t for t in targets if only in t[1]]
    if limit:
        targets = targets[:limit]
    print(f"대상: {len(targets)}개 대학")
    report = []
    for i, (cd, nm, start_url) in enumerate(targets):
        if not start_url.startswith("http"):
            start_url = "https://" + start_url
        safe_nm = re.sub(r'[\\/:*?"<>|]', "_", nm)
        out_dir = os.path.join(PROJECT, "raw", "univ_dist", safe_nm)
        if os.path.isdir(out_dir) and os.listdir(out_dir):
            report.append((nm, "기존스킵"))
            continue
        found_docs = {}
        try:
            body = fetch(start_url)
            links = extract_links(start_url, body)
            for u in find_docs(start_url, body):
                found_docs[u] = "메인"
            # 1depth: 키워드 페이지 최대 4개
            cands = score_and_pick(nm, start_url, links)[:4]
            for cu, clabel in cands:
                try:
                    cbody = fetch(cu)
                    for u in find_docs(cu, cbody):
                        found_docs[u] = clabel[:20]
                    # 2depth: 문서 페이지 안의 하위 링크 1개 더
                    sub = [x for x in extract_links(cu, cbody) if KEY_LINK.search(x[1])][:2]
                    for su, _ in sub:
                        try:
                            for u in find_docs(su, fetch(su)):
                                found_docs[u] = clabel[:20]
                            time.sleep(0.3)
                        except Exception:
                            pass
                    time.sleep(0.3)
                except Exception:
                    pass
        except Exception as e:
            report.append((nm, f"실패: {str(e)[:50]}"))
            continue
        # 문서 다운로드 (최대 4개)
        dl = 0
        for u, src in list(found_docs.items())[:4]:
            try:
                blob = fetch(u, timeout=60)
                ext = os.path.splitext(urllib.parse.unquote(u.split("?")[0]))[1].lower() or ".bin"
                label_src = re.sub(r"\s+", "_", src)[:16]
                os.makedirs(out_dir, exist_ok=True)
                fname = f"{label_src}_{abs(hash(u)) % 10000}{ext}"
                with open(os.path.join(out_dir, fname), "wb") as f:
                    f.write(blob)
                dl += 1
            except Exception:
                pass
        report.append((nm, f"문서발견 {len(found_docs)} / 다운로드 {dl}"))
        time.sleep(0.5)
        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(targets)} 진행")
    print("\n=== 결과 리포트 ===")
    ok = sum(1 for _, s in report if "다운로드 " in s and not s.endswith("다운로드 0"))
    for nm, s in report:
        print(f"  {nm}: {s}")
    print(f"자료 확보 대학: {ok}/{len(report)}")


if __name__ == "__main__":
    main()
