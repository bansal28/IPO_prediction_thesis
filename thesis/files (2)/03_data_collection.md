# 3. Data Collection

This chapter documents the assembly of the working dataset. Each section
describes one data source, how it was accessed, what was collected, how
completeness and correctness were verified, and any technical challenges
overcome. All collection code is deposited in `src/collection/`, and all raw
outputs are stored under `data/raw/`.

## 3.1 Overview and coverage

Five distinct data streams were assembled between 5 February 2019, the earliest
listing in the Chittorgarh tracker, and 8 July 2026, the cut-off for the
dataset used in this dissertation.

| Data stream | Source | Records | Purpose |
|---|---|---|---|
| Chittorgarh yearly IPO trackers | chittorgarh.com | 434 IPO rows across 8 files | IPO universe (spine of the dataset) |
| Chittorgarh detail pages | chittorgarh.com | 434 IPO detail rows × 30 fields | Issue price, listing OHLC, financials, subscription, broker sentiment |
| InvestorGain grey-market data | investorgain.com | 418 IPO rows | Pre-listing grey-market premium (GMP) |
| Yahoo Finance market context | Yahoo Finance via `yfinance` | Nifty 50: 1,853 daily rows; India VIX: 1,837 daily rows | Prior-day market context |
| SEBI DRHP/RHP prospectuses | sebi.gov.in | 416 verified PDF files | Risk-factor text for LLM extraction (Chapter 7) |
| Ghosh et al. cross-validation set | supplementary to arXiv:2412.16174 | 418 IPO rows × 217 columns | Third-party cross-check of issue price and other numeric fields |

The final cleaned dataset contains 419 mainboard equity IPOs after removal of
Real Estate Investment Trusts (REITs), Infrastructure Investment Trusts
(InvITs), and similar non-equity vehicles; the derivation of this figure is
described in Chapter 4.

## 3.2 Chittorgarh yearly IPO trackers

The Indian retail-investor site Chittorgarh publishes an annual tracker page
per calendar year listing every mainboard IPO listing (SME issues are on
separate tracker pages, not used here). Eight tracker CSVs were assembled,
covering 2019 through 2026, containing 434 rows in total, distributed by
year as shown below.

| Year | IPO rows | Tracker CSV filename |
|---|---|---|
| 2019 | 20 | `ipo-performance-all-2019.csv` |
| 2020 | 16 | `ipo-performance-all-2020.csv` |
| 2021 | 66 | `ipo-performance-mainline-2021.csv` |
| 2022 | 39 | `ipo-performance-mainline-2022.csv` |
| 2023 | 60 | `ipo-performance-mainline-2023.csv` |
| 2024 | 93 | `ipo-performance-mainline-2024.csv` |
| 2025 | 108 | `ipo-performance-mainline-2025.csv` |
| 2026 | 32 | `ipo-performance-mainline-2026.csv` |
| **Total** | **434** | |

Files are stored in `data/raw/chittorgarh/`. These files form the *spine* of
the dataset: every subsequent enrichment step joins onto the (company name,
listing year) key derived from this list.

## 3.3 Chittorgarh detail pages

For each of the 434 IPOs identified in the trackers, the corresponding
Chittorgarh detail page was scraped using Playwright, a headless browser
automation library. The script `src/collection/02_collect_chittorgarh_details.py`
navigates to each detail URL, waits for the page to reach `networkidle`, and
extracts thirty structured fields per IPO into `data/raw/raw_ipo_details.csv`.

Fields collected include the issue price, face value, lot size, total issue
size (in number of shares), fresh-issue and offer-for-sale components,
subscription multiples, broker-recommendation counts, key financial figures
(revenue, profit, assets, net worth, borrowings), and the full listing-day
OHLC on the primary exchange.

**Technical challenges encountered and resolved.**

- **Timeout tuning.** The initial timeout of 15 seconds and the default
  waiting condition (`load`) were insufficient for a small number of pages
  that render key elements only after asynchronous data loads. Timeout was
  extended to 45 seconds, the wait condition changed to `networkidle`, and
  a three-attempt retry loop added. After these changes, all 434 pages
  returned successfully with zero collection errors.
- **Listing-close reconciliation.** In an early sanity check, seven IPO rows
  had a `listing_close` value in the yearly tracker that materially disagreed
  with the value on the detail page. In every case examined the detail page
  agreed with the exchange record (for example, Mankind Pharma's true BSE
  close was ₹1424.05, matching the detail page, while the tracker showed
  ₹1080). Consequently, a *locked decision* was recorded that `listing_close`
  is always sourced from the detail page and never from the tracker. This
  decision is logged in Appendix A.

**Coverage of critical fields.** Of the 434 IPO detail rows, 434 have a valid
`listing_close`; 419 have a valid `issue_price`. The 15 IPOs missing an
`issue_price` are the REITs, InvITs, and similar non-equity vehicles that are
excluded during data cleaning (Chapter 4).

## 3.4 Grey-market premium from InvestorGain

Grey-market premium data was collected from InvestorGain, one of the two most
widely-cited public trackers of Indian IPO grey-market activity. A single-
source design was chosen — no other GMP source is mixed into the dataset —
in order to maintain methodological consistency. Different trackers report
different values for the same IPO on the same day; mixing them would
introduce measurement heterogeneity that would be difficult to distinguish
from real signal in downstream analysis. This is logged as a locked decision
in Appendix A.

The scraper `src/collection/04_collect_gmp.py` iterates over the year-indexed
InvestorGain tracker pages using Playwright. Per-year totals collected are
shown below.

| Year | GMP rows |
|---|---|
| 2019 | 4 |
| 2020 | 16 |
| 2021 | 66 |
| 2022 | 39 |
| 2023 | 60 |
| 2024 | 93 |
| 2025 | 108 |
| 2026 | 32 |
| **Total** | **418** |

**Technical challenges encountered and resolved.**

- **Custom pagination.** InvestorGain's yearly tables paginate at 100 rows
  using a custom control (`<button class="pagination-btn">Next</button>`
  inside `<div class="pagination-wrap">` with a "1/2" indicator), rather than
  the more common DataTables pagination or infinite scroll. This was
  determined empirically by live browser inspection of the 2025 table (108
  rows across two pages), and the scraper was written to click the custom
  "Next" button after processing the first page. Without this handling, the
  last eight 2019 rows and the last eight 2025 rows would have been silently
  missed.
- **Wait conditions and checkpointing.** As with the Chittorgarh detail
  scraper, generous timeouts and `domcontentloaded` (rather than
  `networkidle`) were used to accommodate slow renders. A per-year checkpoint
  is written after each year completes, allowing resumption after an
  interruption.

**Grey-market data availability by year.** GMP coverage for 2019 is
substantially incomplete (only 4 rows for 20 listings; the practice of GMP
tracking on InvestorGain begins later). This is not a scraping error but a
genuine data-availability limitation of the pre-listing grey market for the
early period. It is handled explicitly in Chapter 4 by an evidence-based
missingness rule that distinguishes untracked GMP from a genuine zero GMP.

## 3.5 Market context: Nifty 50 and India VIX

Prior-day market context is required to control for the possibility that
IPO underpricing varies with the state of the broader market. Two indices
were collected via the `yfinance` package (`src/collection/03_download_market_data.py`):

- **Nifty 50** — the primary Indian large-cap equity index. Daily open, high,
  low, close, and volume for the period 1 January 2019 through 8 July 2026.
  Final coverage: 1,853 valid trading days. Range observed: 7,610 to 26,329.
- **India VIX** — a volatility index computed from Nifty options. Same date
  range. Final coverage: 1,837 valid trading days. Range observed: 9.1 to
  83.6.

**Technical note: yfinance output format.** As of the version used, `yfinance`
returns seven columns per index including a duplicate `Adj Close` (for indices,
`Adj Close` equals `Close`), and prepends three header rows. Downstream
reading code must therefore use `skiprows=3` and explicit column names. This
is documented in the reproducibility appendix (Appendix B).

## 3.6 Prospectus PDFs from SEBI

The core novelty of this dissertation relies on machine-readable access to the
Risk Factors section of each IPO's regulatory offer document. SEBI publishes
DRHPs and RHPs on its Public Issues portal. A three-stage collection pipeline
was implemented.

### 3.6.1 Stage 1 — bulk retrieval

`src/collection/05_collect_prospectus.py` scrapes SEBI's DRHP and RHP index
pages, harvesting 3,371 filings (1,214 RHP + 2,157 DRHP; index snapshot stored
as `data/raw/sebi_index.csv`). Each candidate filing is fuzzy-matched to the
IPO universe using the `rapidfuzz` library, and the actual PDF URL is
extracted from the SEBI landing page for that filing.

Every downloaded PDF is subjected to a **four-check verification**:

1. **Completeness.** The downloaded byte count must equal the `Content-Length`
   reported by the SEBI server. This check catches truncation, which produced
   corrupted zero-page PDFs in an early pilot.
2. **Openability.** The file must open successfully in `pypdf`.
3. **Identity.** The company name must be present on an early page of the
   document.
4. **Content coverage.** The document must contain a "Risk Factors" section.

Stage 1 obtained 270 verified PDFs.

### 3.6.2 Stage 2 — targeted retrieval of remaining IPOs

For IPOs not obtained in stage 1, `src/collection/06_collect_remaining_prospectus.py`
implements three specific fixes that resolve the failure modes observed:

- **Resumable downloads via HTTP Range.** SEBI's server periodically drops
  connections on large PDFs, producing an `IncompleteRead` exception in
  the HTTP client. Rather than restarting the download from byte zero,
  the script resumes from the last successfully received byte using an
  HTTP `Range: bytes=N-` request. This makes retrieval of very large
  prospectuses reliable.
- **Absolute and relative URL handling.** SEBI links to PDFs sometimes use
  absolute URLs (`https://www.sebi.gov.in/sebi_data/attachdocs/.../x.pdf`)
  and sometimes use relative paths (`attachdocs/...`). A regex that handled
  only the absolute form silently missed the older 2019–2020 filings. The
  fix prepends `https://www.sebi.gov.in/sebi_data/` when the discovered link
  is relative.
- **Rejection of corrigendum and addendum documents.** The fuzzy matcher
  occasionally selected a one-page corrigendum or addendum instead of the
  substantive Red Herring Prospectus for the same IPO. Two guards were
  added: (a) any candidate document must have at least fifty pages to be
  accepted, and (b) an identity guard rejects matches where the candidate
  company name differs from the target by more than the fuzzy-match threshold
  (for example, guaranteeing that Aadhar Housing is not accepted as a match
  for Bajaj Housing).

Stage 2 raised the count to 409 verified PDFs.

### 3.6.3 Stage 3 — final seven

Seven remaining IPOs did not resolve to a downloadable PDF through the
automated pipeline. Their URLs were identified by hand from the SEBI portal
and are hard-coded in `src/collection/07_fetch_final_7.py`: MSTC, SAMHI
Hotels, Patel Retail, RailTel, Urban Company, Turtlemint, and Exxaro Tiles.
The Exxaro Tiles prospectus is AES-encrypted; the `cryptography` Python
package must be installed for `pypdf` to open it with an empty password.

Stage 3 completed the collection at 416 verified PDFs.

### 3.6.4 Final prospectus dataset

All 416 PDFs pass the four verification checks including the presence of a
"Risk Factors" section. A `_validation_log.csv` file inside
`data/prospectus_pdfs/` records per-PDF metadata: file size, page count,
verification status, and any warnings.

The three IPOs for which no valid prospectus was obtained are
[TODO: HRITIK — check the final validation log for the exact list; expected
to be a small handful of very recent 2026 listings whose prospectuses had not
yet been published on the SEBI portal at the collection cut-off date, or old
2019 listings whose PDFs are no longer hosted].

## 3.7 Cross-validation dataset from Ghosh et al.

For a partial independent check on the assembled numeric fields, the
supplementary dataset released with Ghosh, Zheng, and Lopez-Lira (2024) was
obtained as `data/raw/ghosh_mainboard_v18.xlsx`. This file contains 418 rows
and 217 columns. The overlap with the present dataset, computed by
company-name matching after normalisation (stripping the " IPO" suffix
present in Ghosh's `Issuer Company` column, lowercasing, whitespace-normalising),
is 175 IPOs. On the overlap, `Final_Issue_Price` in Ghosh agrees with
`issue_price` in the present dataset to 100 percent concordance.

The remaining Ghosh rows are mostly older IPOs (predominantly from before
2015) that fall outside the present study's window.

## 3.8 Reproducibility

All collection scripts are self-contained and use generous timeouts and
retry policies. No collection step is time-bounded; all are one-time bulk
collections that can be re-run when refreshed data is required. Playwright,
`yfinance`, `pypdf`, `rapidfuzz`, and `cryptography` are the primary
external dependencies. The full list of dependencies with pinned versions
is in `requirements.txt` at the project root.

Collection provenance (source URL, retrieval timestamp, HTTP status) is
recorded in `data/raw/raw_prospectus_links.csv`,
`data/raw/raw_prospectus_links_final.csv`, and
`data/prospectus_pdfs/_validation_log.csv` for the SEBI pipeline; equivalent
provenance for Chittorgarh and InvestorGain is embedded as filename and
timestamp metadata in `data/raw/raw_ipo_urls.csv` and the checkpointed
per-year outputs of the GMP scraper.
