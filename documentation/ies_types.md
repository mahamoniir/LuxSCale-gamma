# IES Photometric Coordinate Systems

A comparison of Type A, Type B, and Type C photometric types used in IES files.

---

## Type C — Most Common

**~90% of all IES files use Type C.**

The coordinate system is built around a vertical axis pointing straight down (nadir).

| Angle | Description | Range |
|-------|-------------|-------|
| **C** | Horizontal rotation around the vertical axis | 0–360° |
| **γ (gamma)** | Vertical angle measured from nadir | 0–180° |

**Natural aim:** Downward

**Typical fixtures:** Downlights, troffers, recessed fixtures, area lights, most general lighting

**When to watch out:** Many IES parsers silently assume Type C. Type B files fed into a Type C parser produce wildly wrong lumen distributions because B-plane angles get misread as C-planes.

---

## Type B — Tilted / Lateral

The luminaire rotates on its lateral (side-to-side) axis — like tilting a floodlight up or down.

| Angle | Description | Range |
|-------|-------------|-------|
| **B** | Lateral rotation angle | −90° to +90° |
| **β (beta)** | Vertical angle | 0–180° |

**Natural aim:** Tilted or upward

**Typical fixtures:** Adjustable floodlights, theatrical fixtures, architectural wallwashers, spots mounted sideways or tilted

---

## Type A — Automotive / Horizontal

The luminaire is treated as if mounted horizontally and facing forward — like a car headlamp or a wall sconce.

| Angle | Description | Range |
|-------|-------------|-------|
| **A** | Horizontal sweep angle | 0–360° |
| **α (alpha)** | Vertical elevation angle | −90° to +90° |

**Natural aim:** Horizontal

**Typical fixtures:** Automotive headlamps, wall sconces, traffic signals, specialty directional fixtures

**Prevalence:** Rare in architectural/commercial IES files — essentially the automotive coordinate system.

---

## Quick Comparison Table

| Attribute | Type C | Type B | Type A |
|-----------|--------|--------|--------|
| Primary axis | C (horizontal rotation) | B (lateral rotation) | A (horizontal sweep) |
| Secondary angle | γ from nadir | β vertical | α elevation |
| Natural aim | Downward | Tilted / upward | Horizontal |
| Typical fixtures | Downlights, troffers | Floodlights, spots | Automotive, signals |
| Prevalence | ~90% of IES files | Occasional | Rare / specialty |
| Header keyword | `PHOTOMETRIC_TYPE C` | `PHOTOMETRIC_TYPE B` | `PHOTOMETRIC_TYPE A` |

---

## Parser Notes

The `PHOTOMETRIC_TYPE` keyword in the IES file header identifies which system is used. A robust IES parser must branch on this value — assuming Type C for all files is a common source of errors, particularly for Type B floodlight and wallwasher data.

> **SC Audit note:** During the SC IES file audit (31 files), Type B misclassification was identified as a systemic issue — fixtures with B-plane data being parsed as C-planes, producing incorrect illuminance calculations and uniformity failures.