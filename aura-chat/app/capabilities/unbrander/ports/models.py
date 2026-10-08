from typing import Protocol

from ..domain import Action, Brief, Finding, PageView, Sorting, Usage


class UnbrandModels(Protocol):
    """The model calls of the unbrand step: sort, pick, judge, repair. Each is
    one structured call; the loop around them is code (unbrand.py).

    A port so LangChain and the choice of model stay in one adapter, and
    unbrand.py is tested with a fake.
    """

    usage: dict[str, Usage]  # per role: "sort", "pick", "judge", "repair"

    async def sort(self, brief: Brief, pages: list[PageView]) -> Sorting:
        """Every page at once: what each is, which stay, the names in the text."""
        ...

    async def pick(self, brief: Brief, page: PageView) -> list[Action]:
        """The actions for one kept page, mostly numbered elements to remove."""
        ...

    async def judge(self, brief: Brief, page: PageView) -> list[Finding]:
        """Branding still visible on one output page. Findings carry its source
        page number."""
        ...

    async def repair(self, brief: Brief, page: PageView, problems: list[str]) -> list[Action]:
        """More actions for one page, given what is still wrong with it."""
        ...
