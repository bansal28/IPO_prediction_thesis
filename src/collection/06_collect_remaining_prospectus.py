"""
STEP 06: Collect the REMAINING prospectus PDFs (fixes all known gaps)
=====================================================================
Step 05 downloaded 270 valid PDFs but left gaps. Analysis of the
validation log identified THREE distinct problems. This script fixes all
of them in one pass, WITHOUT re-downloading the 270 that are already good.

PROBLEM 1 - download failures (81 IPOs):
    SEBI drops the connection on large files (IncompleteRead / timeout).
    FIX: HTTP Range/resume - continue from where the download broke -
    plus retries, a longer read timeout, and a pause between files.

PROBLEM 2 - "matched_no_pdf_url" (64 IPOs):
    Step 05's URL regex only matched the NEW absolute-URL format. Older
    (2019-2020) landing pages use a RELATIVE path (attachdocs/...).
    FIX: extract both formats; prepend the base URL to relative paths.

PROBLEM 3 - corrigendum/addendum mismatches (23 IPOs):
    Step 05's matcher sometimes matched a 1-page "Corrigendum to RHP" or
    "Addendum to RHP" (a post-filing amendment) instead of the actual
    prospectus. Those have no Risk Factors section.
    FIX: reject amendment titles when matching; prefer the real RHP over
    DRHP; require the company's distinctive words to actually match (so we
    don't grab a neighbouring company like Bajaj vs Aadhar Housing).
    Any already-downloaded 1-page amendment PDF is deleted and re-fetched.

DECIDING WHAT TO DO:
    For every equity IPO it checks data/prospectus_pdfs/ first. A PDF is
    considered GOOD only if it opens AND is large enough AND has enough
    pages (>=50) - this automatically flags the tiny corrigendum PDFs as
    NOT good, so they get re-fetched. The 270 real prospectuses are kept.
    Re-running is always safe and resumes partial downloads.

INPUTS:
    data/raw/raw_prospectus_links.csv
    data/raw/sebi_index.csv
    data/prospectus_pdfs/               (already-downloaded PDFs)
OUTPUTS:
    data/prospectus_pdfs/                    (new/fixed PDFs)
    data/raw/raw_prospectus_links_final.csv
    data/raw/manual_download_needed.csv      (only true leftovers)
    data/prospectus_pdfs/_validation_log.csv (rewritten for all)

SETUP:  pip install pandas requests rapidfuzz pypdf
RUN:    python src/collection/06_collect_remaining_prospectus.py
"""

import pandas as pd
import requests
import os
import re
import time
import logging

logging.getLogger("pypdf").setLevel(logging.ERROR)

try:
    from rapidfuzz import fuzz, process
except ImportError:
    raise SystemExit("pip install rapidfuzz")
try:
    from pypdf import PdfReader
except ImportError:
    raise SystemExit("pip install pypdf")


# ============================================================
# CONFIG
# ============================================================
RAW_DIR = "data/raw"
PDF_DIR = "data/prospectus_pdfs"

LINKS_FILE = os.path.join(RAW_DIR, "raw_prospectus_links.csv")
SEBI_INDEX_FILE = os.path.join(RAW_DIR, "sebi_index.csv")
FINAL_LINKS_FILE = os.path.join(RAW_DIR, "raw_prospectus_links_final.csv")
MANUAL_FILE = os.path.join(RAW_DIR, "manual_download_needed.csv")
VALIDATION_LOG = os.path.join(PDF_DIR, "_validation_log.csv")

DOWNLOAD_TIMEOUT_S = 300
MAX_DL_RETRIES = 6
PAUSE_BETWEEN_FILES_S = 3.0
MIN_PDF_BYTES = 300_000
MIN_PDF_PAGES = 50            # a real RHP/DRHP is hundreds of pages;
                             # this rejects 1-3 page corrigendum PDFs
MATCH_THRESHOLD = 82

SEBI_BASE = "https://www.sebi.gov.in/sebi_data/"
HEADERS = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36")}

DROP_PATTERNS = ["REIT", "Trust", "InvIT"]
KNOWN_FPOS = {"Yes Bank Ltd.", "Ruchi Soya Industries Ltd.", "Vodafone Idea Ltd."}
KNOWN_REIT_NAMES = {"Embassy Office Parks", "Mindspace Business Parks"}

# Titles containing any of these are amendments, NOT the prospectus itself
AMENDMENT_WORDS = ["corrigendum", "addendum", "corigendum", "corignedum",
                   "corrigenda", "amendment"]


def is_drop_candidate(c):
    if any(p in c for p in DROP_PATTERNS):
        return True
    return c in KNOWN_FPOS or c in KNOWN_REIT_NAMES


def is_amendment_title(title):
    t = str(title).lower()
    return any(w in t for w in AMENDMENT_WORDS)


def normalize(name):
    if not isinstance(name, str):
        return ""
    n = name.lower().strip()
    for suf in [" - rhp", "- rhp", " - drhp", "- drhp", " - prospectus",
                " -rhp", " -drhp", " rhp", " drhp", " - udrhp 1",
                " - red hearing prospectus", " - red herring prospectus"]:
        n = n.replace(suf, " ")
    for w in AMENDMENT_WORDS:
        n = n.replace(w, " ")
    n = n.replace(" to the ", " ").replace(" to ", " ").replace(" of ", " ")
    for suf in [" limited", " ltd.", " ltd", " pvt.", " pvt", " private",
                " co.", " co", " corp.", " corp", " corporation"]:
        if n.endswith(suf):
            n = n[: -len(suf)].strip()
    n = re.sub(r"[^\w\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def safe_filename(company):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", company)[:80] + ".pdf"


# ============================================================
# MATCHING (rejects amendments; prefers real RHP; guards company identity)
# ============================================================
def find_real_match(company, sebi):
    """
    Find the best NON-amendment SEBI entry for `company`.
    Preference order: RHP (real) > DRHP (real). Requires that the
    company's distinctive words actually appear in the title, so we don't
    grab a neighbouring company.
    Returns (row, score) or (None, best_score).
    """
    cnorm = normalize(company)
    if not cnorm:
        return None, 0
    cwords = set(w for w in cnorm.split() if len(w) > 2)

    # Score every candidate; drop amendments
    candidates = []
    for _, row in sebi.iterrows():
        if is_amendment_title(row["title"]):
            continue
        tnorm = normalize(row["title"])
        score = fuzz.token_set_ratio(cnorm, tnorm)
        if score < MATCH_THRESHOLD:
            continue
        # Identity guard: at least half the company's distinctive words
        # must be present in the title
        twords = set(tnorm.split())
        if cwords:
            overlap = len(cwords & twords) / len(cwords)
            if overlap < 0.5:
                continue
        candidates.append((row, score))

    if not candidates:
        return None, 0

    # Prefer RHP over DRHP, then higher score
    def sort_key(item):
        row, score = item
        is_rhp = 1 if row["doc_type"] == "RHP" else 0
        return (is_rhp, score)
    candidates.sort(key=sort_key, reverse=True)
    return candidates[0][0], candidates[0][1]


# ============================================================
# PDF-URL EXTRACTION (both formats)
# ============================================================
FULL_URL_RE = re.compile(
    r"https?://www\.sebi\.gov\.in/sebi_data/[^\s\"'<>]+\.pdf", re.IGNORECASE)
REL_PATH_RE = re.compile(
    r"(?:sebi_data/)?(attachdocs/[^\s\"'<>]+\.pdf)", re.IGNORECASE)


def extract_pdf_url(landing_url):
    try:
        resp = requests.get(landing_url, headers=HEADERS, timeout=60)
        if resp.status_code != 200:
            return None
        html = resp.text
        for m in FULL_URL_RE.findall(html):
            if "abridged" not in m.lower():
                return m
        for m in REL_PATH_RE.findall(html):
            if "abridged" not in m.lower():
                return SEBI_BASE + m
        allm = FULL_URL_RE.findall(html)
        if allm:
            return allm[0]
        relm = REL_PATH_RE.findall(html)
        if relm:
            return SEBI_BASE + relm[0]
        return None
    except Exception:
        return None


# ============================================================
# DOWNLOAD WITH RESUME
# ============================================================
def get_remote_size(url):
    try:
        r = requests.head(url, headers=HEADERS, timeout=60, allow_redirects=True)
        cl = r.headers.get("Content-Length")
        return int(cl) if cl and cl.isdigit() else None
    except Exception:
        return None


def download_resumable(url, dest_path):
    remote_size = get_remote_size(url)
    tmp = dest_path + ".part"
    for attempt in range(1, MAX_DL_RETRIES + 1):
        have = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        if remote_size and have >= remote_size:
            break
        h = dict(HEADERS)
        mode = "wb"
        if have > 0:
            h["Range"] = f"bytes={have}-"
            mode = "ab"
        try:
            with requests.get(url, headers=h, timeout=DOWNLOAD_TIMEOUT_S,
                              stream=True) as resp:
                if resp.status_code == 200 and have > 0:
                    mode = "wb"; have = 0     # server ignored Range; restart
                elif resp.status_code not in (200, 206):
                    if attempt < MAX_DL_RETRIES:
                        time.sleep(3 * attempt); continue
                    return False, have, f"HTTP {resp.status_code}"
                with open(tmp, mode) as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
        except Exception as e:
            if attempt < MAX_DL_RETRIES:
                wait_s = 4 * attempt
                cur = os.path.getsize(tmp) if os.path.exists(tmp) else 0
                print(f"        drop on attempt {attempt} ({str(e)[:35]}); "
                      f"resuming in {wait_s}s (have {cur} bytes)")
                time.sleep(wait_s); continue
            return False, have, f"connection failed: {str(e)[:50]}"

    if not os.path.exists(tmp):
        return False, 0, "no data"
    final = os.path.getsize(tmp)
    if remote_size and final != remote_size:
        return False, final, f"size mismatch {final}/{remote_size}"
    if final < MIN_PDF_BYTES:
        return False, final, f"too small ({final})"
    os.replace(tmp, dest_path)
    return True, final, None


def validate_pdf(path, company):
    try:
        r = PdfReader(path)
        pages = len(r.pages)
        if pages < MIN_PDF_PAGES:
            return False, pages, False, False, f"only {pages} pages (amendment?)"
        head = ""
        for i in range(min(60, pages)):
            try:
                t = r.pages[i].extract_text()
                if t:
                    head += t + "\n"
            except Exception:
                pass
        low = head.lower()
        cwords = [w for w in normalize(company).split() if len(w) > 3]
        has_co = any(w in low for w in cwords[:3]) if cwords else False
        has_risk = "risk factors" in low
        return True, pages, has_co, has_risk, None
    except Exception as e:
        return False, 0, False, False, str(e)[:100]


def pdf_is_good_on_disk(path):
    """A PDF already on disk counts as good only if it opens AND has
    enough pages (rejects the 1-3 page corrigendum files)."""
    if not os.path.exists(path) or os.path.getsize(path) < MIN_PDF_BYTES:
        return False
    try:
        r = PdfReader(path)
        return len(r.pages) >= MIN_PDF_PAGES
    except Exception:
        return False


# ============================================================
# MAIN
# ============================================================
def main():
    os.makedirs(PDF_DIR, exist_ok=True)
    links = pd.read_csv(LINKS_FILE)
    sebi = pd.read_csv(SEBI_INDEX_FILE)
    title_to_landing = dict(zip(sebi["title"], sebi["landing_url"]))

    print("=" * 60)
    print("STEP 06: Fetch/fix remaining prospectus PDFs")
    print("=" * 60)

    # Work list = every equity IPO whose on-disk PDF is NOT good
    work = []
    already_ok = 0
    for _, row in links.iterrows():
        company = row["company"]
        if is_drop_candidate(company):
            continue
        path = os.path.join(PDF_DIR, safe_filename(company))
        if pdf_is_good_on_disk(path):
            already_ok += 1
            continue
        # If a junk (tiny) PDF exists, remove it so it gets re-fetched
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
        work.append(row)

    print(f"  Already-good PDFs (kept, >= {MIN_PDF_PAGES} pages): {already_ok}")
    print(f"  To fetch/fix: {len(work)}")

    # ---- Phase A: resolve a REAL (non-amendment) URL for each work item ----
    print(f"\n{'='*60}\nPHASE A: Resolving real prospectus URLs\n{'='*60}")
    resolved = []
    still_no_url = []
    for i, row in enumerate(work):
        company = row["company"]
        existing_url = row.get("pdf_url")
        existing_title = row.get("sebi_title")

        # Decide whether we need to RE-MATCH:
        #   - if there's no URL, or
        #   - if the previously matched title was an amendment
        need_rematch = (not isinstance(existing_url, str) or not existing_url.strip()
                        or is_amendment_title(existing_title))

        if need_rematch:
            match_row, score = find_real_match(company, sebi)
            if match_row is None:
                still_no_url.append(company)
                resolved.append({"company": company, "pdf_url": None,
                                 "sebi_title": None, "doc_type": None,
                                 "match_score": score})
                print(f"  [{i+1}/{len(work)}] {company[:42]:<42s} no real match")
                continue
            landing = title_to_landing.get(match_row["title"])
            url = extract_pdf_url(landing) if landing else None
            if not url:
                still_no_url.append(company)
                resolved.append({"company": company, "pdf_url": None,
                                 "sebi_title": match_row["title"],
                                 "doc_type": match_row["doc_type"],
                                 "match_score": score})
                print(f"  [{i+1}/{len(work)}] {company[:42]:<42s} matched, no URL")
                continue
            resolved.append({"company": company, "pdf_url": url,
                             "sebi_title": match_row["title"],
                             "doc_type": match_row["doc_type"],
                             "match_score": score})
            tag = "re-matched" if is_amendment_title(existing_title) else "resolved"
            print(f"  [{i+1}/{len(work)}] {company[:42]:<42s} {tag} "
                  f"({match_row['doc_type']})")
            time.sleep(0.4)
        else:
            # URL already fine (these are the download-failure cases)
            resolved.append({"company": company, "pdf_url": existing_url,
                             "sebi_title": existing_title,
                             "doc_type": row.get("doc_type"),
                             "match_score": row.get("match_score")})

    resolved_df = pd.DataFrame(resolved)
    have_url = resolved_df[resolved_df["pdf_url"].notna()].reset_index(drop=True)
    print(f"\n  Have URLs: {len(have_url)} / {len(work)}   "
          f"No URL (manual): {len(still_no_url)}")

    # ---- Phase B: download + verify ----
    print(f"\n{'='*60}\nPHASE B: Downloading {len(have_url)} PDFs (resume)\n{'='*60}")
    val_rows = []
    ok = fail = 0
    for i, row in have_url.iterrows():
        company = row["company"]
        url = row["pdf_url"]
        path = os.path.join(PDF_DIR, safe_filename(company))

        dok, size, derr = download_resumable(url, path)
        if not dok:
            fail += 1
            print(f"  [{i+1}/{len(have_url)}] {company[:40]:<40s} DL FAIL: {derr}")
            val_rows.append({"company": company, "pages": 0, "has_company": False,
                             "has_risk": False, "status": f"download_fail"})
            time.sleep(PAUSE_BETWEEN_FILES_S); continue

        vok, pages, has_co, has_risk, verr = validate_pdf(path, company)
        if not vok:
            fail += 1
            print(f"  [{i+1}/{len(have_url)}] {company[:40]:<40s} INVALID: {verr}")
            val_rows.append({"company": company, "pages": pages,
                             "has_company": has_co, "has_risk": has_risk,
                             "status": f"invalid: {verr}"})
            if os.path.exists(path):
                os.remove(path)
            time.sleep(PAUSE_BETWEEN_FILES_S); continue

        ok += 1
        flag = "" if has_risk else "  [!] no risk text"
        print(f"  [{i+1}/{len(have_url)}] {company[:40]:<40s} OK "
              f"({size/1024/1024:.1f}MB, {pages}p, risk={has_risk}){flag}")
        val_rows.append({"company": company, "pages": pages, "has_company": has_co,
                         "has_risk": has_risk,
                         "status": "ok" if has_risk else "ok_no_risk_text"})
        time.sleep(PAUSE_BETWEEN_FILES_S)

    # ---- Rebuild the validation log for ALL good PDFs on disk ----
    print(f"\n{'='*60}\nRebuilding validation log for all PDFs on disk\n{'='*60}")
    all_val = []
    for _, row in links.iterrows():
        company = row["company"]
        if is_drop_candidate(company):
            continue
        path = os.path.join(PDF_DIR, safe_filename(company))
        if not os.path.exists(path):
            continue
        vok, pages, has_co, has_risk, verr = validate_pdf(path, company)
        all_val.append({"company": company, "pages": pages,
                        "has_company": has_co, "has_risk": has_risk,
                        "status": "ok" if (vok and has_risk)
                                  else ("ok_no_risk_text" if vok else f"invalid")})
    pd.DataFrame(all_val).to_csv(VALIDATION_LOG, index=False)

    resolved_df.to_csv(FINAL_LINKS_FILE, index=False)
    if still_no_url:
        rows = []
        for c in still_no_url:
            q = requests.utils.quote(f'"{c}" RHP site:sebi.gov.in')
            rows.append({"company": c,
                         "google_sebi_search": f"https://www.google.com/search?q={q}",
                         "sebi_filings_page":
                             "https://www.sebi.gov.in/filings/public-issues.html",
                         "pdf_url": ""})
        pd.DataFrame(rows).to_csv(MANUAL_FILE, index=False)

    # ---- Summary ----
    vdf = pd.DataFrame(all_val)
    total_good = len(vdf)
    with_risk = (vdf["has_risk"] == True).sum() if len(vdf) else 0

    print(f"\n{'='*60}\nSUMMARY\n{'='*60}")
    print(f"  Newly downloaded this run:      {ok}")
    print(f"  Failed this run:                {fail}")
    print(f"  Still need manual lookup:       {len(still_no_url)}")
    print(f"  TOTAL valid PDFs on disk:       {total_good}")
    print(f"  ...with confirmed Risk Factors: {with_risk}")
    if len(vdf):
        no_risk = vdf[vdf["has_risk"] != True]
        if len(no_risk):
            print(f"\n  PDFs still lacking risk text ({len(no_risk)}) "
                  f"- likely scanned/image PDFs, check manually:")
            for _, r in no_risk.head(20).iterrows():
                print(f"     - {r['company']} ({r['pages']}p)")
    if still_no_url:
        print(f"\n  Manual list ({len(still_no_url)}):")
        for c in still_no_url:
            print(f"     - {c}")
    if fail > 0:
        print(f"\n  Re-run to resume failed downloads (partial files kept).")


if __name__ == "__main__":
    main()