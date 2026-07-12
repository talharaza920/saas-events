"""Offline replay of recorded golden-set runs (AI_WIZARD_PLAN evals).

The live runner (scripts/eval_golden.py) records each candidate model's raw
step outputs into evals/recordings/. This test re-judges every recording with
the CURRENT schemas and fixture expectations, so schema tightening or fixture
changes that would invalidate an already-passed model fail the suite instead
of being discovered in production. It costs zero dollars and never calls a
provider. No recordings = skip (a fresh clone before any live run).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.golden import FIXTURES, check_recording

RECORDINGS_DIR = Path(__file__).resolve().parent.parent / "evals" / "recordings"
RECORDINGS = sorted(RECORDINGS_DIR.glob("*.json")) if RECORDINGS_DIR.is_dir() else []


def test_fixture_set_shape():
    """The golden set keeps its teeth: enough fixtures, planted facts, and
    null-expectation cases that a passing model actually earned it."""
    assert len(FIXTURES) >= 12
    assert sum(1 for f in FIXTURES if f.must_flag) >= 3  # planted hallucinations
    assert sum(
        1 for f in FIXTURES if any(v is None for v in f.expected.values())
    ) >= 4  # models must abstain somewhere
    assert sum(1 for f in FIXTURES if f.run_glyph) >= 2
    ids = [f.id for f in FIXTURES]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(
    "path", RECORDINGS, ids=[p.stem for p in RECORDINGS] or None
)
def test_recorded_runs_still_pass(path):
    recording = json.loads(path.read_text(encoding="utf-8"))
    failures = check_recording(recording)
    assert not failures, "\n".join(failures)


@pytest.mark.skipif(bool(RECORDINGS), reason="recordings exist")
def test_no_recordings_yet_notice():
    pytest.skip(
        "no golden-set recordings — run scripts/eval_golden.py against a live "
        "provider before switching ai_text_provider in production"
    )
