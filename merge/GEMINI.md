# LuxSCale AI - Project Instructions

## Project Overview
LuxSCale AI is a Lighting Intelligence Platform. The project focuses on high-quality UX, responsivity, and brand consistency.

## General Instructions
- **Responsivity First:** Always ensure changes do not introduce horizontal scroll or overflow issues. Use fluid layouts.
- **Brand Compliance:** Adhere to Short Circuit (SC) Brand guidelines:
  - Red: `#EB1B26`
  - Headlines: `Anton`
  - Body: `IBM Plex Sans`
  - Dark Backgrounds: `#1D1D1D`, `#2D2D2D`
- **Testing:** Always verify changes across breakpoints (320px to 1920px) as outlined in `INIT.md`.

## Coding Style & Standards
- **CSS Layout:**
  - **Use CSS Variables:** Always use the defined CSS variables in `styles.css` (e.g., `--font-family-anton`, `--text-white`) for consistency.
  - Prefer `clamp()`, `vw`, and `%` over fixed `px` values for padding, gaps, and widths.
  - Use `flex-wrap: wrap` for multi-item containers to ensure mobile compatibility.
  - Avoid overly precise percentage widths (e.g., `59.49%`); prefer clean values like `60%`.
- **CSS Syntax:**
  - **CRITICAL:** Do NOT nest `@media` blocks inside selector blocks. Always extract media queries to the top level.
- **Components:**
  - Ensure absolute-positioned elements have a parent with relative positioning or a defined minimum height to prevent layout collapse.
- **JavaScript Practices:**
  - **Dynamic Height Management:** When adding new interactive components with absolute-positioned children (like tabs or steps), use/extend the `syncContainerHeight` pattern in `script.js` to prevent parent height collapse.
  - **Smooth Transitions:** Always use smooth transitions for toggling visibility or switching between interface states.
  - **User Feedback:** Provide clear visual feedback for interactive elements (e.g., loading states for file uploads, typewriter effects for inputs).

## Reference Documentation
- See `INIT.md` for a detailed audit of previous issues and a verification checklist.
