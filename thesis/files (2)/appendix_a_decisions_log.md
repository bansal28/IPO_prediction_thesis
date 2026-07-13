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
comparable to ordinary equity IPOs. FPOs are follow-on offerings by
already-listed companies and are subject to a different underpricing
mechanism (Rock, 1986). Including any of these would introduce population
heterogeneity that would confound any modelling claim.

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
listing date. Train ≤ 2023 (194 IPOs), validation = 2024 (90 IPOs),
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
kurtosis 8.64 (Section 5.1.1). Extreme values (in particular Sigachi
Industries at +270 percent) drag the mean substantially above the median
(21.3 percent vs 11.4 percent). Reporting mean-only would give a distorted
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

## D-14 · Known source-data corrections applied inline in cleaning

**Locked:** 12 July 2026, during univariate EDA (Section 5.2).
**Decision.** When a Category-2 data error is identified — an error in the
source data itself, not in our scraper code — the fix is applied inline in
`src/processing/01_data_cleaning.py` in a clearly-labelled "Known
source-data corrections" block immediately before the master is written to
disk. Each correction is a single guarded line accompanied by a comment
stating: the affected IPO, the field, the old value, the new value, the
justification, and whether the correction affects a leakage column or a
predictor.

**Escalation policy.** If more than three such corrections accumulate,
they will be extracted into a dedicated
`src/processing/00b_data_corrections.py` script driven by a fixture CSV at
`data/corrections/data_corrections.csv`, and this appendix entry updated
accordingly. Until then, the inline block is the proportionate response.

**Corrections applied to date:**

| IPO | Field | Old | New | Type | Justification |
|---|---|---|---|---|---|
| Udayshivakumar Infra Ltd. (2023-04-03) | `listing_open` | 0.0 | NaN | leakage column | Chittorgarh detail page reports 0.0, which is impossible for a traded stock. True open must lie in [`listing_low`, `listing_high`] = [29.15, 31.5], but the exact value is not recoverable from the source. `listing_open` is a leakage column (never a predictor) and the modelling target `first_day_return` uses `listing_close` (verified correct at ₹31.5), so this correction has no effect on any downstream model. |

**Justification for the policy.** For an academic thesis, every
transformation from raw to master must be traceable in code. Direct
editing of `master_ipo_dataset.csv` (e.g. in a spreadsheet) is prohibited
because it destroys reproducibility. Building an elaborate
corrections-script infrastructure for a single error would be premature
over-engineering. A small, named, guarded block in the cleaning script,
with an entry in this appendix, is the proportionate response for the
current error count.

**Alternatives considered.**
- *Drop the IPO entirely.* Rejected: the IPO has a valid target
  (`first_day_return = -0.10`, computed from a correct `listing_close`
  and `issue_price`); losing a legitimate observation to correct a single
  leakage column is an over-reaction.
- *Look up the true `listing_open` from BSE historical data.* Rejected
  for now: the value is not used in modelling (leakage column). If EDA
  later surfaces a similar problem in a predictor column, this route
  would be revisited.
- *Hand-edit `master_ipo_dataset.csv`.* Rejected: destroys
  reproducibility, cannot be defended in the viva.

## D-15 · `log1p` transformation for right-skewed positive predictors

**Locked:** 12 July 2026, during univariate EDA (Section 5.2.2).
**Decision.** Eight strictly non-negative continuous predictors are
transformed by `log1p` in the feature set produced by Chapter 6:
`total_issue_size`, `fresh_issue`, `ofs`, `revenue`, `assets`,
`borrowing`, `issue_price`, and `sub_total`. For each variable the log-
transformed form is retained in the feature file. The raw forms of
`issue_price` and `sub_total` are **not** additionally retained (see
D-27 for the reasoning against raw+log double-inclusion).
**Justification.** `log1p` reduces the skewness of the affected
variables substantially, moving them from extremely long-tailed to
approximately symmetric (Table 5.2 / Table 6.1). The transformation is
applied uniformly rather than by variable-specific tuning to preserve
interpretability and to avoid overfitting the transformation to the
training set.

## D-16 · `gmp_return` normalisation of raw grey-market premium

**Locked:** 12 July 2026, following bivariate EDA (Section 5.3).
**Decision.** The raw `gmp_value` (grey-market premium in rupees) is
converted into `gmp_return = gmp_value / issue_price`, a dimensionless
quantity representing the grey-market premium as a fraction of the
issue price. The raw `gmp_value` is not used as a feature.
**Justification.** A ₹50 premium means very different things for a ₹100
IPO (50 percent premium) and a ₹1000 IPO (5 percent premium).
Normalising by issue price makes the signal comparable across IPOs.
This also side-steps the mixed-sign problem that would otherwise
preclude direct `log1p` transformation of the raw `gmp_value`. LOWESS
evidence in Figure 5.8 confirms the log-shape relationship between
grey-market premium and first-day return.

## D-17 · Drop `lot_size` in favour of `issue_price`

**Locked:** 12 July 2026, following bivariate EDA (Section 5.3.1).
**Decision.** `lot_size` is removed from the feature set.
`issue_price_log1p` is retained.
**Justification.** SEBI requires the minimum retail application amount
to be approximately ₹15,000, so `issue_price × lot_size ≈ 15,000`
holds mechanically for every mainboard IPO. This produces a Spearman
correlation of −0.996 between the two variables (Figure 5.6), which
would cause severe multicollinearity in a linear model and would
split SHAP importance across two co-referring features in an XGBoost
interpretation. `issue_price` is retained rather than `lot_size`
because it is the more directly interpretable of the two.

## D-18 · Deal-size composition: log-scale components plus one composition ratio

**Locked:** 12 July 2026, following bivariate EDA (Section 5.3.1).
**Decision.** The three deal-size components `total_issue_size`,
`fresh_issue`, and `ofs` are entered into the feature set in
log-transformed form (`total_issue_size_log1p`, `fresh_issue_log1p`,
`ofs_log1p`), and a single composition ratio
`ofs_ratio = ofs / (fresh + ofs)` is additionally computed. IPOs with
no offer-for-sale component have `ofs_ratio = 0`; IPOs with no
fresh-issue component have `ofs_ratio = 1`.
**Justification.** By construction `total_issue_size = fresh_issue +
ofs`, so the three components are algebraically related. Their raw
pairwise correlations of 0.80 to 0.82 (Figure 5.6) reflect this
identity. Keeping the log-scale components alongside the composition
ratio is a modelling-agnostic choice: XGBoost may find interactions
between the size components that the composite ratio does not
expose, while linear baselines can drop the redundant components at
model time. An earlier feature-engineering attempt also introduced
`fresh_ratio = 1 − ofs_ratio`, which is perfectly redundant with
`ofs_ratio`; that error is retired under D-09.

## D-19 · Financial variables enter both as log-scale levels and dimensionless ratios

**Locked:** 12 July 2026, following bivariate EDA (Section 5.3.1).
**Decision.** Three raw financial variables (`revenue`, `assets`,
`borrowing`) are entered as log-transformed levels (`revenue_log1p`,
`assets_log1p`, `borrowing_log1p`). Three dimensionless ratios are
additionally constructed: `profit_margin = profit / revenue`,
`return_on_assets = profit / assets`, and `debt_to_equity =
borrowing / net_worth`. Raw `profit` and `net_worth` do not enter
the feature set directly — they are sign-mixed and heavily skewed,
and enter naturally via the ratios above.
**Justification.** The five raw financials form a company-size cluster
with pairwise Spearman correlations of 0.5 to 0.86 (Figure 5.6),
reflecting the standard confound that larger companies are large on
every dimension. Ratios normalise for scale and capture composition
(profitability, asset efficiency, leverage). Log-scale levels are
also retained because they carry company-scale information that the
scale-free ratios by construction do not; a modelling-agnostic
feature file provides both.

## D-20 · Negative net-worth handling in `debt_to_equity`

**Locked:** 12 July 2026, following univariate EDA (Section 5.2.2).
**Decision.** For IPOs with `net_worth ≤ 0` (five observations in the
416-IPO study population: Stove Kraft, Chemplast Sanmar, DCX Systems,
SAMHI Hotels, and Indiqube Spaces), `debt_to_equity` is set to NaN
and a companion flag `negative_networth_flag` is set to 1. All other
IPOs receive the computed ratio and a flag of 0.
**Justification.** A negative net-worth denominator makes
`debt_to_equity` uninterpretable as a leverage measure (a highly
indebted, solvent company and an insolvent company can yield
similarly-signed ratios of similar magnitude). Setting NaN preserves
missingness information for XGBoost's native handling, and the flag
allows the model to condition on the qualitative fact of
insolvency separately from the quantitative leverage measure.
**Revision note (D-26).** The count of five reflects the 416-IPO
dataset after the FPO exclusion documented in D-26. An earlier
version of this entry recorded six non-positive-net-worth cases; the
sixth (Vodafone Idea 2024, net_worth −₹97,932 crore) is removed by
D-26 because it is an FPO rather than an IPO.

## D-21 · Broker sentiment: any-avoid flag alongside raw counts

**Locked:** 12 July 2026, following bivariate EDA (Section 5.3.2).
**Revised:** by D-27, 12 July 2026.
**Original decision.** `brokers_avoid` and `brokers_subscribe` were
combined into a composite `broker_sentiment` feature computed as
`brokers_subscribe − brokers_avoid`. A binary companion
`any_avoid_flag = 1 if brokers_avoid > 0 else 0` was additionally
supplied.
**Original justification.** The LOWESS smoother for `brokers_avoid` in
Figure 5.8 is essentially a step function: the difference between
zero avoid-recommendations and any avoid-recommendation is large,
but the marginal information from a second or third avoid is small.
The raw count is also 74 percent zeros.
**Revised decision (D-27).** The composite `broker_sentiment` is not
included in the feature file. Both raw counts (`brokers_subscribe`,
`brokers_avoid`) are retained in the feature file alongside
`any_avoid_flag`, so that downstream models can combine them as they
choose. See D-27 for the reasoning.

## D-22 · Regime boundary anchored at 2025-01-01

**Locked:** 12 July 2026, following the regime-break test
(Section 5.4.4).
**Revised:** by D-28, 12 July 2026.
**Original decision.** A binary feature `regime_post_2024 = 1 if
listing_date >= 2025-01-01 else 0` was added to the feature file to
encode the regime boundary identified in Section 5.4.4.
**Original justification.** The Mann-Whitney U test at the pre-2025
versus 2025+ boundary yields p = 6.20 × 10⁻⁷, approximately 45,000
times smaller than the p-value at the pre-2024 versus 2024+ boundary
(p = 2.81 × 10⁻²). Mood's median test corroborates
(p = 2.13 × 10⁻⁶ at the 2025-01-01 boundary).
**Revised decision (D-28).** No regime dummy is included in the
feature file. The regime signal is carried by the market-context
features (`nifty_close`, `vix_close`, `nifty_7d_return`,
`nifty_30d_return`) instead. See D-28 for the reasoning.

## D-23 · GMP-slice reporting in Chapter 9

**Locked:** 12 July 2026, following bivariate EDA (Section 5.3.3).
**Decision.** Chapter 9 reports model performance metrics for the
augmented and baseline models on three test-set slices: the full
test set; the GMP-available subset of the test set; and the
GMP-absent subset of the test set. GMP-absent-slice metrics are
accompanied by a sample-size caveat where the subset falls below
20 observations.
**Justification.** The Chapter 5 finding that `sub_total` and other
demand signals compensate for the absence of GMP (Figure 5.9,
Section 5.3.3) implies that risk-side features (including LLM-
extracted risk features) are most likely to add incremental
predictive value in the GMP-absent slice. Reporting metrics only in
aggregate would obscure this. Slice-level reporting also makes the
narrative of "does the model actually help when the dominant signal
is missing?" answerable, which is the core research question of the
dissertation.

## D-24 · Year-conditionally unstable features flagged in interpretation

**Locked:** 12 July 2026, following temporal EDA (Section 5.4.2).
**Decision.** In every Chapter 9 SHAP-value plot, features whose
year-conditional Spearman correlation with the target crosses zero,
or whose absolute correlation falls below 0.10, in any single year
of the study period are flagged (with a marker or footnote) as
"year-conditionally unstable." The current list is:
`brokers_avoid`, `nifty_30d_return`, `nifty_7d_return`, `assets`.
`assets` is included on account of the sign-flip documented in
Section 5.4.3 (train −0.24 → test +0.11). This list is refreshed if
features are added or removed in Chapter 6.
**Justification.** Section 5.4.2 shows that these features carry a
predictive signal in some years and none (or a reversed sign) in
others. A high SHAP importance for such a feature indicates that the
model has used it to fit training data, but does not imply the
feature will contribute cleanly to test-set predictions. Flagging
these features in interpretation is intellectually honest and
prevents over-claiming.

## D-25 · Drop `face_value` from the feature set

**Locked:** 12 July 2026, during feature engineering (Chapter 6).
**Decision.** `face_value` is not included in the numeric feature
matrix.
**Justification.** Two factors motivate the drop. First, the
target-correlation evidence in Section 5.3.2 shows Spearman ρ = −0.02
between `face_value` and `first_day_return`, indistinguishable from
noise. Second, the variable has a degenerate category structure:
the value ₹4 is taken by exactly one IPO in the study (Nazara
Technologies, 2021), which would either require pooling with a
neighbouring category (a hard-to-defend one-off patch) or would
force any one-hot encoding to include a column that is 1 for a
single observation. Given the absence of any predictive value, the
cleanest resolution is exclusion.

## D-26 · Removal of three Follow-on Public Offers from the working dataset

**Locked:** 13 July 2026, revisiting Chapter 4 §4.3.
**Decision.** Three listings recorded by the Chittorgarh IPO tracker
as mainboard IPOs are, on closer examination, Follow-on Public
Offers (FPOs) by already-listed companies and are removed from the
master by exact-name match in `src/processing/01_data_cleaning.py`:

1. Yes Bank Ltd. (listed 27 July 2020; ₹15,000 crore FPO)
2. Ruchi Soya Industries Ltd. (listed 8 April 2022; ₹4,300 crore FPO)
3. Vodafone Idea Ltd. (listed 25 April 2024; ₹18,000 crore FPO)

After the exclusion the master contains 416 mainboard equity IPOs,
down from 419 (which was the count after the REIT/InvIT exclusion
in the original §4.3).

**Justification.** Chapter 1 §1.4 excludes FPOs from the study on
theoretical grounds. The underpricing mechanism proposed by Rock
(1986) — asymmetric information between issuer and investor at the
moment of first listing — cannot apply to an offering by a company
whose shares have been trading publicly for years. Whatever
explains an FPO's first-day return is a fundamentally different
mechanism from IPO underpricing and should not be pooled with the
primary sample. The exclusion is on economic-scope grounds, not on
data-availability grounds: all three companies have Red Herring
Prospectuses on SEBI's Public Issues portal (Ruchi Soya
additionally filed a Draft RHP), and their RHPs contain risk-factor
disclosures comparable to those of the retained IPOs.

The exclusion is by exact-name match rather than regex to avoid the
risk that a substring like "Yes Bank" could accidentally match
another company.

**Downstream cascade.** The FPO exclusion required re-running the
data-cleaning script, the feature-engineering script, and all four
EDA scripts. The re-run confirmed that no feature-engineering
decision needed to change on the 416-row sample versus the 419-row
sample: skewness ordering, redundancy correlations, and the regime
break p-value are all essentially unchanged.

## D-27 · Broker sentiment: raw counts + any-avoid flag, no composite

**Locked:** 13 July 2026, revising D-21.
**Decision.** The feature file provides `brokers_subscribe`,
`brokers_avoid`, and `any_avoid_flag`. The composite
`broker_sentiment = brokers_subscribe − brokers_avoid` originally
constructed under D-21 is not included.
**Justification.** A subtraction of the avoid count from the
subscribe count conflates two independent signals. An IPO with
twelve subscribes and two avoids scores the same net sentiment
(+10) as an IPO with ten subscribes and zero avoids (+10) — but
these are meaningfully different configurations, and the composite
does not preserve the distinction. The current design provides
both raw counts and the binary any-avoid flag separately, and
lets downstream models combine them as they will.

Whether raw `brokers_avoid` is redundant with `any_avoid_flag`
given the 74-percent-zero step-function structure is a
modelling-time question rather than a feature-engineering-time
question. Linear baselines are expected to drop one or the other;
XGBoost is expected to use whichever gives cleaner splits at each
node.

## D-28 · No regime dummy in the feature file

**Locked:** 13 July 2026, revising D-22.
**Decision.** The feature file does not include a `regime_post_2024`
dummy or any equivalent binary indicator of the 2024–2025 regime
boundary. The regime signal is carried entirely by the market-
context features (`nifty_close`, `vix_close`, `nifty_7d_return`,
`nifty_30d_return`).
**Justification.** The original D-22 anchored the regime dummy at
2025-01-01 because the Mann-Whitney U test in Section 5.4.4
yielded its smallest p-value at that boundary. That test used the
test-period observations (2025–2026) as part of its sample when
computing the p-value at each candidate boundary. Choosing the
anchor date on the basis of that test therefore consulted
test-period information at feature-design time — a form of
information leakage that this dissertation's methodology otherwise
avoids.

Two clean resolutions are available: (a) anchor the dummy at an
externally-verifiable market event (the Nifty peaked at 26,216 on
27 September 2024 and corrected roughly 15 percent through
February–March 2025), or (b) omit the dummy and rely on the
market-context features to carry the regime signal. Option (b) is
adopted because the market-context features are already in the
feature set (`nifty_close`, `vix_close`, and the two trailing
returns), a model can distinguish pre- and post-correction periods
directly from their values (`nifty_close ≈ 26,000` versus
`≈ 22,500`), and adding a binary dummy on top would introduce
redundancy without adding information. Option (a) remains a
defensible alternative and can be added as a sensitivity analysis
in Chapter 8 if validation-set performance warrants it.

---

*Additional entries will be added as further decisions are made during
LLM extraction (Chapter 7), and modelling (Chapter 8).*