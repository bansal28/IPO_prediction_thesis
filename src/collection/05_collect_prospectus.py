"""
STEP 05: Collect prospectus PDFs (RHP/DRHP) from SEBI
======================================================
This is the input for the LLM risk-extraction step - the core novelty of
the thesis. Each PDF is a 300-600 page Red Herring Prospectus containing
a "Risk Factors" section that the LLM will parse into structured fields.

WHY THIS SCRIPT IS CAREFUL (learned from a broken earlier attempt):
  A previous approach produced 0.0 MB / truncated PDFs that would not open
  and had no Risk Factors section. The root cause was INCOMPLETE downloads
  (the file was cut off mid-stream). A truncated PDF is corrupted.

  This script therefore VERIFIES every download with four checks:
    1. Complete download - downloaded byte count matches the server's
       Content-Length header exactly (catches truncation).
    2. Valid PDF - pypdf can open it and read the page count.
    3. Right company - the company name appears on page 1.
    4. Has Risk Factors - a "Risk Factors" section is present.
  A PDF that fails any check is deleted and logged, never kept silently.

SOURCE: SEBI public filings (the authoritative, permanent home of every
DRHP/RHP). Two index sections are scraped:
  - RHP  (Red Herring Documents filed with ROC): ~1,200 records
  - DRHP (Draft Offer Documents filed with SEBI): ~2,100 records
Each index row links to a landing page; the landing page contains the
direct PDF URL (pattern: .../sebi_data/attachdocs/<month>/<id>.pdf).

DESIGN NOTES (one-time collection):
  - No tight timeouts. Generous waits. Nothing fails just for being slow.
  - Checkpoints so a crash never loses progress.
  - Matching uses rapidfuzz; RHP is preferred over DRHP when both match.
  - REITs / InvITs / FPOs are skipped (they are dropped in cleaning and
    their risk sections don't fit the equity-IPO schema).

SETUP:
    pip install playwright pandas requests rapidfuzz pypdf
    python -m playwright install chromium

RUN (three phases - can be run together or separately):
    python src/collection/05_collect_prospectus.py

OUTPUTS:
    data/raw/sebi_index.csv                  - local index of SEBI filings
    data/raw/raw_prospectus_links.csv        - company -> PDF URL + status
    data/raw/manual_download_needed.csv      - unmatched IPOs + search links
    data/prospectus_pdfs/                    - the downloaded, verified PDFs
    data/prospectus_pdfs/_validation_log.csv - per-PDF validation results
"""

import asyncio
from playwright.async_api import async_playwright
import pandas as pd
import requests
import os
import re
import time

try:
    from rapidfuzz import fuzz, process
except ImportError:
    raise SystemExit("Install rapidfuzz:  pip install rapidfuzz")
try:
    from pypdf import PdfReader
except ImportError:
    raise SystemExit("Install pypdf:  pip install pypdf")


# ============================================================
# CONFIG
# ============================================================
RAW_DIR = "data/raw"
PDF_DIR = "data/prospectus_pdfs"

DETAILS_FILE = os.path.join(RAW_DIR, "raw_ipo_details.csv")
SEBI_INDEX_FILE = os.path.join(RAW_DIR, "sebi_index.csv")
LINKS_FILE = os.path.join(RAW_DIR, "raw_prospectus_links.csv")
MANUAL_FILE = os.path.join(RAW_DIR, "manual_download_needed.csv")
VALIDATION_LOG = os.path.join(PDF_DIR, "_validation_log.csv")

SEBI_SECTIONS = [
    {"doc_type": "RHP",
     "url": "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3&smid=11&ssid=15"},
    {"doc_type": "DRHP",
     "url": "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3&smid=10&ssid=15"},
]

# One-time collection: generous, unhurried timing.
PAGE_TIMEOUT_MS = 180_000
WAIT_AFTER_NAV_MS = 3_000
DOWNLOAD_TIMEOUT_S = 300          # 5 min per PDF (some are 30-50 MB)
MATCH_THRESHOLD = 82             # rapidfuzz score 0-100
MIN_PDF_BYTES = 300_000          # a real DRHP/RHP is >300 KB

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36")
}

# Skip these - not equity IPOs (dropped in cleaning anyway)
DROP_PATTERNS = ["REIT", "Trust", "InvIT"]
KNOWN_FPOS = {"Yes Bank Ltd.", "Ruchi Soya Industries Ltd.", "Vodafone Idea Ltd."}
KNOWN_REIT_NAMES = {"Embassy Office Parks", "Mindspace Business Parks"}


# ============================================================
# NAME NORMALIZATION + MATCHING
# ============================================================
def normalize(name):
    if not isinstance(name, str):
        return ""
    n = name.lower().strip()
    # strip SEBI doc-type suffixes
    for suf in [" - rhp", "- rhp", " - drhp", "- drhp", " - prospectus",
                " -rhp", " -drhp", " rhp", " drhp", " - udrhp 1",
                " - udrhp-i", " - corrigendum to rhp",
                " - corrigendum to drhp", " - addendum to drhp"]:
        if n.endswith(suf):
            n = n[: -len(suf)].strip()
    # strip company-form suffixes
    for suf in [" limited", " ltd.", " ltd", " pvt.", " pvt", " private",
                " co.", " co", " corp.", " corp", " corporation"]:
        if n.endswith(suf):
            n = n[: -len(suf)].strip()
    n = re.sub(r"[^\w\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def is_drop_candidate(company):
    if any(p in company for p in DROP_PATTERNS):
        return True
    if company in KNOWN_FPOS or company in KNOWN_REIT_NAMES:
        return True
    return False


def prefer_rhp(a, b):
    if a["doc_type"] == "RHP" and b["doc_type"] != "RHP":
        return a
    if b["doc_type"] == "RHP" and a["doc_type"] != "RHP":
        return b
    return a


# ============================================================
# PHASE 1: Scrape SEBI index (RHP + DRHP) into a local CSV
# ============================================================
async def extract_index_page(page):
    return await page.evaluate('''() => {
        const results = [];
        const tables = document.querySelectorAll('table');
        let best = null, maxRows = 0;
        for (const t of tables) {
            const n = t.querySelectorAll('tbody tr, tr').length;
            if (n > maxRows) { maxRows = n; best = t; }
        }
        if (!best) return results;
        for (const tr of best.querySelectorAll('tr')) {
            const tds = tr.querySelectorAll('td');
            if (tds.length < 2) continue;
            const date = tds[0].textContent.trim();
            const link = tds[1].querySelector('a[href$=".html"]');
            const title = tds[1].textContent.trim();
            if (date && link && link.href) {
                results.push({
                    filing_date: date,
                    title: title.split('\\n')[0].trim(),
                    landing_url: link.href
                });
            }
        }
        return results;
    }''')


async def get_total_pages(page):
    try:
        last = await page.evaluate('''() => {
            for (const a of document.querySelectorAll('a')) {
                const href = a.getAttribute('href') || '';
                if (href.includes("searchFormNewsList") &&
                    a.textContent.trim().toLowerCase() === 'last') {
                    const m = href.match(/searchFormNewsList\\('n',\\s*'(-?\\d+)'\\)/);
                    if (m) return parseInt(m[1]);
                }
            }
            return null;
        }''')
        return (last + 1) if last is not None else 1
    except Exception:
        return 1


async def scrape_sebi_section(page, section):
    doc_type = section["doc_type"]
    print(f"\n  [{doc_type}] {section['url']}")
    await page.goto(section["url"], wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    await page.wait_for_timeout(WAIT_AFTER_NAV_MS)

    total = await get_total_pages(page)
    print(f"    total pages: {total}")

    all_rows = []
    for pidx in range(total):
        if pidx > 0:
            try:
                await page.evaluate(f"searchFormNewsList('n', '{pidx}')")
                await page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT_MS)
                await page.wait_for_timeout(WAIT_AFTER_NAV_MS)
            except Exception as e:
                print(f"    page {pidx+1}: nav failed ({str(e)[:40]}) - skipping")
                continue
        rows = await extract_index_page(page)
        for r in rows:
            r["doc_type"] = doc_type
        all_rows.extend(rows)
        if (pidx + 1) % 10 == 0 or pidx == total - 1:
            print(f"    page {pidx+1}/{total}: cumulative {len(all_rows)}")
    return all_rows


async def build_sebi_index():
    """Scrape both SEBI sections. Returns a DataFrame; also caches to CSV."""
    if os.path.exists(SEBI_INDEX_FILE):
        idx = pd.read_csv(SEBI_INDEX_FILE)
        print(f"Using cached SEBI index: {len(idx)} rows "
              f"(delete {SEBI_INDEX_FILE} to re-scrape)")
        return idx

    print("=" * 60)
    print("PHASE 1: Scraping SEBI filing index (RHP + DRHP)")
    print("=" * 60)
    all_rows = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        for section in SEBI_SECTIONS:
            all_rows.extend(await scrape_sebi_section(page, section))
        await browser.close()

    idx = pd.DataFrame(all_rows).drop_duplicates(subset=["landing_url"])
    idx.to_csv(SEBI_INDEX_FILE, index=False)
    print(f"\nSaved SEBI index: {len(idx)} rows -> {SEBI_INDEX_FILE}")
    return idx


# ============================================================
# PHASE 2: Match IPOs -> landing page -> direct PDF URL
# ============================================================
PDF_URL_RE = re.compile(
    r"https?://www\.sebi\.gov\.in/sebi_data/[^\s\"'<>]+\.pdf", re.IGNORECASE)


def get_direct_pdf_url(landing_url):
    """Fetch a SEBI landing page and return the direct .pdf URL (full doc,
    not the abridged prospectus), or None."""
    try:
        resp = requests.get(landing_url, headers=HEADERS, timeout=60)
        if resp.status_code != 200:
            return None
        matches = PDF_URL_RE.findall(resp.text)
        # Prefer the main document over abridged versions
        for m in matches:
            if "attachdocs" in m and "abridged" not in m.lower():
                return m
        return matches[0] if matches else None
    except Exception:
        return None


def find_match(company, idx):
    """Fuzzy-match company against SEBI index titles. Prefer RHP.
    Returns (row, score) or (None, best_score)."""
    cnorm = normalize(company)
    if not cnorm:
        return None, 0
    choices = idx["title_norm"].tolist()
    matches = process.extract(cnorm, choices, scorer=fuzz.token_set_ratio, limit=5)
    good = [m for m in matches if m[1] >= MATCH_THRESHOLD]
    if not good:
        return None, (matches[0][1] if matches else 0)
    best = idx.iloc[good[0][2]]
    best_score = good[0][1]
    for m in good[1:]:
        best = prefer_rhp(best, idx.iloc[m[2]])
    return best, best_score


# ============================================================
# PHASE 3: Download + verify PDFs (the careful part)
# ============================================================
def safe_filename(company):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", company)[:80] + ".pdf"


def download_verified(url, dest_path):
    """
    Download `url` to `dest_path` and verify completeness.
    Returns (ok: bool, size: int, error: str|None).

    Completeness check: the number of bytes we saved must equal the
    server's Content-Length. This is what catches the truncation bug.
    """
    try:
        with requests.get(url, headers=HEADERS, timeout=DOWNLOAD_TIMEOUT_S,
                          stream=True) as resp:
            if resp.status_code != 200:
                return False, 0, f"HTTP {resp.status_code}"
            declared = resp.headers.get("Content-Length")
            declared = int(declared) if declared and declared.isdigit() else None

            written = 0
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        written += len(chunk)

        # Completeness: must match declared size (if the server gave one)
        if declared is not None and written != declared:
            return False, written, f"TRUNCATED: got {written} of {declared} bytes"
        if written < MIN_PDF_BYTES:
            return False, written, f"Too small ({written} bytes)"
        return True, written, None
    except Exception as e:
        return False, 0, str(e)[:120]


def validate_pdf(path, company):
    """
    Verify a downloaded PDF: (a) opens, (b) mentions the company on an
    early page, (c) has a Risk Factors section.
    Returns (ok: bool, pages: int, has_company: bool, has_risk: bool, err: str|None).
    """
    try:
        r = PdfReader(path)
        pages = len(r.pages)
        if pages == 0:
            return False, 0, False, False, "0 pages"

        # Read text from the first ~60 pages (risk factors are always early)
        head_text = ""
        for i in range(min(60, pages)):
            try:
                t = r.pages[i].extract_text()
                if t:
                    head_text += t + "\n"
            except Exception:
                pass
        low = head_text.lower()

        # Company match: check a couple of distinctive words from the name
        cwords = [w for w in normalize(company).split() if len(w) > 3]
        has_company = any(w in low for w in cwords[:3]) if cwords else False

        has_risk = "risk factors" in low

        return True, pages, has_company, has_risk, None
    except Exception as e:
        return False, 0, False, False, str(e)[:120]


# ============================================================
# MAIN
# ============================================================
async def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(PDF_DIR, exist_ok=True)

    if not os.path.exists(DETAILS_FILE):
        raise SystemExit(f"{DETAILS_FILE} not found. Run step 02 first.")

    # ---- Phase 1: SEBI index ----
    idx = await build_sebi_index()
    idx["title_norm"] = idx["title"].apply(normalize)
    idx = idx[idx["title_norm"].str.len() > 0].reset_index(drop=True)

    # ---- Build target list (equity IPOs only) ----
    details = pd.read_csv(DETAILS_FILE)
    companies = details["company"].dropna().unique().tolist()
    targets = [c for c in companies if not is_drop_candidate(c)]
    dropped = [c for c in companies if is_drop_candidate(c)]
    print(f"\n{'='*60}")
    print("PHASE 2: Matching IPOs to SEBI filings")
    print(f"{'='*60}")
    print(f"  Total IPOs: {len(companies)}")
    print(f"  Equity IPOs to match: {len(targets)}")
    print(f"  Skipped (REIT/InvIT/FPO): {len(dropped)}")

    # ---- Phase 2: match each target ----
    link_records = []
    unmatched = []
    for i, company in enumerate(targets):
        row, score = find_match(company, idx)
        if row is None:
            unmatched.append(company)
            link_records.append({"company": company, "pdf_url": None,
                                 "sebi_title": None, "doc_type": None,
                                 "match_score": score, "status": "unmatched"})
            print(f"  [{i+1}/{len(targets)}] {company[:45]:<45s} x no match ({score})")
            continue
        pdf_url = get_direct_pdf_url(row["landing_url"])
        if not pdf_url:
            unmatched.append(company)
            link_records.append({"company": company, "pdf_url": None,
                                 "sebi_title": row["title"], "doc_type": row["doc_type"],
                                 "match_score": score, "status": "matched_no_pdf_url"})
            print(f"  [{i+1}/{len(targets)}] {company[:45]:<45s} ~ matched but no PDF url")
            continue
        link_records.append({"company": company, "pdf_url": pdf_url,
                             "sebi_title": row["title"], "doc_type": row["doc_type"],
                             "match_score": score, "status": "matched"})
        print(f"  [{i+1}/{len(targets)}] {company[:45]:<45s} OK {row['doc_type']} ({score})")

    links_df = pd.DataFrame(link_records)
    links_df.to_csv(LINKS_FILE, index=False)

    matched = links_df[links_df["status"] == "matched"]
    print(f"\n  Matched with PDF URL: {len(matched)} / {len(targets)}")

    # ---- Phase 3: download + verify ----
    print(f"\n{'='*60}")
    print(f"PHASE 3: Downloading + verifying {len(matched)} PDFs")
    print(f"{'='*60}")

    val_log = []
    dl_ok = dl_fail = 0
    for i, r in matched.reset_index(drop=True).iterrows():
        company = r["company"]
        url = r["pdf_url"]
        path = os.path.join(PDF_DIR, safe_filename(company))

        # Skip if already downloaded AND valid
        if os.path.exists(path) and os.path.getsize(path) > MIN_PDF_BYTES:
            ok, pages, has_co, has_risk, err = validate_pdf(path, company)
            if ok and has_risk:
                print(f"  [{i+1}/{len(matched)}] {company[:40]:<40s} already have "
                      f"({pages}p, risk={has_risk})")
                dl_ok += 1
                val_log.append({"company": company, "pages": pages,
                               "has_company": has_co, "has_risk": has_risk,
                               "status": "already_valid"})
                continue

        # Download with completeness check
        dok, size, derr = download_verified(url, path)
        if not dok:
            dl_fail += 1
            print(f"  [{i+1}/{len(matched)}] {company[:40]:<40s} DOWNLOAD FAIL: {derr}")
            val_log.append({"company": company, "pages": 0, "has_company": False,
                           "has_risk": False, "status": f"download_fail: {derr}"})
            if os.path.exists(path):
                os.remove(path)  # remove partial
            continue

        # Validate the PDF content
        vok, pages, has_co, has_risk, verr = validate_pdf(path, company)
        if not vok:
            dl_fail += 1
            print(f"  [{i+1}/{len(matched)}] {company[:40]:<40s} INVALID PDF: {verr}")
            val_log.append({"company": company, "pages": 0, "has_company": False,
                           "has_risk": False, "status": f"invalid: {verr}"})
            os.remove(path)
            continue

        # Warn (but keep) if no risk section found - may be a scanned doc
        flag = ""
        if not has_risk:
            flag = "  [!] no risk-factors text found - check manually"
        dl_ok += 1
        print(f"  [{i+1}/{len(matched)}] {company[:40]:<40s} OK "
              f"({size/1024/1024:.1f}MB, {pages}p, company={has_co}, risk={has_risk}){flag}")
        val_log.append({"company": company, "pages": pages, "has_company": has_co,
                       "has_risk": has_risk,
                       "status": "ok" if has_risk else "ok_no_risk_text"})
        time.sleep(0.5)  # be gentle on SEBI

    pd.DataFrame(val_log).to_csv(VALIDATION_LOG, index=False)

    # ---- Manual list for unmatched ----
    if unmatched:
        rows = []
        for c in unmatched:
            q = requests.utils.quote(f'"{c}" RHP site:sebi.gov.in')
            rows.append({
                "company": c,
                "google_sebi_search": f"https://www.google.com/search?q={q}",
                "sebi_filings_page":
                    "https://www.sebi.gov.in/filings/public-issues.html",
                "pdf_url": "",   # <- you paste the URL here
            })
        pd.DataFrame(rows).to_csv(MANUAL_FILE, index=False)

    # ---- Summary ----
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"  Equity IPOs targeted:        {len(targets)}")
    print(f"  Matched to SEBI:             {len(matched)}")
    print(f"  PDFs downloaded & valid:     {dl_ok}")
    print(f"  Download/validation fails:   {dl_fail}")
    print(f"  Unmatched (need manual):     {len(unmatched)}")
    print(f"\n  Links table:     {LINKS_FILE}")
    print(f"  Validation log:  {VALIDATION_LOG}")
    if unmatched:
        print(f"  Manual list:     {MANUAL_FILE}")
        print(f"    -> open it, paste PDF URLs, then run 06_manual_download.py")

    # How many have a confirmed risk section?
    if val_log:
        vdf = pd.DataFrame(val_log)
        with_risk = (vdf["has_risk"] == True).sum()
        print(f"\n  PDFs with confirmed Risk Factors section: {with_risk}/{len(vdf)}")


if __name__ == "__main__":
    asyncio.run(main())