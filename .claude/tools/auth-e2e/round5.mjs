// Round 4 headless checks (feature/auth-hardening). Never opens a visible browser.
// node round4.mjs [chromium|webkit]
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { DIR, SITE, API, loadPlaywright } from './lib.mjs';
const pw = loadPlaywright();
const S = DIR, OUTBOX = S + '/outbox', DB = S + '/e2e.db';
const engine = process.argv[2] || 'chromium';
const SHOTS = path.join(S, 'shots', `r5-${engine}`); fs.mkdirSync(SHOTS, { recursive: true });
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


const U = `r5-${uniq}@example.test`, PW1 = 'uniform first long phrase', PW2 = 'uniform second long phrase';
try {
  // ---- return to where you were after the session ends mid-use ----
  let ctx = await ctxNew(); let p = await signupAndFinish(ctx, U, 'Uma Uniform', `Uniform ${uniq}`, PW1, true);
  await p.click('.nav-item[data-view="tasks"]'); await p.waitForTimeout(1200);
  sql(`update users set session_version = session_version + 1 where email='${U}'`);
  await p.click('.nav-item[data-view="alerts"]').catch(() => {});
  await p.waitForURL(/login\.html/, { timeout: 15000 }).catch(() => {});
  check('session ended mid-use -> login remembers the screen', /login\.html/.test(p.url()), p.url());
  await p.fill('#email', U); await p.fill('#password', PW1);
  await Promise.all([p.waitForURL(/index\.html/), p.click('#submitButton')]);
  await p.waitForFunction(() => window.CURRENT_USER, null, { timeout: 15000 }); await p.waitForTimeout(1500);
  const active = await p.evaluate(() => (document.querySelector('.view.active') || {}).id);
  check('signing back in returns to that screen, not the dashboard', /view-(tasks|alerts)/.test(active || ''), `${p.url()} active=${active}`);
  await p.goto(`${SITE}/login.html?next=https://evil.example/x`, { waitUntil: 'networkidle' });
  await p.fill('#email', U); await p.fill('#password', PW1);
  await Promise.all([p.waitForURL(/index\.html/), p.click('#submitButton')]);
  check('a "next" that is not a plain view name is ignored (no open redirect)', p.url().endsWith('/app/index.html'), p.url());
  await ctx.close();

  // ---- logging in during a reset, two devices, UI only ----
  const phoneCtx = await ctxNew(phone); const laptop = await ctxNew();
  const ph = await phoneCtx.newPage(); watch(ph, 'phone');
  await ph.goto(`${SITE}/forgot-password.html`, { waitUntil: 'networkidle' });
  await ph.fill('#email', U); await ph.click('#submitButton'); await ph.waitForSelector('[data-view="sent"]:not([hidden])');
  const rmail = await waitMail(U, countTo(U) + 0 || 1).catch(() => null);
  const resetMail = mails().filter((m) => m.to === U && m.subject.startsWith('Reset')).pop();
  await ph.goto(linkIn(resetMail), { waitUntil: 'networkidle' }); await ph.waitForSelector('[data-view="form"]:not([hidden])');
  const lp = await laptop.newPage(); watch(lp, 'laptop');
  await login(lp, U, PW1, true);   // remembered the old password and signed in meanwhile
  check('signing in with the old password while a reset link is open works', lp.url().endsWith('index.html'));
  await ph.fill('#password', PW2);
  await Promise.all([ph.waitForURL(/index\.html/, { timeout: 20000 }), ph.click('#submitButton')]);
  check('finishing the reset afterwards still works (phone signed in)', ph.url().includes('index.html'), ph.url());
  await lp.click('.nav-item[data-view="tasks"]').catch(() => {});
  await lp.waitForURL(/login\.html/, { timeout: 15000 }).catch(() => {});
  check('the laptop that signed in meanwhile is signed out, with a reason', lp.url().includes('login.html') && (await lp.textContent('#loginNotice').catch(() => '')).includes('session ended'), lp.url());
  await lp.screenshot({ path: `${SHOTS}/02-laptop-after-reset.png` });
  await ph.screenshot({ path: `${SHOTS}/02-phone-after-reset.png` });
  await phoneCtx.close(); await laptop.close();
} catch (e) { check('script error', false, e.stack.split('\n').slice(0, 3).join(' | ')); }
check('no page errors', errors.filter((e) => !/access control checks/.test(e)).length === 0, errors.slice(0, 3).join(' || '));
await browser.close();
console.log(`\nround5 ${engine}: ${results.filter(Boolean).length}/${results.length}`);
