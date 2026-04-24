import argparse
import csv
import genanki
import random
from pathlib import Path

# Fixed model ID and deck ID base so they don't change on every run
# In practice, you might want to hardcode specific IDs here so updates work correctly
MODEL_ID = 1607392319
DECK_ID_BASE = 2059400000

def create_model():
    return genanki.Model(
        MODEL_ID,
        'Korean Vocabulary Model',
        fields=[
            {'name': 'Word'},           # 어휘
            {'name': 'Translation'},    # 日本語訳
            {'name': 'DefinitionJA'},   # 定義の日本語訳
            {'name': 'DefinitionKO'},   # 의미
            {'name': 'Origin'},         # 원어 / 日本の漢字 / 外来語
            {'name': 'POS'},            # 品詞
            {'name': 'WordType'},       # 어종
            {'name': 'Grade'},          # 등급
            {'name': 'Audio'},          # 音声
        ],
        templates=[
            {
                'name': 'Card 1',
                'qfmt': '''
<div class="card-content">
  <div class="word">{{Word}}</div>
  <div class="audio" style="text-align: center; margin-top: 10px;">{{Audio}}</div>
</div>
''',
                'afmt': '''
<div class="card-content">
  <div class="word">{{Word}}</div>
  <div class="audio" style="text-align: center; margin-top: 10px;">{{Audio}}</div>
  <hr id="answer">
  <div class="translation">{{Translation}}</div>
  
  {{#Origin}}
  <div class="origin">{{Origin}}</div>
  {{/Origin}}

  {{#DefinitionJA}}
  <div class="definition-section">
    <div class="definition-title">意味</div>
    <div class="definition-text">{{DefinitionJA}}</div>
  </div>
  {{/DefinitionJA}}
  
  {{#DefinitionKO}}
  <div class="definition-section">
    <div class="definition-title">韓国語の定義</div>
    <div class="definition-text">{{DefinitionKO}}</div>
  </div>
  {{/DefinitionKO}}
  
  <div class="meta-section">
    {{#POS}}
    <div class="info-row">
      <span class="label">品詞:</span> <span class="value">{{POS}}</span>
    </div>
    {{/POS}}
    
    {{#WordType}}
    <div class="info-row">
      <span class="label">語種:</span> <span class="value">{{WordType}}</span>
    </div>
    {{/WordType}}
  </div>
</div>
''',
            },
        ],
        css='''
.card {
  font-family: "Malgun Gothic", "Meiryo", sans-serif;
  font-size: 16px;
  text-align: center;
  color: #333;
  background-color: #f9f9f9;
}

.card.nightMode {
  color: #e0e0e0;
  background-color: #1e1e1e;
}

.card-content {
  max-width: 600px;
  margin: 0 auto;
  background: white;
  padding: 20px;
  border-radius: 10px;
  box-shadow: 0 4px 6px rgba(0,0,0,0.1);
  text-align: left;
}

.card.nightMode .card-content {
  background: #2d2d2d;
  box-shadow: 0 4px 6px rgba(0,0,0,0.3);
}

.word {
  font-size: 3em;
  text-align: center;
  font-weight: bold;
  color: #2c3e50;
  margin-bottom: 10px;
}

.card.nightMode .word {
  color: #ecf0f1;
}

.translation {
  font-size: 1.8em;
  text-align: center;
  color: #e74c3c;
  font-weight: bold;
  margin-bottom: 5px;
}

.origin {
  font-size: 1.2em;
  text-align: center;
  color: #7f8c8d;
  margin-bottom: 20px;
}

.card.nightMode .origin {
  color: #bdc3c7;
}

hr#answer {
  border: 0;
  border-bottom: 2px dashed #bdc3c7;
  margin: 20px 0;
}

.card.nightMode hr#answer {
  border-bottom: 2px dashed #7f8c8d;
}

.meta-section {
  margin-top: 15px;
  border-top: 1px solid #eee;
  padding-top: 15px;
}

.card.nightMode .meta-section {
  border-top: 1px solid #444;
}

.info-row {
  font-size: 1.1em;
  margin-bottom: 8px;
}

.label {
  font-weight: bold;
  color: #7f8c8d;
  display: inline-block;
  width: 60px;
}

.card.nightMode .label {
  color: #95a5a6;
}

.value {
  color: #2c3e50;
}

.card.nightMode .value {
  color: #ecf0f1;
}

.definition-section {
  margin-top: 20px;
  background: #f1f2f6;
  padding: 15px;
  border-radius: 8px;
}

.card.nightMode .definition-section {
  background: #34495e;
}

.definition-title {
  font-weight: bold;
  font-size: 0.9em;
  color: #95a5a6;
  margin-bottom: 5px;
  text-transform: uppercase;
}

.card.nightMode .definition-title {
  color: #bdc3c7;
}

.definition-text {
  font-size: 1.1em;
  line-height: 1.5;
  color: #34495e;
}

.card.nightMode .definition-text {
  color: #ecf0f1;
}
'''
    )

def build_origin_field(row):
    parts = []
    if row.get("원어"):
        parts.append(row["원어"])
    if row.get("日本の漢字"):
        parts.append(f"({row['日本の漢字']})")
    if row.get("外来語"):
        parts.append(f"[{row['外来語']}]")
    return " ".join(parts)

def build_pos_field(row):
    pos_ko = row.get("품사", "")
    pos_ja = row.get("日本語品詞", "")
    if pos_ko and pos_ja:
        return f"{pos_ko} ({pos_ja})"
    return pos_ko or pos_ja

def main():
    parser = argparse.ArgumentParser(description="Convert anki CSV to apkg")
    parser.add_argument("input_csv", help="Input CSV file (e.g. level1_anki.csv)")
    parser.add_argument("--deck-name", help="Name of the Anki deck", default=None)
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    if not input_path.exists():
        print(f"Error: {input_path} does not exist.")
        return 1

    deck_name = args.deck_name
    if not deck_name:
        import re
        match = re.search(r'level(\d+)', input_path.stem, re.IGNORECASE)
        if match:
            deck_name = f"韓国語::Level{match.group(1)}"
        else:
            deck_name = f"韓国語::{input_path.stem}"

    # Generate a deterministic ID based on the file name so updating the deck works
    # Using hash modulo is simple for string -> int
    deck_id = DECK_ID_BASE + (hash(input_path.stem) % 100000000)
    
    deck = genanki.Deck(
        deck_id,
        deck_name
    )
    
    model = create_model()

    count = 0
    with input_path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            word = row.get("어휘", "").strip()
            if not word:
                continue
                
            translation = row.get("日本語訳", "").strip()
            definition_ja = row.get("定義の日本語訳", "").strip()
            definition_ko = row.get("의미", "").strip()
            origin = build_origin_field(row).strip()
            pos = build_pos_field(row).strip()
            word_type = row.get("어종", "").strip()
            grade = row.get("등급", "").strip()
            
            # Read tags
            tags_raw = row.get("tags", "")
            tags = [t.strip() for t in tags_raw.split() if t.strip()]

            note = genanki.Note(
                model=model,
                fields=[
                    word,
                    translation,
                    definition_ja,
                    definition_ko,
                    origin,
                    pos,
                    word_type,
                    grade,
                    "",  # Audio
                ],
                tags=tags
            )
            deck.add_note(note)
            count += 1

    output_path = input_path.with_suffix(".apkg")
    genanki.Package(deck).write_to_file(str(output_path))
    
    print(f"Successfully generated {output_path} with {count} notes.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
