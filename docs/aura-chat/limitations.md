# What Aura Chat cannot do

AUR-90. The honest list, for a realtor deciding whether to trust an answer and
for whoever inherits this.

Two neighbours: [known-issues.md](known-issues.md) is defects — things that are
wrong and have a fix written. This is the shape of the thing: what it was never
built to do, and what it cannot do yet because the data is not there.

---

## 1. It only knows the project sheet

Aura answers from the city tabs of the brokerage's own spreadsheet, through the
portal's `aiindex` action, and from nothing else. It has **no internet access**,
no MLS, no listing feed, and no memory of anything outside the records it was
handed for that one question.

So it cannot answer: what a resale home sold for, what the market is doing,
whether a school is good, anything about a builder that is not in the sheet, or
anything about a project the brokerage does not carry.

It also **cannot see documents.** Brochures, price sheets, deposit schedules and
floor plans are not indexed — that is Phase 5 and it is not built. A question
whose answer is in a PDF gets "could not confirm from current records", which is
the correct answer and still not the one anybody wanted.

## 2. It cannot do anything

Read-only by construction, not by instruction: the data port has no write method
([invariants.md](invariants.md) 5). It cannot update a record, send an email or a
WhatsApp message, book an appointment, reserve a unit, submit a worksheet, or
touch the CRM. Asking it to will produce a polite refusal, not an action.

## 3. Where the data is thin, the answer is thin

The sheet is filled by hand and the gaps are real. Today:

| Missing | Consequence |
|---|---|
| `DEPOSIT %` empty on every priced project | "Which have less than 10% deposit?" cannot be answered at all |
| `SOURCE URL` empty on all 161 | There is nothing to cite. `WEBSITE URL` has 38 and is the usable one |
| `PROJECT ID` empty on 132 of 161 | Ten ids are shared by 26 projects, so 16 cannot be opened, compared or deep-linked ([known-issues 5](known-issues.md)) |
| `COMMISSION`, `INTERNAL NOTES`, `FUB TEMPLATE` empty on all 158 | Not a gap a realtor sees — but it means the Client Mode leak test passes **vacuously** for the three fields it was written for |

None of these are code. See [§ For Sudhanshu](known-issues.md#for-sudhanshu).

## 4. Dates are unreliable

The sheet writes `MM/DD/YYYY`, the parser reads day-first, and the two disagree
on 10 of 23 dated projects ([known-issues 1](known-issues.md)). Consequences:

- **"What changed this week" is not trustworthy** and is deliberately not one of
  the starter chips
- **No answer shows a last-updated date**, even though the field reaches the
  phone. A freshness line would be a confident wrong date on nearly half

## 5. Comparing by name is unreliable

Asked to compare two projects it just named, the model has to supply ids, and
until Phase 4a history carried no ids at all. Storing them fixed most of it, but
`compare_projects` still takes ids only while the model is inclined to send
names ([known-issues 4](known-issues.md)). And six different Markham projects are
all called UnionGlen, so a name is not always an answer even in principle.

## 6. Client Mode hides fields, not judgement

Client Mode strips confidential fields **in code before the model call**, so
commission, internal notes, builder logins and broker links cannot reach the
screen ([invariants.md](invariants.md) 3). What it cannot strip is the model's
own words. It currently explains the brokerage's focus arrangement to a buyer who
asks the right question, with no sheet value anywhere in the answer —
[known-issues 9](known-issues.md), and the reason the leak test reads clean.

**Client Mode is a safety net, not a substitute for looking at the screen.**

## 7. It can be wrong, and it is built to say so

The guardrail is that an unconfirmed fact must come back as "could not confirm
from current records" rather than a plausible number ([invariants.md](invariants.md)
7). It holds most of the time. The current benchmark is **44 of 50**; the
acceptance bar is 47. Every answer carries thumbs and a Report data issue button
because the reports are how the remaining six get found.

**Never quote a price to a buyer off this screen without opening the project.**

## 8. Practical ceilings

| | |
|---|---|
| Questions per realtor | 60 an hour, then `429` for the rest of the hour |
| Model steps per question | 6 |
| Results per search | 12 |
| Projects per comparison | 4 |
| Turns of context | 20 |
| Project data freshness | Up to 5 minutes stale (the cache). `/doctor?fresh=1` rebuilds it |
| Answer time | Median 2 s, slowest measured 6.6 s |

## 9. Not tested on a real phone yet

The chat has been verified from 320×568 to 1024×1366 with device insets
simulated, but **the real-device pass (AUR-66) has not been run** — the on-screen
keyboard above all. Desktop has no dedicated layout pass either; it is the phone
column, centred.

## 10. One process, one region

No replica, no failover. The rate-limit counters and both caches are in memory,
so a restart resets everyone's hourly allowance, and a second replica would
double every ceiling. Fine for twenty realtors; it is not a design that scales
sideways without work.

If the portal is down, Aura is down — it has no copy of the project data and
[will not keep one](architecture.md). If Postgres is down, history is down and
answers keep working.
