# Goal

Modify `build_level1_anki.py` to process `level1.csv` through `level5.csv` and generate `level1_anki.csv` through `level5_anki.csv` with additional features:
1. Translate part-of-speech to Japanese.
2. For `한자어` (Sino-Korean words), convert the Hanja (`원어`) to Japanese Shinjitai.
3. For `외래어` (Loanwords), keep the original alphabet but also provide the Katakana pronunciation.
4. Add a `tags` column combining word origin (外来語, 漢字語, etc.) and part-of-speech.

## User Review Required

No critical breaking changes, but the script name might be changed or we can just make it accept a list of levels to process. We will rename the script or just update it to loop through all levels by default.

## Open Questions

None.

## Proposed Changes

### `build_level1_anki.py` (or rename to `build_anki.py`)

- **Looping over files**: Modify `main()` to loop over `[1, 2, 3, 4, 5]`. For each level, read `level{i}.csv` and output `level{i}_anki.csv`.
- **LLM Payload Modification**: Add `pos` (품사) to the JSON payload sent to the LLM.
- **LLM Prompt Update**: Update the system/user prompt to request a JSON object per word that includes:
  - `translation`: Japanese meaning
  - `shinjitai`: Japanese Shinjitai conversion of the Hanja (if `한자어`)
  - `katakana`: Katakana reading of the loanword (if `외래어`)
  - `pos_ja`: Japanese translation of the part-of-speech
- **Row Processing Updates**:
  - Update `TranslationResult` and `ProcessedRow` to carry the new fields.
  - Update `build_tags` to include Japanese origin tags (e.g. 漢字語, 外来語) and the Japanese part-of-speech.
  - Format the `外来語_カタカナ候補` and `外来語_原語候補` columns appropriately. (We can actually put the format "アルファベット (カタカナ)" in a single column or use the separate columns that are already present). The user requested "元のアルファベットを残しつつカタカナに直してそれを記述" so we could do `原語 (カタカナ)` in a specific column or just use the separate columns.
  - Convert the `한자어` Hanja to Shinjitai and store it. The rules say "어종が한자어のものは漢字を日本で使われてる漢字に変換して記述". We can put this in a new column or overwrite `원어`. We'll add a `日本の漢字` column.
- **CSV Headers**: Ensure headers match the requested columns.

## Verification Plan

Run the script on `level1.csv` for a few rows (or wait for the user to run it) and verify the CSV output contains the correct Japanese translations, Shinjitai, Katakana, and Tags.
