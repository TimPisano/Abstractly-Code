// Round 4 headless checks (feature/auth-hardening). Never opens a visible browser.
// node round4.mjs [chromium|webkit]
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { DIR, SITE, API, loadPlaywright } from './lib.mjs';
const pw = loadPlaywright();
const S = DIR, OUTBOX = S + '/outbox', DB = S + '/e2e.db';
const engine = process.argv[2] || 'chromium';
const SHOTS = path.join(S, 'shots', `r6-${engine}`); fs.mkdirSync(SHOTS, { recursive: true });
const results = []; const check = (n, ok, d = '') => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${d ? '  -- ' + d : ''}`); };
const sql = (q) => execFileSync('sqlite3', ['-cmd', '.timeout 5000', DB, q]).toString().trim();
const mails = () => fs.readdirSync(OUTBOX).sort().map((f) => JSON.parse(fs.readFileSync(`${OUTBOX}/${f}`)));
const linkIn = (m) => m.text.match(/https?:\/\/\S+token=[A-Za-z0-9_\-]+/)[0];
const countTo = (to, subj = '') => mails().filter((m) => m.to === to && m.subject.startsWith(subj)).length;
async function waitMail(to, n, ms = 15000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { const m = mails().filter((x) => x.to === to); if (m.length >= n) return m[n - 1]; await new Promise((r) => setTimeout(r, 150)); } throw new Error('no mail ' + n + ' to ' + to); }
const browser = await pw[engine].launch({ headless: true });
const phone = engine === 'webkit' ? pw.devices['iPhone 13'] : pw.devices['Pixel 5'];
const desk = { viewport: { width: 1440, height: 900 } };
async function ctxNew(dev = desk) { const c = await browser.newContext({ ...dev }); await c.addInitScript((a) => localStorage.setItem('abstractly.apiBaseOverride', a), API); return c; }
const uniq = `${engine}${Date.now() % 100000}`;
const errors = [];
const watch = (p, l) => { p.on('pageerror', (e) => errors.push(`${l}: ${e.message}`)); };

async function signupAndFinish(ctx, email, name, company, password, remember = true) {
  const p = await ctx.newPage(); watch(p, 'signup ' + email);
  await p.goto(`${SITE}/signup.html`, { waitUntil: 'networkidle' });
  await p.fill('#name', name); await p.fill('#email', email); await p.fill('#company', company);
  const n = countTo(email) + 1;
  await p.click('#submitButton'); await p.waitForSelector('[data-view="sent"]:not([hidden])');
  const m = await waitMail(email, n);
  await p.goto(linkIn(m), { waitUntil: 'networkidle' }); await p.waitForSelector('[data-view="form"]:not([hidden])');
  await p.fill('#password', password);
  if (!remember) await p.uncheck('#remember');
  await Promise.all([p.waitForURL(/index\.html/), p.click('#submitButton')]);
  await p.waitForFunction(() => window.CURRENT_USER, null, { timeout: 15000 });
  return p;
}
async function login(p, email, password, remember = true) {
  await p.goto(`${SITE}/login.html`, { waitUntil: 'networkidle' });
  await p.fill('#email', email); await p.fill('#password', password);
  if (!remember) await p.uncheck('#remember');
  await Promise.all([p.waitForURL(/index\.html/), p.click('#submitButton')]);
  await p.waitForFunction(() => window.CURRENT_USER, null, { timeout: 15000 });
}
const viewOf = (p) => p.evaluate(() => [...document.querySelectorAll('[data-view]')].filter((e) => !e.hidden).map((e) => e.dataset.view).join(','));



const V = `r6-${uniq}@example.test`;
try {
  let ctx = await ctxNew(phone); let p = await ctx.newPage(); watch(p, 'paste');
  await p.goto(`${SITE}/signup.html`, { waitUntil: 'networkidle' });
  await p.fill('#name', 'Vic Victor'); await p.fill('#email', V); await p.fill('#company', `Victor ${uniq}`);
  await p.click('#submitButton'); await p.waitForSelector('[data-view="sent"]:not([hidden])');
  const link = linkIn(await waitMail(V, 1));
  for (const junk of ['.', ')', '%20', '&utm_source=mail']) {
    const q = await ctx.newPage(); watch(q, 'paste' + junk);
    await q.goto(link + junk, { waitUntil: 'networkidle' }); await q.waitForTimeout(800);
    check(`link pasted with trailing "${junk}" still opens the form`, (await viewOf(q)) === 'form', await viewOf(q));
    if (junk === '.') {
      const u = await q.evaluate(() => { const i = document.getElementById('username'); const r = i.getBoundingClientRect(); return { v: i.value, ac: i.autocomplete, shown: getComputedStyle(i).display !== 'none' }; });
      check('username field present for password managers (filled, not display:none)', u.v === V && u.ac === 'username' && u.shown, JSON.stringify(u));
    }
    await q.close();
  }
  // a link scanner that only opens the page must not burn the link
  const scanner = await ctx.newPage(); await scanner.goto(link, { waitUntil: 'networkidle' }); await scanner.waitForTimeout(800); await scanner.close();
  const r = await ctx.newPage(); await r.goto(link, { waitUntil: 'networkidle' }); await r.waitForTimeout(800);
  check('opening a link (e.g. an email security scanner) does not use it up', (await viewOf(r)) === 'form', await viewOf(r));
  await ctx.close();
} catch (e) { check('script error', false, e.stack.split('\n').slice(0, 3).join(' | ')); }
check('no page errors', errors.length === 0, errors.slice(0, 3).join(' || '));
await browser.close();
console.log(`\nround6 ${engine}: ${results.filter(Boolean).length}/${results.length}`);
