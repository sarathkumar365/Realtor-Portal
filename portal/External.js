/**
 * Realtor Portal — proxied external APIs: LTB, crime, schools, basement
 * Part of the Realtor Portal Apps Script project; all .gs files share one
 * global scope, so load order does not matter.
 */
/* =====================================================================
   SERVER-FETCH PAGES (external APIs, proxied) — finishes the API
   LTB search · Crime records · School address finder (4 boards)
   These reuse the portal's exact logic. Keys stay server-side.
   ===================================================================== */

/* ---------------- LTB (Ontario Open Data) ---------------- */
var LTB_RESOURCE_ID = '86e75d11-1c2c-4cd9-9b0d-9fccec302b30';
var LTB_MIN_YEAR = 2020, LTB_PAGE_SIZE = 500, LTB_API_LIMIT = 100;
var LTB_COL = {
  file:'File Number/Num\u00e9ro de dossier', apps:'Applications/Requ\u00eates', appType:'Application Type/Type de requ\u00eate',
  addr2:'Rental Unit Address//Adresse du logement locatif', complex:'Complex Address/Adresse du complexe',
  addr:'Rental Unit Address/Adresse du logement locatif', landlord:'Landlord Name/Nom du locateur',
  agent:'Landlord Agent Name/Nom du repr\u00e9sentant du locateur', tenant:'Tenant Name/Nom du locataire',
  former:'Former Tenant Name/Nom de l\u2019ancien locataire', subten:'Sub-Tenant Name/Nom du sous-locataire',
  occ:'Occupant Names/Nom de l\u2019occupant', coop:'Co-op Member Name/Nom du membre de la cooperative',
  coopNm:'Co-op Name/Nom de la cooperative', docType:'Document Type/Type de document',
  date:'Order Date/Date de l\u2019ordonnance', docId:'Document ID/Identifiant du document', dl:'ContentDownload URL/URL de t\u00e9l\u00e9chargement du contenu'
};
function getLTB_(query, offset) {
  query = String(query || '').trim();
  if (query.length < 2) return { ok: false, error: 'Enter at least 2 characters.' };
  offset = Math.max(0, parseInt(offset, 10) || 0);
  try {
    var out = [], scanned = 0, total = 0, pages = Math.ceil(LTB_PAGE_SIZE / LTB_API_LIMIT), p = 0;
    while (p++ < pages) {
      var url = 'https://data.ontario.ca/api/3/action/datastore_search?resource_id=' + encodeURIComponent(LTB_RESOURCE_ID)
        + '&q=' + encodeURIComponent(query) + '&limit=' + LTB_API_LIMIT + '&offset=' + (offset + scanned);
      var r = UrlFetchApp.fetch(url, { method: 'get', muteHttpExceptions: true });
      if (r.getResponseCode() !== 200) { if (scanned === 0) return { ok: false, error: 'Data service returned ' + r.getResponseCode() + '.' }; break; }
      var j; try { j = JSON.parse(r.getContentText()); } catch (e) { break; }
      if (!j || !j.success) break;
      total = j.result.total || 0;
      var recs = j.result.records || [];
      for (var i = 0; i < recs.length; i++) { var n = ltbNorm_(recs[i], query); if (n.year && n.year >= LTB_MIN_YEAR) out.push(n); }
      scanned += recs.length;
      if (offset + scanned >= total || recs.length < LTB_API_LIMIT) break;
    }
    var next = offset + scanned;
    return { ok: true, total: total, records: out, scannedTo: next, hasMore: next < total, offset: offset };
  } catch (e) { return { ok: false, error: String((e && e.message) || e) }; }
}
function ltbNorm_(rec, query) {
  function g(k) { var v = rec[LTB_COL[k]]; return v == null ? '' : String(v).trim(); }
  var appType = g('appType').toUpperCase(), date = g('date'), year = 0, m = date.match(/(\d{4})/); if (m) year = parseInt(m[1], 10);
  var tenant = g('tenant') || g('former') || g('subten'), address = g('addr') || g('addr2'), q = query.toLowerCase();
  var nameBlob = (g('tenant') + ' ' + g('former') + ' ' + g('subten') + ' ' + g('occ') + ' ' + g('landlord') + ' ' + g('agent') + ' ' + g('coop')).toLowerCase();
  var addrBlob = (address + ' ' + g('complex')).toLowerCase();
  return { file: g('file'), appCode: g('apps'), appType: appType, typeLabel: ltbTypeLabel_(appType, g('apps')), date: date, year: year,
    address: address, complexAddress: g('complex'), landlord: g('landlord'), agent: g('agent'), tenant: tenant, occupants: g('occ'),
    coop: g('coop'), coopName: g('coopNm'), docType: g('docType'), pdf: ltbUrl_(g('dl')), flag: appType === 'L',
    matchName: nameBlob.indexOf(q) >= 0, matchAddr: addrBlob.indexOf(q) >= 0 };
}
function ltbTypeLabel_(appType, code) { if (appType === 'L') return 'Landlord application (L)'; if (appType === 'T') return 'Tenant application (T)'; if (appType === 'C') return 'Co-op application (C)'; return code || 'Order'; }
function ltbUrl_(v) { v = String(v || ''); var m = v.match(/HYPERLINK\s*\(\s*"([^"]+)"/i); if (m) return m[1]; var u = v.match(/https?:\/\/\S+/); return u ? u[0] : ''; }

/* ---------------- CRIME (crimemaps.ca via Referer proxy) ---------------- */
var CRIME_BASE = 'https://crimemaps.ca/api/data/', CRIME_REFERER = 'https://crimemaps.ca/', CRIME_CACHE_MIN = 60;
function crimeHeaders_() { return { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36', 'Referer': CRIME_REFERER, 'Accept': 'application/json,text/plain,*/*', 'Accept-Language': 'en-US,en;q=0.9' }; }
function crimeFetchJson_(file) { var res = UrlFetchApp.fetch(CRIME_BASE + file, { headers: crimeHeaders_(), muteHttpExceptions: true, followRedirects: true }); if (res.getResponseCode() !== 200) throw new Error('crimemaps ' + file + ' -> HTTP ' + res.getResponseCode()); return JSON.parse(res.getContentText()); }
function getCrimeCity_(slug) {
  slug = String(slug || '').toLowerCase().trim(); if (!slug) return { ok: false, error: 'No city given.' };
  try {
    var cache = CacheService.getScriptCache(), ck = 'crime_city_' + slug, hit = cache.get(ck);
    if (hit) { var o = JSON.parse(hit); o.cached = true; return o; }
    var agg = crimeGetAgg_(), win = crimeGetWin_();
    var city = (agg.byCity || {})[slug] || null, wcity = win[slug] || null;
    if (!city && !wcity) return { ok: false, error: 'City "' + slug + '" not found in crime data.' };
    var out = { ok: true, slug: slug, city: city, win: wcity };
    try { cache.put(ck, JSON.stringify(out), CRIME_CACHE_MIN * 60); } catch (e) {}
    return out;
  } catch (e) { return { ok: false, error: String((e && e.message) || e) }; }
}
function getCrimeCities_() {
  try { var agg = crimeGetAgg_(), out = [], bc = agg.byCity || {}; for (var slug in bc) out.push({ slug: slug, name: bc[slug].name, province: bc[slug].province }); return { ok: true, cities: out }; }
  catch (e) { return { ok: false, error: String((e && e.message) || e), cities: [] }; }
}
function crimeGetAgg_() {
  var prop = PropertiesService.getScriptProperties(), cached = crimeReadChunked_('crime_agg'), stamp = prop.getProperty('crime_agg_stamp');
  if (cached && stamp && (Date.now() - Number(stamp) < CRIME_CACHE_MIN * 60 * 1000)) return cached;
  var data = crimeFetchJson_('aggregates.json'); try { crimeWriteChunked_('crime_agg', data); prop.setProperty('crime_agg_stamp', String(Date.now())); } catch (e) {} return data;
}
function crimeGetWin_() {
  var prop = PropertiesService.getScriptProperties(), cached = crimeReadChunked_('crime_win'), stamp = prop.getProperty('crime_win_stamp');
  if (cached && stamp && (Date.now() - Number(stamp) < CRIME_CACHE_MIN * 60 * 1000)) return cached;
  var data = crimeFetchJson_('window-city.json'); try { crimeWriteChunked_('crime_win', data); prop.setProperty('crime_win_stamp', String(Date.now())); } catch (e) {} return data;
}
/* Chunking now lives in Core.js (cachePutStr_/cacheGetStr_) and every oversized value
   in the app goes through it, so these are thin wrappers over the shared pair. */
function crimeWriteChunked_(prefix, obj) { try { cachePutStr_(prefix, JSON.stringify(obj), CRIME_CACHE_MIN * 60); } catch (e) {} }
function crimeReadChunked_(prefix) { var s = cacheGetStr_(prefix); if (!s) return null; try { return JSON.parse(s); } catch (e) { return null; } }

/* ---------------- SCHOOL ADDRESS FINDER (Peel/Halton/Durham/York) ---------------- */
var FS_YEAR = 2026, FS_SPS_BASE = 'https://api.spsplus.ca/api/v3/Search', FS_YORK_BASE = 'https://schoollocator.yrdsb.ca/ws/api';
var FS_BOARDS = {
  peel:   { id:'peel',   name:'Peel Region',   sys:'sps',  key:'00f4b315-24e5-4a05-8894-91148c612e0e', origin:'https://www.peelschools.org', locator:'https://schoolfinder.peelschools.org/' },
  halton: { id:'halton', name:'Halton Region', sys:'sps',  key:'6b72823a-348c-4f9a-a904-fa1f4736a2f4', origin:'https://www.hdsb.ca', locator:'https://www.hdsb.ca/schools/Pages/find-your-local-school.aspx' },
  durham: { id:'durham', name:'Durham Region', sys:'sps',  key:'3a8fe81d-15e9-0166-9492-2ac5fcc5f5c0', origin:'https://www.ddsb.ca', locator:'https://www.ddsb.ca/en/schools/find-your-school.aspx' },
  york:   { id:'york',   name:'York Region',   sys:'york', key:'WLxv!Z3R96Q#CUc!', origin:'https://schoollocator.yrdsb.ca', locator:'https://schoollocator.yrdsb.ca/' }
};
function fsBoards_() { var out = []; for (var k in FS_BOARDS) { var b = FS_BOARDS[k]; if (b.sys === 'link' || b.key) out.push({ id: b.id, name: b.name, needsNumber: b.sys === 'york', linkOnly: b.sys === 'link', url: b.url || '', locator: b.locator || '' }); } return out; }
function fsSpsHeaders_(b) { return { 'x-api-key': b.key, 'x-api-version': '3.0', 'Origin': b.origin }; }
function fsPick_(o, names) { if (!o) return ''; for (var i = 0; i < names.length; i++) if (o[names[i]] != null) return o[names[i]]; var low = {}; for (var k in o) low[k.toLowerCase()] = o[k]; for (var j = 0; j < names.length; j++) { var v = low[String(names[j]).toLowerCase()]; if (v != null) return v; } return ''; }
function fsFetchJson_(url, opts, retries) { retries = retries || 1; for (var i = 0; i <= retries; i++) { try { var r = UrlFetchApp.fetch(url, opts), code = r.getResponseCode(); if (code >= 200 && code < 300) { var t = r.getContentText(); if (!t) { Utilities.sleep(250); continue; } var j = JSON.parse(t); if (Array.isArray(j) && j.length === 0 && i < retries) { Utilities.sleep(250); continue; } return j; } } catch (e) {} if (i < retries) Utilities.sleep(250); } return null; }
function fsExpandAddr_(a) {
  a = String(a || '');
  var END = '(?=\\s*(?:[NSEW]{1,2}\\b\\s*)?(?:,|$))';   // last token of street part, allowing an optional N/S/E/W
  var map = [['St','Street'],['Rd','Road'],['Ave','Avenue'],['Av','Avenue'],['Dr','Drive'],['Blvd','Boulevard'],
    ['Cres','Crescent'],['Cresc','Crescent'],['Crt','Court'],['Ct','Court'],['Pl','Place'],['Ln','Lane'],
    ['Hwy','Highway'],['Trl','Trail'],['Terr','Terrace'],['Ter','Terrace'],['Sq','Square'],['Cir','Circle'],
    ['Circ','Circle'],['Pkwy','Parkway'],['Gdns','Gardens'],['Gdn','Gardens'],['Grv','Grove'],['Hts','Heights'],['Way','Way']];
  for (var i = 0; i < map.length; i++) {
    a = a.replace(new RegExp('\\b' + map[i][0] + '\\.?' + END, 'gi'), map[i][1]);
  }
  return a.replace(/\s+/g, ' ').trim();
}
function fsSuggest_(boardId, text) {
  text = fsExpandAddr_(text); if (text.length < 3) return []; var b = FS_BOARDS[boardId]; if (!b) return [];
  if (b.sys === 'sps') { var res = fsFetchJson_(FS_SPS_BASE + '/SuggestAddresses?searchText=' + encodeURIComponent(text), { method: 'get', headers: fsSpsHeaders_(b), muteHttpExceptions: true }, 2) || []; return res.map(function (a) { return { id: String(fsPick_(a, ['addressId', 'id'])), label: String(fsPick_(a, ['displayAddress', 'address', 'fullAddress'])) }; }).filter(function (a) { return a.label; }); }
  if (b.sys === 'york') { var res2 = fsFetchJson_(FS_YORK_BASE + '/AddressLists', { method: 'post', contentType: 'application/json', headers: { 'apikey_0': b.key }, payload: JSON.stringify({ name: text }), muteHttpExceptions: true }, 1) || []; return res2.map(function (a) { return { id: '', label: String(fsPick_(a, ['streetAndMunicipality', 'address', 'display'])) }; }).filter(function (a) { return a.label; }); }
  return [];
}
function fsLookup_(boardId, fullAddress, houseNumber) {
  var b = FS_BOARDS[boardId]; if (!b) return { ok: false, error: 'Unknown region.' };
  if (b.sys === 'link') return { ok: true, board: b.name, linkOnly: true, link: b.url, schools: [] };
  fullAddress = fsExpandAddr_(fullAddress); if (fullAddress.length < 4) return { ok: false, error: 'Enter a full address.' };
  try {
    if (b.sys === 'sps') {
      var sug = fsFetchJson_(FS_SPS_BASE + '/SuggestAddresses?searchText=' + encodeURIComponent(fullAddress), { method: 'get', headers: fsSpsHeaders_(b), muteHttpExceptions: true }, 2) || [];
      if (!sug.length) return { ok: false, error: 'That address wasn\u2019t found in ' + b.name + '.' };
      var best = fsBestMatch_(sug, fullAddress), addressId = String(fsPick_(best, ['addressId', 'id']));
      if (!addressId) return { ok: false, error: 'Could not resolve that address.' };
      var schools = fsSpsSchools_(b, addressId); fsAttachRank_(schools);
      return { ok: true, board: b.name, matched: String(fsPick_(best, ['displayAddress', 'address'])) || fullAddress, schools: schools };
    }
    if (b.sys === 'york') {
      var p = fsParseAddress_(fullAddress, houseNumber); if (!p.street) return { ok: false, error: 'Enter a street name.' };
      var schools2 = fsYorkSchools_(b, p.street + ', ' + p.municipality, p.number); fsAttachRank_(schools2);
      return { ok: true, board: b.name, matched: fullAddress, schools: schools2 };
    }
  } catch (e) { return { ok: false, error: String((e && e.message) || e) }; }
  return { ok: false, error: 'Unsupported region.' };
}
function fsSchools_(boardId, addressId, addressLabel, houseNumber) {
  var b = FS_BOARDS[boardId]; if (!b) return { ok: false, error: 'Unknown region.' };
  if (b.sys === 'link') return { ok: true, board: b.name, linkOnly: true, link: b.url, schools: [] };
  var schools;
  try { if (b.sys === 'sps') schools = fsSpsSchools_(b, addressId); else if (b.sys === 'york') schools = fsYorkSchools_(b, addressLabel, houseNumber); else return { ok: false, error: 'Unsupported region.' }; }
  catch (e) { return { ok: false, error: String((e && e.message) || e) }; }
  fsAttachRank_(schools); return { ok: true, board: b.name, schools: schools };
}
function fsBestMatch_(list, text) { var t = String(text || '').toLowerCase().replace(/\s+/g, ' ').trim(); for (var i = 0; i < list.length; i++) { var d = String(fsPick_(list[i], ['displayAddress', 'address'])).toLowerCase().replace(/\s+/g, ' ').trim(); if (d === t) return list[i]; } for (var j = 0; j < list.length; j++) { var d2 = String(fsPick_(list[j], ['displayAddress', 'address'])).toLowerCase(); if (d2 && (d2.indexOf(t) >= 0 || t.indexOf(d2) >= 0)) return list[j]; } return list[0]; }
function fsParseAddress_(full, houseNumber) { var parts = String(full || '').split(','), first = String(parts[0] || '').trim(), municipality = parts.slice(1).join(',').trim(); var num = String(houseNumber || '').trim(), street = first, m = first.match(/^\s*(\d+[A-Za-z]?)\s+(.+)$/); if (m) { if (!num) num = m[1]; street = m[2].trim(); } return { number: num, street: street, municipality: municipality }; }
function fsSpsSchools_(b, addressId) {
  addressId = String(addressId || '').trim(); if (!addressId) return [];
  var near = fsFetchJson_(FS_SPS_BASE + '/GetSchoolListByAddress?addressId=' + encodeURIComponent(addressId) + '&schoolYear=' + FS_YEAR, { method: 'get', headers: fsSpsHeaders_(b), muteHttpExceptions: true }, 2) || [];
  if (!near.length) return [];
  var dir = fsSpsDirectory_(b), out = [], seen = {};
  function pushRow_(sid, code, name, ranges, gLow, gHigh, full) {
    var track = fsTrack_(name || code, '', []); if (!track) return;
    var grades = fsGradeRanges_(ranges); if (!grades && (gLow || gHigh)) grades = fsCleanGrades_((gLow || '?') + '-' + (gHigh || '?'));
    var coords = fsParseGeo_(fsPick_(full, ['locationGeoJson', 'geoJson', 'location']));
    var norm = fsNormalize_({ name: fsPick_(full, ['schoolName', 'name']) || '', program: track, grades: grades, address: fsPick_(full, ['address1', 'address']), city: fsPick_(full, ['city', 'municipalityName']), community: fsPick_(full, ['municipalityName', 'city']), postal: fsPick_(full, ['postalCode', 'postal']), phone: fsPick_(full, ['phoneNumber', 'phone']), principal: fsPick_(full, ['principalName']), type: fsPick_(full, ['schoolTypeName', 'schoolType']), lat: coords.lat, lng: coords.lng, board: b.name });
    norm.track = track; var key = (String(sid) + '|' + track + '|' + norm.grades).toUpperCase(); if (seen[key]) return; seen[key] = norm; out.push(norm);
  }
  for (var i = 0; i < near.length; i++) {
    var n = near[i], sid = String(fsPick_(n, ['schoolId', 'id'])), full = dir[sid] || n, pts = fsPick_(n, ['programTypes']);
    if (pts && pts.length) { for (var pp = 0; pp < pts.length; pp++) { var pt = pts[pp]; pushRow_(sid, fsPick_(pt, ['programTypeCode']), fsPick_(pt, ['programTypeName', 'name']), fsPick_(pt, ['gradeRanges']), '', '', full); } }
    else pushRow_(sid, fsPick_(n, ['programTypeCode']), fsPick_(n, ['programTypeName']), fsPick_(n, ['gradeRanges']), fsPick_(n, ['gradeLow']), fsPick_(n, ['gradeHigh']), full);
  }
  return out;
}
function fsGradeRanges_(ranges) { if (!ranges || !ranges.length) return ''; var lows = [], highs = []; for (var i = 0; i < ranges.length; i++) { var lo = fsPick_(ranges[i], ['low', 'lowGrade', 'from']), hi = fsPick_(ranges[i], ['high', 'highGrade', 'to']); if (lo !== '') lows.push(String(lo)); if (hi !== '') highs.push(String(hi)); } if (!lows.length && !highs.length) return ''; return fsCleanGrades_((lows[0] || '?') + '-' + (highs[highs.length - 1] || '?')); }
function fsGrades_(n, full) { var names = ['grades', 'gradeRange', 'gradeLevel', 'gradeLevels', 'gradesRange', 'gradeRangeText', 'grade', 'gradesText', 'gradesTaught', 'gradeSpan', 'gradeCategory']; var g = String(fsPick_(n, names) || fsPick_(full, names) || '').trim(); if (g) return fsCleanGrades_(g); var loN = ['lowGrade', 'gradeLow', 'gradeFrom', 'minGrade', 'startGrade', 'fromGrade', 'gradeStart'], hiN = ['highGrade', 'gradeHigh', 'gradeTo', 'maxGrade', 'endGrade', 'toGrade', 'gradeEnd']; var lo = String(fsPick_(n, loN) || fsPick_(full, loN) || '').trim(), hi = String(fsPick_(n, hiN) || fsPick_(full, hiN) || '').trim(); if (lo || hi) return fsCleanGrades_((lo || '?') + '-' + (hi || '?')); return ''; }
function fsCleanGrades_(g) { g = String(g).toUpperCase().replace(/GRADE[S]?/g, '').replace(/\s*TO\s*/g, '-').replace(/\s+/g, ' ').trim(); g = g.replace(/\bJUNIOR\s*KINDERGARTEN\b|\bJUNIOR\s*K\b/g, 'JK').replace(/\bSENIOR\s*KINDERGARTEN\b|\bSENIOR\s*K\b/g, 'SK').replace(/\bKINDERGARTEN\b/g, 'K'); return g.replace(/\s*-\s*/g, '-'); }
function fsTrack_(program, name, programs) { var p = String(program || '').toUpperCase(); if (/EXTENDED\s*FRENCH|\bEF\b/.test(p)) return 'Extended French Track'; if (/FRENCH\s*IMMERSION|\bFI\b|IMMERSION/.test(p)) return 'French Immersion Track'; if (/GIFTED|ENRICH/.test(p)) return 'Gifted / Enriched'; if (/REGULAR|ENGLISH|CORE|\bRT\b|\bDUAL\b/.test(p)) return 'Regular Track'; if (String(program || '').trim()) return String(program).trim(); if (programs && programs.indexOf('French Immersion') >= 0) return 'French Immersion'; return 'Regular Track'; }
function fsSpsDirectory_(b) { var ck = 'fsdir_' + b.id, hit = cacheReadBig_(ck); if (hit) { try { return JSON.parse(hit); } catch (e) {} } var list = fsFetchJson_(FS_SPS_BASE + '/GetSchoolList?schoolYear=' + FS_YEAR, { method: 'get', headers: fsSpsHeaders_(b), muteHttpExceptions: true }, 2) || []; var byId = {}; for (var i = 0; i < list.length; i++) { var s = list[i], sid = fsPick_(s, ['schoolId', 'id']); if (s && sid !== '') byId[String(sid)] = s; } try { cacheWriteBig_(ck, JSON.stringify(byId), 21600); } catch (e) {} return byId; }
function fsParseGeo_(g) { try { var a = JSON.parse(g); if (typeof a === 'string') a = JSON.parse(a); if (a && a.coordinates) a = a.coordinates; if (a && a.length >= 2) return { lng: Number(a[0]), lat: Number(a[1]) }; } catch (e) {} return { lat: '', lng: '' }; }
function fsYorkSchools_(b, addressLabel, houseNumber) {
  var parts = String(addressLabel || '').split(','), streetName = String(parts[0] || '').trim(), municipality = parts.slice(1).join(',').trim(); if (!streetName) return [];
  var body = { streetName: streetName, streetNumber: String(houseNumber || '').trim(), municipality: municipality, elementary_flag: true, secondary_flag: true, elem_fi_flag: true, sec_fi_flag: true, sec_art_flag: true, ib_flag: true, ifReturnSchoolYear: true };
  var res = fsFetchJson_(FS_YORK_BASE + '/SchoolsProfiles', { method: 'post', contentType: 'application/json', headers: { 'apikey_0': b.key }, payload: JSON.stringify(body), muteHttpExceptions: true }, 1) || [];
  var out = [];
  for (var i = 0; i < res.length; i++) { var s = res[i], phone = [fsPick_(s, ['area_code', 'areaCode']), fsPick_(s, ['phone_no', 'phoneNo', 'phone'])].filter(function (x) { return x; }).join('-'); var prog = []; if (fsPick_(s, ['elem_fi_flag', 'sec_fi_flag'])) prog.push('FI'); if (fsPick_(s, ['ib_flag'])) prog.push('IB'); if (fsPick_(s, ['sec_art_flag'])) prog.push('Arts'); out.push(fsNormalize_({ name: fsPick_(s, ['school_name', 'schoolName', 'name']), address: fsPick_(s, ['school_address', 'address']), phone: phone, grades: fsGrades_(s, s), lat: fsPick_(s, ['latitude', 'lat']), lng: fsPick_(s, ['longitude', 'lng']), type: fsPick_(s, ['school_type_code', 'schoolTypeCode', 'type']), program: prog.join(' '), board: b.name })); }
  return out;
}
function fsNormalize_(s) { var grades = fsCleanGrades_(s.grades || ''); return { school: String(s.name || '').trim(), address: String(s.address || '').trim(), city: String(s.city || '').trim(), postal: String(s.postal || '').trim(), phone: String(s.phone || '').trim(), principal: String(s.principal || '').trim(), grades: grades, level: fsLevel_(grades, s.name), type: fsType_(s.type, s.name), programs: fsPrograms_(s.program, s.name), track: fsTrack_(s.program, s.name, fsPrograms_(s.program, s.name)), board: String(s.board || '').trim(), lat: s.lat, lng: s.lng, community: String(s.community || '').trim(), rank: '', score: '' }; }
function fsLevel_(grades, name) { var g = ' ' + String(grades || '').toUpperCase() + ' ', n = String(name || '').toUpperCase(); var gHigh = /\b(9|10|11|12)\b/.test(g), gElem = /\b(JK|SK|K|1|2|3|4|5|6|7|8)\b/.test(g); var hasHigh = gHigh || (!gElem && /SECONDARY|\bHIGH\b|\bH\.?S\.?\b|\bS\.?S\.?\b|\bC\.?I\.?\b|COLLEGIATE|\bACADEMY\b/.test(n)); var hasElem = gElem || (!gHigh && /ELEMENTARY|PUBLIC SCHOOL|\bP\.?S\.?\b/.test(n)); if (hasHigh && hasElem) return 'Intermediate'; if (hasHigh) return 'Secondary'; return 'Elementary'; }
function fsType_(t, name) { var s = (String(t || '') + ' ' + String(name || '')).toUpperCase(); if (s.indexOf('CATHOLIC') >= 0 || /\bST\.?\b|\bSAINT\b|\bHOLY\b|OUR LADY|\bPOPE\b|\bBLESSED\b/.test(s)) return 'Catholic'; if (s.indexOf('PRIVATE') >= 0 || s.indexOf('INDEPENDENT') >= 0) return 'Private'; if (s.indexOf('FRENCH') >= 0 && s.indexOf('IMMERSION') < 0) return 'French'; return 'Public'; }
function fsPrograms_(program, name) { var s = (String(program || '') + ' ' + String(name || '')).toUpperCase(), out = []; if (/FRENCH IMMERSION|\bFI\b|IMMERSION/.test(s)) out.push('French Immersion'); if (/\bIB\b|INTERNATIONAL BACC/.test(s)) out.push('IB'); if (/\bARTS?\b|\bSTEM\b|\bAP\b/.test(s)) out.push('Arts / Specialty'); return out; }
function fsNormName_(s) { return String(s || '').toUpperCase().replace(/\b(CATHOLIC|PUBLIC|ELEMENTARY|SECONDARY|SCHOOL|SENIOR|JUNIOR|SR|JR|MIDDLE|ACADEMY|P\.?S\.?|C\.?S\.?|S\.?S\.?|E\.?S\.?|C\.?I\.?|H\.?S\.?)\b/g, ' ').replace(/[^A-Z0-9]+/g, ' ').trim(); }
function fsAttachRank_(schools) { if (!schools || !schools.length) return; var rank = {}; try { var res = readTab_('School Rankings', 'main', ''); var rows = (res && res.rows) ? res.rows : []; for (var i = 0; i < rows.length; i++) { var nm = rows[i].SCHOOL || rows[i].School || rows[i].school; var k = fsNormName_(nm); if (k && !rank[k]) rank[k] = rows[i]; } } catch (e) {} for (var j = 0; j < schools.length; j++) { var m = rank[fsNormName_(schools[j].school)]; if (m) { schools[j].rank = m.RANK || m.rank || ''; schools[j].score = m.SCORE || m.score || ''; schools[j].community = m.COMMUNITY || m.community || ''; if (!schools[j].city) schools[j].city = m.CITY || m.city || ''; } } }

/* Big-cache helpers for the school directory — same shared chunking as everything else. */
function cacheWriteBig_(key, str, ttl) { try { cachePutStr_(key, str, ttl || 21600); } catch (e) {} }
function cacheReadBig_(key) { return cacheGetStr_(key); }

/* =====================================================================
   BASEMENT CHECK — municipal registration lookup (agent-facing)
   Output is a CLIENT SCRIPT, never a legal verdict. "Legal" is never used.
   Tier A live ArcGIS: Brampton + Oshawa (same adapter, different config).
   Other cities: PERMIT_ON_FILE (Toronto/Vaughan) or NOT_COVERED.
   ===================================================================== */
var BC_CFG = {
  brampton: { name: 'Brampton', tier: 'A', kind: 'arcgis', itemId: '7d9df6528d474b43b6771cb7feefc35e', layer: 0,
              source: 'Brampton GeoHub — Registered Additional Residential Units', asOf: 'updated daily' },
  oshawa:   { name: 'Oshawa', tier: 'A', kind: 'arcgis', serviceUrl: 'https://opendata.arcgis.com/datasets/97d92126eeae4430885d6225df0ff2a0_0/FeatureServer/0', addrField: 'Property_Address', dateFields: { 'Certificate issued': 'Date_Certificate_was_Issued' },
              source: 'Oshawa Open Data — Registered Two Unit Apartments', asOf: 'from the City Land Information System' },
  mississauga: { name: 'Mississauga', tier: 'B', kind: 'sheet', tab: 'Mississauga Second Units', addrCol: 'ADDRESS', wardCol: 'WARD', listDate: '2026-03-08', source: 'Mississauga Second Units Registry (City-published list)', asOf: 'list published 2026-03-08' },
  toronto:  { name: 'Toronto', tier: 'C', kind: 'permit', source: 'Toronto building permits (Second Suite)' },
  vaughan:  { name: 'Vaughan', tier: 'C', kind: 'permit', source: 'Vaughan permit records' }
};
var BC_NOT_COVERED_CITIES = ['barrie','milton','halton hills','pickering','whitby','markham','richmond hill','burlington','caledon','oakville','ajax','kitchener','waterloo','cambridge'];

function bcCityFromAddr_(addr) {
  var a = String(addr || '').toLowerCase();
  for (var slug in BC_CFG) { if (a.indexOf(BC_CFG[slug].name.toLowerCase()) >= 0) return slug; }
  for (var i = 0; i < BC_NOT_COVERED_CITIES.length; i++) if (a.indexOf(BC_NOT_COVERED_CITIES[i]) >= 0) return BC_NOT_COVERED_CITIES[i];
  return '';
}
/* Resolve an ArcGIS item's FeatureServer query URL (cached). */
var BC_TYPES = /^(ST|STREET|RD|ROAD|AVE|AV|AVENUE|DR|DRIVE|BLVD|BOULEVARD|CRES|CRESC|CRESCENT|CRT|CT|COURT|PL|PLACE|LN|LANE|HWY|HIGHWAY|TRL|TRAIL|TER|TERR|TERRACE|SQ|SQUARE|CIR|CIRC|CIRCLE|PKWY|PARKWAY|GDNS|GDN|GARDENS|GRV|GROVE|HTS|HEIGHTS|WAY|CLOSE|GATE|MEWS|GREEN|PATH|RUN|RIDGE|HILL|HOLLOW|VIEW|VALE|WALK|LANDING|CROSSING|COMMON|COMMONS|BAY|CIRCUIT)$/;
function bcNeedle_(address) {
  var first = String(address || '').split(',')[0].toUpperCase().replace(/[.,#]/g, ' ');
  first = first.replace(/\b(UNIT|APT|SUITE|STE|BSMT|BASEMENT|LOWER|UPPER|MAIN)\b.*$/, '').replace(/\s+/g, ' ').trim();
  var toks = first.split(/\s+/).filter(Boolean);
  while (toks.length > 2 && /^[NSEW]{1,2}$/.test(toks[toks.length - 1])) toks.pop();
  while (toks.length > 2 && BC_TYPES.test(toks[toks.length - 1])) toks.pop();
  /* The result is concatenated into a SQL LIKE pattern, so the wildcards matter
     as much as the quote: a bare "%" matches every row and turns one address
     lookup into a dump of the whole municipal registry. */
  return toks.join(' ').replace(/'/g, "''").replace(/[%_]/g, ' ').replace(/\s+/g, ' ').trim();
}
function bcLayerUrl_(cfg) {
  if (cfg.serviceUrl) return cfg.serviceUrl;
  var ck = 'bc_lurl3_' + cfg.itemId, hit = cacheGet_(ck); if (hit && hit.url) return hit.url;
  var meta = UrlFetchApp.fetch('https://www.arcgis.com/sharing/rest/content/items/' + cfg.itemId + '?f=json', { muteHttpExceptions: true });
  if (meta.getResponseCode() !== 200) throw new Error('item meta ' + meta.getResponseCode());
  var j = JSON.parse(meta.getContentText()), base = String((j && j.url) || ''); if (!base) throw new Error('no service url on item');
  base = base.replace(/\/+$/, '');
  var layerUrl = /\/\d+$/.test(base) ? base : (base + '/' + (cfg.layer || 0));
  cachePut_(ck, { url: layerUrl }); return layerUrl;
}
function bcMeta_(cfg, layerUrl) {
  var ck = 'bc_meta3_' + cfg.itemId, hit = cacheGet_(ck); if (hit && hit.fields) return hit;
  var r = UrlFetchApp.fetch(layerUrl + '?f=json', { muteHttpExceptions: true }), out = { fields: [], display: '' };
  try {
    var j = JSON.parse(r.getContentText()); if (j && j.error) throw new Error(j.error.message || 'meta error');
    out.display = String(j.displayField || '');
    var fields = j.fields || [];
    for (var i = 0; i < fields.length; i++) { var f = fields[i], nm = String(f.name || ''); if (f.type !== 'esriFieldTypeString') continue; if (/globalid|guid|shape|geometry|email|www/i.test(nm)) continue; out.fields.push(nm); }
  } catch (e) { out.error = String((e && e.message) || e); }
  cachePut_(ck, out); return out;
}
function bcSearchFields_(meta, cfg) {
  if (cfg && cfg.addrField) return [cfg.addrField];
  var addr = meta.fields.filter(function (n) { return /addr|address|civic|street|location|fulladdr/i.test(n); });
  if (!addr.length && meta.display && meta.fields.indexOf(meta.display) >= 0) addr = [meta.display];
  if (!addr.length) addr = meta.fields.slice(0, 14);
  return addr;
}
function bcArcgisLookup_(cfg, address) {
  var layerUrl = bcLayerUrl_(cfg), meta = bcMeta_(cfg, layerUrl), fields = bcSearchFields_(meta, cfg), needle = bcNeedle_(address);
  var dbg = { layerUrl: layerUrl, display: meta.display, fields: fields, metaError: meta.error || '' };
  if (!needle || !fields.length) return { matched: false, records: [], where: '', _dbg: dbg };
  var where = '(' + fields.map(function (f) { return "UPPER(" + f + ") LIKE '%" + needle + "%'"; }).join(' OR ') + ')';
  var url = layerUrl + '/query?where=' + encodeURIComponent(where) + '&outFields=*&returnGeometry=false&f=json';
  var r = UrlFetchApp.fetch(url, { muteHttpExceptions: true }); if (r.getResponseCode() !== 200) throw new Error('arcgis query ' + r.getResponseCode());
  var j = JSON.parse(r.getContentText()); if (j && j.error) throw new Error('arcgis: ' + (j.error.message || JSON.stringify(j.error)));
  var feats = (j && j.features) || []; dbg.where = where; dbg.count = feats.length;
  return { matched: feats.length > 0, records: feats.map(function (f) { return f.attributes; }), where: where, _dbg: dbg };
}

/* Tier B (Mississauga): match against a Google Sheet tab holding the City-published list. */
function bcSheetLookup_(cfg, address) {
  var ss = ssFor_('main');
  var sh = ss.getSheetByName(cfg.tab);
  if (!sh) { var all = ss.getSheets(); for (var i=0;i<all.length && !sh;i++){ if (all[i].getName().toUpperCase().indexOf('MISSISSAUGA')>=0 && all[i].getName().toUpperCase().indexOf('UNIT')>=0) sh=all[i]; } }
  if (!sh || sh.getLastRow() < 2) return { matched:false, records:[], _dbg:{ error:'tab not found: '+cfg.tab } };
  var vals = sh.getDataRange().getDisplayValues();
  var hdr = vals[0].map(function(h){ return String(h||'').trim().toUpperCase(); });
  var ai = hdr.indexOf(String(cfg.addrCol||'ADDRESS').toUpperCase()); if (ai<0) ai=0;
  var wi = hdr.indexOf(String(cfg.wardCol||'WARD').toUpperCase());
  var needle = bcNeedle_(address).replace(/''/g,"'");
  if (!needle) return { matched:false, records:[], _dbg:{ needle:needle } };
  for (var r=1;r<vals.length;r++){
    var raw = String(vals[r][ai]||'').toUpperCase().replace(/[.,#]/g,' ').replace(/\s+/g,' ').trim();
    if (!raw) continue;
    if (raw.indexOf(needle)===0 || raw.indexOf(' '+needle)>=0 || raw===needle || raw.indexOf(needle+' ')===0){
      var rec = { 'Address on file': vals[r][ai] }; if (wi>=0) rec['Ward']=vals[r][wi];
      return { matched:true, records:[rec], _dbg:{ needle:needle, tab:cfg.tab } };
    }
  }
  return { matched:false, records:[], _dbg:{ needle:needle, tab:cfg.tab } };
}
function bcScript_(status, cityName, cfg, rec) {
  var S = {
    REGISTERED: {
      colour: 'pine', label: 'Registered',
      say: 'I checked ' + cityName + '\u2019s registry and this address shows a registered additional unit on file, with the record dated as shown. That\u2019s the strongest confirmation the City provides, so we can treat the second unit as an established, on-file unit when we run the numbers \u2014 while still getting the paperwork through your lawyer.',
      next: ['Ask the seller for the registration certificate and any final inspection.', 'Have your lawyer confirm the record on closing.', 'You can factor the unit into affordability with reasonable confidence.']
    },
    PERMIT_ON_FILE: {
      colour: 'ochre', label: 'Permit on file',
      say: cityName + ' doesn\u2019t publish a registry of second units \u2014 nobody can look that up. What I can see is a building-permit record for a second suite at this address, which is good evidence but not the same as a registration. I\u2019d want the permit and final inspection documents before we treat it as an established unit.',
      next: ['Ask for the permit number and final inspection sign-off.', 'Order a building-records search through your lawyer.', 'Don\u2019t describe the unit as established in writing until the permit is confirmed.']
    },
    NO_RECORD: {
      colour: 'grey', label: 'No record',
      say: 'I checked ' + cityName + '\u2019s registry and there\u2019s no registration on file for this address. That doesn\u2019t automatically mean the basement is a problem \u2014 it might be family use, built before registration was required, or simply never registered. But it does mean we can\u2019t treat it as an established rental unit when we run the numbers.',
      next: ['Don\u2019t use rental income in the affordability math yet.', 'Ask the seller directly whether it was ever registered.', 'Price the cost of registering it into your offer.']
    },
    NOT_COVERED: {
      colour: 'grey', label: 'Not covered',
      say: cityName + ' doesn\u2019t publish a searchable registry, so there\u2019s nothing for me to look up here \u2014 no result either way. The only reliable answer comes from the City or Town directly, so I\u2019ll put that in as a condition rather than guess.',
      next: ['Add a condition to confirm the unit\u2019s status with the municipality.', 'Ask the seller for any registration or permit paperwork they hold.', 'Don\u2019t rely on rental income until it\u2019s confirmed in writing.']
    },
    AMBIGUOUS: {
      colour: 'blue', label: 'Needs a precise address',
      say: 'That address didn\u2019t resolve to a single property, so I don\u2019t want to give you a false read. Give me the full street address with the city and I\u2019ll check the registry again.',
      next: ['Re-enter the full address including the city.', 'Include the exact house number.']
    }
  };
  var s = S[status] || S.NOT_COVERED;
  var ev = { Source: cfg ? cfg.source : (cityName + ' \u2014 no registry'), Tier: cfg ? ('Tier ' + cfg.tier) : 'Not covered' };
  if (rec) { for (var k in rec) { if (rec[k] != null && String(rec[k]).length && !/geom|shape|objectid|_id|hash/i.test(k)) ev[k] = rec[k]; } }
  return { status: status, statusLabel: s.label, colour: s.colour, say: s.say, next: s.next, evidence: ev };
}

/* Internals — generated SQL, layer URLs, raw exception text — are useful in the
   editor's log and nowhere else. Returning them to the client hands a caller the
   field list to iterate, and for cached actions writes them to every phone. */
function stripDbg_(o) {
  if (!o || typeof o !== 'object') return o;
  delete o._dbg; delete o._debug;
  if (o.records && o.records.length) for (var i = 0; i < o.records.length; i++) stripDbg_(o.records[i]);
  return o;
}
function getBasement_(address) {
  address = String(address || '').trim();
  if (address.length < 4) return { ok: false, error: 'Enter a full address, including the city (e.g. 41 Fanshawe Cres, Brampton).' };
  var slug = bcCityFromAddr_(address), cityName = '';
  try {
    if (slug && BC_CFG[slug]) {
      var cfg = BC_CFG[slug]; cityName = cfg.name;
      if (cfg.kind === 'arcgis') {
        try {
          var res = bcArcgisLookup_(cfg, address);
          var out = bcScript_(res.matched ? 'REGISTERED' : 'NO_RECORD', cityName, cfg, res.matched ? res.records[0] : null);
          out.ok = true; out.city = cityName; out.matched = res.matched; out.count = res.records.length; out.query = bcNeedle_(address);
          out._debug = res._dbg; return out;
        } catch (ee) {
          var soft = bcScript_('AMBIGUOUS', cityName, cfg, null);
          soft.ok = true; soft.city = cityName; soft.statusLabel = 'Temporarily unavailable';
          soft.say = 'I couldn\u2019t reach ' + cityName + '\u2019s registry just now. Let\u2019s confirm this one directly with the City rather than guess.';
          soft.next = ['Try again in a moment.', 'If it persists, confirm the unit\u2019s status with the City directly.'];
          soft._debug = { error: String((ee && ee.message) || ee) };
          return soft;
        }
      }
      if (cfg.kind === 'sheet') {
        var sres = bcSheetLookup_(cfg, address);
        var so = bcScript_(sres.matched ? 'REGISTERED' : 'NO_RECORD', cityName, cfg, sres.matched ? sres.records[0] : null);
        if (sres.matched) so.evidence['List published'] = cfg.listDate || '';
        so.ok = true; so.city = cityName; so.matched = sres.matched; so.count = sres.matched?1:0; so.query = bcNeedle_(address); so._debug = sres._dbg; return so;
      }
      if (cfg.kind === 'permit') { var o1 = bcScript_('PERMIT_ON_FILE', cityName, cfg, null); o1.ok = true; o1.city = cityName; return o1; }
      // tier B (PDF) not live yet -> not covered, honest
      var o2 = bcScript_('NOT_COVERED', cityName, cfg, null); o2.ok = true; o2.city = cityName; return o2;
    }
    // known not-covered city
    if (slug) { var nm = slug.replace(/\b\w/g, function (c) { return c.toUpperCase(); }); var o3 = bcScript_('NOT_COVERED', nm, null, null); o3.ok = true; o3.city = nm; return o3; }
    // city not recognised in the address
    var amb = bcScript_('AMBIGUOUS', 'This address', null, null); amb.ok = true; amb.city = ''; return amb;
  } catch (e) {
    return { ok: false, error: String((e && e.message) || e), city: cityName };
  }
}
/* Coverage list for the UI (tier-grouped). */
function getBasementCoverage_() {
  return { ok: true, tiers: [
    { tier: 'A', label: 'Live city registry \u2014 checks instantly', cities: ['Brampton', 'Oshawa'] },
    { tier: 'C', label: 'Building permits only \u2014 no registry', cities: ['Toronto', 'Vaughan'] },
    { tier: 'B', label: 'Registry published as a file \u2014 not yet live', cities: ['Mississauga'] },
    { tier: 'D/E', label: 'No public registry \u2014 confirm with the municipality', cities: ['Barrie', 'Milton', 'Halton Hills', 'Pickering', 'Whitby', 'Markham', 'Richmond Hill', 'Burlington', 'Caledon', 'Oakville', 'Ajax', 'Kitchener', 'Waterloo', 'Cambridge'] }
  ] };
}
