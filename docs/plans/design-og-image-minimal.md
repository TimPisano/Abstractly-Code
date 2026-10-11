# Plan: design/og-image-minimal

## Goal

Make the link-preview image (`frontend/og-image.png`, 1200x630) minimal:
a near-black background, subtle gold fluted light bands across the full
width, and the Abstractly mark + wordmark large and centered. No other
text. The page's `og:title` supplies the words under the image. Bump the
`og:image` / `twitter:image` URLs to `?v=5` so iMessage, Slack and others
re-fetch the image.

The user's task prompt (2026-10-05) is treated as the plan approval.

## Prior art

- `design/logo` (merged `47f2a7b`) created the current image from
  `design/logo/og/og-image.html` via `design/logo/render_assets.mjs`,
  with tags at `?v=2` on all 14 pages. This branch edits that same
  source. No other branch has a v3 or v4. `feature/calendly-booking`
  carries `?v=2` only because it was cut from main.

## Changes

1. `design/logo/og/og-image.html`: the headline and sample figure are
   removed, the bands run the full width, and the lockup is centered
   (mark 150px tall, wordmark 150px).
2. `design/logo/render_assets.mjs`: new `og` argument renders only the
   OG image, so the favicon and apple-touch icon aren't re-rendered.
3. `frontend/og-image.png`: re-rendered.
4. All 14 pages: `og:image` and `twitter:image` go to `?v=5`. The
   `og:image:alt` and `twitter:image:alt` text described the old
   headline and dollar figure; it now describes the new image.
   `og:title` is unchanged.

## Round 2 (user: "the same gold light bands effect from our landing page hero")

The first version imitated the hero with CSS ribs: denser, dimmer and more
uniform than the real thing. `og-image.html` now draws the hero's **own**
WebGL shader. `render_assets.mjs og` reads `VERT_SRC`/`FRAG_SRC` out of
`frontend/landing.js` at render time and draws one still frame: motion
off, time 0, full brightness, spotlight at (600, 360), just below
centre. It refuses to write a blank PNG if WebGL is missing. The lockup
gets a soft drop shadow so white stays clean over the brightest rods.

## Final (user-approved 2026-10-05)

- **Glow:** the hero shader's spotlight is drawn into a buffer that is
  half as wide relative to its height, so the circle stretches into a
  wide oval: brightest in the centre, fading to black at every edge.
  The light is dead centre.
- **Lockup:** mark 120px, Inter 500 at 128px (120px of ink from the top
  of the "b" to the bottom of the "y"), 36px gap, soft drop shadow.
- **Resolution:** rendered at deviceScaleFactor 2, so the PNG is
  **2400x1260**. The buffer is 1200x1260. The mark and wordmark are
  vector, so they render crisp.
  - Parity check against the approved 1x render: outside the lockup,
    max per-channel difference 5/255. All larger differences are the
    sharper logo edges.
- `og:image:width/height` on all 14 pages are now 2400/1260 to match the
  file.
- A striped all-SVG variant was tried and rejected by the user. It is
  not committed.

## Not changed

- `og:title` and descriptions.
- The favicon and apple-touch `?v=2` cache-busters (those images didn't
  change).
- The `abstractly-n0id.onrender.com` image host (an existing TASKS
  follow-up).

## Verification

- Full-size render looked at.
- iMessage-style card mock at 300px wide (1x and 3x) and a 150px
  thumbnail, looked at.
- Full test suite run.
