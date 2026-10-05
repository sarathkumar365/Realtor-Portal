/**
 * Realtor Portal — core: config, helpers, routing
 * Part of the Realtor Portal Apps Script project; all .gs files share one
 * global scope, so load order does not matter.
 */
/**
 * Realtor Portal — Mobile data API
 * ================================
 * Deploy: Web app > Execute as: Me > Access: Anyone (anonymous). The anonymous
 * access is deliberate — realtors may have no Google account and the login gate
 * itself must be publicly reachable. Access control is our own token layer:
 *
 *   Public (no token):  login, session   (they mint / refresh a token)
 *   Token required:     everything else  (see requireAuth_ / app())
 *
 * The signed token rides in `auth` on every call. The client's call() attaches
 * it automatically; the two credential-carrying actions (login, session) are
 * POST-only so a password or token never lands in a query string / the exec log.
 */

var SHEETS = {
  main:       '1DSaHocXEpfCBoJgE8JUxKsoqrR-H8D08kTLP3hI9-l0',
  deals:      '1FHi7550lIG4oQOWCt9HdLwLM84PxD_sgdEqeoiPsEWI',
  onboarding: '1DtIWnqR6LKN5AqlqwCNfoSk1FFsjEaPu'
};
var DEFAULT_SHEET = 'main';
var API_TOKEN = '';                       // app-level secret; '' = off

/* The admin username is not a secret; the passcode is. It lives in Script
   Properties (Project Settings -> Script Properties -> ADMIN_PASSCODE), never in
   source. If the property is unset, adminPass_() returns null and admin sign-in
   is disabled — fail closed rather than ship a hardcoded passcode. */
var ADMIN_ID = 'admin';
function adminPass_() {
  try { var v = String(PropertiesService.getScriptProperties().getProperty('ADMIN_PASSCODE') || '').trim(); return v || null; }
  catch (e) { return null; }
}

/* Signing key for session tokens. It MUST live in Script Properties
   (Project Settings -> Script Properties -> TOKEN_SECRET). There is deliberately
   NO in-source fallback: signing with a committed placeholder would let anyone
   holding the source forge a session token, including an admin one. When the
   property is missing we fail closed — issuing and verifying tokens throw, so
   nobody can sign in until a real key is set. Run checkSecret() for status. */
var __SECRET = null;
function tokenSecret_() {
  if (__SECRET) return __SECRET;
  var v = '';
  try { v = String(PropertiesService.getScriptProperties().getProperty('TOKEN_SECRET') || '').trim(); } catch (e) {}
  if (v) { __SECRET = v; return __SECRET; }
  throw new Error('TOKEN_SECRET is not set in Script Properties — refusing to sign or verify tokens. '
    + 'Set it in Project Settings -> Script Properties.');
}
/** Editor helper: is a real signing key live? Reports status, never the key. */
function checkSecret() {
  var v = '';
  try { v = String(PropertiesService.getScriptProperties().getProperty('TOKEN_SECRET') || '').trim(); } catch (e) {}
  if (!v) { Logger.log('TOKEN_SECRET: NOT SET — token issuance and verification are disabled (fail closed). Set it in Project Settings.'); return 'NOT SET'; }
  var fp = Utilities.base64EncodeWebSafe(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, v)).slice(0, 8);
  Logger.log('TOKEN_SECRET: set, ' + v.length + ' chars, fingerprint ' + fp
    + (v.length < 32 ? '  (32+ random chars recommended)' : ''));
  return 'SET';
}

/* How long a sign-in lasts. Sliding: every app launch mints a fresh token, so
   anyone who opens the app inside the window never has to sign in again. */
var SESSION_MS = 7 * 24 * 60 * 60 * 1000;

var LOGIN_HEADER_ROW = 2, LOGIN_FIRST_COL = 1, LOGIN_NUM_COLS = 5;   // A..E, row 2
var HEADER_ROW = 2, DATA_START = 3;       // city / school tabs: headers row 2, data row 3
var HEADER_ROWS = { 'main:School Rankings': 2 };

// City-tab column keywords (from the portal's FIELD_KEYS)
/* buildColMap_ binds each field to the FIRST header containing any of its
   keywords, so a keyword that is a substring of another header steals the wrong
   column. Two traps live here:
     - 'PRICE' would match ONTARIO's 'PRICE RANGE', so the keyword is the whole
       'STARTING PRICE'.
     - 'PROJECT ID' contains 'PROJECT', which is harmless only because the ID
       column is appended to the RIGHT of the project name. Added at column A it
       would make every project render as an id -- and would stop getCities_
       recognising the tab at all. */
var FIELD_KEYS = {
  project:['PROJECT'], builder:['BUILDER'], type:['TYPE'], occupancy:['OCCUPANCY','OCCUPAN'],
  broker:['BROKER'], drive:['UNBRANDED'], login:['LOGIN'], office:['OFFICE'], contact:['CONTACT'], fub:['FUB'],
  status:['STATUS'], live:['LIVE ON','ON WEBSITE'], website:['LIVE LINK','LINK'],
  /* Added for Aura Chat. Absent from most tabs today: Sudhanshu is filling them
     for the priority projects, starting with BRAMPTON. An unmapped column reads
     as empty, so a tab without them behaves exactly as before. */
  id:['PROJECT ID'], price:['STARTING PRICE'], maxprice:['MAXIMUM PRICE','MAX PRICE'],
  beds:['BEDROOM'], depositpct:['DEPOSIT %','DEPOSIT PERCENT'], depositsched:['DEPOSIT SCHEDULE'],
  incentives:['INCENTIVE'], lastupdated:['LAST UPDATED'], address:['ADDRESS'], sourceurl:['SOURCE URL']
};

var ALLOW = {
  main: [
    'School', 'School Rankings',
    'BUILDERS', 'Contractors', 'Resources', "FAQ's", 'Lawyers', 'CITIES', 'Events',
    'FocusProjects', 'Focus Dxb Projects', 'HotPriceSheet', 'HotDeals', 'RESALE',
    'PRECON', 'Precon Reserch - Prakash', 'Deposit Calculator', 'COMMERCIAL',
    'ONTARIO', 'AJAX', 'Aurora', 'BARRIE', 'BRAMPTON', 'BRANTFORD', 'BOWMANVILLE',
    'BURLINGTON', 'CALEDON', 'CALEDONIA', 'CAMBRIDGE', 'COURTICE', 'ETOBICOKE',
    'ERIN', 'GUELPH', 'KITCHENER', 'HAMILTON', 'KING CITY', 'LINDSAY', 'LONDON',
    'MILTON', 'MISSISSAUGA', 'MARKHAM', 'NEWMARKET', 'OAKVILLE', 'ORANGEVILLE',
    'OSHAWA', 'OTTAWA', 'PARIS', 'PICKERING', 'RICHMOND HILL', 'SCARBOROUGH',
    'STAYNER', 'STOUFFVILLE', 'WELLAND', 'VAUGHAN', 'WHITBY', 'WOODSTOCK',
    'CALGARY', 'DUBAI'
  ],
  deals: ['Active Listings', 'Websites'],
  onboarding: []
};

/* ================= core helpers ================= */
/* openById is a service round trip, and a cold Home used to make 43 of them for the
   same three spreadsheets. Apps Script globals live for exactly one execution, so
   memoizing here is per-request: no staleness window, no cross-user leakage. */
var __SS = {}, __SS_TABS = {};
function ssKey_(key) { return SHEETS[key] ? key : DEFAULT_SHEET; }
function ssFor_(key) { var k = ssKey_(key); return __SS[k] || (__SS[k] = SpreadsheetApp.openById(SHEETS[k])); }
/* Same story for getSheets(): half a dozen readers each listed every tab separately. */
function sheetsFor_(key) { var k = ssKey_(key); return __SS_TABS[k] || (__SS_TABS[k] = ssFor_(k).getSheets()); }
function json_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }
function isAllowed_(k, t) { return (ALLOW[k] || []).indexOf(t) !== -1; }
function allowedTabs_() { var o = {}; Object.keys(ALLOW).forEach(function (k) { o[k] = ALLOW[k].slice(); }); return o; }
function headerRowFor_(k, t, o) { if (o) return Math.max(1, parseInt(o, 10) || 1); return HEADER_ROWS[k + ':' + t] || 1; }
var __FRESH = false;

/* CacheService caps one value at 100KB. This used to mean anything bigger was dropped
   on the floor -- silently, with no log -- so the most expensive payloads in the app
   (the cross-city project index at 300KB+, the School Rankings tab at ~270KB) were
   never cached at all and were rebuilt from scratch on every single request.

   Oversized values are now split instead: key `k` holds a marker naming the part count
   and `k|0..k|n-1` hold the pieces, written in one putAll so the marker never lands
   without its parts. Values that fit are still stored whole, so the common case stays
   a single round trip. A missing part reads as a miss -- parts expire together, but a
   torn payload would be worse than a rebuild. */
/* Six hours -- the CacheService maximum -- not fifteen minutes. Home transitively
   needs the 60-tab search index, so whoever arrives after the cache lapses pays a
   ~60s rebuild that the client abandons long before it lands. At 900s that was
   every realtor, every morning, and again after any quiet quarter of an hour.
   Paired with warmCache() below, which rebuilds on a timer inside this window, a
   cold cache stops being something a person ever meets. Refresh still forces a
   rebuild for anyone who has just edited a sheet and wants it now. */
var CACHE_TTL = 21600;             // seconds a cached payload stays valid
/* Chunk size is in CHARACTERS while the service's cap is in BYTES, so this leaves room
   for multi-byte content rather than sizing right up to the limit. */
var CHUNK_CHARS = 45000;
var CHUNK_MAX = 300;               // refuse anything past ~13M chars rather than thrash
var CHUNK_TAG = '\u0000chunked:';  // JSON never starts with NUL, so this cannot collide

function cachePutStr_(k, s, ttl) {
  var c = CacheService.getScriptCache();
  ttl = ttl || CACHE_TTL;
  if (s.length <= CHUNK_CHARS) { c.put(k, s, ttl); return true; }
  var n = Math.ceil(s.length / CHUNK_CHARS);
  if (n > CHUNK_MAX) { Logger.log('cache: ' + k + ' too large to cache (' + s.length + ' chars)'); return false; }
  var map = {};
  for (var i = 0; i < n; i++) map[k + '|' + i] = s.substr(i * CHUNK_CHARS, CHUNK_CHARS);
  map[k] = CHUNK_TAG + n;
  c.putAll(map, ttl);
  return true;
}
function cacheGetStr_(k) {
  var c = CacheService.getScriptCache(), head = c.get(k);
  if (head == null) return null;
  if (head.lastIndexOf(CHUNK_TAG, 0) !== 0) return head;      // stored whole
  var n = Number(head.slice(CHUNK_TAG.length));
  if (!(n > 0)) return null;
  var keys = [];
  for (var i = 0; i < n; i++) keys.push(k + '|' + i);
  var got = c.getAll(keys), s = '';
  for (var j = 0; j < n; j++) { var part = got[k + '|' + j]; if (part == null) return null; s += part; }
  return s;
}

/* Warm a batch of keys in one round trip. The city index reads ~40 cached payloads in
   a loop, which was ~40 sequential CacheService.get calls; this collapses them into
   one getAll. Entries are consumed once (see cacheGet_) so nothing can go stale behind
   a write later in the same execution. Chunked values are skipped here and left to
   cacheGet_, which knows how to reassemble them. */
var __CMEMO = {};
function cachePrefetch_(keys) {
  if (__FRESH || !keys || !keys.length) return;
  try {
    var got = CacheService.getScriptCache().getAll(keys);
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i], v = got[k];
      if (v == null || v.lastIndexOf(CHUNK_TAG, 0) === 0) continue;
      try { __CMEMO[k] = JSON.parse(v); } catch (e) {}
    }
  } catch (e) {}
}
function cacheGet_(k) {
  if (__FRESH) return null;
  if (Object.prototype.hasOwnProperty.call(__CMEMO, k)) { var m = __CMEMO[k]; delete __CMEMO[k]; return m; }
  try { var h = cacheGetStr_(k); return h ? JSON.parse(h) : null; } catch (e) { return null; }
}
function cachePut_(k, v, ttl) { try { delete __CMEMO[k]; cachePutStr_(k, JSON.stringify(v), ttl); } catch (e) {} }
/* Read-through with a stampede guard. Without it, everyone who arrives during a
   long rebuild starts their own: five realtors opening at 9am on a cold cache
   meant five concurrent 60-second rebuilds, and ~90 of those exhaust a consumer
   account's whole daily runtime. The first caller builds; the rest wait briefly
   and take the fresh value. Whoever still misses builds anyway — a slow answer
   beats none, and correctness never depends on holding the lock. */
function cachedBuild_(key, build, ttl) {
  var hit = cacheGet_(key); if (hit) return hit;
  var lock = null;
  try { lock = LockService.getScriptLock(); if (!lock.tryLock(0)) lock = null; } catch (e) { lock = null; }
  if (!lock) {
    try { Utilities.sleep(1500); } catch (e) {}
    var second = cacheGet_(key); if (second) return second;
  }
  try {
    var built = build();
    /* An error payload must not be cached: a tab renamed for a minute during a
       rebuild would otherwise serve "tab missing" for the full TTL after the
       sheet is back. Let the next caller rebuild. */
    if (!(built && built.ok === false)) cachePut_(key, built, ttl);
    return built;
  } finally { if (lock) { try { lock.releaseLock(); } catch (e) {} } }
}
/* ---- scheduled warm-up ---------------------------------------------------
   The expensive build happens on the script's own time instead of in front of
   somebody waiting for Home. __FRESH is set deliberately: re-reading a cache
   that is about to expire would warm nothing, so this forces the rebuild and
   overwrites the entry with a full TTL ahead of it.

   Run installWarmTrigger() once from the editor to schedule it. Every four
   hours against a six-hour TTL leaves two hours of margin for a skipped or
   failed run, at roughly six minutes of runtime a day. */
function warmCache() {
  __FRESH = true;
  try { getHome_(); } catch (e) {}          // pulls the search index, focus and contacts
  try { getCities_(); } catch (e) {}
  try { getCityCounts_(); } catch (e) {}
  try { getTaxRates_(); } catch (e) {}       // Property Tax + the Expenses rate table
  __FRESH = false;
}
function installWarmTrigger() {
  var existing = ScriptApp.getProjectTriggers();
  for (var i = 0; i < existing.length; i++) {
    if (existing[i].getHandlerFunction() === 'warmCache') ScriptApp.deleteTrigger(existing[i]);
  }
  ScriptApp.newTrigger('warmCache').timeBased().everyHours(4).create();
  return 'warmCache scheduled every 4 hours';
}

/* The web app is anonymous, so `fresh` must not let a caller force unlimited full-sheet
   reads: at most one cache-busting rebuild per action per 30s. A user tapping Refresh
   still gets a rebuild; a loop cannot exhaust the script's quota. */
function freshAllowed_(action) {
  try {
    var c = CacheService.getScriptCache(), gk = 'freshgate_' + action;
    if (c.get(gk)) return false;
    c.put(gk, '1', 30);
    return true;
  } catch (e) { return false; }
}

/* One column's worth of a getter, for readers that need rich text or formulas from a
   single link column. getRichTextValues() is the slowest call the Sheets service
   offers -- it serializes per-cell formatting runs -- so pulling it over an entire
   sheet to read one column is the most expensive mistake a reader here can make.
   getDataRange() always starts at A1, so a display-values column index maps to sheet
   column index + 1. Returns [] for an absent column, which reads as "no link". */
function colRange_(sh, colIdx, nRows, kind) {
  if (!(colIdx >= 0) || !(nRows > 0)) return [];
  try {
    var rng = sh.getRange(1, colIdx + 1, nRows, 1);
    if (kind === 'rich') return rng.getRichTextValues();
    if (kind === 'formula') return rng.getFormulas();
    return rng.getValues();
  } catch (e) { return []; }
}

/* pull a URL from a cell: real hyperlink, run link, =HYPERLINK(), or bare URL */
function cellUrl_(rt, formula, text) {
  try {
    if (rt) {
      var u = rt.getLinkUrl(); if (u) return u;
      var runs = rt.getRuns ? rt.getRuns() : [];
      for (var i = 0; i < runs.length; i++) { var ru = runs[i].getLinkUrl(); if (ru) return ru; }
    }
  } catch (e) {}
  var m = String(formula || '').match(/HYPERLINK\s*\(\s*"([^"]+)"/i);
  if (m) return m[1];
  var t = String(text || '').trim();
  return /^https?:\/\//i.test(t) ? t : '';
}
function headerMap_(hdr, spec) {
  var m = {};
  for (var key in spec) {
    m[key] = -1; var keys = spec[key];
    for (var c = 0; c < hdr.length && m[key] < 0; c++) for (var k = 0; k < keys.length; k++) if (hdr[c] === keys[k]) { m[key] = c; break; }
    for (var c2 = 0; c2 < hdr.length && m[key] < 0; c2++) for (var k2 = 0; k2 < keys.length; k2++) if (hdr[c2].indexOf(keys[k2]) >= 0) { m[key] = c2; break; }
  }
  return m;
}
function catsFromType_(type) {
  var t = String(type || '').toLowerCase(), out = [];
  if (t.indexOf('town') >= 0) out.push('townhome');
  if (t.indexOf('detach') >= 0) out.push('detached');
  if (t.indexOf('semi') >= 0) out.push('semi');
  if (t.indexOf('condo') >= 0) out.push('condo');
  return out;
}
function findMainTab_(match) {
  var sheets = sheetsFor_('main'); match = String(match).toUpperCase();
  for (var i = 0; i < sheets.length; i++) if (sheets[i].getName().toUpperCase().replace(/\s+/g, '').indexOf(match) >= 0) return sheets[i];
  return null;
}
function dealsFind_(match) {
  var sheets = sheetsFor_('deals'); match = String(match).toUpperCase();
  for (var i = 0; i < sheets.length; i++) if (sheets[i].getName().trim().toUpperCase().indexOf(match) >= 0) return sheets[i];
  return null;
}

/* ================= routing ================= */
/* Stitches the HTML partials into App.html at render time (<?!= include('X') ?>). */
function include(name) { return HtmlService.createHtmlOutputFromFile(name).getContent(); }

function doGet(e) {
  var p = (e && e.parameter) || {};
  if (p.fresh && freshAllowed_(String(p.action || ''))) __FRESH = true;
  if (!p.action) {
    return HtmlService.createTemplateFromFile('App').evaluate()
      .setTitle('Aura Key')
      .addMetaTag('viewport', 'width=device-width, initial-scale=1, viewport-fit=cover')
      .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.DEFAULT);
  }
  if (API_TOKEN && p.token !== API_TOKEN) return json_({ error: 'unauthorized' });
  var a = p.action || '';

  // A password or a live token in a query string is written to the execution log
  // and every proxy on the way. These two are POST-only; doPost carries them.
  if (a === 'login' || a === 'session') return json_({ ok: false, error: 'use POST for ' + a });
  // Same rule, same reason, for every other action: a live token in a query string
  // lands in the execution log, browser history and the Referer of any outbound
  // link. The client only ever POSTs, so nothing legitimate is turned away.
  if (p.auth) return json_({ ok: false, error: 'use POST when sending auth' });

  // Everything goes through app()'s switch — ONE dispatch table, no drift, and
  // the same set of actions whether the caller used GET, POST or the HtmlService
  // bridge. (tabs/tab/bootcampreview used to be doGet-only; they live there now.)
  // Every action there requires a valid token except login/session.
  return json_(app(a, p));
}

function doPost(e) {
  var b = {};
  try { b = JSON.parse((e && e.postData && e.postData.contents) || '{}'); } catch (err) {}
  if (API_TOKEN && b.token !== API_TOKEN) return json_({ error: 'unauthorized' });
  // Same dispatch table as doGet -- no second switch to drift out of sync. POST
  // exists so a password never rides in a query string, where it would land in
  // the execution log: the native build posts login and session here.
  return json_(app(b.action || '', b));
}


/* =====================================================================
   PUBLIC DISPATCHER for the mobile app (google.script.run.app(action, p)).
   Mirrors the JSON routing but returns objects. Single public entry so the
   underscore helpers stay private.
   ===================================================================== */
/* One gate for the whole dispatcher. Every action needs a valid, still-active
   session token except login/session, which mint or refresh one. checkToken_
   also enforces the 7-day expiry, so a copied token dies with its window. */
var PUBLIC_ACTIONS = { login: 1, session: 1 };
function requireAuth_(p) {
  var t = checkToken_((p && p.auth) || '');
  if (!t) return null;
  if (!userStillActive_(t.user)) return null;
  return t;
}
function app(action, p) {
  p = p || {}; action = String(action || '');
  // hasOwnProperty, not a bare lookup: 'constructor', 'toString' and friends are
  // truthy on any plain object and would walk straight past the gate.
  if (!Object.prototype.hasOwnProperty.call(PUBLIC_ACTIONS, action)) {
    var tok = requireAuth_(p);
    if (!tok) return { ok: false, error: 'login required' };
    p.__tok = tok;   // handlers reuse the already-verified token instead of re-checking
  }
  if (p.fresh && !__FRESH && freshAllowed_(action)) __FRESH = true;
  switch (action) {
    case 'home':          return getHome_();
    case 'cities':        return getCities_();
    case 'citycounts':    return getCityCounts_();
    case 'city':          return getProjects_(p.name);
    case 'focus':         return getFocus_();
    case 'listings':      return getListings_();
    case 'builders':      return getBuilders_(p.__tok && p.__tok.role === 'admin');
    case 'contractors':   return getContractors_();
    case 'contacts':      return getContacts_();
    case 'resources':     return getResources_();
    case 'websites':      return getWebsites_();
    case 'faqs':          return getFaqs_();
    case 'vacations':     return getVacations_();
    case 'callnight':     return getCallNight_();
    case 'leaderboard':   return getLeaderboard_(p.period);
    case 'meetings':      return getMeetingsLeaderboard_(p.period);
    case 'schools':
    case 'getRankings':
    case 'getSchools':    return rankingsSlim_();
    case 'schoolfinder':  return getSchoolFinder_();
    // Stripped at the boundary rather than at each of the six return points inside.
    case 'basement':      return (p.__tok && p.__tok.role === 'admin')
                            ? getBasement_(p.addr || p.address)
                            : stripDbg_(getBasement_(p.addr || p.address));
    case 'basementcoverage': return getBasementCoverage_();
    case 'ltb':           return getLTB_(p.q || p.query, p.offset);
    case 'crime':         return getCrimeCity_(p.slug || p.city);
    case 'crimecities':   return getCrimeCities_();
    case 'taxrates':      return getTaxRates_();
    case 'fsboards':      return { ok: true, boards: fsBoards_() };
    case 'fssuggest':     return { ok: true, items: fsSuggest_(p.board, p.q || p.text) };
    case 'fslookup':      return fsLookup_(p.board, p.addr || p.address, p.num || p.houseNumber);
    case 'fsschools':     return fsSchools_(p.board, p.id || p.addressId, p.label || p.addressLabel, p.num || p.houseNumber);
    case 'login':         return handleLogin_(p);
    case 'session':       return handleSession_(p);
    /* Aura Chat's only read. Token-gated like everything else, so the AI
       service sees exactly what the realtor whose token it forwards would. */
    case 'aiindex':       return getAiIndex_();
    case 'tabs':          return { sheets: allowedTabs_() };
    case 'tab':           return readTab_(p.name || '', p.sheet || '', p.headerRow || '');
    case 'mydeals':       return getMyDealsPayload_(p);
    case 'bootcamp':      return getBootcampPayload_(p);
    case 'bootcampreview':return bootcampReview_(p);                  // admin token only (checked inside)
    default:              return { ok: false, error: 'unknown action: ' + action };
  }
}
/** Run once to authorize external requests (basement/crime/ltb/schools). */
function GRANT_URLFETCH_APP() { var r = UrlFetchApp.fetch('https://www.arcgis.com/sharing/rest/content/items/7d9df6528d474b43b6771cb7feefc35e?f=json', { muteHttpExceptions: true }); return 'Authorized. HTTP ' + r.getResponseCode(); }
