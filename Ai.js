/**
 * Realtor Portal — the Aura Chat contract surface
 * ==============================================
 * Everything the AI service reads lives behind this one action. Kept in its own
 * file so the boundary is obvious and so the whole surface can be removed in a
 * single delete if Aura Chat is ever retired.
 *
 * Read-only, by construction: it composes existing readers and writes nothing.
 *
 *   aiindex   the whole cross-city project set, one payload
 *
 * Why one big payload rather than a filtered query: the AI service filters in
 * Python and caches this for a few minutes, so a busy conversation costs one
 * fetch per cache window instead of one per question. Apps Script runtime is a
 * single daily budget shared with the realtors' own app -- protecting it is the
 * reason Aura Chat runs outside Apps Script at all.
 */

/* Its own cache key, deliberately. index_api backs the portal's Cities and
   Focus screens and is on the Home hot path; a heavier payload for a different
   consumer does not belong in it. Both are built from the same per-city
   proj_<CITY> entries, so the sheet reads are shared even though the indexes
   are not.

   ONE key, because this payload is currently identical for every signed-in
   realtor. If anything here ever becomes role-dependent -- as getBuilders_ is,
   hiding LOGIN and PASSWORD from non-admins -- this key MUST split the same
   way getBuilders_ splits its own ('builders_api' vs 'builders_api_admin'),
   and the AI service's own cache must split too. Filtering after the fetch
   does not help: by then the values are already in the cached payload. */
function getAiIndex_() {
  return cachedBuild_('ai_index_v1', buildAiIndex_);
}

function buildAiIndex_() {
  var cities = getCities_().cities;
  /* Warm every city's cached payload in one round trip before the loop reads
     them one at a time -- same keys getProjects_ builds, so a hit here saves it
     the sheet read. Mirrors buildSearchIndex_. */
  var warm = [];
  for (var w = 0; w < cities.length; w++) warm.push('proj_' + String(cities[w] || '').trim().toUpperCase());
  cachePrefetch_(warm);

  var rows = [];
  for (var i = 0; i < cities.length; i++) {
    var city = cities[i], res;
    try { res = getProjects_(city); } catch (e) { res = { rows: [] }; }
    var ps = res.rows || [];
    for (var j = 0; j < ps.length; j++) {
      var p = ps[j];
      /* Unavailable projects are carried, not dropped. The portal's own index
         excludes them because its screens list what is for sale; Aura still has
         to answer "what happened to X?", so the flag travels and the AI service
         decides. */
      rows.push({
        city: city, row: p._row,
        id: p.id, project: p.project, builder: p.builder, type: p.type, cats: p.cats,
        status: p.status, hidden: p.hidden, focus: /fo(cu|uc)s/i.test(p.status || ''),
        occupancy: p.occupancy, address: p.address,
        price: p.price, maxprice: p.maxprice, beds: p.beds,
        depositpct: p.depositpct, depositsched: p.depositsched, incentives: p.incentives,
        lastupdated: p.lastupdated, sourceurl: p.sourceurl,
        website_url: p.website_url, drive_url: p.drive_url, broker_url: p.broker_url,
        /* Builder-portal credentials. Present because the AI service strips them
           for Client Mode itself and needs to know they exist; the portal
           already returns them to any signed-in realtor. */
        login: p.login, office: p.office, contact: p.contact, fub: p.fub
      });
    }
  }
  return { updated: new Date().toISOString(), count: rows.length, rows: rows };
}
