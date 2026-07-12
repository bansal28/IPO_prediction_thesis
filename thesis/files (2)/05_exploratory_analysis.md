# 5. Exploratory Data Analysis

> **NOTE TO SELF (Hritik):** This chapter is a *live scaffold*. It grows one
> section at a time, as each EDA script is run and its outputs are reviewed.
> The write-up rule (recorded in Appendix A) is that after each EDA script,
> the teaching walkthrough from the chat is jointly refactored into a
> section of this chapter *before* proceeding to the next script.

This chapter presents an evidence-based exploration of the cleaned master
dataset produced in Chapter 4. Its purpose is threefold: to characterise the
distribution and temporal behaviour of the target variable; to describe the
distribution, coverage, and outlier structure of every candidate predictor;
and to justify the design decisions of the feature-engineering stage
(Chapter 6) with data rather than intuition. The exploratory pass is
deliberately sequenced *before* feature engineering, so that feature choices
are motivated by patterns observed in the data rather than by prior
assumptions.

The analysis is implemented in four scripts, each of which produces figures
in `reports/figures/eda/` and tables in `reports/tables/eda/`, and each of
which corresponds to one section of this chapter.

## 5.1 Target variable analysis (`01_target_analysis.py`)

[SECTION TO BE WRITTEN. Source material: the teaching walkthrough in chat
covering `01_target_distribution`, `01_target_temporal`, `01_target_regime`,
`01_target_open_vs_close` and the four accompanying tables. Structure to
follow:
  - 5.1.1 Distribution of first-day return
  - 5.1.2 Temporal structure and the 2024–2025 regime shift
  - 5.1.3 Extreme cases: characteristics of the top gainers and losers
  - 5.1.4 Open-based versus close-based first-day return
  - 5.1.5 Implications carried forward
]

## 5.2 Univariate feature analysis (`02_univariate_features.py`)

*Pending: script has not yet been run.*

## 5.3 Bivariate analysis (`03_bivariate.py`)

*Pending: script has not yet been run.*

## 5.4 Temporal and regime-conditional analysis (`04_temporal_and_regime.py`)

*Pending: script has not yet been run.*

## 5.5 EDA-derived commitments carried to feature engineering

*Pending: consolidated at the end of Section 5 once all four scripts are
complete.*
