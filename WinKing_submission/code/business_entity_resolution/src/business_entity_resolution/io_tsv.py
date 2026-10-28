"""TSV read/write helpers.

Two contracts we do not want silently violated:

* Submission files are written as **literal** ``<s1>\\t<comma,joined,ids>\\n`` — no
  quoting, no escaping, no ``csv`` module. Addresses in this dataset are comma-laden
  and pandas' default quoting injects double-quotes that fail
  ``utils/validate_submission.py``. The direct write below is also immune to the
  Python 3.12 ``csv.writer`` API tightening that rejects ``quotechar=""`` (D-27).
* Reading a ``.tsv`` without ``sep="\\t"`` silently gives you one column with the whole
  line in it, so the reader lives here and no notebook builds one locally.
"""
from __future__ import annotations

import io
import pathlib
from typing import Iterable, Mapping


SOURCE_COLS = ["entity_id", "business_name", "business_address", "country"]


def read_source_ids(path: str | pathlib.Path) -> list[str]:
    """Return entity_ids from a source TSV, in file order, skipping blank lines.

    Matches the validator's `read_ids` behaviour but preserves order — we need the
    submission file's rows in the same order as `test_source1.tsv` isn't required, but
    it makes diffs across runs sensible.
    """
    ids: list[str] = []
    with open(path, encoding="utf-8") as f:
        next(f, None)  # header
        for line in f:
            if line.strip():
                ids.append(line.split("\t", 1)[0].strip())
    return ids


def write_submission_tsv(
    path: str | pathlib.Path,
    mapping: Mapping[str, Iterable[str]],
    *,
    header: tuple[str, str] = ("source1_entity_id", "matched_entity_ids"),
    order: Iterable[str] | None = None,
) -> int:
    """Write a submission-style TSV — one row per S1 entity, comma-joined ID list.

    Uses `csv.QUOTE_NONE` (D-12/D-18). Empty ID lists become an empty second field, which
    is what the validator expects for singletons.

    ``order`` is the S1-id iteration order (defaults to `mapping`'s own key order).
    Returns the number of data rows written.
    """
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if order is None:
        order = list(mapping.keys())

    n = 0
    # Direct-write approach — no csv module. Every submission row has exactly two
    # fields: an S1 id (of shape `S1-\d+`, no tabs) and a comma-joined ID list.
    # Neither can legitimately contain a tab or a newline; anything else in them is
    # a bug worth surfacing before it hits disk. Immune to the Python 3.12 csv
    # quotechar-must-be-nonempty tightening (D-27).
    buf = io.StringIO()
    buf.write(f"{header[0]}\t{header[1]}\n")
    for s1 in order:
        ids = mapping.get(s1, ())
        joined = ",".join(ids)
        if "\t" in s1 or "\t" in joined or "\n" in s1 or "\n" in joined:
            raise ValueError(f"tab or newline in submission field for {s1!r}")
        buf.write(f"{s1}\t{joined}\n")
        n += 1

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(buf.getvalue())
    return n
