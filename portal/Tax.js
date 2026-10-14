/**
 * Realtor Portal — property tax rates
 * Part of the Realtor Portal Apps Script project; all .gs files share one
 * global scope, so load order does not matter.
 *
 * Ontario residential (RT) rates, read from two tabs on the main spreadsheet:
 *
 *   'Property Tax Rates'  the history. One row per municipality, per rate area,
 *                         per tax year. Never overwritten.
 *   'Active Rates'        the rate to serve today. 2026 where it exists,
 *                         otherwise the 2025 row, resolved in the sheet itself.
 *
 * One action, `taxrates`, feeds two screens: the Property Tax list and the
 * Home Expenses municipality picker. The 45-municipality table inside AKX stays
 * as the offline fallback, so the calculator still works when the sheet is
 * unreachable — this payload corrects it rather than replacing it.
 */

var PT_TAB_ACTIVE = 'Active Rates';
var PT_TAB_HIST = 'Property Tax Rates';

/* Tab names are matched loosely after an exact miss, the same way
   bcSheetLookup_ falls back, so a rename that only changes case or spacing
   does not take the screen down. */
function ptTab_(name) {
  var ss = ssFor_('main'), sh = ss.getSheetByName(name);
  if (sh) return sh;
  var want = String(name).toUpperCase().replace(/[^A-Z0-9]/g, ''), all = sheetsFor_('main');
  for (var i = 0; i < all.length; i++) {
    if (all[i].getName().toUpperCase().replace(/[^A-Z0-9]/g, '') === want) return all[i];
  }
  return null;
}
/* Header keys are normalised to letters and digits so 'Rate Area', 'rate_area'
   and 'RATE AREA' all bind to the same column. */
function ptCols_(hdr) {
  var m = {};
  for (var c = 0; c < hdr.length; c++) {
    var k = String(hdr[c] || '').toLowerCase().replace(/[^a-z0-9]/g, '');
    if (k && m[k] === undefined) m[k] = c;
  }
  return m;
}
function ptG_(row, cols, key) { var i = cols[key]; return (i === undefined || i < 0) ? '' : row[i]; }
function ptStr_(v) { return String(v == null ? '' : v).trim(); }
function ptNum_(v) {
  if (v === '' || v == null) return null;
  var n = parseFloat(String(v).replace(/[^0-9.\-]/g, ''));
  return isFinite(n) ? n : null;
}
/* The sheet's yes/no columns are hand-typed: 'Y' here, 'YES' two columns over.
   Anything starting with Y counts, so a 'Yes' does not silently drop the row. */
function ptYes_(v) { return ptStr_(v).toUpperCase().indexOf('Y') === 0; }
function ptDate_(v) {
  if (v instanceof Date) return Utilities.formatDate(v, Session.getScriptTimeZone(), 'yyyy-MM-dd');
  return ptStr_(v);
}

function getTaxRates_() { return cachedBuild_('taxrates_api', buildTaxRates_); }

function buildTaxRates_() {
  var act = ptTab_(PT_TAB_ACTIVE);
  if (!act || act.getLastRow() < 2) return { ok: false, error: 'Tab "' + PT_TAB_ACTIVE + '" is missing or empty.', count: 0, rows: [] };
  var av = act.getDataRange().getDisplayValues(), ac = ptCols_(av[0]);

  /* The served keys, collected first so the history read below can skip
     everything else: that tab is append-only and grows by hundreds of rows a
     year, while this lookup only ever wants the default-area rows' year. */
  var need = {};
  for (var k = 1; k < av.length; k++) {
    var km = ptStr_(ptG_(av[k], ac, 'municipality'));
    if (!km || !ptYes_(ptG_(av[k], ac, 'isdefaultarea'))) continue;
    var ky = ptNum_(ptG_(av[k], ac, 'effectiveyear'));
    need[km + '|' + ptStr_(ptG_(av[k], ac, 'ratearea')) + '|' + (ky == null ? '' : String(ky))] = 1;
  }

  /* The component split and the source link live on the history tab, joined on
     municipality | rate area | effective year. One extra read, and only for the
     year actually being served. */
  var comp = {}, his = ptTab_(PT_TAB_HIST);
  if (his && his.getLastRow() > 1) {
    var hv = his.getDataRange().getDisplayValues(), hc = ptCols_(hv[0]);
    for (var h = 1; h < hv.length; h++) {
      var hm = ptStr_(ptG_(hv[h], hc, 'municipality'));
      if (!hm) continue;
      var hk = hm + '|' + ptStr_(ptG_(hv[h], hc, 'ratearea')) + '|' + ptStr_(ptG_(hv[h], hc, 'taxyear'));
      if (!need[hk]) continue;
      comp[hk] = {
        munRate: ptNum_(ptG_(hv[h], hc, 'municipalrate')),
        utRate: ptNum_(ptG_(hv[h], hc, 'uppertierrate')),
        edu: ptNum_(ptG_(hv[h], hc, 'educationrate')),
        levy: ptNum_(ptG_(hv[h], hc, 'speciallevy')),
        url: ptStr_(ptG_(hv[h], hc, 'sourceurl')),
        srcType: ptStr_(ptG_(hv[h], hc, 'sourcetype')),
        verified: ptDate_(ptG_(hv[h], hc, 'lastverified'))
      };
    }
  }

  var rows = [];
  for (var i = 1; i < av.length; i++) {
    var r = av[i], mun = ptStr_(ptG_(r, ac, 'municipality'));
    if (!mun) continue;
    /* The phone shows one rate per city. Hamilton's 24 service areas, Chatham-Kent's
       18 and Kawartha Lakes' 17 are real, but a realtor standing in a kitchen wants
       the number, not a menu — the default area is flagged in the sheet. */
    if (!ptYes_(ptG_(r, ac, 'isdefaultarea'))) continue;
    var area = ptStr_(ptG_(r, ac, 'ratearea')), year = ptNum_(ptG_(r, ac, 'effectiveyear'));
    var rate = ptNum_(ptG_(r, ac, 'effectivetotalrate'));
    var c = comp[mun + '|' + area + '|' + (year == null ? '' : String(year))] || {};
    rows.push({
      mun: mun, area: area, tier: ptStr_(ptG_(r, ac, 'tiertype')), region: ptStr_(ptG_(r, ac, 'uppertier')),
      r26: ptNum_(ptG_(r, ac, 'rate2026')), r25: ptNum_(ptG_(r, ac, 'rate2025')),
      year: year, rate: rate,
      per1m: rate == null ? null : Math.round(rate * 10000),
      fallback: ptYes_(ptG_(r, ac, 'fallbackused')),
      status: ptStr_(ptG_(r, ac, 'sourcestatus')) || 'PENDING',
      quotable: ptYes_(ptG_(r, ac, 'quotable')),
      munRate: c.munRate == null ? null : c.munRate,
      utRate: c.utRate == null ? null : c.utRate,
      edu: c.edu == null ? null : c.edu,
      levy: c.levy == null ? null : c.levy,
      url: c.url || '', srcType: c.srcType || '', verified: c.verified || ''
    });
  }
  rows.sort(function (a, b) { return a.mun < b.mun ? -1 : (a.mun > b.mun ? 1 : 0); });
  return { ok: true, updated: new Date().toISOString(), count: rows.length, rows: rows };
}

/* Editor helper: what needs chasing this quarter. Rates do not all land at once —
   Peel and York publish early, Durham and Halton late — so this lists the short
   list rather than the whole table. */
function taxRatesReview() {
  __FRESH = true;
  var d = getTaxRates_();
  __FRESH = false;
  var cut = new Date(); cut.setFullYear(cut.getFullYear() - 1);
  var n = 0;
  for (var i = 0; i < d.rows.length; i++) {
    var r = d.rows[i], why = [];
    if (!r.quotable) why.push('no published rate in either year');
    if (r.fallback) why.push('serving the ' + r.year + ' rate');
    if (r.status === 'DERIVED') why.push('derived, not published');
    if (r.verified && new Date(r.verified) < cut) why.push('last verified ' + r.verified);
    if (why.length) { n++; Logger.log(r.mun + ' — ' + why.join('; ')); }
  }
  Logger.log(n + ' of ' + d.count + ' municipalities need review');
  return 'see log';
}

/** Editor helper: is the workbook reachable and are the tabs named right? */
function TEST_TAX_RATES() {
  __FRESH = true;
  var d = getTaxRates_();
  __FRESH = false;
  Logger.log('ok: ' + d.ok + (d.error ? '  error: ' + d.error : ''));
  Logger.log('municipalities: ' + d.count);
  if (d.count) Logger.log('first: ' + JSON.stringify(d.rows[0]));
  return d.ok ? 'OK' : 'FAILED';
}
