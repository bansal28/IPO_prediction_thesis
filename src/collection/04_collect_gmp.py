"""
STEP 04: Collect GMP (Grey Market Premium) data from InvestorGain
==================================================================
Source: InvestorGain.com GMP Performance Tracker (mainboard IPOs)
        https://www.investorgain.com/report/ipo-gmp-performance-tracker/377/ipo/?year=YYYY

GMP is an unofficial, unregulated pre-listing price signal. It correlates
strongly (~0.8) with mainboard first-day returns and is one of the most
valuable features in this project. We use InvestorGain as the SINGLE
source for GMP, for methodological consistency (mixing GMP sources would
introduce bias - different trackers report different values).

Known upstream limitations (documented, not bugs):
  - 2019: InvestorGain only tracked GMP for ~4 of ~20 IPOs. Unrecoverable.
  - "GMP = Rs 0" sometimes means "not tracked" (handled later in cleaning).

HOW PAGINATION WORKS (verified against the live page):
  InvestorGain's table is JavaScript-rendered and paginated at 100 rows
  per page using a custom control:
      <div class="pagination-wrap"> First Prev 1/2 Next Last </div>
  with page buttons <button class="pagination-btn">Next</button>.
  Years with more than 100 IPOs (e.g. 2025 has 108 across 2 pages) require
  clicking "Next" to reach the remaining rows. This script clicks through
  every page and aggregates all rows.

DESIGN NOTES:
  - This is a ONE-TIME collection. Timeouts are set generously high so no
    page ever fails just for being slow. If a page is slow, we wait.
  - Each page load is retried a few times as a safety net.
  - CHECKPOINT after every year. If it crashes on year N, years already
    scraped are saved and re-running resumes from year N. Delete
    data/raw/gmp_checkpoint.json to force a completely fresh scrape.

Setup:
    pip install playwright pandas
    python -m playwright install chromium

Run:
    python src/collection/04_collect_gmp.py

Output:
    data/raw/raw_gmp_data.csv       - one row per IPO, raw strings
    data/raw/gmp_checkpoint.json    - progress (auto-deleted on success)
"""

import asyncio
from playwright.async_api import async_playwright
import pandas as pd
import json
import os

# ============================================================
# CONFIG
# ============================================================
OUTPUT_DIR = "data/raw"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "raw_gmp_data.csv")
CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, "gmp_checkpoint.json")

START_YEAR = 2019
END_YEAR = 2026

# One-time collection: no tight time limits. These are deliberately large
# so nothing ever fails just because a page loaded slowly.
PAGE_TIMEOUT_MS = 180_000       # 3 minutes per navigation (generous)
WAIT_AFTER_LOAD_MS = 6_000      # let JS render the table + pagination
WAIT_AFTER_PAGE_CLICK_MS = 4_000  # let the next page's rows render
MAX_PAGES = 20                  # safety cap on page clicks
MAX_LOAD_RETRIES = 4            # retry a failed page load this many times

# Expected mainboard IPO counts per year (from the Chittorgarh trackers).
# Used only to WARN if a year comes up short - never to filter.
EXPECTED_COUNTS = {
    2019: 4,     # InvestorGain tracked very few 2019 IPOs (known-incomplete)
    2020: 16,
    2021: 66,
    2022: 39,
    2023: 60,
    2024: 93,
    2025: 108,
    2026: 32,
}


# ============================================================
# Extract every row (with all cells) from the current table page
# ============================================================
async def extract_table(page):
    return await page.evaluate('''() => {
        const tables = document.querySelectorAll('table');
        let best = null, maxRows = 0;
        for (const t of tables) {
            const n = t.querySelectorAll('tbody tr').length;
            if (n > maxRows) { maxRows = n; best = t; }
        }
        if (!best) return { headers: [], rows: [] };

        const headers = [];
        best.querySelectorAll('thead th').forEach(th => headers.push(th.textContent.trim()));

        const rows = [];
        for (const tr of best.querySelectorAll('tbody tr')) {
            const cells = [];
            tr.querySelectorAll('td').forEach(td => cells.push(td.textContent.trim()));
            if (cells.length >= 3) rows.push(cells);
        }
        return { headers: headers, rows: rows };
    }''')


# ============================================================
# Click the "Next" pagination button. Returns True if it advanced.
# ============================================================
async def click_next(page):
    """Click <button class='pagination-btn'>Next</button> if enabled.
    Returns True if a (non-disabled) Next button was clicked."""
    return await page.evaluate('''() => {
        const btns = document.querySelectorAll('button.pagination-btn');
        for (const b of btns) {
            if (b.textContent.trim() === 'Next' &&
                !b.className.includes('disabled')) {
                b.click();
                return true;
            }
        }
        return false;
    }''')


async def get_page_indicator(page):
    """Return the '1/2' style page indicator text, or None."""
    return await page.evaluate('''() => {
        const el = document.querySelector('.pagination-info');
        return el ? el.textContent.trim() : null;
    }''')


# ============================================================
# Load a year's page (with retries - safety net, not a time limit)
# ============================================================
async def load_page(page, url):
    last_err = None
    for attempt in range(1, MAX_LOAD_RETRIES + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
            await page.wait_for_timeout(WAIT_AFTER_LOAD_MS)
            return True
        except Exception as e:
            last_err = str(e)
            wait_s = 5 * attempt  # 5s, 10s, 15s... unhurried
            if attempt < MAX_LOAD_RETRIES:
                print(f"       load attempt {attempt} failed "
                      f"({last_err[:50]}); waiting {wait_s}s and retrying...")
                await asyncio.sleep(wait_s)
    print(f"       x all {MAX_LOAD_RETRIES} load attempts failed")
    return False


# ============================================================
# Scrape one year by clicking through all pages
# ============================================================
async def scrape_year(page, year):
    url = (f"https://www.investorgain.com/report/"
           f"ipo-gmp-performance-tracker/377/ipo/?year={year}")
    print(f"\n  {year}: loading...", flush=True)

    if not await load_page(page, url):
        return [], []

    headers = []
    all_rows = []
    seen_first = None

    for page_idx in range(MAX_PAGES):
        data = await extract_table(page)
        if not headers and data["headers"]:
            headers = data["headers"]

        # Guard: if the first cell is identical to the previous page's first
        # cell, the click didn't actually advance - stop to avoid a loop.
        current_first = data["rows"][0][0] if data["rows"] else None
        if page_idx > 0 and current_first == seen_first:
            break
        seen_first = current_first

        # Add rows we haven't seen (dedupe by first cell = IPO name)
        existing = {r[0] for r in all_rows if r}
        new_count = 0
        for row in data["rows"]:
            if row and row[0] not in existing:
                all_rows.append(row)
                new_count += 1

        indicator = await get_page_indicator(page)
        ind_str = f" [{indicator}]" if indicator else ""
        print(f"       page {page_idx+1}{ind_str}: {len(data['rows'])} shown, "
              f"{new_count} new (total {len(all_rows)})")

        # Try to advance to the next page
        advanced = await click_next(page)
        if not advanced:
            break  # no enabled Next button = last (or only) page
        await page.wait_for_timeout(WAIT_AFTER_PAGE_CLICK_MS)

    expected = EXPECTED_COUNTS.get(year)
    if expected and len(all_rows) < expected:
        note = "known-incomplete for 2019" if year == 2019 else "possible gap"
        print(f"       !  Got {len(all_rows)}, expected ~{expected} ({note})")
    else:
        print(f"       OK {len(all_rows)} rows")

    return headers, all_rows


# ============================================================
# Checkpoint helpers
# ============================================================
def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE) as f:
                ck = json.load(f)
            return {int(y): v for y, v in ck.items()}
        except Exception:
            return {}
    return {}


def save_checkpoint(year_data):
    serializable = {str(y): {"headers": h, "rows": r}
                    for y, (h, r) in year_data.items()}
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(serializable, f)


# ============================================================
# MAIN
# ============================================================
async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print("GMP DATA COLLECTION (InvestorGain, click-through pagination)")
    print("=" * 60)

    checkpoint = load_checkpoint()
    year_data = {}
    if checkpoint:
        for y, d in checkpoint.items():
            year_data[y] = (d["headers"], d["rows"])
        print(f"Resuming - already have years: {sorted(year_data.keys())}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for year in range(START_YEAR, END_YEAR + 1):
            # Skip a year only if it's already complete in the checkpoint
            if year in year_data:
                have = len(year_data[year][1])
                expected = EXPECTED_COUNTS.get(year, 0)
                if have >= expected or year == 2019:
                    print(f"\n  {year}: already have {have} rows, skipping")
                    continue

            headers, rows = await scrape_year(page, year)
            year_data[year] = (headers, rows)
            save_checkpoint(year_data)

        await browser.close()

    # Flatten to records
    records = []
    for year, (headers, rows) in year_data.items():
        for cells in rows:
            row_dict = {"year": year}
            for i, val in enumerate(cells):
                col = headers[i] if i < len(headers) else f"col_{i}"
                col = col.replace("\u25b2\u25bc", "").strip()
                row_dict[col] = val
            records.append(row_dict)

    df = pd.DataFrame(records)
    df.to_csv(OUTPUT_FILE, index=False)

    # Success -> remove checkpoint
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)

    # ---------- Summary ----------
    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)
    print(f"  Total rows: {len(df)}")
    print(f"  Saved: {OUTPUT_FILE}")
    print(f"\n  Per-year counts (scraped vs expected):")
    for year in range(START_YEAR, END_YEAR + 1):
        got = (df["year"] == year).sum() if "year" in df.columns else 0
        exp = EXPECTED_COUNTS.get(year, "?")
        flag = ""
        if isinstance(exp, int):
            if got >= exp:
                flag = "OK"
            elif year == 2019:
                flag = "(2019 known-incomplete)"
            else:
                flag = f"! short by {exp - got}"
        print(f"    {year}: {got:>3} / {exp}   {flag}")

    if len(df) > 0:
        print(f"\n  Columns: {list(df.columns)}")
        print(f"\n  Sample (first 2 rows):")
        print(df.head(2).to_string(index=False))


if __name__ == "__main__":
    asyncio.run(main())