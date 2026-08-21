/**
 * Single source of truth for the backend API's base URL.
 *
 * Previously each of landing.js, app/access-gate.js, app/api.js, and
 * admin/waitlist/admin.js independently declared its own
 * `const API_BASE_URL = 'http://localhost:5000'` — four copies of the
 * same hardcoded value, in four separate files, with no way to point
 * the frontend at a real deployed backend without editing all four and
 * risking missing one. Loaded as the first <script> in every HTML
 * entry point (landing, /app/, /admin/) specifically so this
 * one declaration is visible to all of them — classic <script> tags in
 * one document share a single top-level lexical scope, so a later
 * script can reference this const by name with no import needed.
 *
 * To point this frontend at a real backend deployment, change the one
 * line below — nothing else in the frontend needs to change.
 */
const API_BASE_URL = 'http://localhost:5000';
