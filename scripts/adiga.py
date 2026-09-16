# -*- coding: utf-8 -*-
"""대입정보포털(adiga.kr) 수집 공용 모듈. 표준 라이브러리만 사용."""
import http.cookiejar
import json
import os
import re
import time
import urllib.parse
import urllib.request

BASE = "https://www.adiga.kr"
PROJECT = os.path.expanduser("~/projects/university")
CACHE = os.path.join(PROJECT, "cache")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")


class Adiga:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.opener.addheaders = [("User-Agent", UA), ("Referer", BASE + "/")]
        self.csrf = None

    def get(self, path, params=None, max_retry=3):
        url = BASE + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        for i in range(max_retry):
            try:
                with self.opener.open(url, timeout=30) as r:
                    return r.read()
            except Exception as e:
                if i == max_retry - 1:
                    raise
                time.sleep(1.5 * (i + 1))

    def _refresh_csrf(self):
        html = self.get("/uct/acd/ade/criteriaAndResultView.do",
                        {"menuId": "PCUCTACD2000"}).decode("utf-8", "replace")
        m = re.search(r'name="_csrf"\s+value="([^"]+)"', html)
        if not m:
            m = re.search(r'"_csrf"\s*,\s*"([^"]+)"', html) or re.search(r'_csrf[^"]*"[^"]*"([^"]+)"', html)
        if not m:
            raise RuntimeError("CSRF 토큰을 찾을 수 없음")
        self.csrf = m.group(1)

    def post(self, path, fields, referer="/uct/acd/ade/criteriaAndResultPopup.do", max_retry=3):
        if self.csrf is None:
            self._refresh_csrf()
        data = dict(fields)
        data["_csrf"] = self.csrf
        body = urllib.parse.urlencode(data).encode()
        url = BASE + path
        for i in range(max_retry):
            try:
                req = urllib.request.Request(url, data=body, method="POST")
                req.add_header("Referer", BASE + referer)
                req.add_header("Content-Type", "application/x-www-form-urlencoded")
                with self.opener.open(req, timeout=60) as r:
                    code = r.getcode()
                    if code == 200:
                        return r.read()
                    raise RuntimeError(f"HTTP {code}")
            except Exception:
                if i == max_retry - 1:
                    raise
                time.sleep(1.5 * (i + 1))
                self.csrf = None  # 세션 만료 대비 재발급
                if self.csrf is None:
                    self._refresh_csrf()

    def download(self, path, params, out_path):
        """파일 다운로드 (CSRF 불필요)."""
        url = BASE + path + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url)
        req.add_header("Referer", BASE + "/")
        with self.opener.open(req, timeout=120) as r:
            blob = r.read()
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(blob)
        return len(blob)


def cache_path(*parts):
    p = os.path.join(CACHE, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def load_univs():
    """normalized/univs.csv 가 있으면 읽고, 없으면 None."""
    p = os.path.join(PROJECT, "normalized", "univs.csv")
    if not os.path.exists(p):
        return None
    import csv
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def polite_sleep(i, base=0.35):
    if i % 50 == 49:
        time.sleep(3)  # 50건마다 길게 쉼
    else:
        time.sleep(base)
