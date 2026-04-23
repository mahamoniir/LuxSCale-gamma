"""
Dictionary inventory and validation helpers for chat dictionaries.

This module is intentionally dependency-free so it can run in CI with:
    python tools/check_dictionaries.py --check
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
FIXED_RESPONSES_PATH = ROOT / "assets" / "fixed_responses.json"
ALIASES_PATH = ROOT / "standards" / "aliases_upgraded.json"
KEYWORDS_PATH = ROOT / "standards" / "standards_keywords_upgraded.json"
STANDARDS_CLEANED_PATH = ROOT / "standards" / "standards_cleaned.json"

INVENTORY_JSON_PATH = ROOT / "documentation" / "back-end" / "dictionary-inventory.json"
INVENTORY_MD_PATH = ROOT / "documentation" / "back-end" / "dictionary-inventory.md"


@dataclass
class Issue:
    severity: str  # "error" | "warning"
    code: str
    message: str
    path: str

    def as_dict(self) -> Dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "path": self.path,
        }


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_dictionary_bundle() -> Dict[str, Any]:
    return {
        "fixed_responses": _load_json(FIXED_RESPONSES_PATH),
        "aliases": _load_json(ALIASES_PATH),
        "keywords": _load_json(KEYWORDS_PATH),
        "standards_cleaned": _load_json(STANDARDS_CLEANED_PATH),
    }


def _count_list_items(values: Iterable[Any]) -> int:
    return sum(1 for _ in values)


def _total_items_in_mapping_list_values(mapping: Dict[str, Any]) -> int:
    total = 0
    for value in mapping.values():
        if isinstance(value, list):
            total += len(value)
    return total


def build_inventory(bundle: Dict[str, Any]) -> Dict[str, Any]:
    fixed = bundle["fixed_responses"]
    aliases = bundle["aliases"]
    keywords = bundle["keywords"]
    standards = bundle["standards_cleaned"]

    responses = list(fixed.get("responses") or [])
    menu_items = list(fixed.get("menu_items") or [])
    static_intents = list(fixed.get("static_intents") or [])
    match_hints = dict(fixed.get("match_hints") or {})

    places = dict(aliases.get("places") or {})
    parameters = dict(aliases.get("parameters") or {})

    common_mappings = dict(keywords.get("common_mappings") or {})
    category_keywords = dict(keywords.get("category_keywords") or {})
    keyword_to_refs = dict(keywords.get("keyword_to_refs") or {})
    usage_examples = dict((keywords.get("usage_guide") or {}).get("examples") or {})

    inventory = {
        "files": {
            "fixed_responses": str(FIXED_RESPONSES_PATH.relative_to(ROOT)).replace("\\", "/"),
            "aliases": str(ALIASES_PATH.relative_to(ROOT)).replace("\\", "/"),
            "keywords": str(KEYWORDS_PATH.relative_to(ROOT)).replace("\\", "/"),
            "standards_cleaned": str(STANDARDS_CLEANED_PATH.relative_to(ROOT)).replace("\\", "/"),
        },
        "fixed_responses": {
            "menu_items_count": len(menu_items),
            "responses_count": len(responses),
            "static_intents_count": len(static_intents),
            "match_hints_keys": sorted(match_hints.keys()),
            "qa_pair_count": sum(
                1
                for response in responses
                if str(response.get("question") or "").strip() and str(response.get("answer") or "").strip()
            ),
            "variant_phrase_count": sum(
                len(response.get("variants") or []) + len(response.get("answer_variants") or [])
                for response in responses
            ),
            "localized_answer_entries": sum(
                1
                for response in responses
                if isinstance(response.get("localized_answers"), dict) and response.get("localized_answers")
            ),
            "pattern_count": sum(
                len(intent.get("patterns_en") or [])
                + len(intent.get("patterns_ar") or [])
                + len(intent.get("patterns_norm") or [])
                for intent in static_intents
            ),
            "sample_questions": [str(item.get("question") or "") for item in menu_items[:8]],
        },
        "aliases_upgraded": {
            "places_canonical_count": len(places),
            "places_alias_total": _total_items_in_mapping_list_values(places),
            "parameters_canonical_count": len(parameters),
            "parameters_alias_total": _total_items_in_mapping_list_values(parameters),
        },
        "standards_keywords_upgraded": {
            "common_mappings_count": len(common_mappings),
            "category_keywords_count": len(category_keywords),
            "keyword_to_refs_count": len(keyword_to_refs),
            "usage_examples_count": len(usage_examples),
            "lookup_flow_steps": _count_list_items((keywords.get("usage_guide") or {}).get("lookup_flow") or []),
            "sample_keywords": list(keyword_to_refs.keys())[:15],
        },
        "standards_cleaned": {
            "rows_count": len(standards) if isinstance(standards, list) else 0,
            "sample_ref_nos": [
                str(row.get("ref_no") or "")
                for row in (standards[:10] if isinstance(standards, list) else [])
                if isinstance(row, dict)
            ],
        },
    }
    return inventory


def validate_schema(bundle: Dict[str, Any]) -> List[Issue]:
    issues: List[Issue] = []
    fixed = bundle["fixed_responses"]
    aliases = bundle["aliases"]
    keywords = bundle["keywords"]
    standards = bundle["standards_cleaned"]

    for required_key in ("menu_items", "responses", "static_intents", "match_hints"):
        if required_key not in fixed:
            issues.append(Issue("error", "missing_key", f"Missing key '{required_key}'", "assets/fixed_responses.json"))

    responses = fixed.get("responses") or []
    if not isinstance(responses, list):
        issues.append(Issue("error", "type_mismatch", "'responses' must be a list", "assets/fixed_responses.json"))
    else:
        for idx, response in enumerate(responses):
            rid = str(response.get("id") or "").strip() if isinstance(response, dict) else ""
            path = f"assets/fixed_responses.json:responses[{idx}]"
            if not rid:
                issues.append(Issue("error", "missing_response_id", "Response missing id", path))
            if not str(response.get("question") or "").strip():
                issues.append(Issue("error", "missing_question", "Response missing question", path))
            if not str(response.get("answer") or "").strip():
                issues.append(Issue("error", "missing_answer", "Response missing answer", path))
            for field_name in ("variants", "answer_variants"):
                field = response.get(field_name)
                if field is not None and not isinstance(field, list):
                    issues.append(Issue("error", "type_mismatch", f"'{field_name}' must be list when present", path))
            localized = response.get("localized_answers")
            if localized is not None and not isinstance(localized, dict):
                issues.append(Issue("error", "type_mismatch", "'localized_answers' must be object", path))

    static_intents = fixed.get("static_intents") or []
    for idx, intent in enumerate(static_intents):
        path = f"assets/fixed_responses.json:static_intents[{idx}]"
        if not str(intent.get("intent_key") or "").strip():
            issues.append(Issue("error", "missing_intent_key", "Static intent missing intent_key", path))
        if not str(intent.get("response_id") or "").strip():
            issues.append(Issue("error", "missing_response_id", "Static intent missing response_id", path))
        for field_name in ("patterns_en", "patterns_ar", "patterns_norm"):
            patterns = intent.get(field_name)
            if patterns is None:
                continue
            if not isinstance(patterns, list):
                issues.append(Issue("error", "type_mismatch", f"'{field_name}' must be list", path))
                continue
            for pat_idx, pattern in enumerate(patterns):
                try:
                    re.compile(str(pattern))
                except re.error as exc:
                    issues.append(
                        Issue(
                            "error",
                            "invalid_regex",
                            f"Invalid regex in {field_name}[{pat_idx}]: {exc}",
                            path,
                        )
                    )

    for mapping_name in ("places", "parameters"):
        mapping = aliases.get(mapping_name)
        path = f"standards/aliases_upgraded.json:{mapping_name}"
        if not isinstance(mapping, dict):
            issues.append(Issue("error", "type_mismatch", f"'{mapping_name}' must be object", path))
            continue
        for canonical, alias_list in mapping.items():
            if not str(canonical).strip():
                issues.append(Issue("error", "empty_canonical", "Empty canonical key", path))
            if not isinstance(alias_list, list):
                issues.append(Issue("error", "type_mismatch", "Aliases value must be list", path))

    for mapping_name in ("common_mappings", "category_keywords", "keyword_to_refs"):
        mapping = keywords.get(mapping_name)
        path = f"standards/standards_keywords_upgraded.json:{mapping_name}"
        if not isinstance(mapping, dict):
            issues.append(Issue("error", "type_mismatch", f"'{mapping_name}' must be object", path))
            continue
        for _, refs in mapping.items():
            if not isinstance(refs, list):
                issues.append(Issue("error", "type_mismatch", "Mapping value must be list", path))

    if not isinstance(standards, list):
        issues.append(Issue("error", "type_mismatch", "'standards_cleaned' must be list", "standards/standards_cleaned.json"))
    return issues


def validate_cross_refs(bundle: Dict[str, Any]) -> List[Issue]:
    issues: List[Issue] = []
    fixed = bundle["fixed_responses"]
    aliases = bundle["aliases"]
    keywords = bundle["keywords"]
    standards = bundle["standards_cleaned"] if isinstance(bundle["standards_cleaned"], list) else []

    valid_refs = {str(row.get("ref_no") or "").strip() for row in standards if isinstance(row, dict)}
    response_ids = {str(response.get("id") or "").strip() for response in (fixed.get("responses") or [])}

    for idx, menu_item in enumerate(fixed.get("menu_items") or []):
        response_id = str(menu_item.get("response_id") or "").strip()
        if response_id and response_id not in response_ids:
            issues.append(
                Issue(
                    "error",
                    "dangling_menu_response_id",
                    f"menu_items[{idx}].response_id '{response_id}' not found in responses",
                    "assets/fixed_responses.json",
                )
            )

    for idx, intent in enumerate(fixed.get("static_intents") or []):
        response_id = str(intent.get("response_id") or "").strip()
        if response_id and response_id not in response_ids:
            issues.append(
                Issue(
                    "error",
                    "dangling_static_intent_response_id",
                    f"static_intents[{idx}].response_id '{response_id}' not found in responses",
                    "assets/fixed_responses.json",
                )
            )

    for idx, response in enumerate(fixed.get("responses") or []):
        refs = list(response.get("source_refs") or [])
        for ref in refs:
            ref_text = str(ref or "").strip()
            if not ref_text:
                continue
            if ref_text in valid_refs:
                continue
            if "/" in ref_text or "." not in ref_text:
                # file/path or symbolic reference, not a numeric ref_no
                continue
            issues.append(
                Issue(
                    "error",
                    "invalid_source_ref_no",
                    f"responses[{idx}] source_refs contains unknown ref '{ref_text}'",
                    "assets/fixed_responses.json",
                )
            )

    place_keys = set((aliases.get("places") or {}).keys())
    required_place_keys = {"Factory", "Office", "Warehouse", "Classroom", "Corridor", "Retail"}
    for place in sorted(required_place_keys):
        if place not in place_keys:
            issues.append(
                Issue(
                    "error",
                    "missing_place_alias_group",
                    f"Expected place alias group '{place}' for chat routing",
                    "standards/aliases_upgraded.json",
                )
            )

    for mapping_name in ("common_mappings", "keyword_to_refs"):
        mapping = keywords.get(mapping_name) or {}
        for keyword, refs in mapping.items():
            for ref in refs:
                ref_text = str(ref or "").strip()
                if ref_text and ref_text not in valid_refs:
                    issues.append(
                        Issue(
                            "warning",
                            "unmapped_keyword_ref_no",
                            (
                                f"{mapping_name} keyword '{keyword}' maps to ref '{ref_text}' "
                                "which is not present in standards_cleaned.json"
                            ),
                            "standards/standards_keywords_upgraded.json",
                        )
                    )
    return issues


def _normalize_phrase(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]+", " ", (value or "").strip().lower())).strip()


def validate_quality(bundle: Dict[str, Any]) -> List[Issue]:
    issues: List[Issue] = []
    fixed = bundle["fixed_responses"]
    responses = list(fixed.get("responses") or [])

    seen_ids: set[str] = set()
    for idx, response in enumerate(responses):
        rid = str(response.get("id") or "").strip()
        path = f"assets/fixed_responses.json:responses[{idx}]"
        if rid in seen_ids:
            issues.append(Issue("error", "duplicate_response_id", f"Duplicate response id '{rid}'", path))
        seen_ids.add(rid)

        phrases: List[str] = []
        phrases.append(str(response.get("question") or ""))
        phrases.extend(str(v) for v in (response.get("variants") or []))
        norm = [_normalize_phrase(p) for p in phrases if _normalize_phrase(p)]
        if len(set(norm)) < len(norm):
            issues.append(Issue("warning", "duplicate_variants", "Duplicate normalized variant(s) in response", path))

        answer_variants = list(response.get("answer_variants") or [])
        if answer_variants and len(answer_variants) < 2:
            issues.append(Issue("warning", "low_answer_variant_count", "Less than 2 answer variants", path))

    for idx, intent in enumerate(fixed.get("static_intents") or []):
        path = f"assets/fixed_responses.json:static_intents[{idx}]"
        answers = intent.get("answers")
        if answers is not None and not isinstance(answers, dict):
            issues.append(Issue("warning", "non_object_answers", "Static intent answers should be object by language", path))

    usage_examples = dict(((bundle["keywords"].get("usage_guide") or {}).get("examples")) or {})
    if not usage_examples:
        issues.append(
            Issue(
                "warning",
                "missing_usage_examples",
                "No usage_guide.examples found in standards keywords dictionary",
                "standards/standards_keywords_upgraded.json",
            )
        )
    return issues


def render_inventory_markdown(inventory: Dict[str, Any], issues: Optional[List[Issue]] = None) -> str:
    files = inventory["files"]
    fixed = inventory["fixed_responses"]
    aliases = inventory["aliases_upgraded"]
    keywords = inventory["standards_keywords_upgraded"]
    standards = inventory["standards_cleaned"]
    issue_lines = []
    for issue in issues or []:
        issue_lines.append(f"- `{issue.severity}` `{issue.code}`: {issue.message} (`{issue.path}`)")
    if not issue_lines:
        issue_lines = ["- No issues detected in current snapshot."]

    return "\n".join(
        [
            "# Dictionary Inventory",
            "",
            "## Files",
            f"- `fixed_responses`: `{files['fixed_responses']}`",
            f"- `aliases`: `{files['aliases']}`",
            f"- `keywords`: `{files['keywords']}`",
            f"- `standards`: `{files['standards_cleaned']}`",
            "",
            "## Fixed Responses Dictionary",
            f"- Menu items: {fixed['menu_items_count']}",
            f"- Responses: {fixed['responses_count']}",
            f"- Static intents: {fixed['static_intents_count']}",
            f"- Q/A pairs: {fixed['qa_pair_count']}",
            f"- Variant phrases: {fixed['variant_phrase_count']}",
            f"- Localized answer entries: {fixed['localized_answer_entries']}",
            f"- Pattern count: {fixed['pattern_count']}",
            "",
            "## Aliases Dictionary",
            f"- Place canonical keys: {aliases['places_canonical_count']}",
            f"- Total place aliases: {aliases['places_alias_total']}",
            f"- Parameter canonical keys: {aliases['parameters_canonical_count']}",
            f"- Total parameter aliases: {aliases['parameters_alias_total']}",
            "",
            "## Keywords Dictionary",
            f"- common_mappings keys: {keywords['common_mappings_count']}",
            f"- category_keywords keys: {keywords['category_keywords_count']}",
            f"- keyword_to_refs keys: {keywords['keyword_to_refs_count']}",
            f"- usage examples: {keywords['usage_examples_count']}",
            f"- lookup_flow steps: {keywords['lookup_flow_steps']}",
            "",
            "## Standards Dictionary",
            f"- rows: {standards['rows_count']}",
            "",
            "## Validation Snapshot",
            *issue_lines,
            "",
            "## Validation Contracts",
            "- Schema contracts:",
            "  - `assets/fixed_responses.json` requires `menu_items`, `responses`, `static_intents`, `match_hints`.",
            "  - Each response must have non-empty `id`, `question`, and `answer`.",
            "  - Static intent regex fields must compile.",
            "  - Alias and keyword mappings must be object-of-list structures.",
            "- Cross-file contracts:",
            "  - `menu_items[].response_id` and `static_intents[].response_id` must resolve to existing `responses[].id`.",
            "  - Numeric `source_refs` must exist in `standards_cleaned.ref_no`.",
            "  - Required routing places (`Factory`, `Office`, `Warehouse`, `Classroom`, `Corridor`, `Retail`) must exist in aliases.",
            "- Quality contracts:",
            "  - No duplicate response IDs.",
            "  - Duplicate normalized variants are reported.",
            "  - Low variant coverage and missing usage examples are flagged.",
            "",
            "## Runtime Routing Test Matrix",
            "- `static_local`: bilingual standard-name intent examples.",
            "- `fixed_exact`: direct dictionary Q/A lookup examples.",
            "- `fixed_suggested`: near-match semantic question examples.",
            "- `planning_local`: English and Arabic fixture-count study questions.",
            "- Language behavior: current message language must override context language.",
            "- Gemini isolation: dictionary-resolvable paths must not call Gemini.",
            "",
            "## Execution Flow and CI Gating",
            "- Local run sequence:",
            "  1. `python tools/check_dictionaries.py --check`",
            "  2. `python tools/check_dictionaries.py --write-inventory --check`",
            "  3. `python -m unittest discover -s tests -p \"test_*.py\"`",
            "- CI policy:",
            "  - Fail build on any `error` issue from `--check`.",
            "  - Keep `warning` issues visible in logs and inventory report for follow-up.",
            "  - Require routing test suite to pass for chat dictionary changes.",
            "",
        ]
    )


def run_all_checks(bundle: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Issue]]:
    inventory = build_inventory(bundle)
    issues: List[Issue] = []
    issues.extend(validate_schema(bundle))
    issues.extend(validate_cross_refs(bundle))
    issues.extend(validate_quality(bundle))
    return inventory, issues


def write_inventory_files(inventory: Dict[str, Any], issues: List[Issue]) -> None:
    INVENTORY_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "inventory": inventory,
        "issues": [issue.as_dict() for issue in issues],
    }
    INVENTORY_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    INVENTORY_MD_PATH.write_text(render_inventory_markdown(inventory, issues), encoding="utf-8")


def _print_issues(issues: List[Issue]) -> None:
    if not issues:
        print("No dictionary issues found.")
        return
    for issue in issues:
        print(f"[{issue.severity}] {issue.code}: {issue.message} ({issue.path})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory and validate dictionary JSON files.")
    parser.add_argument("--check", action="store_true", help="Run validations and print issues.")
    parser.add_argument(
        "--write-inventory",
        action="store_true",
        help="Write inventory snapshot to documentation/back-end/*.json|*.md",
    )
    args = parser.parse_args()

    bundle = load_dictionary_bundle()
    inventory, issues = run_all_checks(bundle)

    if args.write_inventory:
        write_inventory_files(inventory, issues)
        print(f"Wrote inventory JSON: {INVENTORY_JSON_PATH}")
        print(f"Wrote inventory markdown: {INVENTORY_MD_PATH}")

    if args.check:
        _print_issues(issues)
        has_error = any(issue.severity == "error" for issue in issues)
        return 1 if has_error else 0

    if not args.write_inventory and not args.check:
        # default action: run checks and print summary only
        _print_issues(issues)
        return 1 if any(issue.severity == "error" for issue in issues) else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
