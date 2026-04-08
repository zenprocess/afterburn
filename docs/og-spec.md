# OG Image Design Specification — standra.ai Projects

Reusable design system for consistent OG/social images across all zenprocess repos.

## Canvas

| Property | Value |
|----------|-------|
| Format | SVG (vector, renders at any size) |
| Dimensions | 1200 x 630 px (Open Graph standard) |
| Filename | `docs/og-image.svg` |
| README embed | `<p align="center"><img src="docs/og-image.svg" alt="..." width="800" /></p>` |

## Color Palette

### Background
```
Primary:   #0a0a0f  (near-black)
Secondary: #0f1729  (dark navy)
Gradient:  linear 0%→100% diagonal, #0a0a0f → #0f1729 → #0a0a0f
```

### Accent (per-project — this is the thing you change)
```
Afterburn: #ff4500 → #ff6b35 → #ffa500 → #ffd700  (fire: red → orange → amber → gold)
```

Pick a 4-stop gradient per project. The accent drives:
- Icon fill gradients
- Underline bar
- Feature pill borders and text
- Architecture diagram node borders
- Ambient glow

### Text
```
Title:     #ffffff  (pure white)
Tagline:   #8899aa  (muted blue-gray)
Body:      #667788  (dim)
Subtle:    #445566  (near-invisible, for architecture labels)
Footer:    #334455 → #445566
```

### Grid overlay
```
Color:     #ffffff at 4% opacity
Stroke:    0.5px
Spacing:   60px
```

## Typography

| Element | Font Stack | Size | Weight | Spacing |
|---------|-----------|------|--------|---------|
| Title | `'SF Mono', 'Fira Code', 'JetBrains Mono', 'Cascadia Code', monospace` | 82px | 800 | 6px letter-spacing |
| Tagline | `'Inter', 'Helvetica Neue', Arial, sans-serif` | 24px | 400 | 1px letter-spacing |
| Pill labels | `'SF Mono', monospace` | 13px | 500 | default |
| Architecture labels | `'SF Mono', monospace` | 10px | 400 | default |
| Footer text | `'Inter', sans-serif` | 13-14px | 400 | default |
| standra.ai badge | `'Inter', sans-serif` | 11px (label) / 14px (name) | 400 / 600 | default |

## Layout Grid

```
 ┌─────────────────────────────────────────────────────────────┐
 │  0,0                                              1200,0   │
 │                                                             │
 │   ┌──────┐                                                  │
 │   │ ICON │  TITLE (82px)                    y=290           │
 │   │ 130px│  ════════════════════════        y=308 (bar)     │
 │   │ wide │  tagline (24px)                  y=355           │
 │   └──────┘                                                  │
 │   x=115     x=260                                           │
 │                                                             │
 │              [PILL] [PILL] [PILL] [PILL] [PILL]  y=400      │
 │                                                             │
 │              ┌──┐→┌──┐→┌──┐→┌──┐→┌──┐           y=470      │
 │              architecture mini-diagram                      │
 │                                                             │
 │              footer text                         y=560      │
 │              repo URL                            y=582      │
 │                                        ┌──────────────┐     │
 │                                        │ standra.ai   │     │
 │                                        └──────────────┘     │
 └─────────────────────────────────────────────────────────────┘
```

### Key positions
| Element | X | Y |
|---------|---|---|
| Icon top-left | 115 | 170 |
| Icon center | 180 | 280 |
| Title baseline | 260 | 290 |
| Accent bar | 260 | 308 (2px height, 740px width) |
| Tagline baseline | 260 | 355 |
| Feature pills row | 260 | 400 |
| Architecture row | 260 | 470 |
| Footer line 1 | 260 | 560 |
| Footer line 2 | 260 | 582 |
| standra.ai badge | 920 | 548 (220x40 rounded rect) |

## Icon

- Position: left column (x=115, y=170), ~130px wide, ~220px tall
- Style: multi-layer gradient paths (3 layers: outer, inner, core)
- Ambient glow: ellipse behind icon, accent color at 6% opacity, 20px blur
- The icon should represent the project's concept (flame for afterburn)

## Feature Pills

- Row of 3-5 pills at y=400
- Each pill: rounded rect (rx=18), ~145-155px wide, 36px tall
- Border: accent color variants, 1.5px stroke, 60% opacity, no fill
- Text: monospace, 13px, accent color, centered
- Spacing: ~15px gap between pills

## Architecture Mini-Diagram

- Single-row flow at y=470, 50% opacity
- Boxes: 100-110px wide, 28px tall, rx=4
- Borders: accent/neutral colors, 1px stroke
- Arrows: simple lines with triangular polygon heads
- Labels: 10px monospace
- Shows the project's core pipeline left-to-right

## standra.ai Badge

- Fixed position: bottom-right (920, 548)
- Rounded rect: 220x40, rx=6, no fill, #334455 border
- Two lines: "Part of" (11px, #556677) + "standra.ai" (14px bold, #8899aa)
- Always present on all repos

## Ambient Effects

| Effect | Implementation |
|--------|---------------|
| Grid | White lines at 4% opacity, 60px spacing, full canvas |
| Icon glow | Ellipse behind icon, accent color, 6% opacity, `feGaussianBlur stdDeviation="20"` |
| Accent bar glow | Duplicate bar rect with glow gradient, `feGaussianBlur stdDeviation="3"` |

## Per-Project Customization

Only these elements change between repos:

1. **Icon** — different SVG paths representing the project concept
2. **Accent gradient** — 4-stop color scheme (keep the same structure)
3. **Title text** — project name in caps
4. **Tagline text** — one-line description
5. **Pill labels** — project's key features (3-5)
6. **Architecture labels** — project's pipeline steps

Everything else (layout, typography, grid, badge, effects) stays identical.

### Example accent palettes

| Project | Stop 1 | Stop 2 | Stop 3 | Stop 4 | Metaphor |
|---------|--------|--------|--------|--------|----------|
| Afterburn | #ff4500 | #ff6b35 | #ffa500 | #ffd700 | Fire |
| Dispatch | #0066ff | #3388ff | #55aaff | #88ccff | Rail/signal |
| Sentinel | #00cc66 | #33dd88 | #66eeaa | #99ffcc | Shield/scan |
| Sieeve | #8833ff | #9955ff | #aa77ff | #cc99ff | Filter/prism |
| ServingCard | #ff3366 | #ff5588 | #ff77aa | #ff99cc | Card/benchmark |
