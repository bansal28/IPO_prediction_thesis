"""
EDA STEP 01: Target variable analysis
======================================
Deep exploratory analysis of `first_day_return` — the modelling target.
Nothing is engineered here; only visualised and tabulated.

WHAT THIS ANSWERS
  - Is the target's distribution Gaussian-ish, or does it need transformation?
  - Is there a temporal regime shift? (Justifies temporal train/test split
    and may motivate regime dummies in the model.)
  - Where are the extreme values? (Sanity check + narrative material.)
  - How does the "open" first-day return compare to the "close" first-day
    return? (Informs choice of target — we default to close.)

WHAT IT DOES NOT DO
  - No feature engineering. No transforms saved to disk.
  - No modelling. No feature-vs-target relationship analysis.
    (That belongs to scripts 02/03.)

INPUTS
  data/processed/master_ipo_dataset.csv  (419 × 29, cleaned)

OUTPUTS
  reports/figures/eda/01_target_distribution.(png|pdf)
  reports/figures/eda/01_target_temporal.(png|pdf)
  reports/figures/eda/01_target_regime.(png|pdf)
  reports/figures/eda/01_target_open_vs_close.(png|pdf)
  reports/tables/eda/01_target_summary.csv
  reports/tables/eda/01_target_by_year.csv
  reports/tables/eda/01_target_top10_gainers.csv
  reports/tables/eda/01_target_top10_losers.csv

RUN
  python3 src/eda/01_target_analysis.py
  (run from the project root)
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

# Shared styling — resolves relative to this file so cwd doesn't matter
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from _style import PAL, save_fig  # noqa: E402


# ============================================================
# PATHS  (relative to project root; script is run from there)
# ============================================================
MASTER  = "data/processed/master_ipo_dataset.csv"
FIG_DIR = "reports/figures/eda"
TAB_DIR = "reports/tables/eda"

# Ensure output directories exist before anything tries to write to them.
# Idempotent: safe to run repeatedly.
os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(TAB_DIR, exist_ok=True)


def hr(char="-"):
    print(char * 72)


# ============================================================
# LOAD
# ============================================================
def load():
    hr("=")
    print("EDA 01: TARGET VARIABLE ANALYSIS — first_day_return")
    hr("=")
    if not os.path.exists(MASTER):
        raise FileNotFoundError(
            f"{MASTER} not found. Run this script from the project root."
        )
    df = pd.read_csv(MASTER)
    df["listing_date"] = pd.to_datetime(df["listing_date"])
    print(f"  Loaded {len(df)} IPOs from {MASTER}")
    print(f"  Time range: {df['listing_date'].min().date()} "
          f"→ {df['listing_date'].max().date()}")
    if df["first_day_return"].isna().any():
        print(f"  [warn] {df['first_day_return'].isna().sum()} rows have NaN target — dropped for analysis")
    return df


# ============================================================
# 1. DISTRIBUTION OF THE TARGET
# ============================================================
def analyse_distribution(df):
    print("\n" + "=" * 72)
    print("1. DISTRIBUTION OF first_day_return")
    hr()
    y = df["first_day_return"].dropna()

    # Summary statistics
    stats_row = {
        "n":               len(y),
        "mean":            y.mean(),
        "median":          y.median(),
        "std":             y.std(),
        "min":             y.min(),
        "q05":             y.quantile(0.05),
        "q25":             y.quantile(0.25),
        "q75":             y.quantile(0.75),
        "q95":             y.quantile(0.95),
        "max":             y.max(),
        "skew":            y.skew(),
        "excess_kurtosis": y.kurt(),
        "positive_share":  (y > 0).mean(),
        "zero_share":      (y == 0).mean(),
        "negative_share":  (y < 0).mean(),
    }
    print("  Summary statistics:")
    for k, v in stats_row.items():
        print(f"    {k:<18s} {v:>10.4f}")

    pd.DataFrame([stats_row]).to_csv(
        os.path.join(TAB_DIR, "01_target_summary.csv"), index=False)
    print(f"  Saved: {TAB_DIR}/01_target_summary.csv")

    # Formal normality tests (will reject — thesis needs to justify non-Gaussian handling)
    sw_stat, sw_p = stats.shapiro(y)
    ks_stat, ks_p = stats.kstest((y - y.mean()) / y.std(), "norm")
    print(f"\n  Shapiro-Wilk normality test:  W={sw_stat:.4f}, p={sw_p:.2e}")
    print(f"  Kolmogorov-Smirnov (standardised vs N(0,1)):  D={ks_stat:.4f}, p={ks_p:.2e}")
    if sw_p < 0.05:
        print("    -> Target is NOT normal (expected). Skewness/kurtosis inform "
              "loss choice and any target transformation later.")

    # ---- 4-panel distribution figure ----
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))

    # (a) Histogram + KDE
    ax = axes[0, 0]
    ax.hist(y, bins=50, color=PAL["primary"], alpha=0.75,
            edgecolor="white", density=True)
    kde_x = np.linspace(y.min(), y.max(), 400)
    ax.plot(kde_x, stats.gaussian_kde(y)(kde_x),
            color=PAL["accent"], linewidth=2, label="KDE")
    ax.axvline(y.median(), color=PAL["neutral"], linestyle="--",
               label=f"median = {y.median():.3f}")
    ax.axvline(y.mean(),   color="black",       linestyle=":",
               label=f"mean = {y.mean():.3f}")
    ax.axvline(0, color=PAL["muted"], linewidth=0.8)
    ax.set_xlabel("first_day_return")
    ax.set_ylabel("density")
    ax.set_title(f"(a) Distribution (n={len(y)})")
    ax.legend(loc="upper right", frameon=False)

    # (b) Boxplot
    ax = axes[0, 1]
    ax.boxplot(y, vert=False, showfliers=True, patch_artist=True,
               boxprops=dict(facecolor=PAL["primary"], alpha=0.5),
               medianprops=dict(color=PAL["accent"], linewidth=2))
    ax.set_xlabel("first_day_return")
    ax.set_yticks([])
    ax.set_title(f"(b) Boxplot  —  range [{y.min():.2f}, {y.max():.2f}]")
    ax.axvline(0, color=PAL["muted"], linewidth=0.8)

    # (c) Q-Q plot vs normal
    ax = axes[1, 0]
    stats.probplot(y, dist="norm", plot=ax)
    ax.set_title("(c) Q-Q plot vs Normal")
    # Restyle scipy's defaults
    line, fit = ax.get_lines()
    line.set_markerfacecolor(PAL["primary"])
    line.set_markeredgecolor(PAL["primary"])
    line.set_markersize(4)
    fit.set_color(PAL["accent"])

    # (d) Sign-log transform: preserves sign and handles heavy tails on both sides
    ax = axes[1, 1]
    y_symlog = np.sign(y) * np.log1p(np.abs(y))
    ax.hist(y_symlog, bins=50, color=PAL["positive"], alpha=0.75,
            edgecolor="white", density=True)
    ax.set_xlabel("sign(r) * log(1+|r|)  —  sign-log transformed")
    ax.set_ylabel("density")
    ax.set_title(f"(d) Sign-log transform  "
                 f"(skew {y.skew():.2f} -> {pd.Series(y_symlog).skew():.2f})")
    ax.axvline(0, color=PAL["muted"], linewidth=0.8)

    fig.suptitle("first_day_return — distribution overview", fontsize=13, y=1.00)
    fig.tight_layout()
    save_fig(fig, "01_target_distribution", FIG_DIR)
    plt.close(fig)
    print(f"  Saved: {FIG_DIR}/01_target_distribution.(png|pdf)")


# ============================================================
# 2. TEMPORAL ANALYSIS — HOW THE TARGET EVOLVES BY YEAR
# ============================================================
def bootstrap_ci(x, stat_func, n_boot=2000, alpha=0.05, seed=42):
    """Percentile bootstrap CI for any statistic. Reproducible via seed."""
    rng = np.random.default_rng(seed)
    x = np.asarray(x)
    if len(x) == 0:
        return np.nan, np.nan
    idx = rng.integers(0, len(x), size=(n_boot, len(x)))
    boot = np.array([stat_func(x[row]) for row in idx])
    return np.quantile(boot, alpha / 2), np.quantile(boot, 1 - alpha / 2)


def analyse_temporal(df):
    print("\n" + "=" * 72)
    print("2. TEMPORAL STRUCTURE — median / mean / positive share by year")
    hr()

    rows = []
    for yr, g in df.groupby("year"):
        y = g["first_day_return"].dropna().values
        med_lo, med_hi   = bootstrap_ci(y, np.median)
        mean_lo, mean_hi = bootstrap_ci(y, np.mean)
        rows.append({
            "year":         int(yr),
            "n":            len(y),
            "mean":         float(np.mean(y)),
            "mean_ci_lo":   mean_lo,
            "mean_ci_hi":   mean_hi,
            "median":       float(np.median(y)),
            "median_ci_lo": med_lo,
            "median_ci_hi": med_hi,
            "std":          float(np.std(y, ddof=1)) if len(y) > 1 else np.nan,
            "positive_share": float((y > 0).mean()),
            "min":          float(np.min(y)),
            "max":          float(np.max(y)),
        })
    temp_df = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
    print(temp_df.round(3).to_string(index=False))
    temp_df.to_csv(os.path.join(TAB_DIR, "01_target_by_year.csv"), index=False)
    print(f"\n  Saved: {TAB_DIR}/01_target_by_year.csv")

    # ---- 4-panel temporal figure ----
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))

    # (a) IPO count by year
    ax = axes[0, 0]
    ax.bar(temp_df["year"], temp_df["n"],
           color=PAL["primary"], alpha=0.8, edgecolor="white")
    for _, r in temp_df.iterrows():
        ax.text(r["year"], r["n"] + 1, str(int(r["n"])),
                ha="center", fontsize=9)
    ax.set_xlabel("year")
    ax.set_ylabel("IPO count")
    ax.set_title("(a) IPO listings per year")

    # (b) Median with bootstrap CI
    ax = axes[0, 1]
    ax.errorbar(temp_df["year"], temp_df["median"],
                yerr=[temp_df["median"] - temp_df["median_ci_lo"],
                      temp_df["median_ci_hi"] - temp_df["median"]],
                fmt="o-", color=PAL["primary"], capsize=4, linewidth=1.5)
    ax.axhline(0, color=PAL["muted"], linewidth=0.8)
    ax.set_xlabel("year")
    ax.set_ylabel("median first_day_return")
    ax.set_title("(b) Median first-day return by year (95% CI, bootstrap)")

    # (c) Mean with bootstrap CI
    ax = axes[1, 0]
    ax.errorbar(temp_df["year"], temp_df["mean"],
                yerr=[temp_df["mean"] - temp_df["mean_ci_lo"],
                      temp_df["mean_ci_hi"] - temp_df["mean"]],
                fmt="o-", color=PAL["accent"], capsize=4, linewidth=1.5)
    ax.axhline(0, color=PAL["muted"], linewidth=0.8)
    ax.set_xlabel("year")
    ax.set_ylabel("mean first_day_return")
    ax.set_title("(c) Mean first-day return by year (95% CI, bootstrap)")

    # (d) Positive-return share by year
    ax = axes[1, 1]
    ax.bar(temp_df["year"], temp_df["positive_share"],
           color=PAL["positive"], alpha=0.8, edgecolor="white")
    for _, r in temp_df.iterrows():
        ax.text(r["year"], r["positive_share"] + 0.02,
                f'{r["positive_share"]:.0%}', ha="center", fontsize=9)
    ax.axhline(0.5, color=PAL["muted"], linewidth=0.8, linestyle="--")
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("year")
    ax.set_ylabel("share of IPOs with positive return")
    ax.set_title("(d) Positive-return share by year")

    fig.suptitle("first_day_return — temporal structure", fontsize=13, y=1.00)
    fig.tight_layout()
    save_fig(fig, "01_target_temporal", FIG_DIR)
    plt.close(fig)
    print(f"  Saved: {FIG_DIR}/01_target_temporal.(png|pdf)")


# ============================================================
# 3. REGIME SHIFT — PRE-2024 vs 2024+
# ============================================================
def analyse_regime(df):
    print("\n" + "=" * 72)
    print("3. REGIME SHIFT — pre-2024 (2019-2023) vs 2024+ (2024-2026)")
    hr()
    y_all = df["first_day_return"]
    early = y_all[df["year"] <= 2023].dropna()
    late  = y_all[df["year"] >= 2024].dropna()

    print(f"  Pre-2024 (2019-2023):  n={len(early)}")
    print(f"    mean={early.mean():.4f}, median={early.median():.4f}, "
          f"sd={early.std():.4f}")
    print(f"  Post-2024 (2024-2026): n={len(late)}")
    print(f"    mean={late.mean():.4f},  median={late.median():.4f}, "
          f"sd={late.std():.4f}")

    # Distributional tests
    u_stat, u_p = stats.mannwhitneyu(early, late, alternative="two-sided")
    print(f"\n  Mann-Whitney U  (do the distributions differ?):"
          f"  U={u_stat:.0f}, p={u_p:.4e}")
    print(f"    -> {'DIFFERENT distributions (regime shift present)' if u_p < 0.05 else 'no significant difference'}")

    m_stat, m_p, *_ = stats.median_test(early, late)
    print(f"  Mood's median test (do the medians differ?):"
          f"  stat={m_stat:.2f}, p={m_p:.4e}")

    # ---- Figure ----
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    ax = axes[0]
    bins = np.linspace(y_all.min(), y_all.max(), 50)
    ax.hist(early, bins=bins, alpha=0.55, color=PAL["primary"],
            label=f"2019-2023 (n={len(early)})", density=True)
    ax.hist(late, bins=bins, alpha=0.55, color=PAL["accent"],
            label=f"2024-2026 (n={len(late)})", density=True)
    ax.axvline(0, color=PAL["muted"], linewidth=0.8)
    ax.set_xlabel("first_day_return")
    ax.set_ylabel("density")
    ax.set_title(f"(a) Distributions by regime  (Mann-Whitney p={u_p:.2e})")
    ax.legend(frameon=False)

    # ECDFs — usually the clearest way to show a distribution shift
    ax = axes[1]
    for label, series, colour in [
        (f"2019-2023 (n={len(early)})", early, PAL["primary"]),
        (f"2024-2026 (n={len(late)})",  late,  PAL["accent"]),
    ]:
        s = np.sort(series.values)
        ax.plot(s, np.arange(1, len(s) + 1) / len(s),
                color=colour, linewidth=2, label=label)
    ax.axvline(0, color=PAL["muted"], linewidth=0.8)
    ax.axhline(0.5, color=PAL["muted"], linewidth=0.5, linestyle=":")
    ax.set_xlabel("first_day_return")
    ax.set_ylabel("cumulative probability")
    ax.set_title("(b) ECDF by regime")
    ax.legend(frameon=False)

    fig.suptitle("Regime comparison: pre-2024 vs 2024+",
                 fontsize=13, y=1.02)
    fig.tight_layout()
    save_fig(fig, "01_target_regime", FIG_DIR)
    plt.close(fig)
    print(f"\n  Saved: {FIG_DIR}/01_target_regime.(png|pdf)")


# ============================================================
# 4. EXTREME CASES — TOP 10 GAINERS / LOSERS
# ============================================================
def analyse_extremes(df):
    print("\n" + "=" * 72)
    print("4. EXTREME CASES — top 10 gainers and losers")
    hr()
    candidate_cols = ["company", "year", "listing_date", "first_day_return",
                      "issue_price", "gmp_value", "sub_total"]
    show_cols = [c for c in candidate_cols if c in df.columns]

    top = df.nlargest(10, "first_day_return")[show_cols].copy()
    bot = df.nsmallest(10, "first_day_return")[show_cols].copy()

    print("\n  Top 10 gainers:")
    print(top.to_string(index=False))
    print("\n  Top 10 losers:")
    print(bot.to_string(index=False))

    top.to_csv(os.path.join(TAB_DIR, "01_target_top10_gainers.csv"), index=False)
    bot.to_csv(os.path.join(TAB_DIR, "01_target_top10_losers.csv"), index=False)
    print(f"\n  Saved: {TAB_DIR}/01_target_top10_gainers.csv")
    print(f"  Saved: {TAB_DIR}/01_target_top10_losers.csv")


# ============================================================
# 5. OPEN vs CLOSE FIRST-DAY RETURN
# ============================================================
def analyse_open_vs_close(df):
    if "first_day_open_return" not in df.columns:
        print("\n  (first_day_open_return column not present, skipping)")
        return
    print("\n" + "=" * 72)
    print("5. OPEN vs CLOSE first-day return")
    hr()
    both = df[["first_day_open_return", "first_day_return"]].dropna()
    x, y = both["first_day_open_return"], both["first_day_return"]
    r = both.corr().iloc[0, 1]
    diff = y - x
    print(f"  Correlation (open vs close):  r={r:.3f}   (n={len(both)})")
    print(f"  Intraday move (close − open):")
    print(f"    mean={diff.mean():.4f}, median={diff.median():.4f}, "
          f"sd={diff.std():.4f}")
    print(f"    positive share (close > open): {(diff > 0).mean():.2%}")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    ax = axes[0]
    ax.scatter(x, y, alpha=0.4, s=20, color=PAL["primary"], edgecolors="none")
    lo, hi = min(x.min(), y.min()), max(x.max(), y.max())
    ax.plot([lo, hi], [lo, hi], color=PAL["neutral"],
            linestyle="--", linewidth=1, label="y = x")
    ax.axhline(0, color=PAL["muted"], linewidth=0.6)
    ax.axvline(0, color=PAL["muted"], linewidth=0.6)
    ax.set_xlabel("first_day_open_return")
    ax.set_ylabel("first_day_return  (close)")
    ax.set_title(f"(a) Open vs close first-day return  (r={r:.3f})")
    ax.legend(frameon=False)

    ax = axes[1]
    ax.hist(diff, bins=50, color=PAL["positive"], alpha=0.75, edgecolor="white")
    ax.axvline(0, color=PAL["muted"], linewidth=0.8)
    ax.axvline(diff.mean(), color=PAL["accent"], linestyle=":",
               label=f"mean = {diff.mean():.3f}")
    ax.set_xlabel("close − open (intraday move)")
    ax.set_ylabel("count")
    ax.set_title("(b) Intraday move distribution")
    ax.legend(frameon=False)

    fig.tight_layout()
    save_fig(fig, "01_target_open_vs_close", FIG_DIR)
    plt.close(fig)
    print(f"  Saved: {FIG_DIR}/01_target_open_vs_close.(png|pdf)")


# ============================================================
# MAIN
# ============================================================
def main():
    df = load()
    analyse_distribution(df)
    analyse_temporal(df)
    analyse_regime(df)
    analyse_extremes(df)
    analyse_open_vs_close(df)

    print("\n" + "#" * 72)
    print("# EDA 01 COMPLETE")
    print("#" * 72)
    print(f"  Figures: {FIG_DIR}/")
    print(f"  Tables:  {TAB_DIR}/")
    print("  Next up: 02_univariate_features.py "
          "(distributions of raw predictors)")


if __name__ == "__main__":
    main()