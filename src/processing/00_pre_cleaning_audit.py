"""
STEP 00 (audit): Pre-cleaning verification of all raw data files
================================================================
Run this BEFORE the cleaning step. It verifies every raw file that will
feed 01_data_cleaning.py is present, complete, and mergeable - and it
surfaces anything that needs attention.

This is READ-ONLY. It changes nothing. It only reports.

What it checks:
  1. raw_ipo_details.csv   - the spine (434 IPOs, REIT count, target computable)
  2. raw_gmp_data.csv      - GMP per-year counts, the Rs 0 pattern
  3. raw_nifty50_daily.csv - Nifty daily, date range, prior-day coverage
  4. raw_india_vix_daily.csv - VIX daily
  5. chittorgarh/*.csv     - the 8 yearly trackers (issue-price fallback)
  6. ghosh_mainboard_v18.xlsx - cross-validation dataset
  7. prospectus PDFs        - count of valid PDFs on disk
  MERGE KEYS: date formats, GMP<->details matchability, market coverage

Run:
    python src/processing/00_pre_cleaning_audit.py

Everything is printed to the terminal. Copy the output and share it.
"""

import pandas as pd
import os
import glob
import re
import warnings
warnings.filterwarnings("ignore")

# ============================================================
# PATHS  (edit here if your layout differs)
# ============================================================
RAW_DIR = "data/raw"
PDF_DIR = "data/prospectus_pdfs"
TRACKER_DIR = os.path.join(RAW_DIR, "chittorgarh")

DETAILS = os.path.join(RAW_DIR, "raw_ipo_details.csv")
GMP = os.path.join(RAW_DIR, "raw_gmp_data.csv")
NIFTY = os.path.join(RAW_DIR, "raw_nifty50_daily.csv")
VIX = os.path.join(RAW_DIR, "raw_india_vix_daily.csv")
GHOSH = os.path.join(RAW_DIR, "ghosh_mainboard_v18.xlsx")

# REIT / non-equity identification rule (locked decision)
REIT_REGEX = r"REIT|Trust|InvIT|Embassy Office|Mindspace Business"


# ============================================================
# Small parsing helpers (same logic cleaning will use)
# ============================================================
def clean_price(s):
    if pd.isna(s):
        return None
    s = str(s).replace("₹", "").replace(",", "").replace(" per share", "").strip()
    try:
        return float(s)
    except Exception:
        return None


def clean_x(s):
    """Parse subscription like '111.91x' -> 111.91."""
    if pd.isna(s):
        return None
    m = re.search(r"([\d.]+)", str(s))
    return float(m.group(1)) if m else None


def section(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def ok(msg):    print(f"  [OK]   {msg}")
def warn(msg):  print(f"  [WARN] {msg}")
def info(msg):  print(f"  {msg}")


# ============================================================
# 1. DETAILS
# ============================================================
def audit_details():
    section("1. raw_ipo_details.csv  (the spine of the master dataset)")
    if not os.path.exists(DETAILS):
        warn(f"NOT FOUND: {DETAILS}")
        return None
    det = pd.read_csv(DETAILS)
    info(f"Shape: {det.shape}")

    dups = det["company"].duplicated().sum()
    (ok if dups == 0 else warn)(f"Unique companies: {det['company'].nunique()}, duplicates: {dups}")

    reit = det["company"].str.contains(REIT_REGEX, case=False, na=False)
    info(f"REITs/InvITs to drop: {reit.sum()}  ->  {len(det) - reit.sum()} equity IPOs remain")
    if reit.sum() > 0:
        for c in det[reit]["company"].tolist():
            info(f"      drop: {c}")

    # Target computable?
    det["_ip"] = det["issue_price"].apply(clean_price)
    det["_lc"] = det["listing_close"].apply(clean_price)
    non_reit = det[~reit]
    comp = non_reit.dropna(subset=["_ip", "_lc"])
    (ok if len(comp) == len(non_reit) else warn)(
        f"first_day_return computable: {len(comp)}/{len(non_reit)} non-REIT IPOs")

    # Show the return distribution as a sanity check
    if len(comp):
        comp = comp.copy()
        comp["_fdr"] = (comp["_lc"] - comp["_ip"]) / comp["_ip"] * 100
        info(f"Return sanity: mean {comp['_fdr'].mean():.1f}%, "
             f"median {comp['_fdr'].median():.1f}%, "
             f"min {comp['_fdr'].min():.1f}% ({comp.loc[comp['_fdr'].idxmin(),'company']}), "
             f"max {comp['_fdr'].max():.1f}% ({comp.loc[comp['_fdr'].idxmax(),'company']})")
        info(f"             % positive: {(comp['_fdr']>0).mean()*100:.1f}%")

    # Coverage of key columns (non-REIT)
    info(f"\n  Key column coverage (non-REIT, n={len(non_reit)}):")
    for col in ["issue_price", "listing_open", "listing_close", "sub_total",
                "sub_qib", "sub_nii", "sub_retail",
                "revenue", "profit", "assets", "net_worth", "borrowing",
                "fresh_issue", "ofs", "brokers_subscribe", "brokers_avoid"]:
        if col in non_reit.columns:
            nn = non_reit[col].notna().sum()
            info(f"    {col:<18s} {nn:>3}/{len(non_reit)} ({nn/len(non_reit)*100:3.0f}%)")
        else:
            warn(f"    {col:<18s} COLUMN MISSING")
    return det


# ============================================================
# 2. GMP
# ============================================================
def audit_gmp():
    section("2. raw_gmp_data.csv")
    if not os.path.exists(GMP):
        warn(f"NOT FOUND: {GMP}")
        return None
    gmp = pd.read_csv(GMP)
    info(f"Shape: {gmp.shape}")
    info(f"Columns: {list(gmp.columns)}")

    exp = {2019: 4, 2020: 16, 2021: 66, 2022: 39, 2023: 60, 2024: 93, 2025: 108, 2026: 32}
    info("\n  Per-year counts:")
    all_ok = True
    for yr in sorted(exp):
        got = (gmp["year"] == yr).sum()
        flag = "OK" if got >= exp[yr] else f"SHORT by {exp[yr]-got}"
        if got < exp[yr] and yr != 2019:
            all_ok = False
        info(f"    {yr}: {got:>3} / {exp[yr]}   {flag}")
    (ok if all_ok else warn)(f"Total GMP rows: {len(gmp)}")

    # The Rs 0 pattern (drives the cleaning rule)
    def pg(s):
        if pd.isna(s): return None
        s = str(s).replace("₹", "").replace(",", "").strip()
        try: return float(s)
        except: return None
    gmp["_g"] = gmp["GMP"].apply(pg)
    info("\n  GMP=Rs 0 pattern (drives the cleaning rule):")
    for yr in sorted(exp):
        z = ((gmp["year"] == yr) & (gmp["_g"] == 0)).sum()
        n = (gmp["year"] == yr).sum()
        if z > 0:
            info(f"    {yr}: {z}/{n} rows are Rs 0")
    info("    Rule: 2019 all->NaN; 2020 ->NaN if listing gain>15%; 2021+ keep as real")
    return gmp


# ============================================================
# 3 & 4. MARKET DATA
# ============================================================
def audit_market(path, name):
    section(f"{name} ({os.path.basename(path)})")
    if not os.path.exists(path):
        warn(f"NOT FOUND: {path}")
        return None
    # yfinance writes 3 header rows then data; 7 columns incl Adj Close
    df = pd.read_csv(path, skiprows=3,
                     names=["date", "adj_close", "close", "high", "low", "open", "volume"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    valid = df.dropna(subset=["date", "close"])
    dups = valid["date"].duplicated().sum()
    (ok if dups == 0 else warn)(
        f"{len(valid)} valid rows, {valid['date'].min().date()} -> {valid['date'].max().date()}, "
        f"duplicate dates: {dups}")
    info(f"    close range: {valid['close'].min():.1f} to {valid['close'].max():.1f}")
    return valid


# ============================================================
# 5. TRACKERS
# ============================================================
def audit_trackers():
    section("5. Chittorgarh trackers (issue-price fallback)")
    files = sorted(glob.glob(os.path.join(TRACKER_DIR, "*.csv")))
    if not files:
        warn(f"NO tracker CSVs in {TRACKER_DIR}")
        return
    total = 0
    for f in files:
        n = len(pd.read_csv(f))
        total += n
        info(f"    {os.path.basename(f):<45s} {n} IPOs")
    ok(f"{len(files)} files, {total} total rows")


# ============================================================
# 6. GHOSH
# ============================================================
def audit_ghosh():
    section("6. Ghosh dataset (cross-validation)")
    if not os.path.exists(GHOSH):
        warn(f"NOT FOUND: {GHOSH} (cross-validation will be skipped in cleaning)")
        return
    g = pd.read_excel(GHOSH)
    ok(f"Shape: {g.shape}")


# ============================================================
# 7. PROSPECTUS PDFs
# ============================================================
def audit_pdfs():
    section("7. Prospectus PDFs on disk")
    if not os.path.isdir(PDF_DIR):
        warn(f"NOT FOUND: {PDF_DIR}")
        return
    pdfs = [f for f in os.listdir(PDF_DIR) if f.lower().endswith(".pdf")]
    big = [f for f in pdfs
           if os.path.getsize(os.path.join(PDF_DIR, f)) > 300_000]
    ok(f"{len(pdfs)} PDF files, {len(big)} are > 300 KB (real prospectuses)")
    # Validation log if present
    vlog = os.path.join(PDF_DIR, "_validation_log.csv")
    if os.path.exists(vlog):
        v = pd.read_csv(vlog)
        with_risk = (v["has_risk"] == True).sum() if "has_risk" in v.columns else "?"
        info(f"    validation log: {len(v)} entries, {with_risk} with confirmed Risk Factors")


# ============================================================
# 8. MERGE-KEY VERIFICATION
# ============================================================
def audit_merge_keys(det, gmp, nifty):
    section("8. MERGE-KEY VERIFICATION (where cleaning could silently break)")
    if det is None:
        warn("details missing - skipping merge checks")
        return

    # A. Date formats
    det["_ld"] = pd.to_datetime(det["listed_on"], errors="coerce")
    info("A. Listing dates")
    info(f"   details 'listed_on' samples: {det['listed_on'].dropna().head(2).tolist()}")
    dparse = det["_ld"].notna().sum()
    (ok if dparse == len(det) else warn)(f"   details dates parse: {dparse}/{len(det)}")

    if gmp is not None:
        gmp["_ld"] = pd.to_datetime(gmp["Listing Date"], format="%d-%b-%y", errors="coerce")
        info(f"   gmp 'Listing Date' samples:  {gmp['Listing Date'].dropna().head(2).tolist()}")
        gparse = gmp["_ld"].notna().sum()
        (ok if gparse == len(gmp) else warn)(f"   gmp dates parse: {gparse}/{len(gmp)}")

        # B. GMP <-> details matchability by (price + date)
        det["_ip"] = det["issue_price"].apply(clean_price)
        gmp["_ip"] = gmp["IPO Price"].apply(clean_price)
        dk = det.dropna(subset=["_ip", "_ld"]).copy()
        dk["k"] = dk["_ip"].round(0).astype(str) + "_" + dk["_ld"].dt.strftime("%Y-%m-%d")
        gk = gmp.dropna(subset=["_ip", "_ld"]).copy()
        gk["k"] = gk["_ip"].round(0).astype(str) + "_" + gk["_ld"].dt.strftime("%Y-%m-%d")
        reit = dk["company"].str.contains(REIT_REGEX, case=False, na=False)
        dk_ne = dk[~reit]
        m = dk_ne["k"].isin(set(gk["k"])).sum()
        info("\nB. GMP-to-details matching (by issue_price + listing_date)")
        info(f"   Non-REIT IPOs matched to GMP: {m}/{len(dk_ne)}")
        info(f"   Remainder ({len(dk_ne)-m}) need name-override fallback "
             f"(Paytm->One 97, CAMS->Computer Age, etc.)")

    # C. Market data prior-day coverage
    if nifty is not None:
        ndates = set(nifty["date"].dt.strftime("%Y-%m-%d"))
        covered = 0
        for ld in det["_ld"].dropna():
            for d in range(1, 8):
                if (ld - pd.Timedelta(days=d)).strftime("%Y-%m-%d") in ndates:
                    covered += 1
                    break
        n = det["_ld"].notna().sum()
        info("\nC. Market data prior-trading-day coverage (leakage-safe merge)")
        (ok if covered == n else warn)(
            f"   Listings with a prior-day Nifty value: {covered}/{n}")


# ============================================================
# MAIN
# ============================================================
def main():
    print("#" * 72)
    print("# PRE-CLEANING AUDIT - all raw files feeding 01_data_cleaning.py")
    print("#" * 72)

    det = audit_details()
    gmp = audit_gmp()
    nifty = audit_market(NIFTY, "3. Nifty 50 daily")
    _vix = audit_market(VIX, "4. India VIX daily")
    audit_trackers()
    audit_ghosh()
    audit_pdfs()
    audit_merge_keys(det, gmp, nifty)

    section("AUDIT COMPLETE")
    info("Review the [WARN] lines above (if any). If everything is [OK],")
    info("the raw data is ready and we can write 01_data_cleaning.py.")


if __name__ == "__main__":
    main()