// Headless end-to-end checks for feature/auth-flow. Never opens a visible browser.
// node e2e.mjs [chromium|webkit] [desktop|mobile|tablet]
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

import { DIR, SITE, API, loadPlaywright } from './lib.mjs';
const pw = loadPlaywright();

const S = DIR;
const OUTBOX = path.join(S, 'outbox');
const DB = path.join(S, 'e2e.db');
const engine = process.argv[2] || 'chromium';
const form = process.argv[3] || 'desktop';
const SHOTS = path.join(S, 'shots', `${engine}-${form}`);
fs.mkdirSync(SHOTS, { recursive: true });

const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  -- ' + detail : ''}`); };

function sql(q) { return execFileSync('sqlite3', ['-cmd', '.timeout 5000', DB, q]).toString().trim(); }
function mails() { return fs.readdirSync(OUTBOX).sort().map((f) => JSON.parse(fs.readFileSync(path.join(OUTBOX, f)))); }
function linkIn(mail) { return mail.text.match(/https?:\/\/\S+token=[A-Za-z0-9_\-]+/)[0]; }
async function waitMail(to, count, ms = 8000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { const m = mails().filter((x) => x.to === to); if (m.length >= count) return m[m.length - 1]; await new Promise((r) => setTimeout(r, 150)); }
  throw new Error(`no mail #${count} to ${to}`);
}
const uniq = `${engine}${form}${Date.now() % 100000}`;

const devices = {
  desktop: { viewport: { width: 1440, height: 900 } },
  tablet: { viewport: { width: 768, height: 1024 }, hasTouch: true },
  mobile: engine === 'webkit' ? pw.devices['iPhone 13'] : pw.devices['Pixel 5'],
};
const browser = await pw[engine].launch({ headless: true });

async function newCtx() {
  const ctx = await browser.newContext({ ...devices[form] });
  await ctx.addInitScript((api) => { try { localStorage.setItem('abstractly.apiBaseOverride', api); } catch (e) {} }, API);
  return ctx;
}
async function shot(page, name) {
  await page.waitForTimeout(250);
  const file = path.join(SHOTS, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  return file;
}
async function noHorizontalScroll(page, label) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  check(`${label}: no horizontal scroll`, sw <= iw, `scrollWidth ${sw} vs ${iw}`);
}
async function inputFontsAre16(page, label) {
  const small = await page.evaluate(() => [...document.querySelectorAll('input:not([type=checkbox]):not([hidden]):not([aria-hidden=true])')].filter((i) => parseFloat(getComputedStyle(i).fontSize) < 16).map((i) => i.id));
  check(`${label}: inputs >= 16px (no iOS zoom)`, small.length === 0, small.join(','));
}
async function visibleView(page) {
  return page.evaluate(() => [...document.querySelectorAll('[data-view]')].filter((e) => !e.hidden).map((e) => e.dataset.view).join(','));
}
const consoleErrors = [];
function watch(page, label) {
  page.on('pageerror', (e) => consoleErrors.push(`${label}: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) consoleErrors.push(`${label}: ${m.text()}`); });
}

const email = `e2e-${uniq}@example.test`;
try {
  // ---------- A: signup ----------
  let ctx = await newCtx();
  let page = await ctx.newPage(); watch(page, 'signup');
  await page.goto(`${SITE}/signup.html`, { waitUntil: 'networkidle' });
  await shot(page, '01-signup-empty');
  await noHorizontalScroll(page, 'signup'); await inputFontsAre16(page, 'signup');
  await page.click('#submitButton');
  await shot(page, '02-signup-validation');
  check('signup: empty submit shows field errors', (await page.textContent('#nameError')).includes('Enter your name'));
  await page.fill('#name', 'Jordan Lee');
  await page.fill('#email', `e2e-${uniq}@gmial.com`);
  await page.locator('#email').blur();
  check('signup: domain typo hint', (await page.textContent('#emailError')).includes('gmail.com'));
  await page.fill('#email', email);
  await page.fill('#company', `Maple Ridge Capital ${uniq}`);
  await page.dblclick('#submitButton');
  await page.waitForSelector('[data-view="sent"]:not([hidden])');
  await shot(page, '03-signup-sent');
  const sentMail = await waitMail(email, 1);
  await page.waitForTimeout(800);
  check('signup: double-click sent exactly one email', mails().filter((m) => m.to === email).length === 1, `${mails().filter((m) => m.to === email).length}`);
  check('signup: no account before link', sql(`select count(*) from users where email='${email}'`) === '0');

  // ---------- superseded via "send it again" ----------
  await page.click('#resendButton');
  await page.waitForFunction(() => document.querySelector('#resendStatus').textContent.includes('fresh link'));
  await shot(page, '04-signup-resent');
  const freshMail = await waitMail(email, 2);
  const oldLink = linkIn(sentMail), link = linkIn(freshMail);
  check('signup: resend produced a new link', oldLink !== link);

  const p2 = await ctx.newPage(); watch(p2, 'finish-old');
  await p2.goto(oldLink, { waitUntil: 'networkidle' });
  await p2.waitForSelector('[data-view="dead"]:not([hidden])');
  check('finish: old link says newer link', (await p2.textContent('[data-dead="title"]')).includes('newer link'));
  await shot(p2, '05-finish-superseded');
  await p2.close();

  // ---------- two tabs open on the same valid link ----------
  const tabA = await ctx.newPage(); watch(tabA, 'tabA');
  const tabB = await ctx.newPage(); watch(tabB, 'tabB');
  await tabA.goto(link, { waitUntil: 'networkidle' });
  await tabB.goto(link, { waitUntil: 'networkidle' });
  await tabA.waitForSelector('[data-view="form"]:not([hidden])');
  check('finish: token removed from address bar', !tabA.url().includes('token='), tabA.url());
  check('finish: greeting uses first name + company', (await tabA.textContent('#greeting')).includes('Hi Jordan'));
  await shot(tabA, '06-finish-empty');
  await noHorizontalScroll(tabA, 'finish'); await inputFontsAre16(tabA, 'finish');
  await tabA.fill('#password', 'password123');
  await shot(tabA, '07-finish-weak');
  await tabA.click('#submitButton');
  check('finish: weak password blocked client-side', (await tabA.textContent('#passwordError')).includes('rules'));
  await shot(tabA, '08-finish-weak-submitted');
  await tabA.click('#passwordToggle');
  check('finish: show toggles to text', (await tabA.getAttribute('#password', 'type')) === 'text');
  await tabA.fill('#password', 'maple ridge closing day');
  await shot(tabA, '09-finish-good-shown');
  await Promise.all([tabA.waitForURL(/index\.html/, { timeout: 20000 }), tabA.dblclick('#submitButton')]);
  check('finish: lands in dashboard', tabA.url().endsWith('/app/index.html'), tabA.url());
  await tabA.waitForFunction(() => window.CURRENT_USER && window.CURRENT_USER.authenticated, null, { timeout: 15000 });
  await tabA.waitForTimeout(1500);
  await shot(tabA, '10-dashboard-after-signup');
  check('finish: exactly one account', sql(`select count(*) from users where email='${email}'`) === '1');
  check('finish: admin of a new team', sql(`select role from users where email='${email}'`) === 'admin');
  const stored = await tabA.evaluate(() => ({ local: !!localStorage.getItem('authToken'), sess: !!sessionStorage.getItem('authToken') }));
  check('remember (default checked) -> localStorage token', stored.local && !stored.sess, JSON.stringify(stored));

  await tabB.waitForSelector('[data-view="form"]:not([hidden])');
  await tabB.fill('#password', 'another long phrase here');
  await tabB.click('#submitButton');
  await tabB.waitForSelector('[data-view="dead"]:not([hidden])');
  const bTitle = await tabB.textContent('[data-dead="title"]');
  check('two tabs: second submit -> already set up', bTitle.includes('already set up'), bTitle);
  check('two tabs: offers dashboard (logged in)', (await tabB.textContent('[data-dead="actions"]')).includes('dashboard'));
  await shot(tabB, '11-finish-used-other-tab');

  await tabA.goBack({ waitUntil: 'networkidle' }).catch(() => {});
  const backView = await visibleView(tabA).catch(() => '?');
  check('back from dashboard does not return to the password form', !(tabA.url()).includes('finish-signup') || backView !== 'form', `${tabA.url()} view=${backView}`);
  await shot(tabA, '12-after-back');

  const p3 = await ctx.newPage(); watch(p3, 'reopen');
  await p3.goto(link, { waitUntil: 'networkidle' });
  await p3.waitForSelector('[data-view="dead"]:not([hidden])');
  check('reopen used link -> already set up', (await p3.textContent('[data-dead="title"]')).includes('already set up'));
  await p3.close();

  const p4 = await ctx.newPage(); watch(p4, 'tampered');
  await p4.goto(link.slice(0, -3) + 'zzz', { waitUntil: 'networkidle' });
  await p4.waitForSelector('[data-view="dead"]:not([hidden])');
  check('tampered link -> doesnt work', (await p4.textContent('[data-dead="title"]')).includes("doesn't work"));
  await shot(p4, '13-finish-tampered');
  await p4.close();
  await tabB.close();

  await tabA.goto(`${SITE}/index.html`, { waitUntil: 'networkidle' });
  await tabA.waitForFunction(() => window.CURRENT_USER, null, { timeout: 15000 });
  if (await tabA.isVisible('#signOutBtn')) {
    await Promise.all([tabA.waitForURL(/login\.html/), tabA.click('#signOutBtn')]);
    check('sign out -> login with notice', (await tabA.textContent('#loginNotice')).includes('signed out'));
    check('sign out cleared stored tokens', await tabA.evaluate(() => !localStorage.getItem('authToken') && !sessionStorage.getItem('authToken')));
    await shot(tabA, '14-login-signed-out');
  } else {
    check('sign out button visible', false, 'hidden at this size');
  }
  await ctx.close();

  // ---------- expired signup link + one-click resend ----------
  const email2 = `e2e2-${uniq}@example.test`;
  ctx = await newCtx(); page = await ctx.newPage(); watch(page, 'expired');
  await page.goto(`${SITE}/signup.html`, { waitUntil: 'networkidle' });
  await page.fill('#name', 'Sam Ortiz'); await page.fill('#email', email2); await page.fill('#company', `Ortiz Holdings ${uniq}`);
  await page.click('#submitButton');
  const m1 = await waitMail(email2, 1);
  sql(`update signup_requests set created_at='2020-01-01T00:00:00+00:00' where email='${email2}'`);
  await page.goto(linkIn(m1), { waitUntil: 'networkidle' });
  await page.waitForSelector('[data-view="dead"]:not([hidden])');
  check('expired link -> expired screen', (await page.textContent('[data-dead="title"]')).includes('expired'));
  await shot(page, '15-finish-expired');
  await page.click('text=Send me a new link');
  await page.waitForFunction(() => document.querySelector('[data-dead="status"]').textContent.includes('Sent'));
  await shot(page, '16-finish-expired-resent');
  const m2 = await waitMail(email2, 2);
  check('expired resend -> new link to same address', linkIn(m2) !== linkIn(m1));
  await ctx.close();

  // ---------- forgot / reset + other device signed out ----------
  ctx = await newCtx(); page = await ctx.newPage(); watch(page, 'login');
  const other = await newCtx(); const otherPage = await other.newPage(); watch(otherPage, 'otherdevice');
  await otherPage.goto(`${SITE}/login.html`, { waitUntil: 'networkidle' });
  await otherPage.fill('#email', email); await otherPage.fill('#password', 'maple ridge closing day');
  await Promise.all([otherPage.waitForURL(/index\.html/), otherPage.click('#submitButton')]);
  check('other device logged in', otherPage.url().endsWith('index.html'));

  await page.goto(`${SITE}/login.html`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(300);
  await shot(page, '20-login-empty');
  await noHorizontalScroll(page, 'login'); await inputFontsAre16(page, 'login');
  check('login: get started link shown (flag on)', await page.isVisible('#getStartedAlt'));
  await page.fill('#email', email); await page.fill('#password', 'wrong password here');
  await page.click('#submitButton');
  await page.waitForFunction(() => document.querySelector('#formStatus').textContent.length > 0);
  await shot(page, '21-login-wrong');
  await page.click('#forgotLink');
  await page.waitForURL(/forgot-password/);
  await shot(page, '22-forgot-empty');
  await page.fill('#email', email);
  await page.dblclick('#submitButton');
  await page.waitForSelector('[data-view="sent"]:not([hidden])');
  check('forgot: exact message', (await page.textContent('#sentMessage')).trim() === 'If an account exists for that email, we just sent a reset link.');
  await shot(page, '23-forgot-sent');
  const r1 = await waitMail(email, 3);
  check('forgot: reset email subject', r1.subject === 'Reset your Abstractly password', r1.subject);
  await page.waitForTimeout(600);
  check('forgot: double-click sent one email', mails().filter((m) => m.to === email && m.subject.startsWith('Reset')).length === 1);
  await page.goto(linkIn(r1), { waitUntil: 'networkidle' });
  await page.waitForSelector('[data-view="form"]:not([hidden])');
  await shot(page, '24-reset-empty');
  await page.uncheck('#remember');
  await page.fill('#password', 'a brand new phrase now');
  await Promise.all([page.waitForURL(/index\.html/, { timeout: 20000 }), page.click('#submitButton')]);
  const st = await page.evaluate(() => ({ local: !!localStorage.getItem('authToken'), sess: !!sessionStorage.getItem('authToken') }));
  check('reset: unchecked remember -> sessionStorage only', st.sess && !st.local, JSON.stringify(st));
  await page.waitForFunction(() => window.CURRENT_USER, null, { timeout: 15000 });
  await waitMail(email, 4);
  check('reset: password-changed notice sent', mails().some((m) => m.to === email && m.subject === 'Your Abstractly password was changed'));

  await otherPage.reload({ waitUntil: 'networkidle' });
  await otherPage.waitForURL(/login\.html/, { timeout: 15000 }).catch(() => {});
  check('other device signed out after reset', otherPage.url().includes('login.html'), otherPage.url());
  check('other device sees "session ended"', (await otherPage.textContent('#loginNotice').catch(() => '')).includes('session ended'));
  await shot(otherPage, '25-other-device-signed-out');

  await page.goto(linkIn(r1), { waitUntil: 'networkidle' });
  await page.waitForSelector('[data-view="dead"]:not([hidden])');
  check('reset: reused link -> already used', (await page.textContent('[data-dead="title"]')).includes('already used'));
  await shot(page, '26-reset-used');
  await ctx.close(); await other.close();

  // ---------- new tab while "keep me signed in" is off ----------
  ctx = await newCtx(); page = await ctx.newPage(); watch(page, 'twotabs');
  await page.goto(`${SITE}/login.html`, { waitUntil: 'networkidle' });
  await page.fill('#email', email); await page.fill('#password', 'a brand new phrase now');
  await page.uncheck('#remember');
  await Promise.all([page.waitForURL(/index\.html/), page.click('#submitButton')]);
  const tab2 = await ctx.newPage(); watch(tab2, 'tab2');
  await tab2.goto(`${SITE}/index.html`, { waitUntil: 'networkidle' });
  await tab2.waitForTimeout(2500);
  check('unchecked remember: second tab stays signed in', tab2.url().endsWith('index.html'), tab2.url());
  await ctx.close();
} catch (err) {
  check('script error', false, err.stack.split('\n').slice(0, 3).join(' | '));
} finally {
  check('no JS errors on any page', consoleErrors.length === 0, consoleErrors.slice(0, 5).join(' || '));
  await browser.close();
  const failed = results.filter((r) => !r.ok);
  console.log(`\n${engine}/${form}: ${results.length - failed.length}/${results.length} passed. Shots: ${SHOTS}`);
  process.exit(failed.length ? 1 : 0);
}
