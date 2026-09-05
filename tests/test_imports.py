"""Import-hygiene tests.

These exist because of a bug the rest of the suite structurally could not
catch. ``rimal/env/belief_wrapper.py`` imported the observation-layout
constants from ``rimal.baselines.belief``, which made the environment package
depend on the policy package and closed a cycle:

    rimal.baselines -> belief -> policies -> rimal.env.cleaning_env
                    -> rimal/env/__init__ -> belief_wrapper
                    -> rimal.baselines.belief   (partially initialised)

The cycle only fails when ``rimal.baselines`` is imported *before*
``rimal.env``. pytest happens to collect ``test_agents.py`` first, which pulls
in ``rimal.env`` via ``rimal.agents``, so every later import found the package
already loaded and the suite stayed green while ``scripts/m3_verify.py`` --
which imports the baselines first -- was broken for three milestones.

Import order is therefore its own thing to test, and it has to be tested in a
fresh interpreter: once a module is in ``sys.modules`` the cycle is invisible.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Every top-level package, in both orders that matter.
PACKAGES = [
    "rimal.config",
    "rimal.data",
    "rimal.physics",
    "rimal.env",
    "rimal.baselines",
    "rimal.eval",
    "rimal.agents",
]


def _import_in_fresh_interpreter(statement: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", statement],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )


@pytest.mark.parametrize("package", PACKAGES)
def test_each_package_imports_standalone(package: str):
    """Every package must import first, with nothing else loaded before it."""
    result = _import_in_fresh_interpreter(f"import {package}")
    assert result.returncode == 0, (
        f"importing {package} first fails:\n{result.stderr}"
    )


def test_baselines_before_env_does_not_cycle():
    """The exact order that broke scripts/m3_verify.py."""
    result = _import_in_fresh_interpreter(
        "import rimal.baselines; import rimal.env; print('ok')"
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_env_does_not_depend_on_baselines():
    """The structural rule, not just its symptom.

    The environment defines the observation; policies read it. If the env layer
    ever imports the policy layer again, the cycle comes back in some other
    import order even if today's orders happen to work.
    """
    offenders = []
    for path in (ROOT / "rimal" / "env").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # Parse imports rather than grepping text: the modules involved
            # legitimately *mention* the old dependency in comments explaining
            # why it was removed, and a text search flags those.
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "rimal.baselines"
            ):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
            elif isinstance(node, ast.Import):
                offenders += [
                    f"{path.relative_to(ROOT).as_posix()}:{node.lineno}"
                    for alias in node.names
                    if alias.name.startswith("rimal.baselines")
                ]
    assert not offenders, (
        "the env package must not import from the baselines package: " f"{offenders}"
    )


def test_observation_layout_has_one_definition():
    """The constants must be defined in the env layer and nowhere else."""
    from rimal.baselines import belief
    from rimal.env import observation

    for name in (
        "OBS_REPORTED_RATIO",
        "OBS_RAIN_SCALED",
        "OBS_NOISE_SCALED",
        "RAIN_SCALE",
        "NOISE_SCALE",
    ):
        assert hasattr(observation, name), f"{name} missing from rimal.env.observation"
        # baselines may re-export, but must not hold a second, drifting copy.
        assert getattr(belief, name) is getattr(observation, name)
