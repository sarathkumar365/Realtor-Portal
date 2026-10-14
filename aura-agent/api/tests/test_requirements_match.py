"""requirements.txt and pyproject.toml must list the same dependencies.

They exist twice for a reason that is not going away: Railway's builder copies
requirements.txt and runs pip install *before* copying the source, so it cannot
install the project itself. A duplicate list is the price. This test is what
stops it becoming a lie -- add a dependency to pyproject.toml, forget the other
file, and the service builds fine locally and dies on deploy with an ImportError
at startup. That is a bad way to find out.
"""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _pyproject_deps() -> set[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    return set(data["project"]["dependencies"])


def _requirements_deps() -> set[str]:
    lines = (ROOT / "requirements.txt").read_text().splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")}


def test_the_two_dependency_lists_agree():
    pyproject, requirements = _pyproject_deps(), _requirements_deps()
    assert requirements == pyproject, (
        "requirements.txt has drifted from pyproject.toml.\n"
        f"  only in pyproject.toml: {sorted(pyproject - requirements)}\n"
        f"  only in requirements.txt: {sorted(requirements - pyproject)}\n"
        "Regenerate requirements.txt -- the command is in its header."
    )


def test_requirements_does_not_try_to_install_the_project():
    """A bare '.' is the obvious way to avoid duplication and it does not work:
    the source is not in the build context yet when pip runs."""
    assert "." not in _requirements_deps()
