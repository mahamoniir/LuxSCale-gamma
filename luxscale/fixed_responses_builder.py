"""
Build and refresh ``assets/fixed_responses.json`` for chat fallbacks.

The generated file is editable by humans:
- ``generated_answer`` is refreshed from project data.
- ``answer`` is preserved when manually edited.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from typing import Any, Dict, List, Optional

from luxscale.paths import project_root


DEFAULT_FIXED_RESPONSES_PATH = os.path.join(
    project_root(), "assets", "fixed_responses.json"
)
STANDARDS_CLEANED_PATH = os.path.join(
    project_root(), "standards", "standards_cleaned.json"
)
STANDARDS_KEYWORDS_PATH = os.path.join(
    project_root(), "standards", "standards_keywords_upgraded.json"
)
FIXTURE_MAP_PATH = os.path.join(
    project_root(), "assets", "fixture_map_SC_IES_Fixed_v3.json"
)
IES_INDEX_PATH = os.path.join(project_root(), "ies-render", "ies.json")


def _load_json(path: str, default: Any) -> Any:
    if not os.path.isfile(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _standard_row_by_ref(rows: List[dict]) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for row in rows:
        ref = str(row.get("ref_no") or "").strip()
        if ref:
            out[ref] = row
    return out


def _format_standard_answer(row: dict) -> str:
    ref = str(row.get("ref_no") or "-")
    task = str(row.get("task_or_activity") or "target task")
    em = row.get("Em_r_lx", row.get("Em_u_lx", "?"))
    uo = row.get("Uo", "?")
    ra = row.get("Ra", "?")
    return (
        f"Use EN 12464-1 ref {ref} for \"{task}\". "
        f"Target maintained illuminance is about {em} lx with Uo >= {uo} and CRI (Ra) >= {ra}. "
        "In LuxSCale, verify both E_avg and U0 before finalizing."
    )


def _build_answer_variants(answer: str) -> List[str]:
    base = str(answer or "").strip()
    if not base:
        return []
    return [
        base,
        f"Short answer: {base}",
        f"From LuxSCale references: {base}",
        f"Recommended baseline: {base}",
        f"For quick implementation: {base}",
    ]


def _safe_ref_lookup(
    keyword_to_refs: Dict[str, List[str]], by_ref: Dict[str, dict], keyword: str
) -> Optional[dict]:
    refs = keyword_to_refs.get(keyword, []) or []
    for ref in refs:
        row = by_ref.get(str(ref))
        if row:
            return row
    return None


def _fixture_summary(fixture_map: dict) -> Dict[str, Any]:
    entries = fixture_map.get("entries") or []
    grouped: Dict[str, Dict[str, Any]] = {}
    for e in entries:
        name = str(e.get("api_luminaire_name") or "").strip()
        if not name:
            continue
        g = grouped.setdefault(
            name,
            {
                "name": name,
                "powers": [],
                "product_url": "",
                "product_title": "",
                "image_url": "",
                "ies_count": 0,
            },
        )
        try:
            pw = int(e.get("power_w", 0))
            if pw > 0 and pw not in g["powers"]:
                g["powers"].append(pw)
        except Exception:
            pass
        g["ies_count"] += 1
        online = e.get("online") or {}
        if not g["product_url"] and online.get("product_url"):
            g["product_url"] = str(online.get("product_url"))
        if not g["product_title"] and online.get("product_title"):
            g["product_title"] = str(online.get("product_title"))
        imgs = e.get("image_urls") or []
        if not g["image_url"] and isinstance(imgs, list) and imgs:
            g["image_url"] = str(imgs[0])
    rows = list(grouped.values())
    for r in rows:
        r["powers"].sort()
    rows.sort(key=lambda x: x["name"].lower())
    return {
        "total_entries": len(entries),
        "families": rows,
    }


def _ies_summary(ies_index: dict) -> dict:
    summary = ies_index.get("summary") or {}
    entries = ies_index.get("entries") or []
    ok_entries = [e for e in entries if e.get("status") == "ok"]
    sample_shapes = sorted(
        {
            str((e.get("header") or {}).get("shape") or "").strip()
            for e in ok_entries[:120]
            if (e.get("header") or {}).get("shape")
        }
    )
    return {
        "files_total": int(summary.get("files_total") or len(entries) or 0),
        "parsed_ok": int(summary.get("parsed_ok") or len(ok_entries) or 0),
        "parse_failed": int(summary.get("parse_failed") or 0),
        "sample_shapes": sample_shapes[:8],
    }


def _build_generated_responses(
    standards_rows: List[dict],
    standards_keywords: dict,
    fixture_map: dict,
    ies_index: dict,
) -> Dict[str, Any]:
    by_ref = _standard_row_by_ref(standards_rows)
    keyword_to_refs = standards_keywords.get("keyword_to_refs") or {}
    fixtures = _fixture_summary(fixture_map)
    ies_info = _ies_summary(ies_index)

    office = _safe_ref_lookup(keyword_to_refs, by_ref, "office")
    cad = _safe_ref_lookup(keyword_to_refs, by_ref, "cad")
    classroom = _safe_ref_lookup(keyword_to_refs, by_ref, "classroom")
    warehouse = _safe_ref_lookup(keyword_to_refs, by_ref, "warehouse")
    factory = _safe_ref_lookup(keyword_to_refs, by_ref, "factory")
    retail = _safe_ref_lookup(keyword_to_refs, by_ref, "retail")
    corridor = _safe_ref_lookup(keyword_to_refs, by_ref, "corridor")

    menu_items: List[Dict[str, Any]] = []
    responses: List[Dict[str, Any]] = []

    def add_response(
        resp_id: str,
        label: str,
        question: str,
        variants: List[str],
        tags: List[str],
        answer: str,
        source_refs: List[str],
        canonical_key: Optional[str] = None,
        localized_answers: Optional[Dict[str, str]] = None,
    ) -> None:
        menu_items.append(
            {"id": resp_id, "label": label, "question": question, "response_id": resp_id}
        )
        responses.append(
            {
                "id": resp_id,
                "canonical_key": str(canonical_key or resp_id),
                "label": label,
                "question": question,
                "variants": variants,
                "tags": tags,
                "generated_answer": answer,
                "answer": answer,
                "answer_variants": _build_answer_variants(answer),
                "source_refs": source_refs,
                "localized_answers": dict(localized_answers or {}),
            }
        )

    if office:
        add_response(
            "std_office_target",
            "Office Lux Target",
            "What lux and U0 do I use for office workstations?",
            [
                "office lighting target",
                "required lux for office",
                "office workstation standard",
                "open office lux level",
            ],
            ["standards", "office", "en12464"],
            _format_standard_answer(office),
            [str(office.get("ref_no"))],
        )
    add_response(
        "std_code_name",
        "European Code Name",
        "What is the name of the European lighting code used by LuxSCale?",
        [
            "what is the european code used",
            "name of european lighting standard",
            "which code does luxscale use",
            "en 12464 name",
            "bs en 12464 1",
            "what is en12464",
            "ايه اسم الكود الاوروبي",
            "ما اسم المعيار الاوروبي",
            "اسم الكود الاوروبي",
            "اسم معيار الانارة الاوروبي",
            "اي الكود الاوروبي بتاعك",
            "الكود الاوروبي بتاعك ايه",
            "شغال ب كود ايه",
            "شغال على كود ايه",
            "بتستخدم كود اوروبي ايه",
            "اي معيار شغال عليه",
            "what standard do you follow",
            "what code are you using",
            "which lighting standard are you based on",
        ],
        ["standards", "code-name", "en12464"],
        (
            "The European workplace indoor lighting standard used by LuxSCale is EN 12464-1. "
            "When users ask for the code name, respond with EN 12464-1."
        ),
        ["standards/standards_cleaned.json"],
            localized_answers={
                "en": "The European workplace indoor lighting standard used by LuxSCale is EN 12464-1.",
                "ar": "المعيار الأوروبي المستخدم في LuxSCale هو EN 12464-1.",
            },
    )
    if cad:
        add_response(
            "std_cad_target",
            "CAD / Technical Drawing",
            "What is the lighting target for CAD or technical drawing?",
            ["cad lux standard", "technical drawing lux", "drafting workstation lux"],
            ["standards", "cad", "en12464"],
            _format_standard_answer(cad),
            [str(cad.get("ref_no"))],
        )
    if classroom:
        add_response(
            "std_classroom_target",
            "Classroom Lighting",
            "What are classroom lux and uniformity targets?",
            ["classroom lux standard", "school classroom lighting", "education room lux"],
            ["standards", "classroom", "en12464"],
            _format_standard_answer(classroom),
            [str(classroom.get("ref_no"))],
        )
    if warehouse:
        add_response(
            "std_warehouse_target",
            "Warehouse Gangways",
            "What lighting level is used for warehouse gangways?",
            [
                "warehouse lux standard",
                "storage gangway lighting",
                "warehouse aisle lux",
                "factory lighting target",
                "industrial area lux level",
            ],
            ["standards", "warehouse", "en12464"],
            _format_standard_answer(warehouse),
            [str(warehouse.get("ref_no"))],
        )
    if factory:
        add_response(
            "std_factory_target",
            "Factory / Industrial Area",
            "What lux and U0 targets are used for factories or industrial areas?",
            [
                "factory lux standard",
                "factories lux target",
                "industrial area lux target",
                "manufacturing area lighting target",
                "workshop lux standard",
            ],
            ["standards", "factory", "industrial", "en12464"],
            _format_standard_answer(factory),
            [str(factory.get("ref_no"))],
        )
    if retail:
        add_response(
            "std_retail_target",
            "Retail Sales Area",
            "What target lux/U0 is used for general retail sales area?",
            ["retail store lux", "shop lighting target", "sales area illuminance"],
            ["standards", "retail", "en12464"],
            _format_standard_answer(retail),
            [str(retail.get("ref_no"))],
        )
    if corridor:
        add_response(
            "std_corridor_target",
            "Corridors",
            "What lux/U0 targets are typical for corridors?",
            ["corridor lux level", "circulation area illuminance", "hallway lighting target"],
            ["standards", "corridor", "en12464"],
            _format_standard_answer(corridor),
            [str(corridor.get("ref_no"))],
        )

    family_lines = []
    for fam in fixtures["families"]:
        powers = ", ".join(f"{p}W" for p in fam["powers"]) if fam["powers"] else "various powers"
        family_lines.append(f"- {fam['name']}: {powers}")
    catalog_answer = (
        "LuxSCale currently includes these fixture families in the mapped catalog:\n"
        + "\n".join(family_lines[:10])
        + "\nShare room type + dimensions + target lux/U0, and I can narrow the best options."
    )
    add_response(
        "fixture_catalog_overview",
        "Available Fixture Families",
        "What fixtures are available in LuxSCale?",
        [
            "available luminaires",
            "fixture families",
            "what products can i use",
            "catalog list",
        ],
        ["fixtures", "catalog"],
        catalog_answer,
        ["assets/fixture_map_SC_IES_Fixed_v3.json"],
    )

    highbay = next((f for f in fixtures["families"] if f["name"].lower() == "sc highbay"), None)
    street = next((f for f in fixtures["families"] if f["name"].lower() == "sc street"), None)
    flood = next(
        (f for f in fixtures["families"] if f["name"].lower() == "sc flood light exterior"), None
    )
    rec_lines = []
    for fam in [highbay, flood, street]:
        if not fam:
            continue
        powers = ", ".join(f"{p}W" for p in fam["powers"]) if fam["powers"] else "mapped powers"
        rec_lines.append(f"- {fam['name']} ({powers})")
    add_response(
        "fixture_recommendation_baseline",
        "Fixture Recommendation Basics",
        "How does LuxSCale choose fixture recommendations?",
        [
            "how do you recommend fixtures",
            "fixture recommendation logic",
            "choose luminaire",
            "best fixture selection",
        ],
        ["fixtures", "recommendation"],
        (
            "Recommendation starts from task targets (lux/U0), then checks beam behavior and layout spacing.\n"
            "Common starting families in this catalog are:\n"
            + "\n".join(rec_lines)
            + "\nFinal selection should be validated with E_avg, U0, and total power."
        ),
        ["assets/fixture_map_SC_IES_Fixed_v3.json", "ies-render/ies.json"],
    )

    add_response(
        "ies_dataset_overview",
        "IES Dataset Health",
        "How many IES files are in LuxSCale and are they parsed?",
        [
            "ies dataset status",
            "ies files count",
            "photometry database status",
            "ies parsing health",
        ],
        ["ies", "dataset"],
        (
            f"The current IES index reports {ies_info['files_total']} files, "
            f"with {ies_info['parsed_ok']} parsed and {ies_info['parse_failed']} failed. "
            "LuxSCale uses this indexed photometry for layout and comparator workflows."
        ),
        ["ies-render/ies.json"],
    )

    add_response(
        "uniformity_reflection_behavior",
        "Uniformity and Reflection Note",
        "Do reflections change U0 in the current LuxSCale model?",
        [
            "does reflectance affect u0",
            "reflection effect on uniformity",
            "u0 with inter reflection",
            "uniformity and reflected light",
        ],
        ["uniformity", "reflection", "model-limit"],
        (
            "In the current model, inter-reflection is applied as a uniform E boost (direct E × (1+f)). "
            "That changes absolute E_avg but does not change U0/U1 ratios."
        ),
        ["luxscale/uniformity_calculator.py", "luxscale/app_settings.py"],
    )

    add_response(
        "non_lighting_scope",
        "Out-of-Scope Guard",
        "Can you answer non-lighting questions?",
        [
            "tell me about cooking",
            "write me a poem",
            "general knowledge question",
            "not about lighting",
        ],
        ["policy", "scope"],
        (
            "This assistant is optimized for lighting engineering in LuxSCale. "
            "For non-lighting topics, it will avoid AI token usage and ask you to provide a lighting-related question."
        ),
        ["chat-topic-gate"],
    )

    add_response(
        "company_designer_info",
        "LuxSCale Team and Official Website",
        "Who designed LuxSCale and what is the official company website?",
        [
            "who designed luxscale",
            "who built luxscale",
            "luxscale company website",
            "official website of luxscale company",
            "who made you luxscale",
            "who developed this tool",
            "who owns luxscale",
            "who operates luxscale",
            "what is your company website",
            "main website of short circuit",
            "who created this system",
            "ايه موقع الشركة الرئيسي",
            "ما هو الموقع الرسمي للشركة",
            "الشركة اللي صممتك",
            "مين صممك يا luxscale",
            "من صمم luxscale",
            "من طور هذه الاداة",
            "مين عملك",
            "مين عمل التول دي",
            "مين اللي عمل السيستم ده",
            "الشركة المطورة ليك",
            "ايه موقع شورت سيركت",
        ],
        ["company", "about", "shortcircuit"],
        (
            "LuxSCale is designed by the R&D team of Short Circuit Company for lighting solutions in Egypt and UAE. "
            "Official website: https://shortcircuit.company"
        ),
        ["company-profile"],
        localized_answers={
            "en": (
                "LuxSCale is designed by the R&D team of Short Circuit Company for lighting solutions in Egypt and UAE. "
                "Official website: https://shortcircuit.company"
            ),
            "ar": (
                "تم تصميم LuxSCale بواسطة فريق البحث والتطوير في شركة Short Circuit "
                "لحلول الإضاءة في مصر والإمارات. "
                "الموقع الرسمي: https://shortcircuit.company"
            ),
        },
    )

    match_hints = {
        "lighting_positive": [
            "lux",
            "illuminance",
            "luminaire",
            "fixture",
            "beam",
            "uniformity",
            "u0",
            "u1",
            "ies",
            "lighting",
            "en 12464",
            "office lighting",
            "highbay",
            "flood light",
            "street light",
            "downlight",
            "triproof",
            "reflectance",
            "en12464",
            "bs en",
            "cct",
            "cri",
            "ra",
        ],
        "lighting_positive_ar": [
            "اضاءة",
            "إضاءة",
            "انارة",
            "إنارة",
            "لوكس",
            "تجانس",
            "معيار",
            "كود",
            "مصباح",
            "تركيبة",
            "ies",
            "يو او",
        ],
        "recommendation_intent": [
            "recommend",
            "best fixture",
            "best luminaire",
            "which fixture",
            "choose fixture",
            "compare fixtures",
            "suggest fixture",
        ],
        "recommendation_intent_ar": [
            "اقترح",
            "ترشيح",
            "انسب تركيبه",
            "افضل تركيبه",
            "افضل مصباح",
            "اي تركيبه",
            "اختار تركيبه",
        ],
        "negative_scope": [
            "weather",
            "football",
            "movie",
            "music",
            "recipe",
            "politics",
            "stock market",
            "travel",
            "poem",
            "joke",
        ],
        "negative_scope_ar": [
            "طقس",
            "كرة قدم",
            "فيلم",
            "اغنية",
            "وصفة",
            "سياسة",
            "بورصة",
            "سفر",
            "نكتة",
        ],
    }

    return {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sources": {
            "standards_cleaned": "standards/standards_cleaned.json",
            "standards_keywords": "standards/standards_keywords_upgraded.json",
            "fixture_map": "assets/fixture_map_SC_IES_Fixed_v3.json",
            "ies_index": "ies-render/ies.json",
        },
        "menu_items": menu_items,
        "responses": responses,
        "static_intents": [
            {
                "intent_key": "standard_name",
                "response_id": "std_code_name",
                "answers": {
                    "en": "The European workplace indoor lighting standard used by LuxSCale is EN 12464-1.",
                    "ar": "المعيار الأوروبي المستخدم في LuxSCale هو EN 12464-1.",
                },
                "patterns_en": [
                    r"\b(what|which)\s+(is\s+)?(the\s+)?(european|eu|en)\s+(lighting\s+)?(code|standard)\b",
                    r"\b(name\s+of\s+the\s+standard|code\s+name)\b",
                    r"\bname\s+of\s+the\s+standard\b",
                    r"\b(?:what|which|tell me|give me).*(?:code|standard).*(?:used|use|using)\b",
                    r"\bwhat\s+standard\s+do\s+you\s+follow\b",
                    r"\bwhat\s+code\s+are\s+you\s+using\b",
                ],
                "patterns_ar": [
                    r"اسم\s+الكود\s+الاوروبي",
                    r"اسم\s+المعيار\s+الاوروبي",
                    r"ايه\s+اسم\s+الكود\s+الاوروبي",
                    r"ما\s+اسم\s+المعيار",
                    r"(?:ايه|اي|ما)\s*(?:هو\s*)?(?:الكود|المعيار)\s+الاوروبي",
                    r"الكود\s+الاوروبي\s+(?:بتاعك|المستخدم|اللي\s+شغال\s+بيه)",
                    r"شغال\s*(?:ب|على)\s*كود\s*(?:ايه|اي)",
                    r"بتستخدم\s+كود\s+اوروبي\s+ايه",
                    r"(?:اي|ايه)\s+(?:الكود|كود)\s+الاوروبي",
                    r"(?:الكود|كود)\s+(?:اللي|الذي)\s+(?:شغال|بتشتغل|تستخدم)",
                    r"(?:بتستخدم|بتشتغل\s+ب|تعتمد\s+على)\s+(?:كود|معيار)",
                    r"ان\s*12464",
                    r"(?:اي|ايه)\s*معيار\s*(?:شغال|مستخدم)",
                    r"المعيار\s+اللي\s+بتستخدمه",
                ],
            },
            {
                "intent_key": "company_identity",
                "response_id": "company_designer_info",
                "patterns_en": [
                    r"\bwho\s+(?:designed|built|made|developed)\s+(?:you|luxscale)\b",
                    r"\b(?:official|main)\s+website\b",
                    r"\bluxscale\s+company\s+website\b",
                    r"\bwho\s+(?:owns|operates|runs)\s+luxscale\b",
                    r"\bwhat\s+is\s+your\s+company\s+website\b",
                ],
                "patterns_ar": [
                    r"ايه\s+موقع\s+الشركة\s+الرئيسي",
                    r"ما\s+هو\s+الموقع\s+الرسمي\s+للشركة",
                    r"الشركة\s+اللي\s+صممتك",
                    r"مين\s+صممك",
                    r"من\s+صمم\s+luxscale",
                    r"من\s+طور\s+هذه\s+الاداة",
                    r"مين\s+عملك",
                    r"مين\s+عمل\s+التول\s+دي",
                    r"الشركة\s+المطوره\s+ليك",
                    r"ايه\s+موقع\s+شورت\s+سيركت",
                ],
            },
        ],
        "match_hints": match_hints,
    }


def _existing_response_by_id(existing_doc: dict) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for r in existing_doc.get("responses") or []:
        rid = str(r.get("id") or "").strip()
        if rid:
            out[rid] = r
    return out


def _merge_with_existing(generated: dict, existing: dict) -> dict:
    existing_by_id = _existing_response_by_id(existing)
    merged = dict(generated)
    merged_responses: List[dict] = []

    for r in generated.get("responses") or []:
        rid = str(r.get("id") or "")
        prev = existing_by_id.get(rid)
        rr = dict(r)
        if prev:
            prev_answer = str(prev.get("answer") or "").strip()
            prev_generated = str(prev.get("generated_answer") or "").strip()
            if prev_answer and prev_answer != prev_generated:
                rr["answer"] = prev_answer
            elif prev_answer:
                rr["answer"] = rr.get("generated_answer", prev_answer)
            prev_answer_variants = prev.get("answer_variants")
            if isinstance(prev_answer_variants, list):
                cleaned = [str(v).strip() for v in prev_answer_variants if str(v).strip()]
                if cleaned:
                    rr["answer_variants"] = cleaned
            if not rr.get("answer_variants"):
                rr["answer_variants"] = _build_answer_variants(str(rr.get("answer") or ""))
            if not str(rr.get("canonical_key") or "").strip():
                rr["canonical_key"] = str(prev.get("canonical_key") or rr.get("id") or "")
            # Carry user-maintained non-generated fields.
            for carry_key in ("notes", "priority", "enabled"):
                if carry_key in prev and carry_key not in rr:
                    rr[carry_key] = prev[carry_key]
        merged_responses.append(rr)

    merged["responses"] = merged_responses
    merged["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    return merged


def build_fixed_responses_document() -> dict:
    standards_rows = _load_json(STANDARDS_CLEANED_PATH, [])
    standards_keywords = _load_json(STANDARDS_KEYWORDS_PATH, {})
    fixture_map = _load_json(FIXTURE_MAP_PATH, {})
    ies_index = _load_json(IES_INDEX_PATH, {})

    generated = _build_generated_responses(
        standards_rows=standards_rows,
        standards_keywords=standards_keywords,
        fixture_map=fixture_map,
        ies_index=ies_index,
    )
    existing = _load_json(DEFAULT_FIXED_RESPONSES_PATH, {})
    if isinstance(existing, dict) and existing.get("responses"):
        return _merge_with_existing(generated, existing)
    return generated


def regenerate_fixed_responses(output_path: Optional[str] = None) -> dict:
    path = output_path or DEFAULT_FIXED_RESPONSES_PATH
    doc = build_fixed_responses_document()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    return doc


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate assets/fixed_responses.json from standards/fixtures/IES data."
    )
    ap.add_argument(
        "--out",
        default=DEFAULT_FIXED_RESPONSES_PATH,
        help="Output JSON path (default: assets/fixed_responses.json)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and print summary only; do not write file.",
    )
    args = ap.parse_args(argv)

    doc = build_fixed_responses_document()
    if args.dry_run:
        print(
            json.dumps(
                {
                    "responses": len(doc.get("responses") or []),
                    "menu_items": len(doc.get("menu_items") or []),
                    "sources": doc.get("sources") or {},
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(
        f"Wrote {args.out} with {len(doc.get('responses') or [])} responses and "
        f"{len(doc.get('menu_items') or [])} menu items."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

