# 6. Feature Engineering

Feature engineering translates the cleaned master dataset produced in
Chapter 4 into the numeric feature matrix consumed by every downstream
model in Chapters 8 and 9. The pipeline is implemented in a single
script, `src/processing/02_feature_engineering.py`, whose only input
is `data/processed/master_ipo_dataset.csv` and whose only output is
`data/features/features_numeric.csv` (416 rows × 26 columns). No
information from listing-day trading enters at any step, and no
random choices are made — the transformation from master to feature
matrix is deterministic and reproducible.

This chapter is an *implementation record*. The design work that
justifies every transformation was carried out in Chapter 5 and
recorded in Appendix A as decisions D-15 through D-25, D-27 and D-28;
this chapter documents how those decisions were operationalised in
code and what the resulting feature file looks like. The organisation
is: transformations (Section 6.2); normalisation and redundancy
elimination (Section 6.3); financial variables (Section 6.4); broker
sentiment (Section 6.5); market context (Section 6.6); and a note on
regime handling (Section 6.7). Section 6.8 reports the final schema
and missingness pattern of the feature file. Section 6.9 records
what an earlier version of the script did and why it was superseded,
because the correction to that earlier version is a substantive
methodological point.

## 6.1 Overview

The script proceeds in three phases: a load phase that reads the
master and coerces `listing_date` to a `pandas.Timestamp`; an
engineering phase that constructs each feature group in the order
listed above; and a validation phase that spot-checks decision-
specific counts and skewness reductions before the file is written.
No imputation is applied at feature-engineering time. The primary
model (XGBoost) handles missing values natively — the argument for
which is developed in Chapter 8 — and any linear or Ridge baseline
imputes at model time using training-set statistics only. No scaling
or standardisation is applied here either, because standardisation
computed on the full dataset would leak test-period statistics into
training-period inputs.

Four identifier columns — `company`, `listing_date`, `year`, and
`first_day_return` — are carried through unchanged. They are
retained in the feature file to support the temporal train /
validation / test filter (D-03) and stratified reporting (D-13,
D-23), but they are not treated as features by any modelling script.

## 6.2 Log transformation of right-skewed predictors

Eight continuous predictors are transformed by `numpy.log1p` in the
feature set (D-15). The `log1p(x) = log(1 + x)` form is chosen over
the direct `log(x)` so that IPOs with zero values (which occur in
`fresh_issue` and `ofs` when the deal is pure-OFS or pure-fresh, and
which occur in `borrowing` for a small number of debt-free issuers)
map to zero rather than producing `-inf`. This preserves the natural
bounded-below structure of the data while collapsing the right tail.

Table 6.1 reproduces the skewness reduction achieved by the
transformation, computed by the validation phase of the script on
the delivered feature file.

| Variable | Raw skew | `log1p` skew |
|---|---:|---:|
| `revenue` | 20.04 | 0.29 |
| `borrowing` | 13.41 | −0.21 |
| `assets` | 10.69 | 0.57 |
| `fresh_issue` | 7.19 | 0.66 |
| `ofs` | 6.46 | 0.37 |
| `total_issue_size` | 6.39 | 1.04 |
| `sub_total` | 1.99 | −0.07 |
| `issue_price` | 1.90 | −0.33 |

*Table 6.1. Skewness of eight continuous predictors before and after
`log1p` transformation. Values match Table 5.2 and the console output
of `02_feature_engineering.py`.*

For `issue_price` and `sub_total` the raw form is **not** retained
alongside the log form. Providing both would create linear-model
multicollinearity (the two are monotonically related by construction)
for no benefit to XGBoost, which is invariant to monotonic
transformations of individual features. The log-only design is
cleaner across both model families.

Three variables (`gmp_value`, `profit`, `net_worth`) are heavily
skewed but include negative values, precluding a direct `log1p`.
Their information content is captured through derived quantities
(Sections 6.3 and 6.4).

## 6.3 Normalisation and redundancy elimination

Four decisions in this section eliminate feature redundancy that
would otherwise inflate collinearity in a linear model or split
SHAP importance across co-referring features in a tree model.

**`gmp_return` in place of raw `gmp_value` (D-16).** The raw
grey-market premium is a rupee-denominated quantity whose
interpretation depends on the issue price: a ₹50 premium is 50
percent of a ₹100 issue but only 5 percent of a ₹1,000 issue. The
pipeline computes `gmp_return = gmp_value / issue_price`, a
dimensionless quantity directly comparable across IPOs of any price
level. IPOs with `gmp_available = 0` (all 21 cases fall in 2019 or
correspond to 2020 IPOs excluded by the D-06 zero-rule) receive
`NaN`, and the binary flag `gmp_available` is retained so that a
model can condition on the fact of untracked GMP separately from the
magnitude of a tracked GMP. Spot checks confirm correctness of sign
and magnitude: Sigachi Industries yields `gmp_return = +1.38`
(highest first-day gainer at +270 percent); One 97 Communications
(Paytm) yields `gmp_return = −0.014` (worst canonical case at
−27 percent); IRCTC (2019) yields `NaN` (untracked GMP).

**Drop `lot_size` in favour of `issue_price_log1p` (D-17).** Section
5.3.1 documented a Spearman correlation of −0.996 between `lot_size`
and `issue_price` — a mechanical relationship arising from SEBI's
rule that the minimum retail application amount is approximately
₹15,000. Only the log-transformed `issue_price` is retained;
`lot_size` is dropped entirely. This avoids the near-perfect
multicollinearity that would destabilise a linear-model baseline.

**Deal-size composition (D-18).** The three raw deal-size variables
(`total_issue_size`, `fresh_issue`, `ofs`) satisfy the identity
`total_issue_size = fresh_issue + ofs` and correlate pairwise at
0.80–0.82 by construction. The pipeline provides all three in
log-transformed form (`total_issue_size_log1p`, `fresh_issue_log1p`,
`ofs_log1p`) and adds one composition ratio
`ofs_ratio = ofs / (fresh_issue + ofs)`. Structural missingness in
either component (pure-OFS IPOs have `fresh_issue` missing;
pure-fresh IPOs have `ofs` missing) is treated as an implicit zero,
so that `ofs_ratio` is well-defined at zero for pure-fresh and one
for pure-OFS. In the delivered file the distribution of `ofs_ratio`
is 80 pure-fresh, 255 mixed, and 81 pure-OFS. Keeping the raw
log-scale components alongside the composite ratio is a modelling-
agnostic choice: XGBoost may find interactions between the size
components that the composite ratio does not expose, while linear
baselines can drop the redundant components at model time.

**Drop `face_value` (D-25).** `face_value` was found in Section
5.3.2 to correlate with the target at Spearman ρ = −0.02,
essentially noise at n = 416. It also carries a degenerate
category structure: a single IPO (Nazara Technologies, 2021) has
`face_value = 4`, which cannot be pooled cleanly with any
neighbouring category. The variable is dropped in its entirety.

## 6.4 Financial variables

The five raw financial variables (`revenue`, `profit`, `assets`,
`net_worth`, `borrowing`) form a company-size cluster in Section
5.3.1 with pairwise Spearman correlations between 0.5 and 0.86,
reflecting the standard confound that larger companies are large on
every dimension. The pipeline provides two kinds of transformation
side by side.

**Log-transformed scale.** `revenue_log1p`, `assets_log1p`, and
`borrowing_log1p` capture company scale with the skewness reduction
documented in Table 6.1. Raw `revenue`, `assets`, and `borrowing`
are non-negative for every IPO in the dataset, so `log1p` applies
without special-case handling.

**Dimensionless ratios.** Three ratios normalise for scale while
retaining economically meaningful interpretation (D-19):

- `profit_margin = profit / revenue` (profitability);
- `return_on_assets = profit / assets` (asset efficiency);
- `debt_to_equity = borrowing / net_worth` (leverage).

Rows with `revenue = 0` or `assets = 0` produce `NaN` for the
corresponding ratio; the pipeline uses `df.replace(0, np.nan)` on
denominators to prevent silent `inf` results. Sign-mixed inputs
(`profit`, `net_worth`) enter naturally via these ratios — the
resulting values can be negative when the underlying quantities are
negative, and the interpretation is preserved.

**Non-positive net-worth handling (D-20).** For IPOs with
`net_worth ≤ 0` (five observations in the study period: Stove Kraft,
Chemplast Sanmar, DCX Systems, SAMHI Hotels, and Indiqube Spaces),
`debt_to_equity` is set to NaN and a companion flag
`negative_networth_flag` is set to 1. All other IPOs receive the
computed ratio and a flag of 0. A negative-net-worth denominator
makes `debt_to_equity` uninterpretable as a leverage measure — a
highly indebted solvent company and an insolvent company can yield
similarly-signed ratios of similar magnitude — so the flag lets a
model condition on the qualitative fact of insolvency separately
from any quantitative leverage measure. The comparison is written
against `≤ 0` rather than `< 0` deliberately: DCX Systems'
`net_worth` is 0.0 exactly, and an earlier version of the pipeline
that used `< 0` produced an `inf` value in `debt_to_equity` on that
row.

Raw `profit` and `net_worth` do not enter the feature file directly:
they are sign-mixed and heavily skewed, and the ratios above capture
their information content in a scale-invariant form.

## 6.5 Broker sentiment

Two broker-recommendation counts (`brokers_subscribe` and
`brokers_avoid`) are collected from the Chittorgarh detail pages.
Section 5.3.2 identified a specific structure in their relationship
with the target: the LOWESS smoother for `brokers_avoid` is
essentially a step function — the difference between zero
avoid-recommendations and any avoid-recommendation carries most of
the predictive content, while the marginal information from a
second or third avoid is small. The raw `brokers_avoid` count is
also 74 percent zeros (307/416 IPOs), reinforcing the binary
character of the signal.

The pipeline retains both raw counts (`brokers_subscribe`,
`brokers_avoid`) and adds one binary derivative:
`any_avoid_flag = 1 if brokers_avoid > 0 else 0` (D-21). In the
delivered file `any_avoid_flag` is one for 106 IPOs (25.5 percent),
meaning about a quarter of the study population received at least
one avoid recommendation.

Both raw counts are retained alongside the flag on the same
modelling-agnostic reasoning applied in Section 6.3 for deal-size
components. XGBoost may make use of the graded distinction between,
for example, one avoid and three avoids; linear baselines can drop
the redundant raw count at model time if the flag captures all of
the signal. Feature engineering does not pre-decide which encoding
each downstream model will use.

## 6.6 Market context

The four market-context variables (`nifty_close`, `vix_close`,
`nifty_7d_return`, `nifty_30d_return`) are carried through
unchanged. Section 5.2.2 established that all four are already
close to symmetric on their raw scale (VIX has skew 2.4, which could
in principle be reduced by `log1p`, but doing so would obscure its
natural percent-volatility interpretation for Chapter 9 SHAP
readings). Section 5.4.2 established that the two trailing-return
variables are year-conditionally unstable and are to be flagged as
such in Chapter 9 interpretation (D-24). No new transformations are
applied here; the values are the leakage-safe prior-day merges
produced by the D-08 `merge_asof` in the cleaning script.

## 6.7 A note on regime handling

The feature file does **not** include a dedicated regime dummy
variable (D-28, superseding an earlier D-22). Section 5.4.4
establishes that the IPO first-day return distribution shifts
markedly between the 2024 and 2025 listing years, with a Mann-
Whitney U p-value of 6.20 × 10⁻⁷ at the 2025-01-01 boundary. The
market backdrop for this shift is externally observable in the
Nifty 50 and India VIX series (Section 5.4.4 and Chapter 3, §3.5).
Those market conditions enter the feature set directly through
`nifty_close`, `vix_close`, `nifty_7d_return`, and `nifty_30d_return`.
A binary regime dummy anchored at any specific date would be
redundant with these features while introducing an additional
design-time choice — the anchor date — that would be difficult to
select without reference to test-period data. The feature file
therefore captures the regime signal through the continuous market
variables and leaves the model to condition on them as it will.

## 6.8 The output feature file

The feature file `data/features/features_numeric.csv` contains 416
rows and 26 columns organised into seven groups. Table 6.2 gives
the full schema.

| Group | Columns |
|---|---|
| Identifiers | `company`, `listing_date`, `year`, `first_day_return` |
| Structural | `issue_price_log1p` |
| Deal size | `total_issue_size_log1p`, `fresh_issue_log1p`, `ofs_log1p`, `ofs_ratio` |
| Demand | `sub_total_log1p`, `gmp_return`, `gmp_available` |
| Financial | `revenue_log1p`, `assets_log1p`, `borrowing_log1p`, `profit_margin`, `return_on_assets`, `debt_to_equity`, `negative_networth_flag` |
| Broker | `brokers_subscribe`, `brokers_avoid`, `any_avoid_flag` |
| Market | `nifty_close`, `vix_close`, `nifty_7d_return`, `nifty_30d_return` |

*Table 6.2. Column layout of `features_numeric.csv`. The four
identifier columns are retained for stratified reporting and the
temporal split; they are not treated as features by any modelling
script.*

Missingness in the feature file is concentrated in a small number
of columns and is well-understood.

- `fresh_issue_log1p` is missing for 81 rows (19.5 percent) — pure-
  OFS IPOs where no fresh issue exists to log.
- `ofs_log1p` is missing for 80 rows (19.2 percent) — the mirror
  case, pure-fresh IPOs.
- `debt_to_equity` is missing for 63 rows (15.1 percent): the five
  non-positive-net-worth cases plus rows where `borrowing` or
  `net_worth` is missing in the master.
- `borrowing_log1p` is missing for 49 rows (11.8 percent), a
  data-availability gap concentrated in 2019.
- `gmp_return` is missing for 21 rows (5.0 percent), matching
  `gmp_available = 0` exactly.
- `revenue_log1p`, `assets_log1p`, `profit_margin`, and
  `return_on_assets` each have 4 missing rows (1.0 percent),
  corresponding to a small number of 2019 IPOs missing their full
  financial line items.
- `brokers_subscribe` and `brokers_avoid` each have 3 missing rows
  (0.7 percent).

All other columns are fully populated. No `inf` values appear in
any feature column; the validation phase of the script explicitly
asserts this.

## 6.9 A superseded earlier version of the script

An earlier version of the feature-engineering pipeline was written
after an initial pass of the EDA and subsequently retired. It is
worth recording what changed and why, because the correction touches
a methodological point that has broader implications for the
dissertation.

The retired version included two features that have been removed
from the current design:

- **A regime dummy `regime_post_2024`.** The dummy was constructed
  as `listing_date >= 2025-01-01` and was justified by the Mann-
  Whitney U test in Section 5.4.4 which located the strongest
  regime break at exactly that date. The problem with this
  justification is that the Mann-Whitney test used the test-period
  observations (2025-26) as part of computing the p-value at each
  candidate boundary. Choosing 2025-01-01 as the boundary was
  therefore an implicit use of test-period information at feature-
  design time. In the current design (D-28) the dummy is removed
  entirely, and the regime signal is carried by the raw market-
  context features (`nifty_close`, `vix_close`, `nifty_7d_return`,
  `nifty_30d_return`) which vary with the same underlying market
  conditions that drove the shift.

- **Removal of `assets_log1p` and `borrowing_log1p` from the
  feature set.** The retired version dropped these two log-scale
  variables on the grounds that their per-split target correlations
  in Table 5.4 showed instability (assets flipped sign train → test;
  borrowing collapsed toward zero in test). The problem again was
  that this decision consulted test-period statistics: dropping a
  feature because it "does not work in test" is feature selection
  informed by the held-out set. In the current design the two
  variables are retained (D-27); their instability is a modelling-
  time diagnostic that is reported in Chapter 9 under the year-
  conditional stability flag (D-24), not a feature-engineering-time
  drop.

Two features were also retired from the earlier design on
non-methodological grounds:

- A composite `broker_sentiment = brokers_subscribe − brokers_avoid`.
  On reflection, subtracting an avoid count from a subscribe count
  conflates two independent signals: an IPO with twelve subscribes
  and two avoids scores the same net sentiment as an IPO with ten
  subscribes and zero avoids, but these are meaningfully different
  configurations. The current design retains the two raw counts and
  the binary any-avoid flag separately, leaving downstream models to
  combine them as they will.

- Explicit raw versions of `issue_price` and `sub_total` alongside
  the log-transformed forms. These were dropped because retaining
  both raw and log versions of the same variable is a linear-model
  multicollinearity problem for no benefit to XGBoost.

The current script is deterministic and, given the same master file,
produces the same 26-column output file every time. Its output has
been sanity-checked against the master (row count, coverage, ratio
sums, absence of `inf`) inside the script's `validate()` phase before
the file is written.

---

Chapter 7 turns to schema-guided extraction of risk factors from
the 416 verified prospectus PDFs, producing a second feature file
`data/features/features_llm_risk.csv` whose combination with the
numeric feature file constructed here provides the augmented
feature set evaluated in Chapters 8 and 9.