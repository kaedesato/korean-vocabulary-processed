from __future__ import annotations

import argparse
import csv
import http.client
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib import error, request


ROOT = Path(__file__).resolve().parent
DEFAULT_DOTENV = ROOT / ".env"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"


@dataclass
class ProcessedRow:
    output: dict[str, str]
    needs_review: bool


@dataclass
class LLMResult:
    translation: str = ""
    definition_ja: str = ""
    shinjitai: str = ""
    katakana: str = ""
    pos_ja: str = ""


def clean_text(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).replace("\ufeff", "").strip()


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", clean_text(value))


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_settings() -> None:
    load_env_file(DEFAULT_DOTENV)


def openrouter_enabled(flag: bool) -> bool:
    return flag and bool(os.getenv("OPENROUTER_API_KEY"))


def normalize_llm_output(text: str) -> str:
    cleaned = clean_text(text)
    cleaned = cleaned.replace("\r\n", "\n")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _extract_json_candidate(text: str) -> str:
    raw = clean_text(text)
    if not raw:
        return ""
    if raw.startswith("[") and raw.endswith("]"):
        return raw
    match = re.search(r"\[.*\]", raw, flags=re.DOTALL)
    if match:
        return match.group(0)
    match_dict = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if match_dict:
        return match_dict.group(0)
    return ""


def call_openrouter_batch_translation(batch_items: list[dict[str, str]], model: str, timeout: int) -> dict[int, LLMResult]:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key or not batch_items:
        return {}

    payload_items = [
        {
            "id": item["id"],
            "word": item["word"],
            "word_type": item["word_type"],
            "pos": item["pos"],
            "origin": item["origin"],
            "meaning": item["meaning"],
        }
        for item in batch_items
    ]
    prompt = (
        "あなたは韓国語語彙の日本語訳作成アシスタントです。\n"
        "入力のJSON配列を見て、各要素に対応する以下の情報を含んだJSON配列のみを返してください。\n"
        "各要素のフォーマット:\n"
        "{\n"
        "  \"id\": 数値,\n"
        "  \"translation\": \"自然で短い日本語訳\",\n"
        "  \"definition_ja\": \"meaningの日本語訳\",\n"
        "  \"shinjitai\": \"word_typeが'한자어'(漢字語)の場合、originの漢字を日本の新字体に直したもの。該当しない場合は空文字\",\n"
        "  \"katakana\": \"word_typeが'외래어'(外来語)の場合、originのアルファベット等をカタカナ読みしたもの。該当しない場合は空文字\",\n"
        "  \"pos_ja\": \"韓国語の品詞(pos)を日本語の品詞名（名詞、動詞、形容詞など）に翻訳したもの\"\n"
        "}\n"
        "説明文・コードブロック・前置きは一切不要です。必ずJSON配列のみを出力してください。\n"
        f"入力JSON: {json.dumps(payload_items, ensure_ascii=False)}"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You translate and process Korean vocabulary into Japanese and return strict JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": max(2048, 256 * len(batch_items)),
    }
    req = request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=max(5, timeout)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        json_text = _extract_json_candidate(content)
        if not json_text:
            return {}
        parsed = json.loads(json_text)
        result: dict[int, LLMResult] = {}
        if isinstance(parsed, list):
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                try:
                    idx = int(item.get("id"))
                except (TypeError, ValueError):
                    continue
                result[idx] = LLMResult(
                    translation=normalize_llm_output(str(item.get("translation", ""))),
                    definition_ja=normalize_llm_output(str(item.get("definition_ja", ""))),
                    shinjitai=normalize_llm_output(str(item.get("shinjitai", ""))),
                    katakana=normalize_llm_output(str(item.get("katakana", ""))),
                    pos_ja=normalize_llm_output(str(item.get("pos_ja", ""))),
                )
        return result
    except Exception as e:
        print(f"Batch LLM error: {e}")
        return {}


def call_openrouter_translation(word: str, word_type: str, pos: str, origin: str, meaning: str, model: str, timeout: int) -> LLMResult:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return LLMResult()

    prompt = (
        "あなたは韓国語語彙の日本語訳作成アシスタントです。\n"
        "与えられた情報から、以下の情報を含んだJSONオブジェクトのみを返してください。\n"
        "フォーマット:\n"
        "{\n"
        "  \"translation\": \"自然で短い日本語訳\",\n"
        "  \"definition_ja\": \"意味(meaning)の日本語訳\",\n"
        "  \"shinjitai\": \"語種が'한자어'(漢字語)の場合、原語の漢字を日本の新字体に直したもの。該当しない場合は空文字\",\n"
        "  \"katakana\": \"語種が'외래어'(外来語)の場合、原語のアルファベット等をカタカナ読みしたもの。該当しない場合は空文字\",\n"
        "  \"pos_ja\": \"品詞を日本語の品詞名に翻訳したもの\"\n"
        "}\n"
        "説明や記号は不要です。\n"
        f"語彙: {word}\n"
        f"品詞: {pos}\n"
        f"語種: {word_type}\n"
        f"原語: {origin}\n"
        f"意味: {meaning}"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You process Korean vocabulary and return strict JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 512,
    }
    req = request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=max(5, timeout)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        json_text = _extract_json_candidate(content)
        if not json_text:
            return LLMResult()
        item = json.loads(json_text)
        if isinstance(item, dict):
            return LLMResult(
                translation=normalize_llm_output(str(item.get("translation", ""))),
                definition_ja=normalize_llm_output(str(item.get("definition_ja", ""))),
                shinjitai=normalize_llm_output(str(item.get("shinjitai", ""))),
                katakana=normalize_llm_output(str(item.get("katakana", ""))),
                pos_ja=normalize_llm_output(str(item.get("pos_ja", ""))),
            )
        return LLMResult()
    except Exception as e:
        print(f"Single LLM error: {e}")
        return LLMResult()


def chunked_rows(rows: list[dict[str, str]], size: int) -> Iterable[tuple[int, list[dict[str, str]]]]:
    if size <= 0:
        size = 1
    for start in range(0, len(rows), size):
        yield start, rows[start : start + size]


def split_pos(pos_raw: str) -> tuple[str, bool]:
    pos_raw = normalize_spaces(pos_raw)
    if not pos_raw:
        return "", False
    if "/" in pos_raw:
        parts = [p.strip() for p in pos_raw.split("/") if p.strip()]
        return (parts[0], len(parts) > 1)
    return pos_raw, False


def sanitize_definition(definition: str) -> str:
    text = clean_text(definition)
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_meaning_for_review(text: str) -> str:
    text = sanitize_definition(text)
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\n\s+", "\n", text)
    return text.strip()


def build_tags(grade: str, word_type: str, pos_ja: str, flags: Iterable[str]) -> str:
    type_slug = {
        "고유어": "固有語",
        "한자어": "漢字語",
        "외래어": "外来語",
        "혼종어": "混種語",
    }.get(word_type, "その他")
    
    tags = []
    if grade:
        tags.append(f"等級:{grade.replace('등급', '')}")
    tags.append(f"語種:{type_slug}")
    if pos_ja:
        tags.append(f"品詞:{pos_ja}")
    for flag in flags:
        tags.append(f"risk:{flag}")
    return " ".join(tags)


def process_row(
    row: dict[str, str],
    llm_result: LLMResult,
) -> ProcessedRow:
    grade = clean_text(row.get("등급", ""))
    word = clean_text(row.get("어휘", ""))
    pos_raw = clean_text(row.get("품사", ""))
    pos_main, had_multi_pos = split_pos(pos_raw)
    word_type = clean_text(row.get("어종", ""))
    origin = clean_text(row.get("원어", ""))
    definition = normalize_meaning_for_review(row.get("의미", ""))
    
    translation = llm_result.translation
    definition_ja = llm_result.definition_ja
    pos_ja = llm_result.pos_ja
    shinjitai = llm_result.shinjitai
    katakana = llm_result.katakana
    
    flags: list[str] = []
    review = False

    if had_multi_pos:
        flags.append("multi_pos")
    if word_type not in {"고유어", "한자어", "외래어", "혼종어"}:
        flags.append("unknown_word_type")
        review = True
    if not translation:
        review = True
        flags.append("needs_manual_review")

    tags = build_tags(grade, word_type, pos_ja, flags)
    
    output = {
        "등급": grade,
        "어휘": word,
        "품사": pos_main,
        "日本語品詞": pos_ja,
        "어종": word_type,
        "원어": origin,
        "日本の漢字": shinjitai if word_type == "한자어" else "",
        "外来語": katakana if word_type == "외래어" else "",
        "의미": definition,
        "定義の日本語訳": definition_ja,
        "日本語訳": translation,
        "tags": tags,
    }
    return ProcessedRow(output=output, needs_review=review)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        expected = {"등급", "어휘", "품사", "어종", "원어", "의미"}
        missing = expected.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
        return [{k: clean_text(v) for k, v in row.items()} for row in reader]


def get_processed_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        lines = sum(1 for _ in reader)
        return max(0, lines - 1)  # subtract header


def append_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str], write_header: bool) -> None:
    mode = "w" if write_header else "a"
    with path.open(mode, encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore", quoting=csv.QUOTE_MINIMAL)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    load_settings()

    parser = argparse.ArgumentParser(description="Build Anki-ready CSVs from level1.csv to level5.csv with incremental saving")
    parser.add_argument("--use-openrouter", dest="use_openrouter", action="store_true", default=True, help="Use OpenRouter translation (default: enabled)")
    parser.add_argument("--no-openrouter", dest="use_openrouter", action="store_false", help="Disable OpenRouter translation")
    parser.add_argument("--openrouter-model", default=os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL), help="OpenRouter model name")
    parser.add_argument("--llm-batch-size", type=int, default=25, help="Batch size for OpenRouter translation requests")
    parser.add_argument("--llm-retries", type=int, default=2, help="Retry count for failed batch requests")
    parser.add_argument("--llm-timeout", type=int, default=30, help="Timeout seconds per OpenRouter request")
    parser.add_argument("--delay", type=float, default=0.0, help="Delay in seconds between batches to avoid rate limits")
    parser.add_argument("--progress-every", type=int, default=1, help="Print progress every N batches")
    args = parser.parse_args()

    llm_enabled = openrouter_enabled(args.use_openrouter)
    
    fieldnames = [
        "등급",
        "어휘",
        "품사",
        "日本語品詞",
        "어종",
        "원어",
        "日本の漢字",
        "外来語",
        "의미",
        "定義の日本語訳",
        "日本語訳",
        "tags",
    ]

    for level in range(1, 6):
        input_name = f"level{level}.csv"
        output_name = f"level{level}_anki.csv"
        review_name = f"level{level}_anki_review.csv"
        
        input_path = ROOT / input_name
        output_path = ROOT / output_name
        review_path = ROOT / review_name
        
        if not input_path.exists():
            print(f"Skipping {input_name}: file not found.")
            continue
            
        print(f"\n--- Processing {input_name} ---")
        rows = read_rows(input_path)
        total_input_rows = len(rows)
        
        processed_count = get_processed_count(output_path)
        if processed_count > 0:
            print(f"Found existing {output_name} with {processed_count} rows. Resuming...")
        
        if processed_count >= total_input_rows:
            print(f"All {total_input_rows} rows already processed. Skipping.")
            continue
            
        remaining_rows = rows[processed_count:]
        total_remaining = len(remaining_rows)
        batch_size = args.llm_batch_size
        total_batches = (total_remaining + max(1, batch_size) - 1) // max(1, batch_size)
        
        print(f"Rows to process: {total_remaining}/{total_input_rows}, batches={total_batches}, batch_size={batch_size}")
        
        request_count = 0
        translated_total = 0
        review_total = 0
        
        is_first_write_output = (processed_count == 0)
        is_first_write_review = not review_path.exists()
        
        for batch_idx, (start, batch) in enumerate(chunked_rows(remaining_rows, batch_size), start=1):
            batch_items = [
                {
                    "id": i,
                    "word": clean_text(row.get("어휘", "")),
                    "word_type": clean_text(row.get("어종", "")),
                    "pos": clean_text(row.get("품사", "")),
                    "origin": clean_text(row.get("원어", "")),
                    "meaning": normalize_meaning_for_review(row.get("의미", "")),
                }
                for i, row in enumerate(batch)
            ]

            results: dict[int, LLMResult] = {i: LLMResult() for i in range(len(batch))}
            
            if llm_enabled:
                batch_result: dict[int, LLMResult] = {}
                for attempt in range(args.llm_retries + 1):
                    request_count += 1
                    batch_result = call_openrouter_batch_translation(batch_items, args.openrouter_model, args.llm_timeout)
                    if batch_result:
                        break
                    if attempt < args.llm_retries:
                        print(f"Batch {batch_idx}/{total_batches}: empty response, retry {attempt + 1}/{args.llm_retries}", flush=True)
                        time.sleep(min(5 * (2 ** attempt), 60))

                for item in batch_items:
                    idx = int(item["id"])
                    res = batch_result.get(idx)
                    if res and res.translation:
                        results[idx] = res

                # Fallback for missing items
                missing = [item for item in batch_items if not results[int(item["id"])].translation]
                for item in missing:
                    request_count += 1
                    single = call_openrouter_translation(
                        item["word"],
                        item["word_type"],
                        item["pos"],
                        item["origin"],
                        item["meaning"],
                        args.openrouter_model,
                        args.llm_timeout,
                    )
                    if single and single.translation:
                        results[int(item["id"])] = single

            processed_batch = []
            review_batch = []
            
            for i, row in enumerate(batch):
                p_row = process_row(row, results[i])
                processed_batch.append(p_row.output)
                if p_row.output.get("日本語訳"):
                    translated_total += 1
                if p_row.needs_review:
                    review_batch.append(p_row.output)
                    review_total += 1

            append_csv(output_path, processed_batch, fieldnames, write_header=is_first_write_output)
            is_first_write_output = False
            
            if review_batch:
                append_csv(review_path, review_batch, fieldnames, write_header=is_first_write_review)
                is_first_write_review = False
            
            progress_every = max(1, args.progress_every)
            if batch_idx % progress_every == 0 or batch_idx == total_batches:
                done_remaining = min(start + len(batch), total_remaining)
                print(f"Progress: batch {batch_idx}/{total_batches}, rows processed {done_remaining}/{total_remaining}, translated {translated_total}/{done_remaining}, requests {request_count}", flush=True)
                
            if args.delay > 0:
                time.sleep(args.delay)

        print(f"Completed {input_name}: output={output_path.name}, review={review_path.name}")
        
    return 0


if __name__ == "__main__":
    raise SystemExit(main())