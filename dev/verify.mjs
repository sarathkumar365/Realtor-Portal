/* Pre-push verification: load the four server files the way Apps Script does —
   concatenated into ONE global scope — with stubbed platform globals. */
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import vm, { createContext, runInContext } from 'node:vm';

const DIR = '/Users/sarathkumar/Projects/2Creative/Realtor-Portal/';
const SERVER = ['Core.js', 'Sheets.js', 'Team.js', 'External.js', 'Ai.js', 'Tax.js'];
let fail = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fail++; };

// ---- 1. load all four as one scope, like Apps Script ----
const combined = SERVER.map(f => readFileSync(DIR + f, 'utf8')).join('\n');
const htmlReads = [];
const ctx = {
  SpreadsheetApp: { openById: () => { throw new Error('not exercised'); } },
  CacheService: { getScriptCache: () => ({ get: () => null, put: () => {}, getAll: () => ({}), putAll: () => {} }) },
  HtmlService: {
    createHtmlOutputFromFile: (n) => { htmlReads.push(n); return { getContent: () => readFileSync(DIR + n + '.html', 'utf8') }; },
    createTemplateFromFile: (n) => { htmlReads.push(n); return { evaluate: () => ({ setTitle: () => ({ addMetaTag: () => ({ setXFrameOptionsMode: () => 'PAGE' }) }) }) }; },
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

// ---- 5. include() targets exist on disk with exact-case names ----
const appHtml = readFileSync(DIR + 'App.html', 'utf8');
const incs = [...appHtml.matchAll(/include\('([^']+)'\)/g)].map(m => m[1]);
ok(incs.length === 2, `App.html declares ${incs.length} includes: ${incs.join(', ')}`);
incs.forEach(n => ok(existsSync(DIR + n + '.html'), `include('${n}') resolves to ${n}.html on disk (case-exact)`));

// ---- 6. include() actually returns the partial content through the real code path ----
incs.forEach(n => {
  const out = ctx.include(n);
  ok(out.length > 100 && out === readFileSync(DIR + n + '.html', 'utf8'), `include('${n}') returns ${n}.html verbatim (${out.length} bytes)`);
});

// ---- 7. doGet with no action takes the template path and names the right file ----
htmlReads.length = 0;
ctx.doGet({ parameter: {} });
ok(htmlReads.includes('App'), `doGet() with no action renders template 'App' (read: ${htmlReads.join(', ')})`);

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

// ---- clasp must never push the PWA bundle or the dev harness as server code ----
// .clasp.json has rootDir "" and skipSubdirectories false, so every .js/.html/.json
// in the repo is a candidate. www/app.js in the server's global scope would throw
// on `document` before doGet could answer — and the guard lives in .claspignore,
// which git carries per branch while the generated www/ lingers across checkouts.
{
  const ignorePath = DIR + '.claspignore';
  ok(existsSync(ignorePath), '.claspignore exists');
  const ignore = existsSync(ignorePath) ? readFileSync(ignorePath, 'utf8') : '';
  for (const dir of ['www/**', 'dev/**', 'assets/**']) ok(ignore.includes(dir), `.claspignore covers ${dir}`);

  /* Naming the known offenders only guards the ones that existed when the list
     was written. A design handoff dropped in the repo root shipped a browser
     bundle and a support.js, neither of them ignored, and clasp listed both as
     server files -- top-level DOM code that would have thrown on every request.
     So the rule is inverted here: anything in the root that is not a server file
     has to be ignored explicitly, and a new folder fails this check the day it
     appears rather than the day someone pushes. */
  const SERVER_FILES = ['App.html', 'Styles.html', 'Script.html',
                        'Core.js', 'Sheets.js', 'Team.js', 'External.js', 'Ai.js', 'Audit.js', 'Tax.js',
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

// ---- 9. the Aura chat screen ----
// These are not style preferences. Each one is a rule the chat's layout or its
// safety depends on, in a place where nothing else would notice it breaking.
{
  const styles = readFileSync(DIR + 'Styles.html', 'utf8');
  const script = readFileSync(DIR + 'Script.html', 'utf8');
  const appSrc = readFileSync(DIR + 'App.html', 'utf8');

  // Without this the iOS keyboard covers the composer: Safari resizes only the
  // visual viewport, so 100dvh keeps reporting the pre-keyboard height.
  ok(/content="[^"]*interactive-widget=resizes-content/.test(appSrc),
     'viewport meta sets interactive-widget=resizes-content (the iOS keyboard fix)');

  ['aura', 'auraList', 'auraInput', 'auraForm', 'askFab'].forEach((id) =>
    ok(appSrc.includes(`id="${id}"`), `App.html defines #${id}`));

  // The one structural rule the whole screen rests on. A fixed element inside the
  // chat sits behind the iOS keyboard; the flex column does the pinning instead.
  const auraCss = styles.slice(styles.indexOf('/* ---- Aura chat'));
  ok(auraCss.length > 500, 'Styles.html carries the Aura chat block');
  ok(!/\.aura[^{]*\{[^}]*position:\s*fixed/.test(auraCss.replace(/^\.aura\{[^}]*\}/m, '')),
     'nothing inside the chat is position:fixed except .aura itself');
  ok(/\.aura-list\{[^}]*overscroll-behavior:contain/.test(auraCss),
     '.aura-list contains its overscroll (the page behind must not drag)');
  // This used to assert height:100dvh, which was the bug. inset:0 sizes the panel
  // from its fixed containing block -- the real viewport, on any device -- and an
  // explicit height overrides that bottom edge, leaving a strip of page showing
  // under the composer wherever dvh and the layout viewport disagree.
  ok(/\.aura\{[^}]*inset:0/.test(auraCss), '.aura is sized by inset:0');
  ok(!/\.aura\{[^}]*[^-]height:/.test(auraCss),
     '.aura sets no explicit height, so nothing can override inset:0 bottom');
  // The composer must never show a scrollbar it did not earn; auraGrow turns
  // overflow on only at the cap.
  ok(/\.aura-cmp textarea\{[^}]*overflow-y:hidden/.test(auraCss),
     'the composer starts with overflow hidden, not auto');
  ok(/parseFloat\(cs\.borderTopWidth\)/.test(script),
     'auraGrow adds the border back (border-box height excludes what scrollHeight measures)');
  ok(/body\.chat\{[^}]*overflow:hidden/.test(auraCss), 'body.chat locks the page behind');
  ok(/body\.chat[^{]*\.tabbar[^{]*\{display:none\}|body\.chat .*\.tabbar.*display:none/.test(auraCss),
     'body.chat hides the tab bar and the chat button');
  // 16px or iOS zooms the page on focus and never zooms back out.
  ok(/\.aura-cmp textarea\{[^}]*font-size:max\(16px/.test(auraCss),
     'the composer clears the 16px floor that stops iOS zooming on focus');

  ok(/LOAD\.chat\s*=\s*loadChat/.test(script), 'Script.html registers the #chat route');
  ['start', 'tool', 'tool_result', 'text', 'projects', 'done', 'error'].forEach((t) =>
    ok(script.includes(`'${t}'`), `the SSE event '${t}' is handled`));
  // EventSource is GET-only and cannot set an Authorization header, so reaching
  // for it would mean putting the bearer token in the URL.
  ok(!script.includes('new EventSource('), 'the chat streams with fetch, never EventSource');
  // Model output is data, not markup. The mechanism changed from textContent to
  // a node-building markdown renderer; the guarantee must not have.
  ok(/auraMd\(body,\s*text\)/.test(script), 'streamed model text goes through auraMd, not innerHTML');

  // One card renderer, three screens. Two inline copies had already drifted apart.
  ok(/function projectCard\(/.test(script), 'projectCard() exists');
  const calls = (script.match(/projectCard\(/g) || []).length - 1;
  ok(calls >= 3, `projectCard() is called from all three screens (found ${calls})`);
  ok(!/class="card"><span class="pill focus">/.test(script),
     'no inline project-card markup survives outside projectCard()');

  // The chat must not ship to the Apps Script host, which cannot stream to it.
  ok(/function auraReady\(\)\{ return !!window\.AURA_BASE/.test(script),
     'the chat is gated on window.AURA_BASE');
  ok(readFileSync(DIR + 'dev/build.mjs', 'utf8').includes('window.AURA_BASE='),
     'dev/build.mjs emits window.AURA_BASE into the PWA bundle');
  ok(/localStorage\.removeItem\('ak_aura'\)/.test(script),
     'signing out drops the saved chat thread');
  // Retry must remove ITS OWN turn. pop() took whatever was last, so a retry
  // tapped after a newer question deleted that newer answer instead.
  ok(!/AURA_TURNS\.pop\(\)/.test(script), 'retry does not pop() a turn by position');
  ok(/AURA_TURNS\.indexOf\(myTurn\)/.test(script), 'retry removes the turn it created, by identity');
  // A leftover from a rename; assigning to an undeclared name leaks a global.
  ok(!/AURA_LAST/.test(script), 'no assignment to an undeclared AURA_LAST');
  ok(/aria-busy/.test(script),
     'the live region is marked busy while streaming, so the answer is announced once');
}

// ---- 10. projectCard() still renders exactly what it replaced ----
// Home and city each had their own inline copy. Pulling them into one function
// is only safe if the output did not move, and "it looked fine" is not a check
// anyone can repeat six months from now. The pre-extraction templates are kept
// here verbatim and diffed against the shared renderer.
{
  const script = readFileSync(DIR + 'Script.html', 'utf8');
  const grab = (name) => {
    const at = script.indexOf('function ' + name + '(');
    if (at === -1) throw new Error('verify: ' + name + '() not found in Script.html');
    // Brace-match from the signature so a nested closure does not end it early.
    let i = script.indexOf('{', at), depth = 0;
    for (let j = i; j < script.length; j++) {
      if (script[j] === '{') depth++;
      else if (script[j] === '}' && --depth === 0) return script.slice(at, j + 1);
    }
    throw new Error('verify: ' + name + '() is unbalanced');
  };
  const sandbox = { out: null };
  createContext(sandbox);
  runInContext(['esc', 'isUrl', 'safeUrl', 'linkBtn', 'money', 'pct', 'clip', 'projectCard'].map(grab).join('\n'), sandbox);

  // The two renderers as they stood before the extraction, character for character.
  runInContext(`
    function oldHome(p){var meta=[p.builder,p.type,p.occupancy].filter(Boolean).join(' · ');return '<div class="card"><span class="pill focus">Focus</span><div class="card-t">'+esc(p.project||p.name||'Project')+'</div>'+(p.city?'<div class="card-s">'+esc(p.city)+(meta?' · '+esc(meta):'')+'</div>':(meta?'<div class="card-s">'+esc(meta)+'</div>':''))+'<div class="lnkrow">'+linkBtn('Builder',p.broker_url)+linkBtn('Drive',p.drive_url)+linkBtn('Website',p.website_url)+'</div></div>';}
    function oldCity(p){var foc=/focus/i.test(p.status||'');return '<div class="card">'+(foc?'<span class="pill focus">Focus</span>':'')+'<div class="card-t">'+esc(p.name||p.project||'Project')+'</div>'+(p.status&&!foc?'<div class="card-s">'+esc(p.status)+'</div>':'')+'<div class="lnkrow">'+linkBtn('Builder',p.broker_url)+linkBtn('Drive',p.drive_url)+linkBtn('Website',p.website_url)+'</div></div>';}
    var ROWS=[
      {project:'DUO',name:'Duo Condos',city:'Brampton',builder:'National',type:'Condo',occupancy:'2027',status:'Focus Project',broker_url:'https://b.x',drive_url:'https://d.x',website_url:'https://w.x'},
      {name:'Reva',city:'Oakville',status:'Selling',broker_url:'',drive_url:'',website_url:'https://w.x'},
      {name:'NoCity',builder:'B'},
      {project:'',name:'',city:'',status:''},
      {name:'Quote "X" & <b>',city:'T',status:'focus now'}
    ];
    out=[];
    ROWS.forEach(function(p,i){
      if(oldHome(p)!==projectCard(p,{focus:true,project:true})) out.push('home#'+i);
      if(oldCity(p)!==projectCard(p,{bits:['status']})) out.push('city#'+i);
    });
  `, sandbox);
  ok(sandbox.out.length === 0,
     sandbox.out.length
       ? `projectCard() output drifted from the screens it replaced: ${sandbox.out.join(', ')}`
       : 'projectCard() renders home and city byte-for-byte as the inline versions did');

  // ---- 10b. the AUR-46 fields ----
  // They arrive on every payload, so the only thing keeping them off home and
  // city is that the options default off. Worth testing rather than trusting.
  const CHAT = { price: true, deposit: true, incentive: true };
  runInContext(`
    var P={name:'DUO',city:'Brampton',starting_price:370990,depositpct:10,
           depositsched:'$10k on signing, balance to 10% in 180 days',
           incentives:'Free assignment + $10k credit'};
    out={
      chat: projectCard(P, ${JSON.stringify(CHAT)}),
      bare: projectCard(P, {}),
      home: projectCard(P, {focus:true,project:true}),
      city: projectCard(P, {bits:['status']}),
      numPct: pct(10), floatPct: pct(10.5), textPct: pct('10%'), barePct: pct('10'),
      prose: pct('$50k then 5% at closing'), emptyPct: pct(null),
      schedOnly: projectCard({name:'X',depositsched:'$50k on signing'}, {deposit:true}),
      longInc: projectCard({name:'X',incentives:'i'.repeat(400)}, {incentive:true}),
      xss: projectCard({name:'X',incentives:'<img src=x onerror=alert(1)>'}, {incentive:true})
    };
  `, sandbox);
  const r = sandbox.out;
  ok(/10% deposit/.test(r.chat), 'a chat card shows the deposit percentage');
  ok(/Free assignment/.test(r.chat), 'a chat card shows the incentive');
  ok(!/deposit|Free assignment/.test(r.home) && !/deposit|Free assignment/.test(r.city),
     'home and city show neither -- the options default off');
  ok(!/deposit|Free assignment/.test(r.bare), 'no options means no new lines at all');
  ok(r.numPct === '10%' && r.floatPct === '10.5%' && r.textPct === '10%' && r.barePct === '10%',
     'pct() formats a number and normalises sheet text to the same thing');
  ok(r.prose === '$50k then 5% at closing',
     'pct() passes a real schedule through rather than inventing a percentage from it');
  ok(r.emptyPct === '', 'pct() of nothing is nothing, not "0%"');
  ok(/\$50k on signing/.test(r.schedOnly),
     'a schedule with no percentage still shows -- it says something on its own');
  ok(r.longInc.length < 400 && /…/.test(r.longInc), 'a long incentive is clipped, not wrapped over four lines');
  ok(!/<img/.test(r.xss) && /&lt;img/.test(r.xss), 'a sheet cell cannot inject markup through the incentive line');
}

// ---- 11. the markdown renderer ----
// The model writes markdown whether asked to or not, and there is no API flag
// that stops it. What must hold is that rendering it never turns model text into
// markup -- so this checks the parser's output on real captured answers, and
// checks the renderer builds nodes rather than assigning HTML.
{
  const script = readFileSync(DIR + 'Script.html', 'utf8');
  const grab = (name) => {
    const at = script.indexOf('function ' + name + '(');
    if (at === -1) throw new Error('verify: ' + name + '() not found in Script.html');
    let i = script.indexOf('{', at), depth = 0;
    for (let j = i; j < script.length; j++) {
      if (script[j] === '{') depth++;
      else if (script[j] === '}' && --depth === 0) return script.slice(at, j + 1);
    }
    throw new Error('verify: ' + name + '() is unbalanced');
  };

  // The renderer is the only part that touches the page. An attribute set from
  // model text is the one thing that could make a link or a script out of a
  // project name, so neither may appear.
  const render = grab('auraMdRender');
  ok(!/innerHTML/.test(render), 'auraMdRender never assigns innerHTML');
  ok(!/setAttribute|\.href|\.src\b/.test(render), 'auraMdRender never sets an attribute');
  ok(/createElement/.test(render) && /createTextNode/.test(render),
     'auraMdRender builds nodes with createElement/createTextNode');
  // auraPaint still uses innerHTML for the starter-prompt empty state, which is
  // our own literal markup. What must never happen is a *turn's content* going
  // in that way -- the saved answers have to come back through the renderer, or
  // a reopened chat shows the asterisks the live stream had just hidden.
  const paint = grab('auraPaint');
  ok(/auraMd\(/.test(paint), 'restored answers go through the markdown renderer');
  ok(!/esc\(\s*t\.content\s*\)/.test(paint),
     'no turn content is interpolated into an HTML string');

  const box = { out: null };
  createContext(box);
  runInContext([grab('auraMdSpans'), grab('auraMdParse')].join('\n'), box);
  const parse = (t) => { box.t = t; runInContext('out = auraMdParse(t)', box); return box.out; };
  const flat = (b) => (b.t === 'ul' ? b.items.map(i => i.map(s => s.s).join('')) : b.spans.map(s => s.s).join(''));

  // A real answer, captured verbatim from the deployed service.
  const real = 'Here are Ivy-Rogue and East Preserve:\n\n**Ivy-Rogue**\n*   **Builder:** Starlane Home Corporation\n*   **City:** OAKVILLE';
  const blocks = parse(real);
  ok(blocks.length === 3 && blocks[2].t === 'ul',
     `a real captured answer parses to prose + heading + list (got ${blocks.map(b => b.t).join(',')})`);
  ok(flat(blocks[1]) === 'Ivy-Rogue', 'the ** markers are consumed, not shown');
  ok(blocks[1].spans[0].b === true, 'bold is marked as bold rather than left as asterisks');
  ok(JSON.stringify(flat(blocks[2])) === JSON.stringify(['Builder: Starlane Home Corporation', 'City: OAKVILLE']),
     'list items keep their text and lose their bullets');

  // Mid-stream: a ** whose partner has not arrived must not flash as punctuation.
  ok(!JSON.stringify(parse('The cheapest is **DUO')).includes('**'),
     'an unterminated ** is suppressed while the answer is still streaming');

  // Markup in the model's text stays text. The renderer cannot make an element
  // from it -- this proves the parser does not smuggle it through as structure.
  const evil = parse('<img src=x onerror=alert(1)> and **<b>bold</b>**');
  const text = evil.map(flat).join('');
  ok(text.includes('<img src=x onerror=alert(1)>') && text.includes('<b>bold</b>'),
     'HTML in the answer survives as literal text, never as structure');

  ok(parse('plain sentence, no markdown at all').length === 1,
     'ordinary prose is one paragraph and nothing else');
  ok(!/white-space:pre-wrap/.test(readFileSync(DIR + 'Styles.html', 'utf8').split('.aura-ai{')[1].split('}')[0]),
     '.aura-ai no longer preserves whitespace (the parser owns line breaks now)');
}

// ---- 12. the SSE reader ----
// The most protocol-sensitive code in the client, and the easiest to break
// silently: a frame that straddles two network chunks, or a stream that ends
// without saying how, both look like "nothing happened" at the UI.
{
  const script = readFileSync(DIR + 'Script.html', 'utf8');
  const at = script.indexOf('function auraStream(');
  let depth = 0, end = -1;
  for (let j = script.indexOf('{', at); j < script.length; j++) {
    if (script[j] === '{') depth++;
    else if (script[j] === '}' && --depth === 0) { end = j + 1; break; }
  }
  const src = script.slice(at, end);

  // Feed the reader arbitrary chunk boundaries and collect what comes out.
  const run = async (chunks) => {
    const sandbox = { TextDecoder, out: [], chunks, result: null };
    createContext(sandbox);
    runInContext(`
      ${src}
      var i = 0;
      var body = { getReader: function () { return { read: function () {
        return Promise.resolve(i < chunks.length
          ? { done: false, value: chunks[i++] }
          : { done: true });
      } }; } };
      result = auraStream(body, function (ev) { out.push(ev.type); });
    `, sandbox);
    return { ended: await sandbox.result, seen: sandbox.out };
  };
  const enc = (s) => new TextEncoder().encode(s);
  const DONE = 'data: {"type":"done"}\n\n';

  let r = await run([enc('data: {"type":"text"}\n\n' + DONE)]);
  ok(r.ended === true && r.seen.join(',') === 'text,done', 'a whole stream reads both events and reports it ended');

  // The real reason this test exists: chunk boundaries follow the network, not
  // the protocol, so a frame can arrive in pieces -- even mid-token.
  r = await run([enc('data: {"typ'), enc('e":"text"}\n'), enc('\n' + DONE)]);
  ok(r.ended === true && r.seen.join(',') === 'text,done', 'a frame split across three chunks still parses');

  // Ending with no done/error: iOS suspending a backgrounded fetch, a proxy
  // timeout, a container recycled mid-answer. Must NOT look like success.
  r = await run([enc('data: {"type":"text"}\n\n')]);
  ok(r.ended === false, 'a stream that ends without a terminator reports ended=false');
  ok(r.seen.join(',') === 'text', 'the events that did arrive are still delivered');

  r = await run([enc('data: {"type":"error","detail":"x"}\n\n')]);
  ok(r.ended === true, 'an error event counts as a terminator');

  // A final frame with no trailing blank line is still a frame.
  r = await run([enc('data: {"type":"text"}\n\n' + 'data: {"type":"done"}')]);
  ok(r.ended === true, 'a last frame without its blank line is not dropped');

  r = await run([enc(': keepalive\n\n' + 'data: not json\n\n' + DONE)]);
  ok(r.ended === true && r.seen.join(',') === 'done', 'comments and unparseable lines are skipped, not fatal');
}


// ---- 12. the feedback row (AUR-59, AUR-60) ----
// The only place in the chat that POSTs anything but a question, and the only
// one gated on the mode.
{
  const script = readFileSync(DIR + 'Script.html', 'utf8');
  const grab = (name) => {
    const at = script.indexOf('function ' + name + '(');
    if (at === -1) throw new Error('verify: ' + name + '() not found in Script.html');
    let i = script.indexOf('{', at), depth = 0;
    for (let j = i; j < script.length; j++) {
      if (script[j] === '{') depth++;
      else if (script[j] === '}' && --depth === 0) return script.slice(at, j + 1);
    }
    throw new Error('verify: ' + name + '() is unbalanced');
  };

  const row = grab('auraFeedbackRow');
  const pyAll = readFileSync(DIR + 'aura-chat/app/domain/feedback.py', 'utf8');
  ok(/AURA_MODE==='client'/.test(row) && /return null/.test(row),
     'the feedback row is not rendered in Client Mode');
  ok(/!turn\.id/.test(row),
     'an answer with no id gets no row -- a vote that cannot be attributed is not offered');
  // Written inside the .then, so a failed POST cannot leave a reopened chat
  // claiming the report was sent.
  const persistAt = row.indexOf('turn.fb=verdict');
  const thenAt = row.indexOf('.then(function(){');
  ok(persistAt > thenAt && thenAt !== -1,
     'the verdict is persisted only after the POST resolves, never before');
  ok(/fb-fail/.test(row) && /Try again/.test(row),
     'a feedback POST that fails says so and offers a retry');

  // A data issue is a claim about the SHEET, a thumb about the ANSWER.
  const sheetBody = row.slice(row.indexOf('function sheet(verdict)'), row.indexOf('function buttons()'));
  ok(/function sheet\(verdict\)/.test(row),
     'the category sheet knows which button opened it');
  ok(!/send\('down'/.test(sheetBody),
     'the sheet files the verdict it was opened with, never a hardcoded thumbs-down');
  ok(/rep\.addEventListener\('click',function\(\)\{ sheet\(null\); \}\)/.test(row),
     '"Report data issue" opens the sheet with no verdict attached');
  ok(/sheet\('down'\)/.test(row), 'the thumbs-down carries its vote into the sheet');

  // The only free text a realtor can send.
  ok(/if\(verdict\) send\(verdict,null,note\.value\); else buttons\(\);/.test(row),
     'Skip carries the note, and with no vote to file it cancels instead');
  ok(/go\.disabled=!chosen&&!note\.value\.trim\(\)/.test(row),
     'a note with no category still enables Send, so nothing typed is orphaned');

  ok(/verdict is None and self\.category is None and not self\.note\.strip\(\)/.test(pyAll),
     'the server refuses a report carrying neither verdict, category nor note');
  // max_length on a list bounds the count, not the items: twelve 200kB ids was
  // a valid body, and a 2.3MB log line.
  ok(/ProjectId = Annotated\[str, StringConstraints\(max_length=MAX_ID_LEN\)\]/.test(pyAll)
     && /project_ids: list\[ProjectId\]/.test(pyAll),
     'each project id is length-capped, not just the number of them');

  // The answer text is the thing this endpoint was shaped to not carry.
  const post = row.slice(row.indexOf('auraPostFeedback({'), row.indexOf('}).then'));
  ok(!/content|answer:|text/.test(post),
     'the feedback payload carries no answer text -- only the question and the verdict');
  // Read out of the Python, not hardcoded: grepping for the literals while
  // claiming server parity meant a tightened MAX_QUESTION stayed green.
  const pyCap = (name) => {
    const m = pyAll.match(new RegExp('^' + name + ' = (\\d+)$', 'm'));
    if (!m) throw new Error('verify: ' + name + ' not found in feedback.py');
    return m[1];
  };
  const qCap = pyCap('MAX_QUESTION'), nCap = pyCap('MAX_NOTE');
  ok(/answer_id:turn\.id/.test(post), 'the payload keys the report to the answer');
  ok(post.includes('question:clip(question,' + qCap + ')')
     && post.includes('note:clip(note,' + nCap + ')'),
     `the client clips to the server's own caps (question ${qCap}, note ${nCap})`);

  // The categories must match app/domain/feedback.py, or a report files itself
  // under a category the queue has no column for.
  const py = pyAll;
  // Scoped to IssueCategory: Verdict is the same shape one class up.
  const cats = py.slice(py.indexOf('class IssueCategory'), py.indexOf('class Feedback'));
  const server = [...cats.matchAll(/^\s{4}[A-Z_]+ = "([a-z_]+)"$/gm)].map((m) => m[1]);
  // Scoped to AURA_ISSUES: other [key,label] pairs share the shape, and one of
  // them is also called 'other'.
  const issuesAt = script.indexOf('var AURA_ISSUES=[');
  const issues = script.slice(issuesAt, script.indexOf('];', issuesAt));
  const client = [...issues.matchAll(/\['([a-z_]+)','[^']+'\]/g)].map((m) => m[1]);
  ok(server.length === 7, `the server declares exactly the 7 AUR-60 categories (got ${server.length})`);
  ok(server.every((v) => client.includes(v)) && client.length === 7,
     'every server category has a label in AURA_ISSUES and none is invented');

  // The row is built with DOM nodes; a sheet value or a realtor's note reaching
  // innerHTML would be the one injection point the rest of the chat avoids.
  ok(!/innerHTML\s*=\s*[^;]*(?:question|note|content)/.test(row),
     'no user or model text is interpolated into HTML in the feedback row');
  ok(/textContent/.test(row) && /createElement/.test(row),
     'the feedback row is built from nodes, not from an HTML string');

  const posted = grab('auraPostFeedback');
  ok(/'Authorization':'Bearer '\+TOKEN/.test(posted), 'feedback is sent authenticated');
  ok(/\/feedback/.test(posted), 'feedback goes to /feedback');

  // History is what the realtor pays tokens for. The stored turns now carry
  // three fields the model has no use for.
  const ask = grab('auraAsk');
  ok(/return \{role:t\.role,content:t\.content\}/.test(ask),
     'chat history is trimmed to role and content -- ids and verdicts do not go to the model');

  // Phase 4a. Once the server owns the thread the client must stop asserting
  // what was said -- otherwise it is shipping tokens the realtor pays for and a
  // claim it is not entitled to make.
  ok(/var history=AURA_CID\?\[\]:/.test(ask),
     'history is sent only until the server owns the conversation');
  ok(/conversation_id:AURA_CID/.test(ask), 'the conversation id is sent with every question');
  ok(/AURA_CID=ev\.conversation_id/.test(ask),
     'a new chat learns its id from the start event, not a second request');
  const mode2 = grab('auraMode'), fresh = grab('auraNewChat');
  ok(/AURA_CID=null/.test(mode2) && /AURA_CID=null/.test(fresh),
     'New Chat and a mode flip both start a different conversation, not the same one');
  ok(/c:AURA_CID/.test(grab('auraSave')) && /AURA_CID=o\.c/.test(grab('auraLoad')),
     'the conversation id survives closing the app');

  // A stale id used to be unclearable: only assigning when truthy meant a
  // refused id survived, and every later question shipped it with an empty
  // history -- nothing stored, no context, silently, forever.
  ok(/AURA_CID=ev\.conversation_id\|\|null/.test(ask),
     'the conversation id can go back to null, so a refused one is not permanent');
  ok(/AURA_CID=null/.test(grab('forgetData')),
     'signing out drops the conversation id with the rest of the thread');

  // The rate limit (AUR-21) answers 429. Without its own branch that falls into
  // the generic throw below it and reads "Could not reach Aura." -- the one
  // thing that is certainly untrue, because we reached it and it replied.
  ok(/r\.status===429/.test(ask) && ask.indexOf('r.status===429') < ask.indexOf("throw new Error('HTTP '"),
     'a rate-limited answer is named before the generic HTTP failure');
  ok(/Retry-After/.test(ask),
     'the wait the server asked for is what the realtor is told');

  // ---- the chats panel (AUR-38, AUR-50) ----
  const wire = script.slice(script.indexOf('function auraWire()'));
  ok(/\$\('auraNew'\)\.addEventListener\('click',auraHistOpen\)/.test(wire),
     'the header button opens the chats panel');
  ok(/\$\('auraHistNew'\)\.addEventListener\('click',auraNewChat\)/.test(wire),
     'New Chat lives inside the panel, so the header keeps four controls');
  ok(/auraHistClose/.test(grab('auraNewChat')) && /auraHistClose/.test(grab('auraMode')),
     'anything that replaces the thread closes the panel over it');

  const open = grab('auraOpenThread');
  // The stored mode has to land before a turn is painted: a Client thread that
  // comes back blue and switches a moment later defeats the header.
  ok(open.indexOf('AURA_MODE=') !== -1
     && open.indexOf('AURA_MODE=') < open.indexOf('auraPaint()'),
     'a reopened thread applies its stored mode before it paints');
  ok(/auraStop\(\)/.test(open),
     'opening another thread aborts the one still streaming');
  // auraFeedbackRow returns null without an id, so an id-less turn silently
  // loses its thumbs on reopen.
  ok(/id:m\.id/.test(open), 'reopened answers keep their message id, so feedback still works');
  ok(/m\.sources/.test(open), 'and the projects they cited, so a report still names them');
  ok(!/auraCards/.test(open),
     'reopened answers do not rebuild cards -- shared id slugs would show the wrong project');

  const hist = grab('auraHistPaint');
  ok(/createElement/.test(hist) && !/innerHTML/.test(hist),
     'chat titles are set as text, never interpolated into HTML');
  ok(/r\.status===503/.test(grab('auraHistLoad')),
     'a store that is down reads as unavailable, not as a generic failure');

  // ---- the reports queue (AUR-62) ----
  ok(/!n\.admin\|\|AURA_ADMIN/.test(grab('buildNav')),
     'the reports row is drawn only for an admin');
  const who = grab('auraWhoAmI');
  ok(/'\/me'/.test(who) && /d\.admin/.test(who),
     'admin comes from the service, not from anything the client stored at login');
  ok(!/localStorage|sessionStorage/.test(who),
     'and it is never persisted -- a stored role is a role somebody can edit');
  const rep = grab('loadReports');
  // 403 is authorization. Signing the team out over one is the mistake
  // isAuthErr() was written to avoid.
  // The CODE line, not the first line mentioning 403 -- which is the comment
  // above it, and matching that made this check pass for any implementation.
  const on403 = rep.split('\n').filter(l => l.includes('r.status===403')).join(' ');
  ok(/r\.status===401/.test(rep) && on403 && !/sessionLost/.test(on403),
     'a 403 on the reports screen does not end the session');
  ok(/esc\(/.test(grab('reportCard')),
     'realtor-written notes and questions are escaped into the report card');
  ok(/AURA_ADMIN=false/.test(script.slice(script.indexOf('function signOut'), script.indexOf('function signOut') + 600))
     || /AURA_ADMIN=false/.test(grab('forgetData')),
     'signing out drops the admin flag -- shared phones exist');
  // The header is the whole Client Mode signal. Resetting the mode without
  // repainting leaves it saying Client while the mode is realtor -- the next
  // realtor on a shared phone turns the screen around believing it is safe.
  const forget = grab('forgetData');
  ok(/AURA_MODE='realtor'/.test(forget) && /auraPaintMode\(\)/.test(forget),
     'forgetData repaints the header it just reset');

  // Clearing AURA_TURNS does nothing to a request already in flight -- its
  // `done` handler pushed a Realtor answer into the cleared Client thread.
  const mode = grab('auraMode');
  ok(/auraStop\(\)/.test(mode),
     'flipping the mode aborts the stream -- a clear that leaves one running is not a clear');
  ok(mode.indexOf('auraStop()') > -1 && mode.indexOf('auraStop()') < mode.indexOf('AURA_TURNS=[]'),
     'the abort happens before the thread is cleared');

  // A mis-tap posts a verdict and settles the row to "Thanks" with no undo.
  const fbCss = readFileSync(DIR + 'Styles.html', 'utf8');
  const fbBlock = fbCss.slice(fbCss.indexOf('.aura-fb{'), fbCss.indexOf('.aura-note{'));
  ok(/\.aura-fb button\{[^}]*min-height:2\.75rem/.test(fbBlock),
     'feedback buttons are 44px tall');
  ok(/\.aura-fbv\{[^}]*min-width:2\.75rem/.test(fbBlock),
     'the icon-only thumbs are 44px wide as well as tall');
  ok(!/min-height:2\.25rem/.test(fbBlock),
     'no 36px control survives in the feedback row');
}

console.log(fail ? `\n${fail} CHECK(S) FAILED` : '\nALL CHECKS PASSED');
process.exit(fail ? 1 : 0);
