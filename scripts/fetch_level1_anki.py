#!/usr/bin/env python3
"""
한국어기초사전 Open API から level1 (初級) の全単語を取得して
Anki用CSVを生成するスクリプト。

- 全2501件(重複前)を音節ごとのページング方式で取得
- 同じ単語（同形語）は1レコードにまとめる
- 品詞(POS)を日本語に翻訳する
- 出力: data/level1_anki_from_api.csv
"""

import requests
import xml.etree.ElementTree as ET
import csv
import time
import json
import os
from collections import defaultdict

API_KEY = "73656C726FF52816D957CE26286BE7A9"
BASE_URL = "https://krdict.korean.go.kr/api/search"

# すべての韓国語の母音開始音節（ㅏ〜ㅣ）と初声+母音の全組み合わせ
# AC00〜D7A3 を網羅 (11172音節)
# 実用上は頭文字となりうる全音節をカバーするために全音節を走査する
def generate_all_syllables():
    """ハングル全音節 AC00〜D7A3 を生成"""
    return [chr(c) for c in range(0xAC00, 0xD7A4)]

# 品詞マッピング (韓国語 → 日本語)
POS_MAP = {
    "감탄사": "感動詞",
    "관형사": "冠形詞",
    "대명사": "代名詞",
    "동사": "動詞",
    "명사": "名詞",
    "부사": "副詞",
    "수사": "数詞",
    "의존 명사": "依存名詞",
    "접사": "接辞",
    "조사": "助詞",
    "형용사": "形容詞",
    "보조 동사": "補助動詞",
    "보조 형용사": "補助形容詞",
    "어미": "語尾",
    "품사 없음": "品詞なし",
}

def translate_pos(pos_str: str) -> str:
    """'/' 区切りの品詞文字列を日本語に変換。空の場合は '名詞（句）' を返す。"""
    if not pos_str or not pos_str.strip():
        return "名詞（句）"
    parts = [p.strip() for p in pos_str.split("/")]
    translated = [POS_MAP.get(p, p) for p in parts]
    return "/".join(translated)


def robust_request(params, retries=3, timeout=20):
    """リトライ付きAPIリクエスト"""
    headers = {"User-Agent": "Mozilla/5.0"}
    for attempt in range(retries):
        try:
            resp = requests.get(BASE_URL, params=params, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return resp.content
            elif resp.status_code == 429:
                print("  Rate limited. 10秒待機...")
                time.sleep(10)
            else:
                print(f"  HTTP {resp.status_code}, retrying...")
                time.sleep(2)
        except requests.exceptions.Timeout:
            print(f"  タイムアウト (試行 {attempt+1}/{retries})")
            time.sleep(2)
        except Exception as e:
            print(f"  エラー: {e} (試行 {attempt+1}/{retries})")
            time.sleep(2)
    return None


def fetch_all_level1():
    """
    全音節を先頭文字として検索し、level1の全単語を取得する。
    startパラメータは1〜1000まで、numは100固定。
    """
    syllables = generate_all_syllables()
    # 数字・記号から始まる単語のためにダッシュ・数字も追加
    prefixes = ["-"] + syllables

    seen_codes = set()  # 重複チェック用 target_code
    all_items = {}      # target_code -> item dict

    # 進捗保存用ファイル
    progress_file = "data/level1_api_progress.jsonl"
    raw_output = "data/level1_api_raw.jsonl"

    # 途中再開: 既存の進捗を読み込む
    if os.path.exists(raw_output):
        with open(raw_output, encoding="utf-8") as f:
            for line in f:
                item = json.loads(line)
                code = item["target_code"]
                seen_codes.add(code)
                all_items[code] = item
        print(f"既存データ読み込み: {len(all_items)}件")

    completed_prefixes = set()
    if os.path.exists(progress_file):
        with open(progress_file, encoding="utf-8") as f:
            for line in f:
                completed_prefixes.add(line.strip())
        print(f"完了済みプレフィックス: {len(completed_prefixes)}件")

    total_prefixes = len(prefixes)
    print(f"全プレフィックス数: {total_prefixes}")

    try:
        for idx, prefix in enumerate(prefixes):
            if prefix in completed_prefixes:
                continue

            start = 1
            prefix_found = 0
            while True:
                params = {
                    "key": API_KEY,
                    "q": prefix,
                    "advanced": "y",
                    "level": "level1",
                    "method": "start",
                    "num": 100,
                    "start": start,
                    "translated": "y",
                    "trans_lang": "2",  # 日本語
                }
                content = robust_request(params)
                if not content:
                    print(f"  [{idx}/{total_prefixes}] '{prefix}': リクエスト失敗")
                    break

                try:
                    root = ET.fromstring(content)
                except ET.ParseError as e:
                    print(f"  XMLパースエラー: {e}")
                    break

                # エラーチェック
                error = root.find("error")
                if error is not None:
                    code_el = error.find("error_code")
                    msg_el = error.find("message")
                    print(f"  APIエラー: {code_el.text if code_el is not None else '?'} - {msg_el.text if msg_el is not None else '?'}")
                    break

                items = root.findall(".//item")
                if not items:
                    break

                new_count = 0
                for item in items:
                    tc = item.find("target_code")
                    if tc is None:
                        continue
                    target_code = tc.text
                    if target_code in seen_codes:
                        continue
                    seen_codes.add(target_code)
                    new_count += 1
                    prefix_found += 1

                    word_el = item.find("word")
                    pos_el = item.find("pos")
                    grade_el = item.find("word_grade")
                    sup_el = item.find("sup_no")

                    # 全senseの翻訳を収集（複数ある場合は " | " で結合）
                    trans_words = []
                    trans_dfns = []
                    for sense in item.findall(".//sense"):
                        tw = sense.find(".//trans_word")
                        td = sense.find(".//trans_dfn")
                        if tw is not None and tw.text:
                            trans_words.append(tw.text.strip())
                        if td is not None and td.text:
                            trans_dfns.append(td.text.strip())

                    all_items[target_code] = {
                        "target_code": target_code,
                        "word": word_el.text if word_el is not None else "",
                        "sup_no": sup_el.text if sup_el is not None else "0",
                        "pos": pos_el.text if pos_el is not None else "",
                        "grade": grade_el.text if grade_el is not None else "",
                        "meaning": " | ".join(trans_words),
                        "definition": " | ".join(trans_dfns),
                    }

                # 新規アイテムをraw出力に追記
                if new_count > 0:
                    with open(raw_output, "a", encoding="utf-8") as f:
                        for code in list(seen_codes)[-new_count:]:
                            if code in all_items:
                                f.write(json.dumps(all_items[code], ensure_ascii=False) + "\n")

                if len(items) < 100 or start >= 900:
                    break
                start += 100
                time.sleep(0.1)  # レート制限対策

            # プレフィックス完了を記録
            with open(progress_file, "a", encoding="utf-8") as f:
                f.write(prefix + "\n")
            completed_prefixes.add(prefix)

            # 進捗表示（100プレフィックスごと）
            if idx % 100 == 0:
                print(f"進捗: {idx}/{total_prefixes} プレフィックス完了 | 総取得: {len(all_items)}件", flush=True)

            time.sleep(0.05)  # 適度な間隔

    except KeyboardInterrupt:
        print("\n中断されました。進捗を保存済みです。")

    print(f"\n取得完了: {len(all_items)}件 (raw)")
    return list(all_items.values())


def group_and_translate(items):
    """
    同じ単語（word）を1レコードにグループ化し、品詞を日本語訳する。
    """
    grouped = defaultdict(list)
    for item in items:
        grouped[item["word"]].append(item)

    result = []
    for word, entries in sorted(grouped.items()):
        # 品詞を結合（重複除去）
        pos_set = []
        seen_pos = set()
        meanings = []
        definitions = []
        target_codes = []

        for e in entries:
            p = e["pos"].strip()
            if p and p not in seen_pos:
                seen_pos.add(p)
                pos_set.append(p)
            if e["meaning"]:
                meanings.append(e["meaning"])
            if e["definition"]:
                definitions.append(e["definition"])
            target_codes.append(e["target_code"])

        pos_kr = "/".join(pos_set)
        pos_jp = translate_pos(pos_kr)

        result.append({
            "韓国語": word,
            "品詞": pos_jp,
            "日本語訳": " | ".join(meanings),
            "定義": " | ".join(definitions),
            "target_codes": ",".join(target_codes),
        })

    return result


def save_csv(rows, output_path):
    fieldnames = ["韓国語", "品詞", "日本語訳", "定義", "target_codes"]
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV保存完了: {output_path} ({len(rows)}件)")


def main():
    print("=== level1 全件APIクロール開始 ===")
    print(f"APIキー: {API_KEY[:8]}...")

    # 接続テスト
    print("\nAPIへの接続テスト中...")
    test_content = robust_request({"key": API_KEY, "q": "가", "num": 1, "advanced": "y", "level": "level1"}, retries=1, timeout=10)
    if not test_content:
        print("❌ APIに接続できません。ネットワーク接続を確認してください。")
        print("   サーバー: krdict.korean.go.kr:443")
        return
    print("✅ API接続確認OK")

    # 全件取得
    items = fetch_all_level1()
    print(f"\nraw取得件数: {len(items)}件 (期待値: ~2501件)")

    # グループ化 & POS翻訳
    grouped = group_and_translate(items)
    print(f"グループ化後: {len(grouped)}件")

    # CSV保存
    output = "data/level1_anki_from_api.csv"
    save_csv(grouped, output)

    print("\n--- サンプル (最初の10件) ---")
    for r in grouped[:10]:
        print(f"  {r['韓国語']} | {r['品詞']} | {r['日本語訳'][:50]}")


if __name__ == "__main__":
    main()
