/**
 * Local stand-in for the portal's JSON API, for aura-agent/bin/dev.
 *
 * /api answers sign-in locally (authshim.mjs) and proxies every other action to
 * the deployed web app. It accepts the call two ways: ?action=… on a GET, or a
 * JSON body on a POST, which is what the agent sends.
 */
import { createServer } from 'node:http';
import { HANDLES as isAuthAction, handle as authHandle, removeUser } from './authshim.mjs';
import { EXEC } from './config.mjs';

const PORT = 4599;
const JSON_HEADERS = { 'content-type': 'application/json' };

/* One parameter bag whichever way the request arrived. */
async function params(req, url) {
  if (req.method !== 'POST') return Object.fromEntries(url.searchParams);
  let raw = ''; for await (const chunk of req) raw += chunk;
  try { return JSON.parse(raw || '{}'); } catch { return {}; }
}

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

  res.writeHead(404, JSON_HEADERS).end(JSON.stringify({ error: 'not found' }));
}).listen(PORT, () => console.log('portal stand-in on http://localhost:' + PORT + '/api'));
