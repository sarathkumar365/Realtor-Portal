/**
 * Realtor Portal — schema audit (editor-only, read-only)
 *
 * Diagnostics for the Aura Chat sprint. Nothing here is routed, nothing writes.
 * Run from the Apps Script editor and read the execution log.
 *
 *   auditCityHeaders()   what columns the city tabs actually have, and where a
 *                        PROJECT ID column would have to go
 *   auditPriceTabs()     whether HotPriceSheet / Deposit Calculator / PRECON /
 *                        HotDeals carry per-project commercial data
 *
 * Safe to delete once the sprint's discovery tickets close.
 */

/* Every distinct row-2 header across the city tabs, with how many tabs use it.
   A header on all ~60 is a column Aura Chat can rely on; one on three tabs is not. */
function auditCityHeaders() {
  var cities = getCities_().cities, seen = {}, shapes = {}, n = 0;
  Logger.log('=== city tabs: ' + cities.length + ' ===');
  for (var i = 0; i < cities.length; i++) {
    var sh = resolveCity_(cities[i]);
    if (!sh) continue;
    var lastCol = sh.getLastColumn();
    if (lastCol < 2) continue;
    var hdr = sh.getRange(HEADER_ROW, 1, 1, lastCol).getDisplayValues()[0]
      .map(function (h) { return String(h || '').trim().toUpperCase(); });
    n++;
    var shape = hdr.join(' | ');
    shapes[shape] = (shapes[shape] || 0) + 1;
    for (var c = 0; c < hdr.length; c++) if (hdr[c]) seen[hdr[c]] = (seen[hdr[c]] || 0) + 1;
  }
  Logger.log('--- headers, by how many tabs carry them (of ' + n + ') ---');
  Object.keys(seen).sort(function (a, b) { return seen[b] - seen[a]; })
    .forEach(function (h) { Logger.log('  ' + seen[h] + '\t' + h); });

  Logger.log('--- distinct column layouts ---');
  var ks = Object.keys(shapes).sort(function (a, b) { return shapes[b] - shapes[a]; });
  Logger.log('  ' + ks.length + ' distinct layout(s) across ' + n + ' tabs');
  for (var j = 0; j < Math.min(ks.length, 6); j++) Logger.log('  [' + shapes[ks[j]] + ' tabs] ' + ks[j]);
  if (ks.length > 6) Logger.log('  ...and ' + (ks.length - 6) + ' more');

  /* The two invariants a PROJECT ID column must not break: getCities_ identifies a
     city tab by A=PROJECT and B=BUILDER on row 2, and buildColMap_ binds each field
     to the FIRST header containing its keyword. */
  Logger.log('--- widest tab (append a new column after this many) ---');
  var widest = 0, wname = '';
  for (var w = 0; w < cities.length; w++) {
    var s2 = resolveCity_(cities[w]); if (!s2) continue;
    var lc = s2.getLastColumn();
    if (lc > widest) { widest = lc; wname = cities[w]; }
  }
  Logger.log('  ' + widest + ' columns (' + wname + ')');
  Logger.log('  A PROJECT ID column goes at the RIGHT of each tab, never at A.');
  return 'see log';
}

/* Do the tabs nothing in the app reads carry the pricing the city tabs lack? */
function auditPriceTabs() {
  var want = ['HotPriceSheet', 'Deposit Calculator', 'PRECON', 'HotDeals', 'RESALE', 'FocusProjects'];
  for (var i = 0; i < want.length; i++) {
    var sh = null;
    try { sh = ssFor_('main').getSheetByName(want[i]); } catch (e) {}
    Logger.log('=== ' + want[i] + ' ===');
    if (!sh) { Logger.log('  (no such tab)'); continue; }
    var lastRow = sh.getLastRow(), lastCol = sh.getLastColumn();
    Logger.log('  ' + lastRow + ' rows x ' + lastCol + ' cols');
    if (lastRow < 1 || lastCol < 1) continue;
    // Headers are not reliably on row 1 here, so show the first three rows and judge by eye.
    var peek = sh.getRange(1, 1, Math.min(3, lastRow), Math.min(lastCol, 30)).getDisplayValues();
    for (var r = 0; r < peek.length; r++) {
      Logger.log('  r' + (r + 1) + ': ' + peek[r].map(function (v) {
        v = String(v || '').trim(); return v.length > 22 ? v.slice(0, 22) + '…' : v;
      }).join(' | '));
    }
  }
  return 'see log';
}

/* Header row plus the first few data rows of one city tab, so the AI side can see
   how values are actually written (currency symbols, ranges, date formats) before
   any parsing is designed. Display values, exactly as a realtor sees them. */
function auditTabRows(tabName, howMany) {
  tabName = String(tabName || 'BRAMPTON');
  howMany = howMany || 5;
  var sh = resolveCity_(tabName);
  if (!sh) { Logger.log('no city tab named ' + tabName); return 'not found'; }
  var lastCol = sh.getLastColumn(), lastRow = sh.getLastRow();
  Logger.log('=== ' + tabName + ' — ' + lastRow + ' rows x ' + lastCol + ' cols ===');
  var hdr = sh.getRange(HEADER_ROW, 1, 1, lastCol).getDisplayValues()[0];
  var n = Math.min(howMany, lastRow - DATA_START + 1);
  if (n < 1) { Logger.log('no data rows'); return 'empty'; }
  var rows = sh.getRange(DATA_START, 1, n, lastCol).getDisplayValues();
  /* Column-per-line rather than one long row: a 20-column row wraps unreadably in
     the execution log, and the whole point here is to read the values. */
  for (var r = 0; r < n; r++) {
    Logger.log('--- row ' + (DATA_START + r) + ' ---');
    for (var c = 0; c < lastCol; c++) {
      var h = String(hdr[c] || '').trim().replace(/\s+/g, ' ');
      var v = String(rows[r][c] || '').trim();
      if (!h && !v) continue;
      Logger.log('  ' + (h || '(col ' + (c + 1) + ')') + ' = [' + (v.length > 60 ? v.slice(0, 60) + '…' : v) + ']');
    }
  }
  return 'see log';
}
