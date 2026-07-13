# 5. Exploratory Data Analysis

Exploratory analysis was carried out on the cleaned master dataset
produced in Chapter 4 (416 IPOs × 29 columns) *before* any feature
engineering. The purpose was threefold: (a) to characterise the
distribution and temporal behaviour of the target variable;
(b) to describe the distribution, coverage and outlier structure of
every candidate predictor; and (c) to justify feature-engineering
decisions with empirical evidence rather than prior assumption. This
chapter reports the findings that shape the modelling design in
Chapters 6 through 9.

The analysis is implemented in four numbered scripts under `src/eda/`,
each of which writes figures to `reports/figures/eda/` and tables to
`reports/tables/eda/`. All figures and tables referenced in this
chapter are reproducible from those scripts, and the numerical claims
below are drawn directly from the tables.

The chapter is structured as follows. Section 5.1 examines the target
variable in isolation. Section 5.2 examines every candidate predictor
univariately. Section 5.3 examines pairwise relationships between
predictors and between each predictor and the target. Section 5.4
examines how these relationships behave over the eight-year study
period. Section 5.5 consolidates the empirical commitments carried
into Chapter 6.

## 5.1 Target variable analysis

The primary target is `first_day_return`, defined in Chapter 4 as
`(listing_close − issue_price) / issue_price`. This section
characterises its distribution and its temporal structure.

### 5.1.1 Distribution and shape

Across the 416 mainboard IPOs, `first_day_return` has mean 21.3 percent,
median 11.4 percent, and standard deviation 36.4 percent. The
distribution is strongly right-skewed (skewness = 2.36, excess
kurtosis = 8.64), with a minimum of −35.9 percent (Om Freight
Forwarders, October 2025) and a maximum of +270.4 percent (Sigachi
Industries, November 2021). Roughly 71 percent of IPOs closed above
their issue price.

Both a Shapiro-Wilk test (W = 0.802, p ≈ 3 × 10⁻²²) and a
Kolmogorov-Smirnov test against a standard normal (D = 0.145,
p ≈ 5 × 10⁻⁸) reject normality decisively. Figure 5.1 shows the
distribution as a histogram with kernel density estimate, a boxplot,
a Q-Q plot against the normal, and a signed-log-transformed version.
The heavy right tail and thin left tail are visible in every panel.
A signed-log transformation sign(r) · log(1+|r|) substantially
reduces the raw skewness, but does not fully symmetrise — reflecting
the natural asymmetry that losses are bounded below by −100 percent
while gains have no upper limit.

![Distribution of `first_day_return` across the 416 IPOs: histogram
with kernel density estimate (a), boxplot (b), Q-Q plot against a
normal distribution (c), and signed-log transformation (d). Vertical
dashed and dotted lines mark the median and mean
respectively.](../reports/figures/eda/01_target_distribution.png){#fig:target-distribution width=100%}

The gap between mean (21.3 percent) and median (11.4 percent) is a
substantive finding rather than a numerical curiosity: it reflects
the disproportionate influence of a small number of extreme winners
in the right tail. Consistent with this asymmetry, the interquartile
range [−1.4 percent, +31.9 percent] is markedly wider than a
Gaussian approximation would predict. **Because the target is
heavily skewed and heavy-tailed, this dissertation reports the median
as its primary statistic of central tendency, with the mean shown
alongside where appropriate, and reports the mean absolute error
alongside the more outlier-sensitive root-mean-squared error when
evaluating model performance in Chapter 9.** These reporting choices
are locked in Appendix A as D-11 and D-12.

### 5.1.2 Temporal structure and the 2024–2025 regime shift

The single most important finding in this chapter concerns the
temporal behaviour of the target. Figure 5.2 summarises the target's
evolution across the eight-year study window: panel (a) shows IPO
count per year, panel (b) shows the year-by-year median first-day
return with 95 percent bootstrap confidence intervals, panel (c)
shows the mean, and panel (d) shows the fraction of IPOs with
positive first-day return.

![Temporal behaviour of `first_day_return` by listing year: IPO count
(a), median with 95 percent bootstrap confidence interval (b), mean
with 95 percent bootstrap confidence interval (c), and share of IPOs
with positive first-day return
(d).](../reports/figures/eda/01_target_temporal.png){#fig:target-temporal width=100%}

Two features of Figure 5.2 are noteworthy. First, from 2019 through
2024, the median first-day return oscillates in a comparatively
narrow range of roughly 5 percent to 21 percent, with 63 to 83
percent of IPOs closing above their issue price. Second, in 2025 and
2026, the median drops sharply — to 5.2 percent in 2025 and to
−0.7 percent in 2026 — and the positive-return share falls to 67
percent and 46 percent respectively. Panel (b) makes explicit that
the 95 percent confidence interval on the 2024 median [0.13, 0.30]
does not overlap with the 95 percent confidence interval on the 2025
median [0.01, 0.08]. **The 2026 median is the first year in the
study period in which more than half of listed IPOs close below
their issue price.**

The magnitude and statistical significance of this shift are formally
established in Section 5.4.4 below. For the purposes of this section
it suffices to note that the change is not gradual: it occurs
sharply between 2024 and 2025. The consequences of this regime shift
for the locked temporal train / validation / test split (train
≤ 2023, validation = 2024, test = 2025-26; established in Chapter 4)
are substantial and are addressed in Section 5.4.

### 5.1.3 Extreme cases

To understand the character of first-day return outliers, the ten
IPOs with the largest and the ten with the smallest first-day
returns were tabulated with their pre-listing signals. The two lists
show a sharp asymmetry in what precedes an extreme outcome.

Every one of the ten largest first-day gainers (led by Sigachi
Industries at +270 percent, followed by Vibhor Steel Tubes at +193
percent and Paras Defence at +185 percent) had a strongly positive
grey-market premium (GMP) or was subscribed at least 49 times over.
The one exception in the top-10 is IRCTC (2019), for which GMP was
not tracked (`gmp_available = 0` following D-06); its 109×
subscription alone was sufficient to signal the +128 percent
listing.

Among the ten worst first-day losers, all had either negative
grey-market premium, zero grey-market premium, or subscription below
five times. Paytm (One 97 Communications, November 2021) is a
canonical example: pre-listing GMP was −₹30 and subscription was
1.48×, and the stock closed −27 percent on debut. The single
counter-example is Deepak Builders and Engineers (October 2024),
which had GMP of ₹32 and subscription of 29× yet lost 20 percent —
this is the type of case in which post-listing risk realisation
outweighs pre-listing demand, and it is precisely the kind of
observation that motivates the LLM risk-feature agenda of the
dissertation.

### 5.1.4 Open-based versus close-based first-day return

An open-based alternative target, `first_day_open_return =
(listing_open − issue_price) / issue_price`, was computed for
diagnostic purposes and never used as a predictor (leakage column,
per D-07). Its correlation with the close-based target is 0.946
(n = 416), and the mean of the intraday move (close minus open) is
+1.0 percent with a standard deviation of 11.8 percent. The two
targets carry essentially the same information for prediction
purposes; the close-based definition is retained as the primary
target because it is the convention used by Ritter (1991) and by
Ghosh, Zheng and Lopez-Lira (2024).

One diagnostic anomaly was surfaced in this comparison: a single IPO
(Udayshivakumar Infra Ltd., April 2023) has `listing_open = 0.0`,
which is impossible for a traded stock. Its true opening price must
lie in [`listing_low`, `listing_high`] = [₹29.15, ₹31.5] but the
exact value cannot be recovered from the Chittorgarh source. Because
`listing_open` is a leakage column and does not enter any predictor
set, the anomaly has no effect on modelling and no correction is
applied. It is noted here and in Appendix A (D-14) for
completeness.

## 5.2 Univariate feature analysis

Every candidate predictor was examined individually for coverage,
distribution shape, missingness structure over time, and the
appropriateness of a logarithmic transformation. The candidate set
comprises 18 continuous predictors (issue price, deal-size
components, subscription, GMP, five financial variables, two broker
counts, four market-context variables, and lot size) and two
categorical predictors (face value, GMP availability flag).

### 5.2.1 Coverage and summary statistics

Table 5.1 (`reports/tables/eda/02_coverage_and_stats.csv`) reports
per-variable coverage. Most predictors have coverage above 95
percent. Three fall below 90 percent — `fresh_issue` (80.5 percent),
`ofs` (80.8 percent), and `borrowing` (88.2 percent). The
`fresh_issue` and `ofs` gaps are *structural rather than
data-quality* gaps: an IPO with no offer-for-sale component has
`ofs` reported as missing rather than as zero (and *vice versa* for
pure OFS issues). This was established during data cleaning
(Chapter 4) and Chapter 6 will correspondingly treat the missing
component as an implicit zero when computing composition ratios. The
`borrowing` gap is a genuine data-coverage limitation, concentrated
in 2019 (see Section 5.2.3 below).

### 5.2.2 Distributional shape and log-transform candidates

Figure 5.3 shows the raw distribution of every continuous predictor
as a small-multiples grid of histograms. Two visual patterns
dominate. First, several financial and structural variables
(`revenue`, `assets`, `borrowing`, `total_issue_size`, `fresh_issue`,
`ofs`) present as a near-spike at zero with a small number of
extreme outliers, reflected in skewness values above 6. Second, two
variables (`profit` and `net_worth`) display distributions with a
mix of positive and negative values driven by a small number of
loss-making or negative-equity issuers, notably Chemplast Sanmar
(net_worth −₹1,866 crore) and SAMHI Hotels (net_worth −₹871 crore).
Distributions of market-context and broker-sentiment variables are
much closer to symmetric.

![Distributions of the 18 continuous predictors, as a
small-multiples grid. Dashed vertical lines mark medians. Log-scaled
y-axes are used for the most extremely skewed
variables.](../reports/figures/eda/02_continuous_distributions.png){#fig:continuous-distributions width=100%}

Table 5.2 (`reports/tables/eda/02_skewness_table.csv`) summarises
skewness before and after a `log1p` transformation. Where a variable
is strictly non-negative, `log1p` typically reduces skewness by an
order of magnitude — `revenue` moves from 20.04 to 0.29,
`borrowing` from 13.41 to −0.21, `assets` from 10.69 to 0.57.
Figure 5.4 visualises the before-and-after comparison for the
non-negative variables with raw |skew| > 1.

![Skewness before and after `log1p` transformation for non-negative
continuous predictors with raw |skewness| > 1. Coral bars: raw
skewness. Teal bars: log-transformed skewness. Dashed lines mark
|skewness| = 1 as a conventional
threshold.](../reports/figures/eda/02_skewness_before_after_log.png){#fig:skewness-before-after width=90%}

Three variables (`gmp_value`, `profit`, `net_worth`) are heavily
skewed but include negative values, precluding a direct `log1p`. For
these, Chapter 6 will use derived dimensionless ratios
(`gmp_return`, `profit_margin`, `debt_to_equity`) which normalise
scale without requiring log transformation of a mixed-sign variable.

### 5.2.3 Missingness structure over time

Missingness is not random. Figure 5.5 shows a heatmap of the
fraction missing for each variable in each year. The 2019 column is
qualitatively different from every other year: `gmp_value` is
missing for 100 percent of 2019 IPOs (per the D-06 cleaning rule
established in Chapter 4), `borrowing` is missing for 63 percent,
and three additional 2019 IPOs are missing their financial line
items entirely. From 2020 onward the picture is largely clean, with
the sole persistent gaps being `fresh_issue` and `ofs` (which
reflect structural pure-fresh-issue and pure-OFS listings in every
year, as noted above).

![Missingness fraction by variable and year for the ten predictors
that exhibit any missingness. Darker cells indicate a larger
fraction of missing values. 2019 is the data-poor
column.](../reports/figures/eda/02_missingness_by_year.png){#fig:missingness-heatmap width=95%}

The structural nature of the missingness informs the Chapter 6
decision to use native NaN plus a `gmp_available` flag rather than
imputation. Tree-based models (XGBoost) treat NaN as a first-class
value and learn the appropriate split direction; the flag captures
the distinction between "GMP was tracked and equal to zero" and
"GMP was not tracked at all", which the raw column alone cannot
represent.

### 5.2.4 Categorical predictors

Two predictors are meaningfully categorical: `face_value`, which
takes five distinct values {₹1, ₹2, ₹4, ₹5, ₹10} with strongly
uneven frequencies (65, 80, 1, 48, 222 respectively), and
`gmp_available`, which is binary (21 zeros, 395 ones). The single
IPO at `face_value = 4` is Nazara Technologies (2021); the
single-observation category will be pooled with `face_value = 5` in
Chapter 6, or the feature dropped entirely, subject to the
correlation evidence in Section 5.3.

`lot_size` takes 146 distinct integer values ranging from 1 to 780
and is analysed as a continuous variable throughout this chapter.

## 5.3 Bivariate analysis

Bivariate analysis examined both feature-feature relationships (to
detect redundancy) and feature-target relationships (to identify
predictive signal). Spearman rank correlation was used throughout as
the primary metric because the target and many predictors are
heavily right-skewed and Spearman is invariant to monotonic
transformations and robust to outliers. Pearson correlations were
also computed and retained in the raw output tables for comparison.

### 5.3.1 Feature-feature correlations and redundancy

Figure 5.6 shows the full pairwise Spearman correlation matrix as a
lower-triangular heatmap, with variables grouped by category
(structural, demand, GMP, financial, broker, market). Three sources
of redundancy emerge clearly.

![Pairwise Spearman correlation matrix of all 20 predictors and the
target `first_day_return`, shown as a lower-triangular heatmap.
Variables are grouped by category with thin lines marking group
boundaries.](../reports/figures/eda/03_correlation_matrix.png){#fig:corr-matrix width=100%}

First, `lot_size` and `issue_price` correlate at ρ = −0.996. This is
a mechanical rather than economic relationship: the Securities and
Exchange Board of India (SEBI) requires the minimum retail
application amount to be approximately ₹15,000, so `issue_price
× lot_size ≈ 15,000` for every mainboard IPO. The two variables
encode essentially the same information with a sign flip and are
treated as redundant in Chapter 6.

Second, the three deal-size components `total_issue_size`,
`fresh_issue`, and `ofs` inter-correlate at 0.80 to 0.82 by
construction (total = fresh + ofs). Chapter 6 accordingly uses one
log-scaled size and one composition ratio (`ofs_ratio = ofs /
total`) rather than three raw levels.

Third, the five financial variables (`revenue`, `assets`,
`net_worth`, `borrowing`, `profit`) form a "company size" cluster
with pairwise correlations of 0.5 to 0.86. This is the standard
scale confound in firm-level financial data: larger companies are
large on every dimension. Chapter 6 addresses this by converting the
raw levels into dimensionless ratios (`profit_margin`,
`return_on_assets`, `debt_to_equity`) which are much less
inter-correlated than the levels they are derived from.

### 5.3.2 Feature-target correlations

Figure 5.7 ranks every predictor by its absolute Spearman
correlation with `first_day_return`. The distribution of
correlations is highly uneven.

![Feature-target Spearman correlation ranking, sorted by value.
Dashed vertical lines mark reference thresholds at ±0.1 and ±0.3.
Bars are coloured green for positive correlation and coral for
negative.](../reports/figures/eda/03_target_correlation_ranking.png){#fig:target-corr-ranking width=90%}

Two predictors dominate: `gmp_value` (ρ = 0.712, p ≈ 0) and
`sub_total` (ρ = 0.708, p ≈ 0). The next-strongest predictor,
`brokers_avoid`, has magnitude 0.270 — a substantial drop. A small
middle tier (`brokers_subscribe`, `nifty_30d_return`,
`nifty_7d_return`, `borrowing`, `assets`) sits between magnitudes of
0.10 and 0.27. The remaining twelve predictors have |ρ| below 0.10,
essentially indistinguishable from noise at this sample size.

The Pearson-versus-Spearman gap for the two dominant predictors is
informative: `gmp_value` has Pearson 0.529 versus Spearman 0.712,
and `sub_total` has Pearson 0.635 versus Spearman 0.708. The
consistently larger Spearman value signals a monotonic but
non-linear relationship with the target — visualised directly in
Figure 5.8.

![Scatter plots of the six top-correlated predictors against
`first_day_return`, with LOWESS smoothers in red. Titles report the
Spearman correlation and sample size for each
panel.](../reports/figures/eda/03_top_predictor_scatters.png){#fig:top-scatters width=100%}

The LOWESS smoothers show that both dominant predictors exhibit a
concave, log-shaped relationship with the target: rapid increase at
low values, saturation at high values. This provides an empirical
basis for the Chapter 6 decision to include log-transformed variants
of these features in linear-model baselines, though not for the
tree-based primary model (which is invariant to monotonic feature
transformation). The LOWESS for `brokers_avoid` is essentially a
step function: the difference between zero and one
avoid-recommendation is large, but additional avoid-recommendations
add little. This suggests that a binary "any avoid" flag captures
a substantial share of the predictive content of the raw count.

### 5.3.3 GMP-stratified feature-target relationships

Because grey-market premium is the strongest single predictor, and
because the LLM risk-feature agenda of this dissertation aims to add
predictive value beyond a strong numeric baseline, the 416 IPOs were
split into two subsets — those with GMP available (n = 395) and
those without (n = 21) — and per-predictor Spearman correlations
were re-computed within each.

![Spearman correlation with `first_day_return` computed separately
in the GMP-available subset (n = 395, blue) and the GMP-absent
subset (n = 21,
coral).](../reports/figures/eda/03_gmp_stratified_correlations.png){#fig:gmp-stratified width=95%}

In the GMP-absent subset the correlation of `sub_total` with the
target rises to ρ = 0.836 (from 0.699 in the GMP-available subset),
`brokers_subscribe` rises to 0.490 (from 0.247), and the negative
correlation of `borrowing` deepens to −0.383 (from −0.142).
Interpretation: when the dominant GMP signal is missing, other
demand-side and risk-side signals compensate to carry a greater
share of the pre-listing information. The small size of the
GMP-absent subset (n = 21, almost entirely from 2019) implies wide
confidence intervals, so these values should be read as directional
evidence rather than precise estimates. The finding nevertheless
motivates a Chapter 9 reporting decision: model performance in the
augmented (LLM risk features included) versus baseline settings will
be reported separately for the GMP-available and GMP-absent slices,
so that any incremental value in the GMP-absent slice — where risk
signals are most likely to matter — is clearly attributable.

## 5.4 Temporal and regime-conditional analysis

Given the regime shift identified in Section 5.1.2, further analysis
was carried out to determine (a) whether predictor distributions
themselves drift across the study period, (b) whether the
predictor-target relationships identified in Section 5.3 are stable
across time, (c) how the locked train / validation / test split
compares in composition, and (d) at which year boundary the regime
shift is most parsimoniously located.

### 5.4.1 Predictor distributional drift

Figure 5.9 shows year-by-year box plots for ten monitored
predictors, covering the demand, GMP, sentiment, structural,
financial, and market-context groups.

![Distributions of ten monitored predictors by year, shown as box
plots with outliers hidden for readability. Log-scaled y-axis is
used for the most heavily skewed
variables.](../reports/figures/eda/04_feature_drift.png){#fig:feature-drift width=100%}

Several patterns emerge. The median value of `gmp_value` compresses
sharply in the test period, from ₹47 in 2024 to ₹20 in 2025 to
₹0 in 2026. The median `sub_total` collapses from 32× in 2024 to
19× in 2025 to 2.1× in 2026. Median `issue_price` declines from
₹536 in 2021 to ₹174 in 2026. `nifty_close` rises secularly from
approximately 11,500 in 2019 to approximately 25,000 in 2025-26, as
expected from broad-market appreciation. `vix_close` was elevated
during 2020-2022 (COVID and post-COVID period) and has drifted
lower since.

The consequence is that the covariate distribution in the test set
(2025-26) is materially different from the covariate distribution
in the training set (≤ 2023) on several key variables. This
constitutes covariate shift and must be accounted for in the
interpretation of Chapter 9 test-set metrics.

### 5.4.2 Year-conditional stability of top predictors

For each of the six most-correlated predictors, the Spearman
correlation with the target was recomputed within each individual
year, with 95 percent bootstrap confidence intervals. Figure 5.10
shows the resulting trajectories.

![Year-conditional Spearman correlation of the six top predictors
with `first_day_return`. Vertical bars are 95 percent bootstrap
confidence intervals. Horizontal dotted red line marks the
full-sample correlation. The shaded band highlights the 2025-26
test
regime.](../reports/figures/eda/04_year_conditional_correlations.png){#fig:year-cond-corr width=100%}

Only one predictor exhibits temporal stability: `gmp_value`, whose
year-conditional correlation with the target remains within a
[0.60, 0.73] band in every year of the study and whose 95 percent
bootstrap confidence intervals never cross zero. This is the sole
numeric predictor that can be relied upon to provide comparable
predictive signal in training and in test.

The remaining five top predictors are each regime-dependent to some
degree. `sub_total` weakens from ρ ≈ 0.75 in most training-period
years to ρ = 0.46 in 2026 (with a wide CI reflecting small sample
size). `brokers_avoid` oscillates between −0.52 (2020) and +0.14
(2019) and is essentially null in 2023 and 2025. `nifty_30d_return`
collapses from ρ = 0.21 in the full sample to ρ = −0.045 in 2025.

This finding shapes the modelling narrative of Chapter 9: SHAP
importance rankings will reflect what the model uses within its
training data, but only the GMP component of that importance can be
trusted to transfer cleanly to the test regime. Non-GMP feature
contributions on the test set should be interpreted with reference
to their year-conditional stability.

### 5.4.3 Train / validation / test comparison

The three temporal splits induced by the locked partition (train
≤ 2023, validation = 2024, test = 2025-26) were compared directly.
Panel (a) of Figure 5.11 shows the empirical cumulative distribution
function of `first_day_return` in each split. Train and validation
distributions are nearly identical. The test distribution is
shifted markedly to the left: at the origin, roughly 37 percent of
test IPOs have already occurred (i.e. 37 percent lost money on day
one), compared with approximately 25 percent in both train and
validation.

![Comparison of the three temporal splits: (a) target ECDFs and
(b) per-predictor Spearman correlations with
`first_day_return`.](../reports/figures/eda/04_train_val_test_comparison.png){#fig:tvt-comparison width=100%}

Panel (b) shows per-predictor Spearman correlations within each
split for a selection of the top-correlated variables. `gmp_value`
remains at ρ ≈ 0.69-0.73 across all three splits. `sub_total`
decays modestly from 0.76 (train) to 0.65 (test).
`nifty_30d_return` drops from 0.21 (train) to 0.06 (test). Most
strikingly, `assets` changes sign, moving from ρ = −0.236 in
training to ρ = +0.113 in test — a feature whose training-period
signal actively misleads a model on the test set. This has
implications for Chapter 8 modelling that are discussed in
Section 5.5 and revisited under the interpretation caveats in
Chapter 9 (D-24).

Summary statistics of the target in each split confirm the regime
picture: the training-set target has mean 26.2 percent and median
15.5 percent; the test-set target has mean 8.0 percent and median
4.2 percent. Target standard deviation in test (20.1 percent) is
approximately half that of train (40.6 percent).

The methodological consequence is that absolute error metrics (mean
absolute error, root mean squared error) will be smaller on the
test set than on the training set for any model, simply because the
target has less variance to explain. This is not evidence of
superior model performance in the test period. Chapter 9 therefore
reports rank metrics (Spearman correlation between predicted and
actual returns) alongside absolute-error metrics, so that the
model's discrimination of relative outcomes can be evaluated
independently of any compression in the target distribution.

### 5.4.4 The regime break formally located

The visual and numerical evidence of Sections 5.1.2 and 5.4.1
identifies the regime break as occurring between the 2024 and 2025
listing years. This is verified formally with a Mann-Whitney U test
applied to two candidate split points: the pre-2024 versus 2024+
split (consistent with the locked train / validation split) and the
pre-2025 versus 2025+ split (consistent with the visually apparent
break).

For the pre-2024 versus 2024+ split (n = 194 versus 222), the
Mann-Whitney U statistic is 24,222 with p = 2.81 × 10⁻². For the
pre-2025 versus 2025+ split (n = 284 versus 132), the Mann-Whitney
U statistic is 24,434 with p = 6.20 × 10⁻⁷. Mood's median test
corroborates: at the 2024/2025 boundary, the median test statistic
is 22.47 with p = 2.13 × 10⁻⁶.

The corrected split point yields a p-value roughly 45,000 times
smaller than the initial split point. **The regime break is
definitively located between the 2024 and 2025 listing years and is
established at a level of statistical significance far exceeding
conventional thresholds.**

The market backdrop for this break is externally observable in the
Nifty 50 and India VIX series (Chapter 3, §3.5). The Nifty peaked
at 26,216 on 27 September 2024 and then corrected roughly 15 percent
by the February–March 2025 trough; India VIX rose from a 13–14 range
in late 2024 to a 16–18 range through the first half of 2025. The
IPO regime shift is therefore not a phantom of the return data but
reflects an actual change in market conditions during the study
period.

## 5.5 Empirical commitments carried into feature engineering

The findings of Sections 5.1 through 5.4 justify a set of specific,
evidence-grounded decisions that shape feature engineering
(Chapter 6) and modelling (Chapters 8 and 9). These decisions are
recorded formally in Appendix A; the summary here is intended to make
the connection between EDA finding and design choice transparent to
the reader.

**Transformations.** Non-negative variables with meaningful raw skew
and clear log-transform benefit are transformed with `log1p` in the
feature set (D-15). This includes `revenue`, `assets`, `borrowing`,
`total_issue_size`, `fresh_issue`, `ofs`, `issue_price`, and
`sub_total`. Skewness reductions range from an order of magnitude
(revenue, 20.04 → 0.29) to modest (sub_total, 1.99 → −0.07); Table
5.2 records the full before-and-after picture.

**Normalisation.** `gmp_value` is normalised by `issue_price` to
form `gmp_return`, a dimensionless quantity comparable across IPOs
of different price levels (D-16). This addresses both the
mixed-sign problem (which precludes direct `log1p`) and the
interpretability concern that raw ₹ premium is not directly
comparable across issues.

**Redundancy elimination.** The mechanical `lot_size × issue_price
≈ 15,000` relationship (Spearman −0.996) is resolved by retaining
`issue_price` in log form only and dropping `lot_size` (D-17). The
`fresh_issue`, `ofs`, `total_issue_size` triple is resolved by
adding a single composition ratio `ofs_ratio = ofs / (fresh + ofs)`
alongside the log-transformed levels (D-18). `face_value` is
dropped entirely on the strength of its near-zero correlation with
the target (|ρ| = 0.02) and its degenerate single-observation
category (D-25).

**Financial ratios and scale.** Alongside the log-transformed levels
(`revenue_log1p`, `assets_log1p`, `borrowing_log1p`) the pipeline
constructs three dimensionless ratios: `profit_margin = profit /
revenue`, `return_on_assets = profit / assets`, `debt_to_equity =
borrowing / net_worth` (D-19). The five IPOs with non-positive
`net_worth` (Stove Kraft, Chemplast Sanmar, DCX Systems, SAMHI
Hotels, Indiqube Spaces) receive a NaN in `debt_to_equity` and a
companion `negative_networth_flag` (D-20).

**Broker signals.** Given the sparse and step-shaped relationship
of `brokers_avoid` with the target, a binary `any_avoid_flag` is
constructed as `brokers_avoid > 0`. Both raw counts
(`brokers_subscribe`, `brokers_avoid`) are also retained in the
feature file so that XGBoost can use their graded distinctions
where useful (D-21).

**Reporting.** Model performance in Chapter 9 is reported
separately for the GMP-available and GMP-absent slices of the test
set (D-23), and features flagged as year-conditionally unstable in
Section 5.4.2 (`brokers_avoid`, `nifty_30d_return`, `nifty_7d_return`,
`assets`) are noted as such when their SHAP importance is
presented (D-24). The `assets` sign-flip identified in Section 5.4.3
is a particular case of this — the feature is retained in the set
because XGBoost is robust to weak predictors and the model's actual
use of it will be assessed in Chapter 9, but the interpretation of
any assets-related SHAP contribution on the test set must reference
this instability.

**Regime handling.** No dedicated regime dummy is included in the
feature set. The corrected regime boundary is 2024/2025 as
established in Section 5.4.4, but the market-context features
(`nifty_close`, `vix_close`, `nifty_7d_return`, `nifty_30d_return`)
already carry the regime information — a model looking at
`nifty_close = 26,000` (pre-correction) versus `nifty_close =
22,500` (mid-correction) can condition its predictions on the same
underlying signal. Adding a binary dummy anchored to a specific
date chosen from the EDA distribution would risk using
test-period statistics to design a feature, which the dissertation
methodology avoids (D-22).

Chapter 6 implements the feature-engineering pipeline embodied by
these decisions.