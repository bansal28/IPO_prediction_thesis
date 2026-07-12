# Appendix A — Decisions Log

This appendix records every locked methodological decision made during the
dissertation, together with the evidence or reasoning that justified it and
the date of the decision. It is append-only. If a decision is subsequently
revised, the original entry is retained and a new entry is added noting the
revision.

The purpose of this log is to make the design of the dissertation
auditable — a reader or examiner can trace any modelling or preprocessing
choice back to the reasoning behind it.

---

## D-01 · Data source scope: mainboard equity IPOs only

**Locked:** at project start.
**Decision.** The universe of study is Indian mainboard equity IPOs listed
2019 through mid-2026. SME-platform IPOs, REITs, InvITs, and FPOs are
excluded.
**Justification.** SME issues follow a different listing regime with
substantially different investor eligibility and pricing behaviour. REITs
and InvITs are structured products whose first-day dynamics are not
comparable to ordinary equity IPOs. Including them would introduce
population heterogeneity that would confound any modelling claim.

## D-02 · Target definition: close-based first-day return

**Locked:** at project start.
**Decision.** The primary target is
`first_day_return = (listing_close − issue_price) / issue_price`, using the
detail-page `listing_close`. An open-based alternative
(`first_day_open_return`) exists in the master but is not used as the
primary target.
**Justification.** This definition matches the convention used by Ritter
(1991) and by Ghosh, Zheng, and Lopez-Lira (2024), and it maximises
comparability with prior work. EDA (Section 5.1.4) confirms that open-based
and close-based first-day return are correlated at r = 0.946, so the
alternative would yield essentially the same modelling problem.

## D-03 · Evaluation regime: strictly temporal, never random

**Locked:** at project start.
**Decision.** Train, validation, and test splits are always defined by
listing date. Train ≤ 2023 (196 IPOs), validation = 2024 (91 IPOs),
test = 2025–2026 (132 IPOs). No random splitting or k-fold cross-validation
that crosses year boundaries is used at any point.
**Justification.** IPO pricing behaviour is time-dependent (see the
2024–2025 regime shift documented in Section 5.1.2). Random splitting would
leak information about the future into the training set and would produce
optimistic estimates of test-time performance. Temporal splitting is the
only defensible design for a forecasting task.

## D-04 · Listing-close is sourced from the detail page, never the tracker

**Locked:** during data collection (Chapter 3).
**Decision.** For every IPO, `listing_close` is taken from the Chittorgarh
detail page, not from the yearly tracker CSV.
**Justification.** Direct comparison against exchange records showed the
detail page correct in all seven cases where the tracker disagreed
(exemplar: Mankind Pharma, true BSE close ₹1,424.05, detail page correct,
tracker incorrect at ₹1,080).

## D-05 · Grey-market premium is sourced from InvestorGain only

**Locked:** during data collection (Chapter 3).
**Decision.** All GMP values in the master come from InvestorGain. No other
grey-market data source is joined in.
**Justification.** Different trackers report different values for the same
IPO on the same day; mixing sources would introduce measurement
heterogeneity that could not be distinguished from real signal in
downstream analysis. Consistency across a single source is preferred.

## D-06 · GMP-equal-to-zero interpretation, by year

**Locked:** during data cleaning (Chapter 4).
**Decision.**
- 2019: all GMP values set to missing.
- 2020: GMP = 0 set to missing *only if* the observed first-day return
  exceeds 15 percent.
- 2021 and later: GMP = 0 is retained as a genuine signal.

A companion flag column `gmp_available` marks whether GMP was tracked and
reported.
**Justification.** In 2019, InvestorGain's grey-market tracking was not
established; IPOs recorded as GMP = 0 (e.g. IRCTC, first-day return +95
percent) are clearly untracked rather than signalling no premium. From
2021 onward, IPOs with reported GMP = 0 consistently listed around zero
first-day return on average, supporting the interpretation of GMP = 0 as
an informative signal in that period.

## D-07 · Listing-day OHLC excluded from all feature sets

**Locked:** during data cleaning (Chapter 4).
**Decision.** `listing_open`, `listing_close`, `listing_high`, `listing_low`,
and any derivatives are retained in the master strictly for target
computation and reproducibility. They must never appear in any feature set
supplied to a model.
**Justification.** These values are observed on the listing day itself.
Using them as predictors would be data leakage in the strict sense and
would invalidate any modelling claim.

## D-08 · Market context merged strictly prior-day, leakage-safe

**Locked:** during data cleaning (Chapter 4).
**Decision.** Nifty 50 and India VIX values are merged into each IPO row
using `pandas.merge_asof(direction='backward', allow_exact_matches=False)`,
guaranteeing that the joined market value is from a trading date strictly
earlier than the IPO's listing date.
**Justification.** Same reasoning as D-07. The listing-day market close is
not observed at the time of the modelling decision (pre-listing) and must
not be a predictor.

## D-09 · Feature engineering follows exploratory data analysis, not the other way around

**Locked:** on 12 July 2026, mid-project.
**Decision.** Feature engineering must not be performed until exploratory
data analysis on the cleaned master is complete and its findings have been
recorded. An earlier feature-engineering script (produced before EDA) is
retired and no state from it is retained. The final feature-engineering
script (Chapter 6) is written after Section 5.5 of this dissertation is
complete.
**Justification.** Feature-engineering decisions such as log transformation
of skewed variables, treatment of missing values, and identification of
redundant candidates require empirical justification from the data itself.
Making these decisions on prior assumption produced two redundancy bugs in
the retired script (`fresh_ratio ≡ 1 − ofs_ratio`;
`gmp_return_missing ≡ 1 − gmp_available`) that would not have survived
even a simple correlation heatmap.

## D-10 · Data-source consistency for GMP: name-aware merge, with brand-to-legal-name overrides

**Locked:** during data cleaning (Chapter 4).
**Decision.** The GMP merge into the master uses a name-aware join with an
eleven-entry override dictionary mapping trading names (Paytm, Firstcry,
etc.) to legal names (One 97 Communications, Brainbees Solutions, etc.).
Where two IPOs collide on a (issue price, listing date) key, disambiguation
is by company-name token overlap.
**Justification.** Indian IPOs are widely known by trading names that differ
from the legal names on Chittorgarh. A naive (issue price, listing date)
join produced an incorrect GMP assignment between GNG Electronics and
Indiqube Spaces (both listed 30 July 2025 at ₹237). The name-aware fix
correctly retains GNG's GMP of ₹85 and Indiqube's GMP of 0.

## D-11 · Reporting rule: median and IQR, not mean and standard deviation

**Locked:** on 12 July 2026, during EDA of the target.
**Decision.** Wherever central tendency and dispersion are reported for the
target or for skewed features, the primary summary statistics are the
median and the interquartile range. Mean and standard deviation may be
reported alongside, but never alone.
**Justification.** The target `first_day_return` has skew 2.36 and excess
kurtosis 8.69 (Section 5.1.1). Extreme values (in particular Sigachi
Industries at +270 percent) drag the mean substantially above the median
(21.3 percent vs 11.5 percent). Reporting mean-only would give a distorted
picture of the "typical" IPO experience.

## D-12 · Model-error metric family: MAE and median absolute error primary; RMSE secondary

**Locked:** on 12 July 2026, during EDA of the target.
**Decision.** Model evaluation reports mean absolute error (MAE) and
median absolute error as primary error metrics, with root mean squared
error (RMSE) reported as a secondary metric. Rank metrics (Spearman rank
correlation, Kendall's tau) are reported alongside error metrics.
**Justification.** RMSE squares the error, which gives disproportionate
weight to a small number of large-return outliers. MAE and median absolute
error are more representative of typical prediction accuracy on a skewed
target. Rank metrics matter because in the 2025–2026 regime, absolute
predicted return is compressed while the relative ordering of IPOs
(which is the more useful quantity in practice) remains meaningful.

## D-13 · Reporting all results by year in every table

**Locked:** on 12 July 2026, during EDA of the target.
**Decision.** Every model-performance table reports metrics not only pooled
across the test period but also broken down by test-set year (2025 and
2026 separately).
**Justification.** The regime shift documented in Section 5.1.2 means that
a single pooled test-set metric would hide the year-to-year variation in
predictability. Yearly breakdown makes the regime story visible and
supports interpretation of results.

---

*Additional entries will be added as further decisions are made during
feature engineering (Chapter 6), LLM extraction (Chapter 7), and modelling
(Chapter 8).*
