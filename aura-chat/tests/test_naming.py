"""Names in code say what the thing is, enforced rather than remembered.

The design docs label stages, phases and decisions (M2, U3, D16). Those labels
mean nothing to someone reading the code without the docs open, so they stay
in the docs. Single-letter names are the same problem at a smaller scale. The
rule is in working-rules.md; the single-letter check covers Unbrander for now,
and known-issues.md tracks extending it to the rest of the app.
"""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
DOC_LABEL = re.compile(r"\b(?:[MU][0-9]|D[0-9]{1,2})\b")
ALLOWED_SINGLE = {"i", "j", "_"}


def _code_files() -> list[Path]:
    return sorted([*APP.rglob("*.py"), *(ROOT / "scripts").glob("*.py")])


def _single_letter_files() -> list[Path]:
    return sorted([*(APP / "capabilities" / "unbrander").rglob("*.py"),
                   *(ROOT / "scripts").glob("unbrand_*.py")])


def _bound_names(source: str) -> list[tuple[int, str]]:
    """Every name the code binds: variables, loop and comprehension targets,
    arguments, `except ... as`, import aliases, functions and classes."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            found.append((node.lineno, node.id))
        elif isinstance(node, ast.arg):
            found.append((node.lineno, node.arg))
        elif isinstance(node, ast.ExceptHandler) and node.name:
            found.append((node.lineno, node.name))
        elif isinstance(node, ast.alias) and node.asname:
            found.append((node.lineno, node.asname))
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            found.append((node.lineno, node.name))
    return found


def test_no_file_is_named_after_a_doc_label():
    bad = [str(f.relative_to(ROOT)) for f in _code_files() if re.fullmatch(r"[mud][0-9]+", f.stem)]
    assert not bad, f"name these files for what they do: {bad}"


def test_no_doc_labels_in_code_or_comments():
    bad = [f"{f.relative_to(ROOT)}:{number}: {line.strip()}"
           for f in _code_files()
           for number, line in enumerate(f.read_text().splitlines(), 1)
           if DOC_LABEL.search(line)]
    assert not bad, "say it in words, or name the doc:\n" + "\n".join(bad)


def test_no_single_letter_names():
    bad = [f"{f.relative_to(ROOT)}:{line}: {name}"
           for f in _single_letter_files()
           for line, name in _bound_names(f.read_text())
           if len(name) == 1 and name not in ALLOWED_SINGLE]
    assert not bad, "use the noun the value holds:\n" + "\n".join(bad)


def test_the_checks_catch_what_they_claim():
    assert DOC_LABEL.search("the worker in U3 relies on it")
    assert DOC_LABEL.search("(D16)")
    assert not DOC_LABEL.search("U+2019 and UTF8")
    names = {name for _, name in _bound_names(
        "def f(a):\n    try:\n        x = [p for p in a]\n    except E as e:\n        pass\n")}
    assert {"f", "a", "x", "p", "e"} <= names
