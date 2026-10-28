"""End-to-end submission emission — the function `NB09_submission` calls.

Kept deliberately small so it can be reused as the smoke-test (D-18) with an
all-empty mapping.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
from typing import Iterable, Mapping

from .config import Paths
from .io_tsv import read_source_ids, write_submission_tsv


def write_pair_of_tsvs(
    paths: Paths,
    matches: Mapping[str, Iterable[str]],
    candidates: Mapping[str, Iterable[str]],
) -> tuple[int, int]:
    """Write both `matching_results.tsv` and `candidate_pairs.tsv` in the required order.

    Order = the order S1 ids appear in `test_source1.tsv`. Any test id missing from
    ``matches``/``candidates`` is written as an empty row (singleton), which is what the
    scorer expects when a Source-1 entity has no proposed matches.
    """
    s1_order = read_source_ids(paths.test / "test_source1.tsv")

    filled_matches = {s1: matches.get(s1, ()) for s1 in s1_order}
    filled_candidates = {s1: candidates.get(s1, ()) for s1 in s1_order}

    n_m = write_submission_tsv(
        paths.output / "matching_results.tsv",
        filled_matches,
        header=("source1_entity_id", "matched_entity_ids"),
        order=s1_order,
    )
    n_c = write_submission_tsv(
        paths.output / "candidate_pairs.tsv",
        filled_candidates,
        header=("source1_entity_id", "candidate_entity_ids"),
        order=s1_order,
    )
    return n_m, n_c


def run_validator(paths: Paths, check_ids: bool = False) -> tuple[int, str]:
    """Invoke the provided validator on the two output TSVs. Return (exit_code, stdout)."""
    cmd = [
        sys.executable,
        str(paths.validator),
        "--matching", str(paths.output / "matching_results.tsv"),
        "--candidate", str(paths.output / "candidate_pairs.tsv"),
        "--test-dir", str(paths.test),
    ]
    if check_ids:
        cmd.append("--check-ids")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def write_empty_submission(paths: Paths) -> tuple[int, int]:
    """Emit the trivial all-singletons submission — the S0 smoke test."""
    return write_pair_of_tsvs(paths, {}, {})
