"""The three rules from architecture.md section 4.5, enforced rather than remembered.

Every one of these was cheap to write and would be expensive to discover the
hard way: a single adapter import in tools.py turns the "swap the data source"
migration from one file into an archaeology exercise.
"""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module)
    return out


def _py(sub: str) -> list[Path]:
    return sorted((APP / sub).rglob("*.py")) if (APP / sub).exists() else []


FORBIDDEN_IN_DOMAIN = ("fastapi", "httpx", "asyncpg", "pydantic_ai", "openai", "app.adapters")


def test_domain_imports_nothing_external():
    """domain/ is the shape of the business. A vendor type in here leaks into
    every layer above and pins them to today's stack."""
    for f in _py("domain"):
        for mod in _imports(f):
            assert not mod.startswith(FORBIDDEN_IN_DOMAIN), f"{f.name} imports {mod}"


def test_ports_declare_only_protocols():
    """A port that imports an adapter is not a seam, it is a redirect."""
    for f in _py("ports"):
        for mod in _imports(f):
            assert not mod.startswith("app.adapters"), f"{f.name} imports {mod}"
            assert not mod.startswith(("httpx", "asyncpg", "pydantic_ai")), f"{f.name} imports {mod}"


def test_only_the_container_constructs_adapters():
    """The rule that makes PROJECT_SOURCE a one-line change."""
    allowed = {"container.py"}
    for f in sorted(APP.rglob("*.py")):
        if f.name in allowed or "adapters" in f.parts:
            continue
        for mod in _imports(f):
            assert not mod.startswith("app.adapters"), f"{f.relative_to(APP)} imports {mod}"


def test_tools_depend_only_on_domain_and_ports():
    """Written before tools.py exists, so it can never be true-by-accident."""
    tools = APP / "tools.py"
    if not tools.exists():
        return
    for mod in _imports(tools):
        if mod.startswith("app."):
            assert mod.startswith(("app.domain", "app.ports")), f"tools.py imports {mod}"


def test_tools_have_no_redaction_step_of_their_own():
    """Redaction is a property of the repo tools are handed, not a call they
    must remember. A `for_viewer` or `for_client` in tools.py means the guarantee
    has quietly turned back into a convention.
    """
    tools = APP / "tools.py"
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

    from app.domain import MAX_HISTORY_TURNS

    adapter = (APP / "adapters" / "store_postgres.py").read_text()
    assert f"MAX_HISTORY = {MAX_HISTORY_TURNS}" in adapter

    port = (APP / "ports" / "conversations.py").read_text()
    limits = set(re.findall(r"limit: int = (\d+)\s*\n?\s*\) -> list\[dict\]: \.\.\.", port))
    assert str(MAX_HISTORY_TURNS) in limits, f"port history() default is {limits}"
