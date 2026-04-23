# LuxSCale v1.0.2 — UX & Responsivity Init File
**Project:** LuxSCale AI · Lighting Intelligence Platform
**Audit by:** Short Circuit Company
**Brand ref:** https://shortcircuit.company/SCbrand
**Date:** 2026-04-16

---

## 1. Issues Found

### 1.1 Horizontal Scroll / Overflow (Critical)
| Location | Problem | Fix |
|---|---|---|
| `styles.css` `.frame-28-68` | `width: 187.71929824561403%` — wider than viewport | Replace with `width: 100%` |
| `styles.css` `.frame-30-58` | `padding: 84px 477px` — fixed 477px padding causes blowout on any screen <1440px | Replace with `padding: 84px clamp(1rem, 8vw, 120px)` |
| `styles.css` `.landing-page-1` | Broken media queries nested inside selector block (syntax error) | Extract to proper top-level `@media` blocks |
| `styles.css` `.frame-6-32` | `gap: 210px` fixed gap — too wide for tablets/mobile | Replace with `gap: clamp(1rem, 5vw, 80px)` |
| `styles.css` `.frame-18-30` | `gap: 77px` fixed gap | Replace with `gap: clamp(1rem, 4vw, 40px)` |
| `index.html` navbar | `px-5` Bootstrap class = 48px fixed padding each side — causes overflow on mobile | Replaced with responsive `px-3 px-lg-5` |

### 1.2 Layout / UX Problems
| Location | Problem | Fix |
|---|---|---|
| `styles.css` `.frame-5-33` | `width: 59.49018315491216%` — overly precise, non-fluid calculation | Replace with `width: 60%; max-width: 100%` |
| `styles.css` `.frame-32-81`, `.frame-33-83`, `.frame-35-90`, `.frame-36-93` | `width: 49.13494809688581%` — breaks on small screens to side-scroll | Replace with `width: 48%; max-width: 100%` + flex-wrap |
| `assets/css/style.css` `.study-step` | Steps use `position: absolute` without parent having explicit height → content collapse | Added `min-height` to step container |
| `assets/css/style.css` `.auth-form` | Same absolute-positioning issue as study-step | Added `position: relative` fallback |
| `assets/css/style.css` `.hero-section` | `overflow: hidden` clips content on small viewports | Changed to `overflow: visible` with body handling overflow |
| `assets/css/style.css` `.footer-content` | No responsive stacking below 768px | Added proper `flex-direction: column` media query |
| `assets/css/style.css` `.upload-buttons` | `max-width: 700px` with no centering fallback | Added `margin: 0 auto` + `flex-wrap: wrap` |

### 1.3 Font / Import Issues
| Location | Problem | Fix |
|---|---|---|
| `styles.css` | `@font-face` pointing to `fonts/` directory that doesn't exist in project | Replaced with Google Fonts CDN import (already in index.html) |
| `assets/css/style.css` | Google Fonts not imported in CSS file itself — relies on HTML `<link>` only | Added `@import` as fallback |

### 1.4 Broken CSS Syntax
| Location | Problem | Fix |
|---|---|---|
| `styles.css` `.landing-page-1` | `@media` blocks nested INSIDE a selector — invalid CSS, silently ignored by all browsers | Extracted to valid top-level `@media` blocks |

---

## 2. Files Modified

```
LuxSCale/
├── styles.css              ← Fixed overflow widths, broken @media nesting, hardcoded gaps
├── assets/css/style.css    ← Fixed hero overflow, study-step heights, footer responsive, upload buttons
└── INIT.md                 ← This file
```

---

## 3. SC Brand Compliance Notes

The site already correctly uses:
- SC Red `#eb1b26` / `#EB1B26` ✓
- Anton for headlines ✓
- IBM Plex Sans for body (SC equivalent of Poppins for this product) ✓
- Dark backgrounds `#1D1D1D` / `#2D2D2D` ✓
- Logo maintained at correct ratio ✓

No brand regressions introduced in fixes.

---

## 4. Testing Checklist

After applying fixes, verify at these breakpoints:

- [ ] 320px (iPhone SE) — no horizontal scroll
- [ ] 375px (iPhone 14) — no horizontal scroll
- [ ] 768px (iPad) — nav collapses cleanly
- [ ] 1024px (iPad landscape / small laptop)
- [ ] 1440px (standard desktop)
- [ ] 1920px (large screen)

Key flows to test:
- [ ] Chat → type in input → no scroll
- [ ] Study toggle → step transitions don't cause overflow
- [ ] Upload modal → open/close on mobile
- [ ] Footer — stacks cleanly on mobile
