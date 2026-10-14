/**
 * Realtor Portal — sheet readers: projects, directory, login
 * Part of the Realtor Portal Apps Script project; all .gs files share one
 * global scope, so load order does not matter.
 */
/* ================= generic tab reader ================= */
function readTab_(tabName, sheetKey, headerRowOverride) {
  tabName = String(tabName || '').trim();
  if (!tabName) return { error: 'no tab name given' };
  var order = sheetKey && SHEETS[sheetKey] ? [sheetKey]
    : [DEFAULT_SHEET].concat(Object.keys(SHEETS).filter(function (k) { return k !== DEFAULT_SHEET; }));
  var sh = null, foundIn = '';
  for (var i = 0; i < order.length; i++) {
    if (!isAllowed_(order[i], tabName)) continue;
    var c = ssFor_(order[i]).getSheetByName(tabName);
    if (c) { sh = c; foundIn = order[i]; break; }
  }
  if (!sh) return { error: 'not available' };
  var hr = headerRowFor_(foundIn, tabName, headerRowOverride);
  var ck = 'tab_' + foundIn + '_' + tabName + '_h' + hr, hit = cacheGet_(ck);
  if (hit) { hit.cached = true; return hit; }
  var values = sh.getDataRange().getDisplayValues();
  if (values.length < hr) return { sheet: foundIn, tab: tabName, count: 0, rows: [] };
  var headers = values[hr - 1].map(function (h) { return String(h).trim(); });
  var rows = values.slice(hr).filter(function (r) { return r.join('').trim() !== ''; })
    .map(function (r) { var o = {}; headers.forEach(function (h, i) { if (h) o[h] = r[i]; }); return o; });
  var out = { sheet: foundIn, tab: tabName, updated: new Date().toISOString(), count: rows.length, rows: rows };
  cachePut_(ck, out); return out;
}

/* ================= smart table reader (header auto-detect) ================= */
function readTableSmart_(sh) {
  if (!sh || sh.getLastRow() < 2) return [];
  var vals = sh.getDataRange().getDisplayValues();
  function norm(h) { return String(h || '').trim().toLowerCase().replace(/\s+/g, '_'); }
  var hdr = vals[0].map(norm);
  var rows = [];
  for (var r = 1; r < vals.length; r++) {
    var o = { _row: r + 1 };
    for (var c = 0; c < hdr.length; c++) { if (hdr[c] && o[hdr[c]] === undefined) o[hdr[c]] = String(vals[r][c] || '').trim(); }
    rows.push(o);
  }
  return rows;
}

/* ================= city projects (getProjects) ================= */
/* Built once per execution. getSearchIndex_ resolves ~60 cities in a loop, and
   rescanning every sheet name each time cost thousands of getName() calls for an
   answer that cannot change mid-request. */
var __CITY_TABS = null;
function resolveCity_(city) {
  var want = String(city || '').trim().toUpperCase();
  if (!__CITY_TABS) {
    __CITY_TABS = {};
    var sheets = sheetsFor_('main');
    for (var i = 0; i < sheets.length; i++) __CITY_TABS[sheets[i].getName().trim().toUpperCase()] = sheets[i];
  }
  return Object.prototype.hasOwnProperty.call(__CITY_TABS, want) ? __CITY_TABS[want] : null;
}
function buildColMap_(sh, lastCol) {
  var headers = sh.getRange(HEADER_ROW, 1, 1, lastCol || sh.getLastColumn()).getDisplayValues()[0], map = {};
  for (var f in FIELD_KEYS) {
    var keys = FIELD_KEYS[f];
    for (var c = 0; c < headers.length; c++) {
      var h = String(headers[c] || '').trim().toUpperCase(), hit = false;
      for (var k = 0; k < keys.length; k++) if (h.indexOf(keys[k]) >= 0) { hit = true; break; }
      if (hit) { map[f] = c + 1; break; }
    }
  }
  return map;
}
function getProjects_(city) {
  city = String(city || '').trim();
  if (!city) return { error: 'no city name' };
  var key = 'proj_' + city.toUpperCase(), hit = cacheGet_(key);
  if (hit) { hit.cached = true; return hit; }
  var sh = resolveCity_(city);
  if (!sh) return { error: 'city tab "' + city + '" not found' };
  var lastRow = sh.getLastRow();
  if (lastRow < DATA_START) return { city: city, count: 0, rows: [] };
  var lastCol = sh.getLastColumn(), map = buildColMap_(sh, lastCol), numRows = lastRow - DATA_START + 1;
  var disp = sh.getRange(DATA_START, 1, numRows, lastCol).getDisplayValues();
  var bR = null, bF = null, dR = null, dF = null, wR = null, wF = null;
  if (map.broker)  { var b = sh.getRange(DATA_START, map.broker, numRows, 1); bR = b.getRichTextValues(); bF = b.getFormulas(); }
  if (map.drive)   { var d = sh.getRange(DATA_START, map.drive, numRows, 1); dR = d.getRichTextValues(); dF = d.getFormulas(); }
  if (map.website) { var w = sh.getRange(DATA_START, map.website, numRows, 1); wR = w.getRichTextValues(); wF = w.getFormulas(); }
  function txt(row, f) { var idx = map[f]; return idx ? String(row[idx - 1] || '').trim() : ''; }
  var out = [];
  for (var r = 0; r < numRows; r++) {
    var d2 = disp[r], project = txt(d2, 'project'), builder = txt(d2, 'builder');
    if (!project && !builder) continue;
    var type = txt(d2, 'type'), status = txt(d2, 'status');
    out.push({
      _row: DATA_START + r, project: project, builder: builder, type: type, cats: catsFromType_(type),
      occupancy: txt(d2, 'occupancy'), login: txt(d2, 'login'), office: txt(d2, 'office'),
      contact: txt(d2, 'contact'), fub: txt(d2, 'fub'), status: status, live: txt(d2, 'live'),
      hidden: /not\s*avail|unavailable/i.test(String(status).replace(/[-_]/g, ' ')),
      /* Commercial columns, for Aura Chat. Empty on any tab that does not carry
         them yet, which is every tab but BRAMPTON at the time of writing. The
         portal's own screens ignore fields they do not read. */
      id: txt(d2, 'id'), price: txt(d2, 'price'), maxprice: txt(d2, 'maxprice'),
      beds: txt(d2, 'beds'), depositpct: txt(d2, 'depositpct'), depositsched: txt(d2, 'depositsched'),
      incentives: txt(d2, 'incentives'), lastupdated: txt(d2, 'lastupdated'),
      address: txt(d2, 'address'), sourceurl: txt(d2, 'sourceurl'),
      broker_url:  map.broker  ? cellUrl_(bR[r][0], bF[r][0], d2[map.broker - 1])  : '',
      drive_url:   map.drive   ? cellUrl_(dR[r][0], dF[r][0], d2[map.drive - 1])   : '',
      website_url: map.website ? cellUrl_(wR[r][0], wF[r][0], d2[map.website - 1]) : ''
    });
  }
  var res = { city: city.toUpperCase(), updated: new Date().toISOString(), count: out.length, rows: out };
  cachePut_(key, res); return res;
}

/* ================= builders ================= */
/* The LOGIN/PASSWORD columns are credentials to other companies' portals. They
   are admin-only, and the two roles get separate cache keys so a payload built
   for an admin can never be served to — or cached on the phone of — a realtor. */
function getBuilders_(isAdmin) {
  var ck = 'builders_api' + (isAdmin ? '_admin' : '');
  var hit = cacheGet_(ck); if (hit) { hit.cached = true; return hit; }
  var sh = findMainTab_('BUILDER');
  if (!sh) return { count: 0, rows: [] };
  var lastRow = sh.getLastRow(), lastCol = sh.getLastColumn();
  if (lastRow < 2) return { count: 0, rows: [] };
  var hdr = sh.getRange(1, 1, 1, lastCol).getDisplayValues()[0].map(function (h) { return String(h || '').trim().toUpperCase(); });
  function colx(incl, excl) {
    for (var c = 0; c < hdr.length; c++) {
      var h = hdr[c], ok = false, k;
      for (k = 0; k < incl.length; k++) if (h.indexOf(incl[k]) >= 0) { ok = true; break; }
      if (ok && excl) for (k = 0; k < excl.length; k++) if (h.indexOf(excl[k]) >= 0) { ok = false; break; }
      if (ok) return c;
    }
    return -1;
  }
  var iName = colx(['BUILDER NAME']); if (iName < 0) iName = colx(['NAME'], ['PROJECT', 'REP']);
  var iProject = colx(['PROJECT']), iRep = colx(['REP', 'CONTACT'], ['PHONE', 'NUMBER']);
  var iPhone = colx(['PHONE', 'NUMBER', 'MOBILE']), iEmail = colx(['EMAIL']);
  var iBroker = colx(['BROKER', 'PORTAL']), iLogin = colx(['LOGIN', 'USER']), iPass = colx(['PASSWORD', 'PASS']), iNotes = colx(['NOTE']);
  var numRows = lastRow - 1, disp = sh.getRange(2, 1, numRows, lastCol).getDisplayValues();
  var bR = null, bF = null;
  if (iBroker >= 0) { var b = sh.getRange(2, iBroker + 1, numRows, 1); bR = b.getRichTextValues(); bF = b.getFormulas(); }
  function g(row, i) { return i >= 0 ? String(row[i] || '').trim() : ''; }
  var out = [];
  for (var r = 0; r < numRows; r++) {
    var row = disp[r], name = g(row, iName), project = g(row, iProject), rep = g(row, iRep), phone = g(row, iPhone);
    if (!name && !rep && !project && !phone) continue;
    out.push({ _row: r + 2, name: name, project: project, rep: rep, phone: phone, email: g(row, iEmail),
      login: isAdmin ? g(row, iLogin) : '', password: isAdmin ? g(row, iPass) : '', notes: g(row, iNotes),
      broker_url: iBroker >= 0 ? cellUrl_(bR[r][0], bF[r][0], row[iBroker]) : '' });
  }
  var res = { updated: new Date().toISOString(), count: out.length, rows: out };
  cachePut_(ck, res); return res;
}

/* ================= contractors ================= */
function getContractors_() {
  var hit = cacheGet_('contractors_api'); if (hit) { hit.cached = true; return hit; }
  var rows = readTableSmart_(findMainTab_('CONTRACTOR')), out = [];
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i]; if (!r.name && !r.category) continue;
    out.push({ _row: r._row, category: (r.category || '').trim(), name: (r.company_name || r.name || '').trim(),
      contact: (r.contact_person || r.contact || '').trim(), phone: (r.phone || '').trim(),
      email: (r.email || '').trim(), area: (r.address || r.area || '').trim(),
      website: (r.website || '').trim(), notes: (r.notes || '').trim() });
  }
  var res = { updated: new Date().toISOString(), count: out.length, rows: out };
  cachePut_('contractors_api', res); return res;
}

/* ================= contacts (Home) ================= */
function getContacts_() {
  var hit = cacheGet_('contacts_api'); if (hit) { hit.cached = true; return hit; }
  var sheets = sheetsFor_('main'), sh = null;
  for (var i = 0; i < sheets.length && !sh; i++) { var n = sheets[i].getName().trim().toUpperCase(); if (n === 'CONTACTS' || n === 'CONTACT' || n === 'HOME') sh = sheets[i]; }
  for (var j = 0; j < sheets.length && !sh; j++) { var n2 = sheets[j].getName().toUpperCase(); if (n2.indexOf('CONTACT') >= 0 || n2.indexOf('HOME') >= 0) sh = sheets[j]; }
  if (!sh || sh.getLastRow() < 2) return { count: 0, rows: [] };
  var vals = sh.getDataRange().getDisplayValues();
  var hdr = vals[0].map(function (h) { return String(h || '').trim().toUpperCase(); });
  function col(keys) { for (var c = 0; c < hdr.length; c++) for (var k = 0; k < keys.length; k++) if (hdr[c].indexOf(keys[k]) >= 0) return c; return -1; }
  var m = { category: col(['CATEGORY']), title: col(['TITLE']), name: col(['NAME']), company: col(['COMPANY', 'BANK']),
    direct: col(['DIRECT']), office: col(['OFFICE']), email: col(['EMAIL']), address: col(['ADDRESS']), tag: col(['TAG']), notes: col(['NOTE']) };
  function g(row, k) { return m[k] >= 0 ? String(row[m[k]] || '').trim() : ''; }
  var out = [];
  for (var r = 1; r < vals.length; r++) {
    var cat = g(vals[r], 'category'), name = g(vals[r], 'name');
    if (!cat && !name) continue;
    out.push({ category: cat, title: g(vals[r], 'title'), name: name, company: g(vals[r], 'company'),
      direct: g(vals[r], 'direct'), office: g(vals[r], 'office'), email: g(vals[r], 'email'),
      address: g(vals[r], 'address'), tag: g(vals[r], 'tag'), notes: g(vals[r], 'notes') });
  }
  var res = { updated: new Date().toISOString(), count: out.length, rows: out };
  cachePut_('contacts_api', res); return res;
}

/* ================= resources (grouped) ================= */
function getResources_() {
  var hit = cacheGet_('resources_api'); if (hit) return hit;
  var sheets = sheetsFor_('main'), sh = null;
  for (var i = 0; i < sheets.length; i++) if (sheets[i].getName().toUpperCase().indexOf('RESOURCE') >= 0) { sh = sheets[i]; break; }
  if (!sh || sh.getLastRow() < 2) return { categories: [] };
  var vals = sh.getDataRange().getDisplayValues();
  var hdr = vals[0].map(function (h) { return String(h || '').trim().toUpperCase(); });
  function col(keys) { for (var c = 0; c < hdr.length; c++) for (var k = 0; k < keys.length; k++) if (hdr[c].indexOf(keys[k]) >= 0) return c; return -1; }
  var m = { category: col(['CATEGORY']), label: col(['LABEL']), desc: col(['DESCRIPTION', 'DESC']), type: col(['TYPE']), url: col(['URL', 'LINK']), notes: col(['NOTE']) };
  function g(row, k) { return m[k] >= 0 ? String(row[m[k]] || '').trim() : ''; }
  var cats = [], catIndex = {};
  for (var r = 1; r < vals.length; r++) {
    var category = g(vals[r], 'category'), label = g(vals[r], 'label'), desc = g(vals[r], 'desc'), type = g(vals[r], 'type'), url = g(vals[r], 'url'), notes = g(vals[r], 'notes');
    if (!category && !label && !url && !notes) continue;
    if (!category) category = 'Resources';
    if (catIndex[category] == null) { catIndex[category] = cats.length; cats.push({ category: category, _byLabel: {}, items: [] }); }
    var cat = cats[catIndex[category]], k2 = label || url || type || ('row' + r);
    if (cat._byLabel[k2] == null) { cat._byLabel[k2] = cat.items.length; cat.items.push({ label: label, desc: desc, type: type, url: url, notes: notes, subs: [] }); }
    else { var it = cat.items[cat._byLabel[k2]]; if (!it.subs.length) { it.subs.push({ name: it.type || it.label, url: it.url, notes: it.notes }); it.url = ''; it.notes = ''; } it.subs.push({ name: type || label, url: url, notes: notes }); }
  }
  cats.forEach(function (c) { delete c._byLabel; });
  var res = { updated: new Date().toISOString(), categories: cats };
  cachePut_('resources_api', res); return res;
}

/* ================= listings + websites (deals sheet) ================= */
function getListings_() {
  var hit = cacheGet_('listings_api'); if (hit) { hit.cached = true; return hit; }
  var sh = dealsFind_('ACTIVE LISTING') || dealsFind_('LISTING');
  if (!sh || sh.getLastRow() < 2) return { count: 0, rows: [] };
  var rng = sh.getDataRange(), vals = rng.getDisplayValues(), rts = [], fmls = [];
  try { rts = rng.getRichTextValues(); } catch (e) {}
  try { fmls = rng.getFormulas(); } catch (e) {}
  var hdr = vals[0].map(function (h) { return String(h || '').trim().toUpperCase(); });
  var m = headerMap_(hdr, { section:['SECTION'], property:['PROPERTY NAME','PROPERTY'], price:['PRICE'],
    mls:['MLS NO','MLS'], agents:['LISTING AGENTS','AGENTS'], lbx:['LBX CODE'], instructions:['LBX INSTRUCTIONS'],
    showing:['SHOWING TIME'], notice:['NOTICE PERIOD'], other:['LBX OTHER'], status:['STATUS'], link:['LINK','URL'] });
  function g(row, k) { return m[k] >= 0 ? String(row[m[k]] || '').trim() : ''; }
  function linkAt(r, k) { if (m[k] < 0) return ''; var c = m[k]; return cellUrl_(rts[r] ? rts[r][c] : null, fmls[r] ? fmls[r][c] : '', vals[r][c]); }
  var out = [];
  for (var r = 1; r < vals.length; r++) {
    var prop = g(vals[r], 'property'); if (!prop) continue;
    var section = g(vals[r], 'section') || 'Other';
    var link = linkAt(r, 'link') || linkAt(r, 'property') || linkAt(r, 'mls');
    var mlsText = g(vals[r], 'mls'); if (link && /^(link|view|open)$/i.test(mlsText)) mlsText = '';
    // Only the fields the portal actually shows. commission / staging / invoice / post are intentionally omitted.
    out.push({ section: section, exclusive: /exclusive/i.test(section), link: link, property: prop, price: g(vals[r], 'price'),
      mls: mlsText, agents: g(vals[r], 'agents'), lbx: g(vals[r], 'lbx'), instructions: g(vals[r], 'instructions'),
      showing: g(vals[r], 'showing'), notice: g(vals[r], 'notice'), other: g(vals[r], 'other'), status: g(vals[r], 'status') });
  }
  var res = { updated: new Date().toISOString(), count: out.length, rows: out };
  cachePut_('listings_api', res); return res;
}
function getWebsites_() {
  var hit = cacheGet_('websites_api'); if (hit) return hit;
  var sh = dealsFind_('WEBSITE');
  if (!sh || sh.getLastRow() < 2) return { sections: [] };
  var vals = sh.getDataRange().getDisplayValues();
  var hdr = vals[0].map(function (h) { return String(h || '').trim().toUpperCase(); });
  var m = headerMap_(hdr, { section:['SECTION'], name:['NAME'], url:['URL','LINK'] });
  function g(row, k) { return m[k] >= 0 ? String(row[m[k]] || '').trim() : ''; }
  var groups = {}, order = [];
  for (var r = 1; r < vals.length; r++) {
    var name = g(vals[r], 'name'), url = g(vals[r], 'url'); if (!name && !url) continue;
    var sec = g(vals[r], 'section') || 'Other';
    if (groups[sec] == null) { groups[sec] = { section: sec, items: [] }; order.push(sec); }
    groups[sec].items.push({ name: name, url: url });
  }
  var res = { updated: new Date().toISOString(), sections: order.map(function (k) { return groups[k]; }) };
  cachePut_('websites_api', res); return res;
}

/* ================= cities (tab names that look like project tabs) ================= */
function getCities_() {
  var hit = cacheGet_('cities_api'); if (hit) return hit;
  var sheets = sheetsFor_('main'), cities = [], partial = false;
  for (var i = 0; i < sheets.length; i++) {
    var sh = sheets[i];
    /* This runs over every tab in the spreadsheet just to read two header cells, so it
       used to cost three round trips per tab (getLastRow + getLastColumn + getValues).
       Reading the two cells directly costs one. */
    var ab;
    try { ab = sh.getRange(HEADER_ROW, 1, 1, 2).getValues()[0]; }
    catch (e) {
      /* A tab too small to hold those cells is a genuine skip -- that is what the
         dimension checks used to buy. Anything else is a transient service error, and
         Sheets throws plenty of those in a loop this long. Treating the two alike
         would drop a real city and then cache the gap for an hour, so confirm which
         one this is (only on the rare error path) and refuse to cache if the list
         might be short. */
      var small = false;
      try { small = (sh.getLastRow() < HEADER_ROW || sh.getLastColumn() < 2); } catch (e2) {}
      if (!small) partial = true;
      continue;
    }
    var a = String(ab[0] || '').trim().toUpperCase(), b = String(ab[1] || '').trim().toUpperCase();
    if (a.indexOf('PROJECT') >= 0 && b.indexOf('BUILDER') >= 0) cities.push(sh.getName().trim());
  }
  cities.sort();
  var res = { updated: new Date().toISOString(), count: cities.length, cities: cities };
  /* Tab names change far less often than their contents, and rediscovering them is the
     most expensive part of a cold index build. An added city shows up within the hour,
     or immediately via Refresh, which bypasses the cache. A list built while a tab was
     failing is served but never cached, so the gap lasts one request, not an hour. */
  if (!partial) cachePut_('cities_api', res, 3600);
  return res;
}

/* ================= LOGIN =================
   Credentials live in their own spreadsheet, separate from the team's main sheet,
   so realtor passwords are not visible to everyone the main sheet is shared with.
   Its ID is the LOGIN_SHEET_ID Script Property (Project Settings -> Script
   Properties). If unset, we fall back to the main sheet — so an existing LOGIN tab
   there keeps working with no lockout until the ID is set. */
function loginSS_() {
  var id = '';
  try { id = String(PropertiesService.getScriptProperties().getProperty('LOGIN_SHEET_ID') || '').trim(); } catch (e) {}
  if (!id) return ssFor_('main');   // unset -> credentials still live in the main sheet
  // Set-but-unreachable is NOT the same as unset. Silently falling back to the
  // shared main sheet would defeat the split (and hash passwords into the wrong
  // sheet), so a bad ID or a permissions gap fails loud instead.
  try { return SpreadsheetApp.openById(id); }
  catch (e) { throw new Error('LOGIN_SHEET_ID is set but the sheet could not be opened — check the ID and that the deploying account has access: ' + ((e && e.message) || e)); }
}
/* Shared header canonicalization for the LOGIN tab, so the row reader and the
   password-cell locator resolve columns the same way (matched by name, not order). */
function loginNorm_(h) { return String(h || '').trim().toLowerCase().replace(/\s+/g, '_'); }
function loginCanon_(h) {
  if (/^(username|user_?name|user_?id|userid|login|user)$/.test(h)) return 'username';
  if (/^(password|pass|pwd|passcode)$/.test(h)) return 'password';
  if (/^(email|e_?mail|email_?id)$/.test(h)) return 'email';
  if (/^(name|full_?name|realtor_?name|agent_?name|realtor|agent)$/.test(h)) return 'name';
  return h;
}
function loginTab_() {
  var sheets = loginSS_().getSheets();
  for (var i = 0; i < sheets.length; i++) { var n = sheets[i].getName().toUpperCase().replace(/\s+/g, ''); if (n.indexOf('LOGIN') >= 0 || n.indexOf('REALTOR') >= 0) return sheets[i]; }
  return null;
}
function loginRows_() {
  var sh = loginTab_(); if (!sh || sh.getLastRow() < LOGIN_HEADER_ROW) return [];
  var last = sh.getLastRow();
  // Read only the columns that exist — the sheet may have exactly the four it needs
  // (username, password, name, email); columns are then matched by header, not position.
  var ncols = Math.min(LOGIN_NUM_COLS, sh.getLastColumn());
  var vals = sh.getRange(LOGIN_HEADER_ROW, LOGIN_FIRST_COL, last - LOGIN_HEADER_ROW + 1, ncols).getDisplayValues();
  var keys = vals[0].map(loginNorm_).map(loginCanon_), out = [];
  for (var r = 1; r < vals.length; r++) { var o = {}; keys.forEach(function (k, i) { o[k] = vals[r][i]; }); if (o.username) out.push(o); }
  return out;
}
/* Failed guesses cost progressively more time. The first slip is free so a typo
   is never punished; a script grinding through a password list stalls out. Per
   username, and no lockout -- a lockout would let anyone freeze a colleague. */
var LOGIN_BACKOFF_MS = [0, 1000, 2000, 4000, 8000];
var LOGIN_FAIL_ALL = 'lf_all';
/* Failed attempts across every account in the 15-minute window before sign-in
   closes for everyone. Well clear of a whole team fat-fingering; nowhere near
   enough for a spray. */
var LOGIN_GLOBAL_MAX = 60;
function loginFailKey_(user) { return 'lf_' + String(user || '').trim().toLowerCase(); }
function loginDelay_(user) {
  try {
    var n = Number(CacheService.getScriptCache().get(loginFailKey_(user)) || 0);
    return LOGIN_BACKOFF_MS[Math.min(n, LOGIN_BACKOFF_MS.length - 1)];
  } catch (e) { return 0; }
}
/* Apps Script serves requests concurrently, so an unlocked read-modify-write lets
   30 simultaneous guesses all read the same count and all write n+1 — the counter
   advances by one and the backoff never engages. The lock makes each attempt
   actually count. A global tally runs alongside, because a per-user count does
   nothing against someone spraying one guess across every username. */
function loginFailed_(user) {
  var lock = null;
  try { lock = LockService.getScriptLock(); if (!lock.tryLock(3000)) lock = null; } catch (e) { lock = null; }
  try {
    var c = CacheService.getScriptCache(), k = loginFailKey_(user);
    c.put(k, String(Number(c.get(k) || 0) + 1), 900);   // 15 quiet minutes clears the count
    c.put(LOGIN_FAIL_ALL, String(Number(c.get(LOGIN_FAIL_ALL) || 0) + 1), 900);
  } catch (e) {}
  finally { if (lock) { try { lock.releaseLock(); } catch (e) {} } }
}
function loginLockedOut_() {
  try { return Number(CacheService.getScriptCache().get(LOGIN_FAIL_ALL) || 0) >= LOGIN_GLOBAL_MAX; } catch (e) { return false; }
}
function loginOk_(user) { try { CacheService.getScriptCache().remove(loginFailKey_(user)); } catch (e) {} }

/* ---- password storage ----
   Sheet passwords are stored as a salted SHA-256 hash, prefixed 'sha256$'. The
   username is the salt (so no extra sheet column) and a project-wide PASSWORD_PEPPER
   from Script Properties is mixed in, so a leaked sheet alone can't be reversed.
   Legacy rows are still plaintext; they migrate to a hash on first sign-in. */
var PW_SCHEME = 'sha256$';
function pepper_() {
  var v = '';
  try { v = String(PropertiesService.getScriptProperties().getProperty('PASSWORD_PEPPER') || '').trim(); } catch (e) {}
  if (!v) throw new Error('PASSWORD_PEPPER is not set in Script Properties — refusing to hash or verify passwords.');
  return v;
}
function hashPw_(username, pass) {
  var raw = pepper_() + '|' + String(username || '').trim().toLowerCase() + '|' + String(pass || '');
  return PW_SCHEME + Utilities.base64EncodeWebSafe(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, raw));
}
function pwIsHashed_(stored) { return String(stored || '').indexOf(PW_SCHEME) === 0; }
function pwMatches_(username, pass, stored) {
  stored = String(stored || '');
  if (pwIsHashed_(stored)) return hashPw_(username, pass) === stored;
  return stored === pass;   // legacy plaintext — migrated to a hash on success
}
/* Find the exact LOGIN cell holding this user's password, so a migrated hash
   can be written back in place. Mirrors loginRows_' header canonicalization. */
function pwCell_(sh, username) {
  if (!sh || sh.getLastRow() < LOGIN_HEADER_ROW) return null;
  var last = sh.getLastRow();
  var ncols = Math.min(LOGIN_NUM_COLS, sh.getLastColumn());
  var vals = sh.getRange(LOGIN_HEADER_ROW, LOGIN_FIRST_COL, last - LOGIN_HEADER_ROW + 1, ncols).getDisplayValues();
  var keys = vals[0].map(loginNorm_).map(loginCanon_);
  var userIdx = keys.indexOf('username'), passIdx = keys.indexOf('password');
  if (userIdx < 0 || passIdx < 0) return null;
  var want = String(username || '').trim().toLowerCase();
  for (var r = 1; r < vals.length; r++) {
    if (String(vals[r][userIdx] || '').trim().toLowerCase() === want) {
      return { row: LOGIN_HEADER_ROW + r, col: LOGIN_FIRST_COL + passIdx };
    }
  }
  return null;
}
/* Lazy migration: replace a plaintext password cell with its hash. The cell is
   located INSIDE the lock (re-read after acquiring it), so a concurrent row
   insert/delete can't leave us writing to a stale row. Wrapped so any failure
   (locked sheet, missing pepper) can never block an already-valid login. */
function migratePw_(username, pass) {
  try {
    var hashed = hashPw_(username, pass), sh = loginTab_();
    if (!sh) return;
    var lock = LockService.getScriptLock();
    try { lock.waitLock(5000); } catch (e) { return; }
    try {
      var loc = pwCell_(sh, username);
      if (loc) sh.getRange(loc.row, loc.col).setValue(hashed);
    } finally { lock.releaseLock(); }
  } catch (e) { /* migration is best-effort; a valid sign-in must still succeed */ }
}

function handleLogin_(p) {
  var user = String(p.user || p.id || p.username || '').trim(), pass = String(p.pass || p.password || '');
  if (!user || !pass) return { ok: false, error: 'missing id or password' };
  if (loginLockedOut_()) return { ok: false, error: 'too many attempts — try again in a few minutes' };
  // Charged before the comparison, so the wait cannot be read as a hit or a miss.
  var wait = loginDelay_(user); if (wait) Utilities.sleep(wait);
  // IDs are matched case-insensitively, as usernames normally are. Passwords are not.
  var ap = adminPass_();
  if (ap && user.toLowerCase() === ADMIN_ID && pass === ap) { loginOk_(user); return { ok: true, admin: true, name: 'Admin', role: 'admin', token: makeToken_('admin', 'admin') }; }
  var rows = loginRows_();
  for (var i = 0; i < rows.length; i++) {
    var u = String(rows[i].username || '').trim(), stored = String(rows[i].password || '');
    if (u && u.toLowerCase() === user.toLowerCase() && pwMatches_(u, pass, stored)) {
      if (!pwIsHashed_(stored)) migratePw_(u, pass);   // legacy plaintext -> hash on first sign-in
      loginOk_(user);
      return { ok: true, name: rows[i].name || u, email: rows[i].email || '', role: 'realtor', token: makeToken_(u, 'realtor') };
    }
  }
  loginFailed_(user);
  return { ok: false, error: 'invalid id or password' };
}

/* Is this token still backed by a live account? Delete someone's LOGIN row and
   they lose access within the cache window below -- without it, a signed token
   outlives the account it was issued to. Only usernames are cached, never the
   passwords beside them. The built-in admin login is not a sheet row. */
function activeUsers_() {
  var c = null, hit = null;
  try { c = CacheService.getScriptCache(); hit = c.get('active_users'); } catch (e) {}
  if (hit) { try { return JSON.parse(hit); } catch (e) {} }
  var rows = loginRows_(), out = [];
  for (var i = 0; i < rows.length; i++) {
    var u = String(rows[i].username || '').trim().toLowerCase();
    if (u) out.push(u);
  }
  if (c) { try { c.put('active_users', JSON.stringify(out), 300); } catch (e) {} }   // removal bites within 5 min
  return out;
}
function userStillActive_(user) {
  var u = String(user || '').trim().toLowerCase();
  if (!u) return false;
  // The admin is not a sheet row, so its liveness is the passcode's: clear the
  // Script Property and the account is gone, same as deleting a LOGIN row.
  if (u === ADMIN_ID) return !!adminPass_();
  return Object.prototype.hasOwnProperty.call(userGens_(), u);
}
/* A fingerprint of the credential a token was minted against. Change a password
   (or rotate ADMIN_PASSCODE) and every token carrying the old fingerprint stops
   verifying — the per-user revocation the app otherwise lacks, since renewal
   would happily extend a stolen token forever. Derived from the stored hash, so
   it costs no extra column and never exposes the hash itself. */
function credGen_(secretish) {
  return Utilities.base64EncodeWebSafe(
    Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, 'gen:' + String(secretish || ''))
  ).slice(0, 10);
}
/* username -> current fingerprint. Shares the 5-minute window activeUsers_ used,
   so revocation bites just as fast and costs the same single sheet read. */
function userGens_() {
  var c = null, hit = null;
  try { c = CacheService.getScriptCache(); hit = c.get('user_gens'); } catch (e) {}
  if (hit) { try { return JSON.parse(hit); } catch (e) {} }
  var rows = loginRows_(), out = {};
  for (var i = 0; i < rows.length; i++) {
    var u = String(rows[i].username || '').trim().toLowerCase();
    if (u) out[u] = credGen_(String(rows[i].password || ''));
  }
  if (c) { try { c.put('user_gens', JSON.stringify(out), 300); } catch (e) {} }
  return out;
}
function currentGen_(user) {
  var u = String(user || '').trim().toLowerCase();
  if (u === ADMIN_ID) { var ap = adminPass_(); return ap ? credGen_('admin:' + ap) : ''; }
  var g = userGens_();
  return Object.prototype.hasOwnProperty.call(g, u) ? g[u] : '';
}
function makeToken_(user, role) {
  var raw = user + '|' + role + '|' + currentGen_(user) + '|' + Date.now();
  var sig = Utilities.base64EncodeWebSafe(Utilities.computeHmacSha256Signature(raw, tokenSecret_()));
  return Utilities.base64EncodeWebSafe(raw) + '.' + sig;
}
function checkToken_(token) {
  var parts = String(token || '').split('.'); if (parts.length !== 2) return null;
  var raw; try { raw = Utilities.newBlob(Utilities.base64DecodeWebSafe(parts[0])).getDataAsString(); } catch (e) { return null; }
  var want = Utilities.base64EncodeWebSafe(Utilities.computeHmacSha256Signature(raw, tokenSecret_()));
  if (want !== parts[1]) return null;
  // Parsed from the end: the username is the one field that can itself contain
  // a '|', so counting from the front would misread every other field.
  var b = raw.split('|');
  if (b.length < 4) return null;
  var issued = Number(b[b.length - 1]), gen = b[b.length - 2], role = b[b.length - 3], user = b.slice(0, b.length - 3).join('|');
  // A good signature is not enough: past the window the token is dead, which is
  // what stops a copied token from working forever.
  if (!issued || Date.now() - issued > SESSION_MS) return null;
  // Nor is the window enough on its own — renewal would slide it indefinitely.
  // The credential that minted this token must still be the current one, so a
  // password change or a passcode rotation ends every session it issued.
  if (!gen || gen !== currentGen_(user)) return null;
  return { user: user, role: role, issued: issued };
}
/* Called once per app launch: confirms the stored token is still good AND that
   the account still exists, then hands back a fresh one -- which is what makes
   the seven days slide. The display name is not returned; the client kept it
   from sign-in. */
function handleSession_(p) {
  var t = checkToken_(p && p.auth || '');
  if (!t) return { ok: false, error: 'login required' };
  // Renewal is the one place a session can outlive the account, so it is the one
  // place worth a sheet read: without this, a removed realtor renews forever.
  if (!userStillActive_(t.user)) return { ok: false, error: 'login required' };
  return { ok: true, user: t.user, role: t.role, token: makeToken_(t.user, t.role) };
}

/* ================= editor helpers ================= */
function listTabs() {
  Object.keys(SHEETS).forEach(function (key) {
    Logger.log('=== ' + key + ' ===');
    try { ssFor_(key).getSheets().forEach(function (s) { Logger.log('  ' + (isAllowed_(key, s.getName()) ? 'ALLOWED ' : 'blocked ') + '[' + s.getName() + ']'); }); }
    catch (err) { Logger.log('  !! ' + err); }
  });
}
function debugLogin() {
  var rows = loginRows_(); Logger.log('total rows = ' + rows.length);
  for (var i = 0; i < rows.length; i++) Logger.log(i + ' user=[' + rows[i].username + '] name=[' + rows[i].name + '] hashed=' + pwIsHashed_(rows[i].password));
}
