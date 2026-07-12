# Predicting Indian IPO First-Day Return Using Only Pre-Listing Information

**MSc Artificial Intelligence Thesis — King's College London**
Author: Hritik Bansal
Supervisor: Peter

## Research Question
Does structured risk information extracted via LLM from IPO prospectuses
significantly improve first-day return prediction beyond numeric features alone?

## Data Sources
| Source | What | Location |
|--------|------|----------|
| Chittorgarh.com | Listing outcomes (434 IPOs, 2019-2026) | `data/raw/chittorgarh/` |
| Chittorgarh detail pages | Subscription, financials, broker ratings | `data/raw/raw_ipo_details.csv` |
| NSE via yfinance | Nifty 50, India VIX daily prices | `data/raw/raw_nifty50_daily.csv` |
| InvestorGain.com | Grey Market Premium | `data/raw/raw_gmp_data.csv` |
| SEBI (via Chittorgarh) | DRHP/RHP prospectus PDFs (427) | `data/prospectus_pdfs/` |
| Ghosh et al. (2024) | Cross-validation reference | `data/raw/ghosh_mainboard_v18.xlsx` |

## How to Reproduce
Run scripts in order:

### Data Collection (already done)
```
src/collection/step3_collect_details.py
src/collection/step4_market_data.py
src/collection/step5_collect_gmp.py
src/collection/step6_collect_prospectus.py
src/collection/step6b_collect_more_pdfs.py
```

### Data Processing & Modeling
```
python src/processing/01_data_cleaning.py        # raw -> clean merged dataset
python src/processing/02_feature_engineering.py   # compute model-ready features
python src/processing/03_llm_extraction.py        # extract risk fields from PDFs
python src/modeling/04_baseline_model.py           # numeric-only gradient boosting
python src/modeling/05_augmented_model.py          # numeric + LLM risk features
python src/modeling/06_evaluation.py               # Clark-West test + SHAP plots
```

## Project Structure
```
Hritik_thesis/
├── data/
│   ├── raw/                  # original collected data (never modified)
│   ├── processed/            # cleaned & merged datasets
│   ├── features/             # model-ready feature matrices
│   └── prospectus_pdfs/      # 427 DRHP/RHP documents
├── src/
│   ├── collection/           # data collection scripts
│   ├── processing/           # cleaning, features, LLM extraction
│   └── modeling/             # baseline, augmented, evaluation
├── notebooks/                # Jupyter exploration
├── outputs/                  # plots, tables, figures
├── thesis/                   # thesis document
└── README.md
```
