# Cleanup Quarantine Manifest

**Scope:** Files to move into `tempDel/` (preserving directory structure) before final deletion.
**Method used:** Full-repo `rg` scan for basenames; SHA256 for dedup claims; live-tree cross-check.
**Status:** Nothing moved yet — review this list, then quarantine at your pace.

> Convention for moving: recreate the file's original path under `tempDel/`, e.g.
> `assets/instagram-logo.svg` → `tempDel/assets/instagram-logo.svg`.
> This makes restore a one-line `Move-Item` back to the original location.

---

## 🔴 DO NOT MOVE

These are actively imported/served/linked in the live tree. Keep them exactly where they are.

- `app.py`, `result.html`, `index2.html`, `index3.html`, `index4.html`, `generate_report.py`, `standards_routes.py`, `fixtures_routes.py`
- `luxscale/` (entire tree)
- `api/` (Flask + PHP live endpoints)
- `admin/` (dashboard)
- `assets/fixture_map_SC_IES_Fixed_v3.json` (active fixture map)
- `assets/fixture_ies_catalog_SC_IES_Fixed_v3.json`
- `assets/fixtures_online.json`
- `assets/app_settings.json`, `assets/dashboard_config.json`
- `assets/fixed_responses.json`
- `assets/standard-display.js`, `assets/standards-picker.js`
- `assets/logo.svg`, `assets/SClogo.svg`, `assets/favicon.svg`, `assets/AI icon.svg`
- `assets/pdfBG.png`, `assets/pdfBG.svg`
- `assets/myvideo.mp4` (used by `index2/3/4/5.html`, `result.html`)
- `standards/standards_cleaned.json` (primary standards DB)
- `standards/aliases_upgraded.json`
- `standards/standards_keywords_upgraded.json`
- `ies-render/examples/SC_IES_Fixed_v3/` (active IES files — `merged_ies_relative_map()` scans this directory at runtime, not just the map JSON)
- `ies-render/ies_json/` (~207 MB — runtime photometry blobs consumed by `luxscale/ies_json_loader.py`)
- `snapshots/` (referenced by `luxscale/gemini_manager.py`, `/api/ai/snapshots/*`)
- `docs/` (served by `app.py` at `/docs`)
- `tools/` (`check_dictionaries.py` used for QA)
- `chat-with-luxSCale.html` (linked from `assets/js/script.js:330`, `app.py:283`)
- `openies.html` (opened from `result.html:1330`)
- `draw.html` (linked from `index2.html:416`, `index4.html:478`, `result.html:285,1356`)
- `generate_fixed_responses.py` (thin wrapper used by `luxscale/ai_routes.py:370`)
- `.env.example`, `.gitignore`, `.cursor/`, `.claude/`, `Procfile`, `requirements.txt`
- `README.md`, `CLAUDE.md`, `GEMINI.md`, `DEPLOY.md`, `PYTHON_TECHNICAL_DESCRIPTION.md`, `STRUCTURE.md`, `tool_guide.md`, `development_plan/`, `documentation/`

---

## 🟢 SAFE_TO_QUARANTINE — zero code references

~38 files, ~12 MB combined. High confidence: no `rg` match anywhere in the live tree.

### A. Standards duplicates and archives (223 KB)

| Source path | Size | Rationale | Restore risk |
|-------------|------|-----------|--------------|
| `standards/standards_improved.json` | 147,083 B | **Byte-identical** to `standards_cleaned.json` (SHA256 `ECF9DA5D…`). Zero references. | None. |
| `standards/standards_cleaned_backup.json` | 43,869 B | Older snapshot of standards DB. Zero references. | Historical only. |
| `standards/standards.rar` | 32,180 B | Archive backup. Zero references. | Historical only. |

### B. Assets orphans (~11.0 MB — instagram dominates)

| Source path | Size | Rationale |
|-------------|------|-----------|
| `assets/instagram-logo.svg` | **10,900,358 B (10.9 MB)** | Oversized SVG (should be a few KB). Live pages use `images/instagram-111.svg` instead. Zero references. |
| `assets/facebook-logo.svg` | 4,254 B | Live pages use `images/facebook-109.svg`. Zero references. |
| `assets/linkedin-logo.svg` | 2,663 B | Same pattern. Zero references. |
| `assets/hero.svg` | 4,857 B | Zero references. |
| `assets/arrow.svg` | 167 B | Zero references. |
| `assets/fixtures.rar` | 14,417 B | Archive; live catalog is `fixtures_online.json`. Zero references. |

### C. Root legacy Python / txt / bat / css / js (~250 KB)

| Source path | Size | Rationale |
|-------------|------|-----------|
| `app-old.py` | 45,156 B | Superseded by `app.py`. Not imported anywhere. |
| `lighting_calc_old.py` | 14,165 B | Legacy Tkinter GUI. Docs mention it; no runtime import. |
| `app_py_patch.txt` | 226 B | Stale patch snippet. |
| `app_py_patches.txt` | 5,257 B | Stale patch snippets. |
| `env_additions.txt` | 303 B | Stale `.env` notes. |
| `gitignore_additions.txt` | 90 B | Stale `.gitignore` notes. |
| `upgit.bat` | 72 B | Personal git helper. |
| `gemini_key_tester.py` | 2,465 B | Dev-only key tester, mentioned only in `GEMINI.md:21`. |
| `spritespin.min.js` | 28,872 B | 360° viewer library, only referenced in `STRUCTURE.md`. Not linked from any live HTML. |
| `style.css` | 33,077 B | Root copy. Live `index.html` uses `assets/css/style.css`. |

### D. Root legacy HTML (~1.4 MB)

| Source path | Size | Rationale |
|-------------|------|-----------|
| `draw_v4.html` | 107,970 B | Version snapshot; live link is `draw.html`. |
| `draw_v5.html` | 119,887 B | Version snapshot. |
| `draw_v6.html` | 119,887 B | Version snapshot. |
| `draw_v7.html` | 119,138 B | Version snapshot. |
| `draw_v8.html` | 124,957 B | Version snapshot. |
| `draw_v9.html` | 125,183 B | Version snapshot (comment reference in `core-integration.js:168` only). |
| `draw_v10.html` | 130,985 B | Version snapshot (docs only). |
| `sc_draw (2).html` | 50,580 B | Windows "(2)" duplicate scratch. |
| `ies_inter.html` | 195,263 B | Zero references anywhere. |
| `MERGE-PLAN.html` (root) | 20,037 B | Duplicate of `merge/MERGE-PLAN.html`. |
| `res.html` | 3,657 B | Legacy result variant. |
| `chat.html` | 50,916 B | Superseded by `chat-with-luxSCale.html`. |
| `olc-chat.html` | 51,776 B | Older chat shell. |
| `ai_panel_for_result_html.html` | 11,791 B | Dev test harness; panel is integrated in `result.html`. |

### E. Scratch directories (~1.5 MB)

| Source path | Size | Rationale |
|-------------|------|-----------|
| `merge/` | 34 files, 1.28 MB | Scratch merge tree; no imports; duplicates marketing pages. |
| `pipeline/` | 1 file, 30 KB | Internal explorer HTML; docs only. |
| `plan/` | 1 file, 19 KB | Docs only. |
| `guide/` | 6 files, 158 KB | Duplicate `ies_routes.py` snippets. |
| `uniformity/` | 6 files, 35 KB | Docs only. |

---

## 🟡 NEEDS_HUMAN_REVIEW — decide before moving

These are unused *today* but have "maybe still needed" flags. Move any of them individually only after confirming.

| Source path | Size | Why review needed |
|-------------|------|-------------------|
| `assets/logo-Light.svg` | 33,147 B | Unused today; plausible brand asset. |
| `assets/fixture_map.json` | 19,511 B | Fallback for legacy `SC_FIXED` env switch (`ies_dataset_config.py:35-37`) + `ies_routes.py:184`. Safe **only** if you formally retire that switch. |
| `assets/fixture_ies_catalog.json` | 3,003 B | Legacy pair to fixture_map.json. Same caveat. |
| `results.html` | 14,978 B | Legacy PDF result variant. Chain: `results.html` → `spec.html` → `maha/3d_model.html`. |
| `spec.html` | 8,264 B | Only reached from `results.html:431`. Move both together. |
| `online-result.html` | 22,281 B | Legacy variant → `maha/3d_model.html`. |
| `charger.html` | 33,889 B | Docs mark "active"; no inbound HTML/JS reference found. |
| `index5.html` | 34,219 B | Prototype using `core-integration.js`; no inbound links. |
| `index.html` | 143,947 B | Legacy mega-page still linked from nav on `about.html`, `contact.html`, etc. **Do not move without also updating those nav links.** |
| `new_luxscale/` | 39 files, 377 KB | Parallel `luxscale/` copy. Zero `import new_luxscale` in live code. Diff against `luxscale/` before moving. |
| `luxscale_deploy/` | 3 files, 95 KB | Parallel `app.py`/`generate_report.py` copy. Confirm no external deploy pipeline points at it. |
| `maha/` (partial) | 331 files, 14.6 MB | Mixed. Live: `maha/3d_model.html` (used by `result.html:1012`, `openies.html:511`). Candidates to quarantine inside `maha/`: `maha/app.py`, `maha/lighting_calc.py`, unused HTML demos. **Don't move the whole tree.** |
| `ies-render/examples/*.rar` (3 files) | Various | Tool inputs; verify not used by `ies-render/batch.py`. |
| `ies-render/examples/SC_FIXED/`, `ies-render/SC-Database/`, `ies-render/SC-ies/`, `ies-render/ies_json/*_legacy/` (if any) | Various | Legacy IES subtrees. Only quarantine after confirming v3-only deployment; `sc_ies_scan.scan_examples_sc_ies_v3()` currently scans the whole `examples/SC_IES_Fixed_v3/` folder — do NOT move any `.ies` file under there. |

---

## Suggested phased quarantine order

Each phase is independently safe; stop at any point.

### Phase 1 — Free 10.9 MB in one move (lowest risk)
- `assets/instagram-logo.svg`

### Phase 2 — Standards & assets dedup (223 KB)
- `standards/standards_improved.json`
- `standards/standards_cleaned_backup.json`
- `standards/standards.rar`
- `assets/fixtures.rar`, `assets/facebook-logo.svg`, `assets/linkedin-logo.svg`, `assets/hero.svg`, `assets/arrow.svg`

### Phase 3 — Root Python / txt / bat / css / js (~250 KB)
- `app-old.py`, `lighting_calc_old.py`, `app_py_patch.txt`, `app_py_patches.txt`, `env_additions.txt`, `gitignore_additions.txt`, `upgit.bat`, `gemini_key_tester.py`, `spritespin.min.js`, `style.css`

### Phase 4 — Root legacy HTML (~1.4 MB)
- All `draw_v4.html` – `draw_v10.html`
- `sc_draw (2).html`, `ies_inter.html`, `MERGE-PLAN.html` (root), `res.html`, `chat.html`, `olc-chat.html`, `ai_panel_for_result_html.html`

### Phase 5 — Scratch directories (~1.5 MB)
- `merge/`, `pipeline/`, `plan/`, `guide/`, `uniformity/`

### Phase 6 (optional, needs review) — Yellow list
- Duplicate trees: `new_luxscale/`, `luxscale_deploy/`
- Legacy pages: `results.html`, `spec.html`, `online-result.html`, `charger.html`, `index5.html`
- Retire `index.html` **only after** updating nav on `about.html`, `contact.html`, `brand.html`, `career.html`, `contact.html`, `help.html`, `news.html`, `privacy.html`, `terms.html`, `downloads.html`

---

## How to move (PowerShell one-liners)

Each command creates the parent directory under `tempDel/` and moves the file.

```powershell
# Single file example (Phase 1)
New-Item -ItemType Directory -Force -Path tempDel\assets | Out-Null
Move-Item assets\instagram-logo.svg tempDel\assets\instagram-logo.svg

# Directory example (Phase 5)
New-Item -ItemType Directory -Force -Path tempDel | Out-Null
Move-Item merge tempDel\merge
```

### Restore any file with the reverse move

```powershell
Move-Item tempDel\assets\instagram-logo.svg assets\instagram-logo.svg
```

## After each phase — smoke test

```powershell
python -c "import app"                                  # Flask imports cleanly
python -c "from luxscale.lighting_calc import calculate_lighting"
# Then hit the live pages: /calculate, /pdf, /api/report/full via Postman
```

If anything breaks, `Move-Item tempDel\<path> <original path>` and file an issue against this manifest so the next round of cleanup skips it.

---

## Totals

| Bucket | File count | Total size |
|--------|-----------:|-----------:|
| SAFE_TO_QUARANTINE | ~38 files (individual) + 5 scratch dirs | ~12.0 MB (green) + 1.5 MB (scratch) = **~13.5 MB** |
| NEEDS_HUMAN_REVIEW | ~11 files + 4 dirs | ~240+ MB (mostly `ies-render/` legacy subtrees + partial `maha/`) |
| DO_NOT_TOUCH | Live core | — |
