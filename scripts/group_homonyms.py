import csv
import os

def group_file(input_file, output_file):
    if not os.path.exists(input_file):
        print(f"File not found: {input_file}")
        return
    
    grouped_data = {}
    
    with open(input_file, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            word = row['word']
            if word not in grouped_data:
                grouped_data[word] = {
                    "word": word,
                    "pos": set(),
                    "meanings": [],
                    "definitions": [],
                    "target_codes": []
                }
            
            if row['pos']: grouped_data[word]["pos"].add(row['pos'])
            if row['meaning']: grouped_data[word]["meanings"].append(row['meaning'])
            if row['definition']: grouped_data[word]["definitions"].append(row['definition'])
            if row['target_code']: grouped_data[word]["target_codes"].append(row['target_code'])

    final_rows = []
    # Sort by word to keep it neat
    for word in sorted(grouped_data.keys()):
        data = grouped_data[word]
        final_rows.append({
            "word": word,
            "pos": "/".join(sorted(list(data["pos"]))),
            "meaning": " | ".join(data["meanings"]),
            "definition": " | ".join(data["definitions"]),
            "target_codes": ",".join(data["target_codes"])
        })
    
    with open(output_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["word", "pos", "meaning", "definition", "target_codes"])
        writer.writeheader()
        writer.writerows(final_rows)
    
    print(f"Grouped {len(grouped_data)} unique words in {output_file}")

levels = ["level1", "level2", "level3"]
for lv in levels:
    group_file(f"data/{lv}_korean_basic.csv", f"data/{lv}_grouped.csv")
