# Appendix B — Reproducibility

This appendix documents how to reproduce every result in this dissertation
from a fresh clone of the accompanying repository.

## B.1 Environment

- Python 3.14
- Virtual environment created with `python3 -m venv .venv`
- Dependencies pinned in `requirements.txt` at the project root; installed
  via `pip install -r requirements.txt` (on macOS, sometimes with
  `--break-system-packages` flag)

Key libraries: `pandas`, `numpy`, `matplotlib`, `scipy`, `playwright`,
`yfinance`, `pypdf`, `pymupdf`, `pymupdf4llm`, `rapidfuzz`, `cryptography`,
`xgboost`, `shap`.

## B.2 Data collection order

The collection scripts are order-dependent because each stage joins onto
the spine produced by an earlier stage.

1. `src/collection/02_collect_chittorgarh_details.py` — produces
   `data/raw/raw_ipo_details.csv` and `data/raw/raw_ipo_urls.csv`.
2. `src/collection/03_download_market_data.py` — produces
   `data/raw/raw_nifty50_daily.csv` and `data/raw/raw_india_vix_daily.csv`.
3. `src/collection/04_collect_gmp.py` — produces `data/raw/raw_gmp_data.csv`.
4. `src/collection/05_collect_prospectus.py` — produces
   `data/raw/sebi_index.csv`, `data/raw/raw_prospectus_links.csv`, and the
   initial batch of PDFs in `data/prospectus_pdfs/`.
5. `src/collection/06_collect_remaining_prospectus.py` — completes the PDF
   collection where automated retrieval failed on the first pass.
6. `src/collection/07_fetch_final_7.py` — obtains the final seven
   hand-verified prospectus URLs.

Every collection script uses generous timeouts and retry logic. Individual
scripts are idempotent and may be re-run without side effects.

## B.3 Cleaning order

1. `src/processing/00_pre_cleaning_audit.py` — read-only diagnostic pass.
2. `src/processing/01_data_cleaning.py` — produces
   `data/processed/master_ipo_dataset.csv`.

## B.3a Risk-section extraction and certification order

The risk-section pipeline (Chapter 3, §3.7) is order-dependent because
each stage produces the input state that the next stage audits or
refines. This pipeline runs in parallel to §B.3 above — the cleaning
pipeline produces the numeric master dataset, while §B.3a produces the
certified corpus of risk-section markdown files.

1. `src/processing/03a_extract_risk_sections.py` — original regex-based
   extractor, retained for provenance only. Produces the initial
   `data/processed/risk_sections/*.md` files and the historical
   `_extraction_log.csv`. Not used by any downstream analysis, but
   preserved to document how the pipeline evolved.
2. `src/processing/07_reextract_and_certify.py` — re-extracts all 416
   PDFs using content-based multi-signal bounds detection (D-29),
   audits each extraction against the source PDF under the coverage
   and bigram-Jaccard thresholds (D-30), and applies the plain-text
   fallback for `pymupdf4llm` mangled outputs (D-31). Timestamped
   backups of every overwritten .md file are written to
   `data/processed/.backup-risk_sections-YYYYMMDD-HHMMSS/`. Produces
   `reports/tables/eda/07_reextract/certification_log.csv`. Runtime is
   approximately 60 to 80 minutes on a MacBook Air.
3. `src/processing/08_reextract_v2.py` — targeted re-extraction for the
   two failure modes surfaced by the first exploratory pass on the risk
   sections: the SEBI-2022 summary-section trap and the unbounded-end
   failure. Applies the multi-candidate start selection (D-32) and the
   90-page hard cap (D-33) to files matching the two problem-file
   patterns. Produces
   `reports/tables/eda/08_reextract_v2/certification_log_v2.csv`.
   Runtime is approximately 5 to 10 minutes.

The authoritative source of per-file extraction metadata is the
combination of the two certification logs from steps 2 and 3; the older
`_extraction_log.csv` from step 1 is preserved for historical
provenance but is not used by any downstream script.

Two files in the certified corpus require special notes: Sai Silks
(Kalamandir) Ltd. was manually extracted (D-34) and its provenance is
recorded in Appendix A rather than in a certification log; Manoj
Vaibhav Gems N Jewellers Ltd. is retained as the Tesseract OCR output
from Chapter 3 §3.6.4, and is not re-processed by either script (D-35).

## B.4 Exploratory analysis order

Scripts in `src/eda/` are ordered by number and should be run in order,
because each one may depend on earlier findings recorded in the thesis text.

1. `src/eda/01_target_analysis.py`
2. `src/eda/02_univariate_features.py` *(pending)*
3. `src/eda/03_bivariate.py` *(pending)*
4. `src/eda/04_temporal_and_regime.py` *(pending)*
5. `src/eda/05_risk_section_eda.py` — analyses the certified risk-section
   corpus produced by §B.3a. Reports length distribution, numbered-item
   counts, concept prevalence (both overall and by year), temporal
   n-gram drift, and length-versus-return correlations. Writes figures
   and tables under `reports/figures/eda/05_risk_sections/` and
   `reports/tables/eda/05_risk_sections/`, and the per-IPO summary
   `data/features/risk_section_summary.csv`. This script must be re-run
   after any modification to the risk-section corpus (for example,
   after running `07_reextract_and_certify.py` or `08_reextract_v2.py`).

All EDA scripts write PNG and PDF figures to `reports/figures/eda/` and CSV
tables to `reports/tables/eda/`. Both directories are created by the
scripts themselves if not present.

A shared style helper at `src/eda/_style.py` provides consistent typography,
palette, and figure export utilities for every EDA script.

## B.5 Feature engineering

1. `src/processing/02_feature_engineering.py` — reads
   `data/processed/master_ipo_dataset.csv` (produced by §B.3) and
   produces `data/features/features_numeric.csv` (416 rows × 26
   columns). The script is deterministic: same master file in, same
   feature file out. No random seed is required.

The script is composed of three phases (Chapter 6, §6.1): a load phase
that reads the master and coerces `listing_date` to a
`pandas.Timestamp`; an engineering phase that constructs each feature
group (transformations, normalisation, financials, broker sentiment,
market context) in the order documented in Chapter 6; and a validation
phase that spot-checks decision-specific counts and skewness reductions
against the values reported in Table 6.1 before the file is written.
The validation phase refuses to write the output if any invariant
fails (row count not 416, presence of `inf` in any numeric column,
skewness of any log-transformed variable more than 2 standard
deviations from Table 6.1).

No imputation or scaling is applied by this script. The primary model
(XGBoost) handles missing values natively (Chapter 8), and any linear
or Ridge baseline imputes at model time using training-set statistics
only. Applying scaling or standardisation to the full dataset at
feature-engineering time would leak test-period statistics into
training-period inputs, in violation of D-08.

Feature-engineering must be re-run whenever the master dataset changes.
The pipeline is idempotent and produces a byte-identical output file on
repeated runs against the same master, which is asserted by a hash
check in the script's validation phase.

## B.6 LLM extraction

## B.6 LLM extraction and risk-feature engineering
 
The risk-extraction pipeline (Chapter 7) runs after the certified
risk-section corpus (§B.3a) and the numeric feature file (§B.5) exist.
It is order-dependent: extraction produces the raw file, engineering
transforms it, and the numeric feature file is required by the
engineering step as a size normaliser.
 
Credentials are read from environment variables named in `config.toml`
and stored in a git-ignored `.env` at the project root (template in
`.env.example`); no key is stored in the repository or in `config.toml`.
 
1. `src/processing/09_extract_llm_risk.py` — reads the certified corpus
   `data/processed/risk_sections/*.md`, the schema
   `src/processing/risk_extraction_schema.py`, the prompt
   `src/processing/system_prompt_risk_extraction.md`, and run parameters
   from `config.toml`. Dispatches each file to the configured model
   (`gpt-5.6-luna` for the study run) under constrained structured
   output, and writes `data/features/features_llm_risk.csv` (416 rows)
   plus the raw JSON response for every file under
   `data/features/llm_raw/`. The run is **resumable**: rows already
   marked `ok` are skipped on restart with no re-billing. A `--dry-run`
   flag validates configuration and counts files without any API call.
   Study-run parameters: `reasoning_effort = low`, output ceiling
   16,000 tokens; realised cost \$21.13 over 18,857,188 input tokens;
   all 416 rows `ok`. Synchronous runtime is approximately one to two
   hours on a MacBook Air.
2. `src/processing/10_engineer_risk_features.py` — reads
   `data/features/features_llm_risk.csv` and exactly one column
   (`assets_log1p`) from `data/features/features_numeric.csv`, and writes
   the modelling matrix `data/features/features_risk_engineered.csv`
   (416 rows × 25 columns). Deterministic: same inputs in, same file out.
   It never reads `first_day_return`. A normalised join key aligns the
   two files (verified to match all 416 issuers with no collisions).
3. `src/processing/qa_flag_risk_features.py` — reads the raw extraction
   and writes `data/features/qa_flags_risk.csv`, a review list of rows
   flagged for manual inspection (non-standard units, extreme values,
   identical litigation/contingent amounts, absent litigation tables,
   likely-promoter-driven counts, counts without an amount), each row
   accompanied by its extraction reasoning trace. Read-only with respect
   to the feature files; it produces a review artefact only.
A separate scorer, `src/processing/score_extraction.py`, embeds the
five-file hand-adjudicated gold set and diffs any trial extraction
against it field-by-field under fixed tolerances (counts and enumerations
matched exactly; amounts within ±1 percent or ₹0.01 crore; percentages
within ±0.5). It is used to validate a model or schema change before a
full run, not in the production path.
 
Reproducibility note. Because a hosted model may change under a fixed
name, the retained raw outputs in `data/features/llm_raw/` — not the
model endpoint — are the authoritative record of what was extracted. A
re-run against a later version of the same model would be validated
against these retained outputs and against the gold set, rather than
assumed identical. The extraction and engineering steps must be re-run
in order whenever the certified corpus changes; the engineering step
alone must be re-run whenever either the raw extraction or the numeric
feature file changes.
 

## B.7 Modelling

*Written after Chapter 8 is complete.*

## B.8 Building the thesis PDF

From the project root:

```
make -C thesis pdf
```

The Makefile in `thesis/` uses `pandoc` to combine chapter files into a
single PDF at `thesis/build/thesis.pdf`. Individual chapters may be built
with `make -C thesis 03_data_collection.pdf`.

## B.9 Reproducing every figure and table in this dissertation

Every figure and table referenced in this dissertation is regenerable from
the scripts listed above. To regenerate everything from scratch:

```
rm -rf data/processed data/features reports/
python3 src/processing/01_data_cleaning.py
python3 src/processing/07_reextract_and_certify.py
python3 src/processing/08_reextract_v2.py
python3 src/processing/02_feature_engineering.py
python3 src/eda/01_target_analysis.py
python3 src/eda/05_risk_section_eda.py
# ... and so on for later scripts as they are written
```

Note that regenerating from scratch will invoke the extraction pipeline
(§B.3a) which takes 60 to 90 minutes end to end. If the certified corpus
already exists and only the analysis needs to be re-run, the extraction
scripts can be skipped.