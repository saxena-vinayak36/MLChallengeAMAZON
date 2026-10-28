"""Chunked lexical blocking indexes for the constrained execution environment.

The blocker materialises only compact normalized key columns in Parquet parts.
It never builds a Python dictionary containing all Source-2/3 rows, which keeps
the S4 experiment usable on the available 8 GiB machine.
"""
from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pandas as pd

from .normalize import address_key, name_key


_SEP = "\x1f"


def key_text(key: tuple[str, ...]) -> str:
    """Encode a tuple key as a compact, collision-free control-separated string."""
    return _SEP.join(key)


def _chunk_keys(
    frame: pd.DataFrame,
    *,
    mined=None,
) -> pd.DataFrame:
    if mined is None:
        names = [name_key(v) for v in frame["business_name"]]
        addresses = [address_key(v) for v in frame["business_address"]]
    else:
        names = [mined.name_key(v) for v in frame["business_name"]]
        addresses = [mined.address_key(v) for v in frame["business_address"]]
    return pd.DataFrame(
        {
            "entity_id": frame["entity_id"].astype("string"),
            "country": frame["country"].astype("string"),
            "name_key": [key_text(k) for k in names],
            "address_key": [key_text(k) for k in addresses],
        }
    )


def write_index_parts(
    source_path: str | pathlib.Path,
    output_dir: str | pathlib.Path,
    *,
    mined=None,
    chunksize: int = 100_000,
) -> tuple[int, int]:
    """Write compact normalized Parquet parts and return ``(rows, parts)``."""
    source_path = pathlib.Path(source_path)
    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for old in output_dir.glob("part-*.parquet"):
        old.unlink()

    rows = 0
    parts = 0
    for chunk in pd.read_csv(
        source_path,
        sep="\t",
        usecols=["entity_id", "business_name", "business_address", "country"],
        dtype="string",
        keep_default_na=False,
        na_values=[],
        chunksize=chunksize,
    ):
        normalized = _chunk_keys(chunk, mined=mined)
        normalized.to_parquet(
            output_dir / f"part-{parts:06d}.parquet",
            index=False,
            compression="zstd",
        )
        rows += len(normalized)
        parts += 1
    return rows, parts


def parquet_glob(path: str | pathlib.Path) -> str:
    """Return a DuckDB-compatible glob for an index-part directory."""
    return str(pathlib.Path(path) / "part-*.parquet")
