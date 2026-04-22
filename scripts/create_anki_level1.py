#!/usr/bin/env python3
"""
Ankiデッキ用に初級(level1)の韓国語-日本語CSVを生成するスクリプト。
- 同じ単語（同形語）は1レコードにまとめる (level1_grouped.csv を使用)
- POS（品詞）を韓国語から日本語に翻訳する
- 出力: 韓国語, 品詞(日本語), 日本語訳, 定義
"""

import csv
import os

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
    """
    '/' 区切りの品詞文字列を日本語に変換する。
    例: '감탄사/대명사' → '感動詞/代名詞'
    """
    if not pos_str:
        return ""
    parts = [p.strip() for p in pos_str.split("/")]
    translated = [POS_MAP.get(p, p) for p in parts]
    return "/".join(translated)


def main():
    input_path = os.path.join(
        os.path.dirname(__file__), "../data/level1_grouped.csv"
    )
    output_path = os.path.join(
        os.path.dirname(__file__), "../data/level1_anki_jp.csv"
    )

    with open(input_path, encoding="utf-8-sig", newline="") as infile:
        reader = csv.DictReader(infile)
        rows = list(reader)

    print(f"入力レコード数: {len(rows)}")

    output_rows = []
    for row in rows:
        word = row["word"].strip()
        pos_kr = row["pos"].strip()
        meaning = row["meaning"].strip()
        definition = row["definition"].strip()

        pos_jp = translate_pos(pos_kr)
        # 品詞が空の場合（複合名詞句など）は「名詞（句）」を補完
        if not pos_jp:
            pos_jp = "名詞（句）"

        output_rows.append({
            "韓国語": word,
            "品詞": pos_jp,
            "日本語訳": meaning,
            "定義": definition,
        })

    with open(output_path, "w", encoding="utf-8", newline="") as outfile:
        fieldnames = ["韓国語", "品詞", "日本語訳", "定義"]
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"出力レコード数: {len(output_rows)}")
    print(f"出力ファイル: {output_path}")

    # サンプルを表示
    print("\n--- サンプル (最初の10件) ---")
    for r in output_rows[:10]:
        print(f"{r['韓国語']} | {r['品詞']} | {r['日本語訳'][:40]}")


if __name__ == "__main__":
    main()
