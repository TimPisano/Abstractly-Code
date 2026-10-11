# Design tokens

Every color, font, spacing value, radius, shadow, and logo asset the
frontend uses today: where it's defined, and where it's used. Audited
2026-10-11 on branch `docs/design-tokens`. Counts are `var(--x)`
references across `frontend/` (CSS, HTML, and JS), excluding `vendor/`.

**One rule:** `frontend/design-system.css` is the single source of truth.
Every page loads it first, either through a `<link>` or through the
`@import` in `app/styles.css`. New colors go there as a named token, never as
a bare hex in a component rule.

| Stylesheet | Loaded by | Role |
|---|---|---|
| `design-system.css` | every page | All shared tokens + base reset, buttons, confirm dialog |
| `landing.css` | `index.html`, `pricing.html` | Marketing site. **Re-themes** some tokens to dark (see [Local overrides](#local-overrides)) |
| `app/auth.css` | `app/login`, `signup`, `forgot-password`, `reset-password`, `finish-signup` | Dark auth pages, own `--auth-*` aliases |
| `app/styles.css` | `app/index.html`, `app/team-setup.html`, `404.html`, `admin/dashboard.html` | The customer app |
| `admin/admin.css` | `admin/*` | Staff console, on top of `app/styles.css` |
| `owner/owner.css` | `owner/*` | Owner console |

---

## Colors

### Brand: charcoal + brass

| Token | Value | Uses | Purpose |
|---|---|---|---|
| `--lux-black` | `#0a0a0b` | 6 | Darkest ground: auth page and landing backgrounds |
| `--lux-charcoal` | `#17171a` | 4 | Sidebar / dark panels |
| `--lux-charcoal-2` | `#202024` | 1 | One step lighter charcoal |
| `--lux-ivory` | `#f6f3ec` | 36 | Light ground (app background) and text-on-dark |
| `--lux-accent` | `#b68a4e` | 35 | **The brass accent.** Fills, borders, icons only. 3.1:1 on white, too low for text |
| `--lux-accent-hover` | `#a37a41` | 3 | Hover on an accent fill |
| `--lux-accent-tint` | `#f2e9d8` | 7 | Pale brass fill (chips, selected rows) |
| `--lux-accent-tint-hover` | `#e8dcc3` | 1 | Hover on a tint fill |
| `--lux-accent-text` | → `--primary-dark` = `#8f6c3a` | 46 | **Brass as text**, and the primary button fill (4.8:1 with white) |
| `--lux-accent-rgb` | `182, 138, 78` | 10 | `--lux-accent` as a bare triplet for `rgba(var(--lux-accent-rgb), α)` |
| `--lux-accent-ring` | `rgba(182, 138, 78, 0.18)` | 5 | Soft brass focus ring (`box-shadow`) on inputs/selects |

Aliases kept from the pre-redesign palette. They resolve to the brass
values above, and existing rules still use the old names:

| Token | Resolves to | Uses |
|---|---|---|
| `--primary-color` | `--lux-accent` `#b68a4e` | 31 |
| `--primary-hover` | `--lux-accent-hover` `#a37a41` | 1 |
| `--primary-light` | `--lux-accent-tint` `#f2e9d8` | 22 |
| `--primary-dark` | `#8f6c3a` | 1 (via `--lux-accent-text`) |
| `--accent-color` | `--lux-accent` | 1 |
| `--gradient-brand` | `--lux-accent` (flat, deliberately not a gradient) | 1 |

### Semantic (status)

| Token | Value | Uses | Purpose |
|---|---|---|---|
| `--success-color` / `--success-light` | `#2f6b4f` / `#e3ede6` | 22 / 6 | Good / done |
| `--error-color` / `--error-light` | `#9a3b3b` / `#f3e3e1` | 29 / 8 | Wrong / risk |
| `--warning-color` / `--warning-light` | `#a6741f` / `#f3e7d2` | 11 / 7 | Watch this |
| `--lux-error-on-dark` | `#e5a5a0` | 4 | Error text on dark (landing, auth) |
| `--lux-warning-on-dark` | `#e0b374` | 4 | "Medium" amber on dark (landing sample report) |

`--confidence-*` (extraction certainty) and `--severity-*` (lease risk)
reuse the same hex values on purpose. They're kept as separate tokens
because the two meanings have diverged before.

| Token | Value | Uses |
|---|---|---|
| `--confidence-high` / `-bg` | `#2f6b4f` / `#e3ede6` | 16 / 11 |
| `--confidence-medium` / `-bg` | `#a6741f` / `#f3e7d2` | 15 / 12 |
| `--confidence-low` / `-bg` | `#9a3b3b` / `#f3e3e1` | 8 / 8 |
| `--confidence-none-bg` | `#eae6db` | 5 |
| `--severity-high` / `-bg` | `#9a3b3b` / `#f3e3e1` | 15 / 5 |
| `--severity-medium` / `-bg` | `#a6741f` / `#f3e7d2` | 7 / 2 |
| `--severity-low` / `-bg` | `#6f6c62` / `#efeade` | 6 / 3 |

### Neutrals (warm charcoal → ivory)

| Token | Value | Uses |
|---|---|---|
| `--slate-950` | `#0a0a0b` | 0 |
| `--slate-900` | `#17171a` | 0 |
| `--slate-800` | `#202024` | 0 |
| `--slate-700` | `#3a3833` | 0 |
| `--slate-600` | `#58554d` | 2 |
| `--slate-500` | `#6f6c62` | 1 |
| `--slate-400` | `#8b8779` | 2 |
| `--slate-300` | `#b3ada0` | 3 |
| `--slate-200` | `#e6e0d2` | 2 |
| `--slate-100` | `#efeade` | 3 |
| `--slate-50` | `#f6f3ec` | 2 |
| `--text-dark` | `#161512` | 65 |
| `--text-medium` | → `--slate-600` `#58554d` | 131 |
| `--text-light` | → `--slate-400` `#8b8779` | 40 |
| `--border-color` | → `--slate-200` `#e6e0d2` | 78 |
| `--background` | → `--lux-ivory` `#f6f3ec` | 39 |
| `--white` | `#ffffff` | 68 |
| `--sidebar-bg` / `--sidebar-text` / `--sidebar-text-active` | `--lux-charcoal` / `--slate-300` / `--lux-ivory` | 3 / 1 / 1 |

### Dark surfaces and translucents

| Token | Value | Uses | Purpose |
|---|---|---|---|
| `--lux-line-dark` | `rgba(246, 243, 236, 0.14)` | 10 | Hairline border on dark |
| `--lux-line-dark-faint` | `rgba(246, 243, 236, 0.08)` | 5 | Fainter hairline on dark |
| `--overlay-backdrop` | `rgba(10, 10, 11, 0.45)` | 3 | Dim layer behind modals/dialogs |

### Local overrides

These are defined outside `design-system.css` on purpose. They are
page-scoped themes, not duplicates.

**`landing.css` `:root`** (marketing site only) re-themes shared tokens
for a dark page:

| Token | Landing value | Shared value it replaces |
|---|---|---|
| `--text-dark` | `var(--lux-ivory)` | `#161512` |
| `--text-medium` | `rgba(246, 243, 236, 0.68)` | `#58554d` |
| `--text-light` | `rgba(246, 243, 236, 0.45)` | `#8b8779` |
| `--border-color` | `var(--lux-line-dark)` | `#e6e0d2` |
| `--shadow-sm` | `0 1px 2px rgba(10,10,11,.05)` | (deeper set, see Shadows) |
| `--shadow-md` | `0 8px 20px -6px rgba(10,10,11,.12)` | |
| `--shadow-lg` | `0 20px 40px -12px rgba(10,10,11,.22)` | |
| `--radius-sm/md/lg/xl` | `2px / 3px / 4px / 6px` | `6 / 10 / 14 / 20px` (sharper corners) |

The landing page also adds its own tokens: `--panel-bg` `rgba(23,23,26,.6)`,
`--panel-bg-strong` `rgba(20,20,23,.85)`, `--panel-border`
(→ `--lux-line-dark`), `--input-bg` `rgba(255,255,255,.06)`, and `--font-mono`.

**`app/auth.css` `:root`** (loaded only on the auth pages) defines short aliases for the auth screens:
`--auth-bg` (→ `--lux-black`), `--auth-panel` `rgba(23,23,26,.72)`,
`--auth-line` (→ `--lux-line-dark`), `--auth-line-strong`
`rgba(246,243,236,.26)`, `--auth-text` (→ `--lux-ivory`), `--auth-muted`
`rgba(246,243,236,.66)`, `--auth-faint` `rgba(246,243,236,.46)`,
`--auth-input-bg` `rgba(255,255,255,.05)`, `--auth-accent` (→ `--lux-accent`),
`--auth-accent-rgb` (→ `--lux-accent-rgb`), `--auth-error`
(→ `--lux-error-on-dark`), `--auth-success` `#9fcfb2`, `--auth-radius` `6px`.

### Colors still written as literals (and why)

| Where | Value | Why it stays |
|---|---|---|
| `<meta name="theme-color">` in 5 `app/` auth pages | `#0a0a0b` | HTML attributes can't read CSS variables |
| `app/report-view.js:16,21` (iframe `srcdoc`) | `#8b8779`, `#9a3b3b` | An iframe document doesn't inherit the parent's variables |
| `owner/owner-app.js:82` toast inline style | `#fff`, `rgba(0,0,0,…)` | JS-built inline style; one-off |
| `landing.js` shader (`FRAG_SRC`) | brass as 0–1 floats | WebGL can't read CSS. Must match `--lux-accent-rgb` by hand. (Its comment still says that token lives in `landing.css`; it now lives in `design-system.css`) |
| `landing.css:100` `.site-bg` | `#09090a` | Single use, one step off `--lux-black` |
| `landing.css` | ivory at many alphas (`rgba(246,243,236, .4/.55/.6/.65/.85)`), `rgba(255,255,255,.03/.05)`, `rgba(166,116,31,.22)` | One-off translucency steps within one file |
| `app/auth.css:221` autofill inset | `#1c1b1e` | `-webkit-autofill` override; single use |
| `app/auth.css:359` | `#9a7541` | Single use (`.auth-button` hover fill) |
| `app/styles.css:1308, 2112` | `rgba(37, 99, 235, 0.2)` | **Leftover blue focus ring from the old indigo palette.** Changing it would change pixels, so it's left as a finding |
| `app/styles.css` | `rgba(182,138,78,.45)`, `rgba(182,138,78,.35)` | Brass glow at one-off alphas |
| `owner/owner.css:537–539` tier chips | `#e3f1e8`, `#fdf0dc`, `#8a5a1c`, `#f7e0e0` | Close to, but not equal to, `--success-light` / `--warning-*` / `--error-light`. Switching would change pixels |

**Variables that are never defined.** For these, the fallback is what
actually renders, so treat the fallback as the real value:

| Reference | Renders as |
|---|---|
| `var(--bg-subtle, #f4f4f3)`, `app/styles.css:2181` | `#f4f4f3` |
| `var(--bg-subtle, #f1f1f0)`, `owner/owner.css:517` | `#f1f1f0` |
| `var(--color-background-secondary, #f9f9f9)`, `app/index.html:502` | `#f9f9f9` |
| `var(--color-border, #ddd)`, `app/deal-mismatch-view.js:196` | `#ddd` |

Some JS writes `var(--token)` strings into inline styles: avatar colors
in `app.js:810`, chart bars in `trends-view.js`, and status colors in
`owner-app.js`. These use `--lux-accent`, `--success-color`,
`--warning-color`, `--error-color`, `--slate-*`, and `--severity-*`.
Renaming a token means grepping JS too.

---

## Typography

**Family:** `--font-sans` = `'Inter', -apple-system, BlinkMacSystemFont,
'Segoe UI', 'Roboto', 'Helvetica Neue', sans-serif`. Inter is self-hosted
as one variable file, `frontend/fonts/inter-latin-var.woff2` (Latin subset,
weights 100–900, `font-display: swap`, OFL). Every HTML entry point
preloads it. There are no Google Fonts requests.

**Mono:** `--font-mono` = `ui-monospace, 'SF Mono', Menlo, Consolas,
'Liberation Mono', monospace`. It's system-only and used on the landing page
(ticker labels, sample report). `landing.css` also has 2 literal
`'Inter', sans-serif` declarations.

**Weights in use (198 declarations):** 700 ×78, 600 ×77, 500 ×16, 800 ×15,
400 ×6. One each of 900 and 200 (landing), and one 650 (auth).

**Type scale.** These tokens are defined but **not yet referenced**. Existing
rules use the literal rem values, which match the scale.

| Token | Value | px @16 | Literal uses | Typical use |
|---|---|---|---|---|
| `--text-xs` | `0.6875rem` | 11 | 28 | meta, tiny badges |
| `--text-sm` | `0.75rem` | 12 | 55 | captions, table meta |
| `--text-base-sm` | `0.8125rem` | 13 | 87 | secondary body (most common) |
| `--text-base` | `0.875rem` | 14 | 85 | body, buttons |
| `--text-md` | `0.9375rem` | 15 | 37 | subtitles |
| `--text-lg` | `1rem` | 16 | 10 | |
| `--text-xl` | `1.0625rem` | 17 | 14 | card values |
| `--text-2xl` | `1.125rem` | 18 | 10 | |
| `--text-3xl` | `1.25rem` | 20 | 7 | dialog/card h1 |
| `--text-4xl` | `1.5rem` | 24 | 3 | section headings |
| `--text-5xl` | `1.75rem` | 28 | 4 | page h1 |

Off-scale sizes in use: `0.5625rem`, `0.625rem` ×4, `0.78125rem`, `0.9rem` ×2
(auth), `0.975rem` (auth), `1.1875rem`, `1.375rem` ×2, `1.625rem` ×3, `2rem`,
`2.25rem`, `16px` (`.auth-input`; 16px keeps iOS Safari from zooming on focus), `0.8125em` (owner).
The landing and auth headlines use fluid `clamp()` sizes, from
`clamp(1.6rem, 5vw, 1.875rem)` up to `clamp(2.75rem, 5.2vw, 4.5rem)`.

**Line height:** `1.5` (body default, ×28), `1` ×12, `1.55` ×8, `1.6` ×7.
Display type on the landing page is tight: `1.02`–`1.15`.

**Letter spacing:** uppercase labels use `0.03em`–`0.05em` (most common
`0.04em` ×14, `0.03em` ×12). Headlines tighten to `-0.01em` through `-0.045em`.
The landing eyebrow uses `0.22em`.

---

## Spacing

The spacing scale is defined in `design-system.css`, **not yet referenced**
by token. 923 padding/margin/gap values were found, almost all on this
0.0625rem grid:

| Token | Value | px | Literal uses |
|---|---|---|---|
| `--space-1` | `0.125rem` | 2 | 25 |
| `--space-2` | `0.25rem` | 4 | 48 |
| `--space-3` | `0.375rem` | 6 | 52 |
| `--space-4` | `0.5rem` | 8 | 144 |
| `--space-5` | `0.625rem` | 10 | 81 |
| `--space-6` | `0.75rem` | 12 | 103 |
| `--space-7` | `0.875rem` | 14 | 62 |
| `--space-8` | `1rem` | 16 | 87 |
| `--space-10` | `1.25rem` | 20 | 74 |
| `--space-12` | `1.5rem` | 24 | 82 |
| `--space-16` | `2rem` | 32 | 23 |

Common values that aren't tokens yet: `0.0625rem` ×20, `0.1875rem` ×16,
`1.125rem` ×16, `1.75rem` ×14, `2.5rem` ×9, `0.4375rem` ×8, `7rem` ×7
(landing section padding), and `3–8rem` (landing sections). There are a few
off-grid strays: `0.6rem`, `0.4rem`, `0.9rem`, `0.55rem`, `0.7rem`, `0.15rem`,
`0.3rem`, `0.35rem`, `0.1rem`.

---

## Border radius

| Token | Shared value | Landing value | Uses |
|---|---|---|---|
| `--radius-sm` | `6px` | `2px` | 34 |
| `--radius-md` | `10px` | `3px` | 23 |
| `--radius-lg` | `14px` | `4px` | 22 |
| `--radius-xl` | `20px` | `6px` | 0 |
| `--radius-full` | `9999px` | — | 29 |
| `--auth-radius` | `6px` (auth pages) | — | 4 |

Literal radii: `9999px` ×22 (pills, same as `--radius-full`), `50%` ×7
(circles), `0.75rem` ×7, `0.375rem` ×7, `0.5rem` ×6, `0.25rem` ×3,
`0.625rem` ×2, `4px` ×2, and `999px` ×1 (owner). The Q&A question/answer
bubbles (`.qa-question`, `.qa-answer`) use asymmetric radii
(`0.75rem 0.75rem 0.125rem 0.75rem` and its mirror).

---

## Shadows

| Token | Value | Uses |
|---|---|---|
| `--shadow-sm` | `0 1px 2px rgba(10,10,11,.05), 0 1px 1px rgba(10,10,11,.03)` | 16 |
| `--shadow-md` | `0 4px 8px -2px rgba(10,10,11,.08), 0 2px 4px -2px rgba(10,10,11,.05)` | 11 |
| `--shadow-lg` | `0 12px 24px -6px rgba(10,10,11,.12), 0 4px 8px -4px rgba(10,10,11,.06)` | 11 |
| `--shadow-xl` | `0 24px 48px -12px rgba(10,10,11,.20), 0 8px 16px -8px rgba(10,10,11,.08)` | 6 |

The landing page overrides sm/md/lg with deeper single-layer shadows (see
[Local overrides](#local-overrides)).

Focus rings are `box-shadow` too: `0 0 0 2px|3px var(--lux-accent-ring)`
(inputs, app/admin/owner), `0 0 0 3px rgba(var(--auth-accent-rgb), .25)`
(auth), and the leftover blue `0 0 0 2px rgba(37,99,235,.2)` (2 app rules).
One-off shadows: the auth card `0 30px 60px -30px rgba(0,0,0,.8)`, the brass
button glows `0 10px 28px -8px rgba(accent, .45/.5)` (landing/auth), and the
confidence insets `inset 3px 0 0 var(--confidence-*-bg)`.

## Layering (z-index)

There are no tokens. The values in use, low to high:

| z-index | What |
|---|---|
| `-1`, `0`, `1`, `2` | Local stacking (landing background layers and hero, sticky table header/totals row) |
| `40` / `41` | Floating chat button / its panel (`.messaging-fab`/`-panel`, admin `.assistant-fab`/`-panel`) |
| `50` | Landing `.site-header` |
| `100` | Owner `.owner-modal-overlay` |
| `1000` | `.confirm-backdrop`, app `.toast-container` |
| `1300` | `.sidebar-tooltip` |
| `1401` | `.verify-popover` |
| `1500` | `.discrepancy-modal-backdrop`, `.task-modal-backdrop` |
| `2000` | `.skip-link` |

## Motion

Most transitions are `0.15s` (hover/background/border/transform) or
`0.2s ease`. The confirm dialog uses `0.16s`. `prefers-reduced-motion:
reduce` overrides exist in `design-system.css` (skip link, confirm dialog),
`landing.css`, `app/styles.css`, and `app/auth.css` (none in `admin.css` or
`owner.css`). Under reduced motion the landing WebGL background renders a
single static frame.

---

## Logo and icon assets

| Asset | Where | Used by |
|---|---|---|
| **Rows "A" mark** (11-rect pixel A, `viewBox 0 0 24 19`, `fill=currentColor`) | Inline SVG `.landing-logo-mark` / `.footer-logo-mark` | `index.html`, `pricing.html` (header + footer), all 5 `app/` auth pages |
| `favicon.svg` | `frontend/favicon.svg` (770 B; white A on `#0a0a0b` rounded square, 16×16) | every page (`?v=2`) |
| `favicon.ico` | `frontend/favicon.ico` (1,201 B, 32×32) | every page (`?v=2`) |
| `apple-touch-icon.png` | `frontend/apple-touch-icon.png` (999 B) | every page (`?v=2`) |
| `og-image.png` | `frontend/og-image.png` (2400×1260, 591,787 B; mark + gold glow) | `og:image` / `twitter:image` on 11 pages (not the 5 auth pages) (`?v=5`). The URL still points at `abstractly-n0id.onrender.com` |
| Generic **building** icon (Heroicons outline, `.brand-icon`) | Inline SVG | App sidebar: `app/index.html`, `team-setup.html`, `404.html`, `admin/dashboard.html`. **Not yet switched to the rows mark** |
| Logo sources | `design/logo/final/` (`abstractly-lockup-white.svg`, `abstractly-mark-white.svg`, `favicon.svg`, `header-mark.svg.html`); concept variants `design/logo/rows{5,7,9}-*.svg`; generators `design/logo/build.py`, `render_assets.mjs`; OG source `design/logo/og/og-image.html` | Design history: `docs/plans/design-logo.md` |
| UI icons | Inline Heroicons outline SVGs (`stroke="currentColor"`, 1.5–2 stroke) | Nav, buttons, cards app-wide. They take their color from the surrounding text |

---

## Adding or changing a token

1. Add it to `:root` in `design-system.css`, in the matching section, with
   a one-line comment saying what it's for.
2. Reference it with `var(--name)`. Don't paste the hex, and don't add a
   `var(--x, #fallback)` fallback unless `--x` can genuinely be missing
   (that fallback silently becomes the real color if the token is renamed).
3. Changing a value? Grep `frontend/` including JS, since some JS builds
   `var(--token)` inline styles, plus `landing.js` for the shader's copy of the brass.
4. CSS is cached for 10 minutes (`max-age=600`). A new token in
   `design-system.css` used by another file can briefly be missing for a
   visitor with a stale cached copy during a deploy.
