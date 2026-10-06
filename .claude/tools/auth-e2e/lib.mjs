// Shared setup for the auth E2E scripts. Headless only (CLAUDE.md rule 1).
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';

// Working dir for the local API's captured emails + database + screenshots.
export const DIR = process.env.AUTH_E2E_DIR || path.join(os.tmpdir(), 'abstractly-auth-e2e');
export const SITE = process.env.AUTH_E2E_SITE || 'http://localhost:8731/app';
export const API = process.env.AUTH_E2E_API || 'http://127.0.0.1:5731';
fs.mkdirSync(path.join(DIR, 'outbox'), { recursive: true });

// Same lookup as ../screenshots.mjs: a local node_modules, else the npx cache.
export function loadPlaywright() {
  const tryReq = (base) => { try { return createRequire(path.join(base, 'x.js'))('playwright'); } catch { return null; } };
  let pw = tryReq(process.cwd());
  if (pw) return pw;
  const npx = path.join(os.homedir(), '.npm/_npx');
  try { for (const d of fs.readdirSync(npx)) { pw = tryReq(path.join(npx, d, 'node_modules')) || tryReq(path.join(npx, d)); if (pw) return pw; } } catch {}
  console.error('Playwright not found. Run: npx -y playwright@latest install chromium webkit');
  process.exit(2);
}
