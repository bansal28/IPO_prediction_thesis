"""
STEP 03a: Extract the Risk Factors section from every prospectus PDF
=====================================================================
Reads every prospectus PDF in data/prospectus_pdfs/, locates the SEBI-
mandated Risk Factors section, and saves the extracted text as one
Markdown file per IPO under data/processed/risk_sections/.

WHAT COUNTS AS THE "RISK FACTORS" SECTION
  Every Indian DRHP/RHP places its Risk Factors section under a header
  of the form:

      SECTION II: RISK FACTORS       (older / most common)
      SECTION II - RISK FACTORS
      SECTION III - RISK FACTORS     (when a summary section precedes)
      SECTION III: RISK FACTORS

  and closes it with the next "SECTION [Roman numeral] ..." header
  (usually "INTRODUCTION" or "OUR BUSINESS"). This script uses that
  boundary and nothing else.

WHY MARKDOWN INSTEAD OF PLAIN TEXT
  Risk Factors sections contain critical tabular disclosures (the
  outstanding-litigation summary by party and proceeding type; the
  contingent-liabilities breakdown by category; related-party
  transaction amounts). Plain-text extraction collapses tables into
  positional whitespace, which forces the downstream LLM to
  reconstruct the row/column structure from spatial layout. Markdown
  preserves table structure explicitly, so numeric extraction quality
  is materially higher — precisely the fields that carry most signal
  under the SEBI materiality-threshold disclosure format.

WHAT THIS SCRIPT DOES NOT DO
  - No LLM. No feature extraction. No schema.
  - No cleaning of pymupdf4llm's markdown beyond what it produces.
  - No decisions about which risks are "material". That is 03b's job.

INPUTS
  data/prospectus_pdfs/*.pdf         (416 verified PDFs)

OUTPUTS
  data/processed/risk_sections/{safe_name}.md         (one per IPO)
  data/processed/risk_sections/_extraction_log.csv    (per-PDF audit)

RUN
  python3 src/processing/03a_extract_risk_sections.py
  (run from the project root)

DEPENDENCIES
  pymupdf, pymupdf4llm
    pip install pymupdf pymupdf4llm --break-system-packages
"""

import contextlib
import csv
import glob
import io
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore")

import pymupdf                       # low-level PDF access
import pymupdf4llm                   # PDF → Markdown for LLM ingestion


@contextlib.contextmanager
def suppress_stdout():
    """
    pymupdf4llm/mupdf writes 'Document parser messages' and Tesseract/OCR
    status to file descriptor 1 (stdout) from C code, bypassing Python's
    sys.stdout wrapper. Redirect the fd itself so 416 PDFs don't produce
    416 chatty banners.
    """
    sys.stdout.flush()
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_fd = os.dup(1)
    try:
        os.dup2(devnull_fd, 1)
        yield
    finally:
        sys.stdout.flush()
        os.dup2(saved_fd, 1)
        os.close(devnull_fd)
        os.close(saved_fd)


# ============================================================
# PATHS
# ============================================================
PDF_DIR  = "data/prospectus_pdfs"
OUT_DIR  = "data/processed/risk_sections"
LOG_FILE = os.path.join(OUT_DIR, "_extraction_log.csv")


# ============================================================
# BOUNDARY DETECTION
# ============================================================
# Dash-like separator between Roman numeral and "RISK FACTORS":
# ASCII hyphen, en-dash, em-dash, figure/quotation/horizontal-bar
# dashes, minus sign, colon, period. Whitespace folded in.
SEP    = r"[\s:\-\u2010-\u2015\u2212.]*"
ROMAN  = r"[IVX]+"

RISK_START   = re.compile(rf"^SECTION\s+{ROMAN}{SEP}RISK\s+FACTORS?\s*$",
                          re.IGNORECASE)
NEXT_SECTION = re.compile(rf"^SECTION\s+{ROMAN}\b",
                          re.IGNORECASE)

# Table-of-contents lines have dot leaders or a trailing page number;
# skip them so the ToC "Risk Factors ..... 20" is not mistaken for
# the section header itself.
TOC_LEADER = re.compile(r"\.{5,}|\.\s*\d+\s*$")


def find_risk_bounds(doc):
    """
    Return (start_page, end_page, total_pages, error).

    start_page is the 0-indexed page on which "SECTION [Roman]
    RISK FACTORS" appears as a standalone header line.
    end_page is the 0-indexed page on which the FOLLOWING
    "SECTION [Roman]" header first appears. The extracted range
    is [start_page, end_page). Both are None if not found.
    """
    total_pages = doc.page_count
    start, end = None, None

    for i in range(total_pages):
        try:
            page_text = doc.load_page(i).get_text("text") or ""
        except Exception:
            continue

        for raw_line in page_text.split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            if TOC_LEADER.search(line):
                continue

            if start is None and RISK_START.match(line):
                start = i
            elif start is not None and end is None \
                    and NEXT_SECTION.match(line) \
                    and not RISK_START.match(line):
                end = i
                return start, end, total_pages, None

    return start, end, total_pages, None


def extract_risk_markdown(pdf_path, start, end):
    """
    Convert pages [start, end) to Markdown via pymupdf4llm. Returns
    the markdown string. mupdf's own status messages are suppressed
    during the call.
    """
    with suppress_stdout():
        return pymupdf4llm.to_markdown(
            pdf_path,
            pages=list(range(start, end)),
            show_progress=False,
        )


# ============================================================
# CLI OUTPUT HELPERS
# ============================================================
def hr(char="-"):
    print(char * 72)


# ============================================================
# MAIN
# ============================================================
def main():
    hr("=")
    print("STEP 03a: Extract Risk Factors sections from prospectus PDFs")
    hr("=")

    if not os.path.isdir(PDF_DIR):
        print(f"  [FATAL] Not found: {PDF_DIR}")
        print(f"          Run this script from the project root.")
        sys.exit(1)

    os.makedirs(OUT_DIR, exist_ok=True)

    pdfs = sorted(glob.glob(os.path.join(PDF_DIR, "*.pdf")))
    if not pdfs:
        print(f"  [FATAL] No PDFs found in {PDF_DIR}")
        sys.exit(1)

    print(f"  Found {len(pdfs)} PDFs in {PDF_DIR}")
    print(f"  Writing extracted risk sections to {OUT_DIR}/")
    print()

    log_rows = []
    n_ok, n_short, n_no_start, n_error = 0, 0, 0, 0
    MIN_CHARS = 5000  # anything shorter is suspicious — flag but keep

    for idx, pdf_path in enumerate(pdfs, start=1):
        basename = os.path.basename(pdf_path)
        stem = basename[:-4] if basename.lower().endswith(".pdf") else basename

        # --- Open PDF ------------------------------------------
        try:
            doc = pymupdf.open(pdf_path)
            if doc.is_encrypted:
                # SEBI's encrypted PDFs (e.g. Exxaro Tiles) use empty passwords
                if not doc.authenticate(""):
                    raise RuntimeError("decrypt_failed: empty password rejected")
        except Exception as e:
            n_error += 1
            print(f"  [{idx:3d}/{len(pdfs)}] {basename:50s}  "
                  f"OPEN FAIL: {type(e).__name__}: {e}")
            log_rows.append({
                "filename": basename, "total_pages": 0,
                "risk_start_page": "", "risk_end_page": "",
                "risk_pages": 0, "chars": 0, "words": 0,
                "n_tables": 0, "status": "error",
                "error": f"open_failed: {e}",
            })
            continue

        # --- Locate boundaries --------------------------------
        start, end, total, err = find_risk_bounds(doc)
        doc.close()

        if err:
            n_error += 1
            print(f"  [{idx:3d}/{len(pdfs)}] {basename:50s}  ERROR: {err}")
            log_rows.append({
                "filename": basename, "total_pages": total,
                "risk_start_page": "", "risk_end_page": "",
                "risk_pages": 0, "chars": 0, "words": 0,
                "n_tables": 0, "status": "error", "error": err,
            })
            continue

        if start is None:
            n_no_start += 1
            print(f"  [{idx:3d}/{len(pdfs)}] {basename:50s}  "
                  f"NO 'SECTION [X] RISK FACTORS' HEADER")
            log_rows.append({
                "filename": basename, "total_pages": total,
                "risk_start_page": "", "risk_end_page": "",
                "risk_pages": 0, "chars": 0, "words": 0,
                "n_tables": 0, "status": "no_start_header", "error": "",
            })
            continue

        if end is None:
            # Header found but no following section marker — fall back
            # to end-of-document so we still capture the section.
            end = total
            status_note = "no_end_marker_fallback_eof"
        else:
            status_note = None

        # --- Extract as markdown ------------------------------
        try:
            md_text = extract_risk_markdown(pdf_path, start, end)
        except Exception as e:
            n_error += 1
            print(f"  [{idx:3d}/{len(pdfs)}] {basename:50s}  "
                  f"MARKDOWN FAIL: {type(e).__name__}: {e}")
            log_rows.append({
                "filename": basename, "total_pages": total,
                "risk_start_page": start, "risk_end_page": end,
                "risk_pages": end - start, "chars": 0, "words": 0,
                "n_tables": 0, "status": "error",
                "error": f"markdown_failed: {e}",
            })
            continue

        chars   = len(md_text)
        words   = len(md_text.split())
        n_pages = end - start
        # A rough count of markdown tables — the "|---|" separator row
        n_tables = md_text.count("|---")

        if chars < MIN_CHARS:
            status = "ok_but_short"
            n_short += 1
            note = f"  [!] short ({chars} chars)"
        elif status_note:
            status = status_note
            note = f"  [!] {status_note}"
        else:
            status = "ok"
            n_ok += 1
            note = ""

        out_path = os.path.join(OUT_DIR, f"{stem}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md_text)

        print(f"  [{idx:3d}/{len(pdfs)}] {basename:50s}  "
              f"pp {start:>4}-{end:<4} "
              f"({n_pages:>3d}p, {words:>6,}w, {n_tables:>3d}t){note}")

        log_rows.append({
            "filename": basename, "total_pages": total,
            "risk_start_page": start, "risk_end_page": end,
            "risk_pages": n_pages, "chars": chars, "words": words,
            "n_tables": n_tables, "status": status, "error": "",
        })

    # ============================================================
    # WRITE LOG
    # ============================================================
    fieldnames = ["filename", "total_pages",
                  "risk_start_page", "risk_end_page", "risk_pages",
                  "chars", "words", "n_tables", "status", "error"]
    with open(LOG_FILE, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(log_rows)

    # ============================================================
    # SUMMARY
    # ============================================================
    print()
    hr("=")
    print("SUMMARY")
    hr()
    print(f"  Total PDFs processed        : {len(pdfs)}")
    print(f"  Clean extraction (ok)       : {n_ok}")
    print(f"  Extracted but < {MIN_CHARS:>5d} chars : {n_short}")
    print(f"  No RISK FACTORS header      : {n_no_start}")
    print(f"  Read/extract errors         : {n_error}")
    print()
    print(f"  Log:      {LOG_FILE}")
    print(f"  Sections: {OUT_DIR}/")
    hr("=")


if __name__ == "__main__":
    main()