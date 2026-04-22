import csv
import re
from collections import defaultdict

# ファイルパス
input_file = 'data/한국어 학습용 어휘 목록.csv'
output_file = 'data/한국어 학습용 어휘 목록_최종_スッキリ版.csv'

# 品詞のマッピング
pos_info = {
    '감': {'kor': '감탄사', 'jpn': '感嘆詞'},
    '고': {'kor': '고유 명사', 'jpn': '固有名詞'},
    '관': {'kor': '관형사', 'jpn': '冠形詞'},
    '대': {'kor': '대명사', 'jpn': '代名詞'},
    '동': {'kor': '동사', 'jpn': '動詞'},
    '명': {'kor': '명사', 'jpn': '名詞'},
    '보': {'kor': '보조 용언', 'jpn': '補助用言'},
    '부': {'kor': '부사', 'jpn': '副詞'},
    '불': {'kor': '분석 불능', 'jpn': '分析不能'},
    '수': {'kor': '수사', 'jpn': '数詞'},
    '의': {'kor': '의존 명사', 'jpn': '依存名詞'},
    '형': {'kor': '형용사', 'jpn': '形容詞'}
}

grade_priority = {'A': 1, 'B': 2, 'C': 3}
reverse_grade_priority = {1: 'A', 2: 'B', 3: 'C'}

def get_min_grade(grades):
    valid_grades = [grade_priority[g] for g in grades if g in grade_priority]
    return reverse_grade_priority[min(valid_grades)] if valid_grades else ''

# 正規表現: 単語と番号を分離する用
pattern = re.compile(r'^(.*?)(\d*)$')

try:
    data_groups = defaultdict(list)
    total_original = 0
    with open(input_file, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_original += 1
            word_raw = row['단어'].strip()
            
            # 品詞情報を事前に追加
            pos_code = row['품사']
            if pos_code in pos_info:
                row['품사 이름'] = pos_info[pos_code]['kor']
                row['품사 (일본어)'] = pos_info[pos_code]['jpn']
            else:
                row['품사 이름'] = pos_code
                row['품사 (일본어)'] = ''
            
            # 単語と番号を分離
            match = pattern.match(word_raw)
            clean_word = match.group(1) if match else word_raw
            word_num = match.group(2) if match else ""
            
            row['clean_word'] = clean_word
            row['word_num'] = word_num
            
            # 「数字なしの単語」をグループ化のキーにする
            data_groups[clean_word].append(row)

    processed_rows = []
    for clean_word, group in data_groups.items():
        def unique_join(column_name):
            items = []
            for r in group:
                val = r.get(column_name, '').strip()
                if val:
                    parts = [p.strip() for p in val.split(',')]
                    for p in parts:
                        if p not in items: items.append(p)
            return ', '.join(items)

        # その単語に含まれるすべての番号を収集 (例: "02, 26")
        all_nums = []
        for r in group:
            n = r.get('word_num', '')
            if n and n not in all_nums:
                all_nums.append(n)
        word_num_str = ', '.join(all_nums)

        valid_ranks = []
        for r in group:
            rank_val = r.get('순위', '').strip()
            if rank_val.isdigit(): valid_ranks.append(int(rank_val))
        
        processed_rows.append({
            '순위': min(valid_ranks) if valid_ranks else 999999,
            '단어': clean_word,
            '단어번호': word_num_str, # カンマ区切りの番号リスト
            '품사': unique_join('품사'),
            '품사 이름': unique_join('품사 이름'),
            '품사 (일본어)': unique_join('품사 (일본어)'),
            '풀이（意味）': unique_join('풀이'),
            '등급': get_min_grade([r['등급'] for r in group])
        })

    # 1. 순위で昇順ソート
    processed_rows.sort(key=lambda x: x['순위'])

    # 2. 連番を振る
    for i, row in enumerate(processed_rows, 1):
        row['번호'] = i
        if row['순위'] == 999999:
            row['순위'] = ''
        else:
            row['순위'] = str(row['순위'])

    # 書き出し
    fieldnames = ['번호', '순위', '단어', '단어번호', '품사', '품사 이름', '품사 (일본어)', '풀이（意味）', '등급']
    with open(output_file, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(processed_rows)
    
    print(f"Success: {output_file} created (merged homonyms).")
    print(f"Original: {total_original} rows -> Final: {len(processed_rows)} unique words.")

except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"Error: {e}")
