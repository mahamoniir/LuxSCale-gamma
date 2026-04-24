"""
Chat fallback engine for Chat-with-LuxSCale.

Flow:
1) Exact fixed response
2) Semantic fixed suggestion + yes/no confirmation
3) Topic gate + short LLM answer (lighting-focused; out-of-scope otherwise)
"""
from __future__ import annotations

import json
import hashlib
import math
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from luxscale.app_logging import log_step, log_exception
from luxscale.app_settings import get_maintenance_factor, load_app_settings
from luxscale.fixture_catalog import load_fixture_map_document
from luxscale.gemini_manager import ask_gemini_text
from luxscale.lighting_calc import calculate_lighting
from luxscale.paths import project_root


FIXED_RESPONSES_PATH = os.path.join(project_root(), "assets", "fixed_responses.json")
ALIASES_PATHS = [
    os.path.join(project_root(), "standards", "aliases.json"),
    os.path.join(project_root(), "standards", "aliases_upgraded.json"),
]
STANDARDS_CLEANED_PATH = os.path.join(project_root(), "standards", "standards_cleaned.json")
STANDARDS_KEYWORDS_PATH = os.path.join(project_root(), "standards", "standards_keywords_upgraded.json")
PENDING_TTL_SECONDS = 20 * 60
_CONTEXT_MAX_MESSAGES = 12


_PENDING_LOCK = threading.Lock()
_PENDING_SUGGESTIONS: Dict[str, Dict[str, Any]] = {}
_TRANSLATION_CACHE_LOCK = threading.Lock()
_TRANSLATION_CACHE: Dict[str, str] = {}
_TRANSLATION_CACHE_MAX_ITEMS = 512
_CLARIFY_LOCK = threading.Lock()
_CLARIFY_STATE: Dict[str, Dict[str, Any]] = {}
_CLARIFY_TTL_SECONDS = 12 * 60

# Non-Short-Circuit / competitor luminaire name markers (advisory in Gemini reconcile).
_KNOWN_COMPETITOR_LUMINAIRE_RE = re.compile(
    r"\b(?:philips|osram|ledvance|trilux|zumtobel|erco|bega|siteco|sitel|cooper|dial|fagerhult|meanwell|mean\s*well|lithonia|acuity|hubbell)\b",
    re.IGNORECASE,
)
_SC_CATALOG_TOKEN = re.compile(
    r"(?i)\b(SC|SV|SP|BL)(?:\s*[-/]\s*|\s+)([A-Za-z0-9-]{2,})\b",
)
_IDENTITY_PLACE_EN = re.compile(
    r"\b(?:i(?:'m| am| work in| have a| run a| own a|'ve got a)|"
    r"this is a|it(?:'s| is) a|we(?:'re| are) a|for a)\b",
    re.IGNORECASE,
)
_IDENTITY_PLACE_AR = re.compile(
    r"(?:أنا|انا|عندي|عندنا|لدي|لدينا|هذا|ده|احنا|نحن)\s+"
    r"(?:مصنع|مكتب|مخزن|مدرسة|محل|متجر|ممر|ورشة|مستشفى|مستوصف|عيادة|جناح)",
    re.UNICODE,
)


@dataclass
class MatchResult:
    response: dict
    score: float
    matched_phrase: str


@dataclass
class StaticIntentMatch:
    intent_key: str
    answer: str
    response_id: str
    canonical_key: str


_AR_DIACRITICS_RE = re.compile(r"[\u0617-\u061A\u064B-\u0652\u0670\u06D6-\u06ED]")
_AR_CHAR_MAP = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "ة": "ه",
        "ـ": "",
    }
)
_COLLOQUIAL_NORMALIZATION = {
    "مين": "من",
    "مينه": "من",
    "مِين": "من",
    "دى": "دي",
    "دا": "ده",
    "ديه": "دي",
    "داه": "ده",
    "التول": "الاداه",
    "tool": "tool",
    "السيستم": "النظام",
    "بروجرام": "برنامج",
    "البرنامج": "برنامج",
    "بتاعك": "خاصتك",
}


def _normalize_arabic_text(text: str) -> str:
    s = str(text or "")
    if not s:
        return s
    s = s.translate(_AR_CHAR_MAP)
    s = _AR_DIACRITICS_RE.sub("", s)
    return s


def _apply_colloquial_normalization(text: str) -> str:
    s = str(text or "")
    if not s:
        return s
    for src, dst in _COLLOQUIAL_NORMALIZATION.items():
        s = re.sub(r"\b" + re.escape(src) + r"\b", dst, s, flags=re.IGNORECASE)
    return s


def _normalize_text(text: str) -> str:
    s = _normalize_arabic_text(str(text or ""))
    s = _apply_colloquial_normalization(s)
    s = s.strip().lower()
    s = re.sub(r"[^\w\s]+", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _response_canonical_key(response: Optional[dict]) -> str:
    if not isinstance(response, dict):
        return ""
    raw = str(response.get("canonical_key") or response.get("id") or "").strip()
    return raw or ""


def _hash_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _tokenize(text: str) -> List[str]:
    s = _normalize_text(text)
    if not s:
        return []
    return [t for t in s.split(" ") if len(t) > 1]


def _jaccard(tokens_a: List[str], tokens_b: List[str]) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    a = set(tokens_a)
    b = set(tokens_b)
    inter = len(a & b)
    union = len(a | b)
    if union <= 0:
        return 0.0
    return inter / union


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _coerce_context_messages(raw: Any) -> List[Dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, str]] = []
    for item in raw[-_CONTEXT_MAX_MESSAGES:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        text = (
            str(item.get("text") or "")
            or str(item.get("message") or "")
            or str(item.get("content") or "")
        ).strip()
        if not text:
            continue
        out.append({"role": role, "text": text})
    return out


def _context_user_questions(context_messages: List[Dict[str, str]]) -> List[str]:
    return [m["text"] for m in context_messages if m.get("role") == "user" and m.get("text")]


def _contains_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text or ""))


def _contains_latin(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]", text or ""))


def _detect_reply_language(question: str, context_messages: List[Dict[str, str]]) -> str:
    q = (question or "").strip()
    # Current user message has priority over historical context.
    if _contains_latin(q) and not _contains_arabic(q):
        return "en"
    if _contains_arabic(q):
        return "ar"
    prior_users = _context_user_questions(context_messages)
    if q and prior_users:
        recent = prior_users[-6:]
        ar_count = sum(1 for msg in recent if _contains_arabic(msg))
        # Keep language continuity for mixed sessions.
        if ar_count >= max(1, len(recent) // 2):
            return "ar"
        return "en"
    if q:
        return "en"
    if prior_users and _contains_arabic(prior_users[-1]):
        return "ar"
    return "en"


def _is_follow_up_question(question: str) -> bool:
    qn = _normalize_text(question)
    raw = str(question or "").strip()
    if not qn:
        return False
    follow_up_markers = (
        "what about",
        "how about",
        "and for",
        "for factory",
        "for office",
        "for warehouse",
        "same for",
        "also for",
        "and if",
        "then what",
        "what about it",
        "same case for",
        "same for this",
        "what about the",
        "and for the",
        "for the same",
        "also",
        "same for",
        "و",
        "وماذا عن",
        "ماذا عن",
        "طيب",
        "طب",
        "برضه",
        "ايضا",
        "أيضا",
        "نفس",
        "وال",
        "للم",
    )
    if any(m in qn for m in follow_up_markers):
        return True
    # Compact Arabic follow-up like "والمكتب؟", "للمصنع؟"
    if re.search(r"^(?:و)?(?:ال|لل)?(?:مكتب|مصنع|مخزن|مدرسه|مدرسة|محل|ممر)\??$", qn):
        return True
    if raw.startswith("و") and len(_tokenize(raw)) <= 3:
        return True
    return False


def _compose_effective_question(question: str, context_messages: List[Dict[str, str]]) -> str:
    if not _is_follow_up_question(question):
        return question
    users = _context_user_questions(context_messages)
    if not users:
        return question
    prev = users[-1]
    if _contains_arabic(question):
        return (
            f"سؤال المستخدم السابق: {prev}\n"
            f"سؤال متابعة: {question}"
        )
    return (
        f"Previous user question: {prev}\n"
        f"Follow-up question: {question}"
    )


def _answer_variants(base_answer: str) -> List[str]:
    a = str(base_answer or "").strip()
    if not a:
        return []
    return [
        a,
        f"Short answer: {a}",
        f"From LuxSCale references: {a}",
        f"Recommended baseline: {a}",
        f"For quick implementation: {a}",
    ]


def _response_answer_variants(response: dict) -> List[str]:
    existing = response.get("answer_variants")
    if isinstance(existing, list):
        cleaned = [str(x).strip() for x in existing if str(x).strip()]
        if cleaned:
            return cleaned
    return _answer_variants(str(response.get("answer") or ""))


def _response_localized_answer(response: dict, reply_language: str) -> str:
    if not isinstance(response, dict):
        return ""
    localized = response.get("localized_answers")
    if not isinstance(localized, dict):
        return ""
    text = str(localized.get(reply_language) or "").strip()
    if text:
        return text
    if reply_language != "en":
        text = str(localized.get("en") or "").strip()
        if text:
            return text
    return ""


def _pick_fixed_answer(response: dict, question: str, session_id: str) -> str:
    variants = _response_answer_variants(response)
    if not variants:
        return str(response.get("answer") or "")
    # For place/standard prompts, keep canonical wording.
    if len(_tokenize(question)) <= 2:
        return variants[0]
    if _is_standard_target_intent(question):
        return variants[0]
    if _detect_place_canonical(question) is not None:
        return variants[0]
    rid = str(response.get("id") or "")
    seed = f"{session_id}|{rid}|{_normalize_text(question)}"
    idx = abs(hash(seed)) % len(variants)
    return variants[idx]


def _is_repeated_question(
    question: str,
    context_messages: List[Dict[str, str]],
    response_hint: Optional[dict] = None,
) -> bool:
    # Numeric/layout questions are usually unique calculations.
    q = str(question or "")
    if re.search(r"\d+\s*[*x×]\s*\d+", q, flags=re.IGNORECASE):
        return False
    if re.search(r"\d+\s*(?:m|meters|ft|feet|lux|lm|w)\b", q, flags=re.IGNORECASE):
        return False

    prior_users = _context_user_questions(context_messages)
    if not prior_users:
        return False
    qn = _normalize_text(question)
    qt = _tokenize(question)
    for prev in prior_users[-8:]:
        pn = _normalize_text(prev)
        pt = _tokenize(prev)
        score = (_ratio(qn, pn) * 0.60) + (_jaccard(qt, pt) * 0.40)
        if score >= 0.82:
            return True

    if response_hint is None:
        return False

    rid = str(response_hint.get("id") or "")
    if not rid:
        return False
    for prev in prior_users[-8:]:
        ex = exact_fixed_match(prev)
        if ex is not None and str(ex.get("id") or "") == rid:
            return True
        sem = semantic_fixed_match(prev, threshold=0.56)
        if sem is not None and str((sem.response or {}).get("id") or "") == rid:
            return True
    return False


def _should_mark_repeated(
    question: str,
    context_messages: List[Dict[str, str]],
    response_hint: Optional[dict] = None,
    source_kind: str = "",
) -> bool:
    src = str(source_kind or "").strip().lower()
    tokens = _tokenize(question)
    qn = _normalize_text(question)
    prior_users = _context_user_questions(context_messages)
    if not qn or not prior_users:
        return False

    # Do not show repeated-banner for planning or open-ended AI paths.
    if src in {"planning_local", "gemini", "out_of_scope", "static_local"}:
        return False

    # For long/detailed questions, only treat as repeated on exact text match.
    if len(tokens) >= 7:
        return any(qn == _normalize_text(prev) for prev in prior_users[-8:])

    # For concise questions, keep semantic repeated detection.
    return _is_repeated_question(question, context_messages, response_hint=response_hint)


def _repeat_prefix(reply_language: str) -> str:
    if reply_language == "ar":
        return "هذا سؤال مكرر بصياغة مختلفة. الإجابة: "
    return "This appears to be a repeated question. Answer: "


def _apply_repeated_prefix(answer: str, reply_language: str) -> str:
    prefix = _repeat_prefix(reply_language)
    text = str(answer or "").strip()
    if not text:
        return text
    if text.lower().startswith(prefix.lower()):
        return text
    return f"{prefix}{text}"


def _translation_cache_get(text: str, target_lang: str) -> str:
    key = f"{target_lang}:{_hash_text(text)}"
    with _TRANSLATION_CACHE_LOCK:
        return str(_TRANSLATION_CACHE.get(key) or "")


def _translation_cache_put(text: str, target_lang: str, translated: str) -> None:
    key = f"{target_lang}:{_hash_text(text)}"
    with _TRANSLATION_CACHE_LOCK:
        if len(_TRANSLATION_CACHE) >= _TRANSLATION_CACHE_MAX_ITEMS:
            # Keep cache bounded with simple FIFO-like eviction.
            stale_key = next(iter(_TRANSLATION_CACHE.keys()), "")
            if stale_key:
                _TRANSLATION_CACHE.pop(stale_key, None)
        _TRANSLATION_CACHE[key] = str(translated or "")


def _try_local_arabic_standard_answer(text: str) -> str:
    s = str(text or "").strip()
    if not s:
        return ""
    m = re.search(
        r'Use\s+EN\s*12464-1\s+ref\s+([^ ]+)\s+for\s+"?([^".]+)"?.*?about\s+([0-9.]+)\s*lx.*?Uo\s*>=\s*([0-9.]+).*?CRI\s*\(Ra\)\s*>=\s*([0-9.]+)',
        s,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return ""
    ref = str(m.group(1) or "").strip()
    task = str(m.group(2) or "").strip()
    lux = str(m.group(3) or "").strip()
    u0 = str(m.group(4) or "").strip()
    ra = str(m.group(5) or "").strip()
    return (
        f'استخدم EN 12464-1 المرجع {ref} للمهمة "{task}". '
        f"الإضاءة المحافظة المطلوبة تقريبًا {lux} لوكس مع Uo >= {u0} و CRI (Ra) >= {ra}. "
        "في LuxSCale تأكد من E_avg و U0 قبل الاعتماد النهائي."
    )


def _translate_answer_if_needed(answer: str, reply_language: str) -> str:
    text = str(answer or "").strip()
    if not text or reply_language == "en":
        return text
    if reply_language == "ar":
        local_ar = _try_local_arabic_standard_answer(text)
        if local_ar:
            return local_ar
        cached = _translation_cache_get(text, "ar")
        if cached:
            return cached
        prompt = (
            "Translate the following lighting answer to Arabic. "
            "Keep numbers, units, standard references, and product names exactly as-is.\n\n"
            f"{text}"
        )
        g = ask_gemini_text(prompt, max_output_tokens=320, temperature=0.1)
        translated = str(g.get("text") or "").strip()
        if translated:
            _translation_cache_put(text, "ar", translated)
            return translated
        fallback = f"الإجابة:\n{text}"
        _translation_cache_put(text, "ar", fallback)
        return fallback
    return text


def _alias_query_patterns() -> Tuple[re.Pattern[str], ...]:
    return (
        re.compile(r"\balias(?:es)?\s+(?:of|for)\s+([\w\u0600-\u06FF/\-\s]+)\??$", re.IGNORECASE),
        re.compile(r"\bwhat(?:'s| is)?\s+the\s+alias(?:es)?\s+(?:of|for)\s+([\w\u0600-\u06FF/\-\s]+)\??$", re.IGNORECASE),
        re.compile(r"\b([\w\u0600-\u06FF/\-\s]+)\s+alias(?:es)?\??$", re.IGNORECASE),
        re.compile(r"\bsynonym(?:s)?\s+(?:of|for)\s+([\w\u0600-\u06FF/\-\s]+)\??$", re.IGNORECASE),
        re.compile(r"(?:مرادف|مرادفات)\s+([\w\u0600-\u06FF/\-\s]+)\??$", re.IGNORECASE),
    )


def _is_alias_query(question: str) -> bool:
    qn = _normalize_text(question)
    if not qn:
        return False
    markers = ("alias", "aliases", "synonym", "synonyms", "مرادف", "مرادفات")
    return any(m in qn for m in markers)


def _heuristic_place_tuples() -> List[Tuple[str, Tuple[str, ...]]]:
    return [
        (
            "Hospital",
            (
                "hospital",
                "hospitals",
                "healthcare",
                "health care",
                "clinic",
                "clinics",
                "medical center",
                "maternity",
                "ward",
                "wards",
                "patient room",
                "examination room",
                "icu",
                "مستشفى",
                "مستشفيات",
                "مريض",
                "مرضى",
                "مريضة",
                "عيادة",
                "عيادات",
                "رعاية",
                "غرفة مريض",
            ),
        ),
        (
            "Classroom",
            (
                "school",
                "schools",
                "classroom",
                "class room",
                "lecture",
                "training room",
                "فصل",
                "مدرسة",
                "قاعة دراسية",
            ),
        ),
        (
            "Office",
            (
                "office",
                "offices",
                "workspace",
                "workstation",
                "meeting room",
                "مكتب",
                "مكاتب",
                "غرفة اجتماع",
            ),
        ),
        (
            "Factory",
            (
                "factory",
                "factories",
                "industrial",
                "manufacturing",
                "workshop",
                "plant",
                "مصنع",
                "مصانع",
                "ورشة",
            ),
        ),
        (
            "Warehouse",
            (
                "warehouse",
                "warehouses",
                "storage",
                "stockroom",
                "gangway",
                "مخزن",
                "مستودع",
                "مستودعات",
            ),
        ),
        (
            "Corridor",
            (
                "corridor",
                "corridors",
                "hallway",
                "passageway",
                "ممر",
                "ممرات",
            ),
        ),
        (
            "Retail",
            (
                "retail",
                "shop",
                "shops",
                "store",
                "stores",
                "sales area",
                "showroom",
                "متجر",
                "محل",
                "منطقة بيع",
            ),
        ),
    ]


def _best_canonical_from_heuristics(
    base: str,
    token_forms: set,
) -> Optional[str]:
    hits: List[Tuple[str, int]] = []
    for canonical, kws in _heuristic_place_tuples():
        for kw in kws:
            kn = _normalize_text(kw)
            if not kn:
                continue
            if kn in token_forms:
                pos = int(base.find(kn))
                if pos < 0:
                    pos = 0
                hits.append((canonical, pos))
            else:
                try:
                    m = re.search(r"\b" + re.escape(kn) + r"\b", base)
                except re.error:
                    m = None
                if m:
                    hits.append((canonical, int(m.end())))
    if not hits:
        return None
    by_c: Dict[str, int] = {}
    for c, endpos in hits:
        by_c[c] = max(by_c.get(c, -1), int(endpos))
    if len(by_c) == 1:
        return next(iter(by_c))
    if "Hospital" in by_c and "Factory" in by_c:
        return "Hospital"
    return str(max(by_c.items(), key=lambda x: int(x[1]))[0])


def _extract_alias_target(question: str) -> str:
    q = (question or "").strip()
    if not q:
        return ""
    for pat in _alias_query_patterns():
        m = pat.search(q)
        if m:
            return str(m.group(1) or "").strip(" ?.:;,-_")
    return ""


def _static_intent_specs() -> List[Dict[str, Any]]:
    doc = load_fixed_responses_doc()
    raw = doc.get("static_intents")
    if isinstance(raw, list) and raw:
        out: List[Dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = str(item.get("intent_key") or "").strip()
            if not key:
                continue
            out.append(
                {
                    "intent_key": key,
                    "patterns_en": [
                        str(x).strip()
                        for x in (item.get("patterns_en") or [])
                        if str(x).strip()
                    ],
                    "patterns_ar": [
                        str(x).strip()
                        for x in (item.get("patterns_ar") or [])
                        if str(x).strip()
                    ],
                    "patterns_norm": [
                        str(x).strip()
                        for x in (item.get("patterns_norm") or [])
                        if str(x).strip()
                    ],
                    "response_id": str(item.get("response_id") or "").strip(),
                    "answers": item.get("answers") if isinstance(item.get("answers"), dict) else {},
                }
            )
        if out:
            return out

    return [
        {
            "intent_key": "standard_name",
            "patterns_en": [
                r"\b(what|which)\s+(is\s+)?(the\s+)?(european|eu|en)\s+(lighting\s+)?(code|standard)\b",
                r"\b(en|bs\s*en)\s*12464(?:-?1)?\b",
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
                r"بتستخدم\s+كود\s+اوروبي\s+ايه",
                r"(?:اي|ايه)\s+(?:الكود|كود)\s+الاوروبي",
                r"(?:الكود|كود)\s+(?:اللي|الذي)\s+(?:شغال|بتشتغل|تستخدم)",
                r"(?:بتستخدم|بتشتغل\s+ب|تعتمد\s+على)\s+(?:كود|معيار)",
                r"(?:اي|ايه)\s*معيار\s*(?:شغال|مستخدم)",
                r"المعيار\s+اللي\s+بتستخدمه",
                r"ان\s*12464",
            ],
            "patterns_norm": [
                "ايه الكود الاوروبي",
                "اي معيار شغال عليه",
                "الكود الاوروبي بتاعك",
            ],
            "response_id": "std_code_name",
            "answers": {
                "en": (
                    "The European workplace indoor lighting standard used here is EN 12464-1. "
                    "LuxSCale standard targets are mapped to EN 12464-1 task references."
                ),
                "ar": (
                    "المعيار الأوروبي المستخدم هنا هو EN 12464-1 "
                    "لإضاءة أماكن العمل الداخلية، وLuxSCale يربط الأهداف القياسية بمراجع هذا المعيار."
                ),
            },
        },
        {
            "intent_key": "company_identity",
            "patterns_en": [
                r"\bwho\s+(?:designed|built|made|developed)\s+(?:you|luxscale)\b",
                r"\b(?:official|main)\s+website\b",
                r"\bluxscale\s+company\s+website\b",
                r"\bwho\s+(?:owns|operates|runs)\s+luxscale\b",
                r"\bwhat\s+is\s+your\s+company\s+website\b",
                r"\bshort[\s-]*circuit\s+(?:company|co\.?|ltd|inc)\b",
                r"\babout\s+(?:the\s+)?(?:short[\s-]*circuit|shortcircuit|company)\b",
                r"\b(tell|talk)\s+me\s+about\s+.*\bshort[\s-]*circuit\b",
                r"\bshortcircuit\.company\b",
                r"\bwhat\s+is\s+short[\s-]*circuit\b",
                r"\bwho\s+(is|are)\s+short[\s-]*circuit\b",
            ],
            "patterns_ar": [
                r"ايه\s+موقع\s+الشركة\s+الرئيسي",
                r"ما\s+هو\s+الموقع\s+الرسمي\s+للشركة",
                r"الشركة\s+اللي\s+صممتك",
                r"مين\s+صممك",
                r"مين\s+عملك",
                r"مين\s+عمل\s+التول\s+دي",
                r"الشركة\s+المطوره\s+ليك",
                r"ايه\s+موقع\s+شورت\s+سيركت",
                r"من\s+صمم\s+luxscale",
                r"من\s+طور\s+هذه\s+الاداة",
            ],
            "patterns_norm": [
                "مين عملك",
                "مين عمل التول دي",
                "موقع الشركة الرئيسي",
            ],
            "response_id": "company_designer_info",
            "answers": {
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
        }
    ]


def _find_response_by_id(response_id: str) -> Optional[dict]:
    rid = str(response_id or "").strip()
    if not rid:
        return None
    doc = load_fixed_responses_doc()
    for r in doc.get("responses") or []:
        if str(r.get("id") or "").strip() == rid:
            return r
    return None


def _is_standard_name_lookup_question(raw_question: str, normalized_question: str) -> bool:
    q = str(raw_question or "")
    qn = str(normalized_question or "")
    if not qn:
        return False

    value_markers = (
        "target",
        "required",
        "requirement",
        "value",
        "lux",
        "u0",
        "cri",
        "ra",
        "للمكاتب",
        "للمصانع",
        "القيمة",
        "المطلوب",
        "لوكس",
        "تجانس",
    )
    if any(m in qn or m in q for m in value_markers):
        return False

    code_markers = (
        "code",
        "standard",
        "en 12464",
        "en12464",
        "12464",
        "الكود",
        "كود",
        "المعيار",
        "معيار",
    )
    if not any(m in qn or m in q for m in code_markers):
        return False

    ask_markers = (
        "what",
        "which",
        "name",
        "used",
        "use",
        "using",
        "used by",
        "your",
        "what code",
        "which code",
        "which standard",
        "tell me",
        "give me",
        "اسم",
        "ايه",
        "اي",
        "ما",
        "بتاعك",
        "شغال",
        "مستخدم",
        "تستخدم",
        "بتستخدم",
        "بتشتغل",
        "تعتمد",
    )
    return any(m in qn or m in q for m in ask_markers)


def _is_company_identity_lookup_question(q: str, qn: str) -> bool:
    """
    Heuristic: user is asking about Short Circuit / LuxSCale product identity (not a lighting calc).
    """
    if not qn:
        return False
    if re.search(r"\bshort[\s-]*circuit\b", q, flags=re.IGNORECASE) or re.search(
        r"\bshort[\s-]*circuit\b", qn
    ):
        return True
    if re.search(r"shortcircuit\.company", q, flags=re.IGNORECASE) or re.search(
        r"shortcircuit\.company", qn
    ):
        return True
    if (
        re.search(r"\b(lux[\s-]*scale|luxscale)\b", qn)
        and any(
            t in qn
            for t in (
                "who",
                "whom",
                "website",
                "company",
                "designed",
                "made",
                "built",
                "develop",
                "owner",
            )
        )
        and not re.search(
            r"\b\d+(\s*[x*×]\s*\d+){1,2}\b",
            qn,
        )  # avoid hijacking long dimension product questions
    ):
        if not re.search(r"\b\d{2,4}\s*lx\b", qn) and "u0" not in qn and "u₀" not in q:
            return True
    return False


def _detect_identity_as_place(question: str) -> Optional[str]:
    """
    Detect identity-as-place phrasing:
    - "i am a factory ..."
    - "i'm in an office ..."
    - "أنا مصنع ..."
    """
    q = str(question or "").strip()
    if not q:
        return None

    if _IDENTITY_PLACE_EN.search(q) or _IDENTITY_PLACE_AR.search(q):
        place = _detect_place_canonical(q)
        if place:
            return place

    # Non-identity but explicit standard request + place mention.
    if re.search(
        r"\b(?:give me|what(?:'s| is)|tell me|show me)\b.*\b(?:standard|target|lux|code|معيار|كود|لوكس)\b",
        q,
        flags=re.IGNORECASE,
    ):
        place = _detect_place_canonical(q)
        if place:
            return place
    return None


def _match_static_lookup_intent(
    question: str,
    session_id: str,
    reply_language: str,
) -> Optional[StaticIntentMatch]:
    q = str(question or "").strip()
    qn = _normalize_text(q)
    if not qn:
        return None

    for spec in _static_intent_specs():
        intent_key = str(spec.get("intent_key") or "")
        patterns_en = spec.get("patterns_en") or []
        patterns_ar = spec.get("patterns_ar") or []
        patterns_norm = spec.get("patterns_norm") or []
        hit = False

        for p in patterns_en:
            try:
                if re.search(str(p), qn, re.IGNORECASE):
                    hit = True
                    break
            except re.error:
                continue

        if not hit:
            for p in patterns_ar:
                try:
                    if re.search(str(p), q, re.IGNORECASE):
                        hit = True
                        break
                except re.error:
                    continue

        if not hit:
            for p in patterns_norm:
                pp = _normalize_text(str(p))
                if pp and (pp in qn):
                    hit = True
                    break

        if not hit:
            if intent_key == "standard_name" and _is_standard_name_lookup_question(q, qn):
                hit = True
        if not hit:
            if intent_key == "company_identity" and _is_company_identity_lookup_question(q, qn):
                hit = True

        if not hit:
            continue

        if intent_key == "standard_name":
            value_markers = (
                "target",
                "required",
                "requirement",
                "value",
                "lux",
                "u0",
                "cri",
                "ra",
                "للمكاتب",
                "للمصانع",
                "القيمة",
                "المطلوب",
            )
            has_name = _is_standard_name_lookup_question(q, qn)
            has_value = any(m in qn or m in q for m in value_markers)
            if (not has_name) or has_value:
                continue

        response_id = str(spec.get("response_id") or "").strip()
        answers = spec.get("answers") if isinstance(spec.get("answers"), dict) else {}
        local_answer = str(answers.get(reply_language) or "").strip()
        if local_answer:
            canonical = str(response_id or spec.get("intent_key") or "").strip()
            return StaticIntentMatch(
                intent_key=intent_key,
                answer=local_answer,
                response_id=response_id,
                canonical_key=canonical,
            )

        response = _find_response_by_id(response_id) if response_id else None
        if response is not None:
            answer = _response_localized_answer(response, reply_language)
            if not answer:
                answer = _pick_fixed_answer(response, question, session_id)
                answer = _translate_answer_if_needed(answer, reply_language)
            canonical_key = _response_canonical_key(response) or str(spec.get("intent_key") or "")
            return StaticIntentMatch(
                intent_key=intent_key,
                answer=answer,
                response_id=str(response.get("id") or response_id),
                canonical_key=canonical_key,
            )

        answer = str(answers.get(reply_language) or answers.get("en") or "").strip()
        if not answer:
            continue
        return StaticIntentMatch(
            intent_key=intent_key,
            answer=answer,
            response_id=response_id,
            canonical_key=str(spec.get("intent_key") or response_id),
        )

    return None


def _alias_candidates(canonical: str, aliases: List[str]) -> List[str]:
    out: List[str] = []
    c = str(canonical or "").strip()
    if c:
        out.append(c)
        out.append(c.replace("_", " "))
    for a in aliases or []:
        aa = str(a or "").strip()
        if aa:
            out.append(aa)
    return out


def _match_alias_entry(target: str) -> Optional[Dict[str, Any]]:
    tn = _normalize_text(target)
    if not tn:
        return None
    doc = load_aliases_doc()
    sections = [
        ("parameters", doc.get("parameters") or {}),
        ("places", doc.get("places") or {}),
    ]

    best: Optional[Dict[str, Any]] = None
    best_score = 0.0

    for section_name, payload in sections:
        if not isinstance(payload, dict):
            continue
        for canonical, raw_aliases in payload.items():
            alias_list = [str(x).strip() for x in (raw_aliases or []) if str(x).strip()]
            candidates = _alias_candidates(str(canonical), alias_list)
            for cand in candidates:
                cn = _normalize_text(cand)
                if not cn:
                    continue
                if tn == cn:
                    return {
                        "section": section_name,
                        "canonical": str(canonical),
                        "aliases": alias_list,
                    }
                score = (_ratio(tn, cn) * 0.60) + (_jaccard(_tokenize(tn), _tokenize(cn)) * 0.40)
                if score > best_score:
                    best_score = score
                    best = {
                        "section": section_name,
                        "canonical": str(canonical),
                        "aliases": alias_list,
                    }
    if best is not None and best_score >= 0.74:
        return best
    return None


def _detect_place_canonical(text: str) -> Optional[str]:
    base = _normalize_text(text)
    if not base:
        return None

    raw_tokens = [t for t in base.split() if t]
    token_forms = set(raw_tokens)
    for tok in raw_tokens:
        if tok.startswith("و") and len(tok) > 2:
            token_forms.add(tok[1:])
        if tok.startswith("ف") and len(tok) > 2:
            token_forms.add(tok[1:])
        if tok.startswith("لل") and len(tok) > 3:
            token_forms.add(tok[2:])
        if tok.startswith("ال") and len(tok) > 3:
            token_forms.add(tok[2:])
        if tok.startswith("ب") and len(tok) > 2:
            token_forms.add(tok[1:])
        if tok.startswith("وال") and len(tok) > 4:
            token_forms.add(tok[3:])
        if tok.startswith("فال") and len(tok) > 4:
            token_forms.add(tok[3:])
        if tok.startswith("بال") and len(tok) > 4:
            token_forms.add(tok[3:])

    heur = _best_canonical_from_heuristics(base, token_forms)
    if heur is not None:
        return heur

    target_forms = {base}
    if base.endswith("ies") and len(base) > 3:
        target_forms.add(base[:-3] + "y")
    if base.endswith("s") and len(base) > 2:
        target_forms.add(base[:-1])

    doc = load_aliases_doc()
    places = doc.get("places") or {}
    if not isinstance(places, dict):
        return None

    # Token-level alias check (helps Arabic clitics: للمكاتب -> مكاتب).
    for canonical, raw_aliases in places.items():
        aliases = [str(x).strip() for x in (raw_aliases or []) if str(x).strip()]
        candidates = _alias_candidates(str(canonical), aliases)
        for cand in candidates:
            cn = _normalize_text(cand)
            if cn and cn in token_forms:
                return str(canonical)

    best_name: Optional[str] = None
    best_score = 0.0

    for canonical, raw_aliases in places.items():
        aliases = [str(x).strip() for x in (raw_aliases or []) if str(x).strip()]
        candidates = _alias_candidates(str(canonical), aliases)
        for cand in candidates:
            cn = _normalize_text(cand)
            if not cn:
                continue
            candidate_forms = {cn}
            if cn.endswith("y") and len(cn) > 1:
                candidate_forms.add(cn[:-1] + "ies")
            if not cn.endswith("s"):
                candidate_forms.add(cn + "s")
            for tn in target_forms:
                if tn in candidate_forms:
                    return str(canonical)
                for cf in candidate_forms:
                    score = (_ratio(tn, cf) * 0.60) + (_jaccard(_tokenize(tn), _tokenize(cf)) * 0.40)
                    if score > best_score:
                        best_score = score
                        best_name = str(canonical)

    if best_name is not None and best_score >= 0.84:
        return best_name
    return None


def _is_standard_target_intent(question: str) -> bool:
    qn = _normalize_text(question)
    if not qn:
        return False
    markers = (
        "standard",
        "target",
        "lux",
        "u0",
        "uniformity",
        "lighting level",
        "illumination",
        "illuminance",
        "requirement",
        "en 12464",
        "en12464",
        "12464",
        "كود",
        "معيار",
        "لوكس",
        "تجانس",
    )
    return any(m in qn for m in markers)


def _place_tag_candidates(place_name: str) -> set[str]:
    p = _normalize_text(place_name)
    out = {p}
    mapping = {
        "classroom": {"classroom", "school", "education"},
        "office": {"office", "workstation", "meeting"},
        "hospital": {"hospital", "health", "clinic", "ward", "health care", "patient", "maternity"},
        "factory": {"factory", "industrial", "manufacturing", "workshop"},
        "warehouse": {"warehouse", "storage", "gangway"},
        "corridor": {"corridor", "circulation", "hallway"},
        "retail": {"retail", "shop", "sales"},
    }
    out.update(mapping.get(p, set()))
    return out


def _standard_response_for_place(place_name: str) -> Optional[dict]:
    place_tags = _place_tag_candidates(place_name)
    doc = load_fixed_responses_doc()
    responses = list(doc.get("responses") or [])

    for r in responses:
        tags = [_normalize_text(str(t)) for t in (r.get("tags") or [])]
        if "standards" in tags and any(t in place_tags for t in tags):
            return r

    for r in responses:
        rid = _normalize_text(str(r.get("id") or ""))
        q = _normalize_text(str(r.get("question") or ""))
        if any(t in rid or t in q for t in place_tags):
            return r
    return None


def _find_place_standard_response(question: str) -> Optional[dict]:
    # Handle both short place-only follow-ups and longer place+standard questions.
    qt = _tokenize(question)
    if not qt:
        return None
    is_short_place = len(qt) <= 3
    identity_place = _detect_identity_as_place(question)
    if not is_short_place and not _is_standard_target_intent(question):
        if not identity_place:
            return None
    place_name = identity_place or _detect_place_canonical(question)
    if not place_name:
        return None
    return _standard_response_for_place(place_name)


def alias_lookup_answer(
    question: str,
    reply_language: str = "en",
) -> Optional[Dict[str, Any]]:
    if not _is_alias_query(question):
        return None
    target = _extract_alias_target(question)
    if not target:
        return None
    matched = _match_alias_entry(target)
    if not matched:
        return None

    canonical = str(matched.get("canonical") or "").strip()
    alias_list = [str(x).strip() for x in (matched.get("aliases") or []) if str(x).strip()]
    if not canonical:
        return None

    alias_line = ", ".join(alias_list) if alias_list else canonical
    section = str(matched.get("section") or "parameters")
    if reply_language == "ar":
        answer = (
            f'وفق ملف المرادفات، المصطلح الأساسي "{canonical}" ضمن قسم ({section}) '
            f"وله المرادفات التالية: {alias_line}."
        )
    else:
        answer = (
            f'From aliases file, canonical "{canonical}" ({section}) has aliases: {alias_line}.'
        )
    return {
        "source": "alias_lookup",
        "answer": answer,
        "alias_canonical": canonical,
        "alias_section": section,
        "alias_values": alias_list,
        "requires_confirmation": False,
        "show_yes_no": False,
        "confidence": 1.0,
    }


def _extract_lwh_dims(question: str) -> Optional[Tuple[float, float, float]]:
    q = str(question or "")
    patterns = [
        r"\(?\s*(\d+(?:\.\d+)?)\s*(?:m|meter|meters|م)?\s*(?:x|\*|×|by)\s*"
        r"(\d+(?:\.\d+)?)\s*(?:m|meter|meters|م)?\s*(?:x|\*|×|by)\s*"
        r"(\d+(?:\.\d+)?)\s*(?:m|meter|meters|م)?\s*\)?",
        r"(?:l(?:ength)?|طول)\s*[:=]?\s*(\d+(?:\.\d+)?)\D+"
        r"(?:w(?:idth)?|عرض)\s*[:=]?\s*(\d+(?:\.\d+)?)\D+"
        r"(?:h(?:eight)?|ceiling|ارتفاع)\s*[:=]?\s*(\d+(?:\.\d+)?)",
    ]
    for pat in patterns:
        m = re.search(pat, q, flags=re.IGNORECASE)
        if not m:
            continue
        try:
            return (float(m.group(1)), float(m.group(2)), float(m.group(3)))
        except Exception:
            continue
    return None


def _extract_height_hint(question: str) -> Optional[float]:
    m = re.search(
        r"(?:height|ceiling(?:\s+height)?|ارتفاع)\s*[:=]?\s*(\d+(?:\.\d+)?)",
        str(question or ""),
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _extract_rectangle_sides(
    question: str,
    dims: Optional[Tuple[float, float, float]],
) -> Optional[List[float]]:
    q = str(question or "")
    m4 = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:x|\*|×)\s*(\d+(?:\.\d+)?)\s*(?:x|\*|×)\s*"
        r"(\d+(?:\.\d+)?)\s*(?:x|\*|×)\s*(\d+(?:\.\d+)?)",
        q,
        flags=re.IGNORECASE,
    )
    if m4:
        try:
            vals = [float(m4.group(i)) for i in (1, 2, 3, 4)]
            if all(v > 0 for v in vals):
                return vals
        except Exception:
            pass
    if dims is None:
        return None
    l, w, _h = dims
    if l > 0 and w > 0:
        return [float(l), float(w), float(l), float(w)]
    return None


def _mtime_key(path: str) -> float:
    try:
        return float(os.path.getmtime(path)) if os.path.isfile(path) else 0.0
    except OSError:
        return 0.0


def _aliases_mkey() -> float:
    t = 0.0
    for p in ALIASES_PATHS:
        t = max(t, _mtime_key(p))
    return t


@lru_cache(maxsize=4)
def _load_standards_cleaned_stamped(mtime_key: float) -> List[Dict[str, Any]]:
    if not os.path.isfile(STANDARDS_CLEANED_PATH):
        return []
    try:
        with open(STANDARDS_CLEANED_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return list(data) if isinstance(data, list) else []
    except Exception as e:
        log_exception("chat_service._load_standards_cleaned", e)
        return []


def _load_standards_cleaned() -> List[Dict[str, Any]]:
    return _load_standards_cleaned_stamped(_mtime_key(STANDARDS_CLEANED_PATH))


@lru_cache(maxsize=4)
def _standards_row_by_ref_map_stamped(mtime_key: float) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in _load_standards_cleaned_stamped(mtime_key):
        if not isinstance(row, dict):
            continue
        ref = str(row.get("ref_no") or "").strip()
        if ref:
            out[ref] = row
    return out


def _standards_row_by_ref_map() -> Dict[str, Dict[str, Any]]:
    return _standards_row_by_ref_map_stamped(_mtime_key(STANDARDS_CLEANED_PATH))


def _standard_row_by_ref(ref_no: str) -> Optional[Dict[str, Any]]:
    return _standards_row_by_ref_map().get(str(ref_no or "").strip())


@lru_cache(maxsize=4)
def _load_standards_keywords_stamped(mtime_key: float) -> Dict[str, Any]:
    if not os.path.isfile(STANDARDS_KEYWORDS_PATH):
        return {}
    try:
        with open(STANDARDS_KEYWORDS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return dict(data) if isinstance(data, dict) else {}
    except Exception as e:
        log_exception("chat_service._load_standards_keywords", e)
        return {}


def _load_standards_keywords() -> Dict[str, Any]:
    return _load_standards_keywords_stamped(_mtime_key(STANDARDS_KEYWORDS_PATH))


def _extract_standard_ref_no(question: str) -> Optional[str]:
    q = str(question or "")
    m = re.search(r"\b(\d+\.\d+\.\d+)\b", q)
    if not m:
        return None
    ref = str(m.group(1) or "").strip()
    if _standard_row_by_ref(ref):
        return ref
    return None


def _standard_row_for_place(place_name: Optional[str]) -> Optional[Dict[str, Any]]:
    if not place_name:
        return None
    hit = _standard_response_for_place(str(place_name))
    refs = list((hit or {}).get("source_refs") or [])
    for ref in refs:
        row = _standard_row_by_ref(str(ref))
        if row:
            return row
    return None


def _best_standard_row_by_keywords(question: str) -> Optional[Dict[str, Any]]:
    qn = _normalize_text(question)
    if not qn:
        return None
    kw_doc = _load_standards_keywords()
    mapping = kw_doc.get("keyword_to_refs") or {}
    if not isinstance(mapping, dict):
        return None
    best_row: Optional[Dict[str, Any]] = None
    best_score = 0.0
    for keyword, refs in mapping.items():
        k = _normalize_text(str(keyword or ""))
        if not k:
            continue
        if not re.search(r"\b" + re.escape(k) + r"\b", qn):
            continue
        score = (len(k.split()) * 4.0) + (len(k) * 0.1)
        ref_list = refs if isinstance(refs, list) else [refs]
        for ref in ref_list:
            row = _standard_row_by_ref(str(ref))
            if row and score > best_score:
                best_score = score
                best_row = row
    return best_row


def _resolve_fixture_planning_inputs(question: str) -> Dict[str, Any]:
    dims = _extract_lwh_dims(question)
    sides = _extract_rectangle_sides(question, dims)
    place_name = _detect_place_canonical(question)
    height = float(dims[2]) if dims is not None else _extract_height_hint(question)

    standard_ref_no = _extract_standard_ref_no(question)
    standard_row = _standard_row_by_ref(standard_ref_no or "")
    if standard_row is None:
        # Prefer a row mapped to the resolved canonical place (fixed_responses) before
        # keyword hits, so e.g. "hospital" + the word "ward" does not jump to 6.37.2
        # hospital-corridor rows in standards_keywords.
        standard_row = _standard_row_for_place(place_name)
    if standard_row is None:
        standard_row = _best_standard_row_by_keywords(question)
    if standard_row is not None:
        standard_ref_no = str(standard_row.get("ref_no") or standard_ref_no or "").strip() or None

    return {
        "dims": dims,
        "sides": sides,
        "height": height,
        "place_name": place_name,
        "standard_ref_no": standard_ref_no,
        "standard_row": standard_row,
        "category": str((standard_row or {}).get("category") or "").strip(),
        "task_or_activity": str((standard_row or {}).get("task_or_activity") or "").strip(),
    }


def _missing_required_fields_for_planning(params: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    sides = params.get("sides")
    height = params.get("height")
    place_name = params.get("place_name")
    standard_row = params.get("standard_row")
    if not isinstance(sides, list) or len(sides) != 4:
        missing.append("room dimensions (Length × Width × Height in meters)")
    if height is None or float(height) <= 0:
        missing.append("ceiling height (H in meters)")
    if standard_row is None and not place_name:
        missing.append("room type or activity (e.g. factory, office, warehouse)")
    return missing


_PLACE_STANDARD_TARGETS: Dict[str, Tuple[float, float, float]] = {
    "Factory": (200.0, 0.4, 20.0),
    "Hospital": (200.0, 0.4, 80.0),
    "Warehouse": (100.0, 0.4, 20.0),
    "Office": (500.0, 0.6, 80.0),
    "Classroom": (300.0, 0.6, 80.0),
    "Retail": (500.0, 0.4, 80.0),
    "Corridor": (100.0, 0.4, 40.0),
}


def _standard_targets_for_place(place_name: str) -> Tuple[float, float, float]:
    """Return (target_lux, Uo_min, CRI_min) for canonical place name."""
    if not place_name:
        return 200.0, 0.4, 20.0
    row = _PLACE_STANDARD_TARGETS.get(str(place_name).strip())
    if row:
        return row
    return 200.0, 0.4, 20.0


_DEFAULT_MF = 0.80
_DEFAULT_UF = 0.60
_FIXTURE_INTENT_MARKERS = (
    "how many fixture",
    "how many fitting",
    "number of fixture",
    "fixture count",
    "how much fixture",
    "need fixture",
    "كم تركيبة",
    "كم مصباح",
    "عدد التركيبات",
    "عدد المصابيح",
    # wildcard-style markers
    "fixtures*factory",
    "fixtures*office",
    "fixtures*warehouse",
    "fixtures*room",
    "need*light*factory",
    "need*light*room",
)
_AR_FIXTURE_TERMS = (
    "كشاف",
    "كشافات",
    "وحده اناره",
    "وحدة انارة",
    "وحدات اناره",
    "وحدات انارة",
    "تركيبه",
    "تركيبة",
    "تركيبات",
    "مصباح",
    "مصابيح",
    "لمبه",
    "لمبة",
    "لمبات",
    "اناره",
    "اضاءه",
    "إضاءة",
)
_AR_NEED_TERMS = ("هحتاج", "محتاج", "احتاج", "عايز", "عاوزه", "لازم")


_PLACE_TO_LUMINAIRES: Dict[str, Tuple[str, ...]] = {
    "Factory": ("SC highbay", "SC triproof", "SC backlight"),
    "Warehouse": ("SC highbay", "SC triproof"),
    "Office": ("SC backlight", "SC downlight", "SC triproof"),
    "Classroom": ("SC backlight", "SC downlight", "SC triproof"),
    "Retail": ("SC backlight", "SC downlight", "SC triproof", "SC flood light exterior"),
    "Corridor": ("SC triproof", "SC backlight", "SC downlight"),
}


def _uf_for_luminaire(name: str) -> float:
    n = _normalize_text(name)
    if "highbay" in n:
        return 0.65
    if "flood" in n or "street" in n:
        return 0.62
    if "triproof" in n:
        return 0.58
    if "backlight" in n:
        return 0.60
    if "downlight" in n:
        return 0.57
    return _DEFAULT_UF


def _efficacy_guess_lm_per_w(name: str) -> float:
    n = _normalize_text(name)
    if "highbay" in n or "flood" in n or "street" in n:
        return 140.0
    if "triproof" in n or "backlight" in n or "downlight" in n:
        return 110.0
    return 120.0


def _ies_abs_path(relative_ies_path: str) -> str:
    rel = str(relative_ies_path or "").strip().replace("/", os.sep)
    return os.path.join(project_root(), "ies-render", rel)


@lru_cache(maxsize=512)
def _fixture_lumens_from_ies(
    relative_ies_path: str,
    power_w: int,
    luminaire_name: str,
) -> float:
    p = _ies_abs_path(relative_ies_path)
    if os.path.isfile(p):
        try:
            # Local import to avoid heavy module load on app startup.
            from luxscale.ies_analyzer import estimate_lumens, parse_ies_file

            ies = parse_ies_file(p)
            est = float(estimate_lumens(ies) or 0.0)
            if est > 0:
                return est
            header_lm = float(ies.num_lamps) * float(ies.lumens_per_lamp)
            if header_lm > 0:
                return header_lm
        except Exception:
            pass
    return float(max(1.0, power_w * _efficacy_guess_lm_per_w(luminaire_name)))


def _height_compatible(name: str, height: float) -> bool:
    n = _normalize_text(name)
    if "highbay" in n and height < 5.0:
        return False
    if ("backlight" in n or "downlight" in n or "panel" in n) and height > 6.0:
        return False
    return True


def _candidate_fixture_entries_for_place(place_name: str, height: float) -> List[dict]:
    entries = _fixture_entries()
    if not entries:
        return []
    preferred = set(_PLACE_TO_LUMINAIRES.get(str(place_name), ()))
    out: List[dict] = []
    for e in entries:
        name = str(e.get("api_luminaire_name") or "").strip()
        if not name:
            continue
        if preferred and name not in preferred:
            continue
        if not _height_compatible(name, height):
            continue
        out.append(e)
    if out:
        return out
    # Fallback: allow any height-compatible entry.
    return [e for e in entries if _height_compatible(str(e.get("api_luminaire_name") or ""), height)]


_PLACE_TO_CALCULATE_PRESET = {
    "Factory": "Factory production line",
    "Warehouse": "Factory warehouse",
    "Office": "Office",
    "Classroom": "Room",
    "Retail": "Room",
    "Corridor": "Room",
}


def _extract_first_json_object(text: str) -> Optional[Dict[str, Any]]:
    raw = str(text or "").strip()
    if not raw:
        return None
    cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).replace("```", "").strip()
    candidates = [cleaned]
    m = re.search(r"\{[\s\S]*\}", cleaned)
    if m:
        candidates.append(m.group(0))
    for candidate in candidates:
        try:
            val = json.loads(candidate)
            if isinstance(val, dict):
                return val
        except Exception:
            continue
    return None


def _normalize_gemini_place(raw_place: Any) -> Optional[str]:
    v = str(raw_place or "").strip()
    if not v:
        return None
    direct = _detect_place_canonical(v)
    if direct:
        return direct
    mapped = {
        "factory production line": "Factory",
        "factory warehouse": "Warehouse",
        "office": "Office",
        "room": None,
    }
    return mapped.get(_normalize_text(v))


def _structured_gemini_fill_for_planning(
    question: str,
    missing_fields: List[str],
    reply_language: str = "en",
) -> Dict[str, Any]:
    missing_csv = ", ".join(missing_fields)
    prompt = (
        "Extract missing lighting-calculation fields from user question.\n"
        "Return JSON only with this schema:\n"
        "{"
        '"sides":[number,number,number,number] | null, '
        '"height": number | null, '
        '"place": string | null, '
        '"category": string | null, '
        '"task_or_activity": string | null, '
        '"standard_ref_no": string | null, '
        '"confidence": number'
        "}\n"
        "Rules: no prose, no markdown, do not invent standards.\n"
        f"Missing fields now: {missing_csv}\n"
        f"Question: {question}"
    )
    g = ask_gemini_text(prompt, max_output_tokens=180, temperature=0.0)
    return {
        "source": str(g.get("source") or "gemini"),
        "payload": _extract_first_json_object(str(g.get("text") or "")),
        "raw_text": str(g.get("text") or ""),
    }


def _merge_structured_fill(params: Dict[str, Any], fill_payload: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(params)
    payload = dict(fill_payload or {})

    if merged.get("sides") is None:
        raw_sides = payload.get("sides")
        if isinstance(raw_sides, list) and len(raw_sides) == 4:
            try:
                sides = [float(x) for x in raw_sides]
                if all(0.01 <= x <= 5000 for x in sides):
                    merged["sides"] = sides
            except Exception:
                pass

    if merged.get("height") in (None, 0):
        try:
            h = float(payload.get("height"))
            if 0.5 <= h <= 100:
                merged["height"] = h
        except Exception:
            pass

    if not merged.get("place_name"):
        place = _normalize_gemini_place(payload.get("place"))
        if place:
            merged["place_name"] = place

    if merged.get("standard_row") is None:
        raw_ref = str(payload.get("standard_ref_no") or "").strip()
        if raw_ref:
            row = _standard_row_by_ref(raw_ref)
            if row:
                merged["standard_row"] = row
                merged["standard_ref_no"] = str(row.get("ref_no") or raw_ref).strip()

    if merged.get("standard_row") is None and merged.get("place_name"):
        row = _standard_row_for_place(str(merged.get("place_name")))
        if row:
            merged["standard_row"] = row
            merged["standard_ref_no"] = str(row.get("ref_no") or "").strip() or None

    if merged.get("standard_row") is None:
        row = _best_standard_row_by_keywords(
            " ".join(
                [
                    str(payload.get("category") or ""),
                    str(payload.get("task_or_activity") or ""),
                ]
            )
        )
        if row:
            merged["standard_row"] = row
            merged["standard_ref_no"] = str(row.get("ref_no") or "").strip() or None

    merged["category"] = str((merged.get("standard_row") or {}).get("category") or merged.get("category") or "").strip()
    merged["task_or_activity"] = str(
        (merged.get("standard_row") or {}).get("task_or_activity") or merged.get("task_or_activity") or ""
    ).strip()
    return merged


def _resolve_calculate_place(place_name: Optional[str]) -> Optional[str]:
    if not place_name:
        return None
    return _PLACE_TO_CALCULATE_PRESET.get(str(place_name), None)


def _catalog_entry_for_calc_row(luminaire: str, power_w: int, place_name: str, height: float) -> Optional[dict]:
    entries = _candidate_fixture_entries_for_place(place_name, height)
    if not entries:
        entries = _fixture_entries()
    if not entries:
        return None
    target_name = _normalize_text(luminaire)
    best: Optional[Tuple[float, dict]] = None
    for e in entries:
        name = str(e.get("api_luminaire_name") or "").strip()
        if not name:
            continue
        name_score = _ratio(target_name, _normalize_text(name))
        pw = int(e.get("power_w") or 0)
        power_gap = abs(pw - int(power_w or 0))
        score = (name_score * 100.0) - min(40.0, power_gap * 1.2)
        if (best is None) or (score > best[0]):
            best = (score, e)
    return best[1] if best else None


_GAP_TOL = 1e-6


def _pass_flags_from_calc_row(
    row: Dict[str, Any],
    avg_lux: float,
    u0: float,
    target_lux: float,
    uo_min: float,
) -> Tuple[bool, bool, str]:
    """Derive lux/U0 pass flags from calculate_lighting rows.

    Rows use nonnegative ``Lux gap`` / ``U0 gap`` (shortfall vs target); pass when gap ≈ 0.
    """
    lg = row.get("Lux gap")
    ug = row.get("U0 gap")
    if lg is not None and ug is not None:
        try:
            lux_pass = float(lg) <= _GAP_TOL
            u0_pass = float(ug) <= _GAP_TOL
            return lux_pass, u0_pass, "gaps"
        except (TypeError, ValueError):
            pass
    try:
        lux_pass = float(avg_lux) + 1e-9 >= float(target_lux)
        u0_pass = float(u0) + 1e-9 >= float(uo_min)
        return lux_pass, u0_pass, "threshold"
    except (TypeError, ValueError):
        return True, True, "unknown"


def _calc_row_options(
    rows: List[Dict[str, Any]],
    place_name: str,
    height: float,
    area: float,
    target_lux: float,
    uo_min: float,
) -> List[Dict[str, Any]]:
    mf = float(get_maintenance_factor() or _DEFAULT_MF)
    out: List[Dict[str, Any]] = []
    for row in rows:
        luminaire = str(row.get("Luminaire") or "").strip()
        if not luminaire:
            continue
        fixtures = int(row.get("Fixtures") or 0)
        if fixtures <= 0:
            continue
        power_w = int(float(row.get("Power (W)") or 0))
        avg_lux = float(
            row.get("E_avg_grid_lx")
            or row.get("e_avg_grid_lx")
            or row.get("Average Lux")
            or 0.0
        )
        u0 = float(row.get("U0_calculated") or row.get("u0_calculated") or 0.0)
        lux_pass, u0_pass, pass_src = _pass_flags_from_calc_row(
            row, avg_lux, u0, target_lux, uo_min
        )
        selection = str(row.get("Selection") or "").strip()
        total_kw = round((fixtures * power_w) / 1000.0, 2)
        watts_per_m2 = round((fixtures * power_w) / max(area, 1.0), 2)
        lumens = int(float(row.get("IES lumens (lm)") or 0.0))
        nx = int(row.get("layout_nx") or 0)
        ny = int(row.get("layout_ny") or 0)
        cat = _catalog_entry_for_calc_row(luminaire, power_w, place_name, height) or {}
        online = cat.get("online") or {}
        imgs = cat.get("image_urls") or []
        out.append(
            {
                "label": luminaire,
                "fixtures": fixtures,
                "power_w": power_w,
                "achieved_lux": round(avg_lux, 1),
                "u0": round(u0, 3),
                "total_kw": total_kw,
                "watts_per_m2": watts_per_m2,
                "lumens": lumens,
                "uf": round(_uf_for_luminaire(luminaire), 2),
                "mf": round(mf, 2),
                "layout_nx": nx,
                "layout_ny": ny,
                "product_title": str(online.get("product_title") or luminaire),
                "product_url": str(online.get("product_url") or "https://shortcircuit.company"),
                "image_url": str(imgs[0]) if isinstance(imgs, list) and imgs else "",
                "selection": selection,
                "lux_pass": lux_pass,
                "u0_pass": u0_pass,
                "pass_src": pass_src,
                "uniformity_evaluated": True,
            }
        )

    out.sort(
        key=lambda r: (
            int(r["fixtures"]),
            abs(float(r["achieved_lux"])),
            str(r["label"]).lower(),
            int(r["power_w"]),
        )
    )
    return out[:3]


def _run_core_planning_calc(params: Dict[str, Any]) -> Dict[str, Any]:
    sides = params.get("sides") or []
    height = float(params.get("height") or 0.0)
    standard_row = params.get("standard_row")
    place_name = str(params.get("place_name") or "")
    calc_place = _resolve_calculate_place(place_name) if standard_row is None else None

    if not sides or len(sides) != 4 or height <= 0:
        return {"ok": False, "error": "missing_dimensions"}
    if standard_row is None and not calc_place:
        return {"ok": False, "error": "missing_target_context"}

    try:
        rows, length, width, _meta = calculate_lighting(
            calc_place,
            [float(x) for x in sides],
            float(height),
            standard_row=standard_row,
            fast=True,
        )
    except Exception as e:
        log_exception("chat_service._run_core_planning_calc", e)
        return {"ok": False, "error": "calculate_lighting_failed"}

    if not rows:
        return {"ok": False, "error": "no_results"}

    area = float(length * width)
    if standard_row is not None:
        tgt_lux = float(standard_row.get("Em_r_lx") or 200.0)
        tgt_uo = float(standard_row.get("Uo") or 0.4)
    else:
        tgt_lux, tgt_uo, _ = _standard_targets_for_place(place_name)

    options = _calc_row_options(
        rows,
        place_name=place_name,
        height=height,
        area=area,
        target_lux=tgt_lux,
        uo_min=tgt_uo,
    )
    if not options:
        return {"ok": False, "error": "no_options"}

    return {
        "ok": True,
        "rows": rows,
        "length": float(length),
        "width": float(width),
        "area": area,
        "options": options,
    }


def _is_fixture_count_intent(question: str) -> bool:
    qn = _normalize_text(question)
    raw = str(question or "")
    if not qn:
        return False
    for marker in _FIXTURE_INTENT_MARKERS:
        if "*" not in marker and marker in qn:
            return True
    for marker in _FIXTURE_INTENT_MARKERS:
        if "*" in marker and re.search(re.escape(marker).replace("\\*", ".*"), qn):
            return True
    # Arabic study phrasing: when dimensions are present and user asks for fixtures needed.
    has_dims = _extract_lwh_dims(question) is not None
    has_ar_fixture_term = any(t in qn or t in raw for t in _AR_FIXTURE_TERMS)
    has_ar_need = any(t in qn or t in raw for t in _AR_NEED_TERMS)
    if has_dims and (has_ar_fixture_term or _is_recommendation_intent(question)):
        return True
    if has_dims and has_ar_need and _detect_place_canonical(question):
        return True
    return False


_CATALOG_QUESTION_FRAGMENTS = (
    "what fixtures",
    "which fixtures",
    "what fixture types",
    "fixture families",
    "luminaire families",
    "fixture catalog",
    "catalog list",
    "available fixtures",
    "available luminaire",
    "what products can i use",
    "what luminaires",
    "which luminaires",
    "types of fixtures",
    "types of luminaire",
)


def _is_fixture_catalog_intent(question: str) -> bool:
    """True when the user asks which fixture families exist — not a fixture-count study."""
    qn = _normalize_text(question)
    raw = str(question or "")
    if not qn:
        return False
    dims = _extract_lwh_dims(question)
    if dims is not None and _is_fixture_count_intent(question):
        return False
    for frag in _CATALOG_QUESTION_FRAGMENTS:
        if frag in qn:
            return True
    if "catalog" in qn and ("fixture" in qn or "luminaire" in qn or "luxscale" in qn):
        return True
    if ("indoor" in qn or "indoors" in qn) and ("fixture" in qn or "luminaire" in qn):
        return True
    if "do you use" in qn and ("fixture" in qn or "luminaire" in qn):
        return True
    ar_list = ("تركيبات", "كشاف", "مصباح", "لمبات")
    ar_catalog = ("متاح", "كتالوج", "أنواع", "انواع", "إيه", "ايه", "إي")
    if any(t in raw for t in ar_list) and any(t in raw for t in ar_catalog):
        if dims is None or not _is_fixture_count_intent(question):
            return True
    return False


_CATALOG_SCOPE_INDOOR = (
    "indoor",
    "indoors",
    "inside",
    "interior",
    "office",
    "classroom",
    "corridor",
    "retail hall",
    "داخلي",
    "داخلية",
    "داخل المنزل",
    "مكتب",
    "غرفة",
)
_CATALOG_SCOPE_OUTDOOR = (
    "outdoor",
    "outdoors",
    "outside",
    "exterior",
    "external",
    "facade",
    "façade",
    "yard",
    "roadway",
    "carpark",
    "car park",
    "parking lot",
    "street lighting",
    "highbay",
    "high bay",
    "high-bay",
    "open air",
    "forecourt",
    "خارجي",
    "خارجية",
    "فضاء خارجي",
    "موقف",
    "شارع",
)


def _fixture_catalog_scope(question: str) -> str:
    """
    Classify catalog questions as indoor-only, outdoor/tall-only, or full combined list.

    Mirrors ``luxscale.lighting_calc.geometry.determine_luminaire`` split (threshold from settings).
    """
    qn = _normalize_text(question)
    raw = str(question or "")
    if not qn:
        return "all"
    in_hits = sum(1 for m in _CATALOG_SCOPE_INDOOR if m in qn or m in raw)
    out_hits = sum(1 for m in _CATALOG_SCOPE_OUTDOOR if m in qn or m in raw)
    if out_hits > 0 and in_hits == 0:
        return "outdoor"
    if in_hits > 0 and out_hits == 0:
        return "indoor"
    if out_hits > in_hits and out_hits > 0:
        return "outdoor"
    if in_hits > out_hits and in_hits > 0:
        return "indoor"
    return "all"


def _fixed_response_by_canonical(canonical_key: str) -> Optional[Dict[str, Any]]:
    doc = load_fixed_responses_doc()
    for r in doc.get("responses") or []:
        ck = str(r.get("canonical_key") or r.get("id") or "")
        if ck == canonical_key:
            return r
    return None


def _fixture_catalog_question_answer(
    question: str,
    reply_language: str,
    _session_id: str,
) -> Optional[Dict[str, Any]]:
    if not _is_fixture_catalog_intent(question):
        return None
    scope = _fixture_catalog_scope(question)
    canonical_key = (
        "fixture_catalog_indoor"
        if scope == "indoor"
        else "fixture_catalog_outdoor"
        if scope == "outdoor"
        else "fixture_catalog_overview"
    )
    resp = _fixed_response_by_canonical(canonical_key)
    if resp is None:
        return None
    answer = _response_localized_answer(resp, reply_language)
    if not answer:
        answer = str(resp.get("answer") or "").strip()
    if not _response_localized_answer(resp, reply_language):
        answer = _translate_answer_if_needed(answer, reply_language)
    return {
        "source": "fixture_catalog_local",
        "answer": answer,
        "requires_confirmation": False,
        "show_yes_no": False,
        "confidence": 0.97,
        "response_id": str(resp.get("id") or ""),
        "canonical_response_id": canonical_key,
        "fixture_catalog_scope": scope,
    }


def _calc_fixture_options(
    area: float,
    height: float,
    target_lux: float,
    place_name: str,
) -> List[Dict[str, Any]]:
    """
    Run lumen-method using real mapped fixture entries.
    Returns top 3 options sorted by fixture count ascending.
    """
    results: List[Dict[str, Any]] = []
    if area <= 0 or target_lux <= 0:
        return results

    for e in _candidate_fixture_entries_for_place(place_name, height):
        label = str(e.get("api_luminaire_name") or "").strip()
        power_w = int(e.get("power_w") or 0)
        if not label or power_w <= 0:
            continue
        ies_path = str(e.get("relative_ies_path") or "").strip()
        online = e.get("online") or {}
        imgs = e.get("image_urls") or []
        image_url = str(imgs[0]) if isinstance(imgs, list) and imgs else ""
        product_url = str(online.get("product_url") or "https://shortcircuit.company")
        product_title = str(online.get("product_title") or label)
        uf = _uf_for_luminaire(label)
        mf = _DEFAULT_MF
        lumens = _fixture_lumens_from_ies(ies_path, power_w, label)
        flux_per_fixture = lumens * uf * mf
        if flux_per_fixture <= 0:
            continue

        n_exact = (target_lux * area) / flux_per_fixture
        n = int(max(1, math.ceil(n_exact)))
        achieved_lux = round((n * lumens * uf * mf) / area, 1)
        total_kw = round((n * power_w) / 1000.0, 2)
        watts_per_m2 = round((n * power_w) / area, 1) if area > 0 else 0.0

        lux_ok = float(achieved_lux) + 1e-9 >= float(target_lux)
        results.append(
            {
                "label": label,
                "product_title": product_title,
                "product_url": product_url,
                "image_url": image_url,
                "fixtures": n,
                "lumens": int(lumens),
                "power_w": int(power_w),
                "achieved_lux": achieved_lux,
                "total_kw": total_kw,
                "watts_per_m2": watts_per_m2,
                "uf": round(float(uf), 2),
                "mf": round(float(mf), 2),
                "u0": None,
                "selection": "lumen_estimate_only",
                "lux_pass": lux_ok,
                "u0_pass": False,
                "uniformity_evaluated": False,
            }
        )

    results.sort(
        key=lambda r: (
            int(r["fixtures"]),
            float(r["total_kw"]),
            str(r["label"]).lower(),
            int(r["power_w"]),
        )
    )
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for row in results:
        key = (row["label"], row["power_w"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
        if len(deduped) >= 3:
            break
    return deduped


def _planning_answer_industrial_context(place_name: str, task_or_activity: str, category: str) -> bool:
    blob = _normalize_text(f"{place_name} {task_or_activity} {category}")
    markers = (
        "factory",
        "industrial",
        "warehouse",
        "plant",
        "manufacturing",
        "مصنع",
        "صناعي",
        "انتاج",
        "إنتاج",
    )
    return any(m in blob for m in markers)


def _format_local_calc_answer(
    l: float,
    w: float,
    h: float,
    area: float,
    place_name: str,
    target_lux: float,
    uo_min: float,
    options: List[Dict[str, Any]],
    lang: str,
    standard_ref_no: str = "",
    task_or_activity: str = "",
    category: str = "",
    used_gemini_fill: bool = False,
) -> str:
    if not options:
        if lang == "ar":
            return (
                f"الغرفة: {l:g}×{w:g}×{h:g} م | المساحة: {area:g} م² | النوع: {place_name}\n"
                "لا توجد تركيبة مناسبة لهذا الارتفاع في الكتالوج. "
                "يرجى فتح LuxSCale واختيار تركيبة مخصصة."
            )
        return (
            f"Room: {l:g}×{w:g}×{h:g} m | Area: {area:g} m² | Type: {place_name}\n"
            "No fixture in the catalog matched this ceiling height. "
            "Please open LuxSCale and select a fixture manually."
        )

    sep = "─" * 36
    lines: List[str] = []
    std_ref = standard_ref_no or "EN 12464-1 (mapped)"
    task_line = task_or_activity or category or "-"
    fill_note_ar = "تم استكمال بعض الحقول الناقصة تلقائيًا والتحقق منها محليًا." if used_gemini_fill else ""
    fill_note_en = "Some missing fields were auto-completed, then checked locally." if used_gemini_fill else ""

    any_engine_non_compliant = False
    uses_lumen_fallback_only = False

    for opt in options:
        uni_ok = bool(opt.get("uniformity_evaluated", True))
        sel = str(opt.get("selection") or "")
        lux_p = bool(opt.get("lux_pass", True))
        u0_p = bool(opt.get("u0_pass", True))
        if not uni_ok:
            uses_lumen_fallback_only = True
            continue
        if sel and "non_compliant" in sel:
            any_engine_non_compliant = True
        if not lux_p or not u0_p:
            any_engine_non_compliant = True

    engine_opts = [o for o in options if o.get("uniformity_evaluated")]
    all_engine_u0_fail = bool(engine_opts) and all(
        not bool(o.get("u0_pass")) for o in engine_opts
    )

    if lang == "ar":
        lines.append("📐 مدخلات التحليل")
        lines.append(f"   النوع: {place_name}  |  الأبعاد: {l:g} × {w:g} × {h:g} م  |  المساحة: {area:g} م²")
        lines.append(f"   المهمة/النشاط: {task_line}")
        lines.append(f"   الهدف: {target_lux:.0f} لوكس (lx)  |  Uo ≥ {uo_min:g}  |  المرجع: {std_ref}")
        lines.append("   المحرك: LuxScale calculate_lighting (FAST)")
        if fill_note_ar:
            lines.append(f"   ملاحظة: {fill_note_ar}")
        lines.append(sep)
        lines.append("💡 خيارات التركيبات (من محرك LuxScale)")
        for i, opt in enumerate(options, 1):
            img = opt.get("image_url") or ""
            url = opt.get("product_url") or ""
            title = opt.get("product_title") or opt["label"]
            uni_ok = bool(opt.get("uniformity_evaluated", True))
            lux_p = bool(opt.get("lux_pass", True))
            u0_p = bool(opt.get("u0_pass", True))

            lines.append("")
            lines.append(f"  {i}. {title}  ({opt['power_w']} W)")
            if img:
                lines.append(f"  [img]{img}[/img]")
            lines.append(f"     عدد التركيبات : {opt['fixtures']}")
            u0_disp = opt.get("u0")
            if uni_ok and u0_disp is not None:
                lines.append(
                    f"     الإضاءة المحققة: {opt['achieved_lux']} لوكس (lx)  |  U0 (محسوب): {float(u0_disp):g}"
                )
            else:
                lines.append(f"     الإضاءة المحققة (تقدير شعاعي): {opt['achieved_lux']} لوكس (lx)  |  U0: غير محسوب في هذا التقدير")
            lines.append(f"     إجمالي القدرة  : {opt['total_kw']} كيلوواط  ({opt['watts_per_m2']} W/m²)")
            grid_x = opt.get("layout_nx") or 0
            grid_y = opt.get("layout_ny") or 0
            grid_txt = f"{grid_x}x{grid_y}" if grid_x or grid_y else "-"
            lines.append(
                f"     الفيض الضوئي   : {opt['lumens']:,} لومن/تركيبة  |  UF={opt['uf']}  MF={opt['mf']}  |  شبكة={grid_txt}"
            )
            if uni_ok:
                lx_ar = "يلبي الهدف" if lux_p else "أقل من الهدف"
                u0_ar = "يلبي الحد الأدنى" if u0_p else "أقل من المطلوب"
                lines.append(f"     المطابقة للمعيار  : لوكس → {lx_ar}  |  U₀ → {u0_ar}")
            else:
                lx_ar = "يلبي الهدف تقريبًا" if lux_p else "قد لا يكفي للهدف"
                lines.append(f"     المطابقة (لوكس فقط): {lx_ar} (لا يوجد تقييم U₀ في هذا المسار)")
            if url:
                lines.append(f"     [url]{url}[/url]")
        lines.append("")
        lines.append(sep)
        lines.append("ℹ️  هذه النتائج مبنية على نفس محرك LuxScale الأساسي (FAST mode).")
        if uses_lumen_fallback_only:
            lines.append(
                "⚠️ هذا المسار يقدّر عدد التركيبات للوصول تقريبًا إلى لوكس الهدف؛ "
                "لم يُحسب U₀ على شبكة العمل. راجع التخطيط الكامل في LuxSCale قبل الاعتماد النهائي."
            )
        elif any_engine_non_compliant:
            lines.append(
                "⚠️ تحذير: تحقيق متوسط الإضاءة (لوكس) لا يعني بلوغ المعيار إذا كان U₀ أقل من القيمة المطلوبة "
                f"وفق المرجع ({std_ref}). وضع FAST قد يعرض أفضل تقدير متاح عندما لا يوجد تخطيط مطابق تمامًا؛ "
                "جرّب وضع الحساب الكامل في LuxSCale أو زد عدد التركيبات/غيّر عائلة التركيبة أو شبكة التوزيع."
            )
            if all_engine_u0_fail and _planning_answer_industrial_context(
                place_name, task_or_activity, category
            ):
                lines.append(
                    "في مساحات صناعية ضيقة، غالبًا ما تعطي خطوط التركيبات الخطية (مثل triproof) تجانسًا أفضل من الشبكات القليلة للوحات."
                )
        return "\n".join(lines)

    lines.append("📐 Inferred Inputs")
    lines.append(f"   Type: {place_name}  |  Dimensions: {l:g} × {w:g} × {h:g} m  |  Area: {area:g} m²")
    lines.append(f"   Task/activity: {task_line}")
    lines.append(f"   Target: {target_lux:.0f} lx  |  Uo ≥ {uo_min:g}  |  Standard ref: {std_ref}")
    lines.append("   Engine: LuxScale calculate_lighting (FAST)")
    if fill_note_en:
        lines.append(f"   Note: {fill_note_en}")
    lines.append(sep)
    lines.append("💡 Fixture Options  (LuxScale engine)")
    for i, opt in enumerate(options, 1):
        img = opt.get("image_url") or ""
        url = opt.get("product_url") or ""
        title = opt.get("product_title") or opt["label"]
        uni_ok = bool(opt.get("uniformity_evaluated", True))
        lux_p = bool(opt.get("lux_pass", True))
        u0_p = bool(opt.get("u0_pass", True))
        lines.append("")
        lines.append(f"  {i}. {title}  ({opt['power_w']} W)")
        if img:
            lines.append(f"  [img]{img}[/img]")
        lines.append(f"     Fixtures needed : {opt['fixtures']}")
        u0_disp = opt.get("u0")
        if uni_ok and u0_disp is not None:
            lines.append(
                f"     Achieved lux    : {opt['achieved_lux']} lx  |  U0 (calc): {float(u0_disp):g}"
            )
        else:
            lines.append(
                f"     Achieved lux (flux estimate): {opt['achieved_lux']} lx  |  U0: not evaluated on this path"
            )
        lines.append(f"     Total load      : {opt['total_kw']} kW  ({opt['watts_per_m2']} W/m²)")
        grid_x = opt.get("layout_nx") or 0
        grid_y = opt.get("layout_ny") or 0
        grid_txt = f"{grid_x}x{grid_y}" if grid_x or grid_y else "-"
        lines.append(
            f"     Flux / fixture  : {opt['lumens']:,} lm  |  UF={opt['uf']}  MF={opt['mf']}  |  Grid={grid_txt}"
        )
        if uni_ok:
            lx_en = "meets target" if lux_p else "below target"
            u0_en = "meets minimum" if u0_p else "below required"
            lines.append(f"     Standard check    : illuminance → {lx_en}  |  U₀ → {u0_en}")
        else:
            lx_en = "~meets target" if lux_p else "may be short of target"
            lines.append(f"     Lux-only check    : {lx_en} (no U₀ on this fallback)")
        if url:
            lines.append(f"     [url]{url}[/url]")
    lines.append("")
    lines.append(sep)
    lines.append("ℹ️  Results use the same LuxScale core calculation engine (FAST mode).")
    if uses_lumen_fallback_only:
        lines.append(
            "⚠️ This path estimates fixture count from flux toward the lux target; "
            "U₀ was not evaluated on the workplane grid. Validate in full LuxSCale before sign-off."
        )
    elif any_engine_non_compliant:
        lines.append(
            "⚠️ Warning: hitting the average illuminance target does **not** satisfy the standard row if U₀ "
            f"is below the required minimum ({std_ref}). FAST mode may show best-effort layouts when no fully "
            "compliant grid is found — try full calculation in LuxSCale, increase fixtures, change luminaire "
            "family, or tighten spacing."
        )
        if all_engine_u0_fail and _planning_answer_industrial_context(
            place_name, task_or_activity, category
        ):
            lines.append(
                "For compact industrial rooms, linear weatherproof layouts (e.g. triproof runs) often improve "
                "uniformity versus a small number of wide panels."
            )
    return "\n".join(lines)


def _local_fixture_count_guidance(
    question: str,
    reply_language: str = "en",
) -> Optional[Dict[str, Any]]:
    if not _is_fixture_count_intent(question):
        return None

    params = _resolve_fixture_planning_inputs(question)
    missing = _missing_required_fields_for_planning(params)
    used_gemini_fill = False
    gemini_fill_source = ""
    if missing:
        filled = _structured_gemini_fill_for_planning(
            question=question,
            missing_fields=missing,
            reply_language=reply_language,
        )
        gemini_fill_source = str(filled.get("source") or "")
        payload = filled.get("payload")
        if isinstance(payload, dict):
            params = _merge_structured_fill(params, payload)
            used_gemini_fill = True
            missing = _missing_required_fields_for_planning(params)

    if missing:
        items = "; ".join(missing)
        if reply_language == "ar":
            answer = (
                f"لإتمام حساب عدد التركيبات أحتاج القيم التالية: {items}. "
                "أرسلها بصيغة مثل: 80*70*6 داخل مصنع."
            )
        else:
            answer = (
                f"To run fixture calculation I still need: {items}. "
                "You can send them like: 80*70*6 inside factory."
            )
        return {
            "source": "planning_local",
            "answer": answer,
            "requires_confirmation": False,
            "show_yes_no": False,
            "confidence": 0.88,
            "missing_fields": missing,
            "gemini_fill_source": gemini_fill_source or "gemini_unavailable",
        }

    sides = list(params.get("sides") or [])
    h = float(params.get("height") or 0.0)
    l = float(max(float(sides[0]), float(sides[2]))) if len(sides) == 4 else 0.0
    w = float(max(float(sides[1]), float(sides[3]))) if len(sides) == 4 else 0.0
    area = float(l * w)
    place_name = str(params.get("place_name") or "General")
    standard_row = params.get("standard_row")
    if standard_row is not None:
        target_lux = float(standard_row.get("Em_r_lx") or 200.0)
        uo_min = float(standard_row.get("Uo") or 0.4)
    else:
        target_lux, uo_min, _ = _standard_targets_for_place(place_name)

    calc_run = _run_core_planning_calc(params)
    options: List[Dict[str, Any]] = []
    used_engine = bool(calc_run.get("ok"))
    if used_engine:
        l = float(calc_run.get("length") or l)
        w = float(calc_run.get("width") or w)
        area = float(calc_run.get("area") or area)
        options = list(calc_run.get("options") or [])
    else:
        options = _calc_fixture_options(
            area=area,
            height=h,
            target_lux=float(target_lux),
            place_name=place_name,
        )

    answer = _format_local_calc_answer(
        l=float(l),
        w=float(w),
        h=float(h),
        area=area,
        place_name=place_name,
        target_lux=float(target_lux),
        uo_min=float(uo_min),
        options=options,
        lang=reply_language,
        standard_ref_no=str(params.get("standard_ref_no") or ""),
        task_or_activity=str(params.get("task_or_activity") or ""),
        category=str(params.get("category") or ""),
        used_gemini_fill=used_gemini_fill,
    )

    return {
        "source": "planning_local",
        "answer": answer,
        "requires_confirmation": False,
        "show_yes_no": False,
        "confidence": 0.96 if used_engine else 0.9,
        "engine": "calculate_lighting_fast" if used_engine else "fallback_lumen_method",
        "canonical_response_id": "fixture_count_planning",
        "standard_ref_no": str(params.get("standard_ref_no") or ""),
    }


@lru_cache(maxsize=4)
def _load_fixed_responses_doc_stamped(mtime_key: float) -> Dict[str, Any]:
    if not os.path.isfile(FIXED_RESPONSES_PATH):
        return {"responses": [], "menu_items": [], "match_hints": {}}
    try:
        with open(FIXED_RESPONSES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception as e:
        log_exception("chat_service.load_fixed_responses_doc", e)
    return {"responses": [], "menu_items": [], "match_hints": {}}


def load_fixed_responses_doc() -> Dict[str, Any]:
    return _load_fixed_responses_doc_stamped(_mtime_key(FIXED_RESPONSES_PATH))


@lru_cache(maxsize=4)
def _load_aliases_doc_stamped(mtime_key: float) -> Dict[str, Any]:
    for path in ALIASES_PATHS:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as e:
            log_exception("chat_service.load_aliases_doc", e)
    return {"places": {}, "parameters": {}}


def load_aliases_doc() -> Dict[str, Any]:
    return _load_aliases_doc_stamped(_aliases_mkey())


def clear_all_chat_dict_caches() -> None:
    _load_fixed_responses_doc_stamped.cache_clear()
    _load_aliases_doc_stamped.cache_clear()
    _load_standards_cleaned_stamped.cache_clear()
    _load_standards_keywords_stamped.cache_clear()
    _standards_row_by_ref_map_stamped.cache_clear()
    _catalog_luminaire_names_stamped.cache_clear()
    try:
        from luxscale.fixture_catalog import clear_fixture_map_cache

        clear_fixture_map_cache()
    except Exception as e:
        log_exception("chat_service.clear_all_chat_dict_caches", e)


def clear_fixed_responses_cache() -> None:
    clear_all_chat_dict_caches()


def _all_candidates_for_response(r: dict) -> List[str]:
    out: List[str] = []
    q = str(r.get("question") or "").strip()
    if q:
        out.append(q)
    for v in r.get("variants") or []:
        vv = str(v or "").strip()
        if vv:
            out.append(vv)
    return out


def exact_fixed_match(question: str) -> Optional[dict]:
    qn = _normalize_text(question)
    if not qn:
        return None
    doc = load_fixed_responses_doc()
    for r in doc.get("responses") or []:
        for c in _all_candidates_for_response(r):
            if qn == _normalize_text(c):
                return r
    return None


def semantic_fixed_match(question: str, threshold: float = 0.56) -> Optional[MatchResult]:
    qn = _normalize_text(question)
    qt = _tokenize(question)
    if not qn or not qt:
        return None

    doc = load_fixed_responses_doc()
    best: Optional[MatchResult] = None
    for r in doc.get("responses") or []:
        for c in _all_candidates_for_response(r):
            cn = _normalize_text(c)
            ct = _tokenize(c)
            jac = _jaccard(qt, ct)
            seq = _ratio(qn, cn)
            substring_boost = 1.0 if qn in cn or cn in qn else 0.0
            score = (jac * 0.55) + (seq * 0.40) + (substring_boost * 0.05)
            if best is None or score > best.score:
                best = MatchResult(response=r, score=score, matched_phrase=c)
    if best and best.score >= threshold:
        return best
    return None


def _match_hints() -> Dict[str, List[str]]:
    doc = load_fixed_responses_doc()
    h = doc.get("match_hints") or {}
    return {
        "lighting_positive": [str(x).lower() for x in (h.get("lighting_positive") or [])],
        "recommendation_intent": [
            str(x).lower() for x in (h.get("recommendation_intent") or [])
        ],
        "recommendation_intent_ar": [
            str(x).strip() for x in (h.get("recommendation_intent_ar") or [])
        ],
        "negative_scope": [str(x).lower() for x in (h.get("negative_scope") or [])],
        "lighting_positive_ar": [
            str(x).strip() for x in (h.get("lighting_positive_ar") or [])
        ],
        "negative_scope_ar": [
            str(x).strip() for x in (h.get("negative_scope_ar") or [])
        ],
    }


def _signal_terms_present(text: str, terms: List[str]) -> List[str]:
    hits: List[str] = []
    qn = _normalize_text(text)
    if not qn:
        return hits
    for t in terms:
        tt = _normalize_text(t)
        if not tt:
            continue
        if re.search(r"\b" + re.escape(tt) + r"\b", qn):
            hits.append(tt)
    return hits


def _domain_signal_details(question: str) -> Dict[str, Any]:
    qn = _normalize_text(question)
    hints = _match_hints()
    positive_en_hits = _signal_terms_present(
        qn,
        hints["lighting_positive"],
    )
    positive_ar_hits = [
        t for t in hints["lighting_positive_ar"] if t and t in str(question or "")
    ]

    standard_ref_hits: List[str] = []
    std_patterns = [
        r"\b(?:en|bs\s*en)\s*12464(?:\s*-\s*1)?\b",
        r"\bies\b",
        r"\blm\s*[- ]?63\b",
        r"\b12464(?:\s*-\s*1)?\b",
    ]
    for pat in std_patterns:
        if re.search(pat, qn, flags=re.IGNORECASE):
            standard_ref_hits.append(pat)

    quantity_hits: List[str] = []
    qty_patterns = [
        r"\blux\b",
        r"\bu0\b",
        r"\bra\b",
        r"\bcri\b",
        r"\bcct\b",
        r"\bkelvin\b",
        r"\bbeam[-\s]?angle\b",
        r"\b(half|full|narrow)\s+beam\b",
        r"\b(photometr|luminous|intensity|candela|lumen)\b",
    ]
    for pat in qty_patterns:
        if re.search(pat, qn, flags=re.IGNORECASE):
            quantity_hits.append(pat)
    if _contains_arabic(question):
        ar_qty_terms = ("لوكس", "يو او", "تجانس", "توحيد", "را", "مؤشر تجسيد")
        for term in ar_qty_terms:
            if term in str(question or ""):
                quantity_hits.append(term)

    place_hit = _detect_place_canonical(question)
    if place_hit:
        positive_en_hits.append(f"place:{place_hit}")

    negative_en_hits = _signal_terms_present(
        qn,
        hints["negative_scope"],
    )
    negative_ar_hits = [t for t in hints["negative_scope_ar"] if t and t in str(question or "")]

    categories = {
        "domain_noun": bool(positive_en_hits or positive_ar_hits or place_hit),
        "standard_ref": bool(standard_ref_hits),
        "quantity": bool(quantity_hits),
    }

    return {
        "categories": categories,
        "positive_en_hits": positive_en_hits,
        "positive_ar_hits": positive_ar_hits,
        "standard_ref_hits": standard_ref_hits,
        "quantity_hits": quantity_hits,
        "negative_en_hits": negative_en_hits,
        "negative_ar_hits": negative_ar_hits,
    }


def lighting_topic_gate(
    question: str,
    effective_question: Optional[str] = None,
    return_meta: bool = False,
) -> Any:
    """
    Local-only classifier.
    Returns True if question is lighting-related and allowed to use the LLM chat fallback.
    """
    raw = str(question or "").strip()
    effective = str(effective_question or "").strip()
    if not raw:
        result = False
        meta = {"allowed": result, "reason": "empty_question"}
        return (result, meta) if return_meta else result

    raw_details = _domain_signal_details(raw)
    raw_categories = raw_details["categories"]
    raw_signal_count = sum(1 for v in raw_categories.values() if v)
    raw_has_negative = bool(raw_details["negative_en_hits"] or raw_details["negative_ar_hits"])

    place_standard_hit = _find_place_standard_response(raw) is not None
    weak = semantic_fixed_match(raw, threshold=0.46)
    weak_hit = False
    weak_tags: List[str] = []
    if weak is not None:
        weak_tags = [str(t).lower() for t in (weak.response.get("tags") or [])]
        # Include Short Circuit / product identity (see company_designer_info tags).
        _weak_ok = (
            "standards",
            "fixtures",
            "ies",
            "uniformity",
            "company",
            "shortcircuit",
        )
        weak_hit = any(t in _weak_ok for t in weak_tags)

    allowed = False
    reason = "no_signal"
    used_effective = False
    effective_details: Dict[str, Any] = {}

    if place_standard_hit:
        allowed = True
        reason = "place_standard_match"
    elif raw_signal_count >= 1:
        if raw_has_negative and raw_signal_count == 1 and raw_categories.get("domain_noun"):
            # Example: broad text with one weak positive + strong off-topic markers.
            allowed = False
            reason = "negative_scope_overrode_weak_raw_signal"
        else:
            allowed = True
            reason = "raw_signal_categories"
    elif weak_hit:
        allowed = True
        reason = "weak_semantic_fixed_match"
    elif effective and effective != raw:
        # Do not open gate from old context alone unless current raw looks like a follow-up.
        if _is_follow_up_question(raw):
            effective_details = _domain_signal_details(effective)
            eff_count = sum(1 for v in effective_details["categories"].values() if v)
            if eff_count >= 1:
                allowed = True
                reason = "effective_followup_signal"
                used_effective = True

    if raw_has_negative and raw_signal_count == 0:
        allowed = False
        reason = "negative_scope_only"

    meta = {
        "allowed": allowed,
        "reason": reason,
        "raw_signal_count": raw_signal_count,
        "raw_categories": raw_categories,
        "raw_positive_en": raw_details["positive_en_hits"],
        "raw_positive_ar": raw_details["positive_ar_hits"],
        "raw_standard_refs": raw_details["standard_ref_hits"],
        "raw_quantity_refs": raw_details["quantity_hits"],
        "raw_negative_en": raw_details["negative_en_hits"],
        "raw_negative_ar": raw_details["negative_ar_hits"],
        "used_effective": used_effective,
        "effective_categories": (effective_details.get("categories") or {}),
        "weak_semantic_hit": weak_hit,
        "weak_semantic_tags": weak_tags,
    }
    log_step("chat_service.lighting_topic_gate", "decision", **meta)
    return (allowed, meta) if return_meta else allowed


def _is_recommendation_intent(question: str) -> bool:
    qn = _normalize_text(question)
    raw = str(question or "")
    if not qn:
        return False
    hints = _match_hints()
    if any(k in qn for k in hints["recommendation_intent"]):
        return True
    if any(k and k in raw for k in hints["recommendation_intent_ar"]):
        return True
    direct_terms = (
        "recommend",
        "which fixture",
        "best fixture",
        "best luminaire",
        "compare fixture",
        "choose luminaire",
    )
    direct_terms_ar = (
        "اقترح",
        "انسب",
        "افضل",
        "تركيبه",
        "تركيبة",
        "مصباح",
        "لومينير",
    )
    return any(t in qn for t in direct_terms) or any(t in raw for t in direct_terms_ar)


def _purge_pending_locked(now_ts: float) -> None:
    stale = [
        sid
        for sid, rec in _PENDING_SUGGESTIONS.items()
        if (now_ts - float(rec.get("created_at", 0.0))) > PENDING_TTL_SECONDS
    ]
    for sid in stale:
        _PENDING_SUGGESTIONS.pop(sid, None)


def _set_pending_suggestion(
    session_id: str,
    question: str,
    response: dict,
    score: float,
    selected_answer: str,
    reply_language: str,
) -> None:
    now_ts = time.time()
    with _PENDING_LOCK:
        _purge_pending_locked(now_ts)
        _PENDING_SUGGESTIONS[session_id] = {
            "question": question,
            "response": response,
            "score": float(score),
            "selected_answer": str(selected_answer or ""),
            "canonical_key": _response_canonical_key(response),
            "reply_language": str(reply_language or "en"),
            "created_at": now_ts,
        }


def _pop_pending(session_id: str) -> Optional[dict]:
    now_ts = time.time()
    with _PENDING_LOCK:
        _purge_pending_locked(now_ts)
        rec = _PENDING_SUGGESTIONS.get(session_id)
        if not rec:
            return None
        # Keep pending for yes/no use; caller decides to pop.
        return dict(rec)


def _clear_pending(session_id: str) -> None:
    with _PENDING_LOCK:
        _PENDING_SUGGESTIONS.pop(session_id, None)


def _purge_clarify_locked(now_ts: float) -> None:
    stale = [
        sid
        for sid, rec in _CLARIFY_STATE.items()
        if (now_ts - float(rec.get("created_at", 0.0))) > _CLARIFY_TTL_SECONDS
    ]
    for sid in stale:
        _CLARIFY_STATE.pop(sid, None)


def _mark_clarified(session_id: str, question: str, intent_hint: str = "") -> None:
    now_ts = time.time()
    with _CLARIFY_LOCK:
        _purge_clarify_locked(now_ts)
        _CLARIFY_STATE[session_id] = {
            "created_at": now_ts,
            "question": str(question or ""),
            "intent_hint": str(intent_hint or "generic"),
            "already_clarified": True,
        }


def _clear_clarify(session_id: str) -> None:
    with _CLARIFY_LOCK:
        _CLARIFY_STATE.pop(session_id, None)


def _already_clarified(session_id: str) -> bool:
    now_ts = time.time()
    with _CLARIFY_LOCK:
        _purge_clarify_locked(now_ts)
        rec = _CLARIFY_STATE.get(session_id) or {}
    return bool(rec.get("already_clarified"))


def _clarify_intent_for_session(session_id: str) -> str:
    now_ts = time.time()
    with _CLARIFY_LOCK:
        _purge_clarify_locked(now_ts)
        rec = _CLARIFY_STATE.get(session_id) or {}
    return str(rec.get("intent_hint") or "").strip().lower()


def _clarify_intent_hint(question: str, gate_meta: Optional[Dict[str, Any]] = None) -> str:
    q = str(question or "")
    qn = _normalize_text(q)
    if not qn:
        return "generic"

    if _is_fixture_catalog_intent(question):
        return "fixture_catalog"

    company_markers = (
        "who",
        "designed",
        "built",
        "made",
        "developed",
        "website",
        "company",
        "شركه",
        "شركة",
        "صمم",
        "طور",
        "عمل",
        "مين",
        "موقع",
        "رسمي",
    )
    if any(m in qn or m in q for m in company_markers):
        return "company_identity"

    standard_markers = (
        "standard",
        "code",
        "en 12464",
        "en12464",
        "12464",
        "معيار",
        "كود",
        "القياسي",
    )
    if any(m in qn or m in q for m in standard_markers):
        return "standard_name"

    calc_markers = (
        "lux",
        "u0",
        "cri",
        "ra",
        "fixture",
        "fixtures",
        "ies",
        "لوكس",
        "تجانس",
        "تركيبه",
        "تركيبة",
        "مصباح",
        "عدد",
    )
    if _detect_place_canonical(question) is not None:
        return "place_target"
    if _extract_lwh_dims(question) is not None:
        return "fixture_count"
    if any(m in qn or m in q for m in calc_markers):
        return "lighting_calc"

    if isinstance(gate_meta, dict):
        reason = str(gate_meta.get("reason") or "")
        if reason == "weak_semantic_fixed_match":
            return "lighting_calc"
    return "generic"


def _clarify_answer(reply_language: str = "en", intent_hint: str = "generic") -> str:
    hint = str(intent_hint or "generic").strip().lower()
    if reply_language == "ar":
        if hint == "company_identity":
            return (
                "هل تقصد سؤالًا عن الشركة المطوّرة لـLuxSCale "
                "(مثال: من صمّم الأداة أو ما الموقع الرسمي)؟"
            )
        if hint == "standard_name":
            return (
                "هل سؤالك عن اسم المعيار المستخدم (مثل EN 12464-1)، "
                "أم تريد قيمة معيارية لمساحة معيّنة؟"
            )
        if hint == "fixture_catalog":
            return (
                "هل تريد قائمة عائلات التركيبات المتاحة في LuxSCale/الكتالوج، "
                "أم تريد حساب عدد التركيبات لمساحة بأبعاد محددة؟"
            )
        if hint in {"place_target", "fixture_count", "lighting_calc"}:
            return (
                "هل تريد قيمة معيارية للمساحة (lux/U0)، أم تريد حساب عدد التركيبات؟ "
                "اذكر نوع المكان والأبعاد إذا كانت متاحة."
            )
        return (
            "للتأكد أنني أفهم سؤالك بشكل صحيح: "
            "هل تسأل عن معيار إنارة (مثل EN 12464-1) أم عن قيمة مطلوبة لمساحة محددة "
            "(مثل lux/U0 للمكاتب أو المصانع)؟"
        )
    if hint == "company_identity":
        return (
            "Do you mean company identity information "
            "(for example who designed LuxSCale or the official website)?"
        )
    if hint == "standard_name":
        return (
            "Are you asking for the standard name used by LuxSCale (for example EN 12464-1), "
            "or a target value for a specific space?"
        )
    if hint == "fixture_catalog":
        return (
            "Do you want the list of mapped fixture families available in LuxSCale, "
            "or a fixture-count calculation for a room with dimensions?"
        )
    if hint in {"place_target", "fixture_count", "lighting_calc"}:
        return (
            "Do you need a standard target for a space (lux/U0), or a fixture-count estimate? "
            "Share place type and dimensions if available."
        )
    return (
        "Before I continue, a quick check: "
        "are you asking about a lighting standard name (for example EN 12464-1), "
        "or a required target value for a specific space (for example lux/U0 for offices or factories)?"
    )


def _session_id(raw: Optional[str]) -> str:
    sid = (raw or "").strip()
    if sid and re.fullmatch(r"[a-zA-Z0-9._:-]{6,120}", sid):
        return sid
    return secrets.token_hex(12)


def _out_of_scope_answer(reply_language: str = "en") -> str:
    if reply_language == "ar":
        return (
            "هذا السؤال ليس عن الإضاءة. يقتصر مساعد LuxSCale على مواضيع الضوء والإضاءة "
            "والفوتومترية ومعايير الإنارة. "
            "لأسئلة أخرى يرجى استخدام أداة أو مصدر مناسب خارج LuxSCale."
        )
    return (
        "This question is not about light or lighting. "
        "LuxSCale only helps with light-related topics such as photometry, standards, fixtures, and design context. "
        "For anything else, please use another source."
    )


def _fixture_entries() -> List[dict]:
    doc = load_fixture_map_document() or {}
    return list(doc.get("entries") or [])


def _fixture_map_mtime_key() -> float:
    from luxscale.ies_dataset_config import active_fixture_map_basename

    p = os.path.join(project_root(), "assets", str(active_fixture_map_basename() or ""))
    return _mtime_key(p)


@lru_cache(maxsize=4)
def _catalog_luminaire_names_stamped(mtime_key: float) -> frozenset:
    out: set = set()
    for e in _fixture_entries():
        n = str(e.get("api_luminaire_name") or "").strip()
        if n:
            out.add(n.lower())
    return frozenset(out)


def _catalog_luminaire_names() -> set:
    return set(_catalog_luminaire_names_stamped(_fixture_map_mtime_key()))


def _strict_lighting_for_gemini() -> bool:
    try:
        return bool(
            (load_app_settings() or {})
            .get("chat", {})
            .get("strict_lighting_for_gemini", False)
        )
    except Exception:
        return False


def _fixture_family_score(question_norm: str, family_name: str) -> float:
    n = family_name.lower()
    score = 0.0
    if n in question_norm:
        score += 1.5
    heuristics = [
        (("warehouse", "high ceiling", "factory", "industrial", "hangar"), "highbay"),
        (("street", "road", "pole", "outdoor roadway"), "street"),
        (("flood", "façade", "facade", "exterior", "outdoor"), "flood"),
        (("office", "classroom", "panel", "ceiling"), "backlight"),
        (("triproof", "parking", "service area"), "triproof"),
        (("spot", "accent", "downlight"), "downlight"),
    ]
    for keys, target in heuristics:
        if target in n and any(k in question_norm for k in keys):
            score += 1.0
    return score


def recommend_fixtures_from_catalog(question: str, max_items: int = 3) -> List[dict]:
    qn = _normalize_text(question)
    entries = _fixture_entries()
    if not entries:
        return []
    candidates: List[Tuple[float, dict]] = []
    for e in entries:
        name = str(e.get("api_luminaire_name") or "").strip()
        if not name:
            continue
        score = _fixture_family_score(qn, name)
        if score <= 0 and _is_recommendation_intent(question):
            # Keep potential defaults for recommendation requests.
            score = 0.2
        if score <= 0:
            continue
        online = e.get("online") or {}
        imgs = e.get("image_urls") or []
        candidates.append(
            (
                score,
                {
                    "luminaire": name,
                    "power_w": int(e.get("power_w") or 0),
                    "product_title": str(online.get("product_title") or name),
                    "product_url": str(
                        online.get("product_url")
                        or "https://shortcircuit.company"
                    ),
                    "image_url": str(imgs[0]) if isinstance(imgs, list) and imgs else "",
                    "relative_ies_path": str(e.get("relative_ies_path") or ""),
                    "photometry_json": str(e.get("photometry_json") or ""),
                },
            )
        )

    candidates.sort(
        key=lambda x: (-x[0], x[1]["luminaire"].lower(), x[1]["power_w"])
    )

    seen = set()
    out: List[dict] = []
    for _, row in candidates:
        k = (row["luminaire"], row["power_w"])
        if k in seen:
            continue
        seen.add(k)
        out.append(row)
        if len(out) >= max_items:
            break

    if not out and entries:
        # Safe default shortlist.
        for e in entries[:max_items]:
            online = e.get("online") or {}
            imgs = e.get("image_urls") or []
            out.append(
                {
                    "luminaire": str(e.get("api_luminaire_name") or ""),
                    "power_w": int(e.get("power_w") or 0),
                    "product_title": str(online.get("product_title") or e.get("api_luminaire_name") or ""),
                    "product_url": str(online.get("product_url") or "https://shortcircuit.company"),
                    "image_url": str(imgs[0]) if isinstance(imgs, list) and imgs else "",
                    "relative_ies_path": str(e.get("relative_ies_path") or ""),
                    "photometry_json": str(e.get("photometry_json") or ""),
                }
            )
    return out


def _fixture_context_lines(fixtures: List[dict]) -> str:
    if not fixtures:
        return ""
    lines = ["Use only these fixture candidates when recommending products:"]
    for i, f in enumerate(fixtures, start=1):
        lines.append(
            f"{i}) {f['luminaire']} {f['power_w']}W | "
            f"title={f['product_title']} | "
            f"url={f['product_url']} | "
            f"image={f['image_url']} | "
            f"ies={f['relative_ies_path']}"
        )
    return "\n".join(lines)


def _chat_context_lines(context_messages: List[Dict[str, str]]) -> str:
    if not context_messages:
        return ""
    lines = ["Recent chat context:"]
    for msg in context_messages[-6:]:
        role = "User" if msg.get("role") == "user" else "Assistant"
        lines.append(f"- {role}: {msg.get('text')}")
    return "\n".join(lines)


def _compact_luminaire_allowlist(max_names: int = 48) -> str:
    names: List[str] = []
    seen: set = set()
    for e in _fixture_entries() or []:
        n = str((e or {}).get("api_luminaire_name") or "").strip()
        if n and n.lower() not in seen:
            seen.add(n.lower())
            names.append(n)
        if len(names) >= int(max_names):
            break
    if not names:
        return ""
    return "Luminaire name allowlist (use only these labels if naming products): " + ", ".join(names)


def _chat_prompt(
    question: str,
    fixtures: List[dict],
    reply_language: str = "en",
    context_messages: Optional[List[Dict[str, str]]] = None,
) -> str:
    lang_name = "Arabic" if reply_language == "ar" else "English"
    base = (
        "You are LuxSCale's lighting assistant. "
        f"Reply in short plain {lang_name} (max 6 lines). "
        "If the question is about light, lighting, photometry, fixtures, or lighting standards, "
        "answer briefly; add 1–2 well-known reference pointers by name (for example IES, CIE, or EN 12464-1 where appropriate)—do not claim live web access. "
        "If the question is clearly not about light or lighting, say in one line that you only help with light-related questions. "
        "If more data is needed for a design, ask for room dimensions and target lux/U0. "
        "For applicable workplace/indoor task lighting, anchor on EN 12464-1; do not substitute other building codes. "
        "Mention only Short Circuit / SC/SV catalog luminaire labels. "
        "Do not name competitor manufacturers. "
        "If recommending fixtures, include name + watt + one short reason."
    )
    fixture_ctx = _fixture_context_lines(fixtures)
    allow_ctx = _compact_luminaire_allowlist(48)
    context_ctx = _chat_context_lines(context_messages or [])
    return (
        f"{base}\n\n"
        f"{allow_ctx}\n\n"
        f"{context_ctx}\n\n"
        f"User question:\n{question}\n\n"
        f"{fixture_ctx}"
    ).strip()


def _append_local_fixture_block(answer: str, fixtures: List[dict], reply_language: str = "en") -> str:
    if not fixtures:
        return answer.strip()
    if reply_language == "ar":
        lines = [answer.strip(), "", "تركيبات LuxSCale المقترحة محليًا:"]
    else:
        lines = [answer.strip(), "", "Recommended LuxSCale fixtures:"]
    for f in fixtures:
        if reply_language == "ar":
            reason = "مطابقة لنوع المكان وسياق الاستخدام مع توفر ربط IES"
            lines.append(
                f"- {f['luminaire']} {f['power_w']}W — {reason}\n"
                f"  البيانات: IES={f['relative_ies_path']} | Photometry={f['photometry_json']}\n"
                f"  المنتج: {f['product_url']}\n"
                f"  الصورة: {f['image_url']}"
            )
        else:
            reason = "matched by room/use keywords and available IES mapping"
            lines.append(
                f"- {f['luminaire']} {f['power_w']}W — {reason}\n"
                f"  Params: IES={f['relative_ies_path']} | Photometry={f['photometry_json']}\n"
                f"  Product: {f['product_url']}\n"
                f"  Image: {f['image_url']}"
            )
    return "\n".join(lines).strip()


def _extract_first_float(pattern: str, text: str) -> Optional[float]:
    m = re.search(pattern, str(text or ""), flags=re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _reconcile_gemini_answer(
    answer: str,
    question: str,
    reply_language: str,
) -> Dict[str, Any]:
    text = str(answer or "").strip()
    if not text:
        return {"answer": text, "reconciled": False, "notes": []}

    notes: List[str] = []
    reconciled_text = text
    normalized = _normalize_text(text)

    std_match = re.search(r"\b(?:bs\s+en|en)\s*(\d{4,5})(?:\s*-\s*(\d+))?\b", normalized, re.IGNORECASE)
    if std_match:
        std_no = str(std_match.group(1) or "").strip()
        std_part = str(std_match.group(2) or "").strip()
        if std_no != "12464" or (std_part and std_part != "1"):
            notes.append("standard_name_corrected")
            correction = (
                "تصويب مرجعي: المعيار المعتمد في LuxSCale هو EN 12464-1."
                if reply_language == "ar"
                else "Reference correction: LuxSCale standard mapping uses EN 12464-1."
            )
            reconciled_text = f"{text}\n\n{correction}".strip()

    place = _detect_place_canonical(question)
    if place:
        target_lux, target_u0, _ = _standard_targets_for_place(place)
        found_lux = _extract_first_float(r"(\d+(?:\.\d+)?)\s*lx", text)
        found_u0 = _extract_first_float(r"\bu0\b[^0-9]*(\d+(?:\.\d+)?)", text)
        mismatch_lux = found_lux is not None and abs(found_lux - target_lux) > max(35.0, target_lux * 0.22)
        mismatch_u0 = found_u0 is not None and abs(found_u0 - target_u0) > 0.15
        if mismatch_lux or mismatch_u0:
            notes.append("standard_value_corrected")
            correction = (
                f"تصويب محلي: للقسم ({place}) المرجع المحلي في LuxSCale هو {target_lux:.0f} lx و U0≥{target_u0:g} وفق EN 12464-1."
                if reply_language == "ar"
                else f"Local correction: for ({place}), LuxSCale local standard target is {target_lux:.0f} lx and U0≥{target_u0:g} per EN 12464-1."
            )
            if correction not in reconciled_text:
                reconciled_text = f"{reconciled_text}\n\n{correction}".strip()

    if _KNOWN_COMPETITOR_LUMINAIRE_RE.search(reconciled_text):
        if "competitor_brand_note" not in notes:
            notes.append("competitor_brand_note")
        fix = (
            "ملاحظة: LuxSCale يرتبط بكتالوج Short Circuit فقط؛ اذكر أسماء تنافسية (مكتوبة فوق) غير مؤكدة."
            if reply_language == "ar"
            else "Note: LuxSCale is grounded to the Short Circuit catalog; unverified competitor names above are not endorsed."
        )
        if fix not in reconciled_text:
            reconciled_text = f"{reconciled_text}\n\n{fix}".strip()

    cat_names = _catalog_luminaire_names()
    for m in _SC_CATALOG_TOKEN.finditer(reconciled_text):
        pfx = str(m.group(1) or "")
        sfx = str(m.group(2) or "")
        merged = f"{pfx}-{sfx}"
        cands = {merged.lower(), f"{pfx} {sfx}".lower(), (pfx + sfx).lower()}
        if cands & cat_names:
            continue
        if "unknown_catalog_luminaire_token" in notes:
            break
        notes.append("unknown_catalog_luminaire_token")
        ufix = (
            f"تصويب: لا يظهر {merged} في كتالوج LuxSCale — استخدم التركيبات المسردة فقط (SC/SV)."
            if reply_language == "ar"
            else f"Catalog note: {merged} is not listed in the LuxSCale map — use SC/SV fixtures from the provided list only."
        )
        if ufix not in reconciled_text:
            reconciled_text = f"{reconciled_text}\n\n{ufix}".strip()
        break

    return {
        "answer": reconciled_text,
        "reconciled": bool(notes),
        "notes": notes,
    }


def _gemini_fallback_answer(
    question: str,
    raw_question: Optional[str] = None,
    reply_language: str = "en",
    context_messages: Optional[List[Dict[str, str]]] = None,
    force_allow: bool = False,
) -> Dict[str, Any]:
    raw_q = str(raw_question or question or "")
    gate_allowed, gate_meta = lighting_topic_gate(
        raw_q,
        effective_question=question,
        return_meta=True,
    )
    if (not gate_allowed) and (not force_allow):
        log_step(
            "chat_service.gemini_fallback",
            "blocked_by_gate",
            reason=str(gate_meta.get("reason") or ""),
            raw_signal_count=int(gate_meta.get("raw_signal_count") or 0),
        )
        return {
            "source": "out_of_scope",
            "answer": _out_of_scope_answer(reply_language=reply_language),
            "requires_confirmation": False,
            "show_yes_no": False,
            "confidence": 1.0,
            "fixtures": [],
            "gate_meta": gate_meta,
        }

    if (not force_allow) and _strict_lighting_for_gemini():
        det = _domain_signal_details(str(raw_q or ""))
        cats = det.get("categories") or {}
        if not any(
            bool(cats.get(x))
            for x in ("domain_noun", "standard_ref", "quantity")
        ) and not re.search(
            r"(?i)(luxscale|short\s*circuit|lux-scal)",
            str(raw_q or ""),
        ):
            log_step(
                "chat_service.gemini_fallback",
                "blocked_by_strict_setting",
            )
            return {
                "source": "out_of_scope",
                "answer": _out_of_scope_answer(reply_language=reply_language),
                "requires_confirmation": False,
                "show_yes_no": False,
                "confidence": 1.0,
                "fixtures": [],
                "gate_meta": {**(gate_meta or {}), "strict_mode": True},
            }

    need_fixtures = _is_recommendation_intent(question)
    fixtures = (
        recommend_fixtures_from_catalog(question, max_items=5) if need_fixtures else []
    )
    prompt = _chat_prompt(
        question,
        fixtures,
        reply_language=reply_language,
        context_messages=context_messages,
    )
    g = ask_gemini_text(prompt, max_output_tokens=260, temperature=0.2)
    text = (g.get("text") or "").strip()
    source = str(g.get("source") or "gemini")

    if not text:
        if str(source) == "ollama_unavailable":
            if reply_language == "ar":
                text = (
                    "تعذّر الرد الآن. أعد المحاولة بعد لحظات. "
                    "لحسابات داخل التطبيق أرسل أبعاد المساحة ونوع المكان."
                )
            else:
                text = (
                    "I could not get an answer right now. Please try again in a moment. "
                    "For project numbers, use LuxSCale with your room size and place type."
                )
        elif reply_language == "ar":
            text = (
                "تعذّر الرد الآن—قد يكون الاتصال مؤقتًا. أعد المحاولة لاحقًا. "
                "لحسابات في LuxSCale أرسل أبعاد الغرفة ونوع المكان."
            )
        else:
            text = (
                "I could not get an answer right now. Please try again in a few minutes. "
                "This is often a temporary network issue. For lighting calculations, enter dimensions in LuxSCale; many standard topics are also in the app’s local help."
            )
        if str(source) != "ollama_unavailable":
            source = "gemini_unavailable"

    if fixtures:
        text = _append_local_fixture_block(text, fixtures, reply_language=reply_language)

    reconciled = _reconcile_gemini_answer(
        answer=text,
        question=raw_q,
        reply_language=reply_language,
    )
    text = str(reconciled.get("answer") or text)
    if reconciled.get("reconciled"):
        log_step(
            "chat_service.gemini_fallback",
            "post_reconciled",
            notes=list(reconciled.get("notes") or []),
        )

    return {
        "source": source,
        "answer": text,
        "requires_confirmation": False,
        "show_yes_no": False,
        "confidence": 0.75 if source.startswith("gemini:") else 0.35,
        "fixtures": fixtures,
        "gate_meta": gate_meta,
        "reconciled": bool(reconciled.get("reconciled")),
        "reconcile_notes": list(reconciled.get("notes") or []),
    }


def _yes_no_value(value: str) -> Optional[bool]:
    """
    Return True/False only when the message is *only* a short yes/no (no extra words),
    to avoid hijacking a normal follow-up (e.g. "yes, but what about u0?").
    """
    raw = str(value or "").strip()
    if not raw:
        return None
    v = _normalize_text(raw)
    v = " ".join(v.split())
    yes_1 = {
        "yes",
        "y",
        "ok",
        "correct",
        "fine",
        "yep",
        "yeah",
        "نعم",
        "ايوه",
        "ايوا",
        "تمام",
        "اه",
    }
    no_1 = {
        "no",
        "n",
        "nope",
        "not",
        "no.",
        "لا",
        "لأ",
    }
    no_2 = {"not really", "of course not"}
    if v in yes_1:
        return True
    if v in no_1 or v in no_2:
        return False
    return None


def handle_feedback(session_id: str, feedback: str) -> Dict[str, Any]:
    sid = _session_id(session_id)
    yn = _yes_no_value(feedback)
    if yn is None:
        return {
            "status": "error",
            "message": "feedback must be yes or no",
            "session_id": sid,
        }
    pending = _pop_pending(sid)
    if not pending:
        return {
            "status": "error",
            "message": "No pending suggested answer for this session.",
            "session_id": sid,
        }

    question = str(pending.get("question") or "")
    suggested = pending.get("response") or {}
    selected_answer = str(pending.get("selected_answer") or str(suggested.get("answer") or ""))
    canonical_key = str(
        pending.get("canonical_key")
        or _response_canonical_key(suggested)
        or suggested.get("id")
        or ""
    )
    reply_language = str(pending.get("reply_language") or "en")
    _clear_pending(sid)

    if yn:
        _clear_clarify(sid)
        return {
            "status": "success",
            "session_id": sid,
            "source": "fixed_confirmed",
            "answer": selected_answer,
            "response_id": str(suggested.get("id") or ""),
            "canonical_response_id": canonical_key,
            "requires_confirmation": False,
            "show_yes_no": False,
            "confidence": 1.0,
            "question": question,
        }

    # User said no: move to fallback 3 directly.
    out = _gemini_fallback_answer(
        question,
        raw_question=question,
        reply_language=reply_language,
    )
    return {
        "status": "success",
        "session_id": sid,
        "question": question,
        **out,
    }


def handle_question(
    question: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    context_messages: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    sid = _session_id(user_id or session_id)
    raw = (question or "").strip()
    context = _coerce_context_messages(context_messages or [])
    reply_language = _detect_reply_language(raw, context)
    if not raw:
        return {
            "status": "error",
            "message": "message is required",
            "session_id": sid,
        }

    # If user just sent yes/no text, route to feedback branch.
    yn = _yes_no_value(raw)
    if yn is not None and _pop_pending(sid):
        return handle_feedback(sid, "yes" if yn else "no")

    catalog_out = _fixture_catalog_question_answer(raw, reply_language=reply_language, _session_id=sid)
    if catalog_out is not None:
        _clear_pending(sid)
        _clear_clarify(sid)
        return {
            "status": "success",
            "session_id": sid,
            "question": raw,
            **catalog_out,
        }

    # Fixture-count planning has higher priority than static/fixed standard lookups,
    # after catalog list questions (no dimensions).
    planning_out = _local_fixture_count_guidance(raw, reply_language=reply_language)
    if planning_out is not None:
        _clear_pending(sid)
        _clear_clarify(sid)
        return {
            "status": "success",
            "session_id": sid,
            "question": raw,
            **planning_out,
        }

    static_intent = _match_static_lookup_intent(
        raw,
        session_id=sid,
        reply_language=reply_language,
    )
    if static_intent is not None:
        _clear_pending(sid)
        _clear_clarify(sid)
        answer = static_intent.answer
        if _should_mark_repeated(
            raw,
            context,
            source_kind="static_local",
        ):
            answer = _apply_repeated_prefix(answer, reply_language)
        log_step(
            "chat_service.handle_question",
            "resolved_static_intent",
            intent_key=static_intent.intent_key,
            canonical_response_id=static_intent.canonical_key,
        )
        return {
            "status": "success",
            "session_id": sid,
            "source": "static_local",
            "answer": answer,
            "response_id": static_intent.response_id,
            "canonical_response_id": static_intent.canonical_key,
            "intent_key": static_intent.intent_key,
            "requires_confirmation": False,
            "show_yes_no": False,
            "confidence": 1.0,
        }

    place_standard = _find_place_standard_response(raw)
    if place_standard is not None:
        _clear_pending(sid)
        _clear_clarify(sid)
        fixed_answer = _response_localized_answer(place_standard, reply_language)
        if not fixed_answer:
            fixed_answer = _pick_fixed_answer(place_standard, raw, sid)
        if _should_mark_repeated(
            raw,
            context,
            response_hint=place_standard,
            source_kind="fixed_exact",
        ):
            fixed_answer = _apply_repeated_prefix(fixed_answer, reply_language)
        if not _response_localized_answer(place_standard, reply_language):
            fixed_answer = _translate_answer_if_needed(fixed_answer, reply_language)
        return {
            "status": "success",
            "session_id": sid,
            "source": "fixed_exact",
            "answer": fixed_answer,
            "response_id": str(place_standard.get("id") or ""),
            "canonical_response_id": _response_canonical_key(place_standard),
            "requires_confirmation": False,
            "show_yes_no": False,
            "confidence": 1.0,
        }

    alias_out = alias_lookup_answer(raw, reply_language=reply_language)
    if alias_out is not None:
        _clear_pending(sid)
        _clear_clarify(sid)
        if _should_mark_repeated(raw, context, source_kind="alias_lookup"):
            alias_out["answer"] = _apply_repeated_prefix(
                str(alias_out.get("answer") or ""),
                reply_language,
            )
        alias_out["canonical_response_id"] = str(alias_out.get("alias_canonical") or "")
        return {
            "status": "success",
            "session_id": sid,
            "question": raw,
            **alias_out,
        }

    effective_question = _compose_effective_question(raw, context)
    exact = exact_fixed_match(raw)
    if exact is None and effective_question != raw:
        exact = exact_fixed_match(effective_question)
    if exact is not None:
        _clear_pending(sid)
        _clear_clarify(sid)
        fixed_answer = _response_localized_answer(exact, reply_language)
        if not fixed_answer:
            fixed_answer = _pick_fixed_answer(exact, raw, sid)
        if _should_mark_repeated(
            raw,
            context,
            response_hint=exact,
            source_kind="fixed_exact",
        ):
            fixed_answer = _apply_repeated_prefix(fixed_answer, reply_language)
        if not _response_localized_answer(exact, reply_language):
            fixed_answer = _translate_answer_if_needed(fixed_answer, reply_language)
        return {
            "status": "success",
            "session_id": sid,
            "source": "fixed_exact",
            "answer": fixed_answer,
            "response_id": str(exact.get("id") or ""),
            "canonical_response_id": _response_canonical_key(exact),
            "requires_confirmation": False,
            "show_yes_no": False,
            "confidence": 1.0,
        }

    sem = semantic_fixed_match(raw, threshold=0.56)
    if sem is None and effective_question != raw:
        sem = semantic_fixed_match(effective_question, threshold=0.56)
    if sem is not None:
        suggested_answer = _response_localized_answer(sem.response, reply_language)
        if not suggested_answer:
            suggested_answer = _pick_fixed_answer(sem.response, raw, sid)
        if _should_mark_repeated(
            raw,
            context,
            response_hint=sem.response,
            source_kind="fixed_suggested",
        ):
            suggested_answer = _apply_repeated_prefix(suggested_answer, reply_language)
        if not _response_localized_answer(sem.response, reply_language):
            suggested_answer = _translate_answer_if_needed(suggested_answer, reply_language)
        _set_pending_suggestion(
            session_id=sid,
            question=raw,
            response=sem.response,
            score=sem.score,
            selected_answer=suggested_answer,
            reply_language=reply_language,
        )
        return {
            "status": "success",
            "session_id": sid,
            "source": "fixed_suggested",
            "answer": suggested_answer,
            "response_id": str(sem.response.get("id") or ""),
            "canonical_response_id": _response_canonical_key(sem.response),
            "match_score": round(float(sem.score), 4),
            "matched_phrase": sem.matched_phrase,
            "requires_confirmation": True,
            "show_yes_no": True,
            "confirmation_prompt": (
                "هل هذه الإجابة مناسبة لسؤالك؟"
                if reply_language == "ar"
                else "Is that answer your question?"
            ),
            "confidence": float(min(0.99, max(0.5, sem.score))),
        }

    _clear_pending(sid)
    gate_allowed, gate_meta = lighting_topic_gate(
        raw,
        effective_question=effective_question,
        return_meta=True,
    )
    force_gemini = False
    negative_only = str(gate_meta.get("reason") or "") == "negative_scope_only"
    already_clarified = _already_clarified(sid)
    clarify_intent = _clarify_intent_hint(raw, gate_meta=gate_meta)
    last_clarify_intent = _clarify_intent_for_session(sid)
    if not gate_allowed:
        if (not negative_only) and ((not already_clarified) or (last_clarify_intent != clarify_intent)):
            _mark_clarified(sid, raw, intent_hint=clarify_intent)
            log_step(
                "chat_service.handle_question",
                "clarify_before_gemini",
                session_id=sid,
                gate_reason=str(gate_meta.get("reason") or ""),
                clarify_intent=clarify_intent,
            )
            return {
                "status": "success",
                "session_id": sid,
                "source": "clarify_needed",
                "answer": _clarify_answer(reply_language=reply_language, intent_hint=clarify_intent),
                "requires_confirmation": False,
                "show_yes_no": False,
                "confidence": 0.9,
                "already_clarified": False,
                "clarify_intent": clarify_intent,
                "gate_meta": gate_meta,
            }
        if already_clarified and (not negative_only):
            force_gemini = True

    out = _gemini_fallback_answer(
        effective_question,
        raw_question=raw,
        reply_language=reply_language,
        context_messages=context,
        force_allow=force_gemini,
    )
    if out.get("source") != "out_of_scope":
        _clear_clarify(sid)
    if _should_mark_repeated(raw, context, source_kind="gemini"):
        out["answer"] = _apply_repeated_prefix(str(out.get("answer") or ""), reply_language)
    return {
        "status": "success",
        "session_id": sid,
        "question": raw,
        "already_clarified": already_clarified,
        **out,
    }


def get_menu_items() -> List[Dict[str, Any]]:
    doc = load_fixed_responses_doc()
    return list(doc.get("menu_items") or [])


def chat_health() -> Dict[str, Any]:
    doc = load_fixed_responses_doc()
    return {
        "fixed_path": FIXED_RESPONSES_PATH,
        "fixed_responses_count": len(doc.get("responses") or []),
        "menu_items_count": len(doc.get("menu_items") or []),
        "generated_at": doc.get("generated_at"),
        "updated_at": doc.get("updated_at"),
    }

