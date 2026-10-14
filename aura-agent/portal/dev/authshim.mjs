/**
 * Local auth for the dev harness.
 *
 * The only reachable deployment is V1 (@15), which is the team's and carries the
 * old server code — so login/session cannot be exercised against it. Rather than
 * fake the responses, this loads the REAL Core.js and Sheets.js into a VM with
 * Apps Script's services stubbed, and answers from that. The token format, the
 * expiry, the sliding renewal, the throttle and the revocation check are all the
 * shipping code; only the LOGIN sheet is a fixture.
 *
 * Dev only. Never bundled: dev/ is not pushed to Apps Script.
 */
import { readFileSync } from 'node:fs';
import { createContext, runInContext } from 'node:vm';
import crypto from 'node:crypto';

const ROOT = new URL('..', import.meta.url);
const b64web = (b) => Buffer.from(b).toString('base64').replace(/\+/g, '-').replace(/\//g, '_');

/* Dev-only Script Properties. The server now fails closed without TOKEN_SECRET /
   PASSWORD_PEPPER, so the harness must supply them. Not real secrets. */
const DEV_PROPS = {
  TOKEN_SECRET: 'dev-token-secret-not-a-real-key',
  PASSWORD_PEPPER: 'dev-password-pepper-not-a-real-secret',
  ADMIN_PASSCODE: 'dev-admin-pass',
};
/* Server hash format, replicated here to seed a pre-hashed fixture row:
   'sha256$' + base64url(SHA-256(pepper + '|' + lower(username) + '|' + password)) */
const devHash = (username, password) =>
  'sha256$' + b64web(crypto.createHash('sha256')
    .update(DEV_PROPS.PASSWORD_PEPPER + '|' + String(username).toLowerCase() + '|' + password)
    .digest());

/* Stand-ins for the local LOGIN tab. Passwords are case-sensitive, as on the server.
   'harvinder' / 'priya' are legacy plaintext (exercise the migrate-on-login path);
   'nadia' is already hashed (exercise the hashed-compare path). The write-back that
   migration performs on the real sheet is a no-op here — loginRows_ is overridden
   below with an in-memory fixture, so there is no sheet cell to update. */
export const FIXTURE_USERS = [
  { username: 'harvinder', name: 'Harvinder Babra', email: 'h@example.com', password: 'Summer2026' },
  { username: 'priya', name: 'Priya S', email: 'p@example.com', password: 'Autumn2026' },
  { username: 'nadia', name: 'Nadia K', email: 'n@example.com', password: devHash('nadia', 'Winter2026') },
];

const cache = new Map();
const ctx = createContext({
  console,
  PropertiesService: { getScriptProperties: () => ({ getProperty: (k) => DEV_PROPS[k] ?? null }) },
  LockService: { getScriptLock: () => ({ waitLock() {}, releaseLock() {} }) },
  CacheService: {
    getScriptCache: () => ({
      get: (k) => cache.get(k) ?? null,
      put: (k, v) => cache.set(k, v),
      remove: (k) => cache.delete(k),
      // The server chunks oversized values and warms keys in batches, so the stub has
      // to speak getAll/putAll too — without them those paths silently no-op here and
      // the harness stops matching the service it stands in for.
      getAll: (keys) => { const o = {}; for (const k of keys) if (cache.has(k)) o[k] = cache.get(k); return o; },
      putAll: (map) => { for (const k of Object.keys(map)) cache.set(k, map[k]); },
    }),
  },
  Utilities: {
    base64EncodeWebSafe: (v) => b64web(typeof v === 'string' ? Buffer.from(v, 'utf8') : Buffer.from(v)),
    base64DecodeWebSafe: (s) => Buffer.from(String(s).replace(/-/g, '+').replace(/_/g, '/'), 'base64'),
    computeHmacSha256Signature: (raw, key) => crypto.createHmac('sha256', key).update(raw).digest(),
    computeDigest: (_a, v) => crypto.createHash('sha256').update(v).digest(),
    DigestAlgorithm: { SHA_256: 'sha256' },
    newBlob: (b) => ({ getDataAsString: () => Buffer.from(b).toString('utf8') }),
    sleep: () => {},                       // the real backoff would just stall the harness
  },
  SpreadsheetApp: {}, HtmlService: {}, UrlFetchApp: {}, Session: {}, Logger: { log() {} },
});
for (const f of ['Core.js', 'Sheets.js', 'Team.js']) {
  runInContext(readFileSync(new URL(f, ROOT), 'utf8'), ctx, { filename: f });
}
/* the one seam: no spreadsheet here */
ctx.loginRows_ = () => FIXTURE_USERS.map((u) => ({ ...u }));

export const HANDLES = (action) => action === 'login' || action === 'session';
export function handle(action, params) {
  if (action === 'login') return ctx.handleLogin_(params);
  if (action === 'session') return ctx.handleSession_(params);
  return { ok: false, error: 'unknown action: ' + action };
}
/** Drop a user from the fixture sheet, to exercise revocation locally. */
export function removeUser(username) {
  const i = FIXTURE_USERS.findIndex((u) => u.username === username);
  if (i >= 0) FIXTURE_USERS.splice(i, 1);
  cache.delete('active_users');
  return FIXTURE_USERS.map((u) => u.username);
}
