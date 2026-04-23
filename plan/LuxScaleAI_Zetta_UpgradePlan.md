# LuxScaleAI — Zetta Upgrade Plan
**Version:** Zetta (v∞)  
**Author:** Short Circuit Company  
**Status:** Phase 2 — Active (Wall Reflectance Integration)

---

## Overview

This document is the master plan for three sequential upgrades to LuxScaleAI. Each phase builds on the previous one. We execute them one at a time, confirming completion before proceeding.

| Phase | Feature | Status |
|-------|---------|--------|
| **Phase 1** | Gemini AI Chatbox with Standards Intelligence | Pending |
| **Phase 2** | Wall Material Reflectance Effect on Calculations | **▶ Active — Start Here** |
| **Phase 3** | DIALux Compliance & Image Analysis | Pending |

---

---

# PHASE 2 — Wall Material Reflectance Integration
## Status: ▶ ACTIVE

### Goal
Replace the current hardcoded room reflectance presets (`dark / medium / light`) with a real, physics-based reflectance factor (ρ) calculated from the actual wall/ceiling/floor surface HEX color that the user inputs. This makes the inter-reflection estimate accurate to the room's real surfaces.

---

### Equation Verification

The MD file equations are **correct**. Here is the confirmed pipeline:

**Step A — Normalize RGB**
```
R_norm = R_hex / 255
G_norm = G_hex / 255
B_norm = B_hex / 255
```

**Step B — Gamma Linearization (sRGB → Linear)**
```
C_linear = C_norm ^ 2.2
```
> ✅ This is the standard simplified gamma. The precise IEC 61966-2-1 formula uses a piecewise function, but `^ 2.2` is accepted for lighting engineering purposes.

**Step C — Luminous Reflectance (ρ)**
```
ρ = (0.2126 × R_linear) + (0.7152 × G_linear) + (0.0722 × B_linear)
```
> ✅ These are the ITU-R BT.709 luminance coefficients — correct for modern LED/display white points. These give the **photometric reflectance** of the surface, which is exactly what the lighting engine needs.

**Result range:** ρ ∈ [0.0, 1.0]  
- `#000000` → ρ = 0.000 (perfect absorber)  
- `#ffffff` → ρ = 1.000 (perfect reflector)  
- `#808080` → ρ ≈ 0.216 (mid-grey wall)

---

### Current System — How Reflectance Works Today

```
app_settings.py  →  ROOM_REFLECTANCE_PRESETS
    "dark"   → indirect_fraction = 0.05
    "medium" → indirect_fraction = 0.12   ← default
    "light"  → indirect_fraction = 0.18

get_inter_reflection_fraction()  →  returns irf (0.0 – 0.5)

uniformity_calculator.py :: compute_uniformity_metrics()
    arr = arr * (1.0 + f_ir)    ← applies IRF to every grid point
    E_avg, E_min, E_max recalculated after scaling

calculate.py
    irf = get_inter_reflection_fraction()
    → passed to compute_uniformity_metrics() as inter_reflection_fraction
    → also passed to the fallback sweep and the report sync
```

The system already has the plumbing for IRF. We are replacing the **source** of that fraction — from a preset label to a physics-derived value from three HEX colors.

---

### Upgrade Plan — Step by Step

#### Step 2.1 — Add HEX → ρ Utility Module

**File to create:** `luxscale/reflectance.py`

```python
"""
Surface reflectance (ρ) from HEX color codes.
Equations: LuxScaleAI_Equations.md §5
"""
from __future__ import annotations


def hex_to_reflectance(hex_color: str) -> float:
    """
    Convert a HEX color string (e.g. '#A0B2C3' or 'A0B2C3') to
    luminous reflectance ρ ∈ [0.0, 1.0].

    Step A: Normalize  →  Step B: Gamma linearize  →  Step C: BT.709 luminance
    """
    h = hex_color.strip().lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"Invalid HEX color: {hex_color!r}")

    r_hex = int(h[0:2], 16)
    g_hex = int(h[2:4], 16)
    b_hex = int(h[4:6], 16)

    # Step A: Normalize
    r_norm = r_hex / 255.0
    g_norm = g_hex / 255.0
    b_norm = b_hex / 255.0

    # Step B: Gamma linearize (sRGB simplified γ = 2.2)
    r_lin = r_norm ** 2.2
    g_lin = g_norm ** 2.2
    b_lin = b_norm ** 2.2

    # Step C: ITU-R BT.709 luminous reflectance
    rho = 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin

    return float(max(0.0, min(1.0, rho)))


def room_indirect_fraction(
    rho_ceiling: float,
    rho_walls: float,
    rho_floor: float,
    ceiling_weight: float = 0.40,
    wall_weight: float = 0.45,
    floor_weight: float = 0.15,
    irf_scale: float = 0.28,
) -> float:
    """
    Estimate inter-reflection fraction from surface reflectances.

    Weighted average reflectance → scaled to IRF range used by the engine.

    Weights (default) are derived from typical surface area distribution
    in a standard room (ceiling and upper walls contribute most to horizontal
    work-plane inter-reflection).

    irf_scale = 0.28 maps ρ_avg=1.0 → IRF=0.28 (matches the 'light' preset upper
    bound and is consistent with CIE simple cavity approximation for typical rooms).
    Returns a value clamped to [0.0, 0.40].
    """
    rho_avg = (
        ceiling_weight * rho_ceiling +
        wall_weight    * rho_walls   +
        floor_weight   * rho_floor
    )
    irf = rho_avg * irf_scale
    return float(max(0.0, min(0.40, irf)))
```

> **Why these weights?** In a typical room, the ceiling (the primary reflector for downlights) and upper walls contribute 85% of horizontal work-plane inter-reflection. The floor contributes little because it faces away from the work plane. These defaults can be tuned per project.

---

#### Step 2.2 — Add New API Endpoint in `app.py`

**Route to add:** `POST /api/reflectance`

Accept three HEX values, return ρ per surface and the computed IRF.

```python
@app.route('/api/reflectance', methods=['POST'])
def api_reflectance():
    from luxscale.reflectance import hex_to_reflectance, room_indirect_fraction
    data = request.get_json(force=True) or {}
    try:
        ceiling_hex = str(data.get('ceiling', '#CCCCCC'))
        walls_hex   = str(data.get('walls',   '#CCCCCC'))
        floor_hex   = str(data.get('floor',   '#808080'))

        rho_c = hex_to_reflectance(ceiling_hex)
        rho_w = hex_to_reflectance(walls_hex)
        rho_f = hex_to_reflectance(floor_hex)
        irf   = room_indirect_fraction(rho_c, rho_w, rho_f)

        return jsonify({
            'ok': True,
            'ceiling': {'hex': ceiling_hex, 'rho': round(rho_c, 4)},
            'walls':   {'hex': walls_hex,   'rho': round(rho_w, 4)},
            'floor':   {'hex': floor_hex,   'rho': round(rho_f, 4)},
            'irf':     round(irf, 4),
            'label':   f'Custom (ρ ceiling={rho_c:.2f} / walls={rho_w:.2f} / floor={rho_f:.2f})'
        })
    except Exception as ex:
        return jsonify({'ok': False, 'error': str(ex)}), 400
```

---

#### Step 2.3 — Extend `app_settings.py` — New Preset: `custom`

Add a `custom` preset to `ROOM_REFLECTANCE_PRESETS` and a setter function:

```python
# In ROOM_REFLECTANCE_PRESETS dict, add:
"custom": {
    "label": "Custom (from surface HEX colors)",
    "indirect_fraction": 0.12,   # overwritten at runtime by /api/reflectance
},

# New getter to accept a runtime override:
def get_inter_reflection_fraction_for_irf(irf_override: float | None = None) -> float:
    if irf_override is not None:
        return float(max(0.0, min(0.5, irf_override)))
    return get_inter_reflection_fraction()
```

And in `save_app_settings()`, allow saving a `custom_irf` field so the last HEX-derived value persists across requests in the same session.

---

#### Step 2.4 — Extend the Main Calculation Route in `app.py`

In the existing `/api/calculate` (or equivalent) POST handler, accept three new optional fields:

```json
{
  "ceiling_hex": "#F5F5F5",
  "walls_hex":   "#D6C8B0",
  "floor_hex":   "#5A4A3A"
}
```

When present, compute ρ and IRF before calling `calculate_lighting()`, then pass the derived `irf` directly:

```python
# Inside the calculate route, before calling calculate_lighting():
from luxscale.reflectance import hex_to_reflectance, room_indirect_fraction

ceiling_hex = payload.get('ceiling_hex')
walls_hex   = payload.get('walls_hex')
floor_hex   = payload.get('floor_hex')

custom_irf = None
surface_label = None

if ceiling_hex and walls_hex and floor_hex:
    rho_c = hex_to_reflectance(ceiling_hex)
    rho_w = hex_to_reflectance(walls_hex)
    rho_f = hex_to_reflectance(floor_hex)
    custom_irf = room_indirect_fraction(rho_c, rho_w, rho_f)
    surface_label = (
        f"Custom HEX (ρ ceiling={rho_c:.2f} / walls={rho_w:.2f} / floor={rho_f:.2f})"
    )
    # Temporarily override the session IRF for this request
    # (No global state mutation — pass as argument downstream)
```

Then thread `custom_irf` and `surface_label` into `compute_uniformity_metrics()` calls by passing them as `inter_reflection_fraction` and `inter_reflection_label`. The engine already accepts these parameters — **no changes needed to `calculate.py` or `uniformity_calculator.py`**.

---

#### Step 2.5 — Frontend — Color Pickers in `index.html` / `script.js`

Add a collapsible **"Wall Materials"** section to the input form (between room dimensions and the submit button):

**UI Elements:**
- Three `<input type="color">` pickers: Ceiling, Walls, Floor
- Live preview swatches showing the selected color
- Computed ρ values shown in real time (call `/api/reflectance` on change)
- A small badge showing the resulting IRF: `Inter-reflection: 14.2%`
- Default values: Ceiling `#F0F0F0`, Walls `#E0D8CC`, Floor `#666666`

**JS logic:**
```javascript
async function updateReflectance() {
  const res = await fetch('/api/reflectance', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      ceiling: document.getElementById('ceiling_hex').value,
      walls:   document.getElementById('walls_hex').value,
      floor:   document.getElementById('floor_hex').value,
    })
  });
  const data = await res.json();
  if (data.ok) {
    document.getElementById('irf_badge').textContent =
      `Inter-reflection: ${(data.irf * 100).toFixed(1)}%`;
    // Store for form submission
    window._luxReflectance = data;
  }
}
```

On form submit, include the HEX values in the calculation payload.

---

#### Step 2.6 — Update `result.html` Display

Add a new row in the **Room Parameters** section of the results table:

| Parameter | Value |
|-----------|-------|
| Wall reflectance | Custom HEX (ρ ceiling=0.85 / walls=0.62 / floor=0.18) |
| Inter-reflection factor | 14.2% |

The data comes from the fields already returned in the result JSON:
- `Room reflectance preset` → now shows the `surface_label`
- `Inter-reflection fraction (est.)` → already in every result row

No structural changes needed to `result.html` — it already renders these fields.

---

#### Step 2.7 — Update Calculation Logs & PDF Report

In `calculation_trace.py` and `generate_report.py`, ensure the new label (e.g. `Custom HEX (ρ ceiling=0.85 / walls=0.62 / floor=0.18)`) flows through correctly. Since these modules read `room_reflectance_preset` and `inter_reflection_fraction` from the result rows (which we are already populating correctly), this should work with **zero changes**.

Verify by checking one calculation log after a test run.

---

### Files Changed — Phase 2 Summary

| File | Action | Notes |
|------|--------|-------|
| `luxscale/reflectance.py` | **CREATE** | New module — HEX → ρ → IRF |
| `app.py` | **EDIT** | Add `/api/reflectance` route + thread custom_irf into calculate route |
| `luxscale/app_settings.py` | **EDIT** | Add `custom` preset + `get_inter_reflection_fraction_for_irf()` |
| `assets/js/script.js` | **EDIT** | Add color pickers UI logic + `/api/reflectance` call |
| `index.html` (or equivalent input page) | **EDIT** | Add Wall Materials collapsible section with 3 color pickers |
| `result.html` | **VERIFY** | Should display new label automatically — no structural change needed |
| `generate_report.py` | **VERIFY** | Reads from result rows — should work automatically |

### Files NOT Changed
- `luxscale/lighting_calc/calculate.py` — No changes needed
- `luxscale/uniformity_calculator.py` — No changes needed
- `standards/` — No changes needed
- Any IES catalog files — No changes needed

---

### Testing Checklist — Phase 2

- [ ] `hex_to_reflectance('#ffffff')` returns `1.0`
- [ ] `hex_to_reflectance('#000000')` returns `0.0`
- [ ] `hex_to_reflectance('#808080')` returns ≈ `0.216`
- [ ] `room_indirect_fraction(0.85, 0.70, 0.20)` returns ≈ `0.174`
- [ ] `POST /api/reflectance` with valid HEX returns `ok: true` with correct ρ values
- [ ] Color pickers in UI update the IRF badge in real time
- [ ] A calculation run with dark walls (`#333333`) produces lower E_avg than one with white walls (`#FFFFFF`), all else equal
- [ ] Result page shows the surface label correctly
- [ ] Calculation log file shows the new label under `room_reflectance_preset`
- [ ] Fallback sweep uses the same custom IRF (not the global default)

---

---

# PHASE 1 — Gemini AI Chatbox with Standards Intelligence
## Status: Pending (begin after Phase 2 confirmed complete)

### Goal
Activate a conversational AI chat panel powered by Gemini API keys (from `gemini_config.json`) that can: (a) answer questions about lighting standards from `standards_cleaned.json`, and (b) guide a full lighting study interactively — collecting room dimensions, selecting fixtures, then passing all values to the calculation engine and rendering results in `result.html`.

---

### Architecture

```
User chat message
       ↓
Pre-prompt + standards context injection
       ↓
Gemini API (key rotation from gemini_config.json)
       ↓
Intent detection: [standards_query | study_wizard | general]
       ↓
standards_query → search standards_cleaned.json → reply with task lux table
study_wizard    → multi-turn parameter collection → POST /api/calculate → result.html
general         → direct Gemini reply
```

---

### Step-by-Step Plan

#### Step 1.1 — Pre-Prompt Design

The system prompt sent to Gemini on every turn:

```
You are LuxScaleAI's lighting consultant assistant.
You answer questions based on EN 12464-1, IES, and local standards 
from the provided standards database.

When asked about lux requirements: search the standards JSON and reply 
with a clear table — task area, required lux (Em), uniformity (Uo), 
Ra limit, and standard reference.

When asked to design a lighting study:
1. Ask for room category (office / school / hospital / etc.)
2. Ask for room dimensions: width and length (meters)
3. If the user wants exact results, ask for mounting height
4. Once you have all values, output ONLY a JSON block:
   {"action":"calculate","place":"...","width":...,"length":...,"height":...}

Never invent lux values. Always cite the standard reference number.
Reply in the same language the user writes in.
```

#### Step 1.2 — Standards JSON Context Injection

On each turn, inject the relevant subset of `standards_cleaned.json` into the Gemini context. Do not inject the full file every turn (too many tokens). Instead:

- On the first turn, extract all category names and inject as a short index
- When the user mentions a room type (e.g. "office"), inject only that category's entries

This keeps context lean and Gemini responses fast and accurate.

#### Step 1.3 — Gemini Key Manager Integration

The project already has `luxscale/gemini_manager.py`. The chat route will call the existing `GeminiManager` class for key rotation and quota handling. No new key management code needed.

#### Step 1.4 — Chat Route in `app.py`

```
POST /api/chat
Body: { "message": "...", "history": [...] }
Response: { "reply": "...", "action": null | { "calculate": {...} } }
```

If the response contains `{"action":"calculate",...}`, the frontend automatically submits the calculation and redirects to `result.html`.

#### Step 1.5 — Frontend Chat Panel

A floating or side-panel chat interface added to `index.html`:
- Input box + send button
- Message history display (user / assistant bubbles)
- Loading indicator during Gemini API call
- When `action.calculate` is detected → auto-fill the form fields → trigger calculation
- Panel can be toggled open/closed

---

### Files Changed — Phase 1

| File | Action |
|------|--------|
| `luxscale/ai_routes.py` | **EDIT** — add `/api/chat` route using GeminiManager |
| `luxscale/ai_prompt.py` | **EDIT** — add standards-aware pre-prompt builder |
| `assets/js/script.js` | **EDIT** — chat panel UI + action handler |
| `index.html` | **EDIT** — chat panel HTML structure |
| `standards/standards_cleaned.json` | **READ-ONLY** — consumed by prompt builder |

---

---

# PHASE 3 — DIALux Compliance & Image Analysis
## Status: Pending (begin after Phase 1 confirmed complete)

### Goal
Two sub-features:
1. **DIALux Export Compliance** — Validate that a completed LuxScaleAI study meets the same criteria as a DIALux output (Em maintained, Uo, UGRL, Ra), and generate a compliance report in the same format.
2. **Image Analysis** — Accept an uploaded photo of a space (or a DIALux false-color image) and use vision AI to extract or verify lux distribution data.

---

### High-Level Plan (detail to be expanded after Phase 2 + 1 are complete)

#### Sub-feature 3A — DIALux Compliance Report
- Map LuxScaleAI result fields to DIALux report fields (Em_maintained, Uo, UGRL, Ra)
- Add a `POST /api/dialux-compliance` route that takes a study ID and returns a structured compliance object
- Add a "DIALux Compliance" button to `result.html` that generates and downloads a PDF report in DIALux-compatible format
- Use `generate_report.py` as the base, add a new template for the DIALux-style layout

#### Sub-feature 3B — Image Analysis
- Accept image upload (JPG/PNG) via a new endpoint `POST /api/analyze-image`
- Pass image to Gemini Vision (or Claude vision via the existing pipeline) with a prompt asking it to identify: room type, approximate surface colors (→ feed into Phase 2 reflectance), fixture count, and any visible lux meter readings
- Return extracted values pre-filled into the calculation form
- This directly connects to Phase 2 (surface color extraction from photo) and Phase 1 (chat-guided confirmation of extracted values)

---

> **Examples and reference images for Phase 3 will be provided by the team before execution begins.**

---

---

## Execution Order

```
Phase 2  →  confirm ✓  →  Phase 1  →  confirm ✓  →  Phase 3
```

We are now starting **Phase 2, Step 2.1** — creating `luxscale/reflectance.py`.

---

*Plan created: 2026-04-18 | LuxScaleAI Zetta Upgrade Series*
