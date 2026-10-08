"""The three rules from architecture.md section 4.5, enforced rather than remembered.

They hold in the shared platform (app/) and in every capability slice
(app/capabilities/<name>/), which has its own domain/, ports/ and adapters/.

Every one of these was cheap to write and would be expensive to discover the
hard way: a single adapter import in tools.py turns the "swap the data source"
migration from one file into an archaeology exercise.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"


def _imports_in(source: str, package: str) -> list[str]:
    """Every module imported, as an absolute name.

    Relative imports are resolved against `package`, or `from ..chat import tools`
    inside another capability would read as plain "chat" and slip past every rule.
    """
    out: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                out.append(node.module or "")
                continue
            base = package.split(".")[: len(package.split(".")) - (node.level - 1)]
            if node.module:
                out.append(".".join([*base, node.module]))
            else:
                # `from . import x`: x may be a submodule, so it is the import.
                out += [".".join([*base, a.name]) for a in node.names]
    return out


def _imports(path: Path) -> list[str]:
    package = ".".join(("app", *path.relative_to(APP).parts[:-1]))
    return _imports_in(path.read_text(), package)


def test_relative_imports_are_seen_as_absolute():
    """The rules below compare against `app.` names; a relative import must
    reach them in that form."""
    pkg = "app.capabilities.unbrander"
    assert _imports_in("from ..chat.tools import x", pkg) == ["app.capabilities.chat.tools"]
    assert _imports_in("from .. import chat", pkg) == ["app.capabilities.chat"]
    assert _imports_in("from .adapters import pdf", pkg) == [f"{pkg}.adapters"]
    assert _imports_in("from app.domain import Claims", pkg) == ["app.domain"]


def _layer(name: str) -> list[Path]:
    """Every file in a layer directory, shared or inside a capability."""
    return sorted(f for f in APP.rglob("*.py") if name in f.relative_to(APP).parts[:-1])


def _is_adapter(mod: str) -> bool:
    return mod.startswith("app.") and "adapters" in mod.split(".")


def _capability(f: Path) -> str | None:
    parts = f.relative_to(APP).parts
    return parts[1] if parts[0] == "capabilities" and len(parts) > 2 else None


AGENT_FRAMEWORKS = ("pydantic_ai", "langchain", "langgraph")
FORBIDDEN_IN_DOMAIN = ("fastapi", "httpx", "asyncpg", "openai", *AGENT_FRAMEWORKS)


def test_domain_imports_nothing_external():
    """domain/ is the shape of the business. A vendor type in here leaks into
    every layer above and pins them to today's stack."""
    for f in _layer("domain"):
        for mod in _imports(f):
            assert not mod.startswith(FORBIDDEN_IN_DOMAIN), f"{f.relative_to(APP)} imports {mod}"
            assert not _is_adapter(mod), f"{f.relative_to(APP)} imports {mod}"


def test_ports_declare_only_protocols():
    """A port that imports an adapter is not a seam, it is a redirect."""
    for f in _layer("ports"):
        for mod in _imports(f):
            where = f.relative_to(APP)
            assert not _is_adapter(mod), f"{where} imports {mod}"
            assert not mod.startswith(("httpx", "asyncpg", *AGENT_FRAMEWORKS)), (
                f"{where} imports {mod}")


def test_only_the_container_constructs_adapters():
    """The rule that makes PROJECT_SOURCE a one-line change."""
    allowed = {"container.py"}
    for f in sorted(APP.rglob("*.py")):
        if f.name in allowed or "adapters" in f.parts:
            continue
        for mod in _imports(f):
            assert not _is_adapter(mod), f"{f.relative_to(APP)} imports {mod}"


CHAT = APP / "capabilities" / "chat"


@pytest.mark.parametrize("capability", ["chat", "unbrander"])
def test_tools_depend_only_on_domain_and_ports(capability):
    """Written before tools.py exists, so it can never be true-by-accident."""
    tools = APP / "capabilities" / capability / "tools.py"
    if not tools.exists():
        return
    own = f"app.capabilities.{capability}"
    allowed = ("app.domain", "app.ports", f"{own}.domain", f"{own}.ports")
    for mod in _imports(tools):
        assert not mod.startswith(AGENT_FRAMEWORKS), f"{capability}/tools.py imports {mod}"
        if mod.startswith("app."):
            assert mod.startswith(allowed), f"{capability}/tools.py imports {mod}"


def test_tools_have_no_redaction_step_of_their_own():
    """Redaction is a property of the repo tools are handed, not a call they
    must remember. A `for_viewer` or `for_client` in tools.py means the guarantee
    has quietly turned back into a convention.
    """
    tools = CHAT / "tools.py"
    if not tools.exists():
        return
    body = tools.read_text()
    assert "for_viewer" not in body and "for_client" not in body


def test_only_the_container_hands_out_a_project_repo():
    """A route or tool reaching for `container.projects` directly would bypass
    the redacting wrapper — which is the one thing this design exists to make
    impossible. Everything above the container goes through projects_for().
    """
    allowed = {"container.py", "diagnostics.py"}  # diagnostics probes refresh() by design
    for f in sorted(APP.rglob("*.py")):
        if f.name in allowed or "adapters" in f.parts:
            continue
        assert ".projects." not in f.read_text(), f"{f.relative_to(APP)} uses the raw repo"


def test_the_history_window_is_the_same_number_everywhere():
    """Three copies of 20: the domain's MAX_HISTORY_TURNS, the adapter's
    MAX_HISTORY, and the port's default. The adapter keeps its own so it need
    not import domain for one integer -- which is only safe if they cannot
    drift. A smaller adapter window would silently starve the model of context
    the domain believes it is sending."""
    import re

    from app.capabilities.chat.domain import MAX_HISTORY_TURNS

    adapter = (CHAT / "adapters" / "store_postgres.py").read_text()
    assert f"MAX_HISTORY = {MAX_HISTORY_TURNS}" in adapter

    port = (CHAT / "ports" / "conversations.py").read_text()
    limits = set(re.findall(r"limit: int = (\d+)\s*\n?\s*\) -> list\[dict\]: \.\.\.", port))
    assert str(MAX_HISTORY_TURNS) in limits, f"port history() default is {limits}"


def test_the_platform_does_not_reach_into_a_capability():
    """Shared code serves every capability, so it must not depend on one. Only the
    composition root and the app factory wire capabilities in."""
    allowed = {"container.py", "main.py"}
    for f in sorted(APP.rglob("*.py")):
        if f.relative_to(APP).parts[0] == "capabilities" or f.name in allowed:
            continue
        for mod in _imports(f):
            assert not mod.startswith("app.capabilities"), f"{f.relative_to(APP)} imports {mod}"


def test_capabilities_do_not_import_each_other():
    """A capability that imports another is one capability in two folders. What
    both need belongs in the shared platform."""
    for f in sorted((APP / "capabilities").rglob("*.py")):
        own = _capability(f)
        if own is None:
            continue
        for mod in _imports(f):
            parts = mod.split(".")
            if parts[:2] == ["app", "capabilities"] and len(parts) > 2:
                assert parts[2] == own, f"{f.relative_to(APP)} imports {mod}"
