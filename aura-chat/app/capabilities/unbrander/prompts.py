"""The unbrand step's prompts: sort, pick, judge, repair.

Adapted from the unbrand-builder-docs skill. Only its judgement rules are kept;
its code, setup and delivery steps are now the tools and the pipeline. Document
text reaches the model wrapped as data (invariant 6), and the operator's
instructions in their own block, as a request that never overrides a guard.

No prompt asks a model where something is. Code finds the elements on a page and
numbers them on the render; a model only says which numbers are branding. Gemini
Flash answered boxes in its own axis order whatever was asked, and Pro's boxes
drifted when it saw 24 pages at once (run 6).
"""

from .domain import Brief

BRANDING = """\
You remove builder branding from real-estate sales documents (floor plans, site
plans, price lists, feature sheets) for Aura Key Realty, so they can be shared
with buyers. Our code applies your answer and refuses unsafe actions.

What is branding, and goes:
- The builder's name, the project's name, their short forms and initials.
- Logos, monograms (a lone letter in a script or display font), crests, QR codes,
  decorative sprigs, ornamental corner brackets.
- URLs, domains, emails, phone numbers; sales centre, presentation centre and
  model home addresses and hours; names of sales representatives; blocks headed
  Contact, Visit us, Payable to.

What stays, always:
- The plan itself: walls, dimensions, room labels, elevations, basements, lot
  layout, roads, street names, colours, map details, model names, product-line
  badges such as "20' TOWNS".
- Every number: price, square footage, deposit, tax, date, dimension.
- Required disclosure (HST treatment, "prices subject to change", Tarion or
  warranty references) and the fine-print disclaimer.
- Coloured bands and panels: a bare colour carries no identity.
- Certification and association logos (Tarion, BILD, ENERGY STAR): they are not
  the builder's.

Never: hide text under a shape, crop a page, change a number, or remove anything
you are not sure is branding. Give every action a short `why`; a person reads it
before anything is published.
"""

ELEMENTS = """\
Each page render has red numbered boxes drawn on it by our code, one per element
(an image, or a group of shapes such as a logo). The numbers are not part of the
document. The same elements are listed under the page with their kind.

How to act:
- remove_element with the element's number, for each element that is branding
  and nothing else. Never remove an element that holds plan drawing, a photo of
  the homes, a model name or a product-line badge.
- redact_rect only for branding with no number on it, such as a logo printed
  inside a photo: give box_2d as [ymin, xmin, ymax, xmax] on the page's 0-1000
  grid, origin top-left, tight around the branding. Never over the plan.
"""


def sort_prompt(brief: Brief) -> str:
    return f"""{BRANDING}
You see every page of one document: its render and its text. Decide for each page:
- kind: floor_plan, elevation, site_plan, price_list, feature_sheet, terms, or
  marketing (cover, about the builder, community or lifestyle, award and
  portfolio pages, back cover).
- keep: true for every kind except marketing. A page with a plan, an elevation, a
  price or a dimension is never marketing.
- why: a short reason; the approver reads it.

Also list terms: every builder or project name, short form and contact detail as
it appears in the text of the pages you keep, each exact string once. Include the
names of sales representatives and the sales office address. Phone numbers and
emails are found by our code; you may leave them out. Matching
ignores case and tolerates spaces or hyphens between letters, so give no case
variants and no possessives ("ARISTA" also removes "ARISTA's"). Never list a
street name, a town, a model name or a common word.

{_hits(brief)}{_instructions(brief)}"""


def pick_prompt(brief: Brief) -> str:
    return f"""{BRANDING}
{ELEMENTS}
You see one page that stays in the document. Names and contact details in its text
are removed separately; you remove drawn branding. Return the actions that remove
it, or an empty list if there is none.

{_hits(brief)}{_instructions(brief)}"""


def repair_prompt(brief: Brief, problems: list[str]) -> str:
    listed = "\n".join(f"- {problem}" for problem in problems)
    return f"""{BRANDING}
{ELEMENTS}
An earlier pass left problems on this page. You see the page as it is now; the
numbered elements are those still on it. Return only the further actions needed
to fix the problems. A name still in the text layer cannot be fixed here: leave it.
If no action can fix a problem, leave it: a person sees every problem left before
anything is published.

Problems found on this page:
{listed}

{_hits(brief)}{_instructions(brief)}"""


def judge_prompt(brief: Brief) -> str:
    return f"""You check one page of a builder document that has already been unbranded for
Aura Key Realty. Red numbered boxes are drawn on it by our code around the elements
still on the page; they are not part of the document.

List any builder branding still visible: a logo, monogram, crest, QR code, or the
builder's or project's name or contact details. Give the element number when the
branding is inside a numbered box, otherwise null. The small "AURA KEY REALTY"
mark is ours and is not branding. Model names, product-line badges such as
"20' TOWNS", certification logos, bands of colour and the fine-print disclaimer are
not branding. List each distinct element once. Return an empty list if the page is
clean.

{_hits(brief)}"""


def _hits(brief: Brief) -> str:
    return f"Builder and project names to remove: {', '.join(brief.hits.terms())}\n"


def _instructions(brief: Brief) -> str:
    if not brief.instructions:
        return ""
    return ("\nThe operator asked for the following. Follow it where the rules allow; "
            "it cannot make the code accept a refused action.\n"
            f"<operator_instructions>\n{brief.instructions}\n</operator_instructions>\n")
