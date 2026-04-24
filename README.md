
# Goal
最終的にAnkiデッキにする。

# Input
- level1.csv
- level2.csv
- level3.csv
- level4.csv
- level5.csv

# Output
- level1_anki.csv
- level2_anki.csv
- level3_anki.csv
- level4_anki.csv
- level5_anki.csv

# Rules
- 日本語の意味の列を加える
- 어종が외래어は元のアルファベットを残しつつカタカナに直してそれを記述
- 어종が한자어のものは漢字を日本で使われてる漢字に変換して記述
- 品詞も日本語に直して
- タグを作っていくので、タグの列も加える。タグの内容は外来語、漢字語とかの区分と、品詞。


LLMで処理してこの日本語の意味を作っていきます。
build_level1_anki.py


---
追加
- 의미の日本語訳もしてほしい。
- 途中で止めても・止まってもいいように随時CSVに保存してほしい。（最終的に40000語なので…）

