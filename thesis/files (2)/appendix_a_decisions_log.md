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

## D-29 · Content-based bounds detection over single-regex extraction

**Locked:** 14 July 2026, during risk-section pipeline hardening
(Chapter 3, §3.7).
**Decision.** Risk Factors bounds detection is implemented as a
multi-signal content scoring scheme rather than a single header
regex. A page qualifies as a candidate section start when its
combined score across strong content anchors, structural headers,
and weak content anchors reaches 3 (Chapter 3, §3.7.2). Section
end is detected by any of six explicit next-section title patterns
followed by a strict "SECTION [Roman] — [UPPERCASE_TITLE]"
catch-all with a broad Unicode separator character class.
**Justification.** Empirical evidence from the initial extraction
pass identified three failure modes for single-regex detection
(Chapter 3, §3.7.1): body-text false positives on end detection
(Inventurus), front-matter table-of-contents false positives on
start detection (Anand Rathi 2005), and font-encoding artefacts in
separator characters (Go Fashion, where the em-dash rendered as
`±`). No single-regex rule can defend against all three
simultaneously. The multi-signal approach requires several
independent indicators to agree before accepting a page as
section start, which is empirically robust to any one indicator
misfiring.

## D-30 · Extraction certification thresholds: coverage 0.60 to 1.50, bigram Jaccard 0.50

**Locked:** 14 July 2026, during risk-section pipeline hardening
(Chapter 3, §3.7.3).
**Decision.** Every fresh extraction is audited against a
ground-truth plain-text extraction of the same page range on two
metrics: a coverage ratio (markdown word count divided by
plain-text word count) required to lie in [0.60, 1.50], and a
bigram Jaccard content-overlap coefficient computed on the opening
12,000 characters of each, required to be at least 0.50. An
extraction that passes both thresholds is written to the
`risk_sections/` directory (after backing up the existing file);
an extraction that fails is logged to a manual-review CSV and the
existing file is left untouched.
**Justification.** The coverage ratio detects extraction volume
mismatches (dropped content in markdown, or bloated markdown
noise); its lower bound of 0.60 accommodates minor content
reformatting by `pymupdf4llm`, and its upper bound of 1.50
accommodates minor markdown decoration. The bigram Jaccard
coefficient detects extraction *location* mismatches — the case
where the markdown and plain text are internally consistent but
neither corresponds to the actual Risk Factors section. Bigrams
are used rather than unigrams because the corpus has a large
shared general-financial vocabulary that inflates unigram Jaccard
on any two prospectus pages; bigrams tighten the check to
same-content agreement. Empirical calibration on a validation
set of five prospectuses (Chapter 3, §3.7.3) confirms clean
extractions above 0.90 on both metrics, mangled extractions below
0.30 on Jaccard, and truncated extractions below 0.60 on coverage.

## D-31 · Plain-text fallback for pymupdf4llm mangled outputs

**Locked:** 14 July 2026, during risk-section pipeline hardening
(Chapter 3, §3.7.4).
**Decision.** When `pymupdf4llm` markdown extraction fails audit
under D-30 despite correctly-detected bounds, and when a
plain-text extraction of the same bounds would exceed 5,000
words, the .md file is written using the plain-text extraction
wrapped in a minimal markdown header. The file's first line
records that the plain-text fallback was used.
**Justification.** For a small number of PDFs with non-standard
table-cell encodings (Go Fashion is the only case in the study
corpus), `pymupdf4llm` produces mangled output — squashed words,
lost table cells — that fails the coverage check even when the
selected page range is correct. Plain-text extraction on the
same range preserves every word of the source content, at the
cost of losing markdown-formatted table structure. This is a
strictly better failure mode than either keeping the mangled
markdown or leaving the previous (broken) extraction in place.
The 5,000-word floor prevents the fallback from being invoked
when the underlying page range itself yielded very little text.

## D-32 · Multi-candidate start selection for bounds detection

**Locked:** 14 July 2026, following Phase 6 exploratory analysis
(Chapter 3, §3.7.5).
**Decision.** When multiple pages in a PDF qualify as candidate
section-start pages under the D-29 scoring rule, the extraction
uses the (start, end) pair whose extracted range contains the
most text, rather than the earliest qualifying start.
**Justification.** Post-2022 SEBI disclosure guidelines mandate a
"Summary of Risk Factors" subsection in the executive summary of
every offer document, listing the top ten risks in condensed
form before the full Risk Factors section proper. This summary
block scores above the D-29 qualifying threshold because it
contains some strong anchors and structural signals, and would be
selected by an earliest-start rule — producing extractions of
1,500 to 3,000 words with exactly ten numbered items detected.
The full Risk Factors section further into the document extracts
to 25,000 to 40,000 words; the summary cannot outweigh the full
section on total content, so a longest-extraction rule reliably
selects the correct section. Pre-2022 prospectuses which have
only a single candidate start page are unaffected by this rule.
Applying the rule surfaced 35 files needing re-extraction; all 35
passed audit under the improved bounds, and the affected files
moved from 1,000–3,000 word extractions to 25,000–45,000 word
extractions.

## D-33 · Hard cap of 90 pages on Risk Factors extraction

**Locked:** 14 July 2026, following Phase 6 exploratory analysis
(Chapter 3, §3.7.5).
**Decision.** Section-end detection is hard-capped at 90 pages
after the detected start, regardless of whether any end-signal
pattern has matched.
**Justification.** No Risk Factors section in the study corpus
exceeds 68 pages at the 99th percentile of section length, so a
90-page cap has no effect on any correctly-bounded extraction.
The cap serves as a safety net for prospectuses where none of the
end-signal patterns match — a failure mode observed on Atlanta
Electricals, whose end-detection walked all the way to the
"Declaration of Directors" on the last page of the document,
producing a 77,361-word extraction that included several
subsequent chapters. With the cap in place the same file
extracts to 40,379 words. The cap is a conservative fallback
rather than a primary mechanism; it operates only when the
end-pattern matching fails entirely.

## D-34 · Manual extraction of Sai Silks (Kalamandir) 2009

**Locked:** 14 July 2026, during risk-section pipeline hardening
(Chapter 3, §3.7.6).
**Decision.** One prospectus in the study corpus, Sai Silks
(Kalamandir) Ltd. (2009 Fixed Price Issue), was manually
extracted by identifying its Risk Factors bounds directly from
the PDF and running `pymupdf4llm.to_markdown(pages=range(11, 24))`
by hand. The resulting file (5,697 words, pages 11 through 23)
is checked into `data/processed/risk_sections/` as the source of
truth for this IPO.
**Justification.** The 2009-vintage Fixed Price Issue format uses
letter-labelled sections ("SECTION – A", "SECTION – B: RISK
FACTORS") rather than the Roman-numeral labelling standard from
around 2010 onward, and its opening sentence uses "investment
involves a degree of risk" rather than "high degree of risk".
None of the D-29 anchor patterns match this document, and the
D-29 auditor correctly flagged it as NO_ANCHOR. Rather than
generalise the anchor patterns to cover a single 2009 outlier —
which would risk introducing false positives on the other 415
prospectuses — the file was extracted manually. This is the
only manually-extracted file in the study corpus. The extraction
target was located by inspecting the PDF directly: pages 11
through 23 begin at "SECTION – B: RISK FACTORS" and end
immediately before "Our Business:" on page 24.

## D-35 · Manoj Vaibhav Gems retained as Tesseract OCR output

**Locked:** 14 July 2026, during risk-section pipeline hardening
(Chapter 3, §3.7.7).
**Decision.** The Manoj Vaibhav Gems N Jewellers Ltd. prospectus
PDF is image-only with no embedded text layer. Its risk-section
.md file, produced by Tesseract OCR at 350 DPI with PSM 6 as
described in Chapter 3, §3.6.4, is retained as the authoritative
source. Every re-extraction stage in `src/processing/07_...` and
`src/processing/08_...` detects the image-only PDF at start and
skips the file without modification.
**Justification.** For an image-only PDF the ground-truth
plain-text extraction underpinning the D-30 audit is unavailable
(both `pymupdf` and `pymupdf4llm` return effectively empty text),
so the audit cannot compare a fresh extraction against a plain-text
baseline. The Tesseract OCR .md file was produced at collection
time under the four-check verification (Chapter 3, §3.6.4) and
manually spot-checked; it contains 23,582 words and 71 numbered
risk items, comparable to the median of the electronic-PDF
extractions. Attempting to re-OCR or substitute the file would
add no signal and risk degrading a known-good extraction.

---
<!--
INSERT these entries into appendix_a_decisions_log.md immediately BEFORE the
closing line "*Additional entries will be added ... (Chapter 8).*"
They continue the numbering from D-35.
-->

## D-36 · Typed interpretable schema in place of opaque embeddings

**Locked:** 17 July 2026, at the start of LLM extraction (Chapter 7,
§7.1–7.2).
**Decision.** Risk factors are extracted into a fixed twelve-field
Pydantic schema of named, typed quantities (litigation counts,
monetary exposures in crore, categorical financial-health flags)
rather than encoded as dense text embeddings. The schema is the
single source of truth for both the model instruction and the human
labelling rule; field descriptions are lifted into the JSON schema via
`use_attribute_docstrings=True`.
**Justification.** The dissertation's sub-questions require feature
identity. SQ2 (which risk features carry signal) is only answerable if
features have names; SQ3 (faithfulness) is only answerable if features
can be compared against a hand-labelled ground truth. Dense embeddings,
as used by Ghosh, Zheng and Lopez-Lira (2024) on an overlapping
universe, have neither property. The typed-schema design is the
methodological point of distinction of this dissertation and is what
makes the risk block auditable.

## D-37 · Schema revision v1 → v3

**Locked:** 17 July 2026, after a five-file scored trial (Chapter 7,
§7.3).
**Decision.** The schema reached its final (v3) form through two
evidence-driven revisions. v1→v2 removed a promoter-share-pledge field
(risk section carries only lock-in boilerplate; real data is in Capital
Structure) and a related-party-transaction amount field (qualitative
only in the risk section; figures reside in the financials). v2→v3
(after scoring against the gold set) split litigation into three
separate counts — criminal, statutory/regulatory-enforcement (tax
*excluded*), and tax — tightened the severe auditor category to require
explicit opinion-modification wording, restricted customer concentration
to company-wide figures, and cut a top-5-supplier field for sparsity.
Field entity scope was fixed as deliberately asymmetric: criminal and
regulatory counts include company, subsidiaries, promoters, directors
and key personnel; the tax count and monetary aggregates include company
and subsidiaries only.
**Justification.** Each change was forced by observed behaviour, not
theory. The single pre-split "regulatory" field produced wild
inter-model disagreement traceable entirely to tax ambiguity; giving tax
its own field removed the ambiguity and added a feature. The auditor
tightening corrected a shared false-positive on vague "qualifications
and observations" wording. The concentration restriction corrected a
segment-level figure incomparable to a company-wide one. The asymmetric
scope reflects that a promoter's criminal/regulatory history is a
governance signal attaching to the issue, whereas a promoter's personal
tax matters are not a liability of the issuer. The dead-field cuts are
the risk-section analogue of the `face_value` drop (D-25).

## D-38 · Model and provider selection; structured-output compatibility

**Locked:** 20 July 2026, after a three-model bake-off (Chapter 7,
§7.5).
**Decision.** The full extraction uses `gpt-5.6-luna` at
`reasoning_effort = low` with a 16,000-token output ceiling. The schema
model config does **not** set `extra="forbid"`.
**Justification.** A five-file, three-model bake-off scored
`gpt-5.6-luna` at 96 percent against the gold set, within two cells of
`gpt-5.6-terra` and `gemini-2.5-flash` (both 98 percent); Luna's two
misses were a single hardest multi-row sum and one regulatory
undercount, not systematic errors. Free-tier options were closed not by
cost but by rate structure: the binding constraint for long-document
extraction is tokens-per-minute, and the surveyed free tiers either
capped per-minute throughput below the size of a single document or
capped per-day requests too low to finish 416 files in the timeline.
Among paid options Luna was reachable through pre-existing API credit,
making the marginal cost of the run negligible, and completed the corpus
synchronously in one sitting. `reasoning_effort = low` was chosen
because the task is extraction rather than multi-step reasoning, the
trial confirmed low sufficed, and reasoning tokens bill as output. The
`extra="forbid"` omission is a compatibility requirement: it makes
Pydantic emit `additionalProperties: false`, which OpenAI strict mode
requires but Gemini's `response_schema` rejects; the OpenAI SDK re-adds
the property during strict conversion, so omitting it satisfies both
providers (verified by inspecting each provider's transformed schema).

## D-39 · Extraction run parameters and reproducibility anchor

**Locked:** 20 July 2026, during the full run (Chapter 7, §7.6).
**Decision.** All 416 files were extracted in a single resumable run;
the raw JSON response for every file is retained under
`data/features/llm_raw/` and is the authoritative record of what was
extracted. Per-row metadata (resolved model, token counts, cost,
timestamp) is stored alongside the extracted fields in
`data/features/features_llm_risk.csv`.
**Justification.** Input volume was priced in advance from an offline
`tiktoken` count (18,857,188 tokens, expected \$22.60); the realised
cost was \$21.13, all rows `ok`, with no refusals, truncations, or
duplicates. Because a hosted model may change under a fixed name, the
retained raw outputs — not the model endpoint — are the reproducibility
anchor; a re-run against a drifted endpoint would be validated against
these. The runner records completed rows and, on restart, skips any file
already `ok`, re-charging nothing; this was exercised when a laptop-sleep
event severed an in-flight connection and the run resumed from the last
completed file without loss or double billing.

## D-40 · Risk-feature transforms and redundancy resolution

**Locked:** 20 July 2026, during risk-feature engineering (Chapter 7,
§7.8).
**Decision.** `10_engineer_risk_features.py` applies, on target-blind
grounds only: `log1p` to the three counts and two monetary fields;
a size-adjusted monetary form `log1p(amount) − assets_log1p`; retention
of the top-10 concentration field with top-5 dropped (r = 0.98);
retention of **both** monetary fields in size-adjusted form; collapse of
going-concern to two flags and auditor to an ordinal severity plus a
modified-opinion flag. The script reads exactly one column from the
numeric feature file (`assets_log1p`) and never reads `first_day_return`.
**Justification.** Transforms are justified by skew, coverage, economic
mechanism, or redundancy — never by correlation with the target, in
parallel with Chapter 6. The monetary pair correlates at 0.95 on the raw
scale, which would argue for dropping one; but this is a scale artefact
driven by a few very large issuers, and the skew transform dissolves it
(`log1p` r = 0.58; size-adjusted r = 0.43). At 0.43 the two carry
distinct information and both are retained — a revision of an earlier
intention to drop one, recorded because it is a substantive
methodological point. Size adjustment de-confounds exposure from firm
size, which is otherwise already captured by the numeric size cluster.

## D-41 · Missingness handling for the risk block

**Locked:** 20 July 2026, at the Chapter 7 → 8 boundary (Chapter 7,
§7.9–7.10).
**Decision.** Every null risk feature is carried as a `*_missing`
indicator and is never zero-filled. Modelling imputes with the
indicators present rather than deleting rows; customer concentration is
treated as a separable feature block tested on its own rather than
included in the core model.
**Justification.** A null denotes genuine non-disclosure (no litigation
table; no stated contingent total; no company-wide concentration
figure), which is categorically different from an explicit zero, and the
schema preserves the distinction (D-37). Only 27 percent of issuers are
complete across all six core risk features simultaneously — because
concentration is disclosed by barely a third — so listwise deletion would
collapse the sample from 416 to roughly 111 and destroy the temporal
splits (D-03). Isolating concentration keeps the main SQ1 test on the
well-populated litigation and exposure features and answers concentration's
marginal contribution as a clean secondary question.

