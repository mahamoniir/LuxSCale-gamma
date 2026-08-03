"""
Standards lookup service — turns ``standards/standards_cleaned.json`` (331 full rows)
and ``standards/standards_keywords_upgraded.json`` (keyword → ref_no index) into a
two-step "pick a category, then pick a task/activity" flow, plus free-text detection
for when the caller doesn't know which category applies.

Public functions
-----------------
list_categories()            -> every real category in the data, with keyword hints
list_tasks(category)         -> every ref_no/task row inside one category
detect_category(text)        -> ranked category guesses from free text
resolve_ref(ref_no)          -> the full standards_cleaned.json row for one ref_no

"Category" here always means the *combined* key used by standards_keywords_upgraded.json:
``category_base`` alone, or ``"{category_base} – {category_sub}"`` when a sub-category
exists (en-dash, matches the keyword file exactly). This keeps the category dropdown and
the keyword hints pointing at the same thing.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional

try:
    from luxscale.paths import project_root
except Exception:  # pragma: no cover - fallback if paths.py layout differs
    def project_root() -> str:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_DASH = " \u2013 "  # " – " en-dash separator, matches standards_keywords_upgraded.json


def _standards_dir() -> str:
    return os.path.join(project_root(), "standards")


@lru_cache(maxsize=1)
def _load_cleaned() -> List[Dict[str, Any]]:
    path = os.path.join(_standards_dir(), "standards_cleaned.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _load_keywords() -> Dict[str, Any]:
    path = os.path.join(_standards_dir(), "standards_keywords_upgraded.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def clear_standards_cache() -> None:
    """Call after editing either JSON file on disk so the next request reloads it."""
    _load_cleaned.cache_clear()
    _load_keywords.cache_clear()


def _combined_category(row: Dict[str, Any]) -> str:
    base = (row.get("category_base") or "").strip()
    sub = (row.get("category_sub") or "").strip() if row.get("category_sub") else ""
    return f"{base}{_DASH}{sub}" if sub else base


def _norm_ref(ref: Any) -> str:
    return str(ref or "").strip()


# ── categories ──────────────────────────────────────────────────────────────

def list_categories() -> List[Dict[str, Any]]:
    """
    One entry per distinct (category_base [, category_sub]) combination actually
    present in standards_cleaned.json, ordered by table number. Each entry carries
    the ref_no count and, when available, the keyword list from category_keywords
    so the client can show hints without a second round trip.
    """
    rows = _load_cleaned()
    kw = _load_keywords()
    category_keywords = kw.get("category_keywords") or {}

    grouped: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for row in rows:
        key = _combined_category(row)
        if key not in grouped:
            grouped[key] = {
                "category": key,
                "category_base": row.get("category_base"),
                "category_sub": row.get("category_sub"),
                "ref_count": 0,
                "first_table": row.get("table"),
                "keywords": category_keywords.get(key, []),
            }
            order.append(key)
        grouped[key]["ref_count"] += 1

    def _table_sort_key(v: Any) -> tuple:
        parts = re.findall(r"\d+", str(v.get("first_table") or ""))
        return tuple(int(p) for p in parts) if parts else (999,)

    return sorted(grouped.values(), key=_table_sort_key)


# ── tasks within a category ──────────────────────────────────────────────────

def list_tasks(category: str) -> List[Dict[str, Any]]:
    """
    Every ref_no/task_or_activity row inside one combined category key (as returned
    by list_categories()['category']). Returns [] for an unknown category rather
    than raising, so the route can decide how to report "not found".
    """
    category = (category or "").strip()
    if not category:
        return []
    out = []
    for row in _load_cleaned():
        if _combined_category(row) == category:
            out.append(
                {
                    "ref_no": row.get("ref_no"),
                    "table": row.get("table"),
                    "task_or_activity": row.get("task_or_activity"),
                    "Em_r_lx": row.get("Em_r_lx"),
                    "Em_u_lx": row.get("Em_u_lx"),
                    "Uo": row.get("Uo"),
                    "Ra": row.get("Ra"),
                }
            )
    out.sort(key=lambda r: [int(p) for p in re.findall(r"\d+", str(r.get("ref_no") or ""))] or [999])
    return out


def known_categories() -> List[str]:
    return [c["category"] for c in list_categories()]


# ── free-text detection ──────────────────────────────────────────────────────

def _tokenize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", (text or "").lower()).strip()


def detect_category(text: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Rank candidate categories/ref_nos for a free-text room description, following
    the keyword file's own lookup_flow: common_mappings first, then keyword_to_refs,
    then a category_keywords substring scan. Every hit accumulates a score so
    multi-keyword matches (e.g. "open plan office corridor") outrank single hits.

    Returns up to `limit` entries:
      { category, matched_keywords: [...], ref_nos: [...], score, sample_tasks: [...] }
    """
    norm = _tokenize(text)
    if not norm:
        return []

    kw = _load_keywords()
    common_mappings: Dict[str, List[str]] = kw.get("common_mappings") or {}
    keyword_to_refs: Dict[str, List[str]] = kw.get("keyword_to_refs") or {}
    category_keywords: Dict[str, List[str]] = kw.get("category_keywords") or {}

    rows_by_ref = {_norm_ref(r.get("ref_no")): r for r in _load_cleaned()}

    # ref_no -> {score, matched_keywords}
    ref_hits: Dict[str, Dict[str, Any]] = {}

    def _add(ref_nos: List[str], keyword: str, weight: float) -> None:
        for ref in ref_nos:
            ref = _norm_ref(ref)
            entry = ref_hits.setdefault(ref, {"score": 0.0, "matched_keywords": set()})
            entry["score"] += weight
            entry["matched_keywords"].add(keyword)

    # 1. common_mappings — exact/substring phrase match, highest weight
    for phrase, ref_nos in common_mappings.items():
        p = _tokenize(phrase)
        if p and (p == norm or f" {p} " in f" {norm} "):
            _add(ref_nos, phrase, 3.0)

    # 2. keyword_to_refs — individual keyword/synonym match
    for keyword, ref_nos in keyword_to_refs.items():
        k = _tokenize(keyword)
        if k and (k == norm or f" {k} " in f" {norm} "):
            _add(ref_nos, keyword, 2.0)

    # 3. category_keywords — broader substring scan, lowest weight, category-level
    cat_scores: Dict[str, Dict[str, Any]] = {}
    for category, words in category_keywords.items():
        matched = [w for w in words if _tokenize(w) and f" {_tokenize(w)} " in f" {norm} "]
        if matched:
            cat_scores[category] = {"score": 1.0 * len(matched), "matched_keywords": set(matched)}

    # Roll ref-level hits up into per-category candidates
    categories: Dict[str, Dict[str, Any]] = {}
    for ref, hit in ref_hits.items():
        row = rows_by_ref.get(ref)
        if not row:
            continue
        cat = _combined_category(row)
        c = categories.setdefault(
            cat, {"category": cat, "score": 0.0, "matched_keywords": set(), "ref_nos": set()}
        )
        c["score"] += hit["score"]
        c["matched_keywords"] |= hit["matched_keywords"]
        c["ref_nos"].add(ref)

    for cat, hit in cat_scores.items():
        c = categories.setdefault(
            cat, {"category": cat, "score": 0.0, "matched_keywords": set(), "ref_nos": set()}
        )
        c["score"] += hit["score"]
        c["matched_keywords"] |= hit["matched_keywords"]
        if not c["ref_nos"]:
            # No specific ref_no hit yet — offer every ref_no in that category
            c["ref_nos"] = {
                _norm_ref(r.get("ref_no")) for r in _load_cleaned() if _combined_category(r) == cat
            }

    results = []
    for c in categories.values():
        ref_nos = sorted(c["ref_nos"], key=lambda r: [int(p) for p in re.findall(r"\d+", r)] or [999])
        sample_tasks = [
            {"ref_no": r, "task_or_activity": rows_by_ref[r].get("task_or_activity")}
            for r in ref_nos[:5]
            if r in rows_by_ref
        ]
        results.append(
            {
                "category": c["category"],
                "score": round(c["score"], 2),
                "matched_keywords": sorted(c["matched_keywords"]),
                "ref_nos": ref_nos,
                "sample_tasks": sample_tasks,
            }
        )

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


# ── single ref_no resolution ─────────────────────────────────────────────────

def resolve_ref(ref_no: str) -> Optional[Dict[str, Any]]:
    ref_key = _norm_ref(ref_no)
    if not ref_key:
        return None
    for row in _load_cleaned():
        if _norm_ref(row.get("ref_no")) == ref_key:
            return row
    return None
