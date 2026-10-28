"""S2 rule baseline — the first thing that goes on the leaderboard (D-13).

Rule: match a Source-2/3 record to a Source-1 entity iff they share the same **country**
AND the same **(normalized name key, normalized address key)** — i.e. exact match after
`normalize.name_key` + `normalize.address_key`. Exclusivity (§A.3, D-06) is enforced
greedily: an S2/S3 record is claimed by at most one S1.

Two strengths of this baseline that matter for calibration:

* It is precision-heavy by construction — good for the F_0.5 metric and a natural floor
  score for later stages to beat.
* Its failure modes are exactly the noise patterns §A.7 catalogs, so the residue it
  leaves behind is a direct measure of how much work S3 (normalization v1) still needs
  to do.
"""
from __future__ import annotations

import pathlib
from collections import defaultdict
from typing import Iterable

import pandas as pd

from .normalize import name_key, address_key


SOURCE_COLS = ["entity_id", "business_name", "business_address", "country"]


def read_source(path: str | pathlib.Path) -> pd.DataFrame:
    """Load a *_source*.tsv as a DataFrame with string dtypes and NaNs replaced by ''.

    Uses `keep_default_na=False` because the *literal* string `"null"` appears in the
    data and we want to treat it as a token to be filtered by `normalize`, not as a
    missing value pandas silently converts to NaN.
    """
    df = pd.read_csv(
        path,
        sep="\t",
        usecols=SOURCE_COLS,
        dtype="string",
        keep_default_na=False,
        na_values=[],
    )
    for c in SOURCE_COLS:
        df[c] = df[c].fillna("")
    return df


def build_key_index(
    df: pd.DataFrame,
) -> dict[tuple[str, tuple[str, ...], tuple[str, ...]], list[str]]:
    """Return { (country, name_key, addr_key) -> [entity_ids] } for a Source 2 or 3 frame."""
    idx: dict[tuple[str, tuple[str, ...], tuple[str, ...]], list[str]] = defaultdict(list)
    ids = df["entity_id"].to_numpy()
    names = df["business_name"].to_numpy()
    addrs = df["business_address"].to_numpy()
    countries = df["country"].to_numpy()
    for eid, nm, ad, ctry in zip(ids, names, addrs, countries):
        idx[(ctry, name_key(nm), address_key(ad))].append(eid)
    return idx


def match_source1(
    s1_df: pd.DataFrame,
    index: dict[tuple[str, tuple[str, ...], tuple[str, ...]], list[str]],
    *,
    exclusive: bool = True,
) -> dict[str, list[str]]:
    """Return { s1_entity_id -> [matched s2/s3 entity_ids] }, honouring exclusivity.

    Greedy exclusivity — when a Source-2/3 key hashes to several Source-1 rows, the
    first S1 (in `s1_df` order) claims all IDs at that key. This is intentionally the
    dumbest tiebreaker consistent with §A.3; the smarter version arrives in S8.
    """
    out: dict[str, list[str]] = defaultdict(list)
    claimed: set[str] = set() if exclusive else set()  # populated only when exclusive

    for eid, nm, ad, ctry in zip(
        s1_df["entity_id"].to_numpy(),
        s1_df["business_name"].to_numpy(),
        s1_df["business_address"].to_numpy(),
        s1_df["country"].to_numpy(),
    ):
        cands = index.get((ctry, name_key(nm), address_key(ad)), ())
        if not cands:
            continue
        if exclusive:
            fresh = [c for c in cands if c not in claimed]
            if fresh:
                out[eid].extend(fresh)
                claimed.update(fresh)
        else:
            out[eid].extend(cands)
    return dict(out)


def run_rule_baseline(
    s1_df: pd.DataFrame,
    s2_df: pd.DataFrame,
    s3_df: pd.DataFrame,
    *,
    exclusive: bool = True,
) -> dict[str, list[str]]:
    """End-to-end rule baseline over the three source frames.

    Merges S2 and S3 indices into a single lookup so the exclusivity constraint is
    applied across both — a S2 and a S3 record at the same key both get through only
    if no earlier S1 has already claimed them.
    """
    idx2 = build_key_index(s2_df)
    idx3 = build_key_index(s3_df)
    merged: dict[tuple[str, tuple[str, ...], tuple[str, ...]], list[str]] = defaultdict(list)
    for key, ids in idx2.items():
        merged[key].extend(ids)
    for key, ids in idx3.items():
        merged[key].extend(ids)
    return match_source1(s1_df, merged, exclusive=exclusive)
