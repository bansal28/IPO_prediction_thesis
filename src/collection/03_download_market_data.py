"""
STEP 03: Download Nifty 50 and India VIX daily data
====================================================
Downloads two daily time series from Yahoo Finance:

  1. Nifty 50 (^NSEI)      — India's benchmark equity index
  2. India VIX (^INDIAVIX) — implied volatility index (India's "fear gauge")

These give us market context for each IPO's listing day. In the cleaning
step, for each IPO we'll look up the Nifty close and VIX close on the
DAY BEFORE listing (to avoid leakage — you can't know listing-day
Nifty in the morning before markets open).

Setup:
    pip install yfinance pandas certifi

Run:
    python src/collection/03_download_market_data.py

Outputs:
    data/raw/raw_nifty50_daily.csv
    data/raw/raw_india_vix_daily.csv

Note on file format:
    Yahoo Finance's CSV output includes 2 metadata header rows at the
    top ("Ticker" / "Date"). This is a yfinance library quirk, not a
    bug in this script. The cleaning step handles this with skiprows=2.

Runtime: ~30 seconds.
"""

# SSL fix for macOS — must run before any network imports
import certifi
import os
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import yfinance as yf
import pandas as pd
from datetime import datetime

# ============================================================
# CONFIG
# ============================================================
START_DATE = "2019-01-01"
END_DATE = datetime.today().strftime("%Y-%m-%d")  # today

OUTPUT_DIR = "data/raw"
NIFTY_FILE = os.path.join(OUTPUT_DIR, "raw_nifty50_daily.csv")
VIX_FILE = os.path.join(OUTPUT_DIR, "raw_india_vix_daily.csv")


# ============================================================
# Download one ticker with basic sanity checks
# ============================================================
def download_ticker(ticker, name, output_file):
    """Download one ticker's daily history and save to CSV."""
    print(f"\nDownloading {name} ({ticker})...")
    df = yf.download(
        ticker,
        start=START_DATE,
        end=END_DATE,
        progress=False,   # cleaner terminal output
        auto_adjust=False,
    )

    if len(df) == 0:
        print(f"  ⚠  No data returned for {ticker}!")
        print(f"     Common causes: rate limiting, SSL issues, or ticker changed.")
        print(f"     Try: pip install --upgrade yfinance")
        return None

    df.to_csv(output_file)

    # Report basic stats
    print(f"  ✓ {len(df)} trading days: {df.index.min().date()} → {df.index.max().date()}")
    print(f"     Saved: {output_file}")
    return df


# ============================================================
# MAIN
# ============================================================
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print("MARKET DATA DOWNLOAD")
    print(f"  Range: {START_DATE} → {END_DATE}")
    print("=" * 60)

    nifty = download_ticker("^NSEI", "Nifty 50", NIFTY_FILE)
    vix = download_ticker("^INDIAVIX", "India VIX", VIX_FILE)

    # ---------- Summary ----------
    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)
    if nifty is not None:
        print(f"  Nifty 50:   {len(nifty)} days  ({nifty.index.min().date()} → {nifty.index.max().date()})")
    if vix is not None:
        print(f"  India VIX:  {len(vix)} days  ({vix.index.min().date()} → {vix.index.max().date()})")

    print(f"\n  Note: files contain 2 yfinance header rows at the top.")
    print(f"  The cleaning script will handle these with skiprows=2.")


if __name__ == "__main__":
    main()