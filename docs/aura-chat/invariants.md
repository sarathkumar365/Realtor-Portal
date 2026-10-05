# Aura Chat — invariants

Break one of these and the failure is either a security hole or a very long
afternoon. Each is written down because it is not visible from the call site.
Referenced from [`../../AGENTS.md`](../../AGENTS.md).

---

## 1. `TOKEN_SECRET` must be byte-identical to the portal's Script Property

The one setting that fails silently and universally. A mismatch means **every
realtor gets 401 while `/health` stays green** — identical, from the outside, to
every session having expired at once. `/doctor` exists to separate those two:
it asks the portal whether *it* accepts the token, and says so in words.

There is deliberately no default. Missing means refuse to sign or verify.

## 2. The caller's own token is the data-plane credential

`PortalClient.call(action, auth=...)` forwards the realtor's token unchanged.
Never add a service account, an API key with standing access, or a "trusted
backend" path. Permissions are then enforced by code that already exists, and a
revoked realtor loses Aura Chat inside the same 5-minute window as the portal.

## 3. What a viewer may see is a property of the repo, not a step

Two axes, both subtractive, unioned in `Viewer.hidden_fields`:

- **role** — what the *account* may ever see. Builder-portal logins are other
  companies' credentials and are admin-only; the portal gates them the same way
  in `getBuilders_`.
- **mode** — what is on the screen *right now*. A realtor in Client Mode has
  turned their phone toward a buyer.

An admin in Client Mode is still showing a buyer a screen, so admin entitlement
never buys back a client-hidden field.

**The mechanism matters more than the policy.** Tools are handed a
`RedactingProjectRepo` built per request from the verified claims, so there is
no code path that yields an unredacted `Project`. Filtering is not something a
tool remembers to do — it is something a tool cannot avoid. `tools.py`
containing `for_viewer` at all is a test failure.

This is stripped **in code, before the model is called**, never by asking the
model to withhold something: a prompt instruction is a request, this is a
guarantee (AUR-18, AUR-55, AUR-56).

One subtlety worth keeping: search filters on the **unredacted** records.
A query may *use* a field it may not *show* — redacting first would silently
change which projects come back depending on who is looking.

## 4. The portal's runtime is shared, and small

Apps Script gives the whole brokerage ~90 minutes of execution a day, and the
portal's own screens need it. Chat traffic starving Home is a real, listed risk.
So: `aiindex` is cached for `ExecApiProjectRepo.TTL_S` — **5 minutes**, roughly
one fetch per conversation rather than one per question —
`PortalClient.healthy()` caches its verdict, and `/health` must stay cheap — it
is polled by the platform and by any uptime monitor. Never add a per-request
portal call that could have been cached.

## 5. V1 is read-only, by construction

No tool takes a write path. Not "no tool currently writes" — no tool *can*.

## 6. Retrieved text is data, never instructions

Documents and sheet rows are untrusted input. Delimit them, and never let their
contents steer the loop. Only **current** documents are ever returned: an April
price list must never come back beside August's, and that rule lives in the
adapter so no caller can forget it.

## 7. No invented facts

A price, deposit or incentive that cannot be confirmed from current records is
answered with *"could not confirm from current records"*. Zero invented prices
is a stated acceptance criterion, not an aspiration.

## 8. `EXEC_URL` is the deployment's address, and it moves

Publishing the portal through "New deployment" mints a fresh id and retires the
old one. If it changes, `EXEC_URL` here and `EXEC` in `dev/config.mjs` must both
change. See [`../portal.md`](../portal.md) §3.3.

## 9. A shared cache must be keyed by whatever it varies on

`ExecApiProjectRepo` holds the project index in **one slot for the whole
process**, filled by whichever realtor's request arrived first. That is correct
today for one reason only: `aiindex` returns the same bytes to every signed-in
realtor.

**It stops being correct the moment `aiindex` varies by role**, and the portal
already has readers that do. `getBuilders_` hides builder-portal LOGIN and
PASSWORD from non-admins, and `getBasement_` strips debug fields — and
`getBuilders_` is also the precedent for the fix:

```js
var ck = 'builders_api' + (isAdmin ? '_admin' : '');   // Sheets.js
```

Two cache keys, so a payload built for an admin can never be served to a
realtor. Our cache has **no key at all**, which is strictly worse: the first
admin request would poison the slot for every realtor behind it, with no
staleness window to survive.

So, before adding anything role-dependent, permission-dependent or
mode-dependent to `aiindex`:

- key the Apps Script cache the way `getBuilders_` does — `ai_index_v1_admin`
  vs `ai_index_v1`; and
- key `_cached` on the same axis, or drop the cross-request cache entirely.

Filtering *after* the fetch is not a substitute: the confidential values are
already in the cached payload by then, and the next request gets them whole.

**Note the distinction from Client Mode.** Client Mode strips fields per
*request*, from a payload that is identical for everyone, so it is unaffected by
this. The danger is only in fields the **portal itself** decides to withhold
based on who asked.
