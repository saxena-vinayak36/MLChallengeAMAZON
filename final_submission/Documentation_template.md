# ML Challenge 2026: Business Entity Resolution Solution

**Team Name:** WinKing  
**Team Members:** Update from the official portal roster if required.  
**Submission Date:** 2026-09-27

---

## 1. Executive Summary

This submission uses a deterministic, country-partitioned entity-resolution rule that
matches a Source-2 or Source-3 record to a Source-1 record only when their normalized
business-name and business-address keys are both equal.  The final version expands only
the transformations explicitly supplied in the challenge statement: legal name suffixes
(`Corp/Corporation`, `Pvt/Private`, `Ltd/Limited`), address abbreviations
(`Rd/Road`, `St/Street`), and the name connector variation (`&` versus `and`).

The final held-out macro F_0.5 is **0.141762**, up from **0.125270** for the original
exact-normalization baseline.  The generated submission passed the supplied validator
with all 1,732,544 required Source-1 rows present.

---

## 2. Methodology

### 2.1 Problem Analysis

The task is a one-to-many entity-resolution problem: each deduplicated Source-1 record
can link to zero or more records from Sources 2 and 3.  The training data contains noisy
names and addresses, including casing and punctuation changes, legal-suffix variation,
token reordering, diacritics, abbreviations, typos, missing address components, and
transliteration.  Country was treated as an open-set string partition rather than a
hard-coded list, so unseen test countries are retained in the output.

The scoring metric is macro F_0.5.  False merges are costly, especially for singleton
Source-1 records, so the submitted rule deliberately favors high-precision joint
name-and-address agreement instead of speculative fuzzy matches.

### 2.2 Solution Strategy

**Approach Type:** Deterministic exact-key blocking and matching baseline.  
**Core Innovation:** Transparent normalization using only transformations explicitly
provided by the organizers, combined with country partitioning and global exclusivity.

For every record, the pipeline:

1. Lowercases text, folds Latin diacritics while retaining Devanagari marks, tokenizes
   alphanumeric/Devanagari text, and removes literal placeholders such as `null` and
   `--`.
2. Removes only the organizer-provided legal-suffix tokens from names.
3. Drops the organizer-provided name connector `and`, because punctuation tokenization
   already removes `&`, making the two supplied forms equivalent.
4. Canonicalizes only the organizer-provided address pairs `rd -> road` and
   `st -> street`.
5. Builds order-invariant name and address token keys.
6. Matches records only when `(country, normalized_name_key, normalized_address_key)`
   is identical.
7. Enforces exclusivity greedily so one Source-2/Source-3 ID cannot be assigned to more
   than one Source-1 record.

No external entity database, API, registry, pre-trained model, or hand-authored city or
state alias list was used.

---

## 3. Candidate Generation (Blocking)

- **Blocking keys used:** exact `country`, normalized order-invariant business-name key,
  and normalized order-invariant business-address key.
- **Candidate construction:** a Source-2/Source-3 record becomes a candidate only when
  it has the same complete joint key as a Source-1 record.  The final candidate file is
  identical to the accepted-match set because this submission has no later learned
  reranker.
- **Test-scale candidate statistics:** 1,732,544 Source-1 rows; 218,189 rows with at
  least one candidate.  The candidate file is generated in the same deterministic pass
  as the accepted matches.
- **How true matches were protected:** country equality is a measured structural
  constraint in the training data, and normalization is restricted to transformations
  given by the organizers.  The conservative joint key prevents broad, unvalidated
  retrieval from entering the final match list.

---

## 4. Matching Model

**Features used:**

- Name features: normalized token equality after organizer-provided legal-suffix and
  `&`/`and` connector handling.
- Address features: normalized token equality after `Rd/Road` and `St/Street`
  canonicalization.
- Other: exact country equality and a global exclusivity constraint.

**Model type:** No learned model.  The final matcher is a deterministic exact joint-key
rule.  
**Threshold selection method:** No numerical threshold is used.  A candidate is accepted
only under complete joint-key equality; its quality was evaluated using a stratified,
held-out macro F_0.5 split.

---

## 5. Results & Error Analysis

- **Validation macro F_0.5:** `0.141762`
- **Original exact-normalization baseline:** `0.125270`
- **Validation improvement:** `+0.016492`
- **Validation by country:** US `0.160146`; India `0.114208`
- **Final output validation:** PASS — 1,732,544 rows in both required TSVs; 218,189
  non-empty predictions; no blocking format issues.

The explicit address-abbreviation normalization accounts for the large measured gain,
particularly on the US validation portion.  The final `&`/`and` connector treatment
adds a smaller positive holdout gain across both countries. Remaining false negatives
are expected from typos, transliterations, city/state aliases, domain-like names,
missing address components, and other transformations that this conservative final rule
intentionally does not guess. The main false-positive risk is a collision in the full
normalized joint key; country partitioning and global exclusivity reduce that risk.

The public-leaderboard submission of the final output was made separately.  Its score
should be recorded here once the portal reports it.

---

## 6. Conclusion

The final system is small, reproducible, and audit-friendly: it produces the two
required TSVs using only the provided dataset and explicitly permitted normalization
examples.  It delivered a substantial held-out F_0.5 gain over the original baseline
while retaining a strict precision-oriented matching rule and a validator-clean output.

---

## Appendix

### A. Code Artefacts

The ZIP contains `code/business_entity_resolution/` with:

- `src/business_entity_resolution/`: normalization, exact matcher, metric, split,
  submission writer, and validation helpers.
- `notebooks/NB02_metric_and_splits.ipynb`: recreates the stratified holdout artifacts.
- `notebooks/NB09_submission.ipynb`: evaluates the final rule on the holdout, writes
  both output TSVs, and runs the supplied validator.
- `README.md`: Python 3.12 environment and exact reproduction commands.
- `requirements.txt`: pinned dependencies.

### B. Additional Results

| Run | Holdout macro F_0.5 | Non-empty test Source-1 predictions | Validator |
| --- | ---: | ---: | --- |
| Original S2 exact baseline | 0.125270 | 193,014 | PASS |
| Organizer address-abbreviation rule | 0.141495 | 217,809 | PASS |
| Final organizer connector rule | 0.141762 | 218,189 | PASS |

The final executed NB09 notebook and its run record are retained with the project
artifacts for audit and reproduction.
