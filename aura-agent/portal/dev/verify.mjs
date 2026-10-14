/* Pre-push verification: load the four server files the way Apps Script does —
   concatenated into ONE global scope — with stubbed platform globals. */
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import vm, { createContext, runInContext } from 'node:vm';

const DIR = new URL('..', import.meta.url).pathname;
const SERVER = ['Core.js', 'Sheets.js', 'Team.js', 'External.js', 'Ai.js', 'Tax.js'];
let fail = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fail++; };

// ---- 1. load all four as one scope, like Apps Script ----
const combined = SERVER.map(f => readFileSync(DIR + f, 'utf8')).join('\n');
const ctx = {
  SpreadsheetApp: { openById: () => { throw new Error('not exercised'); } },
  CacheService: { getScriptCache: () => ({ get: () => null, put: () => {}, getAll: () => ({}), putAll: () => {} }) },
  HtmlService: {
    createHtmlOutputFromFile: (n) => ({ getContent: () => readFileSync(DIR + n + '.html', 'utf8') }),
    createTemplateFromFile: () => ({ evaluate: () => ({ setTitle: () => ({ addMetaTag: () => ({ setXFrameOptionsMode: () => 'PAGE' }) }) }) }),
    XFrameOptionsMode: { DEFAULT: 1 },
  },
  ContentService: { createTextOutput: (t) => ({ setMimeType: () => ({ json: t }) }), MimeType: { JSON: 'json' } },
  UrlFetchApp: { fetch: () => { throw new Error('not exercised'); } },
  Utilities: { base64EncodeWebSafe: () => 'x', computeHmacSha256Signature: () => [1], formatDate: () => '', sleep: () => {}, newBlob: () => ({ getDataAsString: () => '' }), base64DecodeWebSafe: () => [] },
  Logger: { log: () => {} }, console,
};
vm.createContext(ctx);
try { vm.runInContext(combined, ctx); ok(true, 'all four server files load together in one global scope'); }
catch (e) { ok(false, 'load failed: ' + e.message); process.exit(1); }

// ---- 2. every action in the dispatch table resolves to a real function ----
const core = readFileSync(DIR + 'Core.js', 'utf8');
const appBody = core.slice(core.indexOf('function app(action, p)'));
// A case may return the call directly or wrap it in an object literal
// (`return { ok: true, items: fsSuggest_(...) }`); both shapes name a target.
const targets = [...appBody.matchAll(/case '([a-zA-Z]+)':\s*(?:return|)\s*(?:\{[^}]*?)?\b([a-zA-Z_][a-zA-Z_0-9]*)\(/g)];
const missing = targets.filter(m => typeof ctx[m[2]] !== 'function').map(m => `${m[1]} -> ${m[2]}`);
ok(missing.length === 0, `all ${targets.length} app() dispatch targets are defined${missing.length ? ': MISSING ' + missing.join(', ') : ''}`);

// ---- 3. entry points exist ----
['doGet', 'doPost', 'app', 'include'].forEach(f => ok(typeof ctx[f] === 'function', `entry point ${f}() defined`));

// ---- 4. every helper_ called anywhere is defined somewhere ----
const defined = new Set([...combined.matchAll(/^\s*function ([A-Za-z_0-9]+)/gm)].map(m => m[1]));   // incl. nested fns
const called = new Set([...combined.matchAll(/\b([a-zA-Z][A-Za-z_0-9]*_)\(/g)].map(m => m[1]));
const undef = [...called].filter(n => !defined.has(n));
ok(undef.length === 0, `every private helper called is defined${undef.length ? ': MISSING ' + undef.join(', ') : ''} (${defined.size} functions total)`);

// ---- 8. the cache chunker actually round-trips ----
/* The stubs above make CacheService a no-op, so cachePut_/cacheGet_ are never really
   exercised there. Oversized payloads are split across keys, and a bug in that split
   corrupts cached data silently — exactly the failure the chunker exists to fix — so
   it gets a context with a working in-memory cache. */
function cacheCtx() {
  const store = new Map();
  const cache = {
    get: (k) => (store.has(k) ? store.get(k) : null),
    put: (k, v) => { store.set(k, String(v)); },
    getAll: (keys) => { const o = {}; for (const k of keys) if (store.has(k)) o[k] = store.get(k); return o; },
    putAll: (map) => { for (const k of Object.keys(map)) store.set(k, String(map[k])); },
    remove: (k) => { store.delete(k); },
  };
  const c = { ...ctx, CacheService: { getScriptCache: () => cache }, Logger: { log: () => {} } };
  vm.createContext(c);
  vm.runInContext(combined, c);
  return { c, store };
}

{
  const { c, store } = cacheCtx();
  const small = { rows: [{ a: 1 }], note: 'fits in one key' };
  c.cachePut_('small', small);
  ok(JSON.stringify(c.cacheGet_('small')) === JSON.stringify(small), 'cache: a small payload round-trips unchanged');
  ok(store.size === 1, `cache: a small payload stays in ONE key (got ${store.size})`);
}

{
  const { c, store } = cacheCtx();
  // ~460KB of JSON — the size class that was silently dropped before chunking.
  const big = { rows: Array.from({ length: 4000 }, (_, i) => ({ i, city: 'BRAMPTON', project: 'Project ' + i, url: 'https://example.com/' + i })) };
  const raw = JSON.stringify(big);
  c.cachePut_('big', big);
  ok(raw.length > 95000, `cache: fixture is genuinely oversized (${raw.length} chars, old ceiling 95000)`);
  ok(JSON.stringify(c.cacheGet_('big')) === raw, 'cache: an OVERSIZED payload round-trips unchanged (the bug this fixes)');
  ok(store.size > 2, `cache: the oversized payload really was split (${store.size} keys)`);
  ok(String(store.get('big')).startsWith('\u0000chunked:'), 'cache: the head key holds a chunk marker, not data');

  // A partial expiry must read as a miss, never as a truncated payload.
  store.delete('big|1');
  ok(c.cacheGet_('big') === null, 'cache: a missing part reads as a miss, not a torn payload');
}

{
  // A value that merely *starts* like the marker must not be mistaken for one.
  const { c } = cacheCtx();
  const tricky = { s: '\u0000chunked:9 not really a marker' };
  c.cachePut_('tricky', tricky);
  ok(JSON.stringify(c.cacheGet_('tricky')) === JSON.stringify(tricky), 'cache: marker-lookalike data is not misread as chunked');
}

// ---- 9. column-scoped reads pull from the RIGHT column ----
/* Several readers stopped fetching rich text / formulas for a whole sheet and now
   fetch just the link and date columns. That swapped a full-width column index for a
   single-column one at every use site — get it wrong and links silently come from the
   neighbouring column, which no type check would catch. */
function fakeSheet(rows, links) {
  const nR = rows.length, nC = Math.max(...rows.map((r) => r.length));
  const wide = [];                                     // widths asked for, to prove scoping
  const cell = (r, c) => (rows[r] && rows[r][c] != null ? rows[r][c] : '');
  const rich = (r, c) => ({ getLinkUrl: () => links[r + ',' + c] || null, getRuns: () => [] });
  function range(row, col, nr, nc) {
    if (row < 1 || col < 1 || row - 1 + nr > nR || col - 1 + nc > nC) throw new Error('out of bounds');
    const pick = (fn) => {
      const out = [];
      for (let i = 0; i < nr; i++) { const line = []; for (let j = 0; j < nc; j++) line.push(fn(row - 1 + i, col - 1 + j)); out.push(line); }
      return out;
    };
    return {
      getDisplayValues: () => pick((r, c) => String(cell(r, c))),
      getValues: () => pick(cell),
      getRichTextValues: () => { wide.push(nc); return pick(rich); },
      getFormulas: () => pick(() => ''),
    };
  }
  return {
    __richWidths: wide,
    getLastRow: () => nR, getLastColumn: () => nC, getName: () => 'Events',
    getDataRange: () => range(1, 1, nR, nC),
    getRange: (a, b, c, d) => range(a, b, c, d),
  };
}

{
  const { c } = cacheCtx();
  const sh = fakeSheet(
    [['DATE', 'TITLE', 'LOCATION', 'LINK'],
     ['2026-09-01', 'Team Meeting', 'HQ', 'Register'],
     ['2026-09-15', 'Bootcamp', 'Zoom', 'Sign up']],
    // A decoy link on TITLE: reading the wrong column would grab this instead.
    { '1,3': 'https://example.com/a', '2,3': 'https://example.com/b', '1,1': 'https://WRONG-COLUMN' },
  );
  const rows = c.readLoose_(sh, { date: ['DATE'], title: ['TITLE'], location: ['LOCATION'], link: ['LINK', 'URL'] }, 'title');

  ok(rows.length === 2, `readLoose_: returns both data rows (got ${rows.length})`);
  ok(rows[0] && rows[0].title === 'Team Meeting', 'readLoose_: reads plain text columns');
  ok(rows[0] && rows[0].link === 'https://example.com/a', `readLoose_: link comes from the LINK column (got ${rows[0] && rows[0].link})`);
  ok(rows[1] && rows[1].link === 'https://example.com/b', 'readLoose_: link column stays aligned on later rows');
  ok(!rows.some((r) => String(r.link).includes('WRONG-COLUMN')), 'readLoose_: does NOT pick up a link from a neighbouring column');
  ok(rows[0] && rows[0].iso === '2026-09-01', `readLoose_: date column still resolves (got ${rows[0] && rows[0].iso})`);
  ok(sh.__richWidths.every((w) => w === 1), `readLoose_: rich text fetched one column at a time (widths ${sh.__richWidths.join(',')})`);
}

// ---- clasp must never push the dev harness as server code ----
// .clasp.json has rootDir "" and skipSubdirectories false, so every .js/.html/.json
// in this folder is a candidate. dev/ is Node code that would throw in the
// server's global scope before doGet could answer.
{
  const ignorePath = DIR + '.claspignore';
  ok(existsSync(ignorePath), '.claspignore exists');
  const ignore = existsSync(ignorePath) ? readFileSync(ignorePath, 'utf8') : '';
  ok(ignore.includes('dev/**'), '.claspignore covers dev/**');

  /* Naming the known offenders only guards the ones that existed when the list
     was written. A design handoff dropped in the repo root shipped a browser
     bundle and a support.js, neither of them ignored, and clasp listed both as
     server files -- top-level DOM code that would have thrown on every request.
     So the rule is inverted here: anything in the root that is not a server file
     has to be ignored explicitly, and a new folder fails this check the day it
     appears rather than the day someone pushes. */
  const SERVER_FILES = ['Core.js', 'Sheets.js', 'Team.js', 'External.js', 'Ai.js', 'Audit.js', 'Tax.js',
                        'appsscript.json'];
  const stray = readdirSync(DIR)
    .filter((n) => !n.startsWith('.'))
    .filter((n) => !SERVER_FILES.includes(n))
    .filter((n) => !ignore.split('\n').some((line) => {
      line = line.trim();
      if (!line || line.startsWith('#')) return false;
      /* An extension glob counts. Without this the only way to satisfy the check
         was one line per file, so every new doc needed a .claspignore entry to
         guard against a push that .clasp.json's extension list already made
         impossible -- and deleting one of those redundant-looking lines failed
         verification for a reason nobody could see from the line itself. */
      if (line.startsWith('*.')) return n.endsWith(line.slice(1));
      return line === n || line.startsWith(n + '/') || line.startsWith(n + '**');
    }));
  ok(stray.length === 0,
     stray.length ? `every non-server path is ignored by clasp (NOT ignored: ${stray.join(', ')})`
                  : 'every non-server path is ignored by clasp');
}

console.log(fail ? `\n${fail} CHECK(S) FAILED` : '\nALL CHECKS PASSED');
process.exit(fail ? 1 : 0);
