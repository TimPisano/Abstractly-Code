// Round 4 headless checks (feature/auth-hardening). Never opens a visible browser.
// node round4.mjs [chromium|webkit]
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { DIR, SITE, API, loadPlaywright } from './lib.mjs';
const pw = loadPlaywright();
const S = DIR, OUTBOX = S + '/outbox', DB = S + '/e2e.db';
const engine = process.argv[2] || 'chromium';
const SHOTS = path.join(S, 'shots', `r4-${engine}`); fs.mkdirSync(SHOTS, { recursive: true });
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

const A = `r4a-${uniq}@example.test`, B = `r4b-${uniq}@example.test`, PW_A = 'alpha has a long phrase', PW_B = 'bravo has a long phrase';
try {
  // ---- 1. two people, two tabs, shared "keep me signed in" token ----
  let ctx = await ctxNew();
  const pa = await signupAndFinish(ctx, A, 'Avery Alpha', `Alpha Fund ${uniq}`, PW_A);
  const ctxB = await ctxNew(); await (await signupAndFinish(ctxB, B, 'Blake Bravo', `Bravo Fund ${uniq}`, PW_B)).close(); await ctxB.close();
  const pb = await ctx.newPage(); watch(pb, 'tabB');
  await login(pb, B, PW_B, true);
  await pa.waitForTimeout(3000);
  const aIdentity = await pa.evaluate(() => window.CURRENT_USER && window.CURRENT_USER.email).catch(() => null);
  check("two people, one browser: tab A follows the new sign-in instead of acting as B under A's name", aIdentity === B, `tab A shows ${aIdentity}`);
  await ctx.close();

  // ---- 2. link dies while the page is open ----
  ctx = await ctxNew();
  const C = `r4c-${uniq}@example.test`;
  let p = await ctx.newPage(); watch(p, 'expire-open');
  await p.goto(`${SITE}/signup.html`, { waitUntil: 'networkidle' });
  await p.fill('#name', 'Casey Charlie'); await p.fill('#email', C); await p.fill('#company', `Charlie ${uniq}`);
  await p.click('#submitButton'); await p.waitForSelector('[data-view="sent"]:not([hidden])');
  const cm = await waitMail(C, 1);
  await p.goto(linkIn(cm), { waitUntil: 'networkidle' }); await p.waitForSelector('[data-view="form"]:not([hidden])');
  sql(`update signup_requests set created_at='2020-01-01T00:00:00+00:00' where email='${C}'`);
  await p.fill('#password', 'charlie long passphrase');
  await p.click('#submitButton');
  await p.waitForSelector('[data-view="dead"]:not([hidden])', { timeout: 10000 }).catch(() => {});
  const t2 = await p.textContent('[data-dead="title"]').catch(() => '');
  check('link expires while the form is open -> friendly expired screen on submit', t2.includes('expired'), t2);
  await p.screenshot({ path: `${SHOTS}/02-expired-while-open.png` });

  const tabOther = await ctx.newPage(); watch(tabOther, 'resend-other-tab');
  await p.click('text=Send me a new link'); await waitMail(C, 2);
  await tabOther.goto(linkIn(mails().filter((m) => m.to === C)[1]), { waitUntil: 'networkidle' });
  await tabOther.waitForSelector('[data-view="form"]:not([hidden])');
  const pf = await ctx.newPage(); watch(pf, 'forgot-other');
  await pf.goto(`${SITE}/forgot-password.html`, { waitUntil: 'networkidle' });
  await pf.fill('#email', C); await pf.click('#submitButton'); await pf.waitForSelector('[data-view="sent"]:not([hidden])');
  await waitMail(C, 3);
  await tabOther.fill('#password', 'charlie long passphrase');
  await tabOther.click('#submitButton');
  await tabOther.waitForSelector('[data-view="dead"]:not([hidden])', { timeout: 10000 }).catch(() => {});
  const t3 = await tabOther.textContent('[data-dead="title"]').catch(() => '');
  check('link superseded from another tab while the form is open -> "newer link" screen', t3.includes('newer link'), t3);
  await ctx.close();

  // ---- 3. back / forward ----
  ctx = await ctxNew(); p = await ctx.newPage(); watch(p, 'back');
  await p.goto(`${SITE}/login.html`, { waitUntil: 'networkidle' });
  await p.click('#forgotLink'); await p.waitForURL(/forgot-password/);
  await p.fill('#email', A); await p.click('#submitButton'); await p.waitForSelector('[data-view="sent"]:not([hidden])');
  await p.goBack({ waitUntil: 'networkidle' }); await p.waitForTimeout(500);
  const backBtnUsable = await p.evaluate(() => { const b = document.getElementById('submitButton'); return !!b && !b.disabled && !b.getAttribute('aria-busy'); });
  check('back from "check your inbox" -> a usable login form', p.url().includes('login.html') && backBtnUsable, p.url());
  await p.goForward({ waitUntil: 'networkidle' }); await p.waitForTimeout(500);
  const fwdUsable = await p.evaluate(() => { const b = document.getElementById('submitButton'); return !b || !b.disabled; });
  check('forward again -> forgot page usable (not frozen in "Sending...")', fwdUsable, `view=${await viewOf(p)}`);
  const rm = await waitMail(A, 2);
  await p.goto(linkIn(rm), { waitUntil: 'networkidle' }); await p.waitForSelector('[data-view="form"]:not([hidden])');
  await p.fill('#password', 'alpha new long phrase');
  await Promise.all([p.waitForURL(/index\.html/), p.click('#submitButton')]);
  await p.waitForFunction(() => window.CURRENT_USER, null, { timeout: 15000 });
  await p.goBack({ waitUntil: 'networkidle' }).catch(() => {}); await p.waitForTimeout(1200);
  const backView = await viewOf(p).catch(() => '');
  check('back after a successful reset never shows the password form again', !(p.url().includes('reset-password') && backView === 'form'), `${p.url()} view=${backView}`);
  await ctx.close();

  // ---- 4. double clicks on secondary buttons, Enter repeats ----
  ctx = await ctxNew(); p = await ctx.newPage(); watch(p, 'dbl');
  const D = `r4d-${uniq}@example.test`;
  await p.goto(`${SITE}/signup.html`, { waitUntil: 'networkidle' });
  await p.fill('#name', 'Dana Delta'); await p.fill('#email', D); await p.fill('#company', `Delta ${uniq}`);
  await p.click('#submitButton'); await p.waitForSelector('[data-view="sent"]:not([hidden])'); await waitMail(D, 1);
  await p.dblclick('#resendButton'); await p.waitForTimeout(1500);
  check('double-click "send it again" sends one email, not two', countTo(D) === 2, `${countTo(D)} emails`);
  sql(`update signup_requests set created_at='2020-01-01T00:00:00+00:00' where email='${D}'`);
  await p.goto(linkIn(mails().filter((m) => m.to === D)[1]), { waitUntil: 'networkidle' });
  await p.waitForSelector('[data-view="dead"]:not([hidden])');
  await p.dblclick('text=Send me a new link'); await p.waitForTimeout(1500);
  check('double-click "Send me a new link" sends one email', countTo(D) === 3, `${countTo(D)} emails`);
  await p.goto(`${SITE}/login.html`, { waitUntil: 'networkidle' });
  await p.fill('#email', A); await p.fill('#password', 'alpha new long phrase');
  await p.focus('#password'); await p.keyboard.press('Enter'); await p.keyboard.press('Enter'); await p.keyboard.press('Enter');
  await p.waitForURL(/index\.html/, { timeout: 15000 }).catch(() => {});
  check('Enter pressed 3x on login -> lands once', p.url().endsWith('index.html'), p.url());
  await ctx.close();

  // ---- 5. signup while already signed in; two signups at once ----
  ctx = await ctxNew(); p = await ctx.newPage(); watch(p, 'signedin-signup');
  await login(p, B, PW_B, true);
  await p.goto(`${SITE}/signup.html`, { waitUntil: 'networkidle' }); await p.waitForTimeout(1000);
  const signedInHint = await p.evaluate(() => [...document.querySelectorAll('[data-view]:not([hidden]), .auth-notice:not([hidden])')].map((e) => e.innerText).join(' '));
  check('signup page while signed in offers a way back to the dashboard', /signed in as/i.test(signedInHint), signedInHint.slice(0, 80));
  await p.screenshot({ path: `${SHOTS}/05-signup-while-signed-in.png` });
  await ctx.close();

  ctx = await ctxNew(); const E = `r4e-${uniq}@example.test`;
  const t1 = await ctx.newPage(), t2b = await ctx.newPage();
  for (const [t, co] of [[t1, `Echo One ${uniq}`], [t2b, `Echo Two ${uniq}`]]) {
    await t.goto(`${SITE}/signup.html`, { waitUntil: 'networkidle' });
    await t.fill('#name', 'Emery Echo'); await t.fill('#email', E); await t.fill('#company', co);
  }
  await Promise.all([t1.click('#submitButton'), t2b.click('#submitButton')]);
  await waitMail(E, 2);
  const statuses = [];
  for (const l of mails().filter((m) => m.to === E).map(linkIn)) { const q = await ctx.newPage(); await q.goto(l, { waitUntil: 'networkidle' }); await q.waitForTimeout(1200); statuses.push(await viewOf(q)); }
  check('two signups at once -> exactly one live link, the other says "newer link"', statuses.filter((s) => s === 'form').length === 1 && statuses.filter((s) => s === 'dead').length === 1, statuses.join(' / '));
  await ctx.close();

  // ---- 6. mobile layout stress ----
  for (const [label, dev] of [['landscape', { ...phone, viewport: { width: phone.viewport.height, height: phone.viewport.width } }], ['portrait', phone]]) {
    ctx = await ctxNew(dev); p = await ctx.newPage(); watch(p, label);
    await p.goto(`${SITE}/login.html`, { waitUntil: 'networkidle' });
    await p.addStyleTag({ content: 'html { font-size: 200% !important; }' });
    await p.waitForTimeout(400);
    const geo = await p.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: innerWidth }));
    check(`login at 200% text, ${label}: no sideways scroll`, geo.sw <= geo.iw + 1, `${geo.sw} vs ${geo.iw}`);
    await p.screenshot({ path: `${SHOTS}/06-login-200pct-${label}.png`, fullPage: true });
    await p.goto(`${SITE}/signup.html`, { waitUntil: 'networkidle' });
    const hints = await p.evaluate(() => [...document.querySelectorAll('input:not([hidden]):not([type=checkbox])')].map((i) => `${i.id}:${i.getAttribute('enterkeyhint') || '-'}`).join(' '));
    check(`signup ${label}: inputs tell the phone keyboard what Enter does`, !hints.includes(':-'), hints);
    await ctx.close();
  }
} catch (e) { check('script error', false, e.stack.split('\n').slice(0, 3).join(' | ')); }
// WebKit reports the app dashboard's own background fetches as "access control checks"
// errors when a test navigates away mid-request (existing app code, not auth).
check('no page errors', errors.filter((e) => !/access control checks/.test(e)).length === 0, errors.slice(0, 3).join(' || '));
await browser.close();
console.log(`\nround4 ${engine}: ${results.filter(Boolean).length}/${results.length}`);
