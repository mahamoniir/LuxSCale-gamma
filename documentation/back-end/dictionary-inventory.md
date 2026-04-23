# Dictionary Inventory

## Files
- `fixed_responses`: `assets/fixed_responses.json`
- `aliases`: `standards/aliases_upgraded.json`
- `keywords`: `standards/standards_keywords_upgraded.json`
- `standards`: `standards/standards_cleaned.json`

## Fixed Responses Dictionary
- Menu items: 16
- Responses: 16
- Static intents: 2
- Q/A pairs: 16
- Variant phrases: 176
- Localized answer entries: 2
- Pattern count: 35

## Aliases Dictionary
- Place canonical keys: 15
- Total place aliases: 222
- Parameter canonical keys: 19
- Total parameter aliases: 156

## Keywords Dictionary
- common_mappings keys: 210
- category_keywords keys: 28
- keyword_to_refs keys: 123
- usage examples: 3
- lookup_flow steps: 4

## Standards Dictionary
- rows: 331

## Validation Snapshot
- No issues detected in current snapshot.

## Validation Contracts
- Schema contracts:
  - `assets/fixed_responses.json` requires `menu_items`, `responses`, `static_intents`, `match_hints`.
  - Each response must have non-empty `id`, `question`, and `answer`.
  - Static intent regex fields must compile.
  - Alias and keyword mappings must be object-of-list structures.
- Cross-file contracts:
  - `menu_items[].response_id` and `static_intents[].response_id` must resolve to existing `responses[].id`.
  - Numeric `source_refs` must exist in `standards_cleaned.ref_no`.
  - Required routing places (`Factory`, `Office`, `Warehouse`, `Classroom`, `Corridor`, `Retail`) must exist in aliases.
- Quality contracts:
  - No duplicate response IDs.
  - Duplicate normalized variants are reported.
  - Low variant coverage and missing usage examples are flagged.

## Runtime Routing Test Matrix
- `static_local`: bilingual standard-name intent examples.
- `fixed_exact`: direct dictionary Q/A lookup examples.
- `fixed_suggested`: near-match semantic question examples.
- `planning_local`: English and Arabic fixture-count study questions.
- Language behavior: current message language must override context language.
- Gemini isolation: dictionary-resolvable paths must not call Gemini.

## Execution Flow and CI Gating
- Local run sequence:
  1. `python tools/check_dictionaries.py --check`
  2. `python tools/check_dictionaries.py --write-inventory --check`
  3. `python -m unittest discover -s tests -p "test_*.py"`
- CI policy:
  - Fail build on any `error` issue from `--check`.
  - Keep `warning` issues visible in logs and inventory report for follow-up.
  - Require routing test suite to pass for chat dictionary changes.
