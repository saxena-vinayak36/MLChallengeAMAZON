# Business Entity Resolution Challenge — Project Plan

> **Revision 3 (2026-09-26).** Restructured around *steps and an exploration surface*
> rather than a clock. The goal is to search models and parameters systematically and
> keep the best result. Reasoning for each choice lives in [`DECISIONS.md`](DECISIONS.md).

## 0. Purpose and Standing Rules

This is the working reference: what to build, in what order, and what to sweep at each
point. It is a direction, not a procedure — when evidence contradicts it, deviate,
record why in `DECISIONS.md`, and update this file.

**Four rules that hold across every edit from here on:**

1. **Author locally, execute on AWS.** This laptop writes code. **No stage that touches
   the real dataset runs on this laptop.** The current EC2 runner runs the code (or
   SageMaker if it is later restored), and the outputs it
   prints (metrics, timings, validator exit codes) are what get pasted back into this
   session and logged. Local execution is limited to (a) importing a module to confirm
   it parses, (b) unit tests on hand-authored inputs (like the F_0.5 worked example),
   (c) sub-second sanity checks on ≤10-row slices — never full-scale runs. See D-24.
2. **Always shippable.** After any change to any notebook, `NB09_submission` must still
   run end-to-end on the target AWS runtime and produce `output/matching_results.tsv` +
   `output/candidate_pairs.tsv` that pass `utils/validate_submission.py`. A change that
   breaks the submission path is not finished, however good the offline number.
3. **Notebooks are SageMaker-portable.** Everything is written so a notebook can be
   copy-pasted from the local IDE into a SageMaker JupyterLab space and run unchanged.
   Paths, environment and compute size come from the config cell (§4.2), never from
   hardcoded local paths.
4. **Every experiment is logged.** Config in, metrics out, one row per run in
   `artifacts/runs.jsonl` on the AWS side. When rows arrive back in this session's
   response text they are appended here too. An unlogged experiment did not happen —
   with this many sweep axes (§6), memory is not a reliable record of what was tried.

## 1. Problem Summary

Three independent sources contain noisy, partially overlapping business records with no
shared identifiers. Source 1 is the deduplicated reference; find every Source 2/3 record
referring to the same real-world business as each Source 1 entity. Evaluation is
macro-averaged F_0.5 per Source 1 entity.

### 1.1 Measured scale

| | Source 1 | Source 2 | Source 3 |
|---|---|---|---|
| train rows | 2,206,821 | 5,034,616 | 5,285,603 |
| test rows | 1,732,544 | 4,887,273 | 5,082,316 |

**7,638,365 labelled positive pairs.** At K≈25 candidates/entity, test-time scoring is
**~43M pairs** — the number that decides which models can sit at which stage.

### 1.2 Match cardinality

| true matches | 0 | 1 | 2 | 3 | 4 | 5 | 6+ |
|---|---|---|---|---|---|---|---|
| share of S1 | 5.6% | 5.4% | 17.0% | 24.1% | 21.9% | 14.6% | 11.4% |

**Mean 3.46.** "Always predict empty" scores **0.056**.

### 1.3 Structural facts

- **Matches are strictly exclusive** — 0 duplicates across all 7,638,365 matched IDs.
- **Matches never cross country** — 0 cross-country pairs in 693,069 checked.
- **~74% of Source 2/3 records are matched to something.**
- Test mix: ~38% US, ~47% India, **~15% France** (absent from training).

### 1.4 Noise profile

On true pairs: name-token Jaccard mean 0.607 / median 0.667, **14.9% share zero name
tokens**. Address Jaccard mean 0.611, 4.6% share zero. But **0 of 10,980 true pairs
shared no token in *either* field** — a name ∪ address lexical blocker has a recall
ceiling near 100%.

The corruption is synthetic, and its vocabulary is finite:

| Pattern | Observed example |
|---|---|
| Transliteration | `Tech Engineering Pvt Ltd` ↔ `टेक इंजीनियरिंग प्रा. लि.` |
| Diacritic injection | `Cao Assets` ↔ `Cao Ássets`; `BLUE PÉDIATRICS` |
| OCR-style typo | `New Delhi` ↔ `New De1hi`; `Assets` ↔ `Aofianehs` |
| Legal-suffix drop | `Blue Pediatrics LLC` ↔ `Blue Pediatrics` |
| Token reordering | `769 Sir Philip Dr, Salt Lake City, UT` ↔ `Salt Lake City, Utah, 769 Sir Philip Dr` |
| City aliasing | Mumbai ↔ Bombay; Mechanicsburg CDP ↔ Lower Allen Township |
| State abbreviation | Maharashtra ↔ MH; Utah ↔ UT; Delhi ↔ DL |
| Zero-padding / truncation | `3415` ↔ `03415`; `769` ↔ `69` |
| Placeholders | `null` literals, `--` prefixes, empty addresses |
| Domain-ification | `New Delhi Software Private Limited` ↔ `newdelhisoftware.com` |
| Honorific injection | `Tech Engineering Pvt Ltd` ↔ `Dr Tech Engineering Pvt Ltd` |

Because it is generative and we hold 7.6M labelled examples, these transformations can
be **mined as statistics from training data** rather than hand-authored — more complete
than a manual list, and compliant with the fair-play rules.

### 1.5 How the metric actually behaves

For an entity with 4 true matches:

| prediction | precision | recall | F_0.5 |
|---|---|---|---|
| all 4, plus 1 false positive | 0.80 | 1.00 | **0.833** |
| the 2 most confident | 1.00 | 0.50 | **0.833** |
| only the single best | 1.00 | 0.25 | **0.625** |

With mean 3.46 matches and only 5.6% singletons, recall is expensive to surrender and
the entire singleton bonus caps at **5.6 points**. **Tune the threshold numerically
against the real metric; carry no prior that it should be high.**

## 2. Constraints

- **No external data or lookups.** No ER APIs, registries, geocoding, or internet data —
  including hand-authored reference lists (abbreviations, city aliases). Normalization
  comes from patterns mined out of the training data, language-agnostic string metrics,
  or the zero-shot behaviour of a licensed pretrained model. The five examples in the
  problem statement (Corp/Corporation, Pvt/Private, Ltd/Limited, Rd/Road, St/Street) are
  organizer-provided and fine to use.
- **Model licence: MIT or Apache-2.0, ≤8B parameters.** Verify on the model card itself,
  not a secondary source — §6.4 lists shortlisted models *and* the near-miss traps.
- **Country is an open label set.** No branch keyed to a country string; partition by
  whatever values appear, with a tested path for an unseen label.
- **Output format.** Exactly 1,732,544 rows (one per test S1 entity); S2-/S3- IDs only,
  all present in the test set; no duplicate IDs within a list or duplicate
  `source1_entity_id` rows. Write with `quoting=csv.QUOTE_NONE` — addresses are
  comma-laden and default pandas quoting will fail validation.
- **`candidate_pairs.tsv` is the last candidate set before final scoring** — with a
  cascade, that is the top-K set handed to the reranker, not raw blocking output.

## 3. Architecture

```
lexical blocking  →  GBM scorer  →  neural reranker  →  exclusivity-constrained
(country-            (~43M pairs,    (top-K/entity,      assignment + singleton
 partitioned)         tabular)        ~5-9M pairs)        decision
      │                    │                │                      │
  recall@K,           P/R on           ΔF_0.5 vs.            macro F_0.5
  reduction ratio     candidates       GBM alone             (the real metric)
```

Each stage owns a metric. Nothing advances until the current stage's number exists —
with a large sweep surface, per-stage metrics are what make it possible to attribute a
gain to the change that caused it.

## 4. Repository and Notebook Layout

### 4.1 Structure

```
Working Folder/
├── Plan_ML_Challenge.md
├── DECISIONS.md
├── notebooks/
│   ├── NB00_setup.ipynb              # env detect, paths, deps, smoke test
│   ├── NB01_eda.ipynb                # done — reproduces §1 facts
│   ├── NB02_metric_and_splits.ipynb  # F_0.5 impl + holdout construction
│   ├── NB03_normalization.ipynb      # mine the noise model → alias tables
│   ├── NB04_blocking.ipynb           # candidate generation + recall@K sweep
│   ├── NB05_features.ipynb           # pair features + ablation
│   ├── NB06_model_gbm.ipynb          # GBM family sweep
│   ├── NB07_model_neural.ipynb       # embedder + reranker sweep
│   ├── NB08_decision_layer.ipynb     # threshold, assignment, singletons
│   ├── NB09_submission.ipynb         # ← must always run green
│   └── NB10_error_analysis.ipynb     # breakdowns, hard cases
├── src/business_entity_resolution/   # functions the notebooks import
├── artifacts/                        # parquet intermediates + runs.jsonl
├── output/                           # the two submission TSVs
└── student_resource/                 # given data + validator
```

Notebooks orchestrate and visualise; **real logic lives in `src/`** and is imported. This
keeps the submission package's `code/business_entity_resolution/src/` genuinely runnable
rather than a pile of exported cells, and lets a notebook be re-run after a fix without
re-executing everything above it.

### 4.2 SageMaker portability

Every notebook opens with the same config cell:

```python
# --- config cell: identical across notebooks ---
import os, sys, pathlib
ON_SAGEMAKER = pathlib.Path("/opt/ml").exists() or "SM_CURRENT_HOST" in os.environ
ROOT = pathlib.Path("/home/ec2-user/SageMaker/ber") if ON_SAGEMAKER else pathlib.Path("/Users/pocketfm/Desktop/amazon_ML/Working Folder")
DATA, ART, OUT = ROOT/"student_resource/dataset", ROOT/"artifacts", ROOT/"output"
sys.path.insert(0, str(ROOT/"src"))
for p in (ART, OUT): p.mkdir(parents=True, exist_ok=True)
N_JOBS = os.cpu_count()
```

Rules that keep copy-paste working:

- **No hardcoded absolute paths** outside the config cell.
- **Parquet for intermediates**, never pickle — pickles break across library versions and
  do not survive the local→SageMaker hop.
- **Stage artifacts are self-describing**, so each notebook can start from disk without
  re-running its predecessors. This is what makes a sweep practical.
- **One dependency cell at the top of `NB00`**, pinned, mirrored into `requirements.txt`.
- **Derive parallelism from the instance** (`os.cpu_count()`, `torch.cuda.is_available()`)
  rather than assuming a machine.

## 5. Stages

Ordered by dependency, not by clock. Each stage has an exit criterion — meet it and move
on; the sweeps in §6 are where the remaining time goes.

| # | Stage | Notebook | Exit criterion |
|---|---|---|---|
| **S0** | Environment + data staging; validator smoke test | NB00 | A dummy all-empty submission passes the validator |
| **S1** | Exact macro-F_0.5; stratified holdout by country × cardinality | NB02 | Unit test reproduces the statement's worked example (**0.714**) |
| **S2** | Rule baseline end-to-end → **first leaderboard upload** | NB09 | Valid submission on the board; local-vs-leaderboard offset known |
| **S3** | Mine the noise model → normalization v1 | NB03 | Alias tables materialised; coverage on the 14.9% zero-name-overlap tail measured |
| **S4** | Blocking + recall@K sweep | NB04 | ≥97% recall at a K the downstream stages can afford |
| **S5** | Pair features + grouped ablation | NB05 | Per-group ΔF_0.5 known |
| **S6** | GBM sweep + threshold tuning | NB06 | Best GBM config logged; **upload #2** |
| **S7** | Neural stage: embedder and reranker sweep | NB07 | Either a logged gain over GBM-alone, or a logged decision not to ship it |
| **S8** | Decision layer: threshold, exclusivity assignment, singletons | NB08 | Each component's delta measured independently |
| **S9** | Error analysis → feeds back into S3–S8 | NB10 | Error taxonomy by type × country × source × cardinality |

**S2 comes before all modelling on purpose.** It de-risks the output format early
(comma-laden addresses + default pandas quoting is a real rejection mode), and it turns
the public leaderboard into a second validation signal for the rest of the work.

**S9 is a loop, not a terminus.** Error analysis output should send you back into S3–S8
with a specific hypothesis, not just produce a chart.

## 6. Exploration Surface

This is the centre of the project. Everything above exists so that this can be searched
efficiently. Sweep breadth-first — a cheap knob's best value is usually stable under
later changes, so lock the cheap ones early and spend the remaining budget on §6.4.

### 6.1 Normalization (NB03)

| Axis | Values |
|---|---|
| variant | `v0` raw · `v1` mined aliases · `v2` v1 + transliteration map · `v3` v2 + char-confusion repair |
| case/diacritic folding | on / off (ablate separately — it may help name and hurt address) |
| suffix handling | keep · strip · strip-but-keep-as-feature |
| mined-table confidence cutoff | min support 3 / 10 / 50 occurrences |
| apply to | name only · address only · both |

Features should be computed on **both raw and normalized** forms, letting the model
decide which to trust rather than committing to one.

### 6.2 Blocking (NB04)

| Axis | Values |
|---|---|
| index type | IDF-weighted token · char-trigram TF-IDF · numeric address tokens · **union** |
| char n-gram range | (2,3) · (2,4) · (3,4) · (3,5) |
| K per entity | 10 · 20 · 30 · 50 · 100 |
| IDF floor for token index | drop top 0.1% / 1% most common tokens |
| similarity cutoff | absolute vs. top-K-only |
| dense retrieval added to union | off · on (see §6.4 embedders) |

**Judge on the recall@K vs. candidates-per-entity curve, per country**, and pick the
knee. Blocking sets the recall ceiling for everything downstream, so this sweep has the
highest leverage of any in this section.

### 6.3 Features (NB05)

Groups, ablated as units rather than individually:

- **N — name similarity:** normalized edit distance, Jaro-Winkler, token sort/set ratio,
  token Jaccard, TF-IDF cosine (word + char), bigram/trigram Dice, LCS ratio.
- **A — address similarity:** same metrics on address strings. **Strictly structural
  parsing** — no ZIP/PIN regexes, which are exactly what breaks on unseen French
  layouts. Use generic `standalone_numeric_tokens` extraction and numeric-subset overlap.
- **X — cross-field:** country equality (generic predicate), length and token-count deltas.
- **R — retrieval:** blocking score and rank carried forward.
- **G — group-relative:** score vs. best and second-best sibling candidate for the same
  entity. At mean 3.46 matches, these are what separate "4th real match" from "1st false
  positive" — expect this group to matter more than its size suggests.
- **I — IDF-weighted overlap:** a shared rare token should outweigh a shared `Inc`.

Use `rapidfuzz`; at ~43M pairs the implementation choice is the difference between
minutes and hours.

### 6.4 Models

**Tier 1 — GBM over tabular features (NB06).** Scores all candidates.

| Axis | Values |
|---|---|
| library | LightGBM (MIT) · XGBoost (Apache-2.0) · CatBoost (Apache-2.0) |
| `num_leaves` / `max_depth` | 31 · 63 · 127 · 255 |
| `min_data_in_leaf` | 20 · 100 · 500 |
| `learning_rate` × `n_estimators` | 0.1×500 · 0.05×1500 · 0.02×4000 |
| `feature_fraction` / `bagging_fraction` | 0.6 · 0.8 · 1.0 |
| `lambda_l2` | 0 · 1 · 10 |
| negative sampling ratio | 1:3 · 1:10 · all blocking negatives |
| `scale_pos_weight` | 1 · balanced |
| objective | binary · **LambdaRank grouped by S1 entity** |

The ranking objective is worth real attention: the task is per-entity ranking with a
cutoff, not independent binary classification, and grouping by `source1_entity_id` is
closer to what the metric measures.

**Tier 2 — neural reranker over top-K (NB07).** Only candidates that survive Tier 1.

| Axis | Values |
|---|---|
| base model | `BAAI/bge-reranker-v2-m3` (568M) · `BAAI/bge-reranker-base` (278M) · `Qwen/Qwen3-Reranker-0.6B` · `Qwen/Qwen3-Reranker-4B` · `mixedbread-ai/mxbai-rerank-base-v2` |
| top-K reranked | 3 · 5 · 10 |
| max sequence length | 64 · 128 · 256 |
| **pair serialization** | name-only · `name ‖ address` · templated (`Business: {n}. Address: {a}. Country: {c}`) · normalized vs. raw |
| negatives per positive in fine-tuning | 3 · 7 · 15 (hard negatives from blocking) |
| LR × epochs | 1e-5×1 · 2e-5×2 · 5e-6×3 |
| blending with GBM score | reranker-only · mean · logistic stacker |

**Pair serialization is underexplored by most teams and cheap to sweep** — how the two
records are rendered into a string materially changes reranker accuracy, often more than
swapping the base model does.

**Retrieval embedders (NB07, feeding §6.2 and features).**

| Candidate | Size | Notes |
|---|---|---|
| `BAAI/bge-m3` | 568M | Strong multilingual; handles Devanagari |
| `Qwen/Qwen3-Embedding-0.6B` / `-4B` | 0.6B / 4B | Both within the 8B cap |
| `ibm-granite/granite-embedding-278m-multilingual` | 278M | Cheapest to run at 12M records |
| `intfloat/multilingual-e5-large` | 560M | Well-established multilingual baseline |
| `sentence-transformers/LaBSE` | 471M | Explicitly translation-aligned — a natural fit for the transliteration tail |

> **Licence traps — check the card, do not assume.** `jina-embeddings-v3` and
> `jina-reranker-v2-base-multilingual` are **CC-BY-NC**, which fails the MIT/Apache-2.0
> requirement despite being obvious shortlist candidates. Several strong rerankers are
> similarly non-commercial. Record the verified licence for every model actually used in
> `DECISIONS.md` before it enters the pipeline, not at packaging time.

### 6.5 Decision layer (NB08)

| Axis | Values |
|---|---|
| threshold scope | global · per-country · per-cardinality-prediction |
| assignment | independent · greedy-by-score exclusive · Hungarian/bipartite |
| max predictions per entity | uncapped · capped at 6 · learned per entity |
| singleton handling | same threshold · dedicated abstain rule |
| calibration | none · Platt · isotonic |

Exclusivity is a **measured fact** (§1.3), not a hypothesis — but whether greedy or
optimal assignment is worth the runtime is genuinely open.

### 6.6 Generalization checks (NB10)

Run alongside, not as a search objective: one leave-one-country-out run (train US →
validate India) as a *feature sensitivity filter* — a feature group that helps the
holdout but collapses LOCO is memorizing country artifacts. Plus a France
score-distribution comparison on unlabelled test records, and a crash check on an unseen
country label.

## 7. Answered Questions

Resolved; do not re-litigate without new evidence (revisit triggers are in `DECISIONS.md`).

| Question | Answer | Evidence |
|---|---|---|
| Do matches ever cross country labels? | **No** | 0 of 693,069 pairs checked |
| Are S2/S3 records exclusive to one S1 match? | **Yes, strictly** | 0 duplicates across 7,638,365 matched IDs |
| Where is the blocking recall ceiling? | **~100% for name ∪ address**; name-only caps at ~85% | 0/10,980 share no token in either field; 14.9% share no name token |
| Is a mined normalization table worth building? | **Yes — top non-blocking lever** | It is what converts the 14.9% zero-name-overlap tail into matchable pairs |
| Which features pass CV but collapse under LOCO? | **Open** | Resolved at S9 |

## 8. Revision Log

- **Rev 4 — 2026-09-27.** Corrected the operational wording to EC2-first. S3/S4
  experiments on the available 8 GiB runner must be memory-bounded, batched pilots;
  they do not relax the S4 full-holdout ≥97% recall gate.
- **Rev 3 — 2026-09-26.** Restructured around stages (§5) and an explicit exploration
  surface (§6) instead of an hour-by-hour schedule. Added notebook layout and SageMaker
  portability contract (§4). Added the always-shippable standing rule (§0). Compute
  budgeting removed from the plan body — it was sizing context, not the objective.
- **Rev 2 — 2026-09-26.** Rewritten after direct data profiling: measured scale,
  cardinality, exclusivity, cross-country and noise profile; corrected metric framing;
  Section 6 converted from open questions to answers; `DECISIONS.md` created.
- **Rev 1.** Initial plan. Architecture and per-stage-metric discipline carried forward;
  scale and metric framing superseded.
