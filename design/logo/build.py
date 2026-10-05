#!/usr/bin/env python3
"""Generate the Abstractly logomark SVGs and the preview page.

Direction (round 2): a capital A built only from stacked horizontal
bars, like rows in a rent roll. Bars lengthen from top to bottom to make
the triangle, the counter is a gap, and one bar is shifted sideways: a
caught mismatch. Three variations differ in bar count, bar thickness and
how hard the shift is.

Every SVG in this folder is written by this script, so each variation's
geometry lives in exactly one place (VARIATIONS below). Re-run after
editing:

    PYTHONPATH=<dir with fonttools + uharfbuzz> python3 design/logo/build.py

The wordmark is Inter Medium (the site's own font,
frontend/fonts/inter-latin-var.woff2) converted to outlines, so the
lockup SVGs render identically with no font installed.
"""
import glob
import io
import os

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, '..', '..', 'frontend', 'fonts', 'inter-latin-var.woff2')

WHITE = '#ffffff'
BLACK = '#0a0a0b'      # --lux-black
GOLD = '#b68a4e'       # --lux-accent
GOLD_DEEP = '#8f6c3a'  # --primary-dark (the accent on white backgrounds)

# name -> (ink, accent for the shifted bar, background it is designed for)
COLORWAYS = {
    'white': (WHITE, WHITE, BLACK),
    'white-gold': (WHITE, GOLD, BLACK),
    'black': (BLACK, BLACK, WHITE),
    'black-gold': (BLACK, GOLD_DEEP, WHITE),
}


# ---------------------------------------------------------------- marks
# A row is (y, [(x0, x1), ...], shift); `shift` moves the whole row
# sideways and paints it in the accent. Shape of every A, top to bottom:
# solid apex rows, split rows (the counter), one solid crossbar row, split
# rows (the legs).
#
# Large marks are computed on a 32 grid from a few numbers, so the bars
# stay long and thin (rows, not pixels). Favicons are drawn by hand on the
# 16px grid with every edge on a whole pixel, so they stay crisp.

def R(y, *segs, shift=0):
    return (y, list(segs), shift)


def a_rows(n, bar, top_hw, leg, crossbar, shift_row, shift):
    """Rows for an A of n bars filling y 4..28 and x 1..31 on a 32 grid.

    top_hw: half-width of the apex bar; leg: length of each leg piece in
    split rows; crossbar: index of the solid crossbar row; shift_row /
    shift: which row slips sideways and by how much.
    """
    gap = (24 - n * bar) / (n - 1)
    rows = []
    for i in range(n):
        y = 4 + i * (bar + gap)
        hw = top_hw + (15 - top_hw) * i / (n - 1)
        inner = hw - leg
        if i == crossbar or inner <= 0.4:
            segs = [(16 - hw, 16 + hw)]
        else:
            segs = [(16 - hw, 16 - inner), (16 + inner, 16 + hw)]
        segs = [(round(a, 3), round(b, 3)) for a, b in segs]
        rows.append(R(round(y, 3), *segs, shift=shift if i == shift_row else 0))
    return rows


VARIATIONS = [
    {
        'key': 'rows5', 'name': 'Five rows', 'grid': 32, 'bar': 2.6,
        'idea': 'Five heavy bars. The crossbar is pushed well right: the '
                'strongest, most graphic offset.',
        'rows': a_rows(5, 2.6, 4, 5, crossbar=2, shift_row=2, shift=3),
        'fav': {'bar': 2, 'rows': [
            R(1, (5, 11)),
            R(4, (4, 7), (9, 12)),
            R(7, (3, 13), shift=2),
            R(10, (2, 6), (10, 14)),
            R(13, (1, 5), (11, 15)),
        ]},
    },
    {
        'key': 'rows7', 'name': 'Seven rows', 'grid': 32, 'bar': 1.2,
        'idea': 'Seven hairline bars with air between them: the most '
                'minimal, line-drawn version. The crossbar steps right.',
        'rows': a_rows(7, 1.2, 3, 5, crossbar=3, shift_row=3, shift=2),
        'fav': {'bar': 1, 'rows': [
            R(2, (7, 9)),
            R(4, (6, 10)),
            R(6, (5, 7), (9, 11)),
            R(8, (4, 12), shift=1),
            R(10, (3, 6), (10, 13)),
            R(12, (2, 5), (11, 14)),
            R(14, (1, 4), (12, 15)),
        ]},
    },
    {
        'key': 'rows9', 'name': 'Nine rows', 'grid': 32, 'bar': 1.6,
        'idea': 'Nine dense bars, like a full rent-roll page. The offset is '
                'the subtlest: one leg row slips a single unit, the way a '
                'real mismatch hides in a long list.',
        'rows': a_rows(9, 1.6, 2.5, 5, crossbar=5, shift_row=6, shift=1),
        # Nine 1px bars need 9 + 8 = 17 pixel rows, one more than a
        # favicon has. So at 16px the two apex bars merge into one 2px
        # cap (8 visible rows); the slipped leg row keeps its slip.
        'fav': {'bar': 1, 'tall_first': True, 'rows': [
            R(0, (6, 10)),
            R(3, (5, 7), (9, 11)),
            R(5, (4, 7), (9, 12)),
            R(7, (4, 6), (10, 12)),
            R(9, (3, 13)),
            R(11, (2, 5), (11, 14), shift=1),
            R(13, (2, 5), (11, 14)),
            R(15, (1, 4), (12, 15)),
        ]},
    },
]


def bars(rows, bar, ink, accent, tall_first=False):
    out = []
    for i, (y, segs, shift) in enumerate(rows):
        h = bar * 2 if (tall_first and i == 0) else bar
        fill = accent if shift else ink
        for x0, x1 in segs:
            out.append(f'<rect x="{x0 + shift:g}" y="{y:g}" width="{round(x1 - x0, 3):g}" '
                       f'height="{h:g}" fill="{fill}"/>')
    return ''.join(out)


def mark_body(v, ink, accent):
    return bars(v['rows'], v['bar'], ink, accent)


def bbox(rows, bar, tall_first=False):
    xs = [x + s for _, segs, s in rows for seg in segs for x in seg]
    ys = [rows[0][0], rows[-1][0] + bar]
    return min(xs), min(ys), max(xs), max(ys)


# ------------------------------------------------------------- wordmark

def wordmark_path(text='Abstractly', weight=500, tracking=-0.025):
    """Return (svg path d, advance width, cap height) in font units."""
    font = TTFont(FONT)
    inst = instancer.instantiateVariableFont(font, {'wght': weight})
    inst.flavor = None
    buf = io.BytesIO()
    inst.save(buf)
    data = buf.getvalue()

    hbfont = hb.Font(hb.Face(data))
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
        # Flip y: font units are y-up, SVG is y-down.
        gs[order[info.codepoint]].draw(
            TransformPen(pen, (1, 0, 0, -1, x + pos.x_offset, -pos.y_offset)))
        x += pos.x_advance + tracking * upm
    x -= tracking * upm
    return pen.getCommands(), x, tt['OS/2'].sCapHeight


WM_D, WM_W, WM_CAP = wordmark_path()


def lockup(v, ink, accent):
    """Mark scaled to 32 units tall + wordmark with a 19-unit cap height."""
    x0, y0, x1, y1 = bbox(v['rows'], v['bar'])
    ms = 32 / (y1 - y0)
    mark_w = (x1 - x0) * ms
    cap = 19.0
    s = cap / WM_CAP
    tx = mark_w + 12
    ty = 16 + cap / 2
    width = tx + WM_W * s
    return width, (
        f'<g transform="scale({ms:.5f}) translate({-x0:g} {-y0:g})">{mark_body(v, ink, accent)}</g>'
        f'<path fill="{ink}" transform="translate({tx:.3f} {ty:.3f}) scale({s:.6f})" d="{WM_D}"/>'
    )


# ---------------------------------------------------------------- files

def svg(view_w, view_h, inner, label, w=None, h=None):
    size = f' width="{w}" height="{h}"' if w else ''
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {view_w:g} {view_h:g}"{size} '
            f'role="img" aria-label="{label}">{inner}</svg>\n')


def mark_svg(v, way, w=None):
    ink, accent, _ = COLORWAYS[way]
    g = v['grid']
    return svg(g, g, mark_body(v, ink, accent), 'Abstractly', w, w)


def lockup_svg(v, way, h=None):
    ink, accent, _ = COLORWAYS[way]
    width, inner = lockup(v, ink, accent)
    return svg(round(width, 2), 32, inner, 'Abstractly',
               round(width * h / 32, 1) if h else None, h)


def favicon_svg(v, gold):
    # White bars on a black tile, so it reads in light and dark tabs alike.
    f = v['fav']
    inner = (f'<rect width="16" height="16" rx="2.5" fill="{BLACK}"/>'
             + bars(f['rows'], f['bar'], WHITE, GOLD if gold else WHITE, f.get('tall_first')))
    return svg(16, 16, inner, 'Abstractly')


def write_files():
    for old in glob.glob(os.path.join(HERE, '*.svg')):
        os.remove(old)
    for v in VARIATIONS:
        k = v['key']
        for way in COLORWAYS:
            with open(os.path.join(HERE, f'{k}-mark-{way}.svg'), 'w') as fh:
                fh.write(mark_svg(v, way))
            with open(os.path.join(HERE, f'{k}-lockup-{way}.svg'), 'w') as fh:
                fh.write(lockup_svg(v, way))
        with open(os.path.join(HERE, f'{k}-favicon.svg'), 'w') as fh:
            fh.write(favicon_svg(v, False))
        with open(os.path.join(HERE, f'{k}-favicon-gold.svg'), 'w') as fh:
            fh.write(favicon_svg(v, True))


# ------------------------------------------------------------- preview

def preview():
    cols = []
    for n, v in enumerate(VARIATIONS, 1):
        k = v['key']
        sizes = ''.join(
            f'<div class="fav-cell"><img src="{k}-favicon{g}.svg" width="{px}" height="{px}" alt="">'
            f'<span>{px}px</span></div>' for g in ('', '-gold') for px in (16, 32))
        files = ''.join(f'<li><a href="{k}-{kind}-{way}.svg">{k}-{kind}-{way}.svg</a></li>'
                        for kind in ('mark', 'lockup') for way in COLORWAYS)
        cols.append(f'''
<section class="concept" id="{k}">
  <header class="concept-head">
    <span class="num">0{n}</span>
    <h2>{v["name"]}</h2>
    <p>{v["idea"]}</p>
  </header>

  <div class="pair">
    <div class="panel black big">{mark_svg(v, "white")}</div>
    <div class="panel black big">{mark_svg(v, "white-gold")}</div>
    <div class="panel white big">{mark_svg(v, "black")}</div>
    <div class="panel white big">{mark_svg(v, "black-gold")}</div>
  </div>

  <h3>Lockup</h3>
  <div class="panel black lock">{lockup_svg(v, "white", 44)}</div>
  <div class="panel black lock">{lockup_svg(v, "white-gold", 44)}</div>
  <div class="panel white lock">{lockup_svg(v, "black", 44)}</div>

  <h3>In the header</h3>
  <div class="fake-header black"><span class="brand">{lockup_svg(v, "white", 24)}</span>
    <nav><span>How it works</span><span>Pricing</span><span class="cta">Book a demo</span></nav></div>
  <div class="fake-header white"><span class="brand">{lockup_svg(v, "black-gold", 24)}</span>
    <nav><span>How it works</span><span>Pricing</span><span class="cta">Book a demo</span></nav></div>

  <h3>Favicon</h3>
  <div class="tabs">
    <div class="tab dark-chrome"><img src="{k}-favicon.svg" width="16" height="16" alt="">Abstractly — Deal Mismatch</div>
    <div class="tab light-chrome"><img src="{k}-favicon-gold.svg" width="16" height="16" alt="">Abstractly — Deal Mismatch</div>
  </div>
  <div class="favs panel black">{sizes}</div>
  <div class="favs bare">
    <div class="panel black small"><canvas class="px" data-src="{k}-favicon.svg" width="16" height="16"></canvas><span>real 16px pixels ×6</span></div>
    <div class="panel black small"><canvas class="px" data-src="{k}-favicon-gold.svg" width="16" height="16"></canvas><span>gold, real 16px ×6</span></div>
  </div>

  <h3>Files</h3>
  <ul class="files">{files}
    <li><a href="{k}-favicon.svg">{k}-favicon.svg</a> · <a href="{k}-favicon-gold.svg">gold</a></li>
  </ul>
</section>''')

    with open(os.path.join(HERE, 'index.html'), 'w') as fh:
        fh.write(TEMPLATE.replace('{{CONCEPTS}}', ''.join(cols)))


TEMPLATE = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Abstractly logo concepts</title>
<link rel="icon" href="rows7-favicon.svg" type="image/svg+xml">
<style>
@font-face {
  font-family: 'Inter';
  src: url('../../frontend/fonts/inter-latin-var.woff2') format('woff2');
  font-weight: 100 900;
}
:root {
  --black: #0a0a0b; --panel: #000000; --white: #ffffff; --gold: #b68a4e;
  --line: rgba(255, 255, 255, 0.12); --muted: rgba(255, 255, 255, 0.6);
}
* { box-sizing: border-box; }
html { background: var(--black); }
body { margin: 0; font-family: 'Inter', system-ui, sans-serif; color: var(--white); }
.page-head { max-width: 1320px; margin: 0 auto; padding: 56px 24px 8px; }
.eyebrow { font: 500 12px/1 ui-monospace, 'SF Mono', Menlo, monospace; letter-spacing: .14em;
  text-transform: uppercase; color: var(--gold); }
h1 { font-size: clamp(28px, 4vw, 44px); letter-spacing: -0.03em; margin: 14px 0 10px; font-weight: 600; }
.page-head p { color: var(--muted); max-width: 660px; margin: 0; line-height: 1.55; }
.grid { max-width: 1320px; margin: 0 auto; padding: 32px 24px 80px;
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 28px; }
.concept { min-width: 0; }
.concept-head { min-height: 150px; margin-bottom: 16px; }
.num { font: 500 12px ui-monospace, Menlo, monospace; color: var(--gold); }
h2 { margin: 6px 0 8px; font-size: 22px; font-weight: 600; letter-spacing: -0.02em; }
.concept-head p { margin: 0; color: var(--muted); font-size: 14px; line-height: 1.5; }
h3 { font: 500 11px ui-monospace, Menlo, monospace; letter-spacing: .14em; text-transform: uppercase;
  color: var(--muted); margin: 28px 0 10px; }
.panel { border: 1px solid var(--line); border-radius: 6px; display: flex;
  align-items: center; justify-content: center; }
.panel.black { background: var(--panel); }
.panel.white { background: var(--white); color: var(--black); border-color: transparent; }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.panel.big { aspect-ratio: 1 / 1; }
.panel.big svg { width: 64%; height: auto; }
.panel.lock { height: 112px; margin-bottom: 10px; padding: 0 16px; }
.panel.lock svg { max-width: 100%; height: auto; }
.fake-header { display: flex; align-items: center; justify-content: space-between; gap: 12px;
  height: 60px; padding: 0 16px; border-radius: 6px; margin-bottom: 10px; font-size: 12px; }
.fake-header.black { background: var(--panel); border: 1px solid var(--line); color: var(--muted); }
.fake-header.white { background: var(--white); color: #55534d; }
.fake-header .brand { display: flex; }
.fake-header nav { display: flex; gap: 14px; align-items: center; white-space: nowrap; }
.fake-header .cta { background: var(--gold); color: var(--black); padding: 6px 10px; border-radius: 3px; font-weight: 600; }
.tabs { display: grid; gap: 8px; margin-bottom: 12px; }
.tab { display: flex; align-items: center; gap: 8px; font-size: 12px; height: 34px; padding: 0 12px;
  border-radius: 8px 8px 0 0; width: 240px; max-width: 100%; white-space: nowrap; overflow: hidden; }
.tab img { flex-shrink: 0; }
.dark-chrome { background: #2a2a2e; color: #e8e6e1; }
.light-chrome { background: #ffffff; color: #222; border: 1px solid #ddd; border-bottom: 0; }
.favs { display: flex; gap: 14px; align-items: flex-end; justify-content: center; padding: 18px; margin-bottom: 12px; }
.fav-cell, .small { display: flex; flex-direction: column; align-items: center; gap: 8px; }
.fav-cell span, .small span { font: 11px ui-monospace, Menlo, monospace; color: var(--muted); }
.favs.bare { padding: 0; align-items: stretch; }
.favs.bare .panel { flex: 1; padding: 16px 8px; }
canvas.px { width: 96px; height: 96px; image-rendering: pixelated; }
.files { list-style: none; padding: 0; margin: 0; font: 12px/1.9 ui-monospace, Menlo, monospace; }
.files a { color: var(--gold); text-decoration: none; }
.files a:hover { text-decoration: underline; }
@media (max-width: 1100px) {
  .grid { grid-template-columns: 1fr 1fr; }
  .fake-header nav span:not(.cta) { display: none; }
}
@media (max-width: 720px) {
  .grid { grid-template-columns: 1fr; padding: 24px 16px 64px; }
  .page-head { padding: 40px 16px 0; }
  .concept-head { min-height: 0; }
}
</style>
</head>
<body>
<header class="page-head">
  <div class="eyebrow">Abstractly · Logo exploration · Round 2</div>
  <h1>An A made of rent-roll rows</h1>
  <p>Stacked horizontal bars lengthen into the A; the counter is a gap; one bar is shifted:
  the mismatch we caught. White on black, with an optional gold shifted bar. Wordmark is
  Inter Medium, outlined, tracked slightly tight. Each favicon panel shows the real
  16&times;16 pixels, enlarged.</p>
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
    print(len(glob.glob(os.path.join(HERE, '*.svg'))), 'svgs + index.html')
