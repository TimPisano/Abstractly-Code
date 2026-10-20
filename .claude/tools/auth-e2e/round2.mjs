// Round 2 headless checks: bfcache after sign-out, slow email, revoked session mid-use, 429 + offline UX.
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync, execSync } from 'node:child_process';
import { DIR, SITE, API, loadPlaywright } from './lib.mjs';
const pw = loadPlaywright();
const S = DIR, OUTBOX = S + '/outbox', DB = S + '/e2e.db';
const engine = process.argv[2] || 'chromium';
const SHOTS = path.join(S, 'shots', `r2-${engine}`); fs.mkdirSync(SHOTS, { recursive: true });
const results = []; const check = (n, ok, d = '') => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${d ? '  -- ' + d : ''}`); };
const sql = (q) => execFileSync('sqlite3', ['-cmd', '.timeout 5000', DB, q]).toString().trim();
const mails = () => fs.readdirSync(OUTBOX).sort().map((f) => JSON.parse(fs.readFileSync(`${OUTBOX}/${f}`)));
const linkIn = (m) => m.text.match(/https?:\/\/\S+token=[A-Za-z0-9_\-]+/)[0];
async function waitMail(to, n, ms = 20000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { const m = mails().filter((x) => x.to === to); if (m.length >= n) return m[n - 1]; await new Promise((r) => setTimeout(r, 200)); } throw new Error('no mail ' + n); }
const browser = await pw[engine].launch({ headless: true });
const dev = engine === 'webkit' ? pw.devices['iPhone 13'] : { viewport: { width: 1440, height: 900 } };
async function ctxNew() { const c = await browser.newContext({ ...dev }); await c.addInitScript((a) => localStorage.setItem('abstractly.apiBaseOverride', a), API); return c; }
const uniq = `${engine}${Date.now() % 100000}`;
const email = `r2-${uniq}@example.test`;
try {
  // slow email: server started with SMTP_DELAY
  let ctx = await ctxNew(); let p = await ctx.newPage();
  await p.goto(`${SITE}/signup.html`, { waitUntil: 'networkidle' });
  await p.fill('#name', 'Riley Chen'); await p.fill('#email', email); await p.fill('#company', `Chen Capital ${uniq}`);
  const t0 = Date.now(); await p.click('#submitButton'); await p.waitForSelector('[data-view="sent"]:not([hidden])');
  const elapsed = Date.now() - t0;
  check('slow SMTP does not slow the signup page', elapsed < 3000, `${elapsed}ms`);
  const m = await waitMail(email, 1);
  await p.goto(linkIn(m), { waitUntil: 'networkidle' }); await p.waitForSelector('[data-view="form"]:not([hidden])');
  await p.fill('#password', 'riley picks a long one');
  await Promise.all([p.waitForURL(/index\.html/), p.click('#submitButton')]);
  await p.waitForFunction(() => window.CURRENT_USER, null, { timeout: 15000 });
  await p.waitForTimeout(1000);

  // bfcache after sign out
  await Promise.all([p.waitForURL(/login\.html/), p.click('#signOutBtn')]);
  await p.goBack().catch(() => {});
  await p.waitForTimeout(2500);
  const shellVisible = await p.evaluate(() => { const s = document.getElementById('appShell'); return !!s && getComputedStyle(s).display !== 'none'; }).catch(() => false);
  check('back after sign out does not show the dashboard', !shellVisible, p.url());
  await p.screenshot({ path: `${SHOTS}/01-back-after-signout.png` });
  await ctx.close();

  // revoked mid-use: sign in, then a reset elsewhere bumps session_version
  ctx = await ctxNew(); p = await ctx.newPage();
  await p.goto(`${SITE}/login.html`, { waitUntil: 'networkidle' });
  await p.fill('#email', email); await p.fill('#password', 'riley picks a long one');
  await Promise.all([p.waitForURL(/index\.html/), p.click('#submitButton')]);
  await p.waitForFunction(() => window.CURRENT_USER, null, { timeout: 15000 });
  sql(`update users set session_version = session_version + 1 where email='${email}'`);
  await p.click('.nav-item[data-view="tasks"]').catch(() => {});
  await p.waitForURL(/login\.html/, { timeout: 15000 }).catch(() => {});
  check('session revoked mid-use -> login with notice', p.url().includes('login.html') && (await p.textContent('#loginNotice').catch(() => '')).includes('session ended'), p.url());
  await p.screenshot({ path: `${SHOTS}/02-revoked-mid-use.png` });

  // 429 message
  for (let i = 0; i < 8; i++) {
    await p.fill('#email', `nobody-${uniq}@example.test`); await p.fill('#password', 'wrong wrong wrong');
    await p.click('#submitButton'); await p.waitForFunction(() => document.querySelector('#formStatus').textContent.length > 0);
  }
  const msg = await p.textContent('#formStatus');
  check('rate-limited login says so plainly', msg.includes('Too many'), msg);
  await p.screenshot({ path: `${SHOTS}/03-login-429.png` });
  await ctx.close();

  // offline
  execSync(`pkill -f "auth-e2e/devserver.py"`); await new Promise((r) => setTimeout(r, 1000));
  ctx = await ctxNew(); p = await ctx.newPage();
  await p.goto(`${SITE}/login.html`, { waitUntil: 'load' });
  await p.fill('#email', email); await p.fill('#password', 'riley picks a long one');
  await p.click('#submitButton');
  await p.waitForFunction(() => document.querySelector('#formStatus').textContent.length > 0, null, { timeout: 10000 });
  const off = await p.textContent('#formStatus');
  check('server unreachable -> friendly message, button usable again', off.includes("Couldn't reach") && !(await p.isDisabled('#submitButton')), off);
  await p.screenshot({ path: `${SHOTS}/04-offline.png` });
  await p.goto(`${SITE}/finish-signup.html?token=abc`, { waitUntil: 'load' });
  await p.waitForTimeout(1500);
  const loadingMsg = await p.textContent('#loadingSlow');
  check('finish page offline -> says why instead of spinning forever', loadingMsg.includes("Couldn't reach"), loadingMsg);
  await p.screenshot({ path: `${SHOTS}/05-finish-offline.png` });
  await ctx.close();
} catch (e) { check('script error', false, e.stack.split('\n').slice(0, 3).join(' | ')); }
await browser.close();
console.log(`\nround2 ${engine}: ${results.filter(Boolean).length}/${results.length}`);
