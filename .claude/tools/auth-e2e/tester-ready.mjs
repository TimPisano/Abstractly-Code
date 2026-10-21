// Headless click-through of the tester flow (feature/tester-ready step 6):
// owner creates a team -> its admin sets a password from the emailed link
// -> admin invites a teammate -> teammate joins -> admin uploads a lease ->
// teammate sees it -> admin removes the teammate, who is signed out.
// Headless only (CLAUDE.md). Emails are captured to $AUTH_E2E_DIR/outbox.
//
//   .claude/tools/auth-e2e/run-tester-ready.sh            # API :5741 + site :8741
//   node .claude/tools/auth-e2e/tester-ready.mjs [chromium|webkit] [desktop|mobile]
//
// Prints one line per check and the screenshot paths. Open every PNG before
// saying anything about how a page looks.
import fs from 'node:fs';
import path from 'node:path';
import { loadPlaywright } from './lib.mjs';

const DIR = process.env.AUTH_E2E_DIR;
const SITE = process.env.AUTH_E2E_SITE || 'http://localhost:8741';
const API = process.env.AUTH_E2E_API || 'http://127.0.0.1:5741';
const OWNER_EMAIL = process.env.OWNER_EMAIL;
const OWNER_PASSWORD = process.env.OWNER_PASSWORD;
const LEASE_PDF = process.env.LEASE_PDF;
if (!DIR || !OWNER_EMAIL || !OWNER_PASSWORD || !LEASE_PDF) {
  console.error('Set AUTH_E2E_DIR, OWNER_EMAIL, OWNER_PASSWORD and LEASE_PDF (run-tester-ready.sh prints them).');
  process.exit(2);
}
const engine = process.argv[2] || 'chromium';
const form = process.argv[3] || 'desktop';
const SHOTS = path.join(DIR, 'shots', `${engine}-${form}`);
fs.mkdirSync(SHOTS, { recursive: true });

const pw = loadPlaywright();
const { devices } = pw;
const browser = await pw[engine].launch({ headless: true });
const contextOptions = form === 'mobile' ? { ...devices['iPhone 13'] } : { viewport: { width: 1440, height: 900 } };

const results = [];
const consoleErrors = [];
function check(name, ok, detail = '') {
  results.push({ name, ok });
  console.log(`${ok ? '✓' : '✗'} ${name}${detail ? ` -- ${detail}` : ''}`);
}
async function newPage() {
  const ctx = await browser.newContext(contextOptions);
  await ctx.addInitScript((api) => { try { localStorage.setItem('abstractly.apiBaseOverride', api); } catch (e) {} }, API);
  const page = await ctx.newPage();
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(`${page.url()} :: ${m.text()}`); });
  page.on('dialog', (d) => d.dismiss());
  return page;
}
async function shot(page, name) {
  // Let view transitions and toasts settle, or the PNG shows a half-faded frame.
  // Viewport only: a fullPage capture of the app stretches the fixed sidebar
  // across the page once content is taller than the window (not real layout).
  await page.waitForTimeout(1500);
  const file = path.join(SHOTS, `${name}.png`);
  await page.screenshot({ path: file });
  console.log(`  shot: ${file}`);
}
function latestMail(to, subjectPart) {
  const outbox = path.join(DIR, 'outbox');
  const mails = fs.readdirSync(outbox).sort().map((f) => JSON.parse(fs.readFileSync(path.join(outbox, f), 'utf8')));
  const hit = mails.filter((m) => m.to === to && m.subject.includes(subjectPart)).pop();
  if (!hit) throw new Error(`no email to ${to} with "${subjectPart}"`);
  return hit.text.match(/https?:\/\/\S+token=[A-Za-z0-9_-]+/)[0];
}
async function waitForMail(to, subjectPart) {
  for (let i = 0; i < 40; i++) {
    try { return latestMail(to, subjectPart); } catch { await new Promise((r) => setTimeout(r, 250)); }
  }
  return latestMail(to, subjectPart);
}
async function appLogin(page, email, password) {
  await page.goto(`${SITE}/app/login.html`);
  await page.fill('#email', email);
  await page.fill('#password', password);
  await page.click('#submitButton');
  await page.waitForURL(/\/app\/index\.html/, { timeout: 20000 });
}
// The sidebar is on screen (and clickable) before the app's scripts finish
// loading; a click in that window is silently ignored, and init() then shows
// the Dashboard. So click until the view is really the active one.
async function openView(page, view) {
  const nav = page.locator(`.nav-item[data-view="${view}"]`);
  for (let attempt = 0; attempt < 20; attempt++) {
    if (!(await nav.isVisible())) {
      const toggle = page.locator('#mobileMenuBtn, .mobile-menu-btn, [aria-label="Open menu"]').first();
      if (await toggle.count()) await toggle.click();
    }
    await nav.click();
    if (await page.locator(`#view-${view}.active`).count()) return attempt;
    await page.waitForTimeout(500);
  }
  throw new Error(`could not open the ${view} view`);
}

let current = null; // the page being driven, for a failure screenshot
const stamp = Date.now().toString(36);
const ADMIN_EMAIL = `avery.${stamp}@harbor.test`;
const TEAMMATE_EMAIL = `riley.${stamp}@harbor.test`;
const FIRM = `Harbor Capital ${stamp}`;
const ADMIN_PASSWORD = 'maple ridge closing day';
const TEAMMATE_PASSWORD = 'harbor lights at dusk';

try {
  // ---- 1. Owner creates the team
  const owner = await newPage();
  current = owner;
  await owner.goto(`${SITE}/owner/login.html`);
  await owner.fill('#ownerEmail', OWNER_EMAIL);
  await owner.fill('#ownerPassword', OWNER_PASSWORD);
  await owner.click('#ownerLoginSubmitBtn');
  await owner.waitForSelector('#createTeamBtn', { timeout: 20000 });
  await owner.click('#createTeamBtn');
  await owner.fill('#newFirmName', FIRM);
  await owner.fill('#newAdminName', 'Avery Stone');
  await owner.fill('#newAdminEmail', ADMIN_EMAIL);
  await owner.click('#createTeamForm button[type="submit"]');
  await owner.waitForFunction(() => document.getElementById('createTeamResult').textContent.trim().length > 0, null, { timeout: 15000 });
  check('owner creates a team', true, (await owner.textContent('#createTeamResult')).trim().slice(0, 120));
  await shot(owner, '01-owner-team-created');

  // ---- 2. Admin sets a password from the setup email (first a too-short one)
  const admin = await newPage();
  current = admin;
  await admin.goto(await waitForMail(ADMIN_EMAIL, 'set up'));
  await admin.fill('#setupPassword', 'ninechars');
  await admin.fill('#setupPasswordConfirm', 'ninechars');
  await admin.click('#setupSubmitBtn');
  await admin.waitForTimeout(500);
  // The browser's own minlength check speaks first; either it or the page must name the rule.
  const shortMsg = (await admin.textContent('#setupMessage')).trim()
    || await admin.$eval('#setupPassword', (el) => el.validationMessage);
  check('9-character password: clear message, form stays (setup-link bug fix)',
    (await admin.isVisible('#setupForm')) && /10 characters/.test(shortMsg), shortMsg);
  await shot(admin, '02-setup-short-password');
  await admin.fill('#setupPassword', 'password12');
  await admin.fill('#setupPasswordConfirm', 'password12');
  await admin.click('#setupSubmitBtn');
  await admin.waitForTimeout(500);
  const commonMsg = (await admin.textContent('#setupMessage')).trim();
  check('common 10-character password: "too common", form stays, link not called dead',
    (await admin.isVisible('#setupForm')) && /too common/.test(commonMsg) && !(await admin.isVisible('#setupDeadLinkNote')), commonMsg);
  await shot(admin, '02b-setup-common-password');
  await admin.fill('#setupPassword', ADMIN_PASSWORD);
  await admin.fill('#setupPasswordConfirm', ADMIN_PASSWORD);
  await admin.click('#setupSubmitBtn');
  await admin.waitForURL(/login\.html/, { timeout: 15000 });
  check('setup link -> password set -> login page', true, admin.url());
  await shot(admin, '03-after-setup-login-page');

  // ---- 3. Admin signs in and invites a teammate
  await appLogin(admin, ADMIN_EMAIL, ADMIN_PASSWORD);
  await openView(admin, 'team');
  await admin.waitForSelector('#teamInvitePanel:not([hidden])', { timeout: 15000 });
  check('team page shows the invite form, hides the add-with-password form',
    !(await admin.isVisible('#teamAddMemberPanel')));
  current = admin;
  await admin.fill('#teamInviteEmail', TEAMMATE_EMAIL);
  await admin.fill('#teamInviteName', 'Riley Shaw');
  await admin.selectOption('#teamInviteRole', 'analyst');
  await admin.click('#teamInviteSubmitBtn');
  await admin.waitForSelector('#teamPendingInvitesPanel:not([hidden])', { timeout: 15000 });
  const pending = await admin.textContent('#teamPendingInvitesContainer');
  check('pending invite listed with an expiry', pending.includes(TEAMMATE_EMAIL) && /Expires in/.test(pending), pending.replace(/\s+/g, ' ').trim().slice(0, 120));
  await shot(admin, '04-team-pending-invite');
  await admin.locator('#teamPendingInvitesPanel').scrollIntoViewIfNeeded();
  const overflow = await admin.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  check('no sideways page scroll on the Team page', overflow <= 1, `${overflow}px wider than the window`);
  await shot(admin, '04b-pending-invites-table');

  // ---- 4. Teammate accepts the invite
  const teammate = await newPage();
  current = teammate;
  const inviteUrl = await waitForMail(TEAMMATE_EMAIL, 'Join');
  await teammate.goto(inviteUrl);
  await teammate.waitForFunction(() => document.getElementById('setupHeading').textContent.startsWith('Join'), null, { timeout: 15000 });
  const heading = (await teammate.textContent('#setupHeading')).trim();
  check('invite page greets with the team name', heading === `Join ${FIRM}`, heading);
  check('invite token removed from the address bar', !teammate.url().includes('token='), teammate.url());
  await shot(teammate, '05-invite-page');
  await teammate.fill('#setupPassword', TEAMMATE_PASSWORD);
  await teammate.fill('#setupPasswordConfirm', TEAMMATE_PASSWORD);
  await teammate.click('#setupSubmitBtn');
  await teammate.waitForURL(/\/app\/index\.html/, { timeout: 20000 });
  check('teammate joins and lands in the app signed in', true, teammate.url());
  await shot(teammate, '06-teammate-signed-in');

  await admin.reload();
  await openView(admin, 'team');
  await admin.waitForFunction((email) => document.getElementById('teamMembersTableContainer').textContent.includes(email), TEAMMATE_EMAIL, { timeout: 15000 });
  check('teammate now in Members, pending list empty', !(await admin.isVisible('#teamPendingInvitesPanel')));
  await shot(admin, '07-team-members');

  // ---- 5. Admin uploads; teammate sees it
  await openView(admin, 'upload');
  await admin.setInputFiles('#fileInput', LEASE_PDF);
  await admin.waitForSelector('#uploadResults', { state: 'visible', timeout: 30000 });
  const uploadText = (await admin.textContent('#uploadResultsList')).replace(/\s+/g, ' ').trim();
  check('admin uploads a lease', /[1-9]\d* lease\(s\) created/.test(uploadText) && /\b0 file\(s\) failed/.test(uploadText), uploadText.slice(0, 120));
  await shot(admin, '08-upload-done');

  const leaseName = path.basename(LEASE_PDF, '.pdf');
  await teammate.reload();
  await teammate.waitForFunction((n) => document.body.innerText.includes(n), leaseName, { timeout: 20000 }).catch(() => {});
  check('teammate sees the admin\'s lease on their dashboard', (await teammate.innerText('body')).includes(leaseName));
  await shot(teammate, '09-teammate-sees-lease');

  // ---- 6. Admin removes the teammate; the teammate is signed out
  await openView(admin, 'team');
  await admin.locator(`#teamMembersTableContainer tr:has-text("${TEAMMATE_EMAIL}") .team-status-toggle-btn`).click();
  const confirmText = (await admin.locator('[role="dialog"], [role="alertdialog"]').last().innerText().catch(() => '')).replace(/\s+/g, ' ');
  await admin.getByRole('button', { name: 'Deactivate', exact: true }).last().click();
  await admin.waitForTimeout(800);
  check('remove dialog says they are signed out right away', /signed out right away/.test(confirmText), confirmText.slice(0, 140));
  await shot(admin, '10-teammate-removed');

  await openView(teammate, 'team').catch(() => {});
  await teammate.reload();
  await teammate.waitForURL(/login\.html/, { timeout: 15000 }).catch(() => {});
  check('removed teammate is signed out on their next page load', /login\.html/.test(teammate.url()), teammate.url());
  await shot(teammate, '11-teammate-after-removal');
} catch (err) {
  check('flow completed without an exception', false, err.message.split('\n')[0]);
  if (current) {
    const said = await current.evaluate(() => [...document.querySelectorAll('.access-gate-message, .toast, [role="status"], [role="alert"]')]
      .map((el) => el.textContent.trim()).filter(Boolean).join(' | ')).catch(() => '');
    console.log(`  page said: ${said || '(nothing)'}  url: ${current.url()}`);
    await shot(current, 'zz-failure').catch(() => {});
  }
} finally {
  await browser.close();
}

const relevantErrors = consoleErrors.filter((e) => !/favicon|401 \(UNAUTHORIZED\)|Failed to load resource: the server responded with a status of 401/.test(e));
check('no unexpected console errors', relevantErrors.length === 0, relevantErrors.slice(0, 5).join(' | '));
const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed}/${results.length} checks passed (${engine} ${form}). Screenshots: ${SHOTS}`);
process.exit(failed ? 1 : 0);
