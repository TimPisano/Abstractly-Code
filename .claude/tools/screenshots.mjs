#!/usr/bin/env node
// Headless visual check: screenshots every page at several widths and
// scroll positions, and records console errors and WebGL availability.
// Never opens a visible browser (CLAUDE.md rule 1).
//
//   node .claude/tools/screenshots.mjs <url> [<url> ...] [--out DIR]
//        [--widths 1440,768,375] [--wait 1200]
//
// Writes PNGs plus manifest.json to --out (default: a fresh temp dir) and
// prints every PNG path. Whoever runs this MUST open (Read) each PNG before
// saying anything about how the page looks; "the script ran" is not a check.
//
// Playwright isn't a project dependency; this finds it in a local
// node_modules or the npx cache (`npx playwright install chromium` once).
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

function loadPlaywright() {
  const tryReq = (base) => { try { return createRequire(path.join(base, 'x.js'))('playwright'); } catch { return null; } };
  let pw = tryReq(process.cwd());
  if (pw) return pw;
  const npx = path.join(os.homedir(), '.npm/_npx');
  try {
    for (const d of fs.readdirSync(npx)) {
      pw = tryReq(path.join(npx, d));
      if (pw) return pw;
    }
  } catch {}
  console.error('Playwright not found. Run: npx -y playwright@latest install chromium');
  process.exit(2);
}

const args = process.argv.slice(2);
const opt = (name, dflt) => { const i = args.indexOf(name); return i >= 0 ? args.splice(i, 2)[1] : dflt; };
const outDir = opt('--out', fs.mkdtempSync(path.join(os.tmpdir(), 'shots-')));
const widths = opt('--widths', '1440,768,375').split(',').map(Number);
const waitMs = Number(opt('--wait', '1200'));
const urls = args.filter((a) => !a.startsWith('--'));
if (!urls.length) { console.error('usage: screenshots.mjs <url> [...] [--out DIR] [--widths 1440,768,375]'); process.exit(2); }

const { chromium } = loadPlaywright();
// SwiftShader flags let WebGL/shader backgrounds render in headless mode;
// without them a canvas can silently come out blank and "look fine".
const browser = await chromium.launch({
  headless: true,
  args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
});
fs.mkdirSync(outDir, { recursive: true });
const manifest = [];
for (const url of urls) {
  const slug = url.replace(/^https?:\/\//, '').replace(/[^a-z0-9]+/gi, '_').slice(0, 60);
  for (const width of widths) {
    const page = await browser.newPage({ viewport: { width, height: width < 600 ? 812 : 900 } });
    const errors = [];
    page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errors.push(`${m.type()}: ${m.text()}`); });
    page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 }).catch((e) => errors.push(`goto: ${e.message}`));
    await page.waitForTimeout(waitMs);
    const info = await page.evaluate(() => {
      const c = document.createElement('canvas');
      return {
        height: document.documentElement.scrollHeight,
        overflowX: document.documentElement.scrollWidth > window.innerWidth,
        webgl: !!(c.getContext('webgl2') || c.getContext('webgl')),
        canvases: document.querySelectorAll('canvas').length,
      };
    });
    const shots = [];
    for (const pct of [0, 25, 50, 75, 100]) {
      const y = Math.round((info.height - page.viewportSize().height) * pct / 100);
      await page.evaluate((yy) => window.scrollTo(0, Math.max(0, yy)), y);
      await page.waitForTimeout(400); // let scroll-linked effects settle
      const file = path.join(outDir, `${slug}__w${width}__s${String(pct).padStart(3, '0')}.png`);
      await page.screenshot({ path: file });
      shots.push(file);
    }
    const full = path.join(outDir, `${slug}__w${width}__full.png`);
    // Chromium can't capture arbitrarily tall pages; cap it and keep going.
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: full, fullPage: true, clip: { x: 0, y: 0, width, height: Math.min(info.height, 12000) } })
      .then(() => shots.push(full))
      .catch((e) => errors.push(`full-page screenshot skipped: ${e.message.split('\n')[0]}`));
    manifest.push({ url, width, ...info, errors, shots });
    await page.close();
  }
}
await browser.close();
fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify(manifest, null, 2));
for (const m of manifest) {
  console.log(`\n${m.url} @ ${m.width}px  height=${m.height} overflowX=${m.overflowX} webgl=${m.webgl} canvases=${m.canvases}`);
  for (const e of m.errors) console.log(`  CONSOLE ${e}`);
  for (const s of m.shots) console.log(`  ${s}`);
}
console.log(`\nmanifest: ${path.join(outDir, 'manifest.json')}`);
console.log('Now Read EVERY PNG above before reporting.');
