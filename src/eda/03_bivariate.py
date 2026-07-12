"""
EDA STEP 03: Bivariate analysis
================================
Feature-feature and feature-target relationships. Nothing engineered here;
we analyse how predictors relate to each other and to first_day_return.

WHAT THIS ANSWERS
  - Which predictors are correlated with each other (redundancy signal —
    guides whether we combine them into ratios or drop duplicates)?
  - Which predictors correlate with first_day_return (what actually
    predicts)?
  - Are those relationships linear or non-linear (does log or a ratio
    help), visible in LOWESS-smoothed scatter plots?
  - Do relationships change between the GMP-available subset (n≈398) and
    the GMP-absent subset (n≈21)? This matters for the thesis argument
    that LLM risk features should add value especially when GMP is
    missing.

WHAT IT DOES NOT DO
  - No temporal / regime-conditional analysis (that is script 04).
  - No feature engineering.

METHODOLOGY
  Spearman rank correlation is used throughout as the primary metric
  because (a) the target and many predictors are heavily right-skewed
  (EDA 02), and Spearman is invariant to monotonic transforms, and (b)
  it is robust to outliers. Pearson is reported alongside for reference.

INPUTS
  data/processed/master_ipo_dataset.csv

OUTPUTS
  reports/figures/eda/03_correlation_matrix.(png|pdf)
  reports/figures/eda/03_target_correlation_ranking.(png|pdf)
  reports/figures/eda/03_top_predictor_scatters.(png|pdf)
  reports/figures/eda/03_gmp_stratified_correlations.(png|pdf)
  reports/tables/eda/03_correlation_matrix_spearman.csv
  reports/tables/eda/03_top_pairwise_correlations.csv
  reports/tables/eda/03_target_correlation_ranking.csv
  reports/tables/eda/03_gmp_stratified_correlations.csv

DEPENDENCIES
  Requires `statsmodels` for the LOWESS smoother. If not installed,
  the scatter figure is still produced but without smoothing lines.
  Install with:  pip3 install statsmodels

RUN
  python3 src/eda/03_bivariate.py
  (run from the project root)
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

try:
    from statsmodels.nonparametric.smoothers_lowess import lowess
    HAS_LOWESS = True
except ImportError:
    HAS_LOWESS = False

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
# PREDICTOR GROUPS  (order matters — used for heatmap layout)
# ============================================================
GROUPED_PREDICTORS = [
    ("structural", ["issue_price", "total_issue_size", "fresh_issue", "ofs",
                    "lot_size", "face_value"]),
    ("demand",     ["sub_total"]),
    ("gmp",        ["gmp_value", "gmp_available"]),
    ("financials", ["revenue", "profit", "assets", "net_worth", "borrowing"]),
    ("broker",     ["brokers_subscribe", "brokers_avoid"]),
    ("market",     ["nifty_close", "vix_close", "nifty_7d_return",
                    "nifty_30d_return"]),
]
ALL_PREDICTORS = [v for _, vs in GROUPED_PREDICTORS for v in vs]
TARGET = "first_day_return"


def hr(char="-"):
    print(char * 72)


# ============================================================
# LOAD
# ============================================================
def load():
    hr("=")
    print("EDA 03: BIVARIATE ANALYSIS")
    hr("=")
    if not HAS_LOWESS:
        print("  [warn] statsmodels not installed — LOWESS smoothers "
              "will be omitted from scatter plots.")
        print("         Install with:  pip3 install statsmodels")
    if not os.path.exists(MASTER):
        raise FileNotFoundError(
            f"{MASTER} not found. Run this script from the project root.")
    df = pd.read_csv(MASTER)
    df["listing_date"] = pd.to_datetime(df["listing_date"])
    print(f"  Loaded {len(df)} IPOs from {MASTER}")
    print(f"  Predictors: {len(ALL_PREDICTORS)}, target: {TARGET}")
    return df


# ============================================================
# 1. FEATURE-FEATURE CORRELATION MATRIX
# ============================================================
def correlation_matrix(df):
    print("\n" + "=" * 72)
    print("1. FEATURE-FEATURE CORRELATION MATRIX  (Spearman)")
    hr()
    print("  Spearman used because the target and many predictors are")
    print("  heavily skewed. Lower triangle only shown to avoid visual")
    print("  redundancy.")
    print()

    cols = ALL_PREDICTORS + [TARGET]
    corr = df[cols].corr(method='spearman')
    corr.round(4).to_csv(
        os.path.join(TAB_DIR, "03_correlation_matrix_spearman.csv"))

    # Mask upper triangle for display
    mask = np.triu(np.ones_like(corr, dtype=bool), k=1)
    display_corr = corr.where(~mask)

    fig, ax = plt.subplots(figsize=(13, 11))
    im = ax.imshow(display_corr.values.astype(float),
                   cmap='RdBu_r', vmin=-1, vmax=1, aspect='auto')

    ax.set_xticks(range(len(cols)))
    ax.set_yticks(range(len(cols)))
    ax.set_xticklabels(cols, rotation=45, ha='right', fontsize=8)
    ax.set_yticklabels(cols, fontsize=8)

    # Group separators (thin black lines between predictor groups)
    boundaries = np.cumsum([len(vs) for _, vs in GROUPED_PREDICTORS])
    for b in boundaries[:-1]:
        ax.axvline(b - 0.5, color='black', linewidth=0.5, alpha=0.4)
        ax.axhline(b - 0.5, color='black', linewidth=0.5, alpha=0.4)

    # Annotate cells with correlation values
    for i in range(len(cols)):
        for j in range(len(cols)):
            if j > i:
                continue
            v = display_corr.iloc[i, j]
            if pd.notna(v):
                col_txt = 'white' if abs(v) > 0.5 else 'black'
                ax.text(j, i, f"{v:.2f}", ha='center', va='center',
                        color=col_txt, fontsize=6.5)

    plt.colorbar(im, ax=ax, label='Spearman correlation', shrink=0.7)
    ax.set_title("Feature-feature correlation matrix "
                 "(Spearman, lower triangle)")
    ax.grid(False)
    fig.tight_layout()
    save_fig(fig, "03_correlation_matrix", FIG_DIR)
    plt.close(fig)
    print(f"  Saved: {FIG_DIR}/03_correlation_matrix.(png|pdf)")
    print(f"  Saved: {TAB_DIR}/03_correlation_matrix_spearman.csv")

    # Report top pairwise correlations (predictor-predictor only)
    pred_corr = corr.drop(TARGET, axis=0).drop(TARGET, axis=1)
    pairs = []
    for i in range(len(ALL_PREDICTORS)):
        for j in range(i):
            pairs.append({
                "var1": ALL_PREDICTORS[i],
                "var2": ALL_PREDICTORS[j],
                "spearman": float(pred_corr.iloc[i, j]),
            })
    pairs_df = pd.DataFrame(pairs)
    pairs_df["abs_corr"] = pairs_df["spearman"].abs()
    top_pairs = pairs_df.sort_values("abs_corr", ascending=False).head(15)

    print("\n  Top 15 pairwise correlations by |value|:")
    print(top_pairs[["var1", "var2", "spearman"]].round(3).to_string(index=False))
    top_pairs.to_csv(
        os.path.join(TAB_DIR, "03_top_pairwise_correlations.csv"),
        index=False)
    print(f"\n  Saved: {TAB_DIR}/03_top_pairwise_correlations.csv")


# ============================================================
# 2. FEATURE-TARGET CORRELATION RANKING
# ============================================================
def target_correlation_ranking(df):
    print("\n" + "=" * 72)
    print("2. FEATURE-TARGET CORRELATION RANKING")
    hr()
    print(f"  Target: {TARGET}")
    print("  Metric: Spearman (rank-based, robust). Pearson reported "
          "alongside for reference.")
    print()

    rows = []
    for col in ALL_PREDICTORS:
        both = df[[col, TARGET]].dropna()
        n = len(both)
        if n < 3:
            continue
        sp_r = float(both.corr(method='spearman').iloc[0, 1])
        pe_r = float(both.corr(method='pearson').iloc[0, 1])
        try:
            _, sp_p = stats.spearmanr(both[col], both[TARGET])
            sp_p = float(sp_p)
        except Exception:
            sp_p = np.nan
        rows.append({
            "variable":    col,
            "n":           n,
            "spearman":    sp_r,
            "spearman_p":  sp_p,
            "pearson":     pe_r,
            "abs_spearman": abs(sp_r),
        })
    rank_df = pd.DataFrame(rows).sort_values("abs_spearman",
                                             ascending=False)
    print(rank_df.round(4).to_string(index=False))
    rank_df.to_csv(
        os.path.join(TAB_DIR, "03_target_correlation_ranking.csv"),
        index=False)
    print(f"\n  Saved: {TAB_DIR}/03_target_correlation_ranking.csv")

    # Horizontal bar chart, sorted by spearman value, coloured by sign
    r = rank_df.sort_values("spearman")
    colors = [PAL["positive"] if v > 0 else PAL["negative"]
              for v in r["spearman"]]
    fig, ax = plt.subplots(figsize=(10, max(5, 0.4 * len(r))))
    ax.barh(r["variable"], r["spearman"], color=colors,
            alpha=0.85, edgecolor='white')
    ax.axvline(0, color='black', linewidth=0.5)
    for x in [-0.3, -0.1, 0.1, 0.3]:
        ax.axvline(x, color=PAL["muted"], linestyle=':', linewidth=0.5)
    ax.set_xlabel("Spearman correlation with first_day_return")
    ax.set_title("Feature-target correlation ranking "
                 "(Spearman; dashed lines at ±0.1 and ±0.3)")
    fig.tight_layout()
    save_fig(fig, "03_target_correlation_ranking", FIG_DIR)
    plt.close(fig)
    print(f"  Saved: {FIG_DIR}/03_target_correlation_ranking.(png|pdf)")

    return rank_df


# ============================================================
# 3. TOP-PREDICTOR SCATTER PLOTS
# ============================================================
def top_predictor_scatters(df, rank_df):
    print("\n" + "=" * 72)
    print("3. TOP-PREDICTOR SCATTER PLOTS  (raw vs target, LOWESS)")
    hr()
    top_n = 6
    top_vars = rank_df.head(top_n)["variable"].tolist()
    print(f"  Top {top_n} predictors by |Spearman|: {top_vars}")

    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    axes = axes.flatten()

    for i, var in enumerate(top_vars):
        ax = axes[i]
        both = df[[var, TARGET]].dropna()
        x = both[var].values
        y = both[TARGET].values
        sp_r = float(both.corr(method='spearman').iloc[0, 1])

        ax.scatter(x, y, alpha=0.35, s=15,
                   color=PAL["primary"], edgecolors='none')
        ax.axhline(0, color=PAL["muted"], linewidth=0.5)

        if HAS_LOWESS and len(x) > 20:
            smoothed = lowess(y, x, frac=0.5, return_sorted=True)
            ax.plot(smoothed[:, 0], smoothed[:, 1],
                    color=PAL["accent"], linewidth=2, label='LOWESS')
            ax.legend(frameon=False, fontsize=8, loc='upper left')

        ax.set_xlabel(var)
        ax.set_ylabel(TARGET)
        ax.set_title(f"{var}   (Spearman ρ = {sp_r:.3f}, n={len(both)})",
                     fontsize=10)

    for j in range(top_n, len(axes)):
        axes[j].axis('off')

    fig.suptitle("Top predictors vs first_day_return "
                 "(scatter + LOWESS in red)", fontsize=13, y=1.00)
    fig.tight_layout()
    save_fig(fig, "03_top_predictor_scatters", FIG_DIR)
    plt.close(fig)
    print(f"  Saved: {FIG_DIR}/03_top_predictor_scatters.(png|pdf)")


# ============================================================
# 4. GMP-STRATIFIED ANALYSIS
# ============================================================
def gmp_stratified_analysis(df):
    print("\n" + "=" * 72)
    print("4. GMP-STRATIFIED CORRELATIONS  (available vs absent)")
    hr()
    print("  Do other predictors carry more of the signal when GMP is")
    print("  missing? Motivates the thesis argument that risk features")
    print("  should add value especially in the GMP-absent slice.")
    print()

    avail_mask  = df["gmp_available"] == 1
    absent_mask = df["gmp_available"] == 0
    n_avail  = int(avail_mask.sum())
    n_absent = int(absent_mask.sum())

    print(f"  Subsets: gmp_available (n={n_avail}), "
          f"gmp_absent (n={n_absent}).")
    if n_absent < 20:
        print("  [note] gmp_absent subset is very small; correlations there "
              "have wide confidence intervals — read comparatively, not "
              "as significance tests.")
    print()

    # Exclude gmp_value and gmp_available themselves from the comparison
    compare_vars = [v for v in ALL_PREDICTORS
                    if v not in ("gmp_value", "gmp_available")]

    avail_label  = f"gmp_available (n={n_avail})"
    absent_label = f"gmp_absent (n={n_absent})"

    rows = []
    for var in compare_vars:
        row = {"variable": var}
        for label, mask in [(avail_label, avail_mask),
                            (absent_label, absent_mask)]:
            both = df.loc[mask, [var, TARGET]].dropna()
            if len(both) < 5:
                row[label] = np.nan
            else:
                row[label] = float(
                    both.corr(method='spearman').iloc[0, 1])
        rows.append(row)

    strat_df = pd.DataFrame(rows)
    strat_df = strat_df.sort_values(
        avail_label,
        key=lambda s: s.abs().fillna(-1),
        ascending=False,
    )
    print(strat_df.round(3).to_string(index=False))
    strat_df.to_csv(
        os.path.join(TAB_DIR, "03_gmp_stratified_correlations.csv"),
        index=False)
    print(f"\n  Saved: {TAB_DIR}/03_gmp_stratified_correlations.csv")

    # Side-by-side bar chart
    r = strat_df.copy()
    fig, ax = plt.subplots(figsize=(11, max(5, 0.4 * len(r))))
    y = np.arange(len(r))
    ax.barh(y - 0.2, r[avail_label].fillna(0), height=0.4,
            color=PAL["primary"], alpha=0.85, label=avail_label)
    ax.barh(y + 0.2, r[absent_label].fillna(0), height=0.4,
            color=PAL["accent"],  alpha=0.85, label=absent_label)
    ax.axvline(0, color='black', linewidth=0.5)
    for x in [-0.3, -0.1, 0.1, 0.3]:
        ax.axvline(x, color=PAL["muted"], linestyle=':', linewidth=0.5)
    ax.set_yticks(y)
    ax.set_yticklabels(r["variable"])
    ax.set_xlabel("Spearman correlation with first_day_return")
    ax.set_title("Feature-target correlations by GMP availability subset")
    ax.legend(frameon=False, loc='lower right')
    fig.tight_layout()
    save_fig(fig, "03_gmp_stratified_correlations", FIG_DIR)
    plt.close(fig)
    print(f"  Saved: {FIG_DIR}/03_gmp_stratified_correlations.(png|pdf)")


# ============================================================
# MAIN
# ============================================================
def main():
    df = load()
    correlation_matrix(df)
    rank_df = target_correlation_ranking(df)
    top_predictor_scatters(df, rank_df)
    gmp_stratified_analysis(df)

    print("\n" + "#" * 72)
    print("# EDA 03 COMPLETE")
    print("#" * 72)
    print(f"  Figures: {FIG_DIR}/")
    print(f"  Tables:  {TAB_DIR}/")
    print("  Next up: 04_temporal_and_regime.py "
          "(feature drift over time, regime-conditional relationships)")


if __name__ == "__main__":
    main()