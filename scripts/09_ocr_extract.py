# -*- coding: utf-8 -*-
"""09: OCR 큐(스캔 PDF·텍스트 없는 PDF) → PaddleOCR PP-StructureV3 추출.

출력: extracted/{원본상대경로}.json (디지털 PDF와 동일한 pages 구조)
      + 동일 경로 .raw.json (PaddleOCR 원 결과, 표 HTML 등 보존)
사용: uv run --python .venv-ocr/bin/python python scripts/09_ocr_extract.py [시작인덱스 개수]
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
    pipeline = PPStructureV3(lang="korean",
                             use_doc_orientation_classify=False,
                             use_doc_unwarping=False,
                             use_textline_orientation=False,
                             use_formula_recognition=False,
                             text_recognition_batch_size=1)
    # PPStructureV3 wrapper는 batch_size를 노출하지 않지만 기본값은 8페이지다.
    pipeline.paddlex_pipeline.batch_sampler.batch_size = 1
    n_done = n_skip = 0
    for item in queue:
        src = os.path.join(PROJ, item["path"])
        out = os.path.join(PROJ, "extracted", os.path.relpath(src, RAW) + ".json")
        if os.path.exists(out):
            try:
                if json.load(open(out, encoding="utf-8")).get("lang") == "korean":
                    n_skip += 1
                    continue
            except (OSError, ValueError):
                pass
        try:
            out_tmp, raw_tmp = out + ".tmp", out + ".raw.json.tmp"
            os.makedirs(os.path.dirname(out), exist_ok=True)
            n_pages = 0
            with open(out_tmp, "w", encoding="utf-8") as page_f, \
                    open(raw_tmp, "w", encoding="utf-8") as raw_f:
                page_f.write(json.dumps({"source": item["path"], "kind": "ocr_pdf",
                                         "lang": "korean"},
                                        ensure_ascii=False)[:-1] + ', "pages": [')
                raw_f.write("[")
                for res in pipeline.predict_iter(input=src):
                    text = res.markdown.get("markdown_texts") or ""
                    if n_pages:
                        page_f.write(", ")
                        raw_f.write(", ")
                    json.dump({"page": n_pages + 1, "text": text, "tables": []},
                              page_f, ensure_ascii=False)
                    json.dump(res.json if hasattr(res, "json") else str(res),
                              raw_f, ensure_ascii=False)
                    n_pages += 1
                    if n_pages % 10 == 0:
                        print(f"OCR 페이지 {n_pages}: {item['path']}", flush=True)
                page_f.write("]}")
                raw_f.write("]")
            os.replace(raw_tmp, out + ".raw.json")
            os.replace(out_tmp, out)
            n_done += 1
            print(f"OCR 완료 {n_done}: {item['path']}", flush=True)
        except Exception as e:
            for tmp in (out_tmp, raw_tmp):
                try:
                    os.remove(tmp)
                except FileNotFoundError:
                    pass
            print(f"OCR 실패 {item['path']}: {e}", flush=True)
    print(f"OCR 종료: 완료 {n_done}, 스킵 {n_skip}, 대상 {len(queue)}")
    pipeline.close()


if __name__ == "__main__":
    main()
