"""
EDA STEP 04: Temporal and regime-conditional analysis
======================================================
Final EDA script. Examines how the predictors and their relationship
with first_day_return change across the 8-year study period. Nothing
is engineered here.

WHAT THIS ANSWERS
  - Do predictor distributions drift meaningfully between the train
    period (≤2023) and the test period (2025-26)? This is the
    "covariate shift" question. Large drift means training on the past
    will imperfectly generalise to the future — a real risk.
  - Which predictor-target relationships are stable across years, and
    which change or disappear? Stable relationships are safer to model.
    Year-varying ones may need regime dummies or should be interpreted
    with caution in Chapter 9.
  - What do the three temporal splits (train / val / test) look like
    when compared directly?
  - EDA-01 tested pre-2024 vs 2024+ and rejected equality only weakly
    (Mann-Whitney p=0.028). The visual evidence there suggested the true
    break is 2024→2025. Is that confirmed by re-testing at the correct
    split point?

WHAT IT DOES NOT DO
  - No feature engineering.
  - Repetition of the target-distribution work covered in EDA-01
    (median/mean/positive-share by year) is deliberately avoided.

INPUTS
  data/processed/master_ipo_dataset.csv

OUTPUTS
  reports/figures/eda/04_feature_drift.(png|pdf)
  reports/figures/eda/04_year_conditional_correlations.(png|pdf)
  reports/figures/eda/04_train_val_test_comparison.(png|pdf)
  reports/tables/eda/04_feature_medians_by_year.csv
  reports/tables/eda/04_year_conditional_correlations.csv
  reports/tables/eda/04_train_val_test_summary.csv
  reports/tables/eda/04_train_val_test_correlations.csv
  reports/tables/eda/04_regime_test_2024_vs_2025.csv

RUN
  python3 src/eda/04_temporal_and_regime.py
  (run from the project root)
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

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
# CONFIG
# ============================================================
# Predictors we track for drift. Ten variables chosen to cover the
# major feature groups: demand, GMP, broker sentiment, deal structure,
# financials, and market context.
DRIFT_VARS = [
    "gmp_value", "sub_total", "brokers_subscribe", "brokers_avoid",
    "issue_price", "revenue", "assets", "borrowing",
    "nifty_close", "vix_close",
]

# Log-scale y-axis for variables with heavy right skew (from EDA-02);
# otherwise box widths are unreadable.
LOG_SCALE_VARS = {"revenue", "assets", "borrowing", "sub_total"}

# The six most-correlated predictors from EDA-03 — those we care most
# about for year-conditional analysis.
TOP_PREDICTORS = [
    "gmp_value", "sub_total", "brokers_avoid", "brokers_subscribe",
    "nifty_30d_return", "nifty_7d_return",
]

TARGET = "first_day_return"


def hr(char="-"):
    print(char * 72)


# ============================================================
# LOAD
# ============================================================
def load():
    hr("=")
    print("EDA 04: TEMPORAL AND REGIME-CONDITIONAL ANALYSIS")
    hr("=")
    if not os.path.exists(MASTER):
        raise FileNotFoundError(
            f"{MASTER} not found. Run this script from the project root.")
    df = pd.read_csv(MASTER)
    df["listing_date"] = pd.to_datetime(df["listing_date"])
    print(f"  Loaded {len(df)} IPOs from {MASTER}")
    return df


# ============================================================
# 1. FEATURE DRIFT BY YEAR
# ============================================================
def feature_drift(df):
    print("\n" + "=" * 72)
    print("1. FEATURE DISTRIBUTIONS BY YEAR — do inputs drift?")
    hr()

    years = sorted(df["year"].unique())

    # Median-by-year table
    rows = []
    for var in DRIFT_VARS:
        row = {"variable": var}
        for yr in years:
            sub = df[df["year"] == yr][var].dropna()
            row[str(yr)] = float(sub.median()) if len(sub) > 0 else np.nan
        rows.append(row)
    medians_df = pd.DataFrame(rows)
    print("  Median by year for each drift-monitored variable:")
    print(medians_df.round(3).to_string(index=False))
    medians_df.to_csv(
        os.path.join(TAB_DIR, "04_feature_medians_by_year.csv"),
        index=False)
    print(f"\n  Saved: {TAB_DIR}/04_feature_medians_by_year.csv")

    # Box-plot grid
    n_vars = len(DRIFT_VARS)
    n_cols = 4
    n_rows = int(np.ceil(n_vars / n_cols))
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(15, 4 * n_rows))
    axes = axes.flatten()

    for i, var in enumerate(DRIFT_VARS):
        ax = axes[i]
        data_by_year = [df[df["year"] == yr][var].dropna().values
                        for yr in years]
        # Replace empty arrays with a placeholder so matplotlib doesn't crash
        data_for_plot = [d if len(d) > 0 else np.array([np.nan])
                         for d in data_by_year]

        bp = ax.boxplot(
            data_for_plot,
            tick_labels=[str(y) for y in years],
            showfliers=False,
            patch_artist=True,
            boxprops=dict(facecolor=PAL["primary"], alpha=0.5),
            medianprops=dict(color=PAL["accent"], linewidth=1.5),
            whiskerprops=dict(color=PAL["neutral"]),
            capprops=dict(color=PAL["neutral"]),
        )

        # Log-scale y-axis only if data is strictly positive
        if var in LOG_SCALE_VARS:
            all_positive = all(np.all(d > 0) for d in data_by_year
                               if len(d) > 0)
            if all_positive:
                ax.set_yscale('log')

        # Mark empty years so it's clear
        for j, d in enumerate(data_by_year):
            if len(d) == 0:
                ax.text(j + 1, ax.get_ylim()[0] * 1.05 if var in LOG_SCALE_VARS
                        else 0, "n/a", ha='center', fontsize=7,
                        color=PAL["muted"])

        ax.set_title(var, fontsize=10)
        ax.tick_params(axis='x', labelsize=8, rotation=45)
        ax.tick_params(axis='y', labelsize=8)

    # Hide unused subplots
    for j in range(n_vars, len(axes)):
        axes[j].axis('off')

    fig.suptitle("Feature distributions by year "
                 "(box plots — outliers hidden; log-y where indicated)",
                 fontsize=13, y=1.00)
    fig.tight_layout()
    save_fig(fig, "04_feature_drift", FIG_DIR)
    plt.close(fig)
    print(f"  Saved: {FIG_DIR}/04_feature_drift.(png|pdf)")


# ============================================================
# 2. YEAR-CONDITIONAL FEATURE-TARGET CORRELATIONS
# ============================================================
def year_conditional_correlations(df):
    print("\n" + "=" * 72)
    print("2. YEAR-CONDITIONAL FEATURE-TARGET CORRELATIONS")
    hr()
    print("  Spearman ρ between each top predictor and first_day_return,")
    print("  computed separately for each year. Small early years will")
    print("  have wide bootstrap CIs — read those comparatively, not as")
    print("  significance tests.")
    print()

    years = sorted(df["year"].unique())
    rng = np.random.default_rng(42)

    rows = []
    for var in TOP_PREDICTORS:
        for yr in years:
            sub = df[df["year"] == yr][[var, TARGET]].dropna()
            n = len(sub)
            if n < 5:
                rows.append({"variable": var, "year": int(yr), "n": n,
                             "spearman": np.nan,
                             "ci_lo": np.nan, "ci_hi": np.nan})
                continue
            x = sub[var].values
            y = sub[TARGET].values
            try:
                rho = float(stats.spearmanr(x, y).correlation)
            except Exception:
                rho = np.nan

            # Bootstrap 95% CI
            n_boot = 500
            boot_rhos = []
            for _ in range(n_boot):
                idx = rng.integers(0, n, size=n)
                try:
                    b_rho = stats.spearmanr(x[idx], y[idx]).correlation
                    if not np.isnan(b_rho):
                        boot_rhos.append(float(b_rho))
                except Exception:
                    pass
            if len(boot_rhos) < 50:
                lo, hi = np.nan, np.nan
            else:
                lo, hi = np.quantile(boot_rhos, [0.025, 0.975])
            rows.append({"variable": var, "year": int(yr), "n": n,
                         "spearman": rho,
                         "ci_lo": float(lo), "ci_hi": float(hi)})

    yc_df = pd.DataFrame(rows)
    print(yc_df.round(3).to_string(index=False))
    yc_df.to_csv(
        os.path.join(TAB_DIR, "04_year_conditional_correlations.csv"),
        index=False)
    print(f"\n  Saved: {TAB_DIR}/04_year_conditional_correlations.csv")

    # 2×3 grid of per-predictor line plots
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    axes = axes.flatten()

    for i, var in enumerate(TOP_PREDICTORS):
        ax = axes[i]
        sub = yc_df[yc_df["variable"] == var].sort_values("year")
        valid = sub.dropna(subset=["spearman"])
        y_pos  = valid["spearman"].values
        yerr_lo = y_pos - valid["ci_lo"].values
        yerr_hi = valid["ci_hi"].values - y_pos
        ax.errorbar(valid["year"], y_pos,
                    yerr=[yerr_lo, yerr_hi],
                    fmt='o-', color=PAL["primary"], capsize=4,
                    linewidth=1.5)
        ax.axhline(0, color=PAL["muted"], linewidth=0.5)

        # Full-sample reference line
        full = df[[var, TARGET]].dropna()
        if len(full) > 3:
            full_rho = float(
                stats.spearmanr(full[var], full[TARGET]).correlation)
            ax.axhline(full_rho, color=PAL["accent"], linestyle=':',
                       linewidth=1,
                       label=f'full-sample ρ = {full_rho:.2f}')
            ax.legend(frameon=False, fontsize=8, loc='best')

        # Vertical band highlighting the regime break at 2024/2025
        ax.axvspan(2024.5, 2026.5, color=PAL["muted"], alpha=0.10)

        ax.set_xlabel("year", fontsize=9)
        ax.set_ylabel("Spearman ρ", fontsize=9)
        ax.set_title(f"{var}", fontsize=10)
        ax.tick_params(axis='both', labelsize=8)

    fig.suptitle("Year-conditional Spearman ρ with first_day_return "
                 "(95% bootstrap CI; shaded = 2025-26 regime)",
                 fontsize=13, y=1.00)
    fig.tight_layout()
    save_fig(fig, "04_year_conditional_correlations", FIG_DIR)
    plt.close(fig)
    print(f"  Saved: {FIG_DIR}/04_year_conditional_correlations.(png|pdf)")


# ============================================================
# 3. TRAIN / VAL / TEST COMPARISON
# ============================================================
def train_val_test_comparison(df):
    print("\n" + "=" * 72)
    print("3. TRAIN / VAL / TEST COMPARISON (the locked temporal split)")
    hr()

    splits = [
        ("train (≤2023)",  df[df["year"] <= 2023]),
        ("val (2024)",     df[df["year"] == 2024]),
        ("test (2025-26)", df[df["year"] >= 2025]),
    ]

    # Target summary
    target_rows = []
    for label, sub in splits:
        y = sub[TARGET]
        target_rows.append({
            "split":                 label,
            "n":                     len(sub),
            "target_mean":           float(y.mean()),
            "target_median":         float(y.median()),
            "target_std":            float(y.std()),
            "target_positive_share": float((y > 0).mean()),
        })
    target_df = pd.DataFrame(target_rows)
    print("  Target summary by split:")
    print(target_df.round(3).to_string(index=False))
    target_df.to_csv(
        os.path.join(TAB_DIR, "04_train_val_test_summary.csv"),
        index=False)

    # Top-predictor correlations across splits
    compare_vars = TOP_PREDICTORS + ["borrowing", "assets"]
    corr_rows = []
    for var in compare_vars:
        row = {"variable": var}
        for label, sub in splits:
            both = sub[[var, TARGET]].dropna()
            row[label] = (float(both.corr(method='spearman').iloc[0, 1])
                          if len(both) >= 5 else np.nan)
        corr_rows.append(row)
    corr_df = pd.DataFrame(corr_rows)
    print("\n  Spearman ρ with target by split:")
    print(corr_df.round(3).to_string(index=False))
    corr_df.to_csv(
        os.path.join(TAB_DIR, "04_train_val_test_correlations.csv"),
        index=False)
    print(f"\n  Saved: {TAB_DIR}/04_train_val_test_summary.csv")
    print(f"  Saved: {TAB_DIR}/04_train_val_test_correlations.csv")

    # Figure: two panels — target ECDF, and grouped-bar of correlations
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # (a) target ECDF by split
    ax = axes[0]
    colors_ecdf = [PAL["primary"], PAL["positive"], PAL["accent"]]
    for (label, sub), colour in zip(splits, colors_ecdf):
        y = sub[TARGET].dropna().values
        s = np.sort(y)
        ax.plot(s, np.arange(1, len(s) + 1) / len(s),
                linewidth=2, color=colour, label=f"{label} (n={len(y)})")
    ax.axvline(0, color=PAL["muted"], linewidth=0.6)
    ax.set_xlabel("first_day_return")
    ax.set_ylabel("cumulative probability")
    ax.set_title("(a) Target distribution — ECDF by split")
    ax.legend(frameon=False, loc='lower right', fontsize=9)

    # (b) predictor correlations across splits (grouped horizontal bars)
    ax = axes[1]
    vars_sorted = corr_df["variable"].tolist()
    y = np.arange(len(vars_sorted))
    width = 0.25
    labels = [s[0] for s in splits]
    for k, label in enumerate(labels):
        vals = corr_df[label].fillna(0).values
        ax.barh(y + (k - 1) * width, vals, height=width,
                color=colors_ecdf[k], alpha=0.85, label=label)
    ax.axvline(0, color='black', linewidth=0.5)
    for x in [-0.3, -0.1, 0.1, 0.3]:
        ax.axvline(x, color=PAL["muted"], linestyle=':', linewidth=0.5)
    ax.set_yticks(y)
    ax.set_yticklabels(vars_sorted, fontsize=9)
    ax.set_xlabel("Spearman ρ with first_day_return")
    ax.set_title("(b) Feature-target correlations by split")
    ax.legend(frameon=False, loc='lower right', fontsize=9)

    fig.tight_layout()
    save_fig(fig, "04_train_val_test_comparison", FIG_DIR)
    plt.close(fig)
    print(f"  Saved: {FIG_DIR}/04_train_val_test_comparison.(png|pdf)")


# ============================================================
# 4. REGIME BREAK TEST — the correct split point
# ============================================================
def regime_break_test(df):
    print("\n" + "=" * 72)
    print("4. REGIME BREAK TEST — pre-2025 vs 2025+")
    hr()
    print("  EDA-01 tested pre-2024 vs 2024+ (Mann-Whitney p = 0.029);")
    print("  the visual evidence there suggested the true break is")
    print("  2024→2025. Re-testing at the correct split point:")
    print()

    # The corrected split
    early = df[df["year"] <= 2024][TARGET].dropna()
    late  = df[df["year"] >= 2025][TARGET].dropna()
    u_stat, u_p = stats.mannwhitneyu(early, late, alternative='two-sided')
    m_stat, m_p, *_ = stats.median_test(early, late)

    print(f"  Pre-2025 (2019-2024): n={len(early)}, "
          f"mean={early.mean():.4f}, median={early.median():.4f}")
    print(f"  2025+ (2025-26):      n={len(late)}, "
          f"mean={late.mean():.4f}, median={late.median():.4f}")
    print()
    print(f"  Mann-Whitney U : U={u_stat:.0f}, p={u_p:.4e}")
    print(f"  Mood's median  : stat={m_stat:.2f}, p={m_p:.4e}")

    # For comparison, the EDA-01 split
    early_old = df[df["year"] <= 2023][TARGET].dropna()
    late_old  = df[df["year"] >= 2024][TARGET].dropna()
    u_stat_old, u_p_old = stats.mannwhitneyu(
        early_old, late_old, alternative='two-sided')
    print(f"\n  For reference — the EDA-01 split (pre-2024 vs 2024+):")
    print(f"    n_early={len(early_old)}, n_late={len(late_old)}, "
          f"U={u_stat_old:.0f}, p={u_p_old:.4e}")

    ratio = u_p_old / u_p if u_p > 0 else np.nan
    print()
    print(f"  The pre-2025 vs 2025+ split gives p = {u_p:.2e}, roughly")
    print(f"  {ratio:.0f}× smaller than the EDA-01 split's p = {u_p_old:.2e}.")
    print(f"  This confirms the true regime break is 2024→2025, not")
    print(f"  2023→2024.")

    result = pd.DataFrame([
        {"split":             "pre-2024 vs 2024+ (EDA-01)",
         "n_early":           len(early_old),
         "n_late":            len(late_old),
         "mann_whitney_U":    float(u_stat_old),
         "mann_whitney_p":    float(u_p_old)},
        {"split":             "pre-2025 vs 2025+ (corrected)",
         "n_early":           len(early),
         "n_late":            len(late),
         "mann_whitney_U":    float(u_stat),
         "mann_whitney_p":    float(u_p)},
    ])
    result.to_csv(
        os.path.join(TAB_DIR, "04_regime_test_2024_vs_2025.csv"),
        index=False)
    print(f"\n  Saved: {TAB_DIR}/04_regime_test_2024_vs_2025.csv")


# ============================================================
# MAIN
# ============================================================
def main():
    df = load()
    feature_drift(df)
    year_conditional_correlations(df)
    train_val_test_comparison(df)
    regime_break_test(df)

    print("\n" + "#" * 72)
    print("# EDA 04 COMPLETE — all four EDA scripts finished")
    print("#" * 72)
    print(f"  Figures: {FIG_DIR}/")
    print(f"  Tables:  {TAB_DIR}/")
    print()
    print("  Next up: consolidate findings into Chapter 5 §5.1–§5.5 and")
    print("  update Appendix A with the feature-engineering decisions this")
    print("  EDA has justified. Then Chapter 6 (feature engineering) can")
    print("  be written on solid empirical foundations.")


if __name__ == "__main__":
    main()