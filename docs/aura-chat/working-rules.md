# Aura Chat — working rules and conventions

How to make a change here. Adjectives are not enforceable, so each rule has a
**trigger** (when it fires) and a **check** (how anyone can tell it was
ignored). Referenced from [`../../AGENTS.md`](../../AGENTS.md).

---

## Working rules

### Before writing anything

- **Search first.** Before adding a function, model, field or helper, grep for
  it. In your reply, either name the existing thing you are reusing, or say
  what you searched for and that nothing matched. "I looked and there isn't
  one" is fine; not looking is not.
- **Before creating a file**, check the roadmap. The names and locations for every file
  through Phase 5 are already decided. If what you need is not on that list,
  that is a design decision — ask.
- **Do not add a port.** Five, hard cap. A sixth needs a stated reason and the
  user's agreement.
- **Do not add a dependency.** The stack is fixed: FastAPI, httpx, Pydantic,
  pydantic-settings, and later PydanticAI and asyncpg. Anything else is a
  design decision.
- **Do not add an abstraction with one caller** — no plugin registry, no
  dynamic loading, no config DSL. Ports are compile-time seams wired in one
  file, and that is the whole extent of the indirection this project buys.

### While writing

- **Smallest change that fully solves the problem.** No speculative parameters,
  no "while I'm here" refactors, no options nobody asked for. Spotting an
  unrelated problem is useful — say so; do not fix it in the same change.
- **Reuse the seams that exist**: `PortalClient.call`, the `AuthVerifier`
  two-level verify, `Project` / `ProjectFilters`, `Check` and `Report` in
  `diagnostics.py`, the fakes in `tests/fakes.py`. A new helper duplicating one
  of these is a defect, not a preference.
- **Depend on ports, never on adapters** — outside `container.py`, an
  `app.adapters` import is a test failure.

### Tests

`pytest` is the gate, and it never touches the network.

- **Every port has a fake** in `tests/fakes.py`. A new port, or a new method on
  one, means updating the fake in the same change.
- **Fixing a bug means adding the test that would have caught it**, in the same
  change. Precedent: `test_layering.py` exists because a single stray import
  would turn a one-file migration into archaeology.
- Changing behaviour a test asserts means updating that test in the same
  change — never after, and never by loosening the assertion.
- Run `.venv/bin/python -m pytest -q` before claiming done, and report the
  result including failures.

### Design decisions belong to the user

**Stop and ask** when the change involves: a new port or adapter, a new
dependency or hosted service, the token or auth path, what Client Mode hides,
the shape of a tool the model will see, a new Apps Script action, database
schema, or two defensible approaches with materially different trade-offs.
Present the options and the trade-off, then wait.

**Do not ask** about naming, formatting, which existing helper to use, or
anything AGENTS.md already answers. Decide and move on.

### Report honestly

Say what changed, what was verified and how, and what was deliberately left
out. A failing check reported is worth more than a passing one implied.

---

## Conventions

- **Python 3.12+.** Modern typing throughout: `X | None`, `list[dict]`,
  `StrEnum`, `Protocol`, `@dataclass(slots=True)`. No `Optional`, no `Dict`.
- **Everything crossing a boundary is a Pydantic model**, not a dict. Inside a
  module, a dataclass is fine.
- **Ports are `async`.** An adapter that cannot be async still declares async.
- **Docstrings explain why, and what breaks otherwise.**
  `app/adapters/auth_portal_hmac.py` and `app/diagnostics.py` are the standard:
  the reason a line exists, the failure it prevents, what was measured. A
  docstring restating the signature is worse than none.
- **Never log or return a secret's value.** Name a missing setting, never its
  contents — `config_check` reports `missing: TOKEN_SECRET`, and `/health` does
  not even say that much, because a stranger learning which secret is unset is
  a stranger learning when to try forging one.
- **A dependency's failure must not 500 the diagnosis.** `_timed` catches
  broadly on purpose; the portal being unwell is not the token being bad.
- **Linting:** `ruff`, line length 100. Note that `pyproject.toml` pins only
  line-length and target-version, so ruff 0.16's default rule set applies and
  currently reports ~16 findings (import order, blind `except`, `Depends` in a
  default, `dict()` calls, naive `strptime`). Several are deliberate and
  documented in the code — **do not "fix" them by rewriting working code.** Pinning
  `[tool.ruff.lint] select` is the real fix, and it is a decision for the user.
- **Commit messages:** `type: imperative summary` (`feat`, `fix`, `perf`,
  `security`, `chore`, `style`) with a body explaining the failure, the
  mechanism, and how it was verified. Read `git log` first — the bar is high
  and deliberate.

---

### Record why, not just what

- **Trigger:** any change a future reader could reasonably want to undo — a
  design decision, a rejected alternative, a non-obvious constraint, a bug whose
  fix looks arbitrary without its story.
  **Check:** `git log` shows a substantive commit with no matching entry in
  [`../worklog.md`](../worklog.md).
- **Skip it** for typos, formatting and mechanical renames. An entry nobody
  needs is noise, and noise is how a log stops being read.
- Write the **reason**. The code says what changed and `git log` says when; the
  worklog is for what neither records — the option rejected and why, the
  constraint that forced the shape, what reversing will cost.
- Sharp edges belong in **both** places: a comment where the trap is, so nobody
  meets it unwarned, and the worklog entry so the next reader understands the
  shape of the whole change.

---

## Definition of done

1. `.venv/bin/python -m pytest -q` green, including a test that would have
   caught the thing you just fixed.
2. `test_layering.py` still green — the architecture rules survived the change.
3. `/doctor` green against a real token, if the change touches auth or the data
   plane.
4. Substantive change? [`../worklog.md`](../worklog.md) has an entry for it.
5. What you changed, what you verified, and what you left out, stated plainly.
6. Portal files touched? `node dev/verify.mjs`, then `clasp push`, then publish
   by **editing** the existing deployment.
