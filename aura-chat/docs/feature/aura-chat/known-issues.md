# Known issues

Found, understood, **not fixed**. Fixing everything the moment it is found stops
the build; writing it down badly means finding it twice.

One entry per defect. Each carries the symptom a realtor would see, the root
cause in the code, a command that reproduces it, and the fix I would write. If
an entry cannot be reproduced from a cold checkout, it is not finished.

**This is not the worklog.** [worklog.md](../../worklog.md) says why the code is the
way it is. This says where it is still wrong.

When one is fixed: delete the entry, and put the reason in the worklog.

Status as of **2026-08-27**, against 161 projects (250 sheet rows, 87 dropped as
ONTARIO roll-up). Numbering has gaps where entries were fixed and deleted; the
reasons are in the worklog.

| # | Issue | Severity | Blast radius |
|---|---|---|---|
| [3](#3) | An invented category returns silence, not an error | **High** | any type not in the four buckets |
| [4](#4) | `compare_projects` takes ids only; and a follow-up has no ids to send | **High** | most comparisons |
| [5](#5) | 16 projects are unreachable by id | **High** | 16 of 161 |
| [8](#8) | Benchmark expectations count duplicated rows | Medium | the benchmark's own credibility |
| [9](#9) | Client Mode explains the focus arrangement to a buyer | **High** | any pointed commercial question — *accepted, shipped* |
| [10](#10) | The card can be a different project from the one the answer names | **High** | any "which is the earliest/largest/nearest" question |
| [11](#11) | "Could not confirm X" and then states X, in one sentence | Medium | most single-project answers |
| [12](#12) | Incentives are unsearchable — appliances, development charges, capped DC | Medium | a whole class of realtor questions |
| [13](#13) | No proximity or landmark search | Low | "near Highway 413", "close to the GO" |
| [14](#14) | A refused filter blames "the tool" and leaks internals | Medium | any unsupported word in a query |
| [15](#15) | `schema.sql` is not in the built package | Low | only a run from the installed package, not from the source folder |

Data problems that are not code: [§ For Sudhanshu](#for-sudhanshu).

---

<a id="3"></a>
## 3. An invented category returns silence, not an error

**Severity: High.** Aura denies that projects exist — **intermittently**, which
is worse than always.

**Symptom.** "Show me stacked townhomes." → *"I could not find any stacked
townhomes in our records."* There are five: NOMI, Flori, Northside, Orleans
(Summit Series), Westshore.

Asked again it answers correctly. Whether it fails depends on whether the model
invents a category that run, so the realtor gets a confident denial on one try
and the right answer on the next, with nothing to tell them which they got.

**Root cause.** `ProjectFilters.categories` is an unvalidated `list[str]`. The
portal's buckets are `detached, semi, townhome, condo`. The model called
`search_projects(categories=['stacked townhome'])`, `matches()` intersected that
with the real buckets, got nothing, and returned an empty page — which is
**indistinguishable from "the brokerage has none"**. Nothing anywhere says the
category was not real.

The same search with a valid filter finds all five, so the data and the matcher
are fine. The tool's contract is the defect.

**Reproduce — the defect, deterministically.** The tool accepts any string and
answers "none" to all of them:

```bash
cd aura-chat && .venv/bin/python - <<'EOF'
import asyncio, json, pathlib
from app.domain import ProjectFilters
from app.adapters.projects_exec import ExecApiProjectRepo
from app.adapters.portal_client import PortalClient

tok = json.loads((pathlib.Path.home() / ".aura/session.json").read_text())["token"]
url = open(".env").read().split("EXEC_URL=")[1].split("\n")[0].strip()

async def main():
    repo = ExecApiProjectRepo(PortalClient(url))
    for cats in (["stacked townhome"], ["townhouse"], ["townhome"]):
        page = await repo.search(ProjectFilters(categories=cats), auth=tok)
        print(f"{cats!r:24} -> total={page.total}")

asyncio.run(main())
EOF
```
```
['stacked townhome']     -> total=0
['townhouse']            -> total=0      <- a plausible synonym, silently empty
['townhome']             -> total=102
```

**Reproduce — the realtor-facing failure, unreliably.** `.venv/bin/aura --dev
"Show me stacked townhomes."` and watch the `search_projects(...)` line. When it
reads `categories=['stacked townhome']` the answer is a denial; when the model
picks `categories=['townhome'], query='stacked townhome'` it correctly finds all
five. Both happen. Do not read one good run as the issue being gone.

**Fix.** Validate `categories` against the four buckets and return
`unknown_categories: ['stacked townhome']` alongside the results, so an empty
page cannot mean two different things. Same principle as the truncation fix: a
tool must never let "you asked wrongly" look like "there are none". Free text
already searches `property_type`, so the model can recover on its own once it is
told.

---

<a id="4"></a>
## 4. `compare_projects` takes ids only, and the model sends names

**Severity: High.** Whether a comparison works is luck.

**Symptom.** "Compare Cornerstone and Reva Westfield." → *"I could not confirm
that from current records."* Both projects exist and both have ids.

**Root cause.** `tools.compare_projects` calls `repo.get(pid)`, which matches
`p.id` exactly. `get_project` resolves a name to an id first; `compare_projects`
does not, because that resolution lives inside `get_project` rather than
somewhere both can use. A realtor naming two projects is not handing over ids,
and the model passes what the realtor said.

**Reproduce.**
```bash
cd aura-chat && .venv/bin/aura --dev "Compare Cornerstone and Reva Westfield."
```
The dev line shows `compare_projects(project_ids=['Cornerstone', 'Reva Westfield'])`.

**Fix.** Lift the resolve-a-name step out of `get_project` into a shared helper
in `app/capabilities/chat/tools.py` and use it in both. An ambiguous name should return candidates
to choose from, exactly as `get_project` already does, rather than nothing.

### Second root cause: a follow-up comparison has no ids to send

Named separately because the fix above does **not** touch it, and reading only
the first half would leave half the failures in place.

**Symptom.** Q34 "What townhomes are in Oakville?" → Q35 "Compare the first two."
→ *"I couldn't find those projects by ID."* The dev line shows
`compare_projects(project_ids=['oakville-townhomes-1', 'oakville-townhomes-2'])`
— ids that have never existed. The model invented them in the shape it guessed.

**Root cause.** History carries no ids. `_as_messages` in
`app/capabilities/chat/adapters/agent_pydantic.py` converts each `Turn` to text and nothing else,
deliberately — replaying an old tool result would put a stale price back into
the prompt. The consequence was not intended: with the previous answer reduced
to prose, "the first two" refers to projects the model can name and cannot
identify, so it fabricates plausible ids rather than admitting it has none.

A name resolver does not help here. There is no name in
`['oakville-townhomes-1', ...]` to resolve.

**Reproduce.** A follow-up needs a history array, which the one-shot CLI has no
way to send, so this goes through the endpoint:

```bash
curl -N -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' -d '{"question":"Compare the first two.","history":[{"role":"user","content":"What townhomes are in Oakville?"},{"role":"assistant","content":"Two Oakville townhomes match: Ivy Rogue and New Kleinburg."}]}' "$AURA_BASE/chat"
```

**Fix.** Phase 4, not a patch. Once `ai_messages` stores each answer with its
`sources`, the ids the previous turn actually returned are on the server and
follow-ups resolve against them. The cheap interim — the client keeping ids on
the assistant turn and sending them back — is deliberately **not** taken: it is
work Phase 4 deletes, and the client already mints an `answer_id` per answer
(for feedback) that becomes the `ai_messages` id, so the join is already in
place waiting for the table.

**Not ambiguity.** Worth saying, because it is the natural first guess: the two
projects in Q09 have unique names and real ids (AK-0002, AK-0012). The genuine
ambiguity problem is [#5](#5), and it is worse than same-name-in-two-cities —
six different Markham projects are all called UnionGlen, in the *same* city, so
carrying the city forward would not disambiguate them either. Only the builder
would.

---

<a id="5"></a>
## 5. 16 projects are unreachable by id

**Severity: High.** They can be found by search and then not opened.

**Symptom.** Six different Markham projects are all called UnionGlen. Five of
them cannot be retrieved, compared, or deep-linked — every request for any of
them returns the first.

**Root cause.** Only 29 of 161 rows carry a real PROJECT ID. The rest fall back
to `slugify(city, name)`, which is exactly two parts — so two projects with the
same name in the same city get the same id, and `get()` returns whichever the
sheet lists first.

```
markham:unionglen      6 projects
whitby:whitby-meadows  3
caledon:southcal       3
oakville:ivy-rogue     2   vaughan:new-kleinburg 2   pickering:new-seaton 2
```

10 ids covering 26 projects; **16 are shadowed**.

**Reproduce.** Search Markham, then ask about UnionGlen by any of its builders —
the same record comes back every time.

**Fix, in order of preference.**

1. **Sudhanshu fills PROJECT ID.** The real fix, and it is already underway. See
   the warning in [§ For Sudhanshu](#for-sudhanshu) about the ONTARIO tab: what
   id goes on a duplicated row decides whether de-duplication stays possible.
2. **Add the builder to the slug** — `markham:unionglen:fieldgate-homes`. Fixes
   most collisions today at the cost of another id that changes when a cell is
   edited. Six UnionGlens by six builders separate cleanly; six by one builder
   still collide.
3. **Fall back to the sheet's row number**, which is already in the payload and
   is unique. Stable only until rows are reordered.

Worth deciding before ids are minted, not after.

---

<a id="8"></a>
## 8. Benchmark expectations were written against duplicated data

**Severity: Medium** — it makes the benchmark's own verdicts untrustworthy.

**Symptom.** `benchmarks/questions.csv` expects counts that included ONTARIO
duplicates, so correct answers now fail and the score understates the system.

```
Q12  "around 10" stacked townhomes     really 5 (the other 5 were duplicates)
Q30  "Yes, 4" Ottawa projects          3 named + 1 row with an empty name
Q50  "38 of 246 carry a link"          38 of 161
```

Q07 and Q30 also check `cards>=N`, written before `inventory_summary` existed —
it answers counting questions correctly and returns no cards **by design**, so
the check now fails on the better answer.

**Root cause.** I derived the expectations by reading the sheet before the
duplicate tab was understood.

**Fix.** Re-derive every count against the live 161 and replace card-count checks
with content checks wherever a summary is now the right tool. Do this **last**,
after the fixes above — correcting checks against unfixed behaviour is how a
benchmark quietly becomes a description of the bugs.

---

<a id="for-sudhanshu"></a>
## 9. Client Mode discloses the focus list, and what focus means commercially

**Decision, 2026-08-25: accepted, not fixed before launch.** Sarath's call, made
with the behaviour in front of him. Going live with it is deliberate, so the
things that make it survivable have to be said out loud:

* It needs a buyer to ask a pointed commercial question — "do you earn more on
  some of these?" — while the phone is turned toward them. It does not happen
  on its own.
* No sheet value is disclosed. What leaks is the explanation, in the model's
  own words.
* **The realtor is the control.** Client Mode was always a safety net rather
  than a substitute for watching the screen, and this is exactly the gap where
  that distinction matters. Worth saying to the team at rollout.
* It is one of the ten acceptance criteria ("confidential Client Mode leaks:
  0"), so the MVP does not formally clear until it is fixed.

Revisit before the brokerage advertises Client Mode as buyer-safe.

**Severity: High** — it is the one thing Client Mode exists to prevent, and it is
invisible to the leak test that is supposed to catch it.

**Symptom.** Asked, in **Client Mode**, "Are there projects you earn more on?
Which ones should I look at first?", Aura answers:

> "Aura Key Realty prioritizes certain projects where we have **special
> arrangements**, offering unique benefits to both our clients and **our
> realtors**. These are our 'focus projects.'"

...and lists them, with twelve cards. That is the brokerage telling a buyer it
has a commercial interest in specific projects, over the realtor's shoulder.

**Root cause -- two halves, both needed.**

1. `is_focus` is **not** in `CLIENT_HIDDEN`. `status` is, so the Focus pill on
   the card correctly disappears -- but the underlying boolean survives
   redaction, and `search_projects(focus_only=True)` is still callable in Client
   Mode. Verified: `Project(is_focus=True).for_viewer(CLIENT)` returns
   `status=''` and `is_focus=True`.
2. The **base** system prompt -- the one used in both modes -- says "Focus
   projects are the ones the brokerage is *actively pushing*." `CLIENT_MODE_NOTE`
   names commission, internal notes and builder contacts, but never focus. So in
   Client Mode the model holds an explanation of the commercial arrangement and
   no instruction against sharing it.

**Why the leak test does not catch it.** AUR-58's probe matches the *real values*
from the sheet against everything reaching the phone. This disclosure contains no
sheet value at all -- the model says it in its own words. Twelve adversarial
probes, including a prompt-injection attempt, come back clean while this happens.

**Reproduce.**

```bash
curl -sN -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
  -d '{"question":"Are there projects you earn more on? Which ones should I look at first?","mode":"client"}' \
  https://aura-chat-production-0711.up.railway.app/chat | grep text
```

**The fix I would write.** Structural first, prompt second, because a prompt rule
is a request:

* Add `is_focus` to `CONFIDENTIAL_FIELDS` and `CLIENT_HIDDEN`. It is a boolean,
  so `for_viewer` must blank it to `False` -- the current
  `model_copy(update={f: "" for f in hidden})` writes `""`, which is falsy for a
  bool field only after pydantic coercion and is a trap worth checking. Adding
  the field without getting that right could make it leak harder, not less.
* Reject `focus_only=True` in Client Mode at the tool boundary, so the capability
  is gone rather than discouraged.
* Move "the ones the brokerage is actively pushing" out of the shared prompt, or
  add a Client Mode line forbidding any explanation of what focus means.

**Also worth deciding:** whether a buyer may see focus projects *at all* without
the commercial framing. Showing them is arguably fine -- a realtor recommends
things. Explaining that the brokerage earns more on them is not.

---

<a id="10"></a>
## 10. The card can be a different project from the one the answer names

**Severity: High.** A realtor reads the card, not the paragraph.

**Symptom.** From Sudhanshu's QA pass:

> **Earliest occupancy?**
> The earliest occupancy for a freehold project in Pickering is 2026/27 for
> **Seatonville by Arista Homes**.
> *[card shown: **New Seaton** · PICKERING · Towerhill Homes · from $627,425]*

The sentence names one project and the card underneath shows another.

**Root cause.** `inventory_summary` decides which record gets a card through its
`spotlight` argument, and `spotlight` only understands `cheapest`, `dearest`,
`both` and `none` (`agent_pydantic.py`, the `show not in (...)` guard). There is
no spotlight for "earliest occupancy", "most bedrooms" or anything else. Asked a
superlative it cannot spotlight, the model reasons the right answer out of the
summary text and then asks for the only card it can get — the cheapest.

The prompt already warns about exactly this outcome — *"a card under an answer
that was not about that project reads as a result, and contradicts you"* — which
is a request, not a guarantee, and this is what a request buys.

**Reproduce.** Ask for a city summary, then any superlative that is not price:
"earliest occupancy?", "which has the most bedrooms?".

**The fix I would write.** Two options, in order of preference:

1. Let the model name the record instead of picking from an enum:
   `spotlight_id: str = ""`. It already has the ids in the summary, so it can
   point at the one it just named. Unknown id shows no card.
2. Failing that, refuse the mismatch rather than allow it — drop the card when
   the answer text does not mention the spotlit project's name. Weaker, because
   it is a string check on prose.

---

<a id="11"></a>
## 11. "Could not confirm X" and then states X, in one sentence

**Severity: Medium.** It undermines the one guarantee the system is sold on.

**Symptom.**

> I was **not able to confirm the bedroom count or occupancy date** from current
> records, but it is listed as **having between 3 and 5 bedrooms**.

...under a card reading `Townhome/Detached · 2026`. So it disclaims the bedroom
count and the occupancy, then supplies both, and the card supplies them again.

**Root cause, not yet confirmed.** Likely the model treating a partially-filled
record as unconfirmed — a range rather than a single value, or a `2026/27`
occupancy rather than a date — and hedging while still reporting what it has.
The no-invention rule in the prompt says unconfirmed facts must come back as
"could not confirm"; nothing says what to do with a fact that *is* there but is
imprecise, so the model does both.

**Why it matters more than it reads.** "Could not confirm from current records"
is the sentence that makes Aura trustworthy. Spending it on a fact that is
present teaches realtors to ignore it, and then it fails to protect them on the
day it is real.

**Reproduce.** Ask about any project whose bedrooms are a range: "Detached homes
under $1M in Brampton".

**The fix I would write.** Decide what an imprecise-but-present value is, once,
and say so in the prompt: a range *is* a confirmed value; only an empty field is
unconfirmed. Then check the wording holds on the benchmark's single-project
questions.

---

<a id="12"></a>
## 12. Incentives are unsearchable — appliances, development charges, capped DC

**Severity: Medium.** Reported by Sudhanshu, who owns the column.

**Symptom.** All three of these come back empty:

> **Projects with appliances included.** → could not confirm any…
> **Projects with capped development charges.** → could not confirm any…
> **What are the development charges of Spring Valley Village** → could not confirm…

**and the data is there.** Sudhanshu's note: *"This info is stored in Incentives
(if applicable)"*. Aura even quotes it happily when it has the project in hand —
*"$10,000 to spend at the decor centre, plus central air and five appliances"* —
it simply cannot search on it.

**Root cause.** `ProjectFilters` has no incentive field, so `search_projects`
cannot filter on it and `inventory_summary` cannot count on it. `incentives`
reaches the model only as free text on a record it already found by other means.
Asked directly, the model says so: *"I can only search for projects based on
location, price, type, or builder, not by incentives."*

**Reproduce.** Any of the three questions above.

**The fix I would write.** Add `incentive_contains: str = ""` to
`ProjectFilters` and match it case-insensitively against the incentives text in
`matches`, the same way `query` already works over name and builder. It is a
substring search over a free-text column, so it will be imperfect — "appliances"
will miss "5 appl." — which is an argument for tidying the column, not against
the filter.

---

<a id="13"></a>
## 13. No proximity or landmark search

**Severity: Low.** A capability gap, not a defect.

**Symptom.**

> **Projects close to Highway 413.** → could not confirm any projects near
> Highway 413 from current records

Sudhanshu's note: *"If we can search according to nearby address as highways
nearby Brampton or Pickering likewise which cities we are looking at"*.

**Root cause.** There is nothing to search. The sheet carries a city and an
address; it carries no coordinates, no highway, no transit and no distance. Aura
has no map and no internet.

**The fix I would write.** Not a code fix first. The cheap version is a
`LANDMARKS` or `NEAR` column the team fills in ("Hwy 413, Hwy 410, Mount Pleasant
GO"), searchable the same way [12](#12) proposes. Real proximity needs
geocoding, which is a different project.

---

<a id="14"></a>
## 14. A refused filter blames "the tool" and leaks internals

**Severity: Medium.** It reads as broken software rather than a missing feature.

**Symptom.**

> **Freehold townhomes under $800K?**
> I'm sorry, I cannot fulfill that request. **The tool does not accept
> "freehold" as a valid parameter.**
>
> **townhomes under $800K?**
> I'm sorry, I cannot fulfill that request. The tool does not accept
> "townhomes" as a valid parameter for the inventory summary.

Two problems in two lines. It says *"the tool"* and *"parameter"* to a realtor,
and it refuses a question it can answer — the same session later handled
*"Freehold only."* correctly, and "townhomes" is a plural of a category that
exists.

**Root cause.** Sibling of [3](#3): the four categories are an undeclared
convention rather than an enum on the tool, so the model has to guess whether a
word qualifies, and guesses inconsistently. The wording is the prompt's silence
on how to refuse — nothing tells it to answer as a colleague rather than as an
API.

**Reproduce.** "Freehold townhomes under $800K?" as a first question, with no
prior context.

**The fix I would write.**

* Declare the categories as a `Literal["detached","semi","townhome","condo"]` on
  the tool so the schema carries them and plurals normalise (see also [3](#3)).
* Map the tenure words realtors actually use — freehold, condo, POTL — to what
  the sheet holds, or say plainly that tenure is not recorded.
* Add one prompt line: never name a tool, a parameter or a field. Say what is
  not recorded and offer the nearest question that is.

---

<a id="15"></a>
## 15. `schema.sql` is not in the built package

**Severity: Low.** Nothing breaks today. It breaks the day the service runs from
an installed package instead of from its source folder.

**Symptom.** None yet. If it triggers: the first conversation read or write
fails with `FileNotFoundError: .../app/capabilities/chat/adapters/schema.sql`.
Chat answers still stream, but history and feedback are not stored.

**Root cause.** `store_postgres.py` reads its schema from a file beside itself
(`SCHEMA = Path(__file__).with_name("schema.sql")`) and applies it on first use.
`pyproject.toml` lists packages only (`include = ["app*"]`) and declares no
package data, so setuptools ships the `.py` files and leaves `schema.sql` out.
It works on Railway and locally because uvicorn starts in the source folder,
where `app/` on the path shadows the installed copy. Found 2026-10-06 while
checking the chat move; the file was missing from the wheel before the move too.

**Reproduce.**

```bash
cd aura-chat
.venv/bin/pip wheel . --no-deps -q -w /tmp/aura-wheel
unzip -l /tmp/aura-wheel/aura_chat-*.whl | grep -c schema.sql   # 0
rm -rf build
```

**The fix I would write.**

* In `pyproject.toml`:

  ```toml
  [tool.setuptools.package-data]
  "app.capabilities.chat.adapters" = ["schema.sql"]
  ```

* Add a test that builds the wheel (or reads the setuptools config) and
  asserts every non-`.py` file under `app/` is declared, so the next capability's
  `schema.sql` cannot go missing the same way.

---

## For Sudhanshu — data, not code

No amount of code fixes these.

| What | Where | Why it matters |
|---|---|---|
| `09/31/2025` | Arbor West, Brampton | September has 30 days. Unparseable, so the project has no date at all. |
| `10/25/2026` | Harvest Park, Kitchener | Two months in the future. `recent()` now excludes it and `/doctor` counts it, but the date itself is still wrong in the sheet. |
| `SOURCE URL` empty | all 161 | Nothing to cite. `WEBSITE URL` has 38 and is the usable one. |
| `DEPOSIT %` empty | every priced project | "Which have less than 10% deposit?" cannot be answered at all. |
| `PROJECT ID` empty | 132 of 161 | See [#5](#5). |
| `COMMISSION`, `INTERNAL NOTES`, `FUB TEMPLATE` empty | all 158 | **The Client Mode leak test (AUR-58) passes vacuously for these three.** You cannot leak a field with no data in it. Redaction is proven for `broker_url`, `drive_url`, `builder_contact`, `builder_office` and `builder_login`, which do carry values — the other three are untested until somebody fills them, and they are the three the test was written for. |
| The ONTARIO tab | 87 rows | **Decide before filling PROJECT ID.** If a duplicated row gets the *same* id as its city-tab row, de-duplication becomes possible. If it gets a *different* id, the two become formally distinct projects and the last clue that they are the same — the name — stops being enough. Different ids are worse than no ids. |
