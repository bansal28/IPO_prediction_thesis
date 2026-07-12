"""
STEP 02: Collect IPO detail data from Chittorgarh
==================================================
For each IPO listed in the yearly tracker CSVs (data/raw/chittorgarh/),
visit its detail page on chittorgarh.com and extract the raw data:
  - Issue mechanics (face value, price band, issue price, lot size, sale type)
  - Issue size (total, fresh issue, OFS, share holdings)
  - Company financials (assets, revenue, profit, net worth, borrowings)
  - Broker sentiment (subscribe / avoid counts)
  - Subscription (total and category-wise where available)
  - Listing prices (open, close, high, low)

Values are saved as raw strings. Cleaning happens in a later step.

Prerequisites:
  - data/raw/chittorgarh/  contains the 8 yearly tracker CSVs

Setup (one time):
    pip install playwright pandas
    python -m playwright install chromium

Run:
    python src/collection/02_collect_chittorgarh_details.py

Outputs:
    data/raw/raw_ipo_urls.csv     — list of all IPOs + their detail page URLs
    data/raw/raw_ipo_details.csv  — scraped detail data, one row per IPO
    data/raw/checkpoint.json      — progress checkpoint (safe to delete after
                                    a successful run; used to resume if
                                    interrupted)

Runtime: ~20-25 minutes for ~434 IPOs.  Ctrl+C anytime; re-run resumes.
"""

import asyncio
from playwright.async_api import async_playwright
import pandas as pd
import json
import os
import time
import glob
import re
from datetime import datetime

# ============================================================
# CONFIG
# ============================================================
TRACKER_DIR = "data/raw/chittorgarh"
OUTPUT_DIR = "data/raw"
URLS_FILE = os.path.join(OUTPUT_DIR, "raw_ipo_urls.csv")
DETAILS_FILE = os.path.join(OUTPUT_DIR, "raw_ipo_details.csv")
CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, "checkpoint.json")

# Improvements over the previous version:
#  - Timeout 15s → 45s (caused Vikran Engineering failure last time)
#  - wait_until "domcontentloaded" → "networkidle" (waits for JS to settle)
#  - 3 retries with exponential backoff per IPO
TIMEOUT_MS = 45_000
WAIT_AFTER_LOAD_MS = 1_500
MAX_RETRIES = 3
CHECKPOINT_EVERY = 25


# ============================================================
# STEP A: Build the list of IPOs from the tracker CSVs
# ============================================================
def build_ipo_list_from_trackers():
    """
    Read the 8 yearly tracker CSVs and construct a list of IPOs to scrape.
    Each row gives us the company name and (indirectly) the year. We need
    to look up each IPO's detail-page URL on Chittorgarh separately, since
    the tracker doesn't include URLs.

    Strategy: use Chittorgarh's URL pattern. The IPO performance tracker
    page for year Y (https://www.chittorgarh.com/ipo/ipo_perf_tracker.asp?year=Y)
    contains links to each IPO's detail page. We visit each yearly tracker
    page once, extract the (company, detail_url) pairs, and save them all.
    """
    tracker_files = sorted(glob.glob(os.path.join(TRACKER_DIR, "*.csv")))
    if not tracker_files:
        raise FileNotFoundError(
            f"No tracker CSVs found in {TRACKER_DIR}/  — "
            f"please download the yearly performance trackers from "
            f"chittorgarh.com first."
        )
    print(f"Found {len(tracker_files)} tracker files:")
    for f in tracker_files:
        n = sum(1 for _ in open(f)) - 1  # rows minus header
        print(f"  {os.path.basename(f)}  ({n} IPOs)")

    # We don't actually need to load the CSVs to build the URL list — we'll
    # get URLs from the tracker web pages. But we use the tracker files to
    # infer which YEARS to visit.
    years = set()
    for f in tracker_files:
        # Extract year from filename like "ipo-performance-mainline-2024.csv"
        m = re.search(r"(\d{4})", os.path.basename(f))
        if m:
            years.add(int(m.group(1)))
    return sorted(years)


# ============================================================
# STEP B: Collect IPO detail-page URLs from the tracker web pages
# ============================================================
async def collect_urls_for_year(page, year):
    """Visit the tracker page for one year and get (company, url) rows."""
    url = f"https://www.chittorgarh.com/ipo/ipo_perf_tracker.asp?year={year}"
    await page.goto(url, wait_until="networkidle", timeout=TIMEOUT_MS)
    await page.wait_for_timeout(WAIT_AFTER_LOAD_MS)

    # Extract the data table rows. Column 0 is the company name (with a link
    # to the detail page), the other columns are listing info.
    return await page.evaluate('''() => {
        const table = document.querySelector('table.data-table');
        if (!table) return [];
        const rows = [];
        for (const tr of table.querySelectorAll('tr')) {
            const tds = tr.querySelectorAll('td');
            if (tds.length < 5) continue;
            const bold = tds[0].querySelector('b');
            if (!bold) continue;
            const link = tds[0].querySelector('a[href*="/ipo/"]');
            rows.push({
                company:         bold.textContent.trim(),
                listed_on:       tds[1] ? tds[1].textContent.trim() : '',
                issue_price:     tds[2] ? tds[2].textContent.trim() : '',
                listing_close:   tds[3] ? tds[3].textContent.trim() : '',
                listing_gain:    tds[4] ? tds[4].textContent.trim() : '',
                detail_url:      link ? link.href : ''
            });
        }
        return rows;
    }''')


# ============================================================
# STEP C: Scrape one IPO detail page
# ============================================================
async def scrape_detail_page(page, url):
    """
    Extract raw table data from one Chittorgarh IPO detail page.
    Returns a dict of raw string values.  Never raises — errors surface
    as an 'error' key on the result.
    """
    await page.goto(url, wait_until="networkidle", timeout=TIMEOUT_MS)
    await page.wait_for_timeout(WAIT_AFTER_LOAD_MS)

    return await page.evaluate('''() => {
        // Walk every table on the page. Each table has a first row whose
        // first cell describes what the table contains ("IPO Date & Price
        // Band", "Total Issue Size", "Period Ended", etc.). We use that as
        // a router.
        const r = {};

        for (const t of document.querySelectorAll('table')) {
            const firstRow = t.querySelector('tr');
            if (!firstRow) continue;
            const firstCells = [];
            firstRow.querySelectorAll('th,td').forEach(c => firstCells.push(c.textContent.trim()));
            if (firstCells.length < 2) continue;
            const routerText = firstCells[0].toLowerCase();

            // --- IPO Date & Price Band table ---
            if (routerText.includes('ipo date')) {
                for (const tr of t.querySelectorAll('tr')) {
                    const c = tr.querySelectorAll('td,th');
                    if (c.length < 2) continue;
                    const key = c[0].textContent.trim();
                    const val = c[1].textContent.trim();
                    if (key === 'Face Value')  r.face_value = val;
                    if (key === 'Price Band')  r.price_band = val;
                    if (key === 'Issue Price') r.issue_price = val;
                    if (key === 'Lot Size')    r.lot_size = val;
                    if (key === 'Sale Type')   r.sale_type = val;
                }
            }

            // --- Total Issue Size table ---
            if (routerText.includes('total issue size')) {
                for (const tr of t.querySelectorAll('tr')) {
                    const c = tr.querySelectorAll('td,th');
                    if (c.length < 2) continue;
                    const key = c[0].textContent.trim();
                    const val = c[1].textContent.trim();
                    if (key === 'Total Issue Size')            r.total_issue_size = val;
                    if (key.includes('Fresh Issue'))           r.fresh_issue = val;
                    if (key === 'Offer for Sale')              r.ofs = val;
                    if (key === 'Share Holding Pre Issue')     r.hold_pre = val;
                    if (key === 'Share Holding Post Issue')    r.hold_post = val;
                }
            }

            // --- Financials table ("Period Ended ...") ---
            if (routerText.includes('period ended')) {
                for (const tr of t.querySelectorAll('tr')) {
                    const c = tr.querySelectorAll('td,th');
                    if (c.length < 2) continue;
                    const label = c[0].textContent.trim();
                    const val = c[1].textContent.trim();
                    if (label.includes('Assets'))               r.assets = val;
                    if (label.includes('Total Income') ||
                        label.includes('Revenue'))              r.revenue = val;
                    if (label.includes('Profit After Tax'))     r.profit = val;
                    if (label.includes('NET Worth') ||
                        label.includes('Net Worth'))            r.net_worth = val;
                    if (label.includes('Total Borrowing'))      r.borrowing = val;
                }
            }

            // --- Broker review table ---
            if (routerText.includes('review by')) {
                for (const tr of t.querySelectorAll('tr')) {
                    const c = tr.querySelectorAll('td,th');
                    if (c.length >= 5 && c[0].textContent.trim() === 'Brokers') {
                        r.brokers_subscribe = c[1].textContent.trim();
                        r.brokers_avoid = c[4].textContent.trim();
                    }
                    if (c.length >= 2 && c[0].textContent.trim() === 'Members') {
                        r.members_subscribe = c[1].textContent.trim();
                    }
                }
            }

            // --- Subscription table ---
            if (routerText.includes('category') &&
                firstCells.some(c => c.toLowerCase().includes('subscription'))) {
                for (const tr of t.querySelectorAll('tr')) {
                    const c = tr.querySelectorAll('td,th');
                    if (c.length < 2) continue;
                    const cat = c[0].textContent.trim().toLowerCase();
                    const val = c[1].textContent.trim();
                    if (cat.includes('qib'))                            r.sub_qib = val;
                    if (cat.includes('nii') || cat.includes('hni'))     r.sub_nii = val;
                    if (cat.includes('retail') && !cat.includes('nii')) r.sub_retail = val;
                    if (cat === 'total')                                r.sub_total = val;
                }
            }

            // --- Listing day price table ---
            if (routerText.includes('price details')) {
                for (const tr of t.querySelectorAll('tr')) {
                    const c = tr.querySelectorAll('td,th');
                    if (c.length < 2) continue;
                    const key = c[0].textContent.trim();
                    const val = c[1].textContent.trim();
                    if (key === 'Open')       r.listing_open  = val;
                    if (key === 'Last Trade') r.listing_close = val;
                    if (key === 'High')       r.listing_high  = val;
                    if (key === 'Low')        r.listing_low   = val;
                }
            }
        }
        return r;
    }''')


# ============================================================
# Retry wrapper
# ============================================================
async def scrape_with_retries(page, url):
    """Try scrape_detail_page up to MAX_RETRIES times with 2s / 4s / 8s backoff."""
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await scrape_detail_page(page, url)
        except Exception as e:
            last_error = str(e)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)  # 2s, 4s, 8s
    return {"error": f"All {MAX_RETRIES} attempts failed. Last: {last_error[:120]}"}


# ============================================================
# MAIN
# ============================================================
async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Load checkpoint if resuming
    state = {"urls": [], "details": [], "done": []}
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE) as f:
                state = json.load(f)
            print(f"Resuming from checkpoint: "
                  f"{len(state['urls'])} URLs, "
                  f"{len(state['details'])} details already scraped")
        except Exception as e:
            print(f"Checkpoint unreadable ({e}); starting fresh.")
            state = {"urls": [], "details": [], "done": []}

    years = build_ipo_list_from_trackers()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # ---------- STEP B: get URLs if we don't have them yet ----------
        if not state["urls"]:
            print("\n" + "=" * 60)
            print("Collecting IPO URLs from yearly tracker pages")
            print("=" * 60)
            for year in years:
                print(f"  {year}...", end=" ", flush=True)
                try:
                    rows = await collect_urls_for_year(page, year)
                    for r in rows:
                        r["year"] = year
                    state["urls"].extend(rows)
                    print(f"{len(rows)} IPOs")
                except Exception as e:
                    print(f"ERROR: {e}")

            pd.DataFrame(state["urls"]).to_csv(URLS_FILE, index=False)
            with open(CHECKPOINT_FILE, "w") as f:
                json.dump(state, f, default=str)
            print(f"\nSaved: {URLS_FILE} ({len(state['urls'])} IPOs)")

        # ---------- STEP C: scrape detail pages ----------
        print("\n" + "=" * 60)
        print("Scraping detail pages")
        print("=" * 60)

        done_set = set(state.get("done", []))
        remaining = [
            u for u in state["urls"]
            if u["company"] not in done_set
            and len(u.get("detail_url", "")) > 10
        ]
        print(f"  Already done: {len(done_set)}   Remaining: {len(remaining)}")

        t0 = time.time()
        for idx, ipo in enumerate(remaining):
            raw = await scrape_with_retries(page, ipo["detail_url"])

            # Attach identifiers so we don't lose them on errors
            raw["company"]    = ipo["company"]
            raw["detail_url"] = ipo["detail_url"]
            raw["year"]       = ipo.get("year")
            raw["listed_on"]  = ipo.get("listed_on", "")

            state["details"].append(raw)
            state["done"].append(ipo["company"])

            # Progress + checkpoint
            if (idx + 1) % CHECKPOINT_EVERY == 0 or idx == len(remaining) - 1:
                elapsed = time.time() - t0
                rate = (idx + 1) / elapsed if elapsed > 0 else 0
                eta = (len(remaining) - idx - 1) / rate if rate > 0 else 0
                errs = sum(1 for d in state["details"] if d.get("error"))
                print(f"  [{idx+1}/{len(remaining)}]  "
                      f"{rate:.1f}/sec  ETA: {eta:.0f}s  errors: {errs}")
                with open(CHECKPOINT_FILE, "w") as f:
                    json.dump(state, f, default=str)

        await browser.close()

    # ---------- Save final CSV ----------
    df = pd.DataFrame(state["details"])
    df.to_csv(DETAILS_FILE, index=False)

    n_total = len(df)
    n_errors = df["error"].notna().sum() if "error" in df.columns else 0
    n_have_close = df["listing_close"].notna().sum() if "listing_close" in df.columns else 0
    n_have_price = df["issue_price"].notna().sum() if "issue_price" in df.columns else 0

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)
    print(f"  Total IPOs scraped:      {n_total}")
    print(f"  Errors:                  {n_errors}")
    print(f"  Have listing_close:      {n_have_close}/{n_total}")
    print(f"  Have issue_price:        {n_have_price}/{n_total}")
    print(f"  Saved: {DETAILS_FILE}")

    if n_errors > 0:
        print(f"\n  IPOs with errors:")
        for _, r in df[df["error"].notna()].iterrows():
            print(f"    - {r['company']}: {r['error'][:80]}")


if __name__ == "__main__":
    asyncio.run(main())