import csv
import requests
import xml.etree.ElementTree as ET
import time
import os
import re

# 設定
API_KEY = '73656C726FF52816D957CE26286BE7A9'
INPUT_FILE = 'data/한국어 학습용 어휘 목록_최종_スッキリ版.csv'
OUTPUT_FILE = 'data/한국어 학습용 어휘 목록_最終_日本語訳付.csv'
PROGRESS_FILE = 'data/progress.txt'

def clean_word_name(word_text):
    """APIの単語名から数字などを除去する"""
    if not word_text: return ""
    return re.sub(r'\d+', '', word_text).strip()

def extract_meanings_from_item(item, max_per_item=2):
    """
    1つの辞書アイテムから代表的な日本語訳を抽出する。
    漢字語を最優先。
    """
    meanings = []
    senses = item.findall('sense')
    
    kanji_meanings = []
    other_meanings = []
    
    for sense in senses:
        trans_word = sense.find('.//trans_word')
        if trans_word is None or not trans_word.text:
            continue
        
        raw_text = trans_word.text
        # 【 】の中の漢字を抽出
        kanjis = re.findall(r'【(.*?)】', raw_text)
        if kanjis:
            for k in kanjis:
                if k not in kanji_meanings:
                    kanji_meanings.append(k)
        else:
            # 漢字がない場合は代表語を抽出
            clean_text = re.sub(r'\[.*?\]|\(.*?\)', '', raw_text)
            parts = [p.strip() for p in clean_text.replace('。', ',').split(',') if p.strip()]
            for p in parts:
                if p not in other_meanings:
                    other_meanings.append(p)

    combined = kanji_meanings + [m for m in other_meanings if m not in kanji_meanings]
    return combined[:max_per_item]

def fetch_japanese_meanings(session, target_word, target_sup_nos, target_pos_list):
    """
    指定された単語、複数の番号、品詞リストに基づき、APIから日本語訳を取得する。
    """
    # 音節数（単語の長さ）を取得
    word_len = len(target_word)
    # 詳細検索パラメータを追加: advanced=y, method=exact (完全一致), letter_s/e (文字数制限)
    url = f"https://krdict.korean.go.kr/api/search?key={API_KEY}&q={target_word}&translated=y&trans_lang=2&num=50&advanced=y&method=exact&letter_s={word_len}&letter_e={word_len}"
    
    all_extracted_meanings = []
    
    # ターゲット番号のリストをクリーンアップ (例: ["02", "26"] -> ["2", "26"])
    clean_target_sup_list = [str(int(n)) for n in target_sup_nos if n.strip().isdigit()]
    
    for attempt in range(3):
        try:
            response = session.get(url, timeout=15)
            if response.status_code != 200:
                time.sleep(1)
                continue
            
            root = ET.fromstring(response.content)
            items = root.findall('.//item')
            
            # 全てのターゲット番号について処理
            for target_sup in (clean_target_sup_list if clean_target_sup_list else [""]):
                matching_items = []
                for item in items:
                    item_word = clean_word_name(item.find('word').text)
                    sup_no_node = item.find('sup_no')
                    item_sup_no = sup_no_node.text if sup_no_node is not None else ""
                    
                    if item_word == target_word:
                        if not target_sup or item_sup_no == target_sup:
                            matching_items.append(item)
                
                # 品詞ごとに意味を収集
                for target_pos in target_pos_list:
                    pos_items = [it for it in matching_items if (it.find('pos').text if it.find('pos') is not None else "") == target_pos]
                    source_items = pos_items if pos_items else matching_items
                    
                    for item in source_items:
                        # 複数番号がある場合は、1番号1意味程度に絞ってスッキリさせる
                        max_meanings = 1 if len(clean_target_sup_list) > 1 else 2
                        meanings = extract_meanings_from_item(item, max_per_item=max_meanings)
                        for m in meanings:
                            if m not in all_extracted_meanings:
                                all_extracted_meanings.append(m)

            return all_extracted_meanings[:8] # 全体でも最大8つ程度に制限
            
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            time.sleep(2)
            
    return all_extracted_meanings

def main():
    start_from = 0
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r') as f:
                line = f.readline()
                if line: start_from = int(line)
        except: pass

    rows = []
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, mode='r', encoding='utf-8-sig') as f:
            rows = list(csv.DictReader(f))
    else:
        with open(INPUT_FILE, mode='r', encoding='utf-8-sig') as f:
            rows = list(csv.DictReader(f))

    fieldnames = ['번호', '순위', '단어', '단어번호', '품사', '품사 이름', '품사 (일본어)', '풀이（意味）', '등급', '일본어 뜻']

    print(f"Total rows: {len(rows)}. Starting from: {start_from}")

    session = requests.Session()
    
    try:
        for i in range(start_from, len(rows)):
            row = rows[i]
            if row.get('일본어 뜻'):
                continue

            word = row['단어']
            sup_nos = [n.strip() for n in row['단어번호'].split(',') if n.strip()]
            pos_names = [p.strip() for p in row['품사 이름'].split(',')]
            
            print(f"[{i+1}/{len(rows)}] Processing: {word} (Nos: {', '.join(sup_nos)})")
            
            meanings = fetch_japanese_meanings(session, word, sup_nos, pos_names)
            meaning_str = ', '.join(meanings)
            row['일본어 뜻'] = meaning_str
            
            if meaning_str:
                print(f" -> Result: {meaning_str}")
            
            if (i + 1) % 10 == 0 or (i + 1) == len(rows):
                save_data(fieldnames, rows)
                with open(PROGRESS_FILE, 'w') as f:
                    f.write(str(i + 1))
                print(f"--- Progress saved at {i+1} ---")
            
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("Interrupted.")
    finally:
        save_data(fieldnames, rows)
        print("Final data saved.")

def save_data(fieldnames, rows):
    with open(OUTPUT_FILE, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

if __name__ == "__main__":
    main()
