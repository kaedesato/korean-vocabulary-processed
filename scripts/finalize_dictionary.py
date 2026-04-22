import json
import csv
import os

POS_MAP = {
    "명사": "名詞",
    "대명사": "代名詞",
    "수사": "数詞",
    "조사": "助詞",
    "동사": "動詞",
    "형용사": "形容詞",
    "관형사": "冠形詞",
    "부사": "副詞",
    "감탄사": "感嘆詞",
    "접사": "接辞",
    "의존 명사": "依存名詞",
    "보조 동사": "補助動詞",
    "보조 형용사": "補助形容詞",
    "어미": "語尾",
    "품사 없음": "品詞なし",
    "구": "句",
    "문법 표현": "文法表現"
}

GRADE_MAP = {
    "초급": "level1",
    "중급": "level2",
    "고급": "level3"
}

def translate_pos(pos_str):
    if not pos_str: return ""
    # Some POS might be like "명사, 대명사" (unlikely but possible)
    # or have extra spaces
    pos_clean = pos_str.strip()
    return POS_MAP.get(pos_clean, pos_clean)

def process():
    raw_file = "data/raw_dictionary.jsonl"
    if not os.path.exists(raw_file):
        print("Raw data not found!")
        return

    # levels[grade] = { word: { ...data... } }
    levels = {
        "level1": {},
        "level2": {},
        "level3": {},
        "other": {}
    }

    with open(raw_file, "r", encoding="utf-8") as f:
        for line in f:
            item = json.loads(line)
            word = item['word']
            grade = GRADE_MAP.get(item['grade'], "other")
            
            target_dict = levels[grade]
            if word not in target_dict:
                target_dict[word] = {
                    "word": word,
                    "pos": set(),
                    "meanings": [],
                    "definitions": [],
                    "target_codes": []
                }
            
            trans_pos = translate_pos(item['pos'])
            if trans_pos: target_dict[word]["pos"].add(trans_pos)
            if item['meaning']: target_dict[word]["meanings"].append(item['meaning'])
            if item['definition']: target_dict[word]["definitions"].append(item['definition'])
            if item['target_code']: target_dict[word]["target_codes"].append(item['target_code'])

    # Write CSVs
    for grade, words_dict in levels.items():
        output_file = f"data/{grade}_final.csv"
        final_rows = []
        for word in sorted(words_dict.keys()):
            data = words_dict[word]
            final_rows.append({
                "word": word,
                "pos": "/".join(sorted(list(data["pos"]))),
                "meaning": " | ".join(data["meanings"]),
                "definition": " | ".join(data["definitions"]),
                "target_codes": ",".join(data["target_codes"])
            })
        
        if final_rows:
            with open(output_file, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["word", "pos", "meaning", "definition", "target_codes"])
                writer.writeheader()
                writer.writerows(final_rows)
            print(f"Created {output_file} with {len(final_rows)} words.")

if __name__ == "__main__":
    process()
