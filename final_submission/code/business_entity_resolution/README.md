# Business Entity Resolution — Reproduction Guide

This directory contains the code used to generate the accompanying final submission.
The final strategy is a deterministic, country-partitioned exact matcher using
normalized name and address keys, with only organizer-provided suffix and abbreviation
normalization.

## Requirements

- Python 3.12
- The supplied challenge data at `<project-root>/student_resource/dataset/`
- At least 8 GiB RAM and a 16 GiB swap file for the full execution used here.  A larger
  memory instance is preferable.

## Layout

```text
<project-root>/
├── student_resource/dataset/
├── artifacts/
├── output/
└── code/business_entity_resolution/
    ├── src/
    ├── notebooks/
    └── requirements.txt
```

Copy `src/`, `notebooks/`, and `requirements.txt` from this directory into the project
root (or adapt the commands below to their actual location).  The notebooks use the
`BER_ROOT` environment variable to find that root.

## Environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m ensurepip --upgrade
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Reproduce the split and final TSVs

Run from the project root, with `BER_ROOT` set to that root:

```bash
export BER_ROOT="$PWD"

jupyter nbconvert \
  --to notebook \
  --execute \
  --ExecutePreprocessor.timeout=-1 \
  --output NB02_metric_and_splits.executed.ipynb \
  code/business_entity_resolution/notebooks/NB02_metric_and_splits.ipynb

jupyter nbconvert \
  --to notebook \
  --execute \
  --ExecutePreprocessor.timeout=-1 \
  --output NB09_submission.executed.ipynb \
  code/business_entity_resolution/notebooks/NB09_submission.ipynb
```

NB02 creates the deterministic stratified holdout artifacts.  NB09 evaluates the final
rule, writes `output/matching_results.tsv` and `output/candidate_pairs.tsv`, and invokes
the supplied validator.

## Validate manually

```bash
python student_resource/utils/validate_submission.py \
  --matching output/matching_results.tsv \
  --candidate output/candidate_pairs.tsv \
  --test-dir student_resource/dataset/test
```

The expected result is `PASS — no blocking issues found.`

## Final rule

For each source record, text is lowercased and tokenized; placeholders are removed;
legal suffixes and the explicitly supplied `&`/`and` connector variation are handled in
names; and the explicitly given address abbreviations `Rd/Road` and `St/Street` are
canonicalized.
Records match only when country, normalized name key, and normalized address key are all
equal.  A Source-2/Source-3 ID is greedily assigned to at most one Source-1 entity.
