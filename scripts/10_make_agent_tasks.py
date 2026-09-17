# -*- coding: utf-8 -*-
"""10: 추출 JSON → LLM 정규화 task(JSONL) 생성.

전형요소·반영비율·수능최저·입시결과 키워드가 있는 블록만 우선 선별하고,
원문 근거 위치(locator)를 유지한 채 chunk로 분할한다.
"""
import glob
import hashlib
import json
import os
import re

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRACTED = os.path.join(PROJ, "extracted")
OUT = os.path.join(PROJ, "normalized", "agent_tasks.jsonl")
PROMPT_OUT = os.path.join(PROJ, "normalized", "agent_prompt.md")
MAX_CHARS = 12000

KEYWORDS = re.compile(
    r"전형요소|반영비율|수능최저|학력기준|서류평가|면접|교과성적|학생부종합|학생부교과|"
    r"1단계|2단계|배수|평가요소|지원자격|입시결과|경쟁률|모집인원|합격|등급분포|백분위|충원"
)

PROMPT = """+# 입시 문서 정규화 지시문

입력 파일(normalized/agent_tasks.jsonl)의 각 줄은 하나의 작업(task)이다.
content를 근거로만 아래 형식의 JSON 객체를 반환한다. 문서에 없는 값은 null 또는 빈 배열로 둔다. 절대 추측하지 않는다.

~~~
{
  "records": [
    {
      "record_type": "criteria|result|other",
      "university_name": "",
      "admission_year": null,
      "admission_round": "수시|정시|기타|미상",
      "selection_name": "",
      "recruitment_unit": "",
      "eligibility": [],
      "stages": [
        {"stage": "1단계", "method": "서류", "multiple": null,
         "elements": [{"name": "학생부교과", "weight_percent": null}]}
      ],
      "sat_minimum": {"applies": null, "text": ""},
      "evaluation": [{"element": "", "criteria": "", "quote": ""}],
      "documents": [],
      "metrics": [{"name": "모집인원", "value": "", "unit": ""}],
      "evidence": [{"locator": "", "quote": ""}],
      "confidence": 0.0,
      "notes": []
    }
  ]
}
~~~

규칙:
- 하나의 task에서 여러 전형·모집단위가 나오면 records에 모두 나눈다.
- 반영비율은 percent 숫자로 변환하고, 문서에 없으면 null로 둔다.
- quote는 원문 문구를 그대로 인용하고 locator는 task의 locator 값 중 하나를 사용한다.
- quote는 content에서 공백을 제거해도 문자 단위로 연속되어야 한다. 점선·표 구분자를 건너뛰거나 요약한 인용은 사용하지 않는다.
- PDF 추출에서 괄호·숫자 위치가 뒤섞여 보여도 quote를 사람이 읽는 순서로 다시 배열하지 않고 content 문자 순서 그대로 복사한다.
- confidence는 근거 명확성(0~1)이며, 모호하면 낮게 설정한다.
- JSON 외 설명·마크다운 코드블록을 출력하지 않는다.
"""


def table_text(table):
    return "\n".join(" | ".join(str(c).replace("\n", " ").strip() for c in row) for row in table)


def split_block(block):
    text = block["text"]
    if len(text) <= MAX_CHARS:
        return [block]
    return [
        {"locator": f"{block['locator']} chars {i + 1}-{i + len(text[i:i + MAX_CHARS])}",
         "text": text[i:i + MAX_CHARS]}
        for i in range(0, len(text), MAX_CHARS)
    ]


def blocks(data):
    out = []
    for page in data.get("pages", []):
        parts = [page.get("text", "")]
        parts += [table_text(t) for t in page.get("tables", [])]
        text = "\n\n".join(x for x in parts if x.strip())
        if text.strip():
            out.append({"locator": f"page {page['page']}", "text": text})

    if data.get("text", "").strip():
        out.append({"locator": "text", "text": data["text"]})
    for i, table in enumerate(data.get("tables", []), 1):
        text = table_text(table)
        if text.strip():
            out.append({"locator": f"table {i}", "text": text})

    for sheet in data.get("sheets", []):
        rows = sheet.get("rows", [])
        start = 0
        while start < len(rows):
            buf, size = [], 0
            end = start
            while end < len(rows) and size < MAX_CHARS:
                row_text = " | ".join(str(c).replace("\n", " ") for c in rows[end])
                buf.append(row_text)
                size += len(row_text) + 1
                end += 1
            out.append({"locator": f"sheet {sheet['sheet']} rows {start + 1}-{end}",
                        "text": "\n".join(buf)})
            start = end
    return out


def source_meta(source):
    parts = source.split("/")
    fn = parts[-1]
    year = re.search(r"(20\d{2})", fn)
    if "모집요강" in fn or "시행계획" in fn:
        hint = "criteria"
    elif re.search(r"입시결과|경쟁률|등급분포|전형결과", fn, re.I):
        hint = "result"
    else:
        hint = "unknown"
    return parts[1] if len(parts) > 1 else "", parts[2] if len(parts) > 2 else "", \
        year.group(1) if year else None, hint


def main():
    files = [p for p in glob.glob(os.path.join(EXTRACTED, "**", "*.json"), recursive=True)
             if os.path.basename(p) not in ("_ocr_queue.json", "_failures.json")
             and not p.endswith(".raw.json")]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    expected, covered = set(), set()
    with open(OUT, "w", encoding="utf-8") as tasks, open(PROMPT_OUT, "w", encoding="utf-8") as prompt:
        prompt.write(PROMPT)
        n_tasks = n_chars = n_empty = 0
        for path in sorted(files):
            data = json.load(open(path, encoding="utf-8"))
            all_blocks = blocks(data)
            if all_blocks:
                expected.add(data["source"])
            selected = [b for b in all_blocks if KEYWORDS.search(b["text"])]
            if not selected:
                selected = all_blocks[:1]  # 키워드 없어도 문서 유형 판단용 최소 블록
            if not selected:
                n_empty += 1
                continue
            covered.add(data["source"])
            collection, university, year, hint = source_meta(data["source"])
            chunks, current, size = [], [], 0
            for block in selected:
                for part in split_block(block):
                    if current and size + len(part["text"]) > MAX_CHARS:
                        chunks.append(current)
                        current, size = [], 0
                    current.append(part)
                    size += len(part["text"])
            if current:
                chunks.append(current)

            source_id = hashlib.sha256(data["source"].encode()).hexdigest()[:12]
            for i, chunk in enumerate(chunks, 1):
                content = "\n\n---\n\n".join(
                    f"[locator: {b['locator']}]\n{b['text']}" for b in chunk)
                task = {
                    "id": f"{source_id}-{i:04d}", "source": data["source"],
                    "kind": data.get("kind"), "collection": collection,
                    "university_path": university, "year_hint": year,
                    "document_hint": hint, "content": content,
                }
                tasks.write(json.dumps(task, ensure_ascii=False) + "\n")
                n_tasks += 1
                n_chars += len(content)
        assert covered == expected
    print(f"agent_tasks.jsonl 생성: task {n_tasks}, 문자 {n_chars:,}, 빈 문서 {n_empty}")


if __name__ == "__main__":
    main()
