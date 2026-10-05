/**
 * Realtor Portal — team screens: home, leaderboard, deals, bootcamp
 * Part of the Realtor Portal Apps Script project; all .gs files share one
 * global scope, so load order does not matter.
 */
/* ================= BASIC READ-ONLY PAGES (all open) ================= */

/* Leaderboard — reads ONLY the pre-synced "Leaderboard" tab (FUB sync stays in the portal). */
function fubStamp_(v) {
  if (Object.prototype.toString.call(v) === '[object Date]' && !isNaN(v)) return Utilities.formatDate(v, 'America/Toronto', 'MMM d, h:mm a');
  return String(v == null ? '' : v);
}
// Live current year + month (1..12), from the Toronto clock. Rolls over on its own.
function fubYM_() {
  var n = new Date();
  return { y: Number(Utilities.formatDate(n, 'America/Toronto', 'yyyy')),
           m: Number(Utilities.formatDate(n, 'America/Toronto', 'MM')) };   // m = 1..12
}
function fubMonthKey_(y, m) { return 'y' + y + 'm' + (m < 10 ? '0' : '') + m; }
function fubCurKey_() { var t = fubYM_(); return fubMonthKey_(t.y, t.m); }                 // this month, always current
function fubLastKey_() { var t = fubYM_(), y = t.y, m = t.m - 1; if (m < 1) { m = 12; y--; } return fubMonthKey_(y, m); }  // previous month, year-safe
function lbKey_(p) {
  p = String(p || '').trim();
  if (!p || p === 'month') return fubCurKey_();   // always the ongoing month
  if (p === 'last') return fubLastKey_();          // always the month before
  return p;   // 'week' | 'year' | a specific 'y2026m08' from the month picker
}
/* `period` arrives from the client and lbKey_ passes anything it does not recognise
   straight through, so it must never be pasted into a cache key as-is: arbitrary
   values would mint unbounded entries and push real ones out of a cache that holds
   1000 items -- including the chunks of the city index this all exists to keep warm.
   A '|' would be worse still, since chunk parts live at `key|N`. Only the shapes the
   app actually asks for get a key; anything else is served correctly but uncached. */
function lbCacheKey_(prefix, key) {
  return /^(week|year|all|y\d{4}(m\d{2})?)$/.test(String(key)) ? prefix + key : '';
}
function getLeaderboard_(key) {
  key = lbKey_(key);
  /* Cached per resolved period key, so switching tabs re-reads the sheet at most
     once per period per TTL instead of on every tap. */
  var ck = lbCacheKey_('lb_api_', key), hit = ck ? cacheGet_(ck) : null; if (hit) return hit;
  try {
    var sh = ssFor_('main').getSheetByName('Leaderboard');
    if (!sh) return { ok: false, error: 'No leaderboard data yet.' };
    var lastRow = sh.getLastRow();
    if (lastRow < 2) return { ok: false, error: 'No leaderboard data yet.' };
    var vals = sh.getRange(2, 1, lastRow - 1, 6).getValues(), list = [], updated = '';
    if (key === 'year') {
      var yr = String(new Date().getFullYear()), by = {};
      for (var r = 0; r < vals.length; r++) {
        var pk = String(vals[r][0] || ''), mm = pk.match(/^y(\d{4})m\d{2}$/);
        if (!mm || mm[1] !== yr) continue;
        var nm = String(vals[r][1] || ''); if (!nm) continue;
        var a = by[nm] || (by[nm] = { name: nm, calls: 0, conv: 0, talkSec: 0 });
        a.calls += Number(vals[r][2]) || 0; a.conv += Number(vals[r][3]) || 0; a.talkSec += Number(vals[r][4]) || 0;
        updated = fubStamp_(vals[r][5]) || updated;
      }
      for (var nk in by) list.push(by[nk]);
    } else {
      for (var r2 = 0; r2 < vals.length; r2++) {
        if (String(vals[r2][0]) !== key) continue;
        updated = fubStamp_(vals[r2][5]) || updated;
        list.push({ name: String(vals[r2][1] || ''), calls: Number(vals[r2][2]) || 0, conv: Number(vals[r2][3]) || 0, talkSec: Number(vals[r2][4]) || 0 });
      }
    }
    list = list.filter(function (a) { return !guideIsAdmin_(a.name); });   // hide non-selling accounts
    if (!list.length) return { ok: false, error: 'No rows for "' + key + '".' };
    list.sort(function (x, y) { return (y.talkSec - x.talkSec) || (y.calls - x.calls); });
    var team = { calls: 0, conv: 0, talkSec: 0 };
    list.forEach(function (a) { team.calls += a.calls; team.conv += a.conv; team.talkSec += a.talkSec; });
    var res = { ok: true, period: key, updated: updated, team: team, agents: list };
    if (ck) cachePut_(ck, res);
    return res;
  } catch (e) { return { ok: false, error: String((e && e.message) || e) }; }
}

/* FAQ */
function getFaqs_() {
  var hit = cacheGet_('faqs_api'); if (hit) return hit;
  var sheets = sheetsFor_('main'), sh = null;
  for (var i = 0; i < sheets.length; i++) if (sheets[i].getName().toUpperCase().indexOf('FAQ') >= 0) { sh = sheets[i]; break; }
  if (!sh || sh.getLastRow() < 2) return { count: 0, rows: [] };
  var disp = sh.getDataRange().getDisplayValues(), rts = [], fmls = [];
  var hr = -1;
  for (var r = 0; r < Math.min(6, disp.length) && hr < 0; r++) { if (disp[r].map(function (c) { return String(c || '').trim().toUpperCase(); }).indexOf('QUESTION') >= 0) hr = r; }
  if (hr < 0) hr = 0;
  var hdr = disp[hr].map(function (c) { return String(c || '').trim().toUpperCase(); });
  function col(keys) { for (var c = 0; c < hdr.length; c++) for (var k = 0; k < keys.length; k++) if (hdr[c] === keys[k]) return c; for (var c2 = 0; c2 < hdr.length; c2++) for (var k2 = 0; k2 < keys.length; k2++) if (hdr[c2].indexOf(keys[k2]) >= 0) return c2; return -1; }
  var m = { category: col(['CATEGORY', 'TYPE', 'SECTION']), question: col(['QUESTION', 'Q']), answer: col(['ANSWER', 'RESPONSE']), source: col(['SOURCE', 'LINK', 'URL', 'REFERENCE']) };
  /* Only the source column carries links — fetch that column, not the whole sheet. */
  rts = colRange_(sh, m.source, disp.length, 'rich');
  fmls = colRange_(sh, m.source, disp.length, 'formula');
  function g(row, k) { return m[k] >= 0 ? String(row[m[k]] || '').trim() : ''; }
  var out = [], lastCat = '';
  for (var r2 = hr + 1; r2 < disp.length; r2++) {
    var q = g(disp[r2], 'question'), cat = g(disp[r2], 'category');
    if (cat) lastCat = cat;
    if (!q) continue;
    var src = g(disp[r2], 'source'), url = '';
    if (m.source >= 0) url = cellUrl_(rts[r2] ? rts[r2][0] : null, fmls[r2] ? fmls[r2][0] : '', src);
    out.push({ category: (cat || lastCat || 'General'), question: q, answer: g(disp[r2], 'answer'), source: url, sourceText: (url && /^https?:/i.test(src)) ? '' : src });
  }
  var res = { updated: new Date().toISOString(), count: out.length, rows: out };
  cachePut_('faqs_api', res); return res;
}

/* Vacation Tracker */
function getVacations_() {
  var hit = cacheGet_('vacations_api'); if (hit) return hit;
  var sheets = sheetsFor_('main'), sh = null;
  for (var i = 0; i < sheets.length && !sh; i++) if (sheets[i].getName().trim().toUpperCase().indexOf('VACATION') >= 0) sh = sheets[i];
  if (!sh || sh.getLastRow() < 2) return { count: 0, rows: [] };
  var rng = sh.getDataRange(), disp = rng.getDisplayValues(), vals = rng.getValues();
  var hr = -1;
  for (var r = 0; r < Math.min(5, disp.length) && hr < 0; r++) { var row = disp[r].map(function (c) { return String(c || '').trim().toUpperCase(); }); if (row.indexOf('NAME') >= 0 && (row.indexOf('FROM') >= 0 || row.indexOf('TO') >= 0)) hr = r; }
  if (hr < 0) hr = 0;
  var hdr = disp[hr].map(function (c) { return String(c || '').trim().toUpperCase(); });
  function col(keys) { for (var c = 0; c < hdr.length; c++) for (var k = 0; k < keys.length; k++) if (hdr[c] === keys[k]) return c; for (var c2 = 0; c2 < hdr.length; c2++) for (var k2 = 0; k2 < keys.length; k2++) if (hdr[c2].indexOf(keys[k2]) >= 0) return c2; return -1; }
  var m = { name: col(['NAME']), from: col(['FROM', 'START']), to: col(['TO', 'END']), reachable: col(['REACHABLE']), remove: col(['REMOVE FROM LEAD FLOW', 'LEAD FLOW', 'REMOVE']), note: col(['NOTE']) };
  function iso(v, text) { if (v instanceof Date && !isNaN(v)) return Utilities.formatDate(v, Session.getScriptTimeZone(), 'yyyy-MM-dd'); var d = new Date(String(text || '').trim()); return isNaN(d) ? '' : Utilities.formatDate(d, Session.getScriptTimeZone(), 'yyyy-MM-dd'); }
  function g(row, k) { return m[k] >= 0 ? String(row[m[k]] || '').trim() : ''; }
  var out = [];
  for (var r2 = hr + 1; r2 < disp.length; r2++) {
    var name = g(disp[r2], 'name'); if (!name) continue;
    out.push({ name: name, from: g(disp[r2], 'from'), to: g(disp[r2], 'to'),
      fromISO: m.from >= 0 ? iso(vals[r2][m.from], disp[r2][m.from]) : '', toISO: m.to >= 0 ? iso(vals[r2][m.to], disp[r2][m.to]) : '',
      reachable: g(disp[r2], 'reachable'), remove: g(disp[r2], 'remove'), note: g(disp[r2], 'note') });
  }
  var res = { updated: new Date().toISOString(), count: out.length, rows: out };
  cachePut_('vacations_api', res); return res;
}

/* Call Night (read-only) — names col H (row 2+), date columns I onward, attendance[iso][name]=true */
var CN_NAME_COL = 8, CN_FIRST_DATE_COL = 9;   // H = names, I = first date column
function cnIso_(v) {
  var TZ = 'America/Toronto';
  if (v instanceof Date && !isNaN(v)) return Utilities.formatDate(v, TZ, 'yyyy-MM-dd');
  var sv = String(v == null ? '' : v).trim(); if (!sv) return '';
  var m = sv.match(/^(\d{4})-(\d{2})-(\d{2})/); if (m) return m[1] + '-' + m[2] + '-' + m[3];
  var d = new Date(sv); return isNaN(d) ? '' : Utilities.formatDate(d, TZ, 'yyyy-MM-dd');
}
function cnPresent_(v) {
  if (v === true) return true;
  var sv = String(v == null ? '' : v).trim().toLowerCase();
  return sv === 'present' || sv === 'p' || sv === 'yes' || sv === 'y' || sv === 'true' || sv === '1' || sv === 'x' || sv === '\u2713';
}
function callNightSheet_() {
  var ss = ssFor_('main'), sh = ss.getSheetByName('Call Night');
  if (sh) return sh;
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) if (sheets[i].getName().trim().toUpperCase().indexOf('CALL NIGHT') >= 0) return sheets[i];
  return null;
}
function getCallNight_() {
  var hit = cacheGet_('callnight_api'); if (hit) return hit;
  try {
    var sh = callNightSheet_();
    if (!sh) return { ok: false, error: 'No "Call Night" sheet found.', realtors: [], dates: [], attendance: {} };
    var lastRow = sh.getLastRow(), lastCol = sh.getLastColumn();
    var names = [], nameRows = {};
    if (lastRow >= 2) {
      var nameVals = sh.getRange(2, CN_NAME_COL, lastRow - 1, 1).getValues();
      for (var i = 0; i < nameVals.length; i++) { var n = String(nameVals[i][0] || '').trim(); if (n) { names.push(n); nameRows[n] = i + 2; } }
    }
    var dates = [], dateCols = {};
    if (lastCol >= CN_FIRST_DATE_COL) {
      var hdr = sh.getRange(1, CN_FIRST_DATE_COL, 1, lastCol - CN_FIRST_DATE_COL + 1).getValues()[0];
      for (var c = 0; c < hdr.length; c++) { var iso = cnIso_(hdr[c]); if (iso) { if (!dateCols[iso]) dates.push(iso); dateCols[iso] = CN_FIRST_DATE_COL + c; } }
    }
    dates.sort().reverse();   // newest first
    var attendance = {};
    if (dates.length && names.length) {
      var block = sh.getRange(2, CN_FIRST_DATE_COL, lastRow - 1, lastCol - CN_FIRST_DATE_COL + 1).getValues();
      dates.forEach(function (iso) {
        var colOffset = dateCols[iso] - CN_FIRST_DATE_COL;
        attendance[iso] = {};
        names.forEach(function (n) { attendance[iso][n] = cnPresent_(block[nameRows[n] - 2][colOffset]); });
      });
    }
    /* Only a good read is cached — caching a failure would pin the error for the
       whole TTL, long after whatever caused it went away. */
    var res = { ok: true, updated: new Date().toISOString(), realtors: names, dates: dates, attendance: attendance };
    cachePut_('callnight_api', res); return res;
  } catch (e) { return { ok: false, error: String((e && e.message) || e), realtors: [], dates: [], attendance: {} }; }
}

/* School Finder — region -> board website link */
function getSchoolFinder_() {
  var hit = cacheGet_('schoolfinder_api'); if (hit) return hit;
  var ss = ssFor_('main'), sh = ss.getSheetByName('School');
  if (!sh) { var sheets = ss.getSheets();   // any tab with SCHOOL but not RANK (matches the portal's finder resolver)
    for (var i = 0; i < sheets.length && !sh; i++) { var n = sheets[i].getName().toUpperCase(); if (n.indexOf('SCHOOL') >= 0 && n.indexOf('RANK') < 0) sh = sheets[i]; } }
  var out = [];
  if (sh && sh.getLastRow() >= 1) {
    var vals = sh.getDataRange().getDisplayValues(), start = 0;
    var h0 = String(vals[0][0] || '').toUpperCase(), h1 = String(vals[0][1] || '').toUpperCase();
    if (/REGION|BOARD|AREA|DISTRICT/.test(h0) || /LINK|URL|WEBSITE|SITE/.test(h1)) start = 1;
    for (var r = start; r < vals.length; r++) {
      var region = String(vals[r][0] || '').trim(), url = String(vals[r][1] || '').trim();
      if (!/^https?:\/\//i.test(url)) { for (var c = 1; c < vals[r].length; c++) { var v = String(vals[r][c] || '').trim(); if (/^https?:\/\//i.test(v)) { url = v; break; } } }
      if (!region && !url) continue;
      out.push({ _row: r + 1, region: region, url: url });
    }
  }
  var res = { updated: new Date().toISOString(), count: out.length, rows: out };
  cachePut_('schoolfinder_api', res); return res;
}

/* ================= MEETINGS LEADERBOARD (deals sheet "Meetings" tab) ================= */
var FUB_TZ = 'America/Toronto';
var FUB_MTG_SOLO = 'mandeep';   // skipped when a meeting has a co-agent

/* period -> {start,end} yyyy-MM-dd (null = all time) */
function fubRange_(key) {
  var now = new Date();
  var y = Number(Utilities.formatDate(now, FUB_TZ, 'yyyy')), start, end;
  var mm = String(key).match(/^y(\d{4})m(\d{2})$/);
  if (mm) { var yy = Number(mm[1]), mo = Number(mm[2]) - 1; start = new Date(yy, mo, 1); end = new Date(yy, mo + 1, 0); if (end > now) end = now; }
  else if (key === 'week') { var dow = Number(Utilities.formatDate(now, FUB_TZ, 'u')) % 7; start = new Date(now); start.setDate(now.getDate() - dow); start.setHours(0, 0, 0, 0); end = now; }
  else if (key === 'year') { start = new Date(y, 0, 1); end = now; }
  else if (String(key).match(/^y(\d{4})$/)) { var yr = Number(RegExp.$1); start = new Date(yr, 0, 1); end = new Date(yr, 11, 31); if (end > now) end = now; }
  else { start = new Date(y, now.getMonth(), 1); end = now; }
  return { start: Utilities.formatDate(start, FUB_TZ, 'yyyy-MM-dd'), end: Utilities.formatDate(end, FUB_TZ, 'yyyy-MM-dd') };
}
function fubMtgSheet_() {
  var sheets = sheetsFor_('deals');
  for (var i = 0; i < sheets.length; i++) {
    var nm = sheets[i].getName().trim().toUpperCase();
    if (nm === 'MEETINGS' || (nm.indexOf('MEETING') >= 0 && nm.indexOf('MONTHLY') < 0 && nm.indexOf('STAGE') < 0)) return sheets[i];
  }
  return null;
}
function fubMtgDateISO_(rawVal, dispVal) {
  if (Object.prototype.toString.call(rawVal) === '[object Date]' && !isNaN(rawVal)) return Utilities.formatDate(rawVal, FUB_TZ, 'yyyy-MM-dd');
  var sv = String(dispVal || '').trim(); if (!sv) return '';
  var d = new Date(sv); return isNaN(d) ? '' : Utilities.formatDate(d, FUB_TZ, 'yyyy-MM-dd');
}
function fubIsInternal_(clientName) { return /realtor|agent/.test(String(clientName || '').toLowerCase()); }
function fubSplitAgents_(cell) {
  return String(cell || '').split(/\s*(?:&|\/|,|\band\b|\+)\s*/i).map(function (s) { return s.trim(); }).filter(function (s) { return s.length; });
}
function fubCreditAgent_(agents) {
  if (!agents.length) return '';
  if (agents.length === 1) return agents[0];
  var others = agents.filter(function (a) { return a.toLowerCase().indexOf(FUB_MTG_SOLO) < 0; });
  return others.length ? others[0] : agents[0];
}
function getMeetingsLeaderboard_(key) {
  try {
    key = lbKey_(key);
    var ck = lbCacheKey_('mtg_api_', key), hit = ck ? cacheGet_(ck) : null; if (hit) return hit;
    var range = (key && key !== 'all') ? fubRange_(key) : null;
    var sh = fubMtgSheet_();
    if (!sh || sh.getLastRow() < 2) return { ok: false, error: 'Meetings tab not found or empty.', agents: [] };
    var rng0 = sh.getDataRange(), vals = rng0.getDisplayValues(), raw = rng0.getValues();
    var hdr = vals[0].map(function (h) { return String(h || '').trim().toUpperCase(); });
    function col(keys) { for (var c = 0; c < hdr.length; c++) for (var k = 0; k < keys.length; k++) if (hdr[c] === keys[k]) return c; for (var c2 = 0; c2 < hdr.length; c2++) for (var k2 = 0; k2 < keys.length; k2++) if (hdr[c2].indexOf(keys[k2]) >= 0) return c2; return -1; }
    var aCol = col(['AGENT', 'REALTOR']), cCol = col(['LEAD', 'CLIENT', 'NAME']), dCol = col(['DATE']), monthCol = col(['MONTH']);
    if (aCol < 0) return { ok: false, error: 'No Agent column in Meetings tab.', agents: [] };
    var counts = {};
    for (var r = 1; r < vals.length; r++) {
      if (range) {
        var iso = '';
        if (dCol >= 0) iso = fubMtgDateISO_(raw[r] ? raw[r][dCol] : null, vals[r][dCol]);
        if (!iso && monthCol >= 0) { var mk = String(vals[r][monthCol] || '').trim(); if (/^\d{4}-\d{2}$/.test(mk)) iso = mk + '-15'; }
        if (!iso) continue;
        if (iso < range.start || iso > range.end) continue;
      }
      if (fubIsInternal_(cCol >= 0 ? vals[r][cCol] : '')) continue;
      var agents = fubSplitAgents_(vals[r][aCol]); if (!agents.length) continue;
      var who = fubCreditAgent_(agents); if (!who) continue;
      counts[who.trim()] = (counts[who.trim()] || 0) + 1;
    }
    var list = []; for (var nm in counts) list.push({ name: nm, meetings: counts[nm] });
    list.sort(function (x, y) { return y.meetings - x.meetings; });
    var res = { ok: true, period: key || 'all', agents: list };
    if (ck) cachePut_(ck, res);
    return res;
  } catch (e) { return { ok: false, error: String((e && e.message) || e), agents: [] }; }
}

/* =====================================================================
   BIG CHUNKS: focus/cities index, My Deals, Home payload, Bootcamp
   ===================================================================== */

/* ---------- search index across all city tabs (focus flag lives here) ---------- */
/* School Rankings trimmed to the fields the app renders (~270KB -> ~80KB). */
function rankingsSlim_() {
  var hit = cacheGet_('rankings_slim'); if (hit) { hit.cached = true; return hit; }
  var full = readTab_('School Rankings', 'main', '');
  if (!full || !full.rows) return full;
  function pick(r, names) { for (var k in r) { var lk = k.toLowerCase(); for (var i = 0; i < names.length; i++) if (lk === names[i]) return r[k]; } return ''; }
  var rows = full.rows.map(function (r) {
    return { school: pick(r, ['school', 'name']), level: pick(r, ['level', 'panel']), board: pick(r, ['board']),
             city: pick(r, ['city', 'municipality']), community: pick(r, ['community', 'area']),
             score: pick(r, ['score', 'rating']), rank: pick(r, ['rank', 'ranking']) };
  });
  var out = { updated: full.updated, count: rows.length, rows: rows };
  cachePut_('rankings_slim', out); return out;
}

/* The most expensive build in the app (~60 city tabs), and the one both `focus`
   and `citycounts` depend on — so it is the one that must never be built twice
   at once. cachedBuild_ holds the lock; everything else here is unchanged. */
function getSearchIndex_() {
  return cachedBuild_('index_api', buildSearchIndex_).rows;
}
function buildSearchIndex_() {
  var cities = getCities_().cities, out = [];
  /* Warm every city's cached payload in one round trip before the loop reads them one
     by one — same keys getProjects_ builds, so a hit here saves it the sheet read. */
  var warm = [];
  for (var w = 0; w < cities.length; w++) warm.push('proj_' + String(cities[w] || '').trim().toUpperCase());
  cachePrefetch_(warm);
  for (var i = 0; i < cities.length; i++) {
    var c = cities[i], res;
    try { res = getProjects_(c); } catch (e) { res = { rows: [] }; }
    var ps = res.rows || [];
    for (var j = 0; j < ps.length; j++) {
      var p = ps[j];
      if (p.hidden) continue;                                   // "Not Available" excluded
      out.push({ city: c, project: p.project, builder: p.builder, type: p.type, cats: p.cats,
        broker_url: p.broker_url, drive_url: p.drive_url, website_url: p.website_url, hasFub: !!p.fub, _row: p._row,
        focus: /fo(cu|uc)s/i.test(p.status || ''), occupancy: p.occupancy });
    }
  }
  return { rows: out };   // cachedBuild_ owns the write
}
/* Both of these are small derivations of a very large index. Caching the derivation
   too saves parsing that index (300KB+) on every Home and Cities load — the Cities
   screen asks for both at once, so without this one visit parses it twice. */
function getFocus_() {
  var hit = cacheGet_('focus_api'); if (hit) return hit;
  var idx = getSearchIndex_(), out = [];
  for (var i = 0; i < idx.length; i++) if (idx[i].focus) out.push(idx[i]);
  var res = { updated: new Date().toISOString(), count: out.length, rows: out };
  cachePut_('focus_api', res); return res;
}
function getCityCounts_() {
  var hit = cacheGet_('citycounts_api'); if (hit) return hit;
  var idx = getSearchIndex_(), counts = {};
  for (var i = 0; i < idx.length; i++) { var c = idx[i].city; counts[c] = (counts[c] || 0) + 1; }
  var cities = getCities_().cities, out = [];
  for (var j = 0; j < cities.length; j++) out.push({ city: cities[j], count: counts[cities[j]] || 0 });
  var res = { updated: new Date().toISOString(), count: out.length, cities: out };
  cachePut_('citycounts_api', res); return res;
}


/* ---------- HOME payload (matches the portal's Home) ----------
   Home shows: upcoming events, recent updates, focus projects, and guide links.
   Resources and Concierge (Contractors) are just nav shortcuts in the app -> not
   embedded here. Cities are NOT shown on Home; only their focus projects are. */
function findMainLoose_(keys) {
  var sheets = sheetsFor_('main');
  for (var i = 0; i < sheets.length; i++) { var n = sheets[i].getName().toUpperCase(); for (var k = 0; k < keys.length; k++) if (n.indexOf(keys[k]) >= 0) return sheets[i]; }
  return null;
}
function readLoose_(sh, spec, requireKey) {
  if (!sh || sh.getLastRow() < 2) return [];
  var disp = sh.getDataRange().getDisplayValues();
  var hdr = disp[0].map(function (h) { return String(h || '').trim().toUpperCase(); });
  function col(keys) { for (var c = 0; c < hdr.length; c++) for (var k = 0; k < keys.length; k++) if (hdr[c] === keys[k]) return c; for (var c2 = 0; c2 < hdr.length; c2++) for (var k2 = 0; k2 < keys.length; k2++) if (hdr[c2].indexOf(keys[k2]) >= 0) return c2; return -1; }
  var m = {}; for (var f in spec) m[f] = col(spec[f]);
  var dateIdx = (m.date !== undefined) ? m.date : -1;
  var linkIdx = (m.link !== undefined) ? m.link : -1;
  /* Only the link column needs hyperlink/formula data and only the date column needs
     typed values; everything else comes from the displayed text. This runs on the Home
     hot path, where it used to pull rich text for the entire Events sheet. */
  var rts = colRange_(sh, linkIdx, disp.length, 'rich');
  var fmls = colRange_(sh, linkIdx, disp.length, 'formula');
  var raw = colRange_(sh, dateIdx, disp.length, 'value');
  var out = [];
  for (var r = 1; r < disp.length; r++) {
    var o = {}, has = false;
    for (var key in m) { var idx = m[key]; var v = idx >= 0 ? String(disp[r][idx] || '').trim() : ''; o[key] = v; if (key === requireKey && v) has = true; }
    if (requireKey && !has) continue;
    // link column: pull real hyperlink if present
    if (linkIdx >= 0) { var u = cellUrl_(rts[r] ? rts[r][0] : null, fmls[r] ? fmls[r][0] : '', disp[r][linkIdx]); if (u) o.link = u; }
    o.iso = dateIdx >= 0 ? dateISO_(raw[r] ? raw[r][0] : null, disp[r][dateIdx]) : '';
    out.push(o);
  }
  return out;
}
function getHomeEvents_() {
  var events = readLoose_(findMainLoose_(['EVENT']),
    { date: ['DATE', 'WHEN', 'START'], title: ['TITLE', 'EVENT', 'NAME'], time: ['TIME'],
      location: ['LOCATION', 'WHERE', 'VENUE', 'ADDRESS'], details: ['DETAIL', 'DESCRIPTION', 'NOTE'], link: ['LINK', 'URL', 'RSVP'] }, 'title');
  var today = Utilities.formatDate(new Date(), 'America/Toronto', 'yyyy-MM-dd');
  events = events.filter(function (e) { return !e.iso || e.iso >= today; });
  events.sort(function (a, b) { return (a.iso || '9999') < (b.iso || '9999') ? -1 : 1; });
  return events.slice(0, 40);
}
function getHome_() {
  var hit = cacheGet_('home_api_v2'); if (hit) return hit;
  var res = {
    updated: new Date().toISOString(),
    contacts: getContacts_().rows,   // full list; app groups by category
    events: getHomeEvents_(),        // upcoming events
    focus: getFocus_().rows          // focus projects only (no cities)
    // No guides (own page) and no updates (hardcoded in the app HTML).
  };
  cachePut_('home_api_v2', res); return res;
}

/* ===================== MY DEALS (login-gated) ===================== */
var DEALS_TAB = 'DEALS';
function num_(v) { var n = parseFloat(String(v == null ? '' : v).replace(/[^0-9.\-]/g, '')); return isNaN(n) ? 0 : n; }
function year_(v) { var m = String(v == null ? '' : v).match(/(20\d{2})/); return m ? m[1] : ''; }
function pad2_(n) { n = String(n); return n.length < 2 ? '0' + n : n; }
function dateISO_(rawValue, text) {
  var tz = 'America/Toronto';
  if (rawValue instanceof Date && !isNaN(rawValue)) return Utilities.formatDate(rawValue, tz, 'yyyy-MM-dd');
  var t = String(text == null ? '' : text).trim(); if (!t) return '';
  var m = t.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/); if (m) return m[1] + '-' + pad2_(m[2]) + '-' + pad2_(m[3]);
  m = t.match(/^(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})$/);
  if (m) { var a = parseInt(m[1], 10), b = parseInt(m[2], 10), y = parseInt(m[3], 10); if (y < 100) y += 2000; var mo, da; if (a > 12) { da = a; mo = b; } else { mo = a; da = b; } if (mo >= 1 && mo <= 12 && da >= 1 && da <= 31) return y + '-' + pad2_(mo) + '-' + pad2_(da); }
  var d = new Date(t); return isNaN(d) ? '' : Utilities.formatDate(d, tz, 'yyyy-MM-dd');
}
function fuKey_(property, client, closing) {
  return [property, client, closing].map(function (x) { return String(x == null ? '' : x).trim().toLowerCase().replace(/\s+/g, ' '); }).join('|');
}
/* resolve the deal-match name from a username (token carries username) */
function matchNameForUser_(username) {
  username = String(username || '').trim(); if (!username) return '';
  var rows = loginRows_();
  for (var i = 0; i < rows.length; i++) {
    if (rows[i].username && rows[i].username.toLowerCase() === username.toLowerCase())
      return String(rows[i].deal_name || rows[i].name || rows[i].username || '').trim();
  }
  return '';
}
function getMyDeals_(matchName) {
  matchName = String(matchName || '').trim(); if (!matchName) return [];
  var sh; try { sh = ssFor_('deals').getSheetByName(DEALS_TAB); } catch (e) { return []; }
  if (!sh || sh.getLastRow() < 2) return [];
  var lastCol = Math.max(sh.getLastColumn(), 18);
  var header = sh.getRange(1, 1, 1, lastCol).getDisplayValues()[0];
  function findCol(keys) { for (var c = 0; c < header.length; c++) { var h = String(header[c] || '').toUpperCase(); for (var k = 0; k < keys.length; k++) if (h.indexOf(keys[k]) >= 0) return c; } return -1; }
  var clientCol = findCol(['CLIENT']), notesCol = findCol(['NOTE', 'REMARK']), fubCol = findCol(['FUB', 'FOLLOW UP BOSS']), payCol = findCol(['PAYMENT RECEIVED', 'PAYMENT']);
  var rng2 = sh.getRange(2, 1, sh.getLastRow() - 1, lastCol), vals = rng2.getDisplayValues(), rawv = rng2.getValues();
  var mn = matchName.toLowerCase();
  function eq(x) { return String(x == null ? '' : x).trim().toLowerCase() === mn; }
  var out = [];
  for (var r = 0; r < vals.length; r++) {
    var row = vals[r], commIdx = -1;
    if (eq(row[9])) commIdx = 13; else if (eq(row[10])) commIdx = 14; else if (eq(row[11])) commIdx = 15;
    if (commIdx < 0) continue;
    out.push({
      property: String(row[1] || '').trim(), status: String(row[4] || '').trim(), firm: String(row[5] || '').trim(),
      closing: String(row[6] || '').trim(), price: String(row[7] || '').trim(), priceNum: num_(row[7]),
      commission: String(row[commIdx] || '').trim(), commissionNum: num_(row[commIdx]), trs: String(row[17] || '').trim(),
      payment: payCol >= 0 ? String(row[payCol] || '').trim() : String(row[22] || '').trim(), _row: r + 2,
      client: clientCol >= 0 ? String(row[clientCol] || '').trim() : '', notes: notesCol >= 0 ? String(row[notesCol] || '').trim() : '',
      fub: fubCol >= 0 ? String(row[fubCol] || '').trim() : '',
      closingISO: dateISO_(rawv[r] ? rawv[r][6] : null, row[6]), key: fuKey_(row[1], clientCol >= 0 ? row[clientCol] : '', row[6]), year: year_(row[5])
    });
  }
  return out;
}
function getMyLeads_(matchName) {
  matchName = String(matchName || '').trim(); if (!matchName) return [];
  var ss = ssFor_('deals'), sh = null, sheets = ss.getSheets();
  for (var i = 0; i < sheets.length && !sh; i++) { var nm = sheets[i].getName().trim().toUpperCase(); if (nm.indexOf('LEAD CAPACITY') >= 0 || nm === 'LEADS' || nm.indexOf('LEAD') >= 0) sh = sheets[i]; }
  if (!sh || sh.getLastRow() < 2) return [];
  var vals = sh.getDataRange().getDisplayValues(), hdr = vals[0].map(function (h) { return String(h || '').trim().toUpperCase(); });
  function col(keys) { for (var c = 0; c < hdr.length; c++) for (var k = 0; k < keys.length; k++) if (hdr[c].indexOf(keys[k]) >= 0) return c; return -1; }
  var m = { date: col(['DATE']), realtor: col(['REALTOR', 'AGENT']), client: col(['CLIENT', 'NAME']), stage: col(['STAGE']), source: col(['LEAD SOURCE', 'SOURCE']), fub: col(['FUB', 'LINK', 'URL']), notes: col(['NOTE']) };
  function g(row, k) { return m[k] >= 0 ? String(row[m[k]] || '').trim() : ''; }
  var mn = matchName.toLowerCase(), out = [];
  for (var r = 1; r < vals.length; r++) {
    if (String(g(vals[r], 'realtor')).toLowerCase() !== mn) continue;
    var client = g(vals[r], 'client'); if (!client && !g(vals[r], 'stage')) continue;
    out.push({ date: g(vals[r], 'date'), realtor: g(vals[r], 'realtor'), client: client, stage: g(vals[r], 'stage'), source: g(vals[r], 'source'), fub: g(vals[r], 'fub'), notes: g(vals[r], 'notes') });
  }
  return out;
}
function getMyMeetings_(matchName) {
  matchName = String(matchName || '').trim(); if (!matchName) return [];
  var sh = fubMtgSheet_(); if (!sh || sh.getLastRow() < 2) return [];
  var vals = sh.getDataRange().getDisplayValues(), rts = [], raw = [];
  var hdr = vals[0].map(function (h) { return String(h || '').trim().toUpperCase(); });
  function col(keys) { for (var c = 0; c < hdr.length; c++) for (var k = 0; k < keys.length; k++) if (hdr[c] === keys[k]) return c; for (var c2 = 0; c2 < hdr.length; c2++) for (var k2 = 0; k2 < keys.length; k2++) if (hdr[c2].indexOf(keys[k2]) >= 0) return c2; return -1; }
  var m = { month: col(['MONTH']), date: col(['DATE']), time: col(['TIME']), agent: col(['AGENT', 'REALTOR']), lead: col(['LEAD', 'CLIENT', 'NAME']), url: col(['FUB URL', 'FUB', 'URL', 'LINK']), source: col(['SOURCE']), type: col(['TYPE']), outcome: col(['OUTCOME']), status: col(['STATUS']) };
  if (m.lead === m.url) m.url = -1;
  /* My Deals is deliberately uncached (it is per-realtor), so this runs in full on
     every load — all the more reason not to pull rich text for the whole sheet when
     only the FUB link column needs it, and typed values only for the date column. */
  rts = colRange_(sh, m.url, vals.length, 'rich');
  raw = colRange_(sh, m.date, vals.length, 'value');
  function g(row, k) { return m[k] >= 0 ? String(row[m[k]] || '').trim() : ''; }
  var mn = matchName.toLowerCase(), out = [];
  for (var r = 1; r < vals.length; r++) {
    if (m.agent >= 0 && String(g(vals[r], 'agent')).toLowerCase() !== mn) continue;
    var lead = g(vals[r], 'lead'), diso = m.date >= 0 ? dateISO_(raw[r] ? raw[r][0] : null, vals[r][m.date]) : '';
    if (!lead && !diso) continue;
    var monthKey = g(vals[r], 'month'); if (!monthKey && diso) monthKey = diso.slice(0, 7);
    var url = g(vals[r], 'url');
    if (m.url >= 0 && !/^https?:/i.test(url)) url = cellUrl_(rts[r] ? rts[r][0] : null, '', vals[r][m.url]);
    out.push({ month: monthKey, dateISO: diso, date: g(vals[r], 'date'), time: g(vals[r], 'time'), lead: lead, fub: url, source: g(vals[r], 'source'), type: g(vals[r], 'type'), outcome: g(vals[r], 'outcome'), status: g(vals[r], 'status') });
  }
  out.sort(function (a, b) { return (b.dateISO || '') < (a.dateISO || '') ? -1 : 1; });
  return out;
}
/* Followup log (read-only) */
var FOLLOWUP_DAYS = 90, FOLLOWUP_FROM_YEAR = 2026;
function followupLog_() {
  var ss = ssFor_('deals'), sh = ss.getSheetByName('Followup Log'), map = {};
  if (sh && sh.getLastRow() > 1) {
    var vals = sh.getRange(2, 1, sh.getLastRow() - 1, 8).getDisplayValues();
    for (var r = 0; r < vals.length; r++) {
      var k = String(vals[r][0] || '').trim(); if (!k) continue;
      map[k] = { done: /^(y|yes|true|1|done)$/i.test(String(vals[r][5] || '').trim()), updated: String(vals[r][6] || '').trim(), nextISO: dateISO_(null, vals[r][7]) };
    }
  }
  return map;
}
function friendlyDate_(iso) { if (!iso) return ''; var d = new Date(iso + 'T00:00:00'); return isNaN(d) ? iso : Utilities.formatDate(d, 'America/Toronto', 'MMM d, yyyy'); }
function followupsFor_(deals, realtorName) {
  var log = followupLog_(), tz = 'America/Toronto';
  var today = Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd');
  var cutoff = new Date(); cutoff.setDate(cutoff.getDate() - FOLLOWUP_DAYS);
  var cutISO = Utilities.formatDate(cutoff, tz, 'yyyy-MM-dd'), current = [], future = [];
  for (var i = 0; i < deals.length; i++) {
    var d = deals[i]; if (!d.closingISO) continue;
    if (d.closingISO < FOLLOWUP_FROM_YEAR + '-01-01') continue;
    if (d.closingISO > cutISO) continue;
    var st = log[d.key] || null, days = Math.round((new Date() - new Date(d.closingISO)) / 864e5);
    var row = { key: d.key, property: d.property, client: d.client, closing: d.closing, closingISO: d.closingISO, price: d.price, fub: d.fub, realtor: realtorName || '', days: days };
    if (st && st.done && st.nextISO && st.nextISO > today) { row.nextISO = st.nextISO; row.nextTxt = friendlyDate_(st.nextISO); row.updated = st.updated || ''; future.push(row); }
    else { row.lastContact = (st && st.updated) ? st.updated : ''; current.push(row); }
  }
  current.sort(function (a, b) { return b.days - a.days; });
  future.sort(function (a, b) { return (a.nextISO || '') < (b.nextISO || '') ? -1 : 1; });
  return { current: current, future: future };
}
function myTickets_(username) {
  var u = String(username || '').toLowerCase(), sh = null, sheets = sheetsFor_('main');
  for (var i = 0; i < sheets.length && !sh; i++) if (sheets[i].getName().toUpperCase().indexOf('TICKET') >= 0) sh = sheets[i];
  var rows = readTableSmart_(sh);
  return rows.filter(function (t) { return (t.username || '').toLowerCase() === u; })
    .map(function (t) { return { ticket_id: t.ticket_id, document: t.document, status: t.status || 'Open', raised: t.raised_date, closed: t.closed_date, notes: t.notes }; });
}
/* One of the four bottom tabs, so it is tapped constantly, and it reads six sheets
   per call. The key is the token-derived username — never a client parameter — so
   one realtor's payload can never be served to another. Short TTL: these are the
   figures people refresh to check, and Refresh still forces a rebuild. */
function getMyDealsPayload_(p) {
  var tok = (p && p.__tok) || checkToken_(p.auth || ''); if (!tok) return { ok: false, error: 'login required' };
  var ck = 'mydeals_' + String(tok.user || '').toLowerCase();
  var hit = cacheGet_(ck); if (hit) { hit.cached = true; return hit; }
  var res = buildMyDealsPayload_(tok);
  if (res && res.ok) cachePut_(ck, res, 300);
  return res;
}
function buildMyDealsPayload_(tok) {
  var username = tok.user;
  var matchName = matchNameForUser_(username);
  if (!matchName) return { ok: false, error: 'no deal profile for this user' };
  var deals = []; try { deals = getMyDeals_(matchName); } catch (e) {}
  var leads = []; try { leads = getMyLeads_(matchName); } catch (e) {}
  var followups = { current: [], future: [] }; try { followups = followupsFor_(deals, matchName); } catch (e) {}
  var meetings = []; try { meetings = getMyMeetings_(matchName); } catch (e) {}
  var tickets = []; try { tickets = myTickets_(username); } catch (e) {}
  return { ok: true, name: matchName, username: username, deals: deals, leads: leads, followups: followups, meetings: meetings, tickets: tickets };
}

/* ===================== BOOTCAMP (login-gated, read-only) ===================== */
function onbSS_() { return ssFor_('onboarding'); }
function onbTab_(week) {
  var ss = onbSS_(); if (!ss) return null;
  if (Number(week) === 0) return ss.getSheetByName('Onboarding') || null;
  var sh = ss.getSheetByName('Week ' + week);
  if (!sh && week === 1) { var all = ss.getSheets(); if (all && all.length) sh = all[0]; }
  return sh || null;
}
function onbLinkUrl_(rt, formula) {
  var link = null;
  try { if (rt) { link = rt.getLinkUrl(); if (!link && rt.getRuns) { var runs = rt.getRuns(); for (var k = 0; k < runs.length; k++) { var u = runs[k].getLinkUrl(); if (u) { link = u; break; } } } } } catch (e) {}
  if (!link && formula) { var mm = String(formula).match(/HYPERLINK\(\s*"([^"]+)"/i); if (mm) link = mm[1]; }
  return link || null;
}
function isFill_(bg) { if (!bg) return false; bg = String(bg).toLowerCase().replace(/\s/g, ''); return !(bg === '' || bg === '#ffffff' || bg === '#fff' || bg === 'white' || bg === 'none'); }
function parseTargets_(s) {
  if (!/call|nurtur|home|builder/i.test(s)) return null;
  function n(re) { var m = s.match(re); return m ? Number(m[1]) : null; }
  var calls = n(/(\d+)\s*calls?/i), nur = n(/(\d+)\s*nurtur/i), homes = n(/(\d+)\s*homes?/i), builders = n(/(\d+)\s*builders?/i);
  if (calls == null && nur == null && homes == null && builders == null) return null;
  return [{ nm: 'Outbound calls', unit: 'calls', total: calls || 500 }, { nm: 'Home visits', unit: 'homes', total: homes || 25 }, { nm: 'Builder visits', unit: 'builders', total: builders || 5 }, { nm: 'Nurture leads', unit: 'nurtures', total: nur || 10 }];
}
function getOnboarding_(week) {
  week = Number(week); if (isNaN(week)) week = 1;
  var ck = 'onb_plan_api_' + week, hit = cacheGet_(ck); if (hit) return hit;
  var sh = onbTab_(week);
  if (!sh || sh.getLastRow() < 3) { var min = { n: week, title: (week === 0 ? 'Onboarding' : 'Week ' + week), empty: true, days: [] }; return min; }
  var lastR = sh.getLastRow(), lastC = Math.min(sh.getLastColumn() || 3, 8);
  var rng = sh.getRange(1, 1, lastR, lastC), vals = rng.getDisplayValues(), rich = null, formulas = null, bgs = null;
  try { rich = rng.getRichTextValues(); } catch (e) {}
  try { formulas = rng.getFormulas(); } catch (e) {}
  try { bgs = sh.getRange(1, 1, lastR, 1).getBackgrounds(); } catch (e) {}
  function linkAt(r, c) { return onbLinkUrl_(rich ? rich[r][c] : null, formulas ? formulas[r][c] : ''); }
  var statusCol = 1, notesCol = 2, shotCol = -1, hdrRow = -1;
  for (var r0 = 0; r0 < Math.min(vals.length, 6); r0++) for (var c0 = 0; c0 < lastC; c0++) {
    var v = String(vals[r0][c0] || '').trim().toUpperCase();
    if (v === 'STATUS') { statusCol = c0; hdrRow = r0; } if (v === 'NOTES') { notesCol = c0; if (hdrRow < 0) hdrRow = r0; }
    if (v.indexOf('SCREENSHOT') >= 0 || v.indexOf('PROOF') >= 0 || v.indexOf('SUBMISSION') >= 0 || v.indexOf('SUBMIT') >= 0 || v.indexOf('ATTACH') >= 0 || v.indexOf('UPLOAD') >= 0 || v === 'FILE' || v.indexOf('DOCUMENT') >= 0) shotCol = c0;
  }
  var title = '', focus = '', targets = null, days = [], dayMap = {}, cur = null, expectGoal = false;
  for (var r = 0; r < vals.length; r++) {
    if (r === hdrRow) continue;
    var a = String(vals[r][0] || '').trim(); if (!a) continue;
    if (/^welcome/i.test(a)) { title = a; continue; }
    if (/focus is/i.test(a)) { focus = a.replace(/^.*focus is\s*:?\s*/i, '').trim(); continue; }
    if (/^(status|notes)$/i.test(a)) continue;
    var dm = a.match(/^Day\s*(\d+)/i);
    if (dm) { var dn = Number(dm[1]); if (dayMap[dn]) cur = dayMap[dn]; else { cur = { n: dn, goal: '', tasks: [] }; days.push(cur); dayMap[dn] = cur; } expectGoal = true; continue; }
    if (/^GOAL\b/i.test(a)) {
      var tt = parseTargets_(a);
      if (tt) { targets = tt; continue; }
      if (!cur) { cur = { n: 1, goal: '', tasks: [] }; days.push(cur); }
      cur.tasks.push({ id: 'w' + week + 'd' + cur.n + 't' + cur.tasks.length, title: a.replace(/^GOAL\s*:?\s*/i, ''), url: '', note: '', noteUrl: '', goal: true });
      expectGoal = false; continue;
    }
    var fill = bgs ? isFill_(bgs[r][0]) : false;
    if (fill) { if (expectGoal && cur) { cur.goal = a; expectGoal = false; } continue; }
    expectGoal = false;
    if (!cur) { cur = { n: 1, goal: '', tasks: [] }; days.push(cur); }
    cur.tasks.push({ id: 'w' + week + 'd' + cur.n + 't' + cur.tasks.length, title: a, url: linkAt(r, 0) || '', note: String(vals[r][notesCol] || '').trim(), noteUrl: linkAt(r, notesCol) || '', needShot: shotCol >= 0 ? /^(y|yes|true|1|required|mandatory|need)/i.test(String(vals[r][shotCol] || '').trim()) : false, goal: false });
  }
  if (!days.length) return { n: week, title: title || ('Week ' + week), empty: true, days: [] };
  if (!targets) targets = [{ nm: 'Outbound calls', unit: 'calls', total: 500 }, { nm: 'Home visits', unit: 'homes', total: 25 }, { nm: 'Builder visits', unit: 'builders', total: 5 }, { nm: 'Nurture leads', unit: 'nurtures', total: 10 }];
  var res = { n: week, title: title || ('Week ' + week), focus: focus, targets: targets, days: days };
  cachePut_(ck, res); return res;
}
function onbProgressSheet_() {
  var ss = onbSS_(), sh = ss.getSheetByName('Bootcamp Progress') || ss.getSheetByName('Onboarding Progress');
  return sh || null;
}
function onbProgMap_() { return { ts: 0, user: 1, week: 2, day: 3, id: 4, status: 5, count: 6, notes: 7, proof: 8, dsub: 9, wsub: 10 }; }
function getOnboardingProgress_(user, week) {
  var sh = onbProgressSheet_(), out = { tasks: {}, daysSubmitted: {}, weeksSubmitted: {} };
  if (!sh || sh.getLastRow() < 2) return out;
  var m = onbProgMap_(), rows = sh.getDataRange().getDisplayValues();
  for (var r = 1; r < rows.length; r++) {
    var row = rows[r];
    if (String(row[m.user] || '').toLowerCase() !== String(user).toLowerCase()) continue;
    var w = Number(row[m.week]) || 0; if (week && w !== Number(week)) continue;
    var id = String(row[m.id] || '').trim();
    if (id && id.indexOf('__') !== 0) out.tasks[id] = { status: row[m.status] || 'not', count: Number(row[m.count]) || 0, notes: row[m.notes] || '', proof: row[m.proof] || '' };
    if (row[m.dsub]) out.daysSubmitted[w + '-' + (Number(row[m.day]) || 0)] = row[m.dsub];
    if (row[m.wsub]) out.weeksSubmitted[w] = row[m.wsub];
  }
  return out;
}
function bootcampWhen_(ms) { if (!ms) return ''; try { return Utilities.formatDate(new Date(ms), 'America/Toronto', "yyyy-MM-dd'T'HH:mm:ss"); } catch (e) { return new Date(ms).toISOString(); } }
function bootcampFullName_(user) {
  var rows = loginRows_();
  for (var i = 0; i < rows.length; i++) if (rows[i].username && String(rows[i].username).toLowerCase() === String(user).toLowerCase()) return rows[i].name || '';
  return '';
}
/* Self bootcamp view: plan for a week + this user's progress */
function getBootcampPayload_(p) {
  var tok = (p && p.__tok) || checkToken_(p.auth || ''); if (!tok) return { ok: false, error: 'login required' };
  // My Deals fails closed on a deleted row via matchNameForUser_; this one has to
  // ask, or a removed realtor keeps reading the bootcamp until the token lapses.
  if (!userStillActive_(tok.user)) return { ok: false, error: 'login required' };
  var week = (p.week === undefined || p.week === '') ? 1 : Number(p.week);
  return { ok: true, week: week, plan: getOnboarding_(week), progress: getOnboardingProgress_(tok.user, week) };
}
/* Admin review across weeks 0..4 (admin token only) */
function bootcampReview_(p) {
  var tok = (p && p.__tok) || checkToken_(p.auth || ''); if (!tok || tok.role !== 'admin') return { ok: false, error: 'admin only' };
  if (!userStillActive_(tok.user)) return { ok: false, error: 'admin only' };
  var sh = onbProgressSheet_(), m = onbProgMap_();
  var plans = {};
  [0, 1, 2, 3, 4].forEach(function (w) { try { var pl = getOnboarding_(w); if (pl && pl.days && pl.days.length) plans[w] = pl; } catch (e) {} });
  var users = {};
  if (sh && sh.getLastRow() >= 2) {
    var rng = sh.getDataRange(), rows = rng.getDisplayValues(), raw = rng.getValues();
    for (var r = 1; r < rows.length; r++) {
      var row = rows[r], u = String(row[m.user] || '').trim(); if (!u || u.indexOf('__') === 0) continue;
      var rec = users[u] || (users[u] = { user: u, prog: {}, daysSubmitted: {}, weeksSubmitted: {}, dayStart: {}, dayLast: {}, last: null });
      var tsRaw = raw[r][m.ts], tsMs = (Object.prototype.toString.call(tsRaw) === '[object Date]' && !isNaN(tsRaw)) ? tsRaw.getTime() : 0;
      if (tsMs && (rec.last === null || tsMs > rec.last)) rec.last = tsMs;
      if (row[m.wsub]) rec.weeksSubmitted[String(row[m.week])] = row[m.wsub];
      if (row[m.dsub]) rec.daysSubmitted[String(row[m.week]) + '-' + String(row[m.day])] = row[m.dsub];
      var id = String(row[m.id] || '').trim();
      if (tsMs && id.indexOf('__') !== 0) { var dkey = String(row[m.week]) + '-' + String(row[m.day]); if (!rec.dayStart[dkey] || tsMs < rec.dayStart[dkey]) rec.dayStart[dkey] = tsMs; if (!rec.dayLast[dkey] || tsMs > rec.dayLast[dkey]) rec.dayLast[dkey] = tsMs; }
      if (id && id.indexOf('__') !== 0) rec.prog[id] = { status: String(row[m.status] || ''), notes: row[m.notes] || '', proof: row[m.proof] || '' };
    }
  }
  var wkeys = Object.keys(plans).map(Number).sort(function (a, b) { return a - b; }), helpAll = [];
  var out = Object.keys(users).map(function (k) {
    var rec = users[k], blocks = [], gDone = 0, gTot = 0, uHelp = [], fullName = bootcampFullName_(rec.user) || rec.user;
    function addBlock(w, day, label, rawTasks, submitted) {
      var tasks = (rawTasks || []).filter(function (t) { return !t.goal; }); if (!tasks.length) return;
      var touched = !!submitted || tasks.some(function (t) { return rec.prog[t.id]; }); if (!touched) return;
      var mapped = tasks.map(function (t) { var pr = rec.prog[t.id] || {}; return { id: t.id, title: t.title, status: pr.status || 'pending', notes: pr.notes || '', proof: pr.proof || '' }; });
      var dn = mapped.filter(function (t) { return t.status === 'done'; }).length;
      mapped.forEach(function (t) { if (t.status === 'help') { uHelp.push({ week: w, day: day, task: t.title }); helpAll.push({ user: rec.user, name: fullName, week: w, day: day, task: t.title }); } });
      blocks.push({ label: label, week: w, day: day, total: mapped.length, done: dn, pct: Math.round(dn / mapped.length * 100), submitted: submitted, started: bootcampWhen_(rec.dayStart[w + '-' + day] || 0), updated: bootcampWhen_(rec.dayLast[w + '-' + day] || 0), tasks: mapped });
      gDone += dn; gTot += mapped.length;
    }
    wkeys.forEach(function (w) {
      var pl = plans[w];
      if (w === 0) { var allT = []; (pl.days || []).forEach(function (d) { (d.tasks || []).forEach(function (t) { allT.push(t); }); }); addBlock(0, 1, 'Onboarding', allT, rec.weeksSubmitted['0'] || ''); }
      else (pl.days || []).forEach(function (d) { addBlock(w, d.n, 'Week ' + w + ' \u00b7 Day ' + d.n, d.tasks || [], rec.daysSubmitted[w + '-' + d.n] || ''); });
    });
    return { user: rec.user, name: fullName, last: bootcampWhen_(rec.last || 0), done: gDone, total: gTot, pct: gTot ? Math.round(gDone / gTot * 100) : 0, help: uHelp.length, helpItems: uHelp, blocks: blocks };
  });
  return { ok: true, users: out, helpMap: helpAll };
}

/* ================= REALTOR HIDE-LIST =================
   Non-selling accounts (admin, ISA, Follow Up Boss) that must never appear
   in team rankings. Named for the Buyers Guide, which has been removed; the
   leaderboard still filters on it. */
var GUIDE_HIDE_ = ['rahul gupta', 'isa aurakeyrealty', 'office admin', 'pramodh chandrashekar', 'amar kaur', 'follow up boss', 'nav sodhi'];
function guideIsAdmin_(name) { return GUIDE_HIDE_.indexOf(String(name || '').trim().toLowerCase()) >= 0; }
