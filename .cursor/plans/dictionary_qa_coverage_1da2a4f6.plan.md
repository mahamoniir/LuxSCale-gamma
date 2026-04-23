---
name: Dictionary QA Coverage
overview: Inventory all chat-related dictionary JSON files (Q/A, synonyms, examples, hint patterns), then define an automated validation strategy to test schema integrity, cross-file consistency, and runtime behavior.
todos:
  - id: inventory-dictionaries
    content: Build a complete inventory of dictionary JSON sections (Q/A, synonyms, examples, hint/pattern lists) across the scoped files.
    status: completed
  - id: define-schema-contracts
    content: Define schema/type contracts and validation rules for each dictionary section.
    status: completed
  - id: cross-file-ref-validation
    content: Define checks that validate dictionary mappings and response refs against standards_cleaned and internal IDs.
    status: completed
  - id: dictionary-quality-rules
    content: Define quality checks for duplicates, missing localized entries, malformed patterns, and weak example coverage.
    status: completed
  - id: routing-test-cases
    content: Define dictionary-driven runtime test cases for route outcomes and language behavior without Gemini dependency.
    status: completed
  - id: ci-gating-plan
    content: Define execution order, reporting, and CI gating policy for dictionary validation and behavior tests.
    status: completed
isProject: false
---

# Dictionary Collection and Test Plan

## Scope: Dictionary JSON Files to Include
- Primary Q/A dictionary: [assets/fixed_responses.json](assets/fixed_responses.json)
  - Contains `menu_items`, `responses` (`question`, `answer`, `variants`, `answer_variants`), `static_intents`, and `match_hints`.
- Synonyms/aliases dictionary: [standards/aliases_upgraded.json](standards/aliases_upgraded.json)
  - Contains place aliases and parameter aliases used for intent/entity normalization.
- Keyword/examples dictionary: [standards/standards_keywords_upgraded.json](standards/standards_keywords_upgraded.json)
  - Contains `common_mappings`, `category_keywords`, `keyword_to_refs`, plus `usage_guide.examples`.
- Reference truth table for ref validation: [standards/standards_cleaned.json](standards/standards_cleaned.json)
  - Used to validate that all mapped `ref_no` values in dictionaries are valid.

## What to Collect From Each Dictionary
- From [assets/fixed_responses.json](assets/fixed_responses.json):
  - Q/A pairs: `responses[].question`, `responses[].answer`
  - Synonym-style fields: `responses[].variants`, `static_intents[].patterns_en|patterns_ar|patterns_norm`
  - Hint/prefix-like signal sets: `match_hints.*`
  - Coverage samples: `menu_items[].question`, `answer_variants`, `localized_answers`
- From [standards/aliases_upgraded.json](standards/aliases_upgraded.json):
  - Synonym sets by canonical key for `places` and `parameters`
- From [standards/standards_keywords_upgraded.json](standards/standards_keywords_upgraded.json):
  - Keyword synonym mappings: `common_mappings`, `keyword_to_refs`, `category_keywords`
  - Example guidance: `usage_guide.examples`, `usage_guide.lookup_flow`

## Test Strategy
- **Schema integrity tests**
  - Validate required keys/types/emptiness for each dictionary section.
  - Validate regex patterns in `static_intents` compile successfully.
  - Validate no malformed entries (empty canonical keys, non-list alias sets, invalid language map shapes).
- **Cross-file consistency tests**
  - Every `source_refs`/mapped ref in dictionary files must exist in [standards/standards_cleaned.json](standards/standards_cleaned.json).
  - Canonical place names expected by chat routing should be present in aliases dictionary.
  - Ensure response IDs referenced by `menu_items` and `static_intents` exist in `responses`.
- **Content quality tests**
  - Detect duplicate/near-duplicate variants and conflicting canonical mappings.
  - Ensure multilingual coverage where required (`localized_answers` for selected intents).
  - Flag missing examples in sections that are expected to provide onboarding examples.
- **Runtime behavior tests (dictionary-driven)**
  - Build test cases from dictionary examples/variants and assert expected route class (`static_local`, `fixed_exact`, `fixed_suggested`, `planning_local`).
  - Verify language-localized outputs for Arabic/English dictionary inputs.
  - Verify no Gemini dependency for resolvable dictionary cases.

## Proposed Deliverables
- Dictionary inventory report (machine-readable + human-readable):
  - [documentation/back-end/dictionary-inventory.md](documentation/back-end/dictionary-inventory.md)
  - [documentation/back-end/dictionary-inventory.json](documentation/back-end/dictionary-inventory.json)
- Automated validation test module:
  - [tests/chat/test_dictionary_integrity.py](tests/chat/test_dictionary_integrity.py)
- Dictionary-driven routing tests:
  - [tests/chat/test_dictionary_routing.py](tests/chat/test_dictionary_routing.py)
- Optional reusable checker script for CI/local runs:
  - [tools/check_dictionaries.py](tools/check_dictionaries.py)

## Execution Flow
- Run integrity checks first (fast fail).
- Run cross-file consistency checks.
- Run routing behavior suite with deterministic mocks.
- Publish inventory + failures summary for dictionary maintainers.
- Gate CI on integrity + consistency; keep behavior suite required for chat changes.
