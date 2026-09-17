# -*- coding: utf-8 -*-
"""09: OCR 큐(스캔 PDF·텍스트 없는 PDF) → PaddleOCR PP-StructureV3 추출.

출력: extracted/{원본상대경로}.json (디지털 PDF와 동일한 pages 구조)
      + 동일 경로 .raw.json (PaddleOCR 원 결과, 표 HTML 등 보존)
사용: .venv-ocr/bin/python scripts/09_ocr_extract.py [시작인덱스 개수]
"""
import json
import os
import sys

from paddleocr import PPStructureV3

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(PROJ, "extracted", "_ocr_queue.json")
RAW = os.path.join(PROJ, "raw")


def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    queue = [x for x in json.load(open(QUEUE, encoding="utf-8")) if x["type"] in ("scanned", "empty")]
    if count:
        queue = queue[start:start + count]
    pipeline = PPStructureV3(use_doc_orientation_classify=False,
                             use_doc_unwarping=False,
                             use_textline_orientation=False)
    n_done = n_skip = 0
    for item in queue:
        src = os.path.join(PROJ, item["path"])
        out = os.path.join(PROJ, "extracted", os.path.relpath(src, RAW) + ".json")
        if os.path.exists(out):
            n_skip += 1
            continue
        try:
            pages = []
            raw_all = []
            for res in pipeline.predict(input=src):
                text = ""
                try:
                    text = res["markdown"]["text"] or ""
                except Exception:
                    pass
                pages.append({"page": len(pages) + 1, "text": text, "tables": []})
                raw_all.append(res.json if hasattr(res, "json") else str(res))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            json.dump({"source": item["path"], "kind": "ocr_pdf", "pages": pages},
                      open(out, "w", encoding="utf-8"), ensure_ascii=False)
            json.dump(raw_all, open(out + ".raw.json", "w", encoding="utf-8"),
                      ensure_ascii=False)
            n_done += 1
            print(f"OCR 완료 {n_done}: {item['path']}", flush=True)
        except Exception as e:
            print(f"OCR 실패 {item['path']}: {e}", flush=True)
    print(f"OCR 종료: 완료 {n_done}, 스킵 {n_skip}, 대상 {len(queue)}")


if __name__ == "__main__":
    main()
