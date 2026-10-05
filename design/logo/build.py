#!/usr/bin/env python3
"""Generate the Abstractly logomark concept SVGs and the preview page.

Every SVG in this folder is written by this script, so the geometry of
each concept lives in exactly one place (CONCEPTS below). Re-run after
editing:

    PYTHONPATH=<dir with fonttools + uharfbuzz> python3 design/logo/build.py

The wordmark is Inter SemiBold (the site's own font,
frontend/fonts/inter-latin-var.woff2) converted to outlines, so the
lockup SVGs render identically with no font installed.
"""
import io
import os

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, '..', '..', 'frontend', 'fonts', 'inter-latin-var.woff2')

# Existing palette only (frontend/design-system.css).
BLACK = '#0a0a0b'      # --lux-black
CHARCOAL = '#17171a'   # --lux-charcoal
IVORY = '#f6f3ec'      # --lux-ivory
GOLD = '#b68a4e'       # --lux-accent
GOLD_DEEP = '#8f6c3a'  # --primary-dark (accent on light backgrounds)

THEMES = {
    'dark': {'ink': IVORY, 'accent': GOLD, 'bg': BLACK},
    'light': {'ink': BLACK, 'accent': GOLD_DEEP, 'bg': IVORY},
}


# ---------------------------------------------------------------- marks
# Each mark is drawn on a 32x32 grid. A body is a function of the theme
# colors returning SVG elements. `fav` is a separate 16x16 drawing hinted
# to whole pixels for the favicon, where the 32-grid shape would blur.

def split_mark(ink, accent):
    # Sharp A; the crossbar is two records that don't line up: the left
    # half sits a step higher than the right, with a hairline gap.
    return (
        f'<path fill="{ink}" d="M2 30 13.25 2h5.5L30 30h-5.4L16 8.6 7.4 30z"/>'
        f'<path fill="{ink}" d="M9.6 18.4h5.4v3.4H8.25z"/>'
        f'<path fill="{accent}" d="M17 21.8h4.3l1.37 3.4H17z"/>'
    )


def split_fav(ink, accent):
    # At 16px a gap would vanish, so the mismatch is the step alone.
    return (
        f'<path fill="{ink}" d="M1.5 14 6.5 2h3l5 12H12L8 4.4 4 14z"/>'
        f'<path fill="{ink}" d="M6.5 8H8v2H5.67z"/>'
        f'<path fill="{accent}" d="M8 10h2.33l.84 2H8z"/>'
    )


def fluted_mark(ink, accent, uid='f'):
    # The A silhouette, cut by four thin grooves into five vertical ribs
    # like the fluted-glass bands in the hero. One rib right of centre
    # catches the light (gold), the way a band does as it sweeps across.
    ribs = ''.join(
        f'<rect x="{x}" y="0" width="5.04" height="32" fill="{accent if i == 3 else ink}"/>'
        for i, x in enumerate((1, 7.24, 13.48, 19.72, 25.96))
    )
    return (
        f'<clipPath id="{uid}"><path clip-rule="evenodd" '
        'd="M1 30 13 2h6l12 28h-6.2l-2.66-6.2H9.86L7.2 30zM12.17 18.4h7.66L16 9.47z"/>'
        f'</clipPath><g clip-path="url(#{uid})">{ribs}</g>'
    )


def fluted_fav(ink, accent, uid='ff'):
    # Five 2px ribs with 1px grooves on whole pixels. Clipping the ribs
    # to the A's slanted counter leaves half-pixel slivers at this size,
    # so the apex and crossbar bridge the two inner grooves (otherwise it
    # reads as an H) and only the outer roof line is slanted.
    del uid
    return (
        f'<path fill="{ink}" d="M1 14 3 9.2V14z"/>'
        f'<path fill="{ink}" d="M4 14V6.8L6 2V14z"/>'
        f'<path fill="{ink}" d="M6 2h4v3H6zM6 9h4v2H6z"/>'
        f'<path fill="{accent}" d="M10 14V2l2 4.8V14z"/>'
        f'<path fill="{ink}" d="M13 14V9.2l2 4.8z"/>'
    )


def ledger_mark(ink, accent):
    # Two separate slanted strokes; the crossbar is one highlighted row
    # that runs past both legs, like a flagged line in a rent roll.
    return (
        f'<path fill="{ink}" d="M2 30 11.2 2h4.2L6.6 30z"/>'
        f'<path fill="{ink}" d="M25.4 30 16.6 2h4.2L30 30z"/>'
        f'<rect x="1" y="18" width="30" height="4.6" rx="1" fill="{accent}"/>'
    )


def ledger_fav(ink, accent):
    return (
        f'<path fill="{ink}" d="M1.5 14 5.6 2h2.1L3.6 14z"/>'
        f'<path fill="{ink}" d="M12.4 14 8.3 2h2.1l4.1 12z"/>'
        f'<rect x="1" y="9" width="14" height="2" fill="{accent}"/>'
    )


CONCEPTS = [
    {'key': 'split', 'name': 'Split crossbar',
     'idea': 'A sharp geometric A whose crossbar is broken and stepped: '
             'two records that should line up and don’t.',
     'mark': split_mark, 'fav': split_fav},
    {'key': 'fluted', 'name': 'Fluted A',
     'idea': 'A solid A cut by thin grooves into five vertical ribs, echoing '
             'the fluted-glass light bands in the hero. One rib catches the light.',
     'mark': fluted_mark, 'fav': fluted_fav},
    {'key': 'ledger', 'name': 'Ledger A',
     'idea': 'Two slanted strokes; the crossbar is a single highlighted row '
             'that runs past both legs, like a flagged line in a rent roll.',
     'mark': ledger_mark, 'fav': ledger_fav},
]


def body(concept, kind, ink, accent, uid=None):
    fn = concept[kind]
    if concept['key'] == 'fluted':
        return fn(ink, accent, uid or (concept['key'] + kind))
    return fn(ink, accent)


# ------------------------------------------------------------- wordmark

def wordmark_path(text='Abstractly', weight=600, tracking=-0.02):
    """Return (svg path d, advance width, cap height) in font units."""
    font = TTFont(FONT)
    inst = instancer.instantiateVariableFont(font, {'wght': weight})
    inst.flavor = None
    buf = io.BytesIO()
    inst.save(buf)
    data = buf.getvalue()

    face = hb.Face(data)
    hbfont = hb.Font(face)
    hbuf = hb.Buffer()
    hbuf.add_str(text)
    hbuf.guess_segment_properties()
    hb.shape(hbfont, hbuf, {'kern': True, 'liga': True})

    tt = TTFont(io.BytesIO(data))
    upm = tt['head'].unitsPerEm
    gs = tt.getGlyphSet()
    order = tt.getGlyphOrder()
    pen = SVGPathPen(gs)
    x = 0
    for info, pos in zip(hbuf.glyph_infos, hbuf.glyph_positions):
        gname = order[info.codepoint]
        # Flip y: font units are y-up, SVG is y-down.
        gs[gname].draw(TransformPen(pen, (1, 0, 0, -1, x + pos.x_offset, -pos.y_offset)))
        x += pos.x_advance + tracking * upm
    x -= tracking * upm
    return pen.getCommands(), x, tt['OS/2'].sCapHeight, upm


WM_D, WM_W, WM_CAP, WM_UPM = wordmark_path()


def lockup(concept, ink, accent, uid=None):
    """Mark (32 tall) + wordmark whose cap height is 15 units, centred."""
    cap = 15.0
    s = cap / WM_CAP
    gap = 9.5
    tx = 32 + gap
    ty = 16 + cap / 2
    width = tx + WM_W * s
    return width, (
        f'<g>{body(concept, "mark", ink, accent, uid)}</g>'
        f'<path fill="{ink}" transform="translate({tx:.3f} {ty:.3f}) scale({s:.6f})" d="{WM_D}"/>'
    )


# ---------------------------------------------------------------- files

def svg(view_w, view_h, inner, label, w=None, h=None):
    size = f' width="{w}" height="{h}"' if w else ''
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {view_w:.2f} {view_h}"{size} '
            f'role="img" aria-label="{label}">{inner}</svg>\n')


def favicon(concept):
    # Dark tile so the mark reads on light and dark browser chrome alike.
    inner = (f'<rect width="16" height="16" rx="3" fill="{CHARCOAL}"/>'
             f'{body(concept, "fav", IVORY, GOLD)}')
    return svg(16, 16, inner, 'Abstractly')


def write_files():
    for c in CONCEPTS:
        k = c['key']
        for theme, col in THEMES.items():
            with open(os.path.join(HERE, f'{k}-mark-{theme}.svg'), 'w') as f:
                f.write(svg(32, 32, body(c, 'mark', col['ink'], col['accent']), 'Abstractly'))
            w, inner = lockup(c, col['ink'], col['accent'])
            with open(os.path.join(HERE, f'{k}-lockup-{theme}.svg'), 'w') as f:
                f.write(svg(w, 32, inner, 'Abstractly'))
            with open(os.path.join(HERE, f'{k}-favicon-{theme}.svg'), 'w') as f:
                f.write(svg(16, 16, body(c, 'fav', col['ink'], col['accent']), 'Abstractly'))
        with open(os.path.join(HERE, f'{k}-favicon.svg'), 'w') as f:
            f.write(favicon(c))


# ------------------------------------------------------------- preview

def preview():
    n = [0]

    def uid():
        n[0] += 1
        return f'u{n[0]}'

    def mark(c, theme, px):
        col = THEMES[theme]
        return svg(32, 32, body(c, 'mark', col['ink'], col['accent'], uid()), f'{c["name"]} mark', px, px)

    def fav(c, theme, px):
        col = THEMES[theme]
        return svg(16, 16, body(c, 'fav', col['ink'], col['accent'], uid()), f'{c["name"]} favicon', px, px)

    def lock(c, theme, h):
        col = THEMES[theme]
        w, inner = lockup(c, col['ink'], col['accent'], uid())
        return svg(w, 32, inner, 'Abstractly', round(w * h / 32, 1), h)

    cols = []
    for c in CONCEPTS:
        k = c['key']
        tiles = ''.join(
            f'<div class="fav-cell"><img src="{k}-favicon.svg" width="{px}" height="{px}" alt="">'
            f'<span>{px}px</span></div>' for px in (16, 32, 48))
        cols.append(f'''
<section class="concept" id="{k}">
  <header class="concept-head">
    <span class="num">0{CONCEPTS.index(c) + 1}</span>
    <h2>{c["name"]}</h2>
    <p>{c["idea"]}</p>
  </header>

  <div class="panel dark big">{mark(c, "dark", 200)}</div>
  <div class="panel light big">{mark(c, "light", 200)}</div>

  <h3>Lockup</h3>
  <div class="panel dark lock">{lock(c, "dark", 40)}</div>
  <div class="panel light lock">{lock(c, "light", 40)}</div>

  <h3>In the header</h3>
  <div class="fake-header dark"><span class="brand">{lock(c, "dark", 22)}</span>
    <nav><span>How It Works</span><span>Pricing</span><span class="cta">Book a demo</span></nav></div>
  <div class="fake-header light"><span class="brand">{lock(c, "light", 22)}</span>
    <nav><span>How It Works</span><span>Pricing</span><span class="cta">Book a demo</span></nav></div>

  <h3>Favicon</h3>
  <div class="tabs">
    <div class="tab dark-chrome"><img src="{k}-favicon.svg" width="16" height="16" alt="">Abstractly — Deal Mismatch</div>
    <div class="tab light-chrome"><img src="{k}-favicon.svg" width="16" height="16" alt="">Abstractly — Deal Mismatch</div>
  </div>
  <div class="favs panel dark">{tiles}</div>
  <div class="favs bare">
    <div class="panel dark small">{fav(c, "dark", 16)}<span>16px · no tile</span></div>
    <div class="panel light small">{fav(c, "light", 16)}<span>16px · no tile</span></div>
    <div class="panel dark small zoom"><canvas class="px" data-src="{k}-favicon.svg" width="16" height="16"></canvas><span>real 16px pixels ×6</span></div>
  </div>

  <h3>Files</h3>
  <ul class="files">
    <li><a href="{k}-mark-dark.svg">{k}-mark-dark.svg</a></li>
    <li><a href="{k}-mark-light.svg">{k}-mark-light.svg</a></li>
    <li><a href="{k}-lockup-dark.svg">{k}-lockup-dark.svg</a></li>
    <li><a href="{k}-lockup-light.svg">{k}-lockup-light.svg</a></li>
    <li><a href="{k}-favicon.svg">{k}-favicon.svg</a></li>
    <li><a href="{k}-favicon-dark.svg">{k}-favicon-dark.svg</a> · <a href="{k}-favicon-light.svg">light</a></li>
  </ul>
</section>''')

    html = TEMPLATE.replace('{{CONCEPTS}}', ''.join(cols))
    with open(os.path.join(HERE, 'index.html'), 'w') as f:
        f.write(html)


TEMPLATE = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Abstractly logo concepts</title>
<link rel="icon" href="split-favicon.svg" type="image/svg+xml">
<style>
@font-face {
  font-family: 'Inter';
  src: url('../../frontend/fonts/inter-latin-var.woff2') format('woff2');
  font-weight: 100 900;
}
:root {
  --black: #0a0a0b; --charcoal: #17171a; --ivory: #f6f3ec;
  --gold: #b68a4e; --gold-deep: #8f6c3a;
  --line: rgba(246, 243, 236, 0.14); --muted: rgba(246, 243, 236, 0.62);
}
* { box-sizing: border-box; }
html { background: var(--black); }
body { margin: 0; font-family: 'Inter', system-ui, sans-serif; color: var(--ivory); }
.page-head { max-width: 1320px; margin: 0 auto; padding: 56px 24px 8px; }
.eyebrow { font: 500 12px/1 ui-monospace, 'SF Mono', Menlo, monospace; letter-spacing: .14em;
  text-transform: uppercase; color: var(--gold); }
h1 { font-size: clamp(28px, 4vw, 44px); letter-spacing: -0.03em; margin: 14px 0 10px; font-weight: 600; }
.page-head p { color: var(--muted); max-width: 640px; margin: 0; line-height: 1.55; }
.grid { max-width: 1320px; margin: 0 auto; padding: 32px 24px 80px;
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 28px; }
.concept { min-width: 0; }
.concept-head { min-height: 132px; margin-bottom: 16px; }
.num { font: 500 12px ui-monospace, Menlo, monospace; color: var(--gold); }
h2 { margin: 6px 0 8px; font-size: 22px; font-weight: 600; letter-spacing: -0.02em; }
.concept-head p { margin: 0; color: var(--muted); font-size: 14px; line-height: 1.5; }
h3 { font: 500 11px ui-monospace, Menlo, monospace; letter-spacing: .14em; text-transform: uppercase;
  color: var(--muted); margin: 28px 0 10px; }
.panel { border: 1px solid var(--line); border-radius: 6px; display: flex;
  align-items: center; justify-content: center; }
.panel.dark { background: var(--charcoal); }
.panel.light { background: var(--ivory); color: var(--black); border-color: transparent; }
.panel.big { aspect-ratio: 1 / 1; margin-bottom: 12px; }
.panel.big svg { width: 58%; height: auto; }
.panel.lock { height: 110px; margin-bottom: 12px; padding: 0 16px; }
.panel.lock svg { max-width: 100%; height: auto; }
.fake-header { display: flex; align-items: center; justify-content: space-between; gap: 12px;
  height: 56px; padding: 0 16px; border-radius: 6px; margin-bottom: 12px; font-size: 12px; }
.fake-header.dark { background: rgba(10,10,11,.9); border: 1px solid var(--line); color: var(--muted); }
.fake-header.light { background: var(--ivory); color: #55534d; }
.fake-header .brand { display: flex; }
.fake-header nav { display: flex; gap: 14px; align-items: center; white-space: nowrap; }
.fake-header .cta { background: var(--gold); color: var(--black); padding: 6px 10px; border-radius: 3px; font-weight: 600; }
.tabs { display: grid; gap: 8px; margin-bottom: 12px; }
.tab { display: flex; align-items: center; gap: 8px; font-size: 12px; height: 34px; padding: 0 12px;
  border-radius: 8px 8px 0 0; width: 240px; max-width: 100%; white-space: nowrap; overflow: hidden; }
.tab img { flex-shrink: 0; }
.dark-chrome { background: #2a2a2e; color: #e8e6e1; }
.light-chrome { background: #ffffff; color: #222; border: 1px solid #ddd; border-bottom: 0; }
.favs { display: flex; gap: 12px; align-items: flex-end; justify-content: center; padding: 18px; margin-bottom: 12px; }
.fav-cell, .small { display: flex; flex-direction: column; align-items: center; gap: 8px; }
.fav-cell span, .small span { font: 11px ui-monospace, Menlo, monospace; color: var(--muted); }
.panel.light.small span { color: #55534d; }
.favs.bare { padding: 0; align-items: stretch; }
.favs.bare .panel { flex: 1; padding: 16px 8px; justify-content: flex-end; }
canvas.px { width: 96px; height: 96px; image-rendering: pixelated; }
.files { list-style: none; padding: 0; margin: 0; font: 12px/1.9 ui-monospace, Menlo, monospace; }
.files a { color: var(--gold); text-decoration: none; }
.files a:hover { text-decoration: underline; }
@media (max-width: 1100px) { .grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 720px) {
  .grid { grid-template-columns: 1fr; padding: 24px 16px 64px; }
  .page-head { padding: 40px 16px 0; }
  .concept-head { min-height: 0; }
  .fake-header nav span:not(.cta) { display: none; }
}
</style>
</head>
<body>
<header class="page-head">
  <div class="eyebrow">Abstractly · Logo exploration</div>
  <h1>Three marks built on a capital A</h1>
  <p>Each concept shown large on dark and light, as a lockup with the Abstractly wordmark
  (Inter SemiBold, outlined), in a site header, and at favicon size. Palette is the site’s own:
  black, charcoal, ivory, brass. The 16px favicons use a separate pixel-hinted drawing.</p>
</header>
<main class="grid">{{CONCEPTS}}
</main>
<script>
// Rasterise each favicon at a true 16x16 and blow it up with no smoothing,
// so the preview shows the actual pixels a browser tab would get.
document.querySelectorAll('canvas.px').forEach(function (cv) {
  var img = new Image();
  img.onload = function () { cv.getContext('2d').drawImage(img, 0, 0, 16, 16); };
  img.src = cv.dataset.src;
});
</script>
</body>
</html>
'''


if __name__ == '__main__':
    write_files()
    preview()
    print('wrote', sorted(f for f in os.listdir(HERE) if f.endswith(('.svg', '.html'))))
