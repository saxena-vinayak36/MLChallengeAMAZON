"""Stratified train/holdout split of Source-1 entities (D-03, D-08).

Stratification: country × cardinality bucket. Cardinality is bucketed as {0,1,2,3,4,5,6+}
to match the distribution table in DECISIONS.md §A.2. Fraction is chosen to target
~150k held-out entities — that is what the holdout size argument controls.

Every random draw here takes a `seed` (default 0). Downstream notebooks pass that seed in
so the split is bit-identical across re-runs.

The full S2/S3 candidate universe is *not* materialised into these manifests — it stays
in the source TSVs, and evaluation code joins on `country`. That keeps this file cheap to
write and cheap to load.
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass

import numpy as np
import pandas as pd


CARDINALITY_BUCKETS = (0, 1, 2, 3, 4, 5, 6)  # 6 means "6+"


def bucket_cardinality(n: int) -> int:
    return n if n < 6 else 6


def load_train_manifest(
    train_source1_path: str | pathlib.Path,
    ground_truth_path: str | pathlib.Path,
) -> pd.DataFrame:
    """Return one row per training S1 entity with country + true match list + cardinality.

    Columns: entity_id, country, gt_matches (list[str]), n_true, cardinality_bucket.
    """
    src = pd.read_csv(
        train_source1_path,
        sep="\t",
        usecols=["entity_id", "country"],
        dtype={"entity_id": "string", "country": "string"},
    )
    gt = pd.read_csv(
        ground_truth_path,
        sep="\t",
        dtype={"source1_entity_id": "string", "matched_entity_ids": "string"},
    ).rename(columns={"source1_entity_id": "entity_id"})

    gt["gt_matches"] = gt["matched_entity_ids"].fillna("").apply(
        lambda s: [x for x in s.split(",") if x]
    )
    gt["n_true"] = gt["gt_matches"].str.len()
    gt = gt.drop(columns=["matched_entity_ids"])

    df = src.merge(gt, on="entity_id", how="inner")  # inner: some rows may lack GT rows
    df["cardinality_bucket"] = df["n_true"].apply(bucket_cardinality)
    return df


@dataclass(frozen=True)
class SplitResult:
    holdout: pd.DataFrame
    train: pd.DataFrame
    strata: pd.DataFrame  # (country, bucket, n_total, n_holdout, frac)


def stratified_holdout(
    manifest: pd.DataFrame,
    *,
    target_holdout: int = 150_000,
    seed: int = 0,
) -> SplitResult:
    """Stratified sample by (country, cardinality_bucket) targeting ``target_holdout`` rows.

    Uses a single fraction across strata (proportional-to-stratum-size). This preserves
    every stratum's marginal share; it does *not* balance strata, which would distort the
    macro-F_0.5 estimate the holdout is there to compute.
    """
    frac = target_holdout / len(manifest)
    if not 0 < frac < 1:
        raise ValueError(
            f"target_holdout={target_holdout} vs. manifest size {len(manifest)} "
            f"gives frac={frac}; must be in (0, 1)."
        )

    rng = np.random.RandomState(seed)
    mask = np.zeros(len(manifest), dtype=bool)
    positional = manifest.reset_index(drop=True)
    for _, grp in positional.groupby(["country", "cardinality_bucket"], observed=True):
        n_pick = int(round(frac * len(grp)))
        if n_pick <= 0:
            continue
        chosen = rng.choice(grp.index.to_numpy(), size=n_pick, replace=False)
        mask[chosen] = True

    holdout = positional.loc[mask].reset_index(drop=True)
    train = positional.loc[~mask].reset_index(drop=True)

    strata = (
        positional
        .groupby(["country", "cardinality_bucket"], observed=True)
        .size().rename("n_total").reset_index()
        .merge(
            holdout.groupby(["country", "cardinality_bucket"], observed=True)
            .size().rename("n_holdout").reset_index(),
            on=["country", "cardinality_bucket"], how="left",
        )
    )
    strata["n_holdout"] = strata["n_holdout"].fillna(0).astype(int)
    strata["frac"] = (strata["n_holdout"] / strata["n_total"]).round(4)
    return SplitResult(holdout=holdout, train=train, strata=strata)


def save_split(split: SplitResult, out_dir: pathlib.Path) -> dict:
    """Persist both manifests as parquet (D-17: no pickle). Return file paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    holdout_path = out_dir / "holdout_s1.parquet"
    train_path = out_dir / "train_s1.parquet"
    strata_path = out_dir / "split_strata.parquet"

    # gt_matches is a Python list column — pyarrow serialises it natively.
    split.holdout.to_parquet(holdout_path, index=False)
    split.train.to_parquet(train_path, index=False)
    split.strata.to_parquet(strata_path, index=False)

    return {
        "holdout": str(holdout_path),
        "train": str(train_path),
        "strata": str(strata_path),
    }
