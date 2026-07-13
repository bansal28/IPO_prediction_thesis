"""
FEATURE ENGINEERING: numeric feature construction
==================================================
Reads the cleaned 416-IPO master and produces the numeric feature
matrix used for modelling.

INPUT
  data/processed/master_ipo_dataset.csv      (416 IPOs × 29 cols)

OUTPUT
  data/features/features_numeric.csv         (416 IPOs × 23 cols)

DESIGN RATIONALE

Every choice below is based on either (a) properties of the pooled
distribution / structural facts about the SEBI regime, or (b) EDA
findings that do NOT rely on isolating the test slice (2025-2026).

  1. Log-only transforms for right-skewed non-negative variables.
     Providing raw + log would create linear-model multicollinearity
     for zero benefit to XGBoost. Log-only works cleanly for both.
     Skewness reductions (from EDA 02):
        revenue           20.0 → 0.29
        borrowing         13.4 → -0.21
        assets            10.7 → 0.57
        fresh_issue        7.2 → 0.66
        ofs                6.5 → 0.37
        total_issue_size   6.4 → 1.04
        issue_price        1.9 → -0.33
        sub_total          2.0 → -0.07

  2. `lot_size` DROPPED (Spearman ρ = -0.996 with issue_price).
     Structural redundancy from SEBI's ~₹15,000 minimum retail
     application rule — not a data-driven observation about the
     test slice.

  3. `face_value` DROPPED. Distribution {1.0: 65, 2.0: 80, 4.0: 1,
     5.0: 48, 10.0: 222} — the "4.0" category has one observation
     (Nazara Technologies), which is a degenerate categorical
     encoding. Structural argument, not test-slice-dependent.

  4. Deal size composition. Instead of three redundant deal-size
     variables (fresh_issue, ofs, total_issue_size all pairwise
     0.80-0.82), keep total_issue_size_log1p for scale and
     ofs_ratio = ofs / (fresh + ofs) for composition. Missing
     components treated as implicit zero (structural: pure-fresh
     IPOs have no ofs, pure-OFS IPOs have no fresh_issue).

  5. Also retain fresh_issue_log1p and ofs_log1p in addition to
     the composite. This is a deliberate choice: XGBoost may find
     interactions the composite misses. For linear baselines, this
     introduces multicollinearity — modelling scripts can drop the
     raw log-scale versions at that point. Feature engineering
     should not pre-decide model-family-specific pruning.

  6. gmp_return = gmp_value / issue_price. Raw gmp_value is
     rupee-denominated so its meaning depends on issue price
     (₹50 GMP is 50% of a ₹100 issue but 5% of a ₹1,000 issue).
     Dimensionless normalisation makes issues comparable.
     `gmp_available` retained as a binary flag because the
     GMP-absent slice behaves differently (EDA 03).

  7. Financial ratios (composition) alongside financial scale:
        profit_margin    = profit / revenue      (profitability)
        return_on_assets = profit / assets       (efficiency)
        debt_to_equity   = borrowing / net_worth (leverage)
     Ratios cancel scale confounds within the financial-size
     cluster (revenue/profit/assets/net_worth/borrowing pairwise
     0.5-0.86 correlated). Sign-mixed inputs (profit, net_worth)
     that can't log1p directly enter naturally via ratios.

  8. Non-positive net_worth. debt_to_equity set to NaN and
     `negative_networth_flag` set to 1 for the 5 IPOs with
     net_worth ≤ 0. A highly indebted solvent firm and an
     insolvent firm can produce similarly-signed D/E ratios of
     similar magnitude, so the flag conditions the model on
     insolvency separately from leverage magnitude.

  9. Broker sentiment: keep raw `brokers_subscribe` (well-behaved,
     skew 0.75, graded, median 5). Add `any_avoid_flag` because
     `brokers_avoid` is a step function — 307/416 IPOs (74%) have
     zero avoids. Also retain raw `brokers_avoid` alongside the
     flag: for XGBoost the graded count adds information; linear
     baselines can drop the raw and keep the flag at model time.

 10. Market context (nifty_close, vix_close, nifty_7d_return,
     nifty_30d_return) all retained raw. VIX skew of 2.4 could
     log1p but log obscures its natural percent-volatility
     interpretation. These features also carry the market-regime
     signal (Nifty peaked Sept 2024 and corrected 15% by Feb 2025,
     as visible in raw_nifty50_daily.csv), so no separate regime
     dummy is added.

 11. NO regime dummy. The IPO first-day return distribution
     shifts around late 2024 / early 2025 (visible pooled), and
     this shift is driven by real market conditions (the Nifty
     correction from September 2024). Those market conditions
     enter the model via the four Nifty/VIX features above — a
     binary regime dummy would be redundant with them.

     Earlier drafts of this script included regime_post_2024
     anchored at 2025-01-01. That anchor date was chosen because
     it produced the strongest Mann-Whitney p-value in a
     train-vs-test EDA test — which used the test slice to make
     a feature-engineering decision. Removed.

WHAT THIS SCRIPT DOES NOT DO
  - No imputation. XGBoost handles NaN natively. Linear baselines
    should impute at model time using training-set statistics
    only, to avoid leaking test-period info into inputs.
  - No standardisation. Same rationale.
  - No train/val/test split. That's a modelling concern; this
    script produces one file with a `year` column that modelling
    scripts filter on.

RUN
  python3 src/processing/02_feature_engineering.py
  (from the project root)
"""

import os
import numpy as np
import pandas as pd


# ============================================================
# PATHS
# ============================================================
MASTER   = "data/processed/master_ipo_dataset.csv"
OUT_DIR  = "data/features"
OUT_FILE = os.path.join(OUT_DIR, "features_numeric.csv")
os.makedirs(OUT_DIR, exist_ok=True)


def hr(char="-"):
    print(char * 72)


# ============================================================
# LOAD
# ============================================================
def load():
    hr("=")
    print("FEATURE ENGINEERING: numeric feature construction")
    hr("=")
    if not os.path.exists(MASTER):
        raise FileNotFoundError(
            f"{MASTER} not found. Run this script from the project root.")
    df = pd.read_csv(MASTER)
    df["listing_date"] = pd.to_datetime(df["listing_date"])
    print(f"  Loaded {len(df)} IPOs from {MASTER}")
    print(f"  Master columns: {df.shape[1]}")
    if len(df) != 416:
        print(f"  [WARN] expected 416 rows, got {len(df)}")
    return df


# ============================================================
# ENGINEER
# ============================================================
def engineer(df):
    """Construct the feature matrix. See module docstring for the
    evidence-based justification of every choice below."""
    f = pd.DataFrame(index=df.index)

    # --------------------------------------------------------
    # IDENTIFIERS  (kept for stratified reporting and the
    # temporal-split filter, not treated as features)
    # --------------------------------------------------------
    f["company"]          = df["company"]
    f["listing_date"]     = df["listing_date"]
    f["year"]             = df["year"]
    f["first_day_return"] = df["first_day_return"]

    # --------------------------------------------------------
    # STRUCTURAL
    # `lot_size` DROPPED (ρ = -0.996 with issue_price).
    # `face_value` DROPPED (single-observation "4.0" category).
    # `issue_price` in log form only (raw + log would be
    # linear-model multicollinearity).
    # --------------------------------------------------------
    f["issue_price_log1p"] = np.log1p(df["issue_price"])

    # --------------------------------------------------------
    # DEAL SIZE — scale + composition + raw log-scale components
    # (see rationale note 5 in the docstring for why we keep all
    # three; linear baselines will need to drop redundancy)
    # --------------------------------------------------------
    f["total_issue_size_log1p"] = np.log1p(df["total_issue_size"])
    f["fresh_issue_log1p"]      = np.log1p(df["fresh_issue"])
    f["ofs_log1p"]              = np.log1p(df["ofs"])

    # ofs_ratio: pure-fresh → 0, pure-OFS → 1, mixed → ofs / (fresh + ofs)
    fresh_filled = df["fresh_issue"].fillna(0)
    ofs_filled   = df["ofs"].fillna(0)
    denom        = fresh_filled + ofs_filled
    f["ofs_ratio"] = np.where(
        denom > 0,
        ofs_filled / denom,
        np.nan,   # guard against the impossible case of both zero
    )

    # --------------------------------------------------------
    # DEMAND
    # sub_total in log form only (skew 2.0 → -0.07).
    # gmp_return: dimensionless, sign-preserving (raw gmp_value
    # can be negative so log1p not applicable).
    # gmp_available: binary flag (21 IPOs have no GMP).
    # --------------------------------------------------------
    f["sub_total_log1p"] = np.log1p(df["sub_total"])
    f["gmp_return"]      = df["gmp_value"] / df["issue_price"]
    f["gmp_available"]   = df["gmp_available"]

    # --------------------------------------------------------
    # FINANCIAL — SCALE (log-transformed levels)
    # revenue, assets, borrowing all heavily right-skewed;
    # log1p normalizes them (see rationale note 1).
    # --------------------------------------------------------
    f["revenue_log1p"]   = np.log1p(df["revenue"].clip(lower=0))
    f["assets_log1p"]    = np.log1p(df["assets"].clip(lower=0))
    f["borrowing_log1p"] = np.log1p(df["borrowing"].clip(lower=0))

    # --------------------------------------------------------
    # FINANCIAL — COMPOSITION (dimensionless ratios)
    # Ratios cancel scale confounds within the financial cluster.
    # Denominators guarded with replace(0, NaN) to avoid inf.
    # --------------------------------------------------------
    f["profit_margin"]    = df["profit"] / df["revenue"].replace(0, np.nan)
    f["return_on_assets"] = df["profit"] / df["assets"].replace(0, np.nan)

    # debt_to_equity: non-positive net_worth → NaN AND flag set to 1
    nonpositive_nw = df["net_worth"] <= 0
    f["debt_to_equity"] = np.where(
        nonpositive_nw,
        np.nan,
        df["borrowing"] / df["net_worth"].replace(0, np.nan),
    )
    f["negative_networth_flag"] = nonpositive_nw.astype(int)

    # --------------------------------------------------------
    # BROKER SENTIMENT
    # brokers_subscribe: raw, well-behaved (skew 0.75, graded).
    # brokers_avoid: raw kept AND binary flag added — 74% zeros
    #   makes the graded count nearly binary but XGBoost may use
    #   the graded distinction. Linear baselines drop raw at
    #   model time.
    # --------------------------------------------------------
    f["brokers_subscribe"] = df["brokers_subscribe"]
    f["brokers_avoid"]     = df["brokers_avoid"]
    f["any_avoid_flag"]    = (df["brokers_avoid"] > 0).astype(int)

    # --------------------------------------------------------
    # MARKET CONTEXT
    # All four kept raw. Together these carry the market-regime
    # signal (Nifty correction Q4 2024 - Q1 2025 visible via
    # nifty_close level, elevated VIX, negative trailing returns).
    # No separate regime dummy — the market features carry it.
    # --------------------------------------------------------
    f["nifty_close"]      = df["nifty_close"]
    f["vix_close"]        = df["vix_close"]
    f["nifty_7d_return"]  = df["nifty_7d_return"]
    f["nifty_30d_return"] = df["nifty_30d_return"]

    return f


# ============================================================
# VALIDATE
# ============================================================
def validate(df, f):
    """Sanity-check the engineered feature matrix against
    expectations derived from the raw data."""
    print("\n" + "=" * 72)
    print("VALIDATION")
    hr()

    # -- shape ------------------------------------------------
    print(f"  Row count       : {len(f)}   (expected 416)")
    assert len(f) == len(df), "row count mismatch"
    print(f"  Column count    : {f.shape[1]}")
    n_features = f.shape[1] - 4
    print(f"  Feature columns : {n_features}  "
          f"(excluding company, listing_date, year, first_day_return)")

    # -- structural spot-checks ------------------------------
    print()
    print("  Structural spot-checks:")

    n_neg_nw = int(f["negative_networth_flag"].sum())
    print(f"    negative_networth_flag = 1 in {n_neg_nw} rows  "
          f"(expected 5)")
    assert n_neg_nw == 5, f"negative_networth_flag count off: {n_neg_nw}"

    n_avoid = int(f["any_avoid_flag"].sum())
    share_avoid = n_avoid / len(f)
    print(f"    any_avoid_flag = 1 in {n_avoid} rows ({share_avoid:.1%})")

    pure_fresh = int((f["ofs_ratio"] == 0).sum())
    pure_ofs   = int((f["ofs_ratio"] == 1).sum())
    mixed      = int(((f["ofs_ratio"] > 0) & (f["ofs_ratio"] < 1)).sum())
    ofs_nan    = int(f["ofs_ratio"].isna().sum())
    print(f"    ofs_ratio: pure-fresh={pure_fresh}, mixed={mixed}, "
          f"pure-OFS={pure_ofs}, nan={ofs_nan}  "
          f"(sum={pure_fresh+mixed+pure_ofs+ofs_nan}, expected 416)")
    assert pure_fresh + mixed + pure_ofs + ofs_nan == len(f)

    # -- log-transform skewness verification -----------------
    print()
    print("  Skewness before / after log1p:")
    log_pairs = [
        ("revenue",           "revenue_log1p"),
        ("assets",            "assets_log1p"),
        ("borrowing",         "borrowing_log1p"),
        ("total_issue_size",  "total_issue_size_log1p"),
        ("fresh_issue",       "fresh_issue_log1p"),
        ("ofs",               "ofs_log1p"),
        ("issue_price",       "issue_price_log1p"),
        ("sub_total",         "sub_total_log1p"),
    ]
    for raw, transformed in log_pairs:
        s_raw = df[raw].dropna().skew()
        s_log = f[transformed].dropna().skew()
        print(f"    {raw:22s}  raw = {s_raw:>7.2f}   "
              f"log1p = {s_log:>7.2f}")

    # -- gmp_return spot check --------------------------------
    print()
    print("  gmp_return spot checks:")
    spot_checks = [
        ("Sigachi",        "large positive (top gainer, GMP=225)"),
        ("One 97",         "negative (Paytm: worst listing, GMP=-30)"),
        ("Indian Railway", "NaN (IRCTC 2019 → gmp_available = 0)"),
    ]
    for keyword, expected in spot_checks:
        mask = df["company"].str.contains(keyword, case=False, na=False)
        if mask.any():
            r = f.loc[mask].iloc[0]
            val = r["gmp_return"]
            val_str = f"{val:+.4f}" if pd.notna(val) else "NaN"
            print(f"    {r['company']:40s}  gmp_return = {val_str:>10s}   "
                  f"[expected {expected}]")

    # -- missingness summary ----------------------------------
    print()
    print("  Missingness per feature column:")
    feature_cols = [c for c in f.columns
                    if c not in ("company", "listing_date", "year",
                                 "first_day_return")]
    miss = f[feature_cols].isna().sum().sort_values(ascending=False)
    miss = miss[miss > 0]
    if len(miss) == 0:
        print("    (no missingness in any feature column)")
    else:
        for col, n in miss.items():
            print(f"    {col:28s}  {n:4d} missing ({n/len(f):.1%})")

    # -- inf check --------------------------------------------
    inf_cols = []
    for col in feature_cols:
        if pd.api.types.is_numeric_dtype(f[col]):
            if np.isinf(f[col].fillna(0)).any():
                inf_cols.append(col)
    if inf_cols:
        print(f"\n  [ERROR] inf values in columns: {inf_cols}")
    else:
        print("\n  No inf values in any feature column.")


# ============================================================
# SUMMARY
# ============================================================
def summary(f):
    print("\n" + "=" * 72)
    print("OUTPUT SUMMARY")
    hr()
    print(f"  File: {OUT_FILE}")
    print(f"  Rows: {len(f)}")
    print(f"  Cols: {f.shape[1]}")
    print()
    print("  Column layout:")
    id_cols = ["company", "listing_date", "year", "first_day_return"]
    other_cols = [c for c in f.columns if c not in id_cols]
    print(f"    identifiers ({len(id_cols)}):  {', '.join(id_cols)}")
    print(f"    features    ({len(other_cols)}):")
    for c in other_cols:
        dtype = str(f[c].dtype)
        print(f"      {c:28s}  ({dtype})")


# ============================================================
# MAIN
# ============================================================
def main():
    df = load()
    f  = engineer(df)
    validate(df, f)
    summary(f)

    f.to_csv(OUT_FILE, index=False)
    print()
    print("=" * 72)
    print(f"  Features written to: {OUT_FILE}")
    print("=" * 72)


if __name__ == "__main__":
    main()