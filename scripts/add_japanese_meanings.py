import csv
import requests
import xml.etree.ElementTree as ET
import time
import os
import re

# 設定
API_KEY = '73656C726FF52816D957CE26286BE7A9'
INPUT_FILE = 'data/한국어 학습용 어휘 목록_최종_スッキリ版.csv'
OUTPUT_FILE = 'data/한국어 学習用語彙リスト_日本語訳付.csv'
PROGRESS_FILE = 'data/progress.txt'

def clean_japanese_meaning(meaning, original_explanation):
    """
    辞書形式の日本語訳から、最適な漢字語または訳語を抽出する
    例: 'かかく【価格】。ねだん【値段】' -> '価格, 値段'
    """
    if not meaning:
        return ""
    
    # 【 】の中身を抽出する
    kanji_matches = re.findall(r'【(.*?)】', meaning)
    if kanji_matches:
        # CSVの解説に漢字がある場合、それと一致するものを優先
        if original_explanation:
            for kanji in kanji_matches:
                if kanji in original_explanation:
                    return kanji
        
        # 一致がなくても、見つかった漢字をカンマで繋いで返す
        return ', '.join(dict.fromkeys(kanji_matches)) # 重複除去して結合
        
    # 漢字がない場合は、句読点や記号を除去して返す
    clean_val = re.sub(r'\[.*?\]|\(.*?\)', '', meaning) # [ ] や ( ) を除去
    clean_val = clean_val.replace('。', ', ').replace(' ', '').strip(', ')
    return clean_val

def fetch_japanese_meaning(session, word, pos_target, original_explanation):
    url = f"https://krdict.korean.go.kr/api/search?key={API_KEY}&q={word}&translated=y&trans_lang=2&num=10"
    
    for attempt in range(3):
        try:
            response = session.get(url, timeout=15)
            if response.status_code != 200:
                time.sleep(1)
                continue
            
            root = ET.fromstring(response.content)
            items = root.findall('.//item')
            
            first_meaning_raw = ""
            
            for item in items:
                pos_node = item.find('pos')
                item_pos = pos_node.text if pos_node is not None and pos_node.text else ""
                
                if item_pos not in pos_target:
                    continue
                    
                senses = item.findall('sense')
                for sense in senses:
                    dfn_node = sense.find('definition')
                    definition = dfn_node.text if dfn_node is not None and dfn_node.text else ""
                    
                    trans_node = sense.find('.//trans_word')
                    translation_raw = trans_node.text if trans_node is not None and trans_node.text else ""
                    
                    if not translation_raw:
                        continue
                    
                    if not first_meaning_raw:
                        first_meaning_raw = translation_raw
                    
                    # キーワードマッチング
                    if original_explanation and definition:
                        keywords = re.findall(r'[가-힣]{2,}', original_explanation)
                        for kw in keywords:
                            if kw in definition:
                                return translation_raw
                                
            return first_meaning_raw
            
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            time.sleep(2)
            
    return ""

def main():
    start_from = 0
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r') as f:
                line = f.readline()
                if line: start_from = int(line)
        except: pass

    rows = []
    with open(INPUT_FILE, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        if '일본어 뜻' not in fieldnames:
            fieldnames.append('일본어 뜻')
        rows = list(reader)

    print(f"Total rows: {len(rows)}. Starting from: {start_from}")

    session = requests.Session()
    
    try:
        for i in range(start_from, len(rows)):
            row = rows[i]
            # 既にデータがある場合はスキップ（再開時用）
            if row.get('일본어 뜻'):
                continue

            word = row['단어']
            pos_names = row['품사 이름']
            explanation = row['풀이（意味）']
            
            # コンソール文字化け対策（ログ用）
            print(f"[{i+1}/{len(rows)}] Processing...")
            
            meaning_raw = fetch_japanese_meaning(session, word, pos_names, explanation)
            meaning_clean = clean_japanese_meaning(meaning_raw, explanation)
            row['일본어 뜻'] = meaning_clean
            
            if meaning_clean:
                print(f" -> Result: {meaning_clean}")
            
            # 1行ごとに保存（テスト用）
            save_data(fieldnames, rows)
            with open(PROGRESS_FILE, 'w') as f:
                f.write(str(i + 1))
            print(f"Progress saved at {i+1}")
            
            time.sleep(0.2) # 少し長めにスリープ
            
    except KeyboardInterrupt:
        print("Interrupted.")
    finally:
        save_data(fieldnames, rows)
        print("Final data saved.")

def save_data(fieldnames, rows):
    with open(OUTPUT_FILE, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

if __name__ == "__main__":
    main()

