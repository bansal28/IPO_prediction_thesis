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
`yfinance`, `pypdf`, `rapidfuzz`, `cryptography`, `xgboost`, `shap`.

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

## B.4 Exploratory analysis order

Scripts in `src/eda/` are ordered by number and should be run in order,
because each one may depend on earlier findings recorded in the thesis text.

1. `src/eda/01_target_analysis.py`
2. `src/eda/02_univariate_features.py` *(pending)*
3. `src/eda/03_bivariate.py` *(pending)*
4. `src/eda/04_temporal_and_regime.py` *(pending)*

All EDA scripts write PNG and PDF figures to `reports/figures/eda/` and CSV
tables to `reports/tables/eda/`. Both directories are created by the
scripts themselves if not present.

A shared style helper at `src/eda/_style.py` provides consistent typography,
palette, and figure export utilities for every EDA script.

## B.5 Feature engineering

*Written after Chapter 6 is complete.*

## B.6 LLM extraction

*Written after Chapter 7 is complete.*

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
rm -rf data/processed reports/
python3 src/processing/01_data_cleaning.py
python3 src/eda/01_target_analysis.py
# ... and so on for later scripts as they are written
```
