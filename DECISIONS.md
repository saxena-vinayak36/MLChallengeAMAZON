# Decision Log — Business Entity Resolution Challenge

**Two audiences, one file.**

1. **The challenge write-up.** §C maps every entry onto a section of
   `student_resource/Documentation_template.md`, so producing the required methodology
   document is assembly rather than authoring.
2. **Future me.** Every entry records what was *rejected* and what evidence would
   justify reopening it. A decision without its rationale gets re-litigated by whoever
   picks this up next — including a later session of the same person — at full cost.

**Rules for this file**

- **Append-only.** Never delete a decision. When one is overturned, mark it
  `⚠ Superseded by D-NN` and write the successor. When only the reasoning changed, add an
  `Amended` line. The reversals *are* the record — D-09 and D-15 exist precisely because
  earlier calls were wrong.
- **Every number cites its method**, so it can be re-verified rather than trusted.
- **Nothing claimed that has not run.** Entries about future work are `Planned`.

Companion to [`Plan_ML_Challenge.md`](Plan_ML_Challenge.md), which says *what* to build
and *what to sweep*. This file says *why*.

---

## §A — Measured Facts

All measured 2026-09-26 against `student_resource/dataset/`, reproducible in `NB01_eda`.

### A.1 Scale

| | Source 1 | Source 2 | Source 3 |
|---|---|---|---|
| train rows | 2,206,821 | 5,034,616 | 5,285,603 |
| test rows | 1,732,544 | 4,887,273 | 5,082,316 |

*Method:* `wc -l` per file, minus header.

**7,638,365 labelled positive pairs** — *method:* count of comma-split IDs across
`train_ground_truth.tsv`.

**Implication:** at K≈25, test scoring is ~43M pairs. This decides which model can sit
at which stage, and is the figure the first plan revision never computed.

### A.2 Match cardinality

| true matches | 0 | 1 | 2 | 3 | 4 | 5 | 6+ |
|---|---|---|---|---|---|---|---|
| share of S1 | 5.6% | 5.4% | 17.0% | 24.1% | 21.9% | 14.6% | 11.4% |

**Mean 3.46.** "Always predict empty" = **0.056**.

*Method:* full pass over `train_ground_truth.tsv`, counting IDs per row.

### A.3 Exclusivity

**0 duplicate IDs across all 7,638,365 matched IDs.** Strict 1:many.

*Method:* full pass inserting every matched ID into a set; `len(set) == total count`.

### A.4 Country

**0 cross-country matches** in 693,069 ground-truth pairs checked.

*Method:* loaded `entity_id → country` for all 12.5M training records, compared each S1
entity's country against each of its matches over the first 200k ground-truth rows.

Test mix (first 200k rows per source): **~38% US, ~47% India, ~15% France.** France is
absent from training.

### A.5 Coverage

**~74% of all Source 2/3 records are matched to something** (7.64M / 10.32M training
S2+S3 records).

### A.6 Noise profile on true pairs

*Method:* 3,000 randomly sampled ground-truth entities (seed 0) → 10,980 true pairs;
lowercase, strip non-alphanumeric (Latin + Devanagari retained), token-Jaccard.

| Metric | Value |
|---|---|
| Exact normalized name match | 27.5% |
| Name-token Jaccard, mean / median | 0.607 / 0.667 |
| **True pairs sharing zero name tokens** | **14.9%** |
| Address-token Jaccard, mean | 0.611 |
| True pairs sharing zero address tokens | 4.6% |
| **True pairs sharing zero tokens in *either* field** | **0.0% (0 / 10,980)** |

**Implication:** name-only blocking caps at ~85% recall; name ∪ address reaches ~100%.

### A.7 Corruption vocabulary

Observed directly in sampled true pairs. The corruption is **synthetic and generative** —
a finite transformation set applied programmatically — which is what makes D-05 viable.

| Pattern | Observed example |
|---|---|
| Transliteration | `Tech Engineering Pvt Ltd` ↔ `टेक इंजीनियरिंग प्रा. लि.` |
| Diacritic injection | `Cao Assets` ↔ `Cao Ássets`; `BLUE PÉDIATRICS LLC` |
| OCR-style typo | `New Delhi` ↔ `New De1hi`; `Assets` ↔ `Aofianehs` |
| Legal-suffix drop | `Blue Pediatrics LLC` ↔ `Blue Pediatrics` |
| Token reordering | `769 Sir Philip Dr, Salt Lake City, UT` ↔ `Salt Lake City, Utah, 769 Sir Philip Dr` |
| City aliasing | Mumbai ↔ Bombay; Mechanicsburg CDP ↔ Lower Allen Township |
| State abbreviation | Maharashtra ↔ MH; Utah ↔ UT; Delhi ↔ DL |
| Zero-padding / truncation | `3415` ↔ `03415`; `769` ↔ `69` |
| Placeholders | `null` literals, `--` prefixes, empty address fields |
| Domain-ification | `New Delhi Software Private Limited` ↔ `newdelhisoftware.com` |
| Honorific injection | `Tech Engineering Pvt Ltd` ↔ `Dr Tech Engineering Pvt Ltd` |

### A.8 Metric behaviour

For an entity with 4 true matches:

| prediction | precision | recall | F_0.5 |
|---|---|---|---|
| all 4, plus 1 false positive | 0.80 | 1.00 | **0.833** |
| the 2 most confident | 1.00 | 0.50 | **0.833** |
| only the single best | 1.00 | 0.25 | **0.625** |

With A.2 (mean 3.46, only 5.6% singletons), this is the basis for D-04.

---

## §B — Decision Log

### D-01 — Four-stage cascade architecture
**Status:** Accepted · **Feeds:** Doc §2.2

**Question:** What is the overall pipeline shape?

**Evidence:** A.1 — ~43M pairs at inference. Applying an expensive scorer to all of them
is infeasible; applying only a cheap one leaves signal on the table.

**Decision:** Lexical blocking → GBM on tabular features → neural reranker on top-K →
exclusivity-constrained assignment. Each stage owns a metric.

**Rationale:** Scrutiny rises as volume falls — ~43M cheap scores, ~5–9M expensive ones.
Per-stage metrics are what let a gain be attributed to the change that caused it, which
matters more than usual given the size of the sweep surface in Plan §6.

**Rejected:** End-to-end neural matching (no way to attribute gains, and retraining per
sweep point is prohibitive). Graph/clustering formulation — A.3 shows strict 1:many, so
there is no transitive structure to exploit.

**Revisit if:** blocking recall lands below ~95%, meaning the ceiling is the bottleneck
rather than the scorer.

---

### D-02 — Lexical union blocking as the primary index
**Status:** ⚠ **Amended by D-15** (dense retrieval moved from *rejected* to *sweep axis*;
lexical-as-default stands) · **Feeds:** Doc §3

**Question:** Should candidate generation be lexical, dense, or both?

**Evidence:** A.6 — **0 of 10,980 true pairs shared no token in either field.** Lexical
recall ceiling ~100%. Separately, 14.9% share no *name* token, so name-only caps at ~85%.

**Decision:** IDF-weighted inverted index over name **and** address tokens, unioned with
char-trigram TF-IDF cosine and standalone numeric address tokens. Country-partitioned.

**Rationale:** The union reaches the ceiling with no model, no GPU and no training, which
makes it the right *baseline* — every other retrieval method is measured as a delta
against it rather than adopted on reputation.

**Rejected:** Name-only blocking (caps at ~85%). Phonetic blocking as a separate pass —
Soundex/Metaphone are Latin-script-centric and do nothing for the transliteration tail
that constitutes the hard cases; D-05 covers it better.

**Revisit if:** measured recall@K is below 97% at K≈30, or the France partition
underperforms.

---

### D-03 — Single stratified holdout instead of k-fold CV
**Status:** Accepted · **Feeds:** Doc §4

**Question:** What validation scheme?

**Evidence:** A.1 — 2,206,821 training S1 entities.

**Decision:** One stratified holdout of ~150k S1 entities, by country × cardinality
bucket, carrying their full S2/S3 candidate universe.

**Rationale:** k-fold controls variance when data is scarce. At 150k held-out entities
the standard error on macro-F_0.5 is negligible, so 5-fold buys effectively nothing for
5× the runtime per sweep point — and the sweep surface is large enough that per-point
cost directly determines how much of it gets explored.

**Rejected:** 5-fold CV; nested CV with threshold selection inside each fold.

**Revisit if:** holdout and leaderboard diverge by more than ~0.02, suggesting the split
is unrepresentative.

---

### D-04 — Tune the threshold numerically; reject the "precision-heavy ⇒ be conservative" prior
**Status:** Accepted · **Feeds:** Doc §4

**Question:** How aggressive should the matching threshold be, given F_0.5 weights
precision 2× over recall?

**Evidence:** A.2 and A.8. Mean 3.46 true matches; 5.6% singletons. For 4 true matches,
predicting all 4 with one false positive scores **identically** (0.833) to predicting
only the 2 you are sure of, while predicting only the best scores 0.625.

**Decision:** Sweep the threshold exhaustively against the reimplemented macro-F_0.5,
with no prior on where it lands. Scope of the threshold (global / per-country /
per-cardinality) is itself a sweep axis.

**Rationale:** "Precision-heavy" is true of the formula and misleading about this
dataset. With ~3.5 matches per entity recall is costly to surrender, and the entire
singleton bonus caps at **5.6 points**. An intuition-set conservative threshold is the
most likely single way to leave rank on the table.

**Rejected:** A fixed high threshold justified by the formula's β. A dedicated
high-precision singleton classifier as a first-class component — worth at most 5.6
points; kept as one axis of the decision layer instead.

**Revisit if:** error analysis shows false merges dominating the loss, warranting
per-country or per-cardinality thresholds.

---

### D-05 — Mine the noise model from the 7.6M labelled pairs
**Status:** Accepted · **Feeds:** Doc §2.2 (core innovation), §4

**Question:** How should normalization be built, given the rules forbid external
reference data?

**Evidence:** A.7 — corruption is synthetic with a finite vocabulary. A.6 — 14.9% of true
pairs share zero name tokens, mostly transliteration and domain-ification. A.1 — 7.6M
labelled positives are available as examples of the corruption itself.

**Decision:** Mine transformations from ground-truth pairs as frequency statistics:
Devanagari↔Latin token/character map, city aliases, state abbreviations, legal-suffix
drop set, character-confusion pairs (`l`↔`1`), diacritic folding, zero-padding. Compute
features on **both raw and normalized** forms so the model chooses which to trust.

**Rationale:** The top non-blocking lever. It converts the hard 14.9% tail into matchable
pairs, requires no GPU, and is the component most likely to differentiate from teams
running generic string similarity. It is also explicitly compliant: a statistic learned
from the *provided training data* is not external data, whereas a hand-authored city-alias
list would be.

**Rejected:** A hand-authored abbreviation/alias table — forbidden, and less complete than
what the labels yield. Relying on a multilingual embedder to absorb transliteration
implicitly — plausible, but unverifiable per-transformation; kept as a *comparison* in
the NB07 sweep rather than a substitute.

**Compliance note for the write-up:** the only hand-entered mappings are the five given
in the problem statement (Corp/Corporation, Pvt/Private, Ltd/Limited, Rd/Road,
St/Street). Everything else is mined.

**Revisit if:** the mined tables come out sparse, in which case lean on char-n-gram
similarity, which is transformation-agnostic.

---

### D-06 — Exclusivity-constrained assignment
**Status:** Accepted · **Feeds:** Doc §4

**Question:** Can a Source 2/3 record legitimately belong to several Source 1 entities?

**Evidence:** A.3 — **0 duplicates across all 7,638,365 matched IDs.**

**Decision:** After scoring, resolve conflicts so no S2/S3 record is claimed twice.
Greedy-by-score and Hungarian/bipartite are both in the sweep; the *constraint* is not.

**Rationale:** A free precision gain from a hard structural guarantee. An earlier plan
revision listed this as a tunable — a five-minute check turned it into a fact, which is
strictly better than a tuned parameter. A.5 adds a secondary prior: ~74% of S2/S3 records
have a home, so aggressive claiming is not inherently wrong.

**Rejected:** Independent per-pair scoring with no global constraint (discards a known
guarantee). Treating exclusivity itself as a hyperparameter (wastes sweep budget
confirming something already measured).

**Revisit if:** test data shows evidence of different structure — nothing suggests it will.

---

### D-07 — Country as a hard blocking partition
**Status:** Accepted · **Feeds:** Doc §3

**Question:** Can `country` be a hard filter rather than a soft feature?

**Evidence:** A.4 — 0 cross-country pairs in 693,069 checked.

**Decision:** Partition blocking, feature extraction and scoring by `country` value.

**Rationale:** Splits one large problem into three smaller independent ones at no recall
cost, cutting blocking's quadratic term substantially — which also makes each sweep point
cheaper. Implemented as partition-by-value, satisfying the open-label-set constraint;
France flows through with no special case.

**Rejected:** Country as a boolean equality feature only — safe but wastes a hard
constraint that shrinks the problem.

**Implementation guard:** partition by whatever values appear, never by a hardcoded
`{US, India, France}` set. An unseen fourth label must form its own partition, not fall
into a default branch.

**Revisit if:** France-partition recall is materially below US/India.

---

### D-08 — Subsample training to ~150k S1 entities
**Status:** Accepted · **Feeds:** Doc §4

**Question:** How much of the 2.2M training entities should the model see?

**Evidence:** A.1 — roughly 20× what a GBM needs to saturate on ~30 tabular features.

**Decision:** Sample ~150k S1 entities (stratified by country × cardinality) for feature
extraction and training; separate stratified slice for validation.

**Rationale:** Makes every sweep point ~15× faster at negligible accuracy cost. Sweep
throughput *is* the project — an omission here would silently shrink how much of Plan §6
gets explored.

**Rejected:** Training on all 2.2M entities.

**Revisit if:** learning curves are still climbing at 150k — then step to 400k.

---

### D-09 — Neural reranker retained as a pipeline stage ⟵ **reverses an earlier cut**
**Status:** Accepted · **Amended Rev 3** (rationale restated in throughput terms rather
than dollars) · **Feeds:** Doc §4

**Question:** Does a neural reranker belong in the pipeline?

**What was decided first, and why it was wrong:** The reranker was initially cut as
unaffordable. That call **estimated cost by intuition instead of multiplying it out.**
The actual arithmetic: top-5 × 1.73M entities = ~8.7M pairs, at fp16 / seq 128 on a
single mid-range GPU that is a few hours — comparable to one GBM sweep, not a
project-consuming commitment. The stage was never expensive; the estimate was.

**Decision:** Fine-tune a permissively-licensed reranker on hard negatives from blocking
output and score the GBM's top-K per entity. Base model, top-K, sequence length, pair
serialization, negative ratio and blending are all sweep axes (Plan §6.4). **Ship only
if it beats GBM-alone on the holdout.**

**Rationale:** Highest expected gain per unit of compute in the pipeline, and it attacks
exactly the residue the tabular model handles worst — semantically equivalent but
lexically distant pairs (transliteration, domain-ification).

**Rejected:** Dropping it (the reversed call). Running it over all ~43M pairs — this
genuinely does not fit, and is what the top-K cascade exists to avoid.

**Lesson recorded deliberately:** estimate compute by multiplying the numbers out, not by
recalling what felt slow before. A log containing only decisions that held up is not
useful as self-reference.

**Revisit if:** holdout gain is under ~0.005, in which case ship the GBM alone and spend
the budget on §6.1–6.3 instead.

---

### D-10 — LOCO as a sensitivity filter, not a search objective
**Status:** Accepted · **Feeds:** Doc §5

**Question:** How heavily should leave-one-country-out validation guard against
overfitting to seen countries?

**Evidence:** A.4 — France is ~15% of test. Training has only two countries, so LOCO can
only mean train-US→validate-India (or the reverse).

**Decision:** Run LOCO at S9 as a **feature sensitivity filter** — a feature group that
helps the holdout but collapses LOCO is memorizing country artifacts. Not an optimization
target. Supplemented by a France score-distribution check on unlabelled test records and
a crash check on an unseen country label.

**Rationale:** US↔India is a weak proxy for France, which is Latin-script and
structurally closer to US than India is. Making LOCO a search objective would roughly
double every sweep point's cost to insure a 15% slice via a poor proxy. Running it once
per feature-group decision keeps the real signal at a fraction of the cost.

**Rejected:** LOCO tracked per search iteration. Dropping LOCO entirely — the
sensitivity signal is real and cheap at n=1.

**Guard carried forward:** address parsing stays strictly structural — no ZIP/PIN
regexes, no country-keyed branches, since those are precisely what breaks on unseen
French layouts. Use generic `standalone_numeric_tokens` overlap instead.

**Revisit if:** the France score distribution is visibly shifted from US/India.

---

### D-11 — Model blending
**Status:** ⚠ **Superseded by D-16** · **Feeds:** Doc §4

Originally: ensembling dropped as unvalidatable within a 3-day window. The timeline was
scoping context rather than the objective, and blending is cheap to evaluate once the
holdout harness exists. See D-16.

---

### D-12 — `candidate_pairs.tsv` is the last candidate set before final scoring
**Status:** Accepted · **Feeds:** Doc §3

**Question:** With a cascade, which stage's output is the deliverable candidate set?

**Evidence:** The problem statement is explicit: *"the final candidate list just before
the ML model scores them… If your pipeline has several blocking/filtering stages,
`candidate_pairs.tsv` is the last one: whatever your model actually runs inference over."*

**Decision:** Emit `candidate_pairs.tsv` from the **top-K set handed to the reranker**.
If the reranker is not shipped (D-09 revisit clause), it reverts to the set the GBM
scores. `NB09_submission` derives this from the actual pipeline config rather than a
hardcoded stage, so it stays correct as the cascade shape changes during sweeping.

**Rationale:** The cascade makes this ambiguous by default, and getting it wrong is
invisible on the leaderboard — the file is not scored. It surfaces only in the top-teams
package audit, i.e. at the worst possible moment.

**Rejected:** Emitting raw blocking output — contradicts the statement and makes the
blocking-quality analysis the organizers run meaningless.

**Verification:** every ID in `matching_results.tsv` must appear in
`candidate_pairs.tsv`; the provided validator warns otherwise.

---

### D-13 — Ship a valid submission before any modelling
**Status:** Accepted · **Feeds:** Doc §6

**Question:** When should the first leaderboard upload happen?

**Decision:** At stage S2, from a trivial rule baseline (normalize, near-exact
name + address match), before blocking or features exist.

**Rationale:** Three payoffs. It de-risks the output format early — comma-laden addresses
plus default pandas quoting is a real rejection mode, and discovering it late is
expensive. It calibrates holdout-vs-leaderboard, giving a second validation signal for
every subsequent sweep. And it guarantees a non-zero score exists if anything later goes
wrong. An earlier plan revision put fourteen steps before the first upload.

**Rejected:** Uploading only once the pipeline is complete — concentrates all format risk
at the deadline.

**Implementation note:** write with `quoting=csv.QUOTE_NONE`; run
`utils/validate_submission.py` before this and every subsequent upload.

---

### D-14 — Local IDE for authoring, SageMaker for execution
**Status:** Accepted · **Feeds:** Doc Appendix A

**Question:** Where does code get written, and where does it run?

**Decision:** Author in the local IDE against `src/`; execute heavy stages on SageMaker by
copy-pasting notebooks unchanged. The portability contract is Plan §4.2: environment
auto-detect, no hardcoded paths outside the config cell, parquet intermediates, one
pinned dependency cell, parallelism derived from the instance.

**Rationale:** Local iteration is faster for everything except the stages that need real
memory or a GPU. The contract exists so the hop costs nothing — a notebook that needs
editing to run on SageMaker will, under sweep pressure, silently drift out of sync with
its local version.

**Practical note:** new AWS accounts often have a **zero quota for GPU instance
families**. Check Service Quotas before the neural sweep is needed, since approval is not
instant and the failure mode is a stage that silently never runs.

**Rejected:** Running everything locally (memory-bound stages do not fit). SageMaker
training jobs / pipelines — more ceremony than a single-person project benefits from, and
harder to iterate on interactively.

---

### D-15 — Dense retrieval is a sweep axis, not a rejected alternative
**Status:** Accepted · **Amends:** D-02 · **Feeds:** Doc §3

**Question:** Should dense embedding retrieval be part of candidate generation?

**What changed:** D-02 rejected dense retrieval as primary on the grounds that the
lexical ceiling was already ~100% and a FAISS path would cost implementation hours. The
ceiling finding stands — but "costs hours" was scoping reasoning, and the project's
objective is to *search* retrieval methods and keep the best, not to minimise
implementation.

**Decision:** Lexical union remains the **baseline and default** (D-02). Dense retrieval
is an explicit on/off axis in the blocking sweep (Plan §6.2), evaluated as a recall@K
delta against the lexical union at matched candidate-set size. Embedder choice is its own
axis (Plan §6.4).

**Rationale:** Recall@K is only half the question — the union's *precision* at a given K
matters just as much, since it sets how much work the downstream scorer does per real
match. A dense index may reach the same recall with a smaller, cleaner candidate set,
which is a real gain the ceiling measurement alone does not capture. That is an empirical
question, and the harness exists to answer it.

**Rejected:** Dense-as-primary without measurement (adoption on reputation). Dense
excluded entirely (D-02's original position).

**Revisit if:** dense adds no recall *and* no precision at matched K — then drop it and
reclaim the sweep budget for §6.1 and §6.4.

---

### D-16 — Blending is a sweep axis
**Status:** Accepted · **Supersedes:** D-11 · **Feeds:** Doc §4

**Question:** Should multiple model outputs be combined?

**What changed:** D-11 dropped ensembling as unvalidatable in a 3-day window. The window
was scoping context, and once the holdout harness (D-03) exists, evaluating a blend costs
one extra scoring pass — cheap enough that refusing to measure it is the more arbitrary
choice.

**Decision:** Blending is an axis, not a commitment. In scope: GBM + reranker combination
(reranker-only / mean / logistic stacker, Plan §6.4), and GBM library averaging across
LightGBM / XGBoost / CatBoost if more than one lands close. **Kept only on a measured
holdout gain**, and the trivial rule baseline stays in every comparison.

**Rationale:** Blends are the classic way to buy a small, reliable gain at the end of a
search. The real risk is not cost but self-deception — adopting a blend on a difference
inside the noise. The mitigation is the rule above, not refusing to try.

**Rejected:** Blending adopted by default (the common reflex). Blending excluded entirely
(D-11's position).

**Revisit if:** blend gains sit inside holdout noise — then ship the single best model,
which is also easier to document and reproduce.

---

### D-17 — Notebooks orchestrate; `src/` holds the logic
**Status:** Accepted · **Feeds:** Doc Appendix A

**Question:** How is the code organised across notebooks?

**Decision:** Numbered notebooks `NB00`–`NB10` (Plan §4.1) drive stages and visualise
results; all reusable logic lives in `src/business_entity_resolution/` and is imported.
Each stage writes a self-describing parquet artifact so any notebook can start from disk
without re-running its predecessors.

**Rationale:** Three things follow from this that matter under heavy sweeping. Re-running
one stage after a fix does not re-run everything above it. The submission package's
`code/.../src/` is genuinely runnable rather than a pile of exported cells — which the
organizers audit. And a sweep can drive `src/` functions in a loop without notebook
ceremony.

**Rejected:** One monolithic notebook (no partial re-runs; unreviewable). Pure scripts
with no notebooks (loses the interactive inspection that error analysis depends on).
Pickle intermediates — they break across library versions and do not survive the
local→SageMaker hop.

---

### D-18 — The submission path must stay green after every edit
**Status:** Accepted · **Feeds:** Doc §6

**Question:** How is "still working" defined during heavy experimentation?

**Decision:** After any change to any notebook or `src/` module, `NB09_submission` must
run end-to-end and produce both TSVs passing `utils/validate_submission.py`. A change
that improves an offline metric but breaks the submission path is not finished.

**Rationale:** The failure mode this prevents is specific and common: a sweep that
improves a holdout number while quietly breaking serialization, discovered only when
uploading. Because `candidate_pairs.tsv` depends on the cascade shape (D-12) and the
cascade shape is itself being swept, the submission path is *more* fragile than usual
here, not less.

**Cheap version:** keep a `SMOKE=True` flag that runs the whole path on ~1% of test
entities in a couple of minutes. Full regeneration only before an actual upload.

**Rejected:** Validating only before uploads (defers breakage to the worst moment).

---

### D-19 — Every run is logged to `artifacts/runs.jsonl`
**Status:** Accepted · **Feeds:** Doc §5, Appendix B

**Question:** How are sweep results tracked?

**Decision:** One JSON line per run: timestamp, stage, full config dict, and every metric
(blocking recall@K, reduction ratio, candidate-level P/R, macro-F_0.5, per-country
breakdown). Never overwrite.

**Rationale:** Plan §6 has enough axes that memory is not a reliable record of what was
already tried, and an unlogged experiment will be repeated. It also makes the required
ablation tables in the write-up a query rather than a reconstruction.

**Rejected:** MLflow / W&B — more setup than a single-person project needs, and an
external dependency in a package the organizers must reproduce. A spreadsheet — not
writable from a sweep loop.

---

### D-20 — Verify every model licence on its card before it enters the pipeline
**Status:** Accepted · **Feeds:** Doc §4

**Question:** How is the MIT/Apache-2.0 ≤8B constraint enforced?

**Decision:** Before any pretrained model is used in an experiment, record its verified
licence and parameter count in this file, read from the model card itself. Not at
packaging time — at first use.

**Rationale:** Several of the strongest multilingual retrieval and reranking models are
released under **CC-BY-NC**, which fails the requirement — `jina-embeddings-v3` and
`jina-reranker-v2-base-multilingual` are the obvious traps, precisely because they are
natural shortlist candidates. Discovering a licence problem after a model has been swept,
tuned and shipped means discarding that work. Checking at first use costs a minute.

**Verified so far:** none yet — populate as models enter the sweep. Candidates to verify
are listed in Plan §6.4.

**Rejected:** Checking at packaging time (too late). Trusting aggregator sites or
leaderboard listings, which frequently misstate licences.

---

### D-27 — `csv.writer(quotechar="")` rejected on Python 3.12 — replaced with direct write
**Status:** Accepted · **Date:** 2026-09-27 · **Feeds:** src/business_entity_resolution/io_tsv.py

**Bug:** On the EC2 instance (Ubuntu 26.04, Python 3.12.14 in the project venv per
D-25), the S2 nbconvert run crashed at cell 8 with
`TypeError: "quotechar" must be a 1-character string`. My original
`write_submission_tsv` in `io_tsv.py` set `csv.writer(..., quoting=csv.QUOTE_NONE,
quotechar="")` — the empty string.

**Why it wasn't caught locally:** the S0 smoke test at 2026-09-26 executed on my
Mac's Python 3.9, which accepted the empty `quotechar` (only its stricter-typed
subclass since 3.12 rejects it). It ran; NB00 went green; the D-18 smoke-path check
therefore *did* pass on my box but was a false green for any Python ≥3.12.

**Fix on EC2 (already applied by the user):** `sed` patch changing `quotechar=""` to
`quotechar='"'`. Because `QUOTE_NONE` never consults `quotechar`, any 1-character
value is inert; this is functionally correct and does not affect the emitted bytes.

**Fix in the local repo:** replaced the entire `csv.writer` call with a direct
buffered write:

```python
buf.write(f"{header[0]}\t{header[1]}\n")
for s1 in order:
    joined = ",".join(mapping.get(s1, ()))
    if "\t" in s1 or "\t" in joined or "\n" in s1 or "\n" in joined:
        raise ValueError(...)
    buf.write(f"{s1}\t{joined}\n")
```

This removes the `csv` dependency entirely, closes the Python-version regression
class, and is equivalent to what the validator expects byte-for-byte (literal
`<s1>\t<comma,joined>\n`, no quoting, no escaping). The tab / newline guard stays.

**Assumptions made without asking:**
1. **The user's `sed` patch stays in place on the EC2 box for the current run.** No
   need to force-sync the cleaner local version mid-run — the two produce identical
   output.
2. **The `\t` and `\n` guards are sufficient.** Business names in the source *do*
   contain `,`, `.`, `&` and quotes — but the submission file only ever writes
   `S1-\d+` ids and comma-joined `S[23]-\d+` id lists, none of which can contain
   these characters. If a bug ever puts a raw name string into the submission, the
   guard will catch it via the tab/newline path.

**Lesson recorded:** D-18's "submission path stays green" only means what it says on
the Python version the smoke test ran on. Add "run the smoke on the target Python
version" to the pre-flight checklist — or at least run it on whatever Python the
repo's pyproject/requirements lock to (3.12 here). My Mac's 3.9 is stale and
shouldn't be the sole gate.

**Rejected:** Downgrading to a Python 3.12-compatible csv.writer flag combination
(hides the same class of bug behind slightly different flags — the direct write is
the right size of change).

**Revisit if:** any submission-side field ever legitimately needs to contain a
comma, tab, or quote — which the validator's contract explicitly forbids, so this
should be "never".

---

### D-28 — S3/S4 failures were implementation and resource-boundary failures, not model evidence
**Status:** Accepted · **Date:** 2026-09-27 · **Amends:** D-25's stale compute claim ·
**Feeds:** Plan §5–§6

**Observed facts:** The actual EC2 runner remains `m7i-flex.large` (2 vCPU / 8 GiB
RAM, plus a 16 GiB swap file); it was not resized to the 64 GiB machine described in
D-25. The completed S3-v2 run mined 7,119,291 non-holdout positive pairs but selected
zero aliases and zero drops. The first S4 exact-key diagnostic retained 50.70% of
holdout positives. The global IDF join failed twice while materialising `idf_hits`
(temporary data reached 63.3 GiB, then 11.1 GiB); the `df <= 100` rare-token fallback
completed but reached only 44.83% recall@100.

**Root causes found in code:**

1. S3 alias confidence was divided by every positive-pair occurrence of a token rather
   than by its one-to-one transformation opportunities. This made a reusable alias such
   as `rd → road` virtually impossible to select.
2. S3 drop rate was divided by all 7M pairs instead of appearances of that token, which
   likewise made the 0.80 threshold unreachable for realistic suffixes.
3. The original S4 query joined every holdout reference to the complete retrieval index
   before ranking. This violates the available machine's memory and temporary-disk
   budget. Tightening the token filter prevented the crash only by removing true pairs.
4. The earlier S4 index had no fingerprint of the normalization tables, so a later S3
   change could silently reuse a stale v0 index.

**Decision:** S3 now records transformation diagnostics and uses conditional
transformation confidence / per-token drop rates. S4 v4 fingerprints and rebuilds its
compact index when normalization changes, processes at most 100 S1 references per
query batch, caps DuckDB spill at 4 GiB, and defaults to a 5,000-S1 stratified pilot.
Every new S3/S4 notebook run appends a JSON line to `artifacts/runs.jsonl`.

**What this does not prove:** No new S3 or S4 score exists until the corrected
notebooks run on EC2. The S4 exit criterion remains full-holdout recall@K ≥97%; neither
the 50.70% exact diagnostic nor the 44.83% rare-token result is a pass, and neither
deserves a leaderboard submission.

**Revisit:** After the batched pilot reports recall and candidates-per-S1. If recall is
well below the target at K=100, add the planned char-trigram and numeric-address union
as separate bounded experiments; do not loosen a global join or run S5/S6 prematurely.

---

### D-26 — Resource under-provisioning at S2 execution: swap is a workaround, not a fix
**Status:** Accepted · **Date:** 2026-09-27 · **Feeds:** Plan §5

**What happened:** The EC2 instance for the S2 run (D-25) was launched as
`m7i-flex.large` — 2 vCPU / **8 GB RAM**. My guidance had specified 32-64 GB. The gap
was noticed only after `nohup jupyter nbconvert` hit 93.2% memory + active swap at
~18 min in, with no progress past `[NbConvertApp] Converting notebook` in the log.

**Contributing factors:**
1. A 16 GiB swap file was created (`fallocate -l 16G /swapfile`) to prevent OOM. It
   *did* prevent OOM, but for a dict-lookup-heavy workload like `build_key_index`,
   swap makes the process effectively non-progressing — every hash-table access hits
   a cold page. Swap protects against crashes; it does not preserve throughput.
2. `m7i-flex.large` is a burstable-baseline instance. Even without the RAM issue,
   the CPU credits deplete on sustained load, throttling to a fraction of vCPU
   capacity. Not the right family for a batch-style compute run.

**Decision:** For every stage from S2 onward, the launch checklist includes
a pre-flight resource size:

| Stage | Minimum instance |
|---|---|
| S0, S1 | `t3.large` (2 vCPU / 8 GB) — trivial |
| S2 rule baseline | `m7i.4xlarge` (16 vCPU / **64 GB**) |
| S3 mine noise model | `m7i.4xlarge` or `r7i.4xlarge` |
| S4 blocking | `r7i.4xlarge` (16 vCPU / **128 GB**) — sparse matmul over 10M vectors |
| S5–S6 features + GBM | `m7i.8xlarge` or `r7i.4xlarge` |
| S7 embedder / reranker | GPU: `g5.2xlarge` (A10G 24 GB) |
| S8 decision layer | `m7i.4xlarge` |

*Never* use `-flex` variants for compute — the burstable model silently
under-delivers on any sustained pass.

**Swap is retained as a safety net**, not the primary sizing strategy. If a job
starts touching swap heavily (`vmstat si/so > 1000/s`), abort and resize; don't
wait for it to page its way through.

**Assumptions I made without asking:**
1. **`nohup jupyter nbconvert` on the current instance was worth killing rather than
   waiting out.** Even if it eventually completed, the number would tell us nothing
   about the code (only about swap performance under this workload), and the
   subsequent NB03 / NB04 runs would hit the same wall — spending time here is buying
   nothing that generalises.
2. **The 100 GB EBS volume, the `.venv`, and `~/ber` all survive an instance-type
   change** — this is true for EBS-root EC2 instances (which this is), but is worth
   stating so we don't re-provision from scratch after every resize.

**Rejected:** Adding more swap (doesn't fix the root cause). Rewriting the tokenizer
now to reduce memory footprint (real optimization but blocks S2 for hours to save
budget on an instance that's already too small).

**Revisit if:** SageMaker becomes the execution environment instead of EC2 — instance
sizing there is per-space and re-picked from a fixed list; this table maps onto the
`ml.*` names one-to-one.

---

### D-25 — Execution moved from SageMaker Studio to plain EC2 ⟵ pivot from D-14
**Status:** Accepted · **Date:** 2026-09-27 · **Amends:** D-14 · **Feeds:**
[SAGEMAKER_RUNBOOK.md](SAGEMAKER_RUNBOOK.md)

**What changed:** D-14 assumed SageMaker Studio JupyterLab as the execution surface,
and [SAGEMAKER_RUNBOOK.md](SAGEMAKER_RUNBOOK.md) was written for that. The actual
S2 execution moved to a plain EC2 instance instead (`ber-runner`,
`i-0bf893ffc58af558d`, `us-east-1`, Ubuntu 26.04 LTS, 100 GiB gp3), with S3
(`vinayak-ber-2026-399855128385-us-east-1-an`) as the code+data hand-off surface.

**Facts of the current setup** (from the EC2 continuation addendum, 2026-09-27):

- **Compute:** initially `m7i-flex.large`, resized to `m7i.4xlarge` per D-26.
- **OS:** Ubuntu 26.04 LTS. Default Python is 3.14, which does *not* have wheels for
  `pyarrow==17.0.0` — the source build fails on `pkg_resources`. Resolution: install
  a compatible Python via `uv python install 3.12`, create `~/ber/.venv` under 3.12,
  reinstall the requirements. **Any future notebook/venv work on this host uses
  `~/ber/.venv/bin/python`, not `python3`.**
- **IAM:** instance role `ber-ec2-s3-role`, attached, S3 read access. Verified via
  `aws sts get-caller-identity`.
- **Project location:** `~/ber` (approx 2.5 GiB extracted). `BER_ROOT="$HOME/ber"`
  is exported per-command and appended to `~/.bashrc`.
- **Execution pattern:** `nohup env BER_ROOT=... .venv/bin/jupyter nbconvert --to
  notebook --execute notebooks/NBxx.ipynb --output notebooks/NBxx.executed.ipynb`,
  PID written to `logs/NBxx.pid`, log at `logs/NBxx.log`.

**Rationale for the pivot** (as I understand it — not stated in the addendum):
plain EC2 gives finer instance control, a persistent EBS volume that survives
type changes, and direct SSH/`nohup`/tmux workflows that don't depend on a Studio
space staying open. The trade is that Studio's kernel-management and file-browser
niceties go away; the code was already `src/`-first (D-17), so nothing was lost.

**Assumption made without asking:** the SageMaker runbook is now **secondary** for
this project. It stays in the repo as a reference for anyone continuing this on
Studio, but the primary execution path is EC2 + `nohup nbconvert`. The paste-back
contract (D-24) is unchanged — notebooks still end with the `PASTE-BACK` block.

**Standing security follow-up (from the addendum):** SSH inbound was temporarily
broadened to `0.0.0.0/0` for EC2 Instance Connect debugging. **Restore to My-IP
(or a narrower CIDR) as soon as browser access is no longer needed** — this is on
the addendum's own §7 checklist and is called out here so it isn't lost.

**Rejected:**
- Continuing on SageMaker Studio (D-14) — moot, execution moved.
- Baking Python 3.14 wheel workarounds into `requirements.txt` — Python 3.12 via
  `uv` is cleaner and matches the pinned deps' current wheel availability.

**Revisit if:** the neural stages (S7) start being painful without SageMaker's
managed training-job / GPU-space conveniences.

**Amendments to Plan / files:**
- Update [SAGEMAKER_RUNBOOK.md](SAGEMAKER_RUNBOOK.md) with an "or: EC2" section so
  the two paths sit side by side. (Deferred; will do on the next code push.)
- `config.py` currently detects SageMaker via `/opt/ml` and `SM_CURRENT_HOST`.
  Neither is true on plain EC2, so `ON_SAGEMAKER=False` and the fallback is the
  Mac path — but `BER_ROOT` override handles it correctly. **No code change
  needed**, but worth noting so nobody re-adds a "SageMaker vs EC2" branch that
  isn't necessary.

---

### D-24 — Standing rule: author locally, execute on AWS ⟵ **corrects the S2 attempt**
**Status:** Accepted · **Date:** 2026-09-26 · **Feeds:** Plan §0

**Question:** Where does code run during development?

**What triggered this:** At S2 I started executing `run_baseline.py` on this Mac
against the full 12M-row training data. It stalled at ~13 min in the tokenizer over 10M
S2+S3 records under memory/CPU pressure, and the user pointed out that this device is
for authoring code only — the AWS instance runs the code.

**Decision:** The local machine authors code. Full-scale execution of anything that
touches the real dataset happens on SageMaker. Locally, three things are allowed:

1. **Import checks** — `python3 -c "from business_entity_resolution.<mod> import ..."`
   to confirm a module parses and its symbols exist.
2. **Unit tests on hand-authored inputs** — e.g. the F_0.5 worked example from the
   problem statement (149 chars of hand-written input, not the dataset).
3. **Sub-second sanity checks on ≤10-row slices** — e.g. verifying `name_key`
   collapses `Cao Assets Inc` and `Cao Ássets Inc` to the same tuple.

Any full-dataset run — even for "just a quick number" — belongs on AWS.

**Rationale:** The laptop has 16 GB RAM and no GPU. A full pass over the ~12M-record
sources triggers paging and takes 10-20× longer than the same code on a right-sized
SageMaker instance. Local runs also produce numbers that mislead about *actual* wall
clock — a 20-min local baseline is a 90-second AWS baseline, and planning around the
former inflates every experiment budget wrongly.

**Rejected:** Local execution "for iteration speed" (backwards — right-sizing on AWS
*is* the iteration speed). Local runs on a sampled subset (drift between subset
behaviour and full-dataset behaviour is exactly what we're trying to measure).

**Enforcement:** Every notebook opens with a comment in the config cell stating this,
and I do not run `python3` on anything that reads `train_source*.tsv` or
`test_source*.tsv` end-to-end from this session onwards. `NB00`'s validator check
against a hand-generated empty submission is still allowed — it does not iterate over
any source file's rows, just re-reads the tiny outputs it wrote.

**Revisit if:** ever the constraint changes (e.g. project moves to a machine with more
RAM). Until then, treat this as a hard invariant.

---

### D-23 — S2 code complete, awaiting AWS execution
**Status:** Planned (code done; measurement pending AWS run) · **Date:** 2026-09-26 ·
**Feeds:** Doc §2.2, §3

**What was done (code):** Two modules added to `src/business_entity_resolution/`.
`normalize.py` implements the v0 normalization primitives — `strip_diacritics`,
`tokenize`, `name_key`, `address_key`, `joint_key`. Only the five organizer-given legal
suffixes are hand-encoded (Corp/Corporation, Pvt/Private, Ltd/Limited); everything else
is a language-agnostic string operation, per D-05's compliance boundary. The Devanagari
range (`\\u0900-\\u097f`) is preserved so transliteration cases survive tokenization.
`rule_baseline.py` builds a per-country `(name_key, address_key) → [entity_ids]` index
over Source-2 and Source-3, and matches each Source-1 entity by exact key equality,
enforcing exclusivity (D-06) greedily.

`notebooks/NB09_submission.ipynb` wires this up: (1) load the S1 holdout parquet from
S1, (2) score the rule on the holdout to establish the local calibration anchor,
(3) run the rule on the test sources, (4) emit both TSVs and run the validator,
(5) log to `runs.jsonl`, (6) print a `PASTE-BACK` block with the metrics for the local
chat.

**Verified locally (hand-authored inputs, D-24-compliant):**

- `Cao Assets Inc` and `Cao Ássets Inc` collapse to the same `name_key`.
- `Blue Pediatrics LLC` vs. `Blue Pediatrics` **do not** collapse — LLC is not in the
  organizer-given suffix set. Expected, and it flags what S3 (mined normalizer) will
  need to close.
- Address-token reorder is handled by sorting the token tuple; abbreviation cases
  (`Drive`/`Dr`, `Utah`/`UT`) are not — again what S3 exists for.

**Not run locally (per D-24):** the full 12M-row indexing, the holdout F_0.5 score, the
submission TSVs on the test set, the validator call. Awaiting SageMaker output.

**Assumptions made without asking:**

1. **v0 uses exact name-key + address-key equality.** No partial matches, no
   near-duplicates. This trades recall for precision — appropriate for an F_0.5 baseline
   and gives S3–S8 something with clean failure modes to attack.
2. **Exclusivity tiebreaker is first-S1-in-file-order wins.** When two Source-1 records
   normalize to the same key and both would claim the same Source-2/3 candidate, the
   one appearing earlier in `test_source1.tsv` gets it. This is the dumbest choice
   consistent with §A.3; the smarter version (score-based Hungarian) is D-06's remit at
   S8.
3. **Candidate file = matched file at S2.** Per D-12, `candidate_pairs.tsv` is the last
   candidate set before the final scorer. At S2 there is no scorer beyond the rule
   itself, so both files hold the same lists. This changes at S6 (GBM) and S7
   (reranker).

**Rejected:** Loosening the rule to name-only (would trigger many-to-many merges that
would be filtered by exclusivity anyway, but would tank precision). Preprocessing
addresses to strip state/province tokens (leaks a country-aware branch, breaking D-07's
open-label-set constraint).

**How to complete this stage:** run `NB09_submission.ipynb` on SageMaker (see
[SAGEMAKER_RUNBOOK.md](SAGEMAKER_RUNBOOK.md)) and paste back the `PASTE-BACK-START` /
`PASTE-BACK-END` block. On receipt the fields land in `artifacts/runs.jsonl` here, D-23
gets amended to `Accepted` with the numbers, and if the score looks sane the
`output/matching_results.tsv` from AWS gets uploaded to the leaderboard for the
holdout↔leaderboard offset (D-03 revisit trigger).

**Files added**
- `src/business_entity_resolution/{normalize,rule_baseline}.py`
- `notebooks/NB09_submission.ipynb`
- `SAGEMAKER_RUNBOOK.md`

---

### D-22 — S1 complete: macro F_0.5 verified, stratified holdout persisted
**Status:** Accepted · **Date:** 2026-09-26 · **Feeds:** Doc §4

**What was done:** Two modules landed in `src/business_entity_resolution/`.
`metric.py` implements `f_beta_per_entity` and `macro_f05` with the singleton edge case
handled explicitly; the worked example returns **0.7143** and every case in Plan §1.5's
threshold-behaviour table checks out. `splits.py` builds the training manifest
(one row per S1 with country, gt_matches, n_true, cardinality_bucket) and cuts a
stratified holdout by country × cardinality bucket using a single fraction (no rebalancing).

Verified numbers:

- Manifest rows: **2,206,821** (matches §A.1).
- Countries: US 1,323,633 · India 883,188 (matches §A.4 — no France in training).
- Cardinality distribution reproduces §A.2 exactly (0→5.6%, 1→5.4%, 2→17.0%, 3→24.1%,
  4→21.9%, 5→14.6%, 6+→11.4%; mean 3.461, expected 3.46).
- Holdout size: **149,999** (target 150,000; short by one from proportional rounding).
- Per-stratum drift: bucket ≤4e-6, country ≤6e-6 — effectively zero.
- Empty-baseline macro F_0.5 on the holdout = **0.0558** = singleton fraction, exactly
  as the metric predicts. Cross-validates the metric implementation *and* the split in
  one number.

Artifacts persisted: `artifacts/holdout_s1.parquet` (6.95 MB), `artifacts/train_s1.parquet`
(91.9 MB), `artifacts/split_strata.parquet` (3.6 KB). Run row appended to
`artifacts/runs.jsonl`.

**Assumptions made without asking:**

1. **Stratification is proportional-to-stratum-size, not balanced.** Balancing would
   distort the very macro-F_0.5 estimate the holdout is here to compute; every stratum
   in the strata table shows the target fraction 0.068 to three decimals.
2. **Cardinality bucket = `{0,1,2,3,4,5,6+}`.** Chosen so the buckets align with the
   distribution table in §A.2 that every future run reports against.
3. **`train_source1.tsv ⋈ train_ground_truth.tsv` is an inner join.** If any S1 row
   lacks a GT row it is dropped from the manifest — measured, none are dropped (both
   files have 2,206,821 data rows).
4. **`gt_matches` is stored as a Python list column in parquet, not a comma-joined
   string.** pyarrow serialises it natively; reading back gives a list without needing
   a re-parse. Compact enough (7 MB) that no compression tuning is needed.
5. **Seed = 0 everywhere in this project unless a sweep needs to vary it.** Recorded in
   the `runs.jsonl` config so any run can be re-reproduced by seed.

**Rejected:** k-fold CV (D-03 already decided). Balanced stratified sampling (bias
described above). Storing the full S2/S3 candidate universe in the holdout manifest —
join on country at eval time instead; keeps the file small and cheap to load.

**Revisit if:** the holdout↔leaderboard offset (measured at S2) exceeds 0.02, which
would suggest the split is not representative and either seed variation or a larger
holdout is warranted.

**Files added**
- `src/business_entity_resolution/{metric,splits}.py`
- `notebooks/NB02_metric_and_splits.ipynb`
- `artifacts/holdout_s1.parquet`, `artifacts/train_s1.parquet`, `artifacts/split_strata.parquet`
- New row in `artifacts/runs.jsonl`

**Depends on:** pyarrow (installed at S1 — not pinned in `requirements.txt` yet; will
add during the S2 dependency freeze).

---

### D-21 — S0 complete: repo skeleton, empty submission passes validator
**Status:** Accepted · **Date:** 2026-09-26 · **Feeds:** Doc Appendix A

**What was done:** Repo skeleton created (`src/business_entity_resolution/`, `notebooks/`,
`artifacts/`, `output/`). Three modules landed: `config.py` (env auto-detect and paths),
`io_tsv.py` (validator-safe TSV writer using `csv.QUOTE_NONE`), `submission.py`
(end-to-end submission emission + validator invocation). `notebooks/NB00_setup.ipynb`
runs the config cell, imports from `src/`, peeks each dataset file, writes an all-empty
submission and calls the validator. Exit code 0 — `1,732,544` rows in each of
`matching_results.tsv` and `candidate_pairs.tsv`; validator prints
`PASS — no blocking issues found. Safe to submit.` Logged to `artifacts/runs.jsonl` per
D-19.

**Assumptions made without asking** (recorded so a later revision can challenge them):

1. **Submission row order = order in `test_source1.tsv`.** The validator does not require
   any specific order, but keeping a deterministic order makes cross-run diffs sensible
   and cuts the chance of a re-shuffle masking a real change. If a later stage benefits
   from grouping by country or by predicted-cardinality, override via the `order=`
   argument of `write_submission_tsv`.
2. **"Empty submission" = one row per S1 with empty `matched_entity_ids`.** The problem
   statement is explicit that this is how singletons are encoded, and the validator
   accepts it. No trailing tab, no `"nan"`, no `None` — literally an empty second field.
3. **`BER_ROOT` environment variable overrides both hardcoded default roots.** Added as
   a convenience for CI-style execution on a machine that is neither the local mac nor
   SageMaker. Does not affect the copy-paste path Plan §4.2 documents.
4. **Notebook/nb execution tooling (`jupyter`, `nbclient`) is a *dev* dependency, not a
   pipeline one.** Only used for offline "does the notebook still run clean" checks
   (D-18); not needed to produce the submission. Not pinned in `requirements.txt` yet.
5. **`.tsv` reads / writes assume UTF-8.** The validator itself errors on non-UTF-8
   input, so treating UTF-8 as the file-format law across the codebase matches the
   scorer's contract.

**Rejected:** Writing a JSON schema for `runs.jsonl` at this point (premature — the
metric shape changes at S1). Adding a pytest suite for `src/` at S0 (deferred until any
non-trivial function exists to test; `NB00`'s green run is the current gate).

**Revisit if:** the validator's behaviour on `--check-ids` shows any surprise once
S2/S3 real IDs start appearing in the file (S4 onwards). Re-run `run_validator(paths,
check_ids=True)` at that point.

**Files added**
- `src/business_entity_resolution/{__init__,config,io_tsv,submission}.py`
- `notebooks/NB00_setup.ipynb`
- `requirements.txt`
- `output/matching_results.tsv`, `output/candidate_pairs.tsv` (all-empty smoke submission)
- `artifacts/runs.jsonl` (one row: S0 smoke)

---

## §C — Mapping to `Documentation_template.md`

| Template section | Source |
|---|---|
| **1. Executive Summary** | D-01 (architecture) + D-05 (core innovation) |
| **2.1 Problem Analysis** | §A in full — especially A.2 cardinality, A.3 exclusivity, A.6 blocking ceiling, A.7 corruption vocabulary |
| **2.2 Solution Strategy** | D-01, D-02, D-15. **Approach type:** Blocking + Cascade Classifier. **Core innovation:** D-05, mined noise model |
| **3. Candidate Generation** | D-02 (blocking keys), D-07 (country partition), D-15 (dense comparison), D-12 (what the file contains), A.6 (how we know true matches were not lost) + the recall@K curve |
| **4. Matching Model** | Feature groups from Plan §6.3; D-05 (normalization), D-08 (training volume), D-09 (reranker), D-16 (blending), D-04 (threshold selection), D-06 (assignment), D-20 (licences) |
| **5. Results & Error Analysis** | Filled at S9 — not yet available |
| **6. Conclusion** | D-05 as the technical contribution; D-09 and D-15 as lessons |
| **Appendix A — Code Artefacts** | D-17 (structure), D-14 (execution environment), entry points |
| **Appendix B — Additional Results** | Queried from `runs.jsonl` (D-19): recall@K curve, feature ablation, model sweep table, per-country breakdown |

**Two points to make explicitly in the write-up**, because they are where this approach
differs from the obvious one:

1. **The blocking ceiling was measured, not assumed** (A.6). Reporting that name-only
   blocking caps at ~85% while name ∪ address reaches ~100%, with the measurement behind
   it, demonstrates the blocking analysis the organizers say they audit for.
2. **The normalization tables are mined, not authored** (D-05). State the compliance
   reasoning directly — it is both the honest framing and the stronger technical claim.

---

## §D — Genuinely Open

Only what is unresolved. Everything else is in §B with a revisit trigger.

| # | Open question | Resolved at |
|---|---|---|
| O-1 | Optimal K — the knee of recall@K vs. candidates/entity, per country | S4 |
| O-2 | Does dense retrieval beat the lexical union on precision at matched K? | S4 (D-15) |
| O-3 | Which normalization variant (v0–v3) wins, and does it differ by field? | S3 |
| O-4 | Which feature groups pass the holdout but collapse under LOCO? | S9 |
| O-5 | Binary objective vs. LambdaRank grouped by `source1_entity_id` | S6 |
| O-6 | Which reranker base model, and does pair serialization matter more than model choice? | S7 |
| O-7 | Does the reranker earn its stage over GBM-alone? | S7 (D-09) |
| O-8 | Greedy vs. Hungarian assignment — worth the runtime? | S8 |
| O-9 | Global threshold, or per-country / per-cardinality? | S8 |
| O-10 | Does France behave like US, like India, or like neither? | S9 |
