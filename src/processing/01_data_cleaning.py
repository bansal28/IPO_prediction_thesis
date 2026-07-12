# """
# STEP 01: Data cleaning - build the master IPO dataset
# ======================================================
# Merges all raw collected files into ONE clean, analysis-ready table:
#     data/processed/master_ipo_dataset.csv   (419 equity IPOs)

# This is the single source of truth for feature engineering and modelling.

# PIPELINE (9 steps):
#   1. Load raw_ipo_details.csv (434 rows - the spine)
#   2. Parse all raw strings -> numbers ("Rs 178 per share"->178.0, "111.91x"->111.91)
#   3. Drop 15 REITs/InvITs -> 419 equity IPOs
#   4. Compute first_day_return from the DETAIL-PAGE listing_close
#   5. Parse listing dates, add listing_date + year
#   6. Merge Nifty + VIX at DAY-BEFORE-LISTING (leakage-safe) + trailing returns
#   7. Merge GMP (price+date match + name overrides), apply the Rs 0 rule,
#      add a gmp_available flag
#   8. Cross-validate against Ghosh (overlapping IPOs, expect ~100% price match)
#   9. Drop unusable columns; write the master CSV

# LOCKED DECISIONS baked in here (from the collection/audit phase):
#   - listing_close ALWAYS from the detail page, never the tracker
#     (verified: detail page had Mankind Pharma's true BSE close Rs 1424.05,
#      the tracker wrongly showed Rs 1080)
#   - REIT rule: name matches REIT|Trust|InvIT OR Embassy Office/Mindspace
#   - GMP=Rs 0: 2019 all->NaN; 2020 ->NaN if listing gain>15%; 2021+ keep real
#   - Leakage: Nifty/VIX use the day BEFORE listing; listing OHLC columns are
#     used only to build the target, then EXCLUDED from the feature set
#   - Category subscription (sub_qib/nii/retail) dropped (only ~1% coverage);
#     sub_total (100%) is retained

# Run:
#     python src/processing/01_data_cleaning.py

# Output:
#     data/processed/master_ipo_dataset.csv
# """

# import pandas as pd
# import numpy as np
# import os
# import re
# import warnings
# warnings.filterwarnings("ignore")

# # ============================================================
# # PATHS
# # ============================================================
# RAW_DIR = "data/raw"
# PROC_DIR = "data/processed"

# DETAILS = os.path.join(RAW_DIR, "raw_ipo_details.csv")
# GMP = os.path.join(RAW_DIR, "raw_gmp_data.csv")
# NIFTY = os.path.join(RAW_DIR, "raw_nifty50_daily.csv")
# VIX = os.path.join(RAW_DIR, "raw_india_vix_daily.csv")
# GHOSH = os.path.join(RAW_DIR, "ghosh_mainboard_v18.xlsx")
# OUTPUT = os.path.join(PROC_DIR, "master_ipo_dataset.csv")

# REIT_REGEX = r"REIT|Trust|InvIT|Embassy Office|Mindspace Business"

# # GMP brand-name -> detail-page legal-name overrides (for the ~15 that don't
# # match by price+date). These are the documented cases.
# GMP_NAME_OVERRIDES = {
#     "CAMS": "Computer Age Management Services Ltd.",
#     "Paytm": "One 97 Communications Ltd.",
#     "SJS Enterprises": "S.J.S.Enterprises Ltd.",
#     "Policybazaar": "PB Fintech Ltd.",
#     "KIMS": "Krishna Institute of Medical Sciences Ltd.",
#     "Five Star Business Finance": "Five-Star Business Finance Ltd.",
#     "Mufti Jeans": "Credo Brands Marketing Ltd.",
#     "Firstcry": "Brainbees Solutions Ltd.",
#     "Aasaan Loans": "Akme Fintrade (India) Ltd.",
#     "NSDL": "National Securities Depository Ltd.",
#     "Leela Hotels": "Schloss Bangalore Ltd.",
# }


# # ============================================================
# # PARSING HELPERS
# # ============================================================
# def parse_price(s):
#     """'Rs 178 per share' / 'Rs 1,424.05' -> float."""
#     if pd.isna(s):
#         return np.nan
#     s = str(s).replace("₹", "").replace(",", "").replace(" per share", "").strip()
#     m = re.search(r"-?\d+\.?\d*", s)
#     return float(m.group()) if m else np.nan


# def parse_x(s):
#     """'111.91x' -> 111.91."""
#     if pd.isna(s):
#         return np.nan
#     m = re.search(r"-?\d+\.?\d*", str(s))
#     return float(m.group()) if m else np.nan


# def parse_crore(s):
#     """'Rs 637.97 Cr' / 'Rs 1,234.00 Cr' -> float (in crore)."""
#     if pd.isna(s):
#         return np.nan
#     s = str(s).replace("₹", "").replace(",", "").replace("Cr", "").strip()
#     m = re.search(r"-?\d+\.?\d*", s)
#     return float(m.group()) if m else np.nan


# def parse_int(s):
#     """'12' / '12 brokers' -> int-ish float."""
#     if pd.isna(s):
#         return np.nan
#     m = re.search(r"-?\d+", str(s))
#     return float(m.group()) if m else np.nan


# def parse_gmp_val(s):
#     """'Rs 145' / 'Rs -4' / 'Rs 0' -> float."""
#     if pd.isna(s):
#         return np.nan
#     s = str(s).replace("₹", "").replace(",", "").strip()
#     m = re.search(r"-?\d+\.?\d*", s)
#     return float(m.group()) if m else np.nan


# def parse_listing_gain_pct(s):
#     """From GMP 'Listing Price' like 'Rs 626.00 (95.62%)' -> 95.62."""
#     if pd.isna(s):
#         return np.nan
#     m = re.search(r"\(([-\d.]+)%\)", str(s))
#     return float(m.group(1)) if m else np.nan


# def hr():
#     print("-" * 68)


# # ============================================================
# # STEP 1: LOAD DETAILS
# # ============================================================
# def load_details():
#     print("=" * 68)
#     print("STEP 1: Load raw_ipo_details.csv")
#     print("=" * 68)
#     det = pd.read_csv(DETAILS)
#     print(f"  Loaded {len(det)} rows, {len(det.columns)} columns")
#     return det


# # ============================================================
# # STEP 2: PARSE STRINGS -> NUMBERS
# # ============================================================
# def parse_numeric(det):
#     print("\n" + "=" * 68)
#     print("STEP 2: Parse raw strings -> numbers")
#     print("=" * 68)
#     df = det.copy()

#     # Prices
#     df["issue_price"] = df["issue_price"].apply(parse_price)
#     df["face_value"] = df["face_value"].apply(parse_price)
#     for col in ["listing_open", "listing_close", "listing_high", "listing_low"]:
#         if col in df.columns:
#             df[col] = df[col].apply(parse_price)

#     # Lot size (int)
#     if "lot_size" in df.columns:
#         df["lot_size"] = df["lot_size"].apply(parse_int)

#     # Issue sizes (crore)
#     for col in ["total_issue_size", "fresh_issue", "ofs"]:
#         if col in df.columns:
#             df[col] = df[col].apply(parse_crore)

#     # Financials (crore)
#     for col in ["revenue", "profit", "assets", "net_worth", "borrowing"]:
#         if col in df.columns:
#             df[col] = df[col].apply(parse_crore)

#     # Subscription (x)
#     for col in ["sub_total", "sub_qib", "sub_nii", "sub_retail"]:
#         if col in df.columns:
#             df[col] = df[col].apply(parse_x)

#     # Broker counts (int)
#     for col in ["brokers_subscribe", "brokers_avoid", "members_subscribe"]:
#         if col in df.columns:
#             df[col] = df[col].apply(parse_int)

#     print("  Parsed prices, issue sizes, financials, subscription, broker counts.")
#     print(f"  Example: issue_price now numeric, sample: "
#           f"{df['issue_price'].dropna().head(3).tolist()}")
#     print(f"  Example: sub_total sample: {df['sub_total'].dropna().head(3).tolist()}")
#     return df


# # ============================================================
# # STEP 3: DROP REITs / InvITs
# # ============================================================
# def drop_reits(df):
#     print("\n" + "=" * 68)
#     print("STEP 3: Drop REITs / InvITs (not equity IPOs)")
#     print("=" * 68)
#     reit = df["company"].str.contains(REIT_REGEX, case=False, na=False)
#     print(f"  Dropping {reit.sum()} REITs/InvITs:")
#     for c in df[reit]["company"].tolist():
#         print(f"      - {c}")
#     df = df[~reit].reset_index(drop=True)
#     print(f"  Remaining equity IPOs: {len(df)}")
#     return df


# # ============================================================
# # STEP 4: COMPUTE TARGET
# # ============================================================
# def compute_target(df):
#     print("\n" + "=" * 68)
#     print("STEP 4: Compute first_day_return (from detail-page listing_close)")
#     print("=" * 68)
#     df["first_day_return"] = (df["listing_close"] - df["issue_price"]) / df["issue_price"]
#     # Also a listing-open return (sometimes used as an alternative target)
#     if "listing_open" in df.columns:
#         df["first_day_open_return"] = (df["listing_open"] - df["issue_price"]) / df["issue_price"]
#     n = df["first_day_return"].notna().sum()
#     print(f"  first_day_return computed for {n}/{len(df)} IPOs")
#     print(f"  Mean {df['first_day_return'].mean()*100:.1f}%, "
#           f"Median {df['first_day_return'].median()*100:.1f}%, "
#           f"Std {df['first_day_return'].std()*100:.1f}%")
#     print(f"  Positive: {(df['first_day_return']>0).mean()*100:.1f}%")
#     return df


# # ============================================================
# # STEP 5: DATES
# # ============================================================
# def parse_dates(df):
#     print("\n" + "=" * 68)
#     print("STEP 5: Parse listing dates")
#     print("=" * 68)
#     df["listing_date"] = pd.to_datetime(df["listed_on"], errors="coerce")
#     df["year"] = df["listing_date"].dt.year
#     n = df["listing_date"].notna().sum()
#     print(f"  Parsed listing_date for {n}/{len(df)} IPOs")
#     print(f"  Range: {df['listing_date'].min().date()} -> {df['listing_date'].max().date()}")
#     print(f"  Per-year: {df['year'].value_counts().sort_index().to_dict()}")
#     return df


# # ============================================================
# # STEP 6: MERGE MARKET DATA (leakage-safe)
# # ============================================================
# def load_market(path):
#     """yfinance format: 3 header rows, 7 cols incl Adj Close. Use Close."""
#     m = pd.read_csv(path, skiprows=3,
#                     names=["date", "adj_close", "close", "high", "low", "open", "volume"])
#     m["date"] = pd.to_datetime(m["date"], errors="coerce")
#     m["close"] = pd.to_numeric(m["close"], errors="coerce")
#     m = m.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
#     return m[["date", "close"]]


# def merge_market(df):
#     print("\n" + "=" * 68)
#     print("STEP 6: Merge Nifty + VIX at day-before-listing (leakage-safe)")
#     print("=" * 68)
#     nifty = load_market(NIFTY).rename(columns={"close": "nifty_close"})
#     vix = load_market(VIX).rename(columns={"close": "vix_close"})

#     # For each IPO, get the market value on the LAST trading day BEFORE listing.
#     # merge_asof with direction='backward' + allow_exact_matches=False gives us
#     # strictly-prior values (never the listing day itself).
#     df = df.sort_values("listing_date").reset_index(drop=True)

#     df = pd.merge_asof(
#         df, nifty.rename(columns={"date": "nifty_date"}),
#         left_on="listing_date", right_on="nifty_date",
#         direction="backward", allow_exact_matches=False,
#     )
#     df = pd.merge_asof(
#         df, vix.rename(columns={"date": "vix_date"}),
#         left_on="listing_date", right_on="vix_date",
#         direction="backward", allow_exact_matches=False,
#     )

#     # Trailing Nifty returns (7-day and 30-day) leading up to listing
#     nifty_idx = nifty.set_index("date")["nifty_close"]

#     def trailing_return(listing_dt, days):
#         prior = nifty_idx[nifty_idx.index < listing_dt]
#         if len(prior) < 2:
#             return np.nan
#         end_val = prior.iloc[-1]
#         target_day = listing_dt - pd.Timedelta(days=days)
#         past = prior[prior.index <= target_day]
#         if len(past) == 0:
#             return np.nan
#         start_val = past.iloc[-1]
#         return (end_val - start_val) / start_val

#     df["nifty_7d_return"] = df["listing_date"].apply(lambda d: trailing_return(d, 7))
#     df["nifty_30d_return"] = df["listing_date"].apply(lambda d: trailing_return(d, 30))

#     print(f"  nifty_close (prev day): {df['nifty_close'].notna().sum()}/{len(df)}")
#     print(f"  vix_close (prev day):   {df['vix_close'].notna().sum()}/{len(df)}")
#     print(f"  nifty_7d_return:        {df['nifty_7d_return'].notna().sum()}/{len(df)}")
#     print(f"  nifty_30d_return:       {df['nifty_30d_return'].notna().sum()}/{len(df)}")
#     print("  (prev-day values guarantee no listing-day leakage)")

#     df = df.drop(columns=["nifty_date", "vix_date"], errors="ignore")
#     return df


# # ============================================================
# # STEP 7: MERGE GMP
# # ============================================================
# def merge_gmp(df):
#     print("\n" + "=" * 68)
#     print("STEP 7: Merge GMP + apply Rs 0 rule + gmp_available flag")
#     print("=" * 68)
#     gmp = pd.read_csv(GMP)

#     # Parse GMP fields
#     gmp["gmp_value"] = gmp["GMP"].apply(parse_gmp_val)
#     gmp["gmp_ip"] = gmp["IPO Price"].apply(parse_price)
#     gmp["gmp_listing_date"] = pd.to_datetime(gmp["Listing Date"], format="%d-%b-%y",
#                                              errors="coerce")
#     gmp["gmp_listing_gain"] = gmp["Listing Price"].apply(parse_listing_gain_pct)

#     # --- Apply the Rs 0 rule BEFORE merging ---
#     # 2019: all Rs 0 -> NaN (untracked)
#     # 2020: Rs 0 -> NaN only if listing gain > 15% (untracked); else keep (real zero)
#     # 2021+: keep all Rs 0 as genuine
#     def adjust_zero(row):
#         if row["gmp_value"] != 0:
#             return row["gmp_value"]
#         yr = row["year"] if "year" in row and pd.notna(row["year"]) else \
#              (row["gmp_listing_date"].year if pd.notna(row["gmp_listing_date"]) else None)
#         if yr == 2019:
#             return np.nan
#         if yr == 2020:
#             return np.nan if (pd.notna(row["gmp_listing_gain"]) and row["gmp_listing_gain"] > 15) else 0.0
#         return 0.0
#     if "year" not in gmp.columns:
#         gmp["year"] = gmp["gmp_listing_date"].dt.year
#     gmp["gmp_value_adj"] = gmp.apply(adjust_zero, axis=1)

#     n_nulled = ((gmp["gmp_value"] == 0) & (gmp["gmp_value_adj"].isna())).sum()
#     print(f"  Rs 0 -> NaN conversions (untracked early-year): {n_nulled}")

#     # --- Match key: issue_price (rounded) + listing_date ---
#     df["_k"] = df["issue_price"].round(0).astype("Int64").astype(str) + "_" + \
#                df["listing_date"].dt.strftime("%Y-%m-%d")
#     gmp["_k"] = gmp["gmp_ip"].round(0).astype("Int64").astype(str) + "_" + \
#                 gmp["gmp_listing_date"].dt.strftime("%Y-%m-%d")

#     gmp_lookup = gmp.dropna(subset=["_k"]).drop_duplicates("_k").set_index("_k")["gmp_value_adj"]
#     df["gmp_value"] = df["_k"].map(gmp_lookup)
#     matched_by_key = df["gmp_value"].notna().sum()
#     print(f"  Matched by (issue_price + listing_date): {matched_by_key}/{len(df)}")

#     # --- Name-override fallback for the ones not matched by key ---
#     # Build a name->gmp lookup from the GMP file
#     gmp_by_name = gmp.dropna(subset=["gmp_value_adj"]).copy()
#     # exact brand-name index
#     name_to_gmp = {}
#     for _, r in gmp.iterrows():
#         name_to_gmp[str(r["IPO"]).strip()] = r["gmp_value_adj"]

#     unmatched = df[df["gmp_value"].isna()]
#     override_hits = 0
#     for idx, row in unmatched.iterrows():
#         legal = row["company"]
#         # find any GMP brand-name whose override maps to this legal name
#         brand = None
#         for b, mapped_legal in GMP_NAME_OVERRIDES.items():
#             if mapped_legal == legal:
#                 brand = b
#                 break
#         if brand and brand in name_to_gmp:
#             df.at[idx, "gmp_value"] = name_to_gmp[brand]
#             override_hits += 1

#     print(f"  Recovered via name-overrides: {override_hits}")

#     # --- Report anything STILL unmatched (so we catch cases beyond the 11) ---
#     still = df[df["gmp_value"].isna() & (df["year"] >= 2020)]
#     # (2019 IPOs legitimately have no GMP - don't flag those)
#     print(f"  Still without GMP (year>=2020, may need a new override): {len(still)}")
#     if len(still) > 0:
#         for _, r in still.iterrows():
#             print(f"      - {r['company']} ({r['year']})")

#     # gmp_available flag: 1 if we have a GMP value, else 0
#     df["gmp_available"] = df["gmp_value"].notna().astype(int)
#     print(f"  gmp_available=1 for {df['gmp_available'].sum()}/{len(df)} IPOs")

#     df = df.drop(columns=["_k"], errors="ignore")
#     return df


# # ============================================================
# # STEP 8: CROSS-VALIDATE AGAINST GHOSH
# # ============================================================
# def cross_validate_ghosh(df):
#     print("\n" + "=" * 68)
#     print("STEP 8: Cross-validate issue prices against Ghosh")
#     print("=" * 68)
#     if not os.path.exists(GHOSH):
#         print("  Ghosh file not found - skipping cross-validation.")
#         return
#     try:
#         g = pd.read_excel(GHOSH)
#     except Exception as e:
#         print(f"  Could not read Ghosh file ({e}) - skipping.")
#         return

#     # Find a company-name column and an issue-price column in Ghosh
#     name_col = None
#     for c in g.columns:
#         if "company" in c.lower() or "issuer" in c.lower():
#             name_col = c
#             break
#     price_col = None
#     for c in g.columns:
#         cl = c.lower()
#         if ("issue" in cl and "price" in cl) or cl in ("offer price", "ipo price"):
#             price_col = c
#             break

#     if not name_col or not price_col:
#         print(f"  Couldn't locate Ghosh name/price columns "
#               f"(name={name_col}, price={price_col}) - skipping.")
#         return

#     def norm(s):
#         s = str(s).lower()
#         s = re.sub(r"\b(ltd|limited|the|and|co|corp|india)\b", "", s)
#         s = re.sub(r"[^a-z0-9 ]", " ", s)
#         return re.sub(r"\s+", " ", s).strip()

#     g["_n"] = g[name_col].apply(norm)
#     g["_p"] = pd.to_numeric(g[price_col], errors="coerce")
#     gmap = g.dropna(subset=["_p"]).drop_duplicates("_n").set_index("_n")["_p"]

#     df["_n"] = df["company"].apply(norm)
#     overlap = df[df["_n"].isin(gmap.index)].copy()
#     overlap["_gp"] = overlap["_n"].map(gmap)
#     overlap["_match"] = (overlap["issue_price"] - overlap["_gp"]).abs() < 1.0

#     n = len(overlap)
#     matches = overlap["_match"].sum()
#     print(f"  Overlapping IPOs with Ghosh: {n}")
#     if n > 0:
#         print(f"  Issue-price concordance: {matches}/{n} ({matches/n*100:.1f}%)")
#         mism = overlap[~overlap["_match"]]
#         if len(mism) > 0:
#             print(f"  Mismatches ({len(mism)}):")
#             for _, r in mism.head(10).iterrows():
#                 print(f"      {r['company']}: ours={r['issue_price']}, ghosh={r['_gp']}")
#     df.drop(columns=["_n"], errors="ignore", inplace=True)


# # ============================================================
# # STEP 9: SELECT COLUMNS + WRITE
# # ============================================================
# def finalize(df):
#     print("\n" + "=" * 68)
#     print("STEP 9: Select final columns + write master dataset")
#     print("=" * 68)

#     # Columns to KEEP in the master (clean parsed values only).
#     # NOTE: listing_open/high/low/close are the OUTCOME - kept here only so the
#     # target is reproducible, but feature engineering must EXCLUDE them.
#     keep = [
#         # identifiers
#         "company", "listing_date", "year",
#         # target(s)
#         "first_day_return", "first_day_open_return",
#         # issue mechanics (features)
#         "issue_price", "face_value", "lot_size",
#         "total_issue_size", "fresh_issue", "ofs",
#         # demand (features)
#         "sub_total", "gmp_value", "gmp_available",
#         # financials (features)
#         "revenue", "profit", "assets", "net_worth", "borrowing",
#         # ownership (features)
#         "hold_pre", "hold_post",
#         # broker sentiment (features)
#         "brokers_subscribe", "brokers_avoid",
#         # market context (features, leakage-safe)
#         "nifty_close", "vix_close", "nifty_7d_return", "nifty_30d_return",
#         # outcome columns (for reference/reproducibility, NOT features)
#         "listing_open", "listing_close", "listing_high", "listing_low",
#     ]
#     keep = [c for c in keep if c in df.columns]
#     master = df[keep].copy()

#     # Drop the category-subscription columns explicitly (only ~1% coverage)
#     for c in ["sub_qib", "sub_nii", "sub_retail"]:
#         if c in master.columns:
#             master = master.drop(columns=[c])

#     os.makedirs(PROC_DIR, exist_ok=True)
#     master.to_csv(OUTPUT, index=False)

#     print(f"  Master dataset shape: {master.shape}")
#     print(f"  Columns ({len(master.columns)}): {list(master.columns)}")
#     print(f"\n  Saved: {OUTPUT}")

#     # Coverage summary
#     print("\n  Final coverage:")
#     for c in master.columns:
#         nn = master[c].notna().sum()
#         print(f"    {c:<22s} {nn:>3}/{len(master)} ({nn/len(master)*100:3.0f}%)")

#     return master


# # ============================================================
# # MAIN
# # ============================================================
# def main():
#     print("#" * 68)
#     print("# BUILDING MASTER IPO DATASET")
#     print("#" * 68)

#     det = load_details()
#     df = parse_numeric(det)
#     df = drop_reits(df)
#     df = compute_target(df)
#     df = parse_dates(df)
#     df = merge_market(df)
#     df = merge_gmp(df)
#     cross_validate_ghosh(df)
#     master = finalize(df)

#     print("\n" + "#" * 68)
#     print("# DONE")
#     print("#" * 68)
#     print(f"  {len(master)} equity IPOs written to {OUTPUT}")
#     print("  Reminder: feature engineering must EXCLUDE the listing_open/")
#     print("  close/high/low columns (they are the outcome).")


# if __name__ == "__main__":
#     main()



"""
STEP 01: Data cleaning - build the master IPO dataset
======================================================
Merges all raw collected files into ONE clean, analysis-ready table:
    data/processed/master_ipo_dataset.csv   (419 equity IPOs)

This is the single source of truth for feature engineering and modelling.

PIPELINE (9 steps):
  1. Load raw_ipo_details.csv (434 rows - the spine)
  2. Parse all raw strings -> numbers ("Rs 178 per share"->178.0, "111.91x"->111.91)
  3. Drop 15 REITs/InvITs -> 419 equity IPOs
  4. Compute first_day_return from the DETAIL-PAGE listing_close
  5. Parse listing dates, add listing_date + year
  6. Merge Nifty + VIX at DAY-BEFORE-LISTING (leakage-safe) + trailing returns
  7. Merge GMP (price+date match + name overrides), apply the Rs 0 rule,
     add a gmp_available flag
  8. Cross-validate against Ghosh (overlapping IPOs, expect ~100% price match)
  9. Drop unusable columns; write the master CSV

LOCKED DECISIONS baked in here (from the collection/audit phase):
  - listing_close ALWAYS from the detail page, never the tracker
    (verified: detail page had Mankind Pharma's true BSE close Rs 1424.05,
     the tracker wrongly showed Rs 1080)
  - REIT rule: name matches REIT|Trust|InvIT OR Embassy Office/Mindspace
  - GMP=Rs 0: 2019 all->NaN; 2020 ->NaN if listing gain>15%; 2021+ keep real
  - Leakage: Nifty/VIX use the day BEFORE listing; listing OHLC columns are
    used only to build the target, then EXCLUDED from the feature set
  - Category subscription (sub_qib/nii/retail) dropped (only ~1% coverage);
    sub_total (100%) is retained

Run:
    python src/processing/01_data_cleaning.py

Output:
    data/processed/master_ipo_dataset.csv
"""

import pandas as pd
import numpy as np
import os
import re
import warnings
warnings.filterwarnings("ignore")

# ============================================================
# PATHS
# ============================================================
RAW_DIR = "data/raw"
PROC_DIR = "data/processed"

DETAILS = os.path.join(RAW_DIR, "raw_ipo_details.csv")
GMP = os.path.join(RAW_DIR, "raw_gmp_data.csv")
NIFTY = os.path.join(RAW_DIR, "raw_nifty50_daily.csv")
VIX = os.path.join(RAW_DIR, "raw_india_vix_daily.csv")
GHOSH = os.path.join(RAW_DIR, "ghosh_mainboard_v18.xlsx")
OUTPUT = os.path.join(PROC_DIR, "master_ipo_dataset.csv")

REIT_REGEX = r"REIT|Trust|InvIT|Embassy Office|Mindspace Business"

# GMP brand-name -> detail-page legal-name overrides (for the ~15 that don't
# match by price+date). These are the documented cases.
GMP_NAME_OVERRIDES = {
    "CAMS": "Computer Age Management Services Ltd.",
    "Paytm": "One 97 Communications Ltd.",
    "SJS Enterprises": "S.J.S.Enterprises Ltd.",
    "Policybazaar": "PB Fintech Ltd.",
    "KIMS": "Krishna Institute of Medical Sciences Ltd.",
    "Five Star Business Finance": "Five-Star Business Finance Ltd.",
    "Mufti Jeans": "Credo Brands Marketing Ltd.",
    "Firstcry": "Brainbees Solutions Ltd.",
    "Aasaan Loans": "Akme Fintrade (India) Ltd.",
    "NSDL": "National Securities Depository Ltd.",
    "Leela Hotels": "Schloss Bangalore Ltd.",
}


# ============================================================
# PARSING HELPERS
# ============================================================
def parse_price(s):
    """'Rs 178 per share' / 'Rs 1,424.05' -> float."""
    if pd.isna(s):
        return np.nan
    s = str(s).replace("₹", "").replace(",", "").replace(" per share", "").strip()
    m = re.search(r"-?\d+\.?\d*", s)
    return float(m.group()) if m else np.nan


def parse_x(s):
    """'111.91x' -> 111.91."""
    if pd.isna(s):
        return np.nan
    m = re.search(r"-?\d+\.?\d*", str(s))
    return float(m.group()) if m else np.nan


def parse_crore(s):
    """'Rs 637.97 Cr' / 'Rs 1,234.00 Cr' -> float (in crore)."""
    if pd.isna(s):
        return np.nan
    s = str(s).replace("₹", "").replace(",", "").replace("Cr", "").strip()
    m = re.search(r"-?\d+\.?\d*", s)
    return float(m.group()) if m else np.nan


def parse_int(s):
    """'12' / '12 brokers' -> int-ish float."""
    if pd.isna(s):
        return np.nan
    m = re.search(r"-?\d+", str(s))
    return float(m.group()) if m else np.nan


def parse_gmp_val(s):
    """'Rs 145' / 'Rs -4' / 'Rs 0' -> float."""
    if pd.isna(s):
        return np.nan
    s = str(s).replace("₹", "").replace(",", "").strip()
    m = re.search(r"-?\d+\.?\d*", s)
    return float(m.group()) if m else np.nan


def parse_listing_gain_pct(s):
    """From GMP 'Listing Price' like 'Rs 626.00 (95.62%)' -> 95.62."""
    if pd.isna(s):
        return np.nan
    m = re.search(r"\(([-\d.]+)%\)", str(s))
    return float(m.group(1)) if m else np.nan


def hr():
    print("-" * 68)


# ============================================================
# STEP 1: LOAD DETAILS
# ============================================================
def load_details():
    print("=" * 68)
    print("STEP 1: Load raw_ipo_details.csv")
    print("=" * 68)
    det = pd.read_csv(DETAILS)
    print(f"  Loaded {len(det)} rows, {len(det.columns)} columns")
    return det


# ============================================================
# STEP 2: PARSE STRINGS -> NUMBERS
# ============================================================
def parse_numeric(det):
    print("\n" + "=" * 68)
    print("STEP 2: Parse raw strings -> numbers")
    print("=" * 68)
    df = det.copy()

    # Prices
    df["issue_price"] = df["issue_price"].apply(parse_price)
    df["face_value"] = df["face_value"].apply(parse_price)
    for col in ["listing_open", "listing_close", "listing_high", "listing_low"]:
        if col in df.columns:
            df[col] = df[col].apply(parse_price)

    # Lot size (int)
    if "lot_size" in df.columns:
        df["lot_size"] = df["lot_size"].apply(parse_int)

    # Issue sizes (crore)
    for col in ["total_issue_size", "fresh_issue", "ofs"]:
        if col in df.columns:
            df[col] = df[col].apply(parse_crore)

    # Financials (crore)
    for col in ["revenue", "profit", "assets", "net_worth", "borrowing"]:
        if col in df.columns:
            df[col] = df[col].apply(parse_crore)

    # Subscription (x)
    for col in ["sub_total", "sub_qib", "sub_nii", "sub_retail"]:
        if col in df.columns:
            df[col] = df[col].apply(parse_x)

    # Broker counts (int)
    for col in ["brokers_subscribe", "brokers_avoid", "members_subscribe"]:
        if col in df.columns:
            df[col] = df[col].apply(parse_int)

    print("  Parsed prices, issue sizes, financials, subscription, broker counts.")
    print(f"  Example: issue_price now numeric, sample: "
          f"{df['issue_price'].dropna().head(3).tolist()}")
    print(f"  Example: sub_total sample: {df['sub_total'].dropna().head(3).tolist()}")
    return df


# ============================================================
# STEP 3: DROP REITs / InvITs
# ============================================================
def drop_reits(df):
    print("\n" + "=" * 68)
    print("STEP 3: Drop REITs / InvITs (not equity IPOs)")
    print("=" * 68)
    reit = df["company"].str.contains(REIT_REGEX, case=False, na=False)
    print(f"  Dropping {reit.sum()} REITs/InvITs:")
    for c in df[reit]["company"].tolist():
        print(f"      - {c}")
    df = df[~reit].reset_index(drop=True)
    print(f"  Remaining equity IPOs: {len(df)}")
    return df


# ============================================================
# STEP 4: COMPUTE TARGET
# ============================================================
def compute_target(df):
    print("\n" + "=" * 68)
    print("STEP 4: Compute first_day_return (from detail-page listing_close)")
    print("=" * 68)
    df["first_day_return"] = (df["listing_close"] - df["issue_price"]) / df["issue_price"]
    # Also a listing-open return (sometimes used as an alternative target)
    if "listing_open" in df.columns:
        df["first_day_open_return"] = (df["listing_open"] - df["issue_price"]) / df["issue_price"]
    n = df["first_day_return"].notna().sum()
    print(f"  first_day_return computed for {n}/{len(df)} IPOs")
    print(f"  Mean {df['first_day_return'].mean()*100:.1f}%, "
          f"Median {df['first_day_return'].median()*100:.1f}%, "
          f"Std {df['first_day_return'].std()*100:.1f}%")
    print(f"  Positive: {(df['first_day_return']>0).mean()*100:.1f}%")
    return df


# ============================================================
# STEP 5: DATES
# ============================================================
def parse_dates(df):
    print("\n" + "=" * 68)
    print("STEP 5: Parse listing dates")
    print("=" * 68)
    df["listing_date"] = pd.to_datetime(df["listed_on"], errors="coerce")
    df["year"] = df["listing_date"].dt.year
    n = df["listing_date"].notna().sum()
    print(f"  Parsed listing_date for {n}/{len(df)} IPOs")
    print(f"  Range: {df['listing_date'].min().date()} -> {df['listing_date'].max().date()}")
    print(f"  Per-year: {df['year'].value_counts().sort_index().to_dict()}")
    return df


# ============================================================
# STEP 6: MERGE MARKET DATA (leakage-safe)
# ============================================================
def load_market(path):
    """yfinance format: 3 header rows, 7 cols incl Adj Close. Use Close."""
    m = pd.read_csv(path, skiprows=3,
                    names=["date", "adj_close", "close", "high", "low", "open", "volume"])
    m["date"] = pd.to_datetime(m["date"], errors="coerce")
    m["close"] = pd.to_numeric(m["close"], errors="coerce")
    m = m.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    return m[["date", "close"]]


def merge_market(df):
    print("\n" + "=" * 68)
    print("STEP 6: Merge Nifty + VIX at day-before-listing (leakage-safe)")
    print("=" * 68)
    nifty = load_market(NIFTY).rename(columns={"close": "nifty_close"})
    vix = load_market(VIX).rename(columns={"close": "vix_close"})

    # For each IPO, get the market value on the LAST trading day BEFORE listing.
    # merge_asof with direction='backward' + allow_exact_matches=False gives us
    # strictly-prior values (never the listing day itself).
    df = df.sort_values("listing_date").reset_index(drop=True)

    df = pd.merge_asof(
        df, nifty.rename(columns={"date": "nifty_date"}),
        left_on="listing_date", right_on="nifty_date",
        direction="backward", allow_exact_matches=False,
    )
    df = pd.merge_asof(
        df, vix.rename(columns={"date": "vix_date"}),
        left_on="listing_date", right_on="vix_date",
        direction="backward", allow_exact_matches=False,
    )

    # Trailing Nifty returns (7-day and 30-day) leading up to listing
    nifty_idx = nifty.set_index("date")["nifty_close"]

    def trailing_return(listing_dt, days):
        prior = nifty_idx[nifty_idx.index < listing_dt]
        if len(prior) < 2:
            return np.nan
        end_val = prior.iloc[-1]
        target_day = listing_dt - pd.Timedelta(days=days)
        past = prior[prior.index <= target_day]
        if len(past) == 0:
            return np.nan
        start_val = past.iloc[-1]
        return (end_val - start_val) / start_val

    df["nifty_7d_return"] = df["listing_date"].apply(lambda d: trailing_return(d, 7))
    df["nifty_30d_return"] = df["listing_date"].apply(lambda d: trailing_return(d, 30))

    print(f"  nifty_close (prev day): {df['nifty_close'].notna().sum()}/{len(df)}")
    print(f"  vix_close (prev day):   {df['vix_close'].notna().sum()}/{len(df)}")
    print(f"  nifty_7d_return:        {df['nifty_7d_return'].notna().sum()}/{len(df)}")
    print(f"  nifty_30d_return:       {df['nifty_30d_return'].notna().sum()}/{len(df)}")
    print("  (prev-day values guarantee no listing-day leakage)")

    df = df.drop(columns=["nifty_date", "vix_date"], errors="ignore")
    return df


# ============================================================
# STEP 7: MERGE GMP
# ============================================================
def merge_gmp(df):
    print("\n" + "=" * 68)
    print("STEP 7: Merge GMP + apply Rs 0 rule + gmp_available flag")
    print("=" * 68)
    gmp = pd.read_csv(GMP)

    # Parse GMP fields
    gmp["gmp_value"] = gmp["GMP"].apply(parse_gmp_val)
    gmp["gmp_ip"] = gmp["IPO Price"].apply(parse_price)
    gmp["gmp_listing_date"] = pd.to_datetime(gmp["Listing Date"], format="%d-%b-%y",
                                             errors="coerce")
    gmp["gmp_listing_gain"] = gmp["Listing Price"].apply(parse_listing_gain_pct)

    # --- Apply the Rs 0 rule BEFORE merging ---
    # 2019: all Rs 0 -> NaN (untracked)
    # 2020: Rs 0 -> NaN only if listing gain > 15% (untracked); else keep (real zero)
    # 2021+: keep all Rs 0 as genuine
    def adjust_zero(row):
        if row["gmp_value"] != 0:
            return row["gmp_value"]
        yr = row["year"] if "year" in row and pd.notna(row["year"]) else \
             (row["gmp_listing_date"].year if pd.notna(row["gmp_listing_date"]) else None)
        if yr == 2019:
            return np.nan
        if yr == 2020:
            return np.nan if (pd.notna(row["gmp_listing_gain"]) and row["gmp_listing_gain"] > 15) else 0.0
        return 0.0
    if "year" not in gmp.columns:
        gmp["year"] = gmp["gmp_listing_date"].dt.year
    gmp["gmp_value_adj"] = gmp.apply(adjust_zero, axis=1)

    n_nulled = ((gmp["gmp_value"] == 0) & (gmp["gmp_value_adj"].isna())).sum()
    print(f"  Rs 0 -> NaN conversions (untracked early-year): {n_nulled}")

    # --- Match by (issue_price + listing_date), name-aware for collisions ---
    # NOTE: two IPOs can list on the same day at the same issue price (e.g.
    # GNG Electronics and Indiqube Spaces both listed 2025-07-30 at Rs 237).
    # A plain (price+date) key would give them the SAME GMP. So when more
    # than one GMP row matches, we disambiguate by company-name overlap.
    def _norm_name(s):
        s = str(s).lower()
        s = re.sub(r"\b(ltd|limited|the|and|co|corp|india|pvt|private)\b", " ", s)
        s = re.sub(r"[^a-z0-9]", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    gmp["_gn"] = gmp["IPO"].apply(_norm_name)
    df["_mn"] = df["company"].apply(_norm_name)

    def _find_gmp(row):
        if pd.isna(row["issue_price"]) or pd.isna(row["listing_date"]):
            return np.nan
        cands = gmp[(gmp["gmp_ip"].round(0) == round(row["issue_price"])) &
                    (gmp["gmp_listing_date"] == row["listing_date"])]
        if len(cands) == 0:
            return np.nan
        if len(cands) == 1:
            return cands.iloc[0]["gmp_value_adj"]
        # collision: pick the candidate whose name best overlaps
        mw = set(row["_mn"].split())
        best, best_score = np.nan, -1
        for _, c in cands.iterrows():
            score = len(mw & set(c["_gn"].split()))
            if score > best_score:
                best_score, best = score, c["gmp_value_adj"]
        return best

    df["gmp_value"] = df.apply(_find_gmp, axis=1)
    matched_by_key = df["gmp_value"].notna().sum()
    # Report any collisions that were disambiguated
    coll = df.groupby(df["issue_price"].round(0).astype(str) + "_" +
                      df["listing_date"].dt.strftime("%Y-%m-%d")).size()
    n_coll = (coll > 1).sum()
    print(f"  Matched by (issue_price + listing_date): {matched_by_key}/{len(df)}")
    if n_coll:
        print(f"  ({n_coll} price+date collisions resolved by name overlap)")

    # --- Name-override fallback for the ones not matched by key ---
    # Build a name->gmp lookup from the GMP file
    gmp_by_name = gmp.dropna(subset=["gmp_value_adj"]).copy()
    # exact brand-name index
    name_to_gmp = {}
    for _, r in gmp.iterrows():
        name_to_gmp[str(r["IPO"]).strip()] = r["gmp_value_adj"]

    unmatched = df[df["gmp_value"].isna()]
    override_hits = 0
    for idx, row in unmatched.iterrows():
        legal = row["company"]
        # find any GMP brand-name whose override maps to this legal name
        brand = None
        for b, mapped_legal in GMP_NAME_OVERRIDES.items():
            if mapped_legal == legal:
                brand = b
                break
        if brand and brand in name_to_gmp:
            df.at[idx, "gmp_value"] = name_to_gmp[brand]
            override_hits += 1

    print(f"  Recovered via name-overrides: {override_hits}")

    # --- Report GMP gaps, distinguishing the TWO reasons ---
    # (a) NaN'd by the Rs 0 rule (untracked early-year) - this is CORRECT
    # (b) genuinely couldn't match to the GMP file - may need a new override
    still = df[df["gmp_value"].isna() & (df["year"] >= 2020)].copy()
    # Was each one present in the GMP file (by name) but Rs 0 -> NaN'd,
    # vs truly absent?
    gmp_names = set(gmp["IPO"].astype(str).str.strip())
    def in_gmp_file(company):
        # crude contains-check against GMP brand names
        c = company.lower().replace(" ltd.", "").replace(" limited", "").strip()
        for gn in gmp_names:
            if c[:12] in gn.lower() or gn.lower()[:12] in c:
                return True
        return False
    rule_nulled = [r["company"] for _, r in still.iterrows() if in_gmp_file(r["company"])]
    truly_absent = [r["company"] for _, r in still.iterrows() if not in_gmp_file(r["company"])]
    print(f"  GMP gaps (year>=2020): {len(still)} total")
    print(f"    - NaN'd by Rs 0 rule (in GMP file but untracked, CORRECT): "
          f"{len(rule_nulled)}")
    for c in rule_nulled:
        print(f"        {c}")
    print(f"    - Truly absent (may need a name override): {len(truly_absent)}")
    for c in truly_absent:
        print(f"        {c}")

    # gmp_available flag: 1 if we have a GMP value, else 0
    df["gmp_available"] = df["gmp_value"].notna().astype(int)
    print(f"  gmp_available=1 for {df['gmp_available'].sum()}/{len(df)} IPOs")

    df = df.drop(columns=["_mn"], errors="ignore")
    return df


# ============================================================
# STEP 8: CROSS-VALIDATE AGAINST GHOSH
# ============================================================
def cross_validate_ghosh(df):
    print("\n" + "=" * 68)
    print("STEP 8: Cross-validate issue prices against Ghosh")
    print("=" * 68)
    if not os.path.exists(GHOSH):
        print("  Ghosh file not found - skipping cross-validation.")
        return
    try:
        g = pd.read_excel(GHOSH)
    except Exception as e:
        print(f"  Could not read Ghosh file ({e}) - skipping.")
        return

    # Ghosh column names are known for this file. The issuer column is
    # "Issuer Company" (values end with " IPO") and the final price column
    # is "Final_Issue_Price". (Auto-detection previously misfired because
    # "Issuer Company" contains the substring "issue".)
    name_col = "Issuer Company" if "Issuer Company" in g.columns else None
    price_col = "Final_Issue_Price" if "Final_Issue_Price" in g.columns else None
    if not name_col or not price_col:
        # Fall back to a stricter auto-detect
        for c in g.columns:
            if c.lower().strip() in ("issuer company", "company name"):
                name_col = c; break
        for c in g.columns:
            if "final" in c.lower() and "price" in c.lower():
                price_col = c; break
    if not name_col or not price_col:
        print(f"  Couldn't locate Ghosh name/price columns "
              f"(name={name_col}, price={price_col}) - skipping.")
        return

    def norm(s):
        s = str(s).lower().replace(" ipo", " ")  # Ghosh appends " IPO"
        s = re.sub(r"\b(ltd|limited|the|and|co|corp|india|private|pvt)\b", " ", s)
        s = re.sub(r"[^a-z0-9]", " ", s)          # also removes & . ( )
        return re.sub(r"\s+", " ", s).strip()

    g["_n"] = g[name_col].apply(norm)
    g["_p"] = pd.to_numeric(g[price_col], errors="coerce")
    gmap = g.dropna(subset=["_p"]).drop_duplicates("_n").set_index("_n")["_p"]

    df["_n"] = df["company"].apply(norm)
    overlap = df[df["_n"].isin(gmap.index)].copy()
    overlap["_gp"] = overlap["_n"].map(gmap)
    overlap["_match"] = (overlap["issue_price"] - overlap["_gp"]).abs() < 1.0

    n = len(overlap)
    matches = overlap["_match"].sum()
    print(f"  Overlapping IPOs with Ghosh: {n}")
    if n > 0:
        print(f"  Issue-price concordance: {matches}/{n} ({matches/n*100:.1f}%)")
        mism = overlap[~overlap["_match"]]
        if len(mism) > 0:
            print(f"  Mismatches ({len(mism)}):")
            for _, r in mism.head(10).iterrows():
                print(f"      {r['company']}: ours={r['issue_price']}, ghosh={r['_gp']}")
    df.drop(columns=["_n"], errors="ignore", inplace=True)


# ============================================================
# STEP 9: SELECT COLUMNS + WRITE
# ============================================================
def finalize(df):
    print("\n" + "=" * 68)
    print("STEP 9: Select final columns + write master dataset")
    print("=" * 68)

    # Columns to KEEP in the master (clean parsed values only).
    # NOTE: listing_open/high/low/close are the OUTCOME - kept here only so the
    # target is reproducible, but feature engineering must EXCLUDE them.
    keep = [
        # identifiers
        "company", "listing_date", "year",
        # target(s)
        "first_day_return", "first_day_open_return",
        # issue mechanics (features)
        "issue_price", "face_value", "lot_size",
        "total_issue_size", "fresh_issue", "ofs",
        # demand (features)
        "sub_total", "gmp_value", "gmp_available",
        # financials (features)
        "revenue", "profit", "assets", "net_worth", "borrowing",
        # ownership: hold_pre/hold_post are raw share-count strings that
        # don't parse to useful features (dilution ratio is noisy, with a
        # -186% outlier, and overlaps fresh_issue). Dropped.
        # broker sentiment (features)
        "brokers_subscribe", "brokers_avoid",
        # market context (features, leakage-safe)
        "nifty_close", "vix_close", "nifty_7d_return", "nifty_30d_return",
        # outcome columns (for reference/reproducibility, NOT features)
        "listing_open", "listing_close", "listing_high", "listing_low",
    ]
    keep = [c for c in keep if c in df.columns]
    master = df[keep].copy()

    # Drop the category-subscription columns explicitly (only ~1% coverage)
    for c in ["sub_qib", "sub_nii", "sub_retail"]:
        if c in master.columns:
            master = master.drop(columns=[c])

    os.makedirs(PROC_DIR, exist_ok=True)
    master.to_csv(OUTPUT, index=False)

    print(f"  Master dataset shape: {master.shape}")
    print(f"  Columns ({len(master.columns)}): {list(master.columns)}")
    print(f"\n  Saved: {OUTPUT}")

    # Coverage summary
    print("\n  Final coverage:")
    for c in master.columns:
        nn = master[c].notna().sum()
        print(f"    {c:<22s} {nn:>3}/{len(master)} ({nn/len(master)*100:3.0f}%)")

    return master


# ============================================================
# MAIN
# ============================================================
def main():
    print("#" * 68)
    print("# BUILDING MASTER IPO DATASET")
    print("#" * 68)

    det = load_details()
    df = parse_numeric(det)
    df = drop_reits(df)
    df = compute_target(df)
    df = parse_dates(df)
    df = merge_market(df)
    df = merge_gmp(df)
    cross_validate_ghosh(df)
    master = finalize(df)

    print("\n" + "#" * 68)
    print("# DONE")
    print("#" * 68)
    print(f"  {len(master)} equity IPOs written to {OUTPUT}")
    print("  Reminder: feature engineering must EXCLUDE the listing_open/")
    print("  close/high/low columns (they are the outcome).")


if __name__ == "__main__":
    main()