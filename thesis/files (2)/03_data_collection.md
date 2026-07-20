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
| SEBI DRHP/RHP prospectuses | sebi.gov.in | 416 verified PDF files | Risk-factor text; certified via the extraction pipeline in §3.7 for use in Chapter 7 LLM extraction |
| Ghosh et al. cross-validation set | supplementary to arXiv:2412.16174 | 418 IPO rows × 217 columns | Third-party cross-check of issue price and other numeric fields |

The final cleaned dataset contains 416 mainboard equity IPOs after removal
of Real Estate Investment Trusts (REITs), Infrastructure Investment Trusts
(InvITs), and similar non-equity vehicles, plus a further exclusion of three
Follow-on Public Offers (FPOs) mis-categorised in the Chittorgarh tracker as
IPOs; the derivation of this figure is described in Chapter 4.

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
excluded during data cleaning (Chapter 4). A further three of the 419
IPO-typed rows are Follow-on Public Offers rather than initial offerings and
are also excluded downstream (Chapter 4 §4.3.1), leaving 416 mainboard
equity IPOs in the final cleaned dataset.

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
verification status, and any warnings. Three of the 416 PDFs correspond to
FPOs (Yes Bank, Ruchi Soya, Vodafone Idea); these documents are technically
valid RHPs but the associated companies are excluded downstream by the
FPO exclusion rule (Chapter 4 §4.3.1), so their extracted risk-factor text
does not participate in modelling.

One of the retained PDFs (Manoj Vaibhav Gems N Jewellers Ltd.) is a scanned
document with no embedded text layer. Its risk-factor text was recovered by
OCR using pymupdf pixmap rendering at 350 DPI and Tesseract PSM 6, producing
approximately 24,000 words across 71 numbered risk items. The OCR provenance
is recorded in the `_extraction_log.csv` header for that IPO.

The verification described in this section confirms that the PDF itself is
present, opens, identifies the correct company, and contains a "Risk Factors"
section at the document level. It does not confirm that the *extraction* from
the PDF to a machine-readable representation is faithful: as §3.7 documents,
the initial extractor produced silently-broken output for a small number of
PDFs (bounds matched to the wrong section, encoding artefacts confusing end
detection, and so on), and a separate audit-and-recertification pipeline was
required to produce the certified corpus of 416 risk sections consumed by
downstream chapters.

## 3.7 Risk Factors extraction, audit, and certification

Section 3.6 established that 416 prospectus PDFs are present on disk and
that each one contains a Risk Factors section at the PDF-content level.
The step from a PDF on disk to a machine-readable representation of just
the Risk Factors section — a per-IPO markdown file that any downstream
analysis (Chapter 5 exploratory work, Chapter 7 LLM extraction) can treat
as clean input — is a separate pipeline with its own failure modes and its
own certification. This section documents that pipeline.

The pipeline is implemented across three numbered scripts,
`src/processing/03a_extract_risk_sections.py` (the original extractor,
retained for provenance), `src/processing/07_reextract_and_certify.py` (the
working extractor with content-based bounds detection), and
`src/processing/08_reextract_v2.py` (a second-pass fix for two failure
modes discovered only after the first-pass Chapter 5 exploratory analysis
on the risk sections). The section motivates each of the three stages in
turn, and closes with a summary of the final certified corpus state.

### 3.7.1 Initial extraction and the failure modes it exposed

The initial extractor followed the natural design implied by the structure
of an Indian Red Herring Prospectus: locate the section header
("SECTION II — RISK FACTORS" for a book-built issue), extract every page
from that header up to the next section header ("SECTION III —
INTRODUCTION" in the standard SEBI format), and convert the resulting
page range to markdown with `pymupdf4llm`. Bound detection was implemented
as two regular expressions, `RISK_START` matching the "RISK FACTORS" header
at line start, and `NEXT_SECTION` matching the subsequent
"SECTION [Roman] — [TITLE]" header at line start. The extractor ran on
all 416 PDFs and produced 416 markdown files at
`data/processed/risk_sections/`, with a log of the page range used per IPO
in `_extraction_log.csv`.

Three failure modes were surfaced during the exploratory analysis of the
resulting corpus. Each is characterised below by the failing case that
first revealed it.

**Failure mode 1 — body-text false positive on the end pattern.** For
Inventurus Knowledge Solutions Ltd. (December 2024), the `NEXT_SECTION`
regex matched the body-text fragment "Section V of the Companies Act, 2013"
appearing on the second page of the Risk Factors section itself. The
extractor stopped after three pages, producing an .md file with 764 words
instead of the expected ~30,000. The failure was silent: no error was
raised, and downstream statistics simply recorded Inventurus as an
extremely short risk section, which no automated check flagged as
anomalous.

**Failure mode 2 — front-matter false positive on the start pattern.**
For Anand Rathi Share & Stock Brokers Ltd. (2005 draft prospectus), the
`RISK_START` regex matched a table-of-contents entry in the front matter
("SECTION II: RISK FACTORS ....... 8") rather than the actual Risk Factors
header, which in this 2005-era document uses a bare "RISK FACTORS" without
the "SECTION II" prefix. The extractor pulled pages 8 through 14
(front-matter content: definitions, forward-looking statements) rather
than the real Risk Factors on pages 10 through 15. The resulting .md
contained 2,611 words of the wrong content and appeared numerically normal.

**Failure mode 3 — font-encoding artefact in the separator character.**
For Go Fashion (India) Ltd. (November 2021), the character between
"SECTION III" and "INTRODUCTION" in the page header was rendered by
`pymupdf` as `±` (Unicode U+00B1, plus-minus sign) rather than the em-dash
actually present in the source PDF. This is a known limitation of PDF
text extraction when the font's character mapping table is non-standard.
The `NEXT_SECTION` regex, which required a hyphen or colon between the
Roman numeral and the section title, did not match, and the extractor
walked past the true end of Risk Factors until it found another matchable
pattern deep in the document.

These three failure modes shared one property that made them difficult to
detect: the resulting .md file was internally consistent (the markdown
matched, character-for-character, the plain-text extraction of the same
page range) but the *page range itself* was wrong. Any check that compared
the .md against the source PDF using the same bounds the extractor had
chosen would confirm the extraction was faithful, while failing to notice
that the bounds themselves did not correspond to the Risk Factors section.
A different verification method was required.

### 3.7.2 Content-based bounds detection

The `07_reextract_and_certify.py` script re-extracts every risk section
using bounds located by content signals rather than by header pattern.
The design principle (locked in Appendix A as D-29) is that a prospectus's
Risk Factors section is identified not by a single header regex — which
the failure modes above demonstrate to be unreliable — but by a
*combination of independent content anchors that appear only inside Risk
Factors sections in Indian prospectuses*.

Every page in every PDF is scored for how strongly it resembles a
Risk Factors page. Three "strong" content anchors each contribute 3 points
to a page's score:

- the phrase "investment in [our|the] Equity Shares involves a high degree
  of risk" (the canonical SEBI-mandated opening sentence);
- the standalone heading "INTERNAL RISK FACTORS" (a subsection heading
  used by the vast majority of Indian prospectuses);
- the phrase "carefully consider … the risks described below" (a variant
  opening used by older or Fixed Price prospectuses).

Two structural signals — the "SECTION [Roman] — RISK FACTORS" header and
a bare "RISK FACTORS" header — each contribute 2 points. Two "weak"
content anchors — "lose all or part of [your|their] investment" and
"material adverse effect on [the|our] business" — each contribute 1 point
but can appear outside Risk Factors too, so they do not qualify a page on
their own.

A page qualifies as a candidate start page when its score reaches 3. This
threshold is chosen so that any single strong anchor, or the combination
of a header signal with a weak anchor, is sufficient. Empirically, real
Risk Factors sections' opening pages score 6 to 12 under this scheme
(multiple anchors, header, and weak signals stacking); false-positive
pages such as front-matter table-of-contents entries score 2 or below.

End detection uses a broader set of section-title patterns than the
original extractor, still requiring an all-uppercase title after the Roman
numeral to prevent body-text false positives, and admitting a wider set of
separator characters including the plus-minus sign observed in Go Fashion.
Six explicit title patterns are matched (INTRODUCTION, THE OFFER, ABOUT or
BUSINESS, FINANCIAL, SUMMARY FINANCIAL INFORMATION, INDUSTRY OVERVIEW),
followed by a strict generic "SECTION [Roman] — [UPPERCASE_TITLE]" catch-all.

### 3.7.3 Certification: per-extraction audit against ground truth

Every re-extraction is audited immediately, before its output is allowed
to overwrite the existing .md file. The audit compares the `pymupdf4llm`
markdown output for the chosen page range against a ground-truth
plain-text extraction of the same page range obtained via
`pymupdf.Page.get_text('text')`. Two metrics are computed.

The first is a **coverage ratio**: the ratio of markdown word count to
plain-text word count. A well-formed markdown extraction preserves
approximately every content word from the underlying plain text, so this
ratio should sit in the neighbourhood of 1.0. Values substantially below
1.0 indicate that the markdown converter has dropped content (for example,
silently discarding tables it could not parse). Values substantially above
1.0 indicate injected markdown noise.

The second is a **bigram-Jaccard content-overlap coefficient**: the
Jaccard similarity of the set of two-word phrases appearing in the opening
12,000 characters of the markdown against the set of two-word phrases in
the opening 12,000 characters of the plain text. Bigrams are used rather
than individual tokens because the corpus has a large shared vocabulary
of general financial language — words like "company", "shares",
"material", "risk" appear on almost every page — and unigram Jaccard
therefore over-matches on pages that share vocabulary without sharing
content. Bigrams tighten this: sharing a two-word phrase requires the
same word in the same order, and is a more discriminating measure of
whether the two extractions describe the same content region.

Empirical thresholds (locked in Appendix A as D-30) are: coverage in
[0.60, 1.50] and bigram Jaccard at least 0.50. The thresholds are
calibrated on a validation set of five prospectuses spanning the three
observed failure modes plus two known-clean baselines; failed
extractions fall below 0.30 on Jaccard, correctly-bounded but mangled
markdown falls below 0.60 on coverage, and clean extractions sit above
0.90 on both.

An extraction that passes audit overwrites the existing .md file after a
timestamped backup of the original is written to a
`.backup-risk_sections-YYYYMMDD-HHMMSS/` directory. An extraction that
fails audit leaves the existing .md file untouched, and a row is written
to a needs-manual-review CSV together with the audit numbers and the
detected page bounds. The safety guarantee is therefore straightforward:
an .md file is only overwritten when a fresh extraction has been
certified against its own PDF, and the pre-run state can be restored
from backups at any point.

### 3.7.4 Handling of pymupdf4llm mangled outputs

For one prospectus in the study (Go Fashion), the `pymupdf4llm` markdown
converter produced output that failed the coverage check (0.40) despite
the bounds being correct. Inspection of the output showed that the
converter had squashed words together across table cells (for example,
"andAnalysis ofFinancial ConditionandResultsofOperations") and had
discarded roughly half the underlying page content. This is a known
limitation of `pymupdf4llm` on PDFs whose tables use certain custom
cell-boundary encodings.

The pipeline handles this case (D-31 in Appendix A) with a plain-text
fallback: when `pymupdf4llm` output fails audit, and when a plain-text
extraction of the same page range would exceed 5,000 words, the .md
file is written using the plain-text extraction wrapped in a minimal
markdown header rather than the mangled markdown. The plain-text
fallback loses markdown-formatted tables, but preserves every word of
the source content — a substantially better failure mode than the
alternative. In the final certified corpus, one file (Go Fashion) was
written via the plain-text fallback; a note recording this is written
into the file's opening line.

### 3.7.5 Second-pass fix: SEBI-2022 summary trap and unbounded end

After the pipeline in §3.7.2 through §3.7.4 was run on all 416 PDFs, a
preliminary exploratory pass on the resulting risk sections (Chapter 5)
surfaced a further pattern that neither the audit nor the content-based
bounds detection had prevented. Approximately thirty modern prospectuses
(listing year ≥ 2022) had extracted to unusually short .md files, on the
order of 1,500 to 3,000 words with exactly ten numbered items detected.
The near-exact modal item count of ten was the diagnostic tell:
post-2022 SEBI disclosure guidelines mandate that the executive summary
of an offer document include a "Summary of Risk Factors" subsection
listing the top ten risk factors in condensed form, before the full
Risk Factors section proper. The content-based bounds detection was
matching this summary block — which does contain some of the strong
anchor phrases — and stopping at the summary's end rather than
proceeding to the full section.

A separate failure appeared in the opposite direction for Atlanta
Electricals Ltd. (2025), where the end-detection matched no pattern
between the true section end and the last page of the entire document,
producing a 77,361-word extraction that included several subsequent
chapters.

The `08_reextract_v2.py` script applies two targeted changes to address
these two failure modes. First, the bounds-detection logic is extended
to consider *all* pages that qualify as candidate starts (rather than
only the earliest such page) and to select the (start, end) pair whose
extracted range contains the most text. This is a principled selection
rule because the SEBI-2022 summary block extracts to approximately 2,000
words while the corresponding full Risk Factors section extracts to
25,000 to 40,000 words; the summary cannot outweigh the full section on
total content, and pre-2022 prospectuses which have only one candidate
start page are unaffected by the change. Second, a hard cap of 90 pages
is applied to the end detection: no Risk Factors section in the study
corpus exceeds this length (the 99th percentile of section length is 68
pages), and the cap prevents runaway extractions when end-signal
patterns fail to match at all. Both changes are locked in Appendix A
(D-32 and D-33).

The v2 script targets only files matching the two problem patterns
(word count under 15,000 with at most 15 items, or word count above
60,000) rather than re-processing all 416 PDFs, which would risk
introducing changes to already-clean extractions for no gain. The
targeted run identified 35 files, of which all 35 were re-extracted
and passed audit under the improved bounds. The Rubicon Research Ltd.
extraction, for example, moved from 1,195 words with 10 items to 43,850
words with 90 items; Atlanta Electricals moved from 77,361 words to
40,379 words; Anand Rathi Share & Stock Brokers Ltd. (2005) was
included in the run by the word-count filter but its bounds were
confirmed unchanged by the multi-candidate selection (its Fixed Price
Issue format contains only one candidate start page, and no larger
extraction is available anywhere in the document).

### 3.7.6 A single manually extracted prospectus: Sai Silks

One prospectus in the corpus, Sai Silks (Kalamandir) Ltd. (2009 draft
prospectus), was not extractable by either the content-based pipeline
or the v2 second-pass. Its 2009-vintage Fixed Price Issue format uses
letter-labelled sections ("SECTION – A", "SECTION – B: RISK FACTORS")
rather than the Roman-numeral labelling standard in later book-built
issues, and its opening sentence uses "investment involves a degree of
risk" rather than the modern "high degree of risk" — with the effect
that none of the anchor patterns matched, and the file was flagged as
NO_ANCHOR by the audit.

Manual inspection of the PDF located the real Risk Factors section on
pages 11 through 23, ending immediately before an "Our Business:"
section on page 24. The pages were extracted directly with
`pymupdf4llm` and written to
`data/processed/risk_sections/Sai_Silks__Kalamandir__Ltd_.md`
(5,697 words, 13 pages). This is the only manually extracted file in
the study corpus, and the decision is logged as D-34.

### 3.7.7 Handling of the one OCR file: Manoj Vaibhav Gems

Manoj Vaibhav Gems N Jewellers Ltd. is the one prospectus PDF in the
study corpus that is image-only, with no embedded text layer (§3.6.4).
All three re-extraction stages detect this at their start (the "no
extractable text in the first ten pages" check in
`07_reextract_and_certify.py`) and leave the existing Tesseract-OCR .md
file untouched. The OCR output (23,582 words, 71 numbered items) is
treated as authoritative for this one file. D-35 records that no
attempt is made to re-OCR or otherwise substitute this file.

### 3.7.8 Final certified corpus

The pipeline in §3.7.2 through §3.7.7, run in sequence, produces the
certified corpus used by every downstream chapter of this dissertation:

- 413 files re-extracted and audited by the v1 pipeline (D-30
  thresholds);
- 35 files re-extracted and audited by the v2 pipeline (D-32 and D-33);
- 1 file (Sai Silks) manually extracted (D-34);
- 1 file (Manoj Vaibhav Gems) retained as Tesseract OCR (D-35);
- 1 file (Go Fashion) written via the plain-text fallback (D-31).

Together this covers all 416 prospectuses in the study. The corpus'
final length distribution has a median of 28,934 words with an IQR of
25,478 to 33,058 and a range of 1,826 to 52,071 words. The number of
detected numbered risk items has a median of 77 with a range of 3 to
105; no file in the corpus has zero detected items. The one legitimate
short outlier (Anand Rathi 2005 at 1,974 words) reflects the
substantially shorter Risk Factors sections of pre-2010 Indian
prospectuses.

Provenance for each file is recorded in
`reports/tables/eda/07_reextract/certification_log.csv` (v1) and
`reports/tables/eda/08_reextract_v2/certification_log_v2.csv` (v2), each
row of which contains the detected page bounds, the matched start and
end signals, the audit numbers (coverage and bigram Jaccard), and the
action taken. These two logs together are the authoritative record of
the extraction pipeline; the earlier `_extraction_log.csv` produced by
the original extractor is preserved alongside them for historical
provenance but is not the current source of truth for any per-file
metadata.

The methodological lesson worth noting is that no single regex-based
extraction rule is robust across a seven-year corpus of Indian
prospectuses. SEBI disclosure formats have changed materially over the
study period — pre-2010 Fixed Price Issues use letter-labelled
sections; pre-2022 book-built issues use one set of section titles;
post-2022 issues introduce the summary block that traps naive start
detection — and font-encoding artefacts in individual PDFs introduce
further heterogeneity. Multi-signal content-based detection combined
with immediate per-extraction audit, and a small number of targeted
manual interventions where automation is not sufficient, is what a
defensible extraction pipeline needs to look like on this kind of
corpus.

## 3.8 Cross-validation dataset from Ghosh et al.

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

## 3.9 Reproducibility

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

The full extraction and certification pipeline described in §3.7 is
documented in reproducibility form in Appendix B §B.3a, which lists the
scripts in the order they must be run and identifies the authoritative
certification logs.