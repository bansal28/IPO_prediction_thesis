"""
00_data_audit.py
================
Run this BEFORE cleaning to understand what raw data you have,
how the sources connect, and what issues need fixing.

Run from the project root:
    python src/processing/00_data_audit.py

No dependencies beyond pandas and openpyxl:
    pip install pandas openpyxl
"""

import pandas as pd
import os

RAW = "data/raw"

print("=" * 70)
print("COMPLETE DATA AUDIT")
print("=" * 70)


# ============================================================
# 1. Chittorgarh performance tracker CSVs (your manual downloads)
# ============================================================
print("\n\n📁 SOURCE 1: Chittorgarh performance tracker (Step 1)")
print("-" * 70)
chit_dir = os.path.join(RAW, "chittorgarh")
total_s1 = 0
for f in sorted(os.listdir(chit_dir)):
    if f.startswith("."): continue
    df = pd.read_csv(os.path.join(chit_dir, f))
    total_s1 += len(df)
    print(f"  {f:50s} {len(df):4d} rows")
print(f"  {'TOTAL':50s} {total_s1:4d}")

sample = pd.read_csv(os.path.join(chit_dir, sorted(os.listdir(chit_dir))[0]))
print(f"\n  Columns: {list(sample.columns)}")
print(f"  Sample row:")
for col in sample.columns:
    print(f"    {col}: {sample.iloc[0][col]}")


# ============================================================
# 2. Scraped detail data (from Step 3 script)
# ============================================================
print("\n\n📁 SOURCE 2: Scraped detail pages (Step 3)")
print("-" * 70)
det = pd.read_csv(os.path.join(RAW, "raw_ipo_details.csv"))
print(f"  Rows: {len(det)}")
print(f"  Columns ({len(det.columns)}): {list(det.columns)}")
errors = det["error"].notna().sum() if "error" in det.columns else 0
print(f"  Errors: {errors}")

print(f"\n  Field coverage:")
for col in det.columns:
    if col in ["company", "detail_url", "year", "listed_on", "error"]:
        continue
    if det[col].dtype == object:
        n = (det[col].notna() & (det[col].str.strip() != "")).sum()
    else:
        n = det[col].notna().sum()
    pct = n / len(det) * 100
    status = "✓" if pct > 80 else ("~" if pct > 50 else "✗")
    print(f"    {status} {col:25s} {n:4d}/{len(det)}  ({pct:5.1f}%)")


# ============================================================
# 3. Scraped URL list
# ============================================================
print("\n\n📁 SOURCE 3: Scraped URL list")
print("-" * 70)
urls = pd.read_csv(os.path.join(RAW, "raw_ipo_urls.csv"))
print(f"  Rows: {len(urls)}")
print(f"  Columns: {list(urls.columns)}")
print(f"  Per year:")
for yr in sorted(urls["year"].unique()):
    print(f"    {int(yr)}: {len(urls[urls['year']==yr])}")


# ============================================================
# 4. Market data
# ============================================================
print("\n\n📁 SOURCE 4: Market data (Step 4)")
print("-" * 70)
for fname in ["raw_nifty50_daily.csv", "raw_india_vix_daily.csv"]:
    df = pd.read_csv(os.path.join(RAW, fname))
    print(f"\n  {fname}:")
    print(f"    Total rows: {len(df)}")
    print(f"    Row 0 (junk): {df.iloc[0].tolist()}")
    print(f"    Row 1 (junk): {df.iloc[1].tolist()}")
    print(f"    Row 2 (first real): {df.iloc[2].tolist()}")
    dates = df.iloc[2:]["Price"].dropna()
    print(f"    Actual data rows: {len(dates)}")
    print(f"    Date range: {dates.iloc[0]} to {dates.iloc[-1]}")


# ============================================================
# 5. GMP data
# ============================================================
print("\n\n📁 SOURCE 5: GMP data (Step 5)")
print("-" * 70)
gmp = pd.read_csv(os.path.join(RAW, "raw_gmp_data.csv"))
print(f"  Rows: {len(gmp)}")
print(f"  Columns: {list(gmp.columns)}")
print(f"  Per year:")
for yr in sorted(gmp["year"].unique()):
    print(f"    {int(yr)}: {len(gmp[gmp['year']==yr])}")
print(f"\n  Sample (row 2):")
for col in gmp.columns:
    print(f"    {col}: {gmp.iloc[2][col]}")


# ============================================================
# 6. Prospectus links
# ============================================================
print("\n\n📁 SOURCE 6: Prospectus PDF links (Step 6)")
print("-" * 70)
links = pd.read_csv(os.path.join(RAW, "raw_prospectus_links_v2.csv"))
print(f"  Rows: {len(links)}")
has_pdf = links["pdf_url"].notna().sum()
print(f"  Has PDF link: {has_pdf}/{len(links)} ({has_pdf/len(links)*100:.1f}%)")

pdf_dir = "data/prospectus_pdfs"
if os.path.isdir(pdf_dir):
    pdfs = [f for f in os.listdir(pdf_dir) if f.endswith(".pdf")]
    print(f"  PDFs on disk: {len(pdfs)}")
else:
    print(f"  PDFs folder not found — add your prospectus_pdfs/ to data/")


# ============================================================
# 7. Ghosh dataset
# ============================================================
print("\n\n📁 SOURCE 7: Ghosh et al. dataset (Step 7)")
print("-" * 70)
ghosh = pd.read_excel(os.path.join(RAW, "ghosh_mainboard_v18.xlsx"))
print(f"  Rows: {len(ghosh)}, Columns: {len(ghosh.columns)}")
ghosh["Listing Date"] = pd.to_datetime(ghosh["Listing Date"], errors="coerce")
print(f"  Date range: {ghosh['Listing Date'].min().date()} to {ghosh['Listing Date'].max().date()}")
ghosh_overlap = ghosh[ghosh["Listing Date"].dt.year.between(2019, 2023)]
print(f"  Overlapping with our data (2019-2023): {len(ghosh_overlap)} IPOs")


# ============================================================
# 8. Cross-source matching check
# ============================================================
print("\n\n📁 CROSS-SOURCE MATCHING")
print("-" * 70)

# Details vs URLs
det_names = set(det["company"].dropna().str.strip())
url_names = set(urls["company"].dropna().str.strip())
print(f"\n  Details vs URLs:")
print(f"    Match: {len(det_names & url_names)}/{len(det_names)}  ", end="")
print("✓" if det_names == url_names else "MISMATCH")

# GMP matching
gmp_names = set(gmp["IPO▲▼"].dropna().str.strip())
exact = len(det_names & gmp_names)
print(f"\n  Details vs GMP:")
print(f"    Exact match: {exact}/{len(gmp_names)}")
print(f"    GMP uses SHORT names — fuzzy matching needed in cleaning")
print(f"    Examples:")
for _, row in gmp.head(5).iterrows():
    gn = row["IPO▲▼"]
    matches = [d for d in det_names if gn.lower() in d.lower()]
    m = matches[0] if matches else "NO MATCH"
    print(f"      GMP '{gn}' → Detail '{m}'")

# Ghosh matching
ghosh_names = set(ghosh["Company Name"].dropna().str.strip())
det_short = {n[:20].lower(): n for n in det_names}
ghosh_short = {n[:20].lower(): n for n in ghosh_names}
fuzzy = len(set(det_short.keys()) & set(ghosh_short.keys()))
print(f"\n  Details vs Ghosh:")
print(f"    Exact match: {len(det_names & ghosh_names)}")
print(f"    Fuzzy match (first 20 chars): {fuzzy}")


# ============================================================
# SUMMARY
# ============================================================
print(f"\n\n{'=' * 70}")
print("SUMMARY")
print(f"{'=' * 70}")
print(f"""
  434 mainboard IPOs (2019-2026)

  Per-IPO data: listing outcomes, subscription, financials,
  broker ratings, issue details, GMP (410/434), prospectus PDFs (427/434)

  Market context: Nifty 50 + India VIX daily (Jan 2019 - Jul 2026)

  Cross-validation: Ghosh dataset overlaps ~185 IPOs (2019-2023)

  Issues for cleaning:
    1. Market CSVs: 2 junk header rows from yfinance
    2. GMP names shortened vs detail names (fuzzy join needed)
    3. sub_qib/nii/retail only 1.6% coverage (use sub_total instead)
    4. fresh_issue/ofs ~80% (normal — some IPOs are purely one type)
    5. 1 scraping error (Vikran Engineering)
    6. All detail fields are raw strings needing number parsing
    7. Ghosh names don't exactly match ours (fuzzy join for validation)
""")