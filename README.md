# 韓国語学習用語彙リストの加工プロジェクト

韓国語学習用の語彙リスト（CSV）を、学習やアプリ開発に使いやすい形式に加工・整理するプロジェクトです。

## 構成
- `data/`: 加工前後のデータファイル
  - `한국어 학습용 어휘 목록.csv`: オリジナルの語彙リスト
  - `한국어 학습용 어휘 목록_최종_スッキリ版.csv`: 加工・統合済みの最終版
- `scripts/`: データ加工に使用した Python スクリプト群

## 加工内容
1. **単語のクリーンアップ**: 単語の後ろについていた辞書番号（例：`가격03` → `가격`）を分離・削除しました。
2. **品詞の翻訳**: 記号で表記されていた品詞を正式名称（韓国語）に変換し、さらに日本語訳（例：`名詞`, `動詞`）の列を追加しました。
3. **重複の統合**:
   - 同じ表記の単語を1つのレコードにまとめました。
   - **順位**: 重複する中で最小の数値を採用。
   - **品詞・意味**: すべての品詞と意味をカンマで列挙。
   - **等級**: `A > B > C` の優先順位で最高のものを採用。

## 作成者
- kaedesato (main@kaedesato.work)

## 環境変数
- `OPENROUTER_API_KEY`: 日本語訳をLLM（OpenRouter）で生成するために必須です。
- `OPENROUTER_MODEL`: 使用するモデル名です（デフォルト: `openai/gpt-4o-mini`）。
- 参考として [.env.example](.env.example) を置いてあります。

## build_level1_anki.py の実行
`build_level1_anki.py` は現在、全件LLM翻訳が主経路です。漢字互換置換や外来語カタカナ辞書に依存した訳語生成は行いません。

### 例: まず安定重視で実行
```bash
python build_level1_anki.py \
  --input level1.csv \
  --output level1_anki_new_b25.csv \
  --review-output level1_anki_new_review_b25.csv \
  --llm-batch-size 20 \
  --llm-retries 4 \
  --llm-timeout 20 \
  --progress-every 1
```

### 主要オプション
- `--llm-batch-size`: 1リクエストあたりの語数（目安: 20〜50）
- `--llm-retries`: バッチ失敗時の再試行回数
- `--llm-timeout`: 1リクエストのタイムアウト秒数
- `--progress-every`: 何バッチごとに進捗を表示するか

実行完了時に `OpenRouter requests: ...` が表示され、実際のAPI呼び出し回数を確認できます。
