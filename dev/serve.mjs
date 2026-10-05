/**
 * Local dev harness for the Realtor Portal Apps Script web app.
 *
 * Serves App.html from disk and shims google.script.run so that
 * app(action, params) is proxied to the deployed web app's JSON API. Lets us
 * edit the UI locally against live data.
 *
 * /api accepts the same call two ways — ?action=… on a GET, or a JSON body on a
 * POST — so the PWA bundle (dev/build.mjs, which only ever POSTs) can be pointed
 * here too: AK_EXEC=http://localhost:4599/api node dev/build.mjs --serve
 */
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { HANDLES as isAuthAction, handle as authHandle, removeUser } from './authshim.mjs';
import { EXEC } from './config.mjs';

const PORT = 4599;
/* The PWA bundle runs on its own origin (:4600), so its responses need to be readable
   cross-origin. text/plain POSTs and GETs are "simple" requests: no preflight to answer. */
const JSON_HEADERS = { 'content-type': 'application/json', 'access-control-allow-origin': '*' };

/* One parameter bag whichever way the request arrived. */
async function params(req, url) {
  if (req.method !== 'POST') return Object.fromEntries(url.searchParams);
  let raw = ''; for await (const chunk of req) raw += chunk;
  try { return JSON.parse(raw || '{}'); } catch { return {}; }
}

const SHIM = `<script>
// dev-only: stand in for the Apps Script client bridge
window.google = window.google || {}; window.google.script = window.google.script || {};
Object.defineProperty(window.google.script, 'run', { get: function () {
  var ok = null, bad = null;
  var chain = {
    withSuccessHandler: function (f) { ok = f; return chain; },
    withFailureHandler: function (f) { bad = f; return chain; },
    app: function (action, p) {
      var q = new URLSearchParams(Object.assign({ action: action }, p || {}));
      fetch('/api?' + q.toString())
        .then(function (r) { return r.json(); })
        .then(function (d) { console.log('[api]', action, d); if (ok) ok(d); })
        .catch(function (e) { console.error('[api:fail]', action, e); if (bad) bad(e); });
    }
  };
  return chain;
} });
</script>`;

createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');

  // dev-only lever: /dev/remove?user=priya drops a fixture user, so the
  // "removed realtor loses access" path can be walked locally.
  if (url.pathname === '/dev/remove') {
    const left = removeUser(url.searchParams.get('user') || '');
    res.writeHead(200, JSON_HEADERS);
    return res.end(JSON.stringify({ ok: true, remaining: left }));
  }

  if (url.pathname === '/api') {
    const p = await params(req, url);
    const action = String(p.action || '');
    // Login and session are answered here by the real Core.js / Sheets.js in a VM
    // against a fixture LOGIN tab, so the auth paths can be walked without touching
    // the team's credentials sheet. Everything else proxies to the live deployment
    // — which is gated, so a locally minted token is refused there; data screens
    // need a token from a real sign-in to come back with data.
    if (isAuthAction(action)) {
      const out = authHandle(action, p);
      console.log(action, '-> local', JSON.stringify(out).length + 'b');
      res.writeHead(200, JSON_HEADERS);
      return res.end(JSON.stringify(out));
    }
    try {
      const upstream = req.method === 'POST'
        ? await fetch(EXEC, { method: 'POST', headers: { 'content-type': 'text/plain;charset=utf-8' }, body: JSON.stringify(p), redirect: 'follow' })
        : await fetch(EXEC + '?' + url.searchParams.toString(), { redirect: 'follow' });
      const body = await upstream.text();
      console.log(action, '->', upstream.status, body.length + 'b');
      res.writeHead(upstream.status, JSON_HEADERS);
      res.end(body);
    } catch (err) {
      console.error('proxy error', err.message);
      res.writeHead(502, JSON_HEADERS);
      res.end(JSON.stringify({ error: String(err.message) }));
    }
    return;
  }

  try {
    let html = await readFile(new URL('../App.html', import.meta.url), 'utf8');
    // Resolve Apps Script partials the way HtmlService.createTemplateFromFile would.
    for (const m of [...html.matchAll(/<\?!=\s*include\('([^']+)'\)\s*\?>/g)]) {
      const part = await readFile(new URL(`../${m[1]}.html`, import.meta.url), 'utf8');
      html = html.replace(m[0], () => part);   // replacer fn: keeps $ sequences literal
    }
    res.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
    res.end(html.replace('</head>', SHIM + '</head>'));
  } catch (err) {
    res.writeHead(500).end(String(err.message));
  }
}).listen(PORT, () => console.log('Realtor Portal dev harness on http://localhost:' + PORT));
