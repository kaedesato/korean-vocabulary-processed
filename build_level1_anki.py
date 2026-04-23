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
DEFAULT_INPUT = ROOT / "level1.csv"
DEFAULT_OUTPUT = ROOT / "level1_anki_new.csv"
DEFAULT_REVIEW_OUTPUT = ROOT / "level1_anki_new_review.csv"
DEFAULT_DOTENV = ROOT / ".env"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"


@dataclass
class ProcessedRow:
    output: dict[str, str]
    needs_review: bool


@dataclass
class TranslationResult:
    translations: list[str]
    request_count: int


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
    return match.group(0) if match else ""


def call_openrouter_batch_translation(batch_items: list[dict[str, str]], model: str, timeout: int) -> dict[int, str]:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key or not batch_items:
        return {}

    payload_items = [
        {
            "id": item["id"],
            "word": item["word"],
            "word_type": item["word_type"],
            "origin": item["origin"],
            "meaning": item["meaning"],
        }
        for item in batch_items
    ]
    prompt = (
        "あなたは韓国語語彙の日本語訳作成アシスタントです。"
        "入力の配列を見て、各要素に対応する自然で短い日本語訳を返してください。"
        "出力はJSON配列のみ。各要素は {\"id\": 数値, \"translation\": \"訳語\"}。"
        "説明文・コードブロック・前置きは不要です。\n"
        f"入力JSON: {json.dumps(payload_items, ensure_ascii=False)}"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You translate Korean vocabulary into concise Japanese and return strict JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": max(256, 64 * len(batch_items)),
    }
    req = request.Request(
        "https://openrouter.io/api/v1/chat/completions",
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
        result: dict[int, str] = {}
        if isinstance(parsed, list):
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                try:
                    idx = int(item.get("id"))
                except (TypeError, ValueError):
                    continue
                translation = normalize_llm_output(str(item.get("translation", "")))
                if translation:
                    result[idx] = translation
        return result
    except (error.URLError, error.HTTPError, http.client.RemoteDisconnected, TimeoutError, KeyError, IndexError, json.JSONDecodeError):
        return {}


def call_openrouter_translation(word: str, word_type: str, origin: str, meaning: str, model: str, timeout: int) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return ""

    prompt = (
        "あなたは韓国語語彙の日本語訳作成アシスタントです。"
        "与えられた情報から、Anki用に短く自然な日本語訳を1つだけ返してください。"
        "漢字語は日本語の標準的な漢字表記に寄せ、外来語は必要ならカタカナ、難しければ原語を保持してください。"
        "出力は訳語のみで、説明や記号は不要です。\n"
        f"語彙: {word}\n"
        f"語種: {word_type}\n"
        f"原語: {origin}\n"
        f"意味: {meaning}"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You translate Korean vocabulary into concise Japanese."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 32,
    }
    req = request.Request(
        "https://openrouter.io/api/v1/chat/completions",
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
        text = data["choices"][0]["message"]["content"].strip()
        return normalize_llm_output(text)
    except (error.URLError, error.HTTPError, http.client.RemoteDisconnected, TimeoutError, KeyError, IndexError, json.JSONDecodeError):
        return ""


def chunked_rows(rows: list[dict[str, str]], size: int) -> Iterable[tuple[int, list[dict[str, str]]]]:
    if size <= 0:
        size = 1
    for start in range(0, len(rows), size):
        yield start, rows[start : start + size]


def translate_rows_with_openrouter(
    rows: list[dict[str, str]],
    model: str,
    batch_size: int,
    retries: int,
    timeout: int,
    progress_every: int,
) -> TranslationResult:
    translations = [""] * len(rows)
    request_count = 0
    total = len(rows)
    if total == 0:
        return TranslationResult(translations=translations, request_count=request_count)

    total_batches = (total + max(1, batch_size) - 1) // max(1, batch_size)
    print(
        f"LLM translation start: rows={total}, batch_size={batch_size}, batches={total_batches}, retries={retries}, timeout={timeout}s",
        flush=True,
    )

    for batch_idx, (start, batch) in enumerate(chunked_rows(rows, batch_size), start=1):
        batch_items = [
            {
                "id": start + i,
                "word": clean_text(row.get("어휘", "")),
                "word_type": clean_text(row.get("어종", "")),
                "origin": clean_text(row.get("원어", "")),
                "meaning": normalize_meaning_for_review(row.get("의미", "")),
            }
            for i, row in enumerate(batch)
        ]

        batch_result: dict[int, str] = {}
        for attempt in range(retries + 1):
            request_count += 1
            batch_result = call_openrouter_batch_translation(batch_items, model, timeout)
            if batch_result:
                break
            if attempt < retries:
                print(
                    f"Batch {batch_idx}/{total_batches}: empty response, retry {attempt + 1}/{retries}",
                    flush=True,
                )
                time.sleep(min(2 ** attempt, 8))

        for item in batch_items:
            idx = int(item["id"])
            translated = batch_result.get(idx, "")
            if translated:
                translations[idx] = translated

        # Batch response can be partially missing; single fallback keeps output coverage high.
        missing = [item for item in batch_items if not translations[int(item["id"])]]
        for item in missing:
            request_count += 1
            single = call_openrouter_translation(
                item["word"],
                item["word_type"],
                item["origin"],
                item["meaning"],
                model,
                timeout,
            )
            if single:
                translations[int(item["id"])] = single

        if progress_every <= 0:
            progress_every = 1
        if batch_idx % progress_every == 0 or batch_idx == total_batches:
            done = min(start + len(batch), total)
            translated_count = sum(1 for t in translations if t)
            print(
                f"Progress: batch {batch_idx}/{total_batches}, rows {done}/{total}, translated {translated_count}/{total}, requests {request_count}",
                flush=True,
            )

    return TranslationResult(translations=translations, request_count=request_count)


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


def split_definition_blocks(definition: str) -> list[str]:
    text = sanitize_definition(definition)
    if not text:
        return []
    blocks: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line:
            blocks.append(line)
    return blocks or [text]


def normalize_meaning_for_review(text: str) -> str:
    text = sanitize_definition(text)
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\n\s+", "\n", text)
    return text.strip()


def build_tags(grade: str, word_type: str, flags: Iterable[str]) -> str:
    type_slug = {
        "고유어": "native",
        "한자어": "hanja",
        "외래어": "loanword",
        "혼종어": "mixed",
    }.get(word_type, "other")
    tags = ["source:level1"]
    if grade:
        tags.append(f"grade:{grade.replace('등급', '')}")
    tags.append(f"type:{type_slug}")
    for flag in flags:
        tags.append(f"risk:{flag}")
    return " ".join(tags)


def process_row(
    row: dict[str, str],
    llm_translation: str = "",
) -> ProcessedRow:
    grade = clean_text(row.get("등급", ""))
    word = clean_text(row.get("어휘", ""))
    pos_raw = clean_text(row.get("품사", ""))
    pos_main, had_multi_pos = split_pos(pos_raw)
    word_type = clean_text(row.get("어종", ""))
    definition = normalize_meaning_for_review(row.get("의미", ""))
    translation = normalize_llm_output(llm_translation)
    loan_candidates = ["", ""]
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
    elif review:
        flags.append("needs_manual_review")

    tags = build_tags(grade, word_type, flags)
    output = {
        "등급": grade,
        "어휘": word,
        "품사": pos_main,
        "어종": word_type,
        "원어": clean_text(row.get("원어", "")),
        "의미": definition,
        "日本語訳": translation,
        "定義": definition,
        "外来語_カタカナ候補": loan_candidates[0],
        "外来語_原語候補": loan_candidates[1],
        "品質フラグ": "|".join(dict.fromkeys(flags)),
        "tags": tags,
    }
    return ProcessedRow(output=output, needs_review=review)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        expected = {"등급", "어휘", "표준동형어번호수정", "품사", "어종", "원어", "의미", "분야"}
        missing = expected.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
        return [{k: clean_text(v) for k, v in row.items()} for row in reader]


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore", quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    load_settings()

    parser = argparse.ArgumentParser(description="Build an Anki-ready CSV from level1.csv")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input CSV path")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output CSV path")
    parser.add_argument("--review-output", type=Path, default=DEFAULT_REVIEW_OUTPUT, help="Manual review CSV path")
    parser.add_argument("--use-openrouter", dest="use_openrouter", action="store_true", default=True, help="Use OpenRouter translation (default: enabled)")
    parser.add_argument("--no-openrouter", dest="use_openrouter", action="store_false", help="Disable OpenRouter translation")
    parser.add_argument("--openrouter-model", default=os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL), help="OpenRouter model name")
    parser.add_argument("--llm-batch-size", type=int, default=25, help="Batch size for OpenRouter translation requests")
    parser.add_argument("--llm-retries", type=int, default=2, help="Retry count for failed batch requests")
    parser.add_argument("--llm-timeout", type=int, default=30, help="Timeout seconds per OpenRouter request")
    parser.add_argument("--progress-every", type=int, default=1, help="Print progress every N batches")
    args = parser.parse_args()

    input_path = args.input if args.input.is_absolute() else ROOT / args.input
    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    review_path = args.review_output if args.review_output.is_absolute() else ROOT / args.review_output

    rows = read_rows(input_path)
    llm_enabled = openrouter_enabled(args.use_openrouter)
    translation_result = TranslationResult(translations=[""] * len(rows), request_count=0)
    if llm_enabled:
        translation_result = translate_rows_with_openrouter(
            rows,
            model=args.openrouter_model,
            batch_size=args.llm_batch_size,
            retries=max(0, args.llm_retries),
            timeout=max(5, args.llm_timeout),
            progress_every=max(1, args.progress_every),
        )

    processed = [
        process_row(
            row,
            llm_translation=translation_result.translations[i],
        )
        for i, row in enumerate(rows)
    ]

    fieldnames = [
        "등급",
        "어휘",
        "품사",
        "어종",
        "원어",
        "의미",
        "日本語訳",
        "定義",
        "外来語_カタカナ候補",
        "外来語_原語候補",
        "品質フラグ",
        "tags",
    ]

    write_csv(output_path, [r.output for r in processed], fieldnames)
    review_rows = [r.output for r in processed if r.needs_review]
    if review_rows:
        write_csv(review_path, review_rows, fieldnames)
    elif review_path.exists():
        review_path.unlink()

    total = len(processed)
    review_count = len(review_rows)
    translated_count = sum(1 for r in processed if r.output["日本語訳"])
    print(f"Wrote {total} rows to {output_path.name}")
    print(f"Translated rows: {translated_count}")
    print(f"Review rows: {review_count}")
    if review_count:
        print(f"Review file: {review_path.name}")
    if llm_enabled:
        print(f"OpenRouter requests: {translation_result.request_count} (batch size: {args.llm_batch_size})")
    else:
        print("OpenRouter translation: disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())