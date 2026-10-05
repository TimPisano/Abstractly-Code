#!/usr/bin/env node
// Render the chosen mark's raster assets into frontend/, headlessly:
//   frontend/og-image.png        1200x630, from og/og-image.html
//   frontend/apple-touch-icon.png 180x180, white mark on near-black
//   frontend/favicon.ico          16 + 32 + 48 px PNGs from final/favicon.svg
// Run `python3 build.py` first (it writes final/). Then:
//   node design/logo/render_assets.mjs        # all three
//   node design/logo/render_assets.mjs og     # only og-image.png
// Uses the same Playwright lookup as .claude/tools/screenshots.mjs.
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.join(HERE, '..', '..', 'frontend');

function loadPlaywright() {
  const tryReq = (base) => { try { return createRequire(path.join(base, 'x.js'))('playwright'); } catch { return null; } };
  let pw = tryReq(process.cwd());
  if (pw) return pw;
  const npx = path.join(os.homedir(), '.npm/_npx');
  for (const d of fs.existsSync(npx) ? fs.readdirSync(npx) : []) {
    pw = tryReq(path.join(npx, d));
    if (pw) return pw;
  }
  console.error('Playwright not found. Run: npx -y playwright@latest install chromium');
  process.exit(2);
}

// An .ico is a 6-byte header, a 16-byte entry per image, then the images;
// modern ICOs may embed PNGs as-is.
function ico(pngs) {
  const head = Buffer.alloc(6 + 16 * pngs.length);
  head.writeUInt16LE(0, 0); head.writeUInt16LE(1, 2); head.writeUInt16LE(pngs.length, 4);
  let offset = head.length;
  pngs.forEach(({ size, data }, i) => {
    const e = 6 + 16 * i;
    head.writeUInt8(size >= 256 ? 0 : size, e);
    head.writeUInt8(size >= 256 ? 0 : size, e + 1);
    head.writeUInt16LE(1, e + 4);   // colour planes
    head.writeUInt16LE(32, e + 6);  // bits per pixel
    head.writeUInt32LE(data.length, e + 8);
    head.writeUInt32LE(offset, e + 12);
    offset += data.length;
  });
  return Buffer.concat([head, ...pngs.map((p) => p.data)]);
}

const { chromium } = loadPlaywright();
const browser = await chromium.launch({ headless: true });

async function shoot(url, width, height, out, opts = {}) {
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  await page.goto(url);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  const buf = await page.screenshot({ omitBackground: !!opts.transparent });
  await page.close();
  if (out) fs.writeFileSync(out, buf);
  return buf;
}

const fileUrl = (p) => pathToFileURL(p).href;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'abstractly-assets-'));

// OG image.
await shoot(fileUrl(path.join(HERE, 'og', 'og-image.html')), 1200, 630, path.join(FRONTEND, 'og-image.png'));

if (process.argv[2] === 'og') {
  await browser.close();
  console.log('wrote og-image.png');
  process.exit(0);
}

// Apple touch icon: iOS rounds the corners itself, so the square is full-bleed.
const markUrl = fileUrl(path.join(HERE, 'final', 'abstractly-mark-white.svg'));
const touch = path.join(tmp, 'touch.html');
fs.writeFileSync(touch, `<html><body style="margin:0;width:180px;height:180px;background:#0a0a0b;display:flex;align-items:center;justify-content:center"><img src="${markUrl}" style="width:112px;height:auto;margin-top:-2px"></body></html>`);
await shoot(fileUrl(touch), 180, 180, path.join(FRONTEND, 'apple-touch-icon.png'));

// favicon.ico: each size rasterised straight from the SVG at that size.
const favUrl = fileUrl(path.join(HERE, 'final', 'favicon.svg'));
const pngs = [];
for (const size of [16, 32, 48]) {
  const f = path.join(tmp, `fav${size}.html`);
  fs.writeFileSync(f, `<html><body style="margin:0;background:transparent"><img src="${favUrl}" width="${size}" height="${size}" style="display:block"></body></html>`);
  pngs.push({ size, data: await shoot(fileUrl(f), size, size, path.join(tmp, `fav${size}.png`), { transparent: true }) });
}
fs.writeFileSync(path.join(FRONTEND, 'favicon.ico'), ico(pngs));

await browser.close();
console.log('wrote og-image.png, apple-touch-icon.png, favicon.ico; favicon PNGs in', tmp);
