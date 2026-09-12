"""The browser simulator must stay a faithful port of the engine.

``web/simulator.html`` is a second implementation of the physics, and its data
is a snapshot of the engine's. Both can drift silently: a constant changed in
``rimal/`` but not in the port, or a data-layer fix (the lead-in year, the
rainfall units) that the exported snapshot never picked up. These tests make
that drift fail the suite rather than wait for someone to notice a number.

Both need the parquet caches (data + energy table), so they carry the
``network`` marker like ``test_env.py``: on a cold clone they fetch, and
afterwards they run offline. The second also needs ``node`` and is skipped
without it -- skipped, not passed, so the report says which.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


@pytest.mark.network
def test_shipped_simulator_data_is_what_the_engine_produces():
    """``export_sim_data.py --check`` must find nothing stale."""
    result = _run("export_sim_data.py", "--check")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.network
@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_shipped_simulator_physics_agrees_with_the_engine():
    """``verify_simulator.py`` must pass every check against the shipped file."""
    result = _run("verify_simulator.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SIMULATOR VERIFIED" in result.stdout


@pytest.mark.network
@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_site_physics_module_agrees_with_the_engine():
    """The site's ES-module port must pass the same harness, plus guarded/ppo."""
    result = _run("verify_simulator.py", "--module", "site/src/lib/physics/rimal.js")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SIMULATOR VERIFIED" in result.stdout
