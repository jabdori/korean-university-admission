# -*- coding: utf-8 -*-
"""11: Gemini API로 agent task 정규화 실행.

사용:
  GEMINI_API_KEY=... python3 scripts/11_run_agent.py --limit 2
  GEMINI_API_KEY=... python3 scripts/11_run_agent.py --workers 2

성공한 task id는 재실행 시 스킵한다. API 키는 환경 변수로만 전달한다.
"""
import argparse
import datetime
import json
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS = os.path.join(PROJ, "normalized", "agent_tasks.jsonl")
PROMPT = os.path.join(PROJ, "normalized", "agent_prompt.md")
RESULTS = os.path.join(PROJ, "normalized", "agent_results.jsonl")
ERRORS = os.path.join(PROJ, "normalized", "agent_errors.jsonl")
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="gemini-3.6-flash")
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--limit", type=int, default=0, help="0이면 전체")
    p.add_argument("--ids", help="쉼표로 구분된 task id만 실행")
    p.add_argument("--progress", type=int, default=25)
    p.add_argument("--check", action="store_true", help="저장된 결과 형식 검증")
    return p.parse_args()


def compact(text):
    return "".join(text.split())


def validate_records(task, data, check_quotes=True):
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise ValueError("records 배열이 없음")
    locators = set(re.findall(r"\[locator: ([^\]]+)\]", task.get("content", "")))
    content = compact(task.get("content", ""))
    for i, record in enumerate(data["records"]):
        if not isinstance(record, dict):
            raise ValueError(f"records[{i}] 객체 아님")
        if record.get("record_type") not in ("criteria", "result", "other"):
            raise ValueError(f"records[{i}].record_type 오류")
        evidence = record.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"records[{i}].evidence 없음")
        for j, item in enumerate(evidence):
            if not isinstance(item, dict):
                raise ValueError(f"records[{i}].evidence[{j}] 객체 아님")
            quote, locator = item.get("quote", ""), item.get("locator", "")
            if not quote or not locator:
                raise ValueError(f"records[{i}].evidence[{j}] 값 없음")
            if check_quotes:
                if locator not in locators:
                    raise ValueError(f"records[{i}].evidence[{j}].locator 불일치")
                if compact(quote) not in content:
                    raise ValueError(f"records[{i}].evidence[{j}].quote 불일치")


def request_once(task, prompt, key, model):
    payload = {
        "systemInstruction": {"parts": [{"text": prompt}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(task, ensure_ascii=False)}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "maxOutputTokens": 32768,
        },
    }
    req = urllib.request.Request(
        API.format(model=model),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        if e.code == 429:
            raise RuntimeError("RATE_LIMIT " + detail[:500])
        if e.code in (408, 500, 502, 503, 504):
            raise RuntimeError(f"RETRYABLE HTTP {e.code}: {detail[:500]}")
        raise RuntimeError(f"HTTP {e.code}: {detail[:500]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"RETRYABLE network: {e}") from e

    try:
        text = "".join(part.get("text", "") for part in
                       body["candidates"][0]["content"]["parts"])
        return json.loads(text)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        raise RuntimeError("응답에서 JSON을 찾을 수 없음") from e


def call_api(task, prompt, key, model):
    delays = (5, 15, 45)
    for attempt in range(4):
        try:
            data = request_once(task, prompt, key, model)
            validate_records(task, data)
            return data
        except ValueError:
            # 모델이 근거 quote를 요약하는 경우가 있어 재호출하면 통과한다.
            if attempt >= 2:
                raise
            time.sleep(2)
        except RuntimeError as e:
            if attempt == 3 or not str(e).startswith(("RATE_LIMIT", "RETRYABLE")):
                raise
            time.sleep(delays[min(attempt, 2)])


def done_ids():
    ids = set()
    if not os.path.exists(RESULTS):
        return ids
    with open(RESULTS, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            try:
                ids.add(json.loads(line)["id"])
            except Exception as e:
                raise RuntimeError(f"agent_results.jsonl {i}줄 파싱 실패: {e}") from e
    return ids


def iter_tasks(wanted, done, limit):
    n = 0
    with open(TASKS, encoding="utf-8") as f:
        for line in f:
            task = json.loads(line)
            if wanted and task["id"] not in wanted:
                continue
            if task["id"] in done:
                continue
            yield task
            n += 1
            if limit and n >= limit:
                break


def check_results():
    ids = set()
    records = 0
    with open(RESULTS, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row["id"] in ids:
                raise ValueError(f"중복 결과: {row['id']}")
            ids.add(row["id"])
            validate_records({"content": "", "id": row["id"]}, row, check_quotes=False)
            records += len(row["records"])
    print(f"검증 통과: task {len(ids)}, records {records}")


def main():
    args = parse_args()
    if args.check:
        check_results()
        return
    if args.workers < 1 or args.progress < 1:
        raise SystemExit("--workers/--progress는 1 이상")
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY 환경 변수가 필요합니다")
    prompt = open(PROMPT, encoding="utf-8").read()
    done = done_ids()
    wanted = set(filter(None, args.ids.split(","))) if args.ids else set()
    limit = args.limit if args.limit > 0 else 0
    success = failure = 0
    stopped = False

    with open(RESULTS, "a", encoding="utf-8") as out, \
         open(ERRORS, "a", encoding="utf-8") as errors, \
         ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {}

        def handle(done_futures):
            nonlocal success, failure, stopped
            for future in done_futures:
                task = futures.pop(future)
                try:
                    data = future.result()
                    out.write(json.dumps({
                        "id": task["id"], "source": task["source"],
                        "document_hint": task["document_hint"], "model": args.model,
                        "records": data["records"],
                    }, ensure_ascii=False) + "\n")
                    out.flush()
                    success += 1
                except Exception as e:
                    message = str(e)
                    errors.write(json.dumps({
                        "id": task["id"], "source": task["source"],
                        "error": message[:2000],
                        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    }, ensure_ascii=False) + "\n")
                    errors.flush()
                    failure += 1
                    if message.startswith("RATE_LIMIT"):
                        stopped = True
                if (success + failure) % args.progress == 0:
                    print(f"진행: 성공 {success}, 실패 {failure}", flush=True)

        for task in iter_tasks(wanted, done, limit):
            while len(futures) >= args.workers * 4:
                ready, _ = wait(futures, return_when=FIRST_COMPLETED)
                handle(ready)
                if stopped:
                    break
            if stopped:
                break
            futures[pool.submit(call_api, task, prompt, key, args.model)] = task

        while futures:
            ready, _ = wait(futures, return_when=FIRST_COMPLETED)
            handle(ready)
            if stopped:
                for future in futures:
                    future.cancel()
                futures.clear()

    state = " rate limit로 중단 - 잠시 후 재실행하면 이어서 진행됩니다" if stopped else ""
    print(f"정규화 종료: 성공 {success}, 실패 {failure}, 기존 성공 {len(done)}{state}")


if __name__ == "__main__":
    main()
