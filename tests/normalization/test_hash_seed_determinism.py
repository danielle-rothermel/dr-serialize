from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SUBPROCESS_WATCHDOG_SECONDS = 60
HASH_SEEDS = ("0", "1", "4242")

SOURCE_ROOT = Path(__file__).parents[2] / "src"

NORMALIZE_SET_SCRIPT = """
import sys

from dr_serialize import (
    Serializer,
    canonical_json,
    postgres_jsonb_limits,
)

members = frozenset(
    {
        "alpha",
        "bravo",
        "charlie",
        "delta",
        "echo",
        "10",
        "2",
        "\\u00e9clair",
    }
)
serializer = Serializer(limits=postgres_jsonb_limits())
sys.stdout.write(canonical_json(serializer.to_jsonable(members)))
"""


def _normalize_set_with_seed(seed: str) -> str:
    env = {
        **os.environ,
        "PYTHONHASHSEED": seed,
        "PYTHONPATH": str(SOURCE_ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    # A fresh interpreter varies string hash randomization; timeout is a
    # watchdog.
    completed = subprocess.run(  # noqa: S603 -- fixed interpreter and in-repo code
        [sys.executable, "-c", NORMALIZE_SET_SCRIPT],
        capture_output=True,
        check=True,
        env=env,
        text=True,
        timeout=SUBPROCESS_WATCHDOG_SECONDS,
    )
    return completed.stdout


@pytest.mark.subprocess
def test_set_normalization_is_identical_across_hash_seeds() -> None:
    outputs = {seed: _normalize_set_with_seed(seed) for seed in HASH_SEEDS}

    assert outputs["0"] == (
        '["10","2","\\u00e9clair","alpha","bravo","charlie","delta","echo"]'
    )
    assert len(set(outputs.values())) == 1, outputs
