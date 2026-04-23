# Chat Local Calculation Plan
## Dimension-Based Fixture Estimate in `chat_service.py`

**Goal:** When the user provides room dimensions in the chat, return a short local calculation summary with fixture options (no AI, no Gemini). Ask only for missing required data.

---

## Current State

`_local_fixture_count_guidance()` already:
- Detects fixture-count intent via `_is_fixture_count_intent()`
- Extracts L × W × H via `_extract_lwh_dims()`
- Detects place type (factory, office, etc.) via `_detect_place_canonical()`
- Returns a **text-only** response pointing the user to the calculator

**What it does NOT do:** Actually run the lumen-method math locally.

---

## What You Need to Build

### Stage 1 — Determine What Data You Have vs. What You're Missing

**Required inputs for a meaningful estimate:**
| Parameter | Source | Default if missing |
|---|---|---|
| L, W (m) | Parsed from message | — must ask |
| H (m) | Parsed from message | ask only if H matters for fixture type |
| Place type | Keyword detection | ask if ambiguous |
| Target lux (E) | EN 12464-1 standard for place | auto-fill from standards |
| Utilization factor (UF) | Typical range by place | use conservative default (0.6) |
| Maintenance factor (MF) | Room cleanliness | default 0.8 |

**Ask only for what's truly missing.** If place type is detected → lux target is auto-filled. Never ask for lux if the place is known.

---

## Implementation Steps

### Step 1 — Create `_missing_required_fields(dims, place)` helper

In `chat_service.py`, add:

```python
def _missing_required_fields(
    dims: Optional[Tuple[float, float, float]],
    place_name: Optional[str],
) -> List[str]:
    """Return list of labels that must be asked before calculation can proceed."""
    missing = []
    if dims is None:
        missing.append("room dimensions (Length × Width × Height in meters)")
    elif dims[2] is None or dims[2] <= 0:
        missing.append("ceiling height (H in meters)")
    if place_name is None:
        missing.append("room type (e.g. factory, office, warehouse)")
    return missing
```

**Rule:** If `missing` is non-empty → return a short asking message, nothing else. No calculation yet.

---

### Step 2 — Extend `_local_fixture_count_guidance()` to run lumen-method math

Replace the current stub answer with a real calculation block when all required data is present.

```python
def _local_fixture_count_guidance(
    question: str,
    reply_language: str = "en",
) -> Optional[Dict[str, Any]]:
    if not _is_fixture_count_intent(question):
        return None

    dims = _extract_lwh_dims(question)          # (L, W, H) or None
    place_name = _detect_place_canonical(question)

    # --- Stage A: ask for missing fields ---
    missing = _missing_required_fields(dims, place_name)
    if missing:
        items = "; ".join(missing)
        if reply_language == "ar":
            answer = f"لإتمام الحساب، أحتاج: {items}."
        else:
            answer = f"To estimate fixtures I need: {items}."
        return {
            "source": "planning_local",
            "answer": answer,
            "requires_confirmation": False,
            "show_yes_no": False,
            "confidence": 0.9,
        }

    # --- Stage B: look up standard lux target ---
    l, w, h = dims
    area = l * w
    std_lux, uo_min, cri_min = _standard_targets_for_place(place_name)

    # --- Stage C: run lumen-method for 2-3 typical fixture families ---
    summaries = _calc_fixture_options(area, h, std_lux)

    # --- Stage D: format short answer ---
    answer = _format_local_calc_answer(
        l, w, h, area, place_name, std_lux, uo_min, summaries, reply_language
    )

    return {
        "source": "planning_local",
        "answer": answer,
        "requires_confirmation": False,
        "show_yes_no": False,
        "confidence": 0.95,
    }
```

---

### Step 3 — Add `_standard_targets_for_place(place_name)` helper

This reuses your existing `define_places` / constants data so there is no duplication.

```python
# In chat_service.py — import at top:
from luxscale.lighting_calc.constants import define_places

_PLACE_CANONICAL_MAP = {
    "Factory":    ("Factory",    200, 0.4, 20),
    "Warehouse":  ("Warehouse",  100, 0.4, 20),
    "Office":     ("Office",     500, 0.6, 80),
    "Classroom":  ("Classroom",  300, 0.6, 80),
    "Retail":     ("Retail",     500, 0.4, 80),
    "Corridor":   ("Corridor",   100, 0.4, 40),
}

def _standard_targets_for_place(
    place_name: str,
) -> Tuple[float, float, float]:
    """Return (target_lux, Uo_min, CRI_min) for a canonical place name."""
    row = _PLACE_CANONICAL_MAP.get(place_name)
    if row:
        return row[1], row[2], row[3]
    return 200.0, 0.4, 20.0   # safe industrial default
```

> **Alternative:** Load this from `standards_cleaned.json` instead of hardcoding. That's cleaner long-term — see Note at end of document.

---

### Step 4 — Add `_calc_fixture_options(area, h, target_lux)` — the core math

This is the lumen method: `N = (E × A) / (Φ × UF × MF)`

```python
_TYPICAL_FIXTURE_FAMILIES = [
    # (label, lumens_per_fixture, power_W, typical_UF)
    ("LED Highbay 150W",  18000, 150, 0.65),
    ("LED Highbay 100W",  12000, 100, 0.65),
    ("LED Panel 40W",      4000,  40, 0.60),
    ("LED Batten 36W",     3600,  36, 0.58),
    ("LED Lowbay 60W",     7200,  60, 0.62),
]

_DEFAULT_MF = 0.80

def _calc_fixture_options(
    area: float,
    height: float,
    target_lux: float,
) -> List[Dict]:
    """
    Run lumen-method for each fixture family.
    Return list of result dicts sorted by fixture count ascending.
    Filter families appropriate for height.
    """
    results = []
    for label, lumens, power_w, uf in _TYPICAL_FIXTURE_FAMILIES:
        # Height gate: highbays for H>=5m, panels/battens for H<5m
        if "Highbay" in label and height < 5.0:
            continue
        if ("Panel" in label or "Batten" in label) and height > 6.0:
            continue

        mf = _DEFAULT_MF
        flux_per_fixture = lumens * uf * mf
        if flux_per_fixture <= 0:
            continue

        n_exact = (target_lux * area) / flux_per_fixture
        n = int(n_exact) + (1 if n_exact % 1 > 0 else 0)   # ceiling

        achieved_lux = round((n * lumens * uf * mf) / area, 1)
        total_kw = round((n * power_w) / 1000, 2)
        lux_per_m2 = round(achieved_lux / max(area, 1), 2)

        results.append({
            "label":         label,
            "fixtures":      n,
            "lumens":        lumens,
            "power_w":       power_w,
            "achieved_lux":  achieved_lux,
            "total_kw":      total_kw,
            "watts_per_m2":  round((n * power_w) / area, 1),
        })

    results.sort(key=lambda r: r["fixtures"])
    return results[:3]   # show at most 3 options
```

---

### Step 5 — Add `_format_local_calc_answer(...)` — render the summary

Keep it short. One header line, a compact table or bullet list, and one action line.

```python
def _format_local_calc_answer(
    l, w, h, area, place_name, target_lux, uo_min,
    options: List[Dict],
    lang: str,
) -> str:
    lines = []

    if lang == "ar":
        lines.append(
            f"🏭 الغرفة: {l:g}×{w:g}×{h:g} م | المساحة: {area:g} م² | "
            f"النوع: {place_name} | الإضاءة المطلوبة: {target_lux:.0f} lx"
        )
        lines.append("")
        lines.append("خيارات التركيبات (حساب تقريبي بطريقة التدفق الضوئي):")
        for opt in options:
            lines.append(
                f"  • {opt['label']}: **{opt['fixtures']} تركيبة** "
                f"→ {opt['achieved_lux']} lx | {opt['total_kw']} kW "
                f"| {opt['watts_per_m2']} W/m²"
            )
        lines.append("")
        lines.append(
            "للحصول على نتائج دقيقة مع بيانات IES وتوزيع مكاني كامل، "
            "افتح حاسبة LuxSCale واختر التركيبة المناسبة."
        )
    else:
        lines.append(
            f"Room: {l:g}×{w:g}×{h:g} m | Area: {area:g} m² | "
            f"Type: {place_name} | Target: {target_lux:.0f} lx (EN 12464-1, Uo≥{uo_min})"
        )
        lines.append("")
        lines.append("Fixture options (lumen-method estimate):")
        for opt in options:
            lines.append(
                f"  • {opt['label']}: **{opt['fixtures']} fixtures** "
                f"→ {opt['achieved_lux']} lx | {opt['total_kw']} kW "
                f"| {opt['watts_per_m2']} W/m²"
            )
        lines.append("")
        lines.append(
            "For IES-backed accuracy and spatial layout, open LuxSCale "
            "and pick your fixture model."
        )

    return "\n".join(lines)
```

---

### Step 6 — Extend `_is_fixture_count_intent()` to cover more natural phrasings

The user typed *"how many fixtures i need in factory with dimensions 80×90×4"* — make sure every variant matches.

```python
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
    # natural dimension-first phrasings
    "fixtures.*factory",
    "fixtures.*office",
    "fixtures.*warehouse",
    "fixtures.*room",
    "need.*light.*factory",
    "need.*light.*room",
)

def _is_fixture_count_intent(question: str) -> bool:
    qn = _normalize_text(question)
    if not qn:
        return False
    # literal substring markers
    for m in _FIXTURE_INTENT_MARKERS:
        if "*" not in m and m in qn:
            return True
    # regex markers
    import re
    for m in _FIXTURE_INTENT_MARKERS:
        if "*" in m and re.search(m.replace("*", ".*"), qn):
            return True
    return False
```

---

### Step 7 — Connect to the `ask()` dispatcher (already wired)

The current dispatcher in `ask()` already does:

```python
planning_out = _local_fixture_count_guidance(raw, reply_language=reply_language)
if planning_out is not None:
    return {**base, **planning_out}
```

**No change needed here.** The function just needs to return richer content.

---

### Step 8 — Handle the "no fixture options match height" edge case

If `_calc_fixture_options` returns an empty list (unusual height range), fall back to a graceful message instead of a blank table:

```python
if not options:
    options_text = (
        "No standard fixture family matched the given height. "
        "Please open LuxSCale and select a custom fixture."
    )
else:
    options_text = _format_options_block(options, lang)
```

---

## File Change Summary

| File | Change |
|---|---|
| `luxscale/chat_service.py` | Add helpers: `_missing_required_fields`, `_standard_targets_for_place`, `_calc_fixture_options`, `_format_local_calc_answer`. Extend `_local_fixture_count_guidance` and `_is_fixture_count_intent`. |
| No other file changed | All logic is self-contained in `chat_service.py`. |

---

## Example Result for the Factory Query

**Input:** `how many fixtures i need in factory with dimensions 80*90*4`

**Output (source: `planning_local`):**
```
Room: 80×90×4 m | Area: 7200 m² | Type: Factory | Target: 200 lx (EN 12464-1, Uo≥0.4)

Fixture options (lumen-method estimate):
  • LED Batten 36W: 312 fixtures → 200.0 lx | 11.23 kW | 1.6 W/m²
  • LED Lowbay 60W: 249 fixtures → 201.1 lx | 14.94 kW | 2.1 W/m²
  • LED Panel 40W: 375 fixtures → 200.0 lx | 15.0 kW | 2.1 W/m²

For IES-backed accuracy and spatial layout, open LuxSCale and pick your fixture model.
```

> Note: At H=4 m, highbay fixtures are filtered out automatically.

---

## Optional Enhancement (Phase 2)

Instead of hardcoding `_TYPICAL_FIXTURE_FAMILIES`, pull from your real fixture catalog:

```python
from luxscale.fixture_catalog import load_fixture_map_document

def _calc_fixture_options_from_catalog(area, height, target_lux):
    doc = load_fixture_map_document()
    families = doc.get("fixtures", [])
    # filter by height range, compute N for each, return top 3
```

This makes chat answers consistent with what the full calculator uses, and automatically updates when you add new SC fixtures.

---

## Notes

- **MF = 0.80** is a conservative default for industrial spaces. You can expose it as an optional chat parameter later.
- **UF = 0.6–0.65** is typical for direct luminaires in a clean factory. If the user mentions a dirty or dusty environment, lower it to 0.55.
- Keep the answer **short** — 6–10 lines max. The chat is not the report; it is the gateway to the full calculator.
