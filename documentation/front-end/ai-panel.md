# AI Analysis Panel — Front-end

> **Files:** `result.html` (integrated panel) · `ai_panel_for_result_html.html` (standalone test)  
> **Brand:** Short Circuit · `#eb1b26` red · quality badge colour-coded by score

---

## 1. Panel Location in result.html

The AI panel renders inside `result.html` after the user views a study result. It is triggered either:
- **Automatically** on page load (if auto-analyze is enabled in settings)
- **Manually** by clicking the "Analyse with AI" button

The panel is **per-study** — it analyzes the full study payload associated with the current `?token=` in the URL.

---

## 2. API Call

```javascript
// Called from result.html
const response = await fetch(`${API_BASE}/api/ai/analyze`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ token: studyToken })
});
const data = await response.json();
```

The panel sends **only the token** — the server loads the full study payload and builds the AI prompt server-side.

---

## 3. Panel UI Sections

### Quality score badge

Colour-coded by score range:

| Score range | Badge colour | Label |
|-------------|-------------|-------|
| 85–100 | Green (`#27ae60`) | Excellent |
| 65–84 | Orange (`#d68910`) | Good |
| 40–64 | Red (`#c0392b`) | Needs improvement |
| 0–39 | Dark red | Critical issues |

Displays: score number, confidence percentage, source label.

### Source meta-row

```
Source: Gemini — account_1_free    Confidence: 90%
```

If `source === "snapshot"`, a note is shown: "Showing last approved analysis (AI unavailable)."  
If `source === "default"`, a note indicates no AI is configured yet.

### Issues list

Each issue card shows:

```
● HIGH   Average Illuminance (Em)
         Calculated lux is 2.6% below required 500 lux
         → Increase fixture count to 26 or use higher efficacy
```

Severity mapping to CSS classes:

| Severity | Background | Text colour | Border |
|----------|------------|-------------|--------|
| `high` | `#fdecea` | `#c0392b` | Left 3px red |
| `medium` | `#fef9e7` | `#d68910` | Left 3px orange |
| `low` | `#eaf4fb` | `#2471a3` | Left 3px blue |

If `issues.length === 0`, shows a green "No issues found" message.

### Suggestions list

Bullet list of engineering tips. Each item is 13px body text with bottom border separator.

### Summary box

One-sentence summary in a light blue background box (`#f8f8ff`).

### Approve & Save button

```html
<button class="approve-btn" onclick="approveFix()">
  ✓ Approve & Save as Baseline
</button>
```

On click:
1. Calls `POST /api/ai/approve-fix` with `{ analysis: currentAnalysis, token: studyToken }`
2. On success: button label changes to "✓ Saved as Baseline", button disabled
3. On failure: error message below button

---

## 4. `ai_panel_for_result_html.html` — Test Harness

This standalone file allows testing the AI panel independently from `result.html`.

### Usage

1. Open the file in a browser
2. Enter a study token (or use the default test token)
3. Set Flask URL (pills for common dev ports)
4. Click "Run AI Analysis"

This is used during development to test AI responses without needing to run the full calculator flow.

### Key differences from production panel

- Standalone page, not embedded in result.html
- Token input is editable
- Flask URL is configurable via pills
- Shows raw JSON response in a collapsible debug section

---

## 5. Error States

| Error | Panel behaviour |
|-------|----------------|
| Token not found (404) | "Study not found" message |
| No results in payload | "No results to analyze" message |
| All AI unavailable + no snapshot | Default message with suggestion to configure AI |
| Network error | "Could not connect to server" with retry button |

---

## 6. Styling Reference

The AI panel uses inline styles consistent with the SC design system:

```css
--panel-bg:      #ffffff
--border-radius: 16px
--shadow:        0 4px 24px rgba(0,0,0,0.08)
--heading-font:  'Segoe UI', sans-serif  /* result.html uses Anton for headers */
--accent:        #534AB7  /* panel accent — purple, distinct from SC red */
--approve-green: #27ae60
```

> Note: The standalone test harness uses `#534AB7` purple as its accent colour. The integrated `result.html` panel follows the SC brand system (`#eb1b26`). When fully integrating the panel, align to SC red.

---

Next: [architecture-and-stack.md](./architecture-and-stack.md)
