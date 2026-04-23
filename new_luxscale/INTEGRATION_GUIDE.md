# LuxScale × IES Modal — Integration Guide
*What to copy, what to replace, and where*

---

## Files delivered

| File | Action |
|------|--------|
| `ies_routes.py` | **Replace** your existing `ies_routes.py` entirely |
| `ies_analyzer.py` | Already in your project — **keep as-is** (no change needed) |
| `polar_modal_snippet.html` | **Replace** your polar modal block in `result.html` |

---

## Step 1 — `ies_routes.py`

Replace the whole file. Key improvements over the version you had:

- **`/ies/upload`** now returns two extra keys in every response:
  ```json
  {
    "session_id": "abc12345",
    "filename":   "SC_FLOOD_150W.ies",
    "customer": {            ← NEW: only what the customer needs
      "total_lumens":    24000,
      "beam_angle_deg":  120.0,
      "field_angle_deg": 168.5,
      "peak_candela":    7639,
      "declared_lumens": 24000,
      "lor_pct":         100.0,
      "shape":           "rectangular with luminous sides",
      "symmetry":        "Asymmetric / full azimuth (0–360°)",
      "fixture_width_m": 0.35,
      "fixture_length_m":0.55,
      "fixture_height_m":0.12,
      "horizontal_angles":[0,45,...],
      "num_vertical": 37,
      "num_horizontal": 5
    },
    "ies_data": { ... }      ← raw matrix for Three.js
  }
  ```

- **`/ies/panorama`** now accepts rectangular rooms:
  - `room_w` — room width (m)
  - `room_l` — room length (m)  
  - `room_h` — ceiling height (m)
  - `fixture_h` — luminaire mounting height (m) — defaults to 80% of ceiling
  - These come from your LuxScale place data, not user sliders.

- **`/ies/plot/polar`** — unchanged endpoint, same URL.

- **`/ies/ies_data`** — raw candela JSON for Three.js, unchanged.

Register the blueprint in your `app.py` / `main.py`:
```python
from ies_routes import ies_bp
app.register_blueprint(ies_bp)
```
*(If you already have this line, nothing changes.)*

---

## Step 2 — `result.html`

### 2a. In `<head>` — add Pannellum CSS
```html
<link rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.css">
```

### 2b. Remove your old polar modal
Find and delete everything between your old modal's opening `<div>` and its
closing `</div>` (including both tags).

### 2c. Paste `polar_modal_snippet.html`
Paste the entire content of `polar_modal_snippet.html` just before `</body>`.

It contains:
- The modal HTML
- All CSS (scoped with `ies-` prefix — won't conflict with your styles)
- Three.js `<script>` tag *(remove if already loaded in your project)*
- Pannellum `<script>` tag
- All JavaScript

### 2d. Trigger the modal from your "See Polar Curve" button

**After your IES file upload** (wherever you call `/ies/upload`), store the
session id and call `iesPopulateSpecs()`:

```javascript
// When the IES file upload completes:
const data = await fetch('/ies/upload', { method:'POST', body: formData })
                   .then(r => r.json());

const iesSid = data.session_id;

// Populate the modal specs immediately (no modal shown yet):
iesPopulateSpecs(data.customer, data.filename);
```

**On your "See Polar Curve" button click:**

```javascript
// placeData comes from your LuxScale project/place form fields:
const placeData = {
  room_w: parseFloat(document.getElementById('place-width').value),   // metres
  room_l: parseFloat(document.getElementById('place-length').value),  // metres
  room_h: parseFloat(document.getElementById('place-height').value),  // metres
};

openIESModal(iesSid, placeData, 'SC Flood Light 150W');
//            ↑ sid    ↑ place dims  ↑ product name for header
```

`openIESModal` opens the modal, pre-fills all the room sliders from `placeData`,
and switches to the Specs tab automatically.

---

## What each tab shows

### 📋 Specs (default tab)
**Customer-facing tiles — NO jargon:**

| Tile | Value |
|------|-------|
| Total Lumens | Integrated lm from photometric data |
| Beam Angle | 50% peak (half-power angle) |
| Field Angle | 10% peak (full spread angle) |
| Peak Intensity | Peak candela |

Below the tiles: a collapsed "Technical data ▾" section shows LOR, shape,
symmetry, fixture dimensions — for installers who want it.

### 📐 Polar Curve
matplotlib polar diagram from the accurate `ies_analyzer.py` engine.
H-plane selector + scale (linear / sqrt / log) + beam/field lines.

### 💡 Light Sim
360° equirectangular room panorama using real IES candela data.  
Room dimensions are pre-filled from your place data.  
Drag to look around, scroll to zoom (Pannellum viewer).

### 🌐 3-D View
Three.js interactive candela sphere.  
Drag to rotate, scroll to zoom, wireframe toggle.

---

## Variable name mapping (LuxScale → modal)

Your place form field IDs might differ. Map them in your button handler:

| LuxScale field | What to pass |
|---------------|-------------|
| Room/space width | `room_w` (metres) |
| Room/space length | `room_l` (metres) |
| Room/space height / ceiling | `room_h` (metres) |

If your project stores dimensions in another unit (cm, ft), convert before
passing: `room_w: cm_value / 100`.

---

## Notes

- The `panorama` endpoint accepts both GET and POST.  
  The modal uses GET with query params — no change needed on your server.

- All modal JS is namespaced with `ies` prefix (variables: `_ies...`,  
  functions: `ies...`) so it won't conflict with your existing JS.

- Three.js r128 is loaded from Cloudflare CDN. If your project already loads  
  Three.js, remove the first `<script>` tag in the snippet.
