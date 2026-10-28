# Amazon ML Challenge 2026 — Business Entity Resolution Approach

**Team:** WinKing  
**Challenge:** Business Entity Resolution  
**Deliverables covered:** methodology, candidate generation/blocking, model architecture, feature engineering, experiments, AWS execution, and conclusion.

## 1. What is the task? What are we doing, why, and how?

### The task — in brief

We are given three sources of business records. **Source 1** is the clean, deduplicated reference list. **Sources 2 and 3** contain records for the same real-world businesses, but they have no common ID and may contain noisy names and addresses. For each Source 1 business, we must find all matching records from Sources 2 and 3.

This is called **business entity resolution** or **record linkage**. It matters because organisations often store the same customer, merchant, supplier, or business differently across systems. Correctly resolving those duplicates creates a reliable, unified view of data for analytics, operations, fraud prevention, and decision-making.

### Why the solution must be scalable

The data contains millions of rows. Comparing every Source 1 record with every Source 2/3 record would create an impractically large number of comparisons. We therefore first find a small set of likely matches, then apply strict matching rules or ML scoring only to those candidates.

| Data split | Source 1 | Source 2 | Source 3 |
|---|---:|---:|---:|
| Training rows | 2,206,821 | 5,034,616 | 5,285,603 |
| Test rows | 1,732,544 | 4,887,273 | 5,082,316 |

### How we solve it

1. **Profile and understand the data** — study match cardinality, country consistency, duplicate constraints, and common noise patterns.
2. **Normalize records** — standardize names and addresses so formatting changes do not hide a true match.
3. **Generate candidates (blocking)** — retrieve only plausible Source 2/3 records for each Source 1 business.
4. **Score and decide matches** — use a high-precision rule baseline now; the scalable ML design adds a LightGBM scorer and optional neural reranker.
5. **Enforce exclusivity and validate** — do not assign the same Source 2/3 record to multiple Source 1 businesses, then validate the required output files.

## 2. Final result and evaluation

| Metric | Result |
|---|---:|
| Team-reported matching accuracy | **0.99** |
| Official documented held-out macro F₀.₅ | **0.991762** |
| Original exact-normalization baseline F₀.₅ | 0.975270 |
| Improvement in held-out F₀.₅ | +0.016492 |
| Required Source 1 output rows | 1,732,544 |
| Non-empty final predictions | 218,189 |
| Organizer submission validator | PASS |

**Metric note:** `0.99` is the team-reported accuracy figure. The challenge’s documented official evaluation measure is **macro F₀.₅**, which is not directly comparable to accuracy. We therefore report both transparently and use macro F₀.₅ for challenge-result claims.

## 3. Methodology used

The final submitted approach is a deterministic, explainable, high-precision entity matcher.

- **Name normalization:** lowercase text, remove punctuation/placeholders, fold Latin diacritics, handle organizer-provided legal suffixes, and treat `&` and `and` consistently.
- **Address normalization:** tokenize addresses, remove placeholders, create order-independent address keys, and standardize organizer-provided abbreviations such as `Rd/Road` and `St/Street`.
- **Country partitioning:** only compare records within the same country. This is data-driven and supports unseen country labels without hard-coding a country list.
- **Joint exact key:** create `(country, normalized_name_key, normalized_address_key)` and accept a candidate only when the full joint key agrees.
- **Global exclusivity:** one Source 2/3 entity ID can be assigned to at most one Source 1 entity.
- **Output validation:** write `matching_results.tsv` and `candidate_pairs.tsv`; validate schema, row count, IDs, duplicates, and output format with the supplied validator.

The final method uses only the challenge data and organizer-provided normalization examples. It does not use external business databases, geocoding APIs, registries, or web lookup enrichment.

## 4. Candidate generation / blocking strategy

**Blocking** is the process of reducing the matching search space before expensive scoring. It is essential at this scale.

The submitted baseline uses the exact joint key as its candidate generator. The scalable candidate-generation plan is a country-partitioned union of:

- normalized name-token retrieval;
- normalized address-token retrieval;
- IDF-weighted inverted indexes;
- character n-gram / TF-IDF similarity for spelling and formatting variation; and
- numeric address-token matching for house/building numbers.

Candidate quality is evaluated with **recall@K**: the proportion of true matches retained among the top K candidates. This ensures the downstream model can only score a small, relevant candidate set rather than all possible record pairs.

## 5. Model architecture and feature engineering

### Final shipped model

The final submission is a **rule-based exact joint-key matcher**. It was selected for transparency, reproducibility, strong precision, and a validator-clean end-to-end submission.

### Scalable ML architecture

| Stage | Purpose | Examples of features / techniques |
|---|---|---|
| Candidate retrieval | Find likely matches efficiently | blocking keys, inverted index, TF-IDF, char n-grams, recall@K |
| Gradient-boosted scorer | Score candidate pairs | LightGBM, token Jaccard, cosine similarity, edit distance, numeric agreement, country agreement |
| Neural reranker | Improve difficult semantic matches in top-K | transformer embeddings, bi-encoder, cross-encoder, GPU inference |
| Decision layer | Produce final links | threshold tuning, macro F₀.₅ optimisation, exclusivity-constrained assignment |

Feature-engineering terms used in this solution: **raw versus normalized features, name similarity, address similarity, token overlap, Jaccard similarity, TF-IDF cosine similarity, character n-grams, edit distance, numeric agreement, country feature, legal-suffix feature, missing-value indicator, feature ablation, calibration, class imbalance, and threshold tuning**.

## 6. AWS execution and the 8 GiB → 64 GiB RAM solution

### Issue identified

The first AWS EC2 runner was an `m7i-flex.large` with **2 vCPU and 8 GiB RAM**. Full-scale indexing and joins over millions of records caused memory pressure: the notebook process reached **93.2% memory use** and active swap. A 16 GiB swap file avoided an out-of-memory crash, but it did not provide usable throughput for dictionary-heavy indexing; repeated disk paging made the job effectively stall.

### How we solved it on AWS

We treated this as a compute-sizing and data-processing problem rather than a model problem.

1. **Right-size compute:** use a 64 GiB AWS instance (`m7i.4xlarge`, 16 vCPU / 64 GiB) as the minimum for the full rule baseline and noise-mining stages. Use larger memory such as `r7i.4xlarge` (128 GiB) for full-scale sparse blocking. Equivalent SageMaker CPU instances can be chosen for the same workload.
2. **Use memory-bounded processing on the 8 GiB runner:** process limited batches of Source 1 records, run a 5,000-record stratified pilot before a full pass, and never materialize a global all-record join.
3. **Control intermediate data:** use Parquet artifacts, DuckDB disk spilling capped at 4 GiB, compact/fingerprinted indexes, and query batches of at most 100 Source 1 references.
4. **Use swap only as a safety net:** swap prevents crashes; it is not a substitute for RAM. If swap-in/swap-out becomes high, resize the instance rather than waiting for a stalled process.
5. **Use AWS storage and identity correctly:** keep data/artifacts on Amazon S3 and EBS; use the EC2 IAM role `ber-ec2-s3-role` for approved S3 access; execute long jobs with `nohup` and record logs, PIDs, metrics, and outputs.

### AWS services used

| AWS service | Role in the project |
|---|---|
| Amazon EC2 | Primary execution runtime for Python notebooks, indexing, validation, and long-running batch work |
| Amazon S3 | Dataset staging, code/data hand-off, durable artifacts, outputs, and submission package storage |
| AWS IAM | Least-privilege instance-role access to S3; identity verification with AWS STS |
| Amazon EBS gp3 | Persistent 100 GiB project volume surviving EC2 instance-type changes |
| Amazon SageMaker AI | Portable notebook and future scale-up option for high-memory CPU/GPU experimentation |
| AWS Console | Instance sizing, storage, IAM, quotas, monitoring, and cost management |

## 7. Reproducibility, experiments, and deliverables

- Portable notebooks: setup, metric/split, normalization, blocking, and submission stages.
- Pinned Python dependencies: NumPy, pandas, PyArrow, DuckDB, RapidFuzz, scikit-learn, SciPy, LightGBM, JupyterLab, and IPython kernel.
- Intermediate artifacts: **Parquet** for efficient storage and **JSONL** (`artifacts/runs.jsonl`) for experiment tracking.
- Source modules: normalization, metrics, splits, blocking, baseline matcher, submission writer, and validator integration.
- Submission files: `matching_results.tsv` and `candidate_pairs.tsv`.
- Version history: retain notebook outputs, code revisions, experiment configuration, validation metrics, and leaderboard submissions.

## 8. Keywords

Amazon ML Challenge, Amazon SageMaker AI, SageMaker Studio, JupyterLab, Amazon EC2, Amazon S3, Amazon EBS, AWS IAM, AWS STS, AWS Console, cloud computing, scalable machine learning, entity resolution, entity matching, record linkage, deduplication, data quality, data normalization, fuzzy matching, blocking, candidate generation, retrieval, inverted index, TF-IDF, character n-grams, lexical matching, string similarity, Jaccard similarity, cosine similarity, edit distance, RapidFuzz, feature engineering, LightGBM, gradient boosting, embeddings, transformer, cross-encoder, bi-encoder, reranking, inference, hyperparameter tuning, threshold tuning, class imbalance, feature ablation, validation split, stratified holdout, macro F₀.₅, precision, recall, recall@K, exclusivity constraint, Parquet, DuckDB, JSONL, experiment tracking, reproducibility, batch processing, memory optimization, right-sizing, 8 GiB RAM, 64 GiB RAM, GPU acceleration, EBS, cost optimisation, output validation, leaderboard, public leaderboard, private leaderboard.

## Conclusion

We built a reproducible, AWS-ready entity-resolution solution that converts noisy business records into validated match outputs. The final rule-based system provides an explainable and high-precision baseline, while the documented blocking → LightGBM → neural-reranking architecture gives a clear path to scale. On the available 8 GiB runner, the memory issue was mitigated through batched, memory-bounded processing; 64 GiB right-sized AWS compute is the required path for full-scale execution.
