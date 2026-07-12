"""
EDA STEP 02: Univariate feature analysis
=========================================
Distribution, coverage, skewness, and data-quality inspection of every raw
candidate predictor in the cleaned master dataset. Nothing engineered here;
each variable examined in isolation.

WHAT THIS ANSWERS
  - Which raw predictors are right-skewed enough to warrant log transformation
    at feature-engineering time (Chapter 6)?
  - What is the coverage of each predictor across the dataset, and how does
    that missingness pattern look over time?
  - Which categorical predictors (face_value, lot_size) take how many values?
  - Are there any data-quality issues (impossible values, extreme outliers)?
    In particular, we investigate the anomaly spotted in EDA-01: an IPO with
    first_day_open_return ≈ -1.0, implying listing_open ≈ 0.

WHAT IT DOES NOT DO
  - No feature engineering. No transforms saved to disk.
  - No bivariate analysis (that is script 03).

INPUTS
  data/processed/master_ipo_dataset.csv  (419 × 29, cleaned)

OUTPUTS
  reports/figures/eda/02_continuous_distributions.(png|pdf)
  reports/figures/eda/02_categorical_distributions.(png|pdf)
  reports/figures/eda/02_missingness_by_year.(png|pdf)
  reports/figures/eda/02_skewness_before_after_log.(png|pdf)
  reports/tables/eda/02_coverage_and_stats.csv
  reports/tables/eda/02_missingness_by_year.csv
  reports/tables/eda/02_skewness_table.csv
  reports/tables/eda/02_data_quality_flags.csv

RUN
  python3 src/eda/02_univariate_features.py
  (run from the project root)
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from _style import PAL, save_fig  # noqa: E402


# ============================================================
# PATHS
# ============================================================
MASTER  = "data/processed/master_ipo_dataset.csv"
FIG_DIR = "reports/figures/eda"
TAB_DIR = "reports/tables/eda"

os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(TAB_DIR, exist_ok=True)


# ============================================================
# VARIABLE CATEGORIES
# ============================================================
# The candidate predictors that will feed feature engineering (Chapter 6).
# Grouped here for readability in the printed report.
CONTINUOUS_PREDICTORS = [
    # Structural (deal shape)
    "issue_price", "total_issue_size", "fresh_issue", "ofs", "lot_size",
    # Demand
    "sub_total", "gmp_value",
    # Financials
    "revenue", "profit", "assets", "net_worth", "borrowing",
    # Broker sentiment
    "brokers_subscribe", "brokers_avoid",
    # Market context (all strictly prior-day, leakage-safe)
    "nifty_close", "vix_close", "nifty_7d_return", "nifty_30d_return",
]
# `lot_size` is a discrete integer but has 146 distinct values (1–780) —
# it belongs with the continuous variables, not with the small-cardinality
# categoricals below.
CATEGORICAL_PREDICTORS = ["face_value", "gmp_available"]

# Leakage columns — analysed here for data-quality only, NEVER predictors.
LEAKAGE_COLS = ["listing_open", "listing_close", "listing_high", "listing_low",
                "first_day_open_return"]


# ============================================================
# UTILITIES
# ============================================================
def hr(char="-"):
    print(char * 72)


def variable_stats(s):
    """Return summary stats for one numeric column."""
    n = len(s)
    valid = s.dropna()
    if len(valid) == 0:
        return {"n_total": n, "n_valid": 0, "coverage": 0.0,
                "n_missing": n, "n_zero": 0, "n_negative": 0,
                "mean": np.nan, "median": np.nan, "std": np.nan,
                "min": np.nan, "q25": np.nan, "q75": np.nan, "max": np.nan,
                "skew": np.nan}
    return {
        "n_total":    n,
        "n_valid":    len(valid),
        "coverage":   len(valid) / n,
        "n_missing":  int(s.isna().sum()),
        "n_zero":     int((valid == 0).sum()),
        "n_negative": int((valid < 0).sum()),
        "mean":       float(valid.mean()),
        "median":     float(valid.median()),
        "std":        float(valid.std()) if len(valid) > 1 else np.nan,
        "min":        float(valid.min()),
        "q25":        float(valid.quantile(0.25)),
        "q75":        float(valid.quantile(0.75)),
        "max":        float(valid.max()),
        "skew":       float(valid.skew()) if len(valid) > 1 else np.nan,
    }


# ============================================================
# LOAD
# ============================================================
def load():
    hr("=")
    print("EDA 02: UNIVARIATE FEATURE ANALYSIS")
    hr("=")
    if not os.path.exists(MASTER):
        raise FileNotFoundError(
            f"{MASTER} not found. Run this script from the project root.")
    df = pd.read_csv(MASTER)
    df["listing_date"] = pd.to_datetime(df["listing_date"])
    print(f"  Loaded {len(df)} IPOs from {MASTER}")
    print(f"  Predictors analysed: "
          f"{len(CONTINUOUS_PREDICTORS)} continuous, "
          f"{len(CATEGORICAL_PREDICTORS)} categorical")
    print(f"  Leakage columns analysed for data quality only: "
          f"{len(LEAKAGE_COLS)}")
    return df


# ============================================================
# 1. COVERAGE + SUMMARY STATISTICS
# ============================================================
def coverage_and_stats(df):
    print("\n" + "=" * 72)
    print("1. COVERAGE AND SUMMARY STATISTICS")
    hr()

    rows = []
    for col in CONTINUOUS_PREDICTORS + CATEGORICAL_PREDICTORS:
        st = variable_stats(df[col])
        st["variable"] = col
        st["type"] = "continuous" if col in CONTINUOUS_PREDICTORS else "categorical"
        rows.append(st)

    stats_df = pd.DataFrame(rows)[[
        "variable", "type", "n_valid", "coverage",
        "n_missing", "n_zero", "n_negative",
        "mean", "median", "std", "min", "q25", "q75", "max", "skew",
    ]]

    print(stats_df.round(3).to_string(index=False))
    stats_df.to_csv(os.path.join(TAB_DIR, "02_coverage_and_stats.csv"),
                    index=False)
    print(f"\n  Saved: {TAB_DIR}/02_coverage_and_stats.csv")

    # Highlight anything with < 90% coverage
    low_cov = stats_df[stats_df["coverage"] < 0.9]
    print("\n  Variables with < 90% coverage:")
    if len(low_cov) == 0:
        print("    (none — every predictor has ≥ 90% coverage)")
    else:
        for _, r in low_cov.iterrows():
            print(f"    {r['variable']:<24s} coverage={r['coverage']:.1%}  "
                  f"({r['n_missing']} missing / {r['n_valid'] + r['n_missing']})")

    return stats_df


# ============================================================
# 2. CONTINUOUS-VARIABLE DISTRIBUTION GRID
# ============================================================
def plot_continuous_grid(df):
    print("\n" + "=" * 72)
    print("2. DISTRIBUTIONS OF CONTINUOUS PREDICTORS (small-multiples grid)")
    hr()

    n_vars = len(CONTINUOUS_PREDICTORS)
    n_cols = 4
    n_rows = int(np.ceil(n_vars / n_cols))

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(14, 3 * n_rows))
    axes = axes.flatten()

    for i, col in enumerate(CONTINUOUS_PREDICTORS):
        ax = axes[i]
        s = df[col].dropna()
        if len(s) == 0:
            ax.text(0.5, 0.5, "no data", ha='center', va='center',
                    transform=ax.transAxes)
            ax.set_title(col, fontsize=9)
            continue
        n_bins = min(40, max(10, int(np.sqrt(len(s)))))
        ax.hist(s, bins=n_bins, color=PAL["primary"], alpha=0.75,
                edgecolor='white')
        ax.axvline(s.median(), color=PAL["accent"], linestyle='--',
                   linewidth=1)
        skew_v = s.skew()
        ax.set_title(f"{col}\nskew={skew_v:.2f}, n={len(s)}", fontsize=9)
        ax.tick_params(axis='both', labelsize=8)
        # Log-scale y-axis when data is strictly positive AND extremely skewed —
        # otherwise the histogram is unreadable.
        if s.min() > 0 and skew_v > 5:
            ax.set_yscale('log')

    # Hide any unused subplots
    for j in range(n_vars, len(axes)):
        axes[j].axis('off')

    fig.suptitle("Continuous predictors — raw distributions "
                 "(dashed line = median)", fontsize=13, y=1.00)
    fig.tight_layout()
    save_fig(fig, "02_continuous_distributions", FIG_DIR)
    plt.close(fig)
    print(f"  Saved: {FIG_DIR}/02_continuous_distributions.(png|pdf)")


# ============================================================
# 3. CATEGORICAL VARIABLE VALUE COUNTS
# ============================================================
def plot_categorical(df):
    print("\n" + "=" * 72)
    print("3. CATEGORICAL PREDICTORS — value counts")
    hr()

    fig, axes = plt.subplots(1, len(CATEGORICAL_PREDICTORS), figsize=(11, 4))
    if len(CATEGORICAL_PREDICTORS) == 1:
        axes = [axes]
    for ax, col in zip(axes, CATEGORICAL_PREDICTORS):
        vc_full = df[col].value_counts(dropna=False).sort_index()
        # Safeguard: if someone later moves a high-cardinality variable in
        # here by accident, don't produce an unreadable plot — cap at 20
        # and warn.
        if len(vc_full) > 20:
            print(f"  [warn] {col} has {len(vc_full)} distinct values — "
                  f"treating as categorical is questionable; showing top 20")
            vc = vc_full.nlargest(20).sort_index()
        else:
            vc = vc_full
        # Label NaN explicitly if present
        labels = [f"{idx}" if pd.notna(idx) else "NaN" for idx in vc.index]
        ax.bar(labels, vc.values, color=PAL["primary"], alpha=0.8,
               edgecolor='white')
        for i, v in enumerate(vc.values):
            ax.text(i, v + max(vc.values) * 0.015, str(int(v)),
                    ha='center', fontsize=9)
        ax.set_title(col)
        ax.set_ylabel('count')
        ax.set_xlabel(col)

        print(f"  {col} — {len(vc_full)} distinct value(s):")
        for idx, v in vc_full.items():
            print(f"    {idx if pd.notna(idx) else 'NaN':<10} {v}")

    fig.suptitle("Categorical predictors — value counts", fontsize=13, y=1.02)
    fig.tight_layout()
    save_fig(fig, "02_categorical_distributions", FIG_DIR)
    plt.close(fig)
    print(f"\n  Saved: {FIG_DIR}/02_categorical_distributions.(png|pdf)")


# ============================================================
# 4. MISSINGNESS HEATMAP BY YEAR
# ============================================================
def missingness_heatmap(df):
    print("\n" + "=" * 72)
    print("4. MISSINGNESS BY VARIABLE × YEAR")
    hr()

    all_predictors = CONTINUOUS_PREDICTORS + CATEGORICAL_PREDICTORS
    missing_vars = [c for c in all_predictors if df[c].isna().any()]

    if len(missing_vars) == 0:
        print("  No missingness in any predictor — skipping heatmap.")
        return

    print(f"  Variables with any missingness: {len(missing_vars)}")

    years = sorted(df["year"].unique())
    matrix = pd.DataFrame(index=missing_vars, columns=years, dtype=float)
    for var in missing_vars:
        for yr in years:
            sub = df[df["year"] == yr][var]
            matrix.loc[var, yr] = sub.isna().mean() if len(sub) > 0 else np.nan

    matrix.to_csv(os.path.join(TAB_DIR, "02_missingness_by_year.csv"))
    print(f"  Saved: {TAB_DIR}/02_missingness_by_year.csv")

    fig, ax = plt.subplots(figsize=(10, max(4, 0.45 * len(missing_vars))))
    im = ax.imshow(matrix.values.astype(float), cmap='Reds',
                   vmin=0, vmax=1, aspect='auto')
    ax.set_xticks(range(len(years)))
    ax.set_xticklabels([str(y) for y in years])
    ax.set_yticks(range(len(missing_vars)))
    ax.set_yticklabels(missing_vars)

    # Annotate cells with percentages
    for i in range(len(missing_vars)):
        for j in range(len(years)):
            v = matrix.iloc[i, j]
            if pd.notna(v):
                colour = 'white' if v > 0.5 else 'black'
                ax.text(j, i, f"{v:.0%}", ha='center', va='center',
                        color=colour, fontsize=8)

    plt.colorbar(im, ax=ax, label="fraction missing")
    ax.set_xlabel("year"); ax.set_ylabel("variable")
    ax.set_title("Missingness fraction by variable × year "
                 "(darker = more missing)")
    ax.grid(False)
    fig.tight_layout()
    save_fig(fig, "02_missingness_by_year", FIG_DIR)
    plt.close(fig)
    print(f"  Saved: {FIG_DIR}/02_missingness_by_year.(png|pdf)")


# ============================================================
# 5. SKEWNESS AND LOG-TRANSFORM PREVIEW
# ============================================================
def skewness_analysis(df):
    print("\n" + "=" * 72)
    print("5. SKEWNESS AND LOG-TRANSFORM PREVIEW")
    hr()
    print("  Rule of thumb: |skew| > 1 = candidate for transformation.")
    print("  log1p is only applied where values are strictly non-negative.")
    print()

    rows = []
    for col in CONTINUOUS_PREDICTORS:
        s = df[col].dropna()
        if len(s) < 2:
            continue
        raw_skew = float(s.skew())
        can_log = bool(s.min() >= 0)
        log_skew = float(np.log1p(s).skew()) if can_log else np.nan
        rows.append({
            "variable":  col,
            "min":       float(s.min()),
            "raw_skew":  raw_skew,
            "can_log1p": can_log,
            "log_skew":  log_skew,
        })

    skew_df = pd.DataFrame(rows)
    skew_df["needs_transform"] = skew_df["raw_skew"].abs() > 1
    skew_df["log_helps"] = (
        skew_df["can_log1p"]
        & skew_df["log_skew"].abs().lt(skew_df["raw_skew"].abs())
    )

    print(skew_df.round(3).to_string(index=False))
    skew_df.to_csv(os.path.join(TAB_DIR, "02_skewness_table.csv"), index=False)
    print(f"\n  Saved: {TAB_DIR}/02_skewness_table.csv")

    # Bar chart of variables that both need transformation and can be logged
    plot_vars = skew_df[skew_df["needs_transform"] & skew_df["can_log1p"]] \
        .sort_values("raw_skew", ascending=False)

    if len(plot_vars) == 0:
        print("  No variables both need transform AND can be log1p'd.")
        return skew_df

    fig, ax = plt.subplots(figsize=(10, max(4, 0.4 * len(plot_vars))))
    y = np.arange(len(plot_vars))
    ax.barh(y - 0.2, plot_vars["raw_skew"], height=0.4,
            color=PAL["accent"], alpha=0.75, label='raw skew')
    ax.barh(y + 0.2, plot_vars["log_skew"], height=0.4,
            color=PAL["positive"], alpha=0.75, label='log1p skew')
    ax.axvline(1,  color=PAL["muted"], linestyle=':', label='|skew| = 1 threshold')
    ax.axvline(-1, color=PAL["muted"], linestyle=':')
    ax.axvline(0,  color='black', linewidth=0.5)
    ax.set_yticks(y)
    ax.set_yticklabels(plot_vars["variable"])
    ax.set_xlabel("skewness")
    ax.set_title("Skewness before vs after log1p — non-negative variables "
                 "with |skew| > 1")
    ax.legend(frameon=False)
    fig.tight_layout()
    save_fig(fig, "02_skewness_before_after_log", FIG_DIR)
    plt.close(fig)
    print(f"  Saved: {FIG_DIR}/02_skewness_before_after_log.(png|pdf)")

    return skew_df


# ============================================================
# 6. DATA-QUALITY HUNT
# ============================================================
def data_quality_hunt(df):
    print("\n" + "=" * 72)
    print("6. DATA-QUALITY HUNT")
    hr()
    print("  Impossible values, listing-OHLC consistency violations, and")
    print("  the anomaly spotted in EDA-01 (first_day_open_return ≈ -1.0).\n")

    issues = []

    def add(kind, row, detail):
        issues.append({
            "issue_type": kind,
            "company": row["company"],
            "listing_date": row["listing_date"],
            "detail": detail,
        })

    # 6a. Any zero or negative listing_open (impossible for a traded stock)
    if "listing_open" in df.columns:
        for _, r in df[df["listing_open"] <= 0].iterrows():
            add("nonpositive_listing_open", r,
                f"listing_open={r['listing_open']}, "
                f"listing_close={r.get('listing_close')}, "
                f"issue_price={r['issue_price']}")

    # 6b. first_day_open_return close to -1.0 (the EDA-01 anomaly)
    if "first_day_open_return" in df.columns:
        for _, r in df[df["first_day_open_return"] <= -0.99].iterrows():
            add("first_day_open_return_near_-1", r,
                f"first_day_open_return={r['first_day_open_return']:.4f}, "
                f"listing_open={r.get('listing_open')}, "
                f"issue_price={r['issue_price']}")

    # 6c. Listing OHLC internal consistency
    ohlc = ["listing_open", "listing_close", "listing_high", "listing_low"]
    if all(c in df.columns for c in ohlc):
        d = df.dropna(subset=ohlc)
        # high must be >= low
        for _, r in d[d["listing_high"] < d["listing_low"]].iterrows():
            add("listing_high_lt_low", r,
                f"high={r['listing_high']}, low={r['listing_low']}")
        # open must lie in [low, high]
        bad_open = d[(d["listing_open"] > d["listing_high"])
                     | (d["listing_open"] < d["listing_low"])]
        for _, r in bad_open.iterrows():
            add("listing_open_outside_high_low", r,
                f"open={r['listing_open']}, "
                f"high={r['listing_high']}, low={r['listing_low']}")
        # close must lie in [low, high]
        bad_close = d[(d["listing_close"] > d["listing_high"])
                      | (d["listing_close"] < d["listing_low"])]
        for _, r in bad_close.iterrows():
            add("listing_close_outside_high_low", r,
                f"close={r['listing_close']}, "
                f"high={r['listing_high']}, low={r['listing_low']}")

    # 6d. Negatives in variables that should be non-negative
    non_negative = ["issue_price", "total_issue_size", "sub_total",
                    "revenue", "assets", "brokers_subscribe",
                    "brokers_avoid", "nifty_close", "vix_close",
                    "fresh_issue", "ofs",
                    "listing_open", "listing_close",
                    "listing_high", "listing_low"]
    for col in non_negative:
        if col not in df.columns:
            continue
        for _, r in df[df[col] < 0].iterrows():
            add(f"unexpected_negative_{col}", r,
                f"{col}={r[col]}")

    if len(issues) == 0:
        print("  No data-quality issues found.")
        pd.DataFrame(columns=["issue_type", "company",
                              "listing_date", "detail"]) \
            .to_csv(os.path.join(TAB_DIR, "02_data_quality_flags.csv"),
                    index=False)
    else:
        issues_df = pd.DataFrame(issues).sort_values(["issue_type", "company"])
        # Deduplicate: same (issue_type, company) may fire from multiple checks
        issues_df = issues_df.drop_duplicates(subset=["issue_type", "company"])
        print(f"  Found {len(issues_df)} distinct data-quality flag(s):\n")
        for _, r in issues_df.iterrows():
            print(f"    [{r['issue_type']}]")
            print(f"      {r['company']} ({r['listing_date'].date()})")
            print(f"      {r['detail']}\n")
        issues_df.to_csv(os.path.join(TAB_DIR, "02_data_quality_flags.csv"),
                         index=False)
    print(f"  Saved: {TAB_DIR}/02_data_quality_flags.csv")


# ============================================================
# MAIN
# ============================================================
def main():
    df = load()
    coverage_and_stats(df)
    plot_continuous_grid(df)
    plot_categorical(df)
    missingness_heatmap(df)
    skewness_analysis(df)
    data_quality_hunt(df)

    print("\n" + "#" * 72)
    print("# EDA 02 COMPLETE")
    print("#" * 72)
    print(f"  Figures: {FIG_DIR}/")
    print(f"  Tables:  {TAB_DIR}/")
    print("  Next up: 03_bivariate.py "
          "(feature-feature correlations, feature-target relationships)")


if __name__ == "__main__":
    main()
    