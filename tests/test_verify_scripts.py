"""Static checks on the milestone acceptance scripts.

These exist because the same bug happened twice, and both times the test suite
could not have caught it:

* ``scripts/m3_verify.py`` was broken for three milestones by an import cycle
  introduced in M5 (see ``test_imports.py``);
* ``scripts/m5_verify.py`` ran every check and then crashed unpacking its own
  results, because a ``declared`` flag was added to ``check()`` while the
  summary block that consumes ``RESULTS`` still expected the old three-tuple.

Both were edits that broke an *earlier* script, and neither was noticed because
the script was not re-run. The acceptance scripts are deliverables -- they are
the evidence each milestone is done -- so their internal consistency is worth
asserting cheaply and always, rather than only discovering it on the next
hour-long training run.

These are static checks by design: they parse the scripts rather than execute
them, so they stay fast enough to run on every commit. End-to-end execution of
the fast scripts is a separate, slower concern.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SCRIPTS = sorted((Path(__file__).resolve().parents[1] / "scripts").glob("m*_verify.py"))


def _module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def test_every_milestone_has_an_acceptance_script():
    names = {p.stem for p in SCRIPTS}
    assert names == {f"m{i}_verify" for i in range(8)}, names


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.stem)
def test_script_parses(path: Path):
    _module(path)


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.stem)
def test_results_arity_is_consistent(path: Path):
    """What ``check()`` appends must match what the summary unpacks.

    This is the exact m5_verify bug: ``check()`` grew a fourth field and the
    summary kept destructuring three, so the script did all its work and then
    raised ValueError on the last line.
    """
    tree = _module(path)

    appended: set[int] = set()
    unpacked: set[int] = set()

    for node in ast.walk(tree):
        # RESULTS.append((a, b, c[, d]))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "RESULTS"
            and node.args
            and isinstance(node.args[0], ast.Tuple)
        ):
            appended.add(len(node.args[0].elts))

        # [... for a, b, c[, d] in RESULTS ...]
        for comp in getattr(node, "generators", []):
            if (
                isinstance(comp.iter, ast.Name)
                and comp.iter.id == "RESULTS"
                and isinstance(comp.target, ast.Tuple)
            ):
                unpacked.add(len(comp.target.elts))

    assert appended, f"{path.name} never appends to RESULTS"
    assert len(appended) == 1, f"{path.name} appends differing tuple sizes: {appended}"
    assert unpacked, f"{path.name} never consumes RESULTS"
    assert unpacked == appended, (
        f"{path.name}: check() appends {appended} field(s) but the summary "
        f"unpacks {unpacked} -- the script will crash after running every check"
    )


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.stem)
def test_script_declares_its_criteria_in_the_docstring(path: Path):
    """Each script must state the criteria that were declared before it was built.

    The project's whole method is that acceptance criteria are fixed in advance;
    a script whose docstring does not carry them cannot be audited against the
    plan later.
    """
    docstring = ast.get_docstring(_module(path)) or ""
    assert "declared" in docstring.lower(), (
        f"{path.name} docstring must record the criteria declared before the "
        "milestone was built"
    )


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.stem)
def test_exit_code_is_nonzero_when_a_check_fails(path: Path):
    """A red run must exit non-zero, including for self-imposed scrutiny checks.

    A script that prints FAIL and exits 0 is worse than no check at all.
    """
    source = path.read_text(encoding="utf-8")
    assert "return 1" in source, f"{path.name} has no failing exit path"
    assert "raise SystemExit(main())" in source, (
        f"{path.name} must propagate its exit code"
    )
