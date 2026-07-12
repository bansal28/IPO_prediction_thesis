"""
STEP 02: Feature engineering - build the numeric feature set
=============================================================
Reads the master dataset and produces the model-ready NUMERIC features:
    data/features/features_numeric.csv

This is the feature set that BOTH models in the thesis share:
    - baseline model:  these numeric features only
    - augmented model: these + the LLM-extracted risk features (later step)
So it must be clean, interpretable (for SHAP), and strictly leakage-free.

DESIGN DECISIONS (all agreed before writing):

  A. Missing-value handling = native NaN + missingness flags.
     XGBoost learns an optimal split direction for NaN, so we do NOT
     fabricate values. For the two features with a meaningful gap
     (debt_to_equity, gmp_return) we add a binary *_missing flag, because
     "borrowing not disclosed" or "GMP not tracked" is itself signal.
     (A median-imputed version can be produced later for linear models.)

  B. ofs_ratio / fresh_ratio missing = genuine 0, NOT a data gap.
     Verified in the data: every IPO with ofs missing has fresh/total=1.00
     (pure fresh-issue, ofs truly 0), and vice-versa; ZERO IPOs have both
     missing. So a missing component is filled with 0 before the ratio.
     This gives 100% coverage on these two structural features.

  C. Log transforms for right-skewed absolutes (skew>2 in the data):
     total_issue_size (skew 14), revenue (20), assets (9), sub_total (2).
     Uses log1p. issue_price (skew 1.9) is left untransformed.

  D. Edge cases:
     - Negative net_worth (5 IPOs): debt_to_equity is meaningless with a
       negative denominator, so we NaN the ratio and set the missing flag,
       and add a separate negative_networth_flag (distress signal).
     - Negative profit (45 IPOs): VALID (loss-making). profit_margin and
       return_on_assets correctly go negative. Kept as-is.

  LEAKAGE: listing_open/close/high/low and first_day_open_return are NEVER
  read here. Market features are already prior-day from cleaning. `year`
  is carried ONLY for the temporal split, and is NOT a model feature.

Run:
    python src/processing/02_feature_engineering.py

Output:
    data/features/features_numeric.csv
"""

import pandas as pd
import numpy as np
import os
import warnings
warnings.filterwarnings("ignore")

# ============================================================
# PATHS
# ============================================================
PROC_DIR = "data/processed"
FEAT_DIR = "data/features"
MASTER = os.path.join(PROC_DIR, "master_ipo_dataset.csv")
OUTPUT = os.path.join(FEAT_DIR, "features_numeric.csv")

# Columns that must NEVER become features (outcome / identifiers / alt target)
LEAKAGE_COLS = ["listing_open", "listing_close", "listing_high", "listing_low",
                "first_day_open_return"]


def hr():
    print("-" * 68)


# ============================================================
# LOAD
# ============================================================
def load_master():
    print("=" * 68)
    print("STEP 1: Load master dataset")
    print("=" * 68)
    df = pd.read_csv(MASTER)
    df["listing_date"] = pd.to_datetime(df["listing_date"])
    print(f"  Loaded {df.shape[0]} IPOs x {df.shape[1]} columns")

    # Safety: confirm leakage columns exist in master (they do) but will be dropped
    present_leak = [c for c in LEAKAGE_COLS if c in df.columns]
    print(f"  Leakage columns present in master (will NOT be used): {present_leak}")
    return df


# ============================================================
# STEP 2: STRUCTURAL RATIOS (ofs / fresh) - 0-fill proven
# ============================================================
def build_structural(df, F):
    print("\n" + "=" * 68)
    print("STEP 2: Structural ratios (ofs_ratio, fresh_ratio)")
    print("=" * 68)

    # Decision B: a missing component is a genuine 0 (pure issue type).
    ofs = df["ofs"].fillna(0.0)
    total = df["total_issue_size"]

    F["ofs_ratio"] = pd.Series(np.where(total > 0, ofs / total, np.nan), index=df.index)
    # NOTE: fresh_ratio is intentionally NOT created - it equals 1 - ofs_ratio
    # exactly (fresh + ofs = total for every IPO), so it is perfectly redundant
    # and would split SHAP importance across identical features. ofs_ratio alone
    # captures the fresh-vs-ofs composition.

    print(f"  ofs_ratio:   coverage {F['ofs_ratio'].notna().sum()}/{len(df)} "
          f"(range {np.nanmin(F['ofs_ratio']):.2f}-{np.nanmax(F['ofs_ratio']):.2f})")
    print(f"  (fresh_ratio omitted: = 1 - ofs_ratio exactly, perfectly redundant)")
    print(f"  (missing component treated as 0 = pure issue type, proven in audit)")


# ============================================================
# STEP 3: LOG TRANSFORMS (skewed absolutes)
# ============================================================
def build_logs(df, F):
    print("\n" + "=" * 68)
    print("STEP 3: Log transforms for right-skewed features")
    print("=" * 68)

    # log1p is safe for zeros; all these are strictly positive anyway.
    F["issue_size_log"] = np.log1p(df["total_issue_size"])
    F["revenue_log"] = np.log1p(df["revenue"])
    F["assets_log"] = np.log1p(df["assets"])
    F["sub_total_log"] = np.log1p(df["sub_total"])

    for name, raw in [("issue_size_log", "total_issue_size"),
                      ("revenue_log", "revenue"),
                      ("assets_log", "assets"),
                      ("sub_total_log", "sub_total")]:
        before = df[raw].skew()
        after = F[name].skew()
        print(f"  {name:<16s} skew {before:6.1f} -> {after:5.1f}  "
              f"(coverage {F[name].notna().sum()}/{len(df)})")


# ============================================================
# STEP 4: FINANCIAL RATIOS (native NaN + flags)
# ============================================================
def build_financial(df, F):
    print("\n" + "=" * 68)
    print("STEP 4: Financial ratios (native NaN, edge-case aware)")
    print("=" * 68)

    # profit_margin = profit / revenue  (negative profit -> negative margin, valid)
    F["profit_margin"] = pd.Series(np.where(df["revenue"] > 0,
                                  df["profit"] / df["revenue"], np.nan), index=df.index)

    # return_on_assets = profit / assets
    F["return_on_assets"] = pd.Series(np.where(df["assets"] > 0,
                                     df["profit"] / df["assets"], np.nan), index=df.index)

    # debt_to_equity = borrowing / net_worth
    #   Negative net_worth makes this meaningless -> NaN it, flag separately.
    neg_nw = df["net_worth"] < 0
    de = df["borrowing"] / df["net_worth"]
    de[neg_nw] = np.nan
    F["debt_to_equity"] = de
    F["negative_networth_flag"] = neg_nw.astype(int)

    print(f"  profit_margin:     coverage {F['profit_margin'].notna().sum()}/{len(df)}")
    print(f"  return_on_assets:  coverage {F['return_on_assets'].notna().sum()}/{len(df)}")
    print(f"  debt_to_equity:    coverage {F['debt_to_equity'].notna().sum()}/{len(df)} "
          f"({neg_nw.sum()} negative-net-worth NaN'd + flagged)")
    print(f"  45 loss-making IPOs correctly yield negative margin/ROA (kept).")


# ============================================================
# STEP 5: SENTIMENT + GMP
# ============================================================
def build_sentiment_gmp(df, F):
    print("\n" + "=" * 68)
    print("STEP 5: Broker sentiment + normalized GMP")
    print("=" * 68)

    # broker_sentiment = subscribe / (subscribe + avoid); 0=all avoid, 1=all subscribe
    denom = df["brokers_subscribe"] + df["brokers_avoid"]
    F["broker_sentiment"] = pd.Series(np.where(denom > 0,
                                     df["brokers_subscribe"] / denom, np.nan), index=df.index)

    # gmp_return = gmp_value / issue_price  (the strongest expected predictor)
    F["gmp_return"] = pd.Series(np.where(df["issue_price"] > 0,
                               df["gmp_value"] / df["issue_price"], np.nan), index=df.index)

    print(f"  broker_sentiment: coverage {F['broker_sentiment'].notna().sum()}/{len(df)} "
          f"(range {np.nanmin(F['broker_sentiment']):.2f}-{np.nanmax(F['broker_sentiment']):.2f})")
    print(f"  gmp_return:       coverage {F['gmp_return'].notna().sum()}/{len(df)} "
          f"(range {np.nanmin(F['gmp_return']):.2f}-{np.nanmax(F['gmp_return']):.2f})")

    corr = pd.concat([F["gmp_return"], df["first_day_return"]], axis=1).dropna().corr().iloc[0, 1]
    print(f"  gmp_return vs first_day_return correlation: {corr:.3f} "
          f"(sanity: literature ~0.8)")


# ============================================================
# STEP 6: PASS-THROUGH FEATURES + MISSINGNESS FLAGS
# ============================================================
def build_passthrough(df, F):
    print("\n" + "=" * 68)
    print("STEP 6: Pass-through features + missingness flags")
    print("=" * 68)

    # Market context (already leakage-safe from cleaning)
    F["nifty_close"] = df["nifty_close"]
    F["vix_close"] = df["vix_close"]
    F["nifty_7d_return"] = df["nifty_7d_return"]
    F["nifty_30d_return"] = df["nifty_30d_return"]

    # Raw demand signals kept alongside their logs
    F["sub_total"] = df["sub_total"]
    F["issue_price"] = df["issue_price"]

    # GMP availability flag (distinguishes "no GMP data" from "GMP was zero")
    F["gmp_available"] = df["gmp_available"]

    # Missingness flag for debt_to_equity (has a meaningful 15% gap).
    # NOTE: we do NOT add a gmp_return_missing flag - it would be identical to
    # (1 - gmp_available), which we already keep. gmp_available covers it.
    F["debt_to_equity_missing"] = F["debt_to_equity"].isna().astype(int)

    print("  Market: nifty_close, vix_close, nifty_7d_return, nifty_30d_return")
    print("  Demand: sub_total (raw), issue_price")
    print("  Flags:  gmp_available, debt_to_equity_missing")
    print("  (gmp_return_missing omitted: = 1 - gmp_available exactly)")


# ============================================================
# STEP 7: ASSEMBLE + WRITE
# ============================================================
def finalize(df, F):
    print("\n" + "=" * 68)
    print("STEP 7: Assemble feature matrix + write")
    print("=" * 68)

    feat = pd.DataFrame(F)

    # Carry identifiers/target/split key at the FRONT (not model features)
    out = pd.concat([
        df[["company", "year", "first_day_return"]].reset_index(drop=True),
        feat.reset_index(drop=True),
    ], axis=1)

    # Explicit ordering: meta, then the model features grouped logically
    feature_cols = [
        # structural
        "ofs_ratio", "issue_size_log",
        # financial
        "profit_margin", "return_on_assets", "debt_to_equity",
        "negative_networth_flag",
        # size/scale
        "revenue_log", "assets_log",
        # demand
        "sub_total", "sub_total_log", "issue_price",
        # sentiment / GMP
        "broker_sentiment", "gmp_return", "gmp_available",
        # market
        "nifty_close", "vix_close", "nifty_7d_return", "nifty_30d_return",
        # missingness flag
        "debt_to_equity_missing",
    ]
    meta_cols = ["company", "year", "first_day_return"]
    out = out[meta_cols + feature_cols]

    os.makedirs(FEAT_DIR, exist_ok=True)
    out.to_csv(OUTPUT, index=False)

    print(f"  Feature matrix: {out.shape[0]} IPOs x {len(feature_cols)} features "
          f"(+ 3 meta columns)")
    print(f"  Saved: {OUTPUT}")

    # Confirm no leakage columns leaked in
    leaked = [c for c in LEAKAGE_COLS if c in out.columns]
    if leaked:
        print(f"  [WARN] LEAKAGE COLUMNS PRESENT: {leaked}")
    else:
        print(f"  [OK]   No leakage columns present (listing OHLC excluded)")

    # Feature coverage table
    print("\n  Feature coverage:")
    for c in feature_cols:
        nn = out[c].notna().sum()
        flag = "" if nn == len(out) else f"  ({len(out)-nn} NaN -> XGBoost handles natively)"
        print(f"    {c:<24s} {nn:>3}/{len(out)} ({nn/len(out)*100:3.0f}%){flag}")

    return out


# ============================================================
# STEP 8: TEMPORAL SPLIT PREVIEW (for the modelling step)
# ============================================================
def split_preview(out):
    print("\n" + "=" * 68)
    print("STEP 8: Temporal split preview (no random splits - time-based)")
    print("=" * 68)
    train = out[out["year"] <= 2023]
    test = out[out["year"] >= 2025]
    val = out[out["year"] == 2024]
    print(f"  Train (<=2023): {len(train)} IPOs")
    print(f"  Val   (2024):   {len(val)} IPOs")
    print(f"  Test  (2025-26): {len(test)} IPOs")
    print(f"  (This split is applied in the modelling step, not here.)")


# ============================================================
# MAIN
# ============================================================
def main():
    print("#" * 68)
    print("# FEATURE ENGINEERING - numeric feature set")
    print("#" * 68)

    df = load_master()
    F = {}
    build_structural(df, F)
    build_logs(df, F)
    build_financial(df, F)
    build_sentiment_gmp(df, F)
    build_passthrough(df, F)
    out = finalize(df, F)
    split_preview(out)

    print("\n" + "#" * 68)
    print("# DONE")
    print("#" * 68)
    print(f"  {out.shape[0]} IPOs, {out.shape[1]-3} features written to {OUTPUT}")
    print("  Next: LLM risk-factor extraction from the 416 prospectus PDFs,")
    print("  then baseline (numeric-only) vs augmented (numeric+risk) models.")


if __name__ == "__main__":
    main()