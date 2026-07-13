"""
STEP 03a-PATCH-V2: Robust recovery of failed risk-section extractions
======================================================================
Second-pass patch. Read _extraction_log.csv, find rows whose status is
not "ok" or already "ok_..." from v1, and try again with the fixes
below (each traced back to a concrete failure observed in v1).

FIXES OVER v1
  1. Allow en-dash / em-dash BEFORE the Roman numeral in the start
     header — v1's `\s+` between SECTION and the numeral rejected
     "SECTION – II- RISK FACTORS" (Amir Chand, Tolins Tyres).
  2. Require any candidate section to be at least MIN_PAGES pages long,
     and at most MAX_PAGES. Rejects the ToC-collision 0-page range
     (Precision Pipes) and the 215-page overshoot (Sai Silks).
  3. When scanning for the end marker, accept a curated list of
     next-section titles (INTRODUCTION, THE OFFER, CAPITAL STRUCTURE,
     etc.) in addition to "SECTION [Roman]" — many prospectuses don't
     use Roman-numeral section numbering at all (Aeroflex, Sanstar,
     Vibhor Steel Tubes, Krystal Integrated, Veranda Learning).
  4. Reversed word order: "II. SECTION – RISK FACTORS" (Atlanta
     Electricals). Added as an explicit alternative start pattern.
  5. Letter numbering: "SECTION – B: RISK FACTORS" (Sai Silks 2009).
     Start pattern now accepts a single A-Z after SECTION as well as
     a Roman numeral.
  6. Scanned PDFs with no text layer (Manoj Vaibhav Gems) are detected
     early via a document-level char-count and flagged as needing OCR;
     no false extraction is attempted.

INPUTS
  data/prospectus_pdfs/*.pdf
  data/processed/risk_sections/_extraction_log.csv   (must exist)

OUTPUTS (per PDF re-processed)
  data/processed/risk_sections/{stem}.md
  Updated row in _extraction_log.csv

RUN
  python3 src/processing/03a_patch_v2.py
  (from the project root)
"""

import contextlib
import csv
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore")

import pymupdf
import pymupdf4llm


# ============================================================
# PATHS  (mirror 03a)
# ============================================================
PDF_DIR  = "data/prospectus_pdfs"
OUT_DIR  = "data/processed/risk_sections"
LOG_FILE = os.path.join(OUT_DIR, "_extraction_log.csv")

MIN_CHARS  = 5000     # anything shorter than 5k chars is suspicious
MIN_PAGES  = 5        # reject spurious start/end where the span < 5 pages
MAX_PAGES  = 120      # reject spurious runaway ranges (Sai Silks 215p)
MIN_TEXT_CHARS_FIRST_10P = 1000   # threshold below which we call it scanned


# ============================================================
# REGEXES
# ============================================================
# Separator class: whitespace + any dash-like character + colon + period.
SEP_ANY = r"[\s:\-\u2010-\u2015\u2212.]"
ROMAN   = r"[IVX]+"
LETTER  = r"[A-Z]"

# START patterns — tried in order. Each must match the WHOLE line.
START_PATTERNS = [
    # A: strict — "SECTION II: RISK FACTORS", "SECTION II - RISK FACTORS"
    re.compile(rf"^SECTION\s+{ROMAN}{SEP_ANY}*RISK\s+FACTORS?\s*$",
               re.IGNORECASE),
    # B: en-dash / hyphen allowed BEFORE the Roman numeral too
    #    (fixes Amir Chand: "SECTION – II- RISK FACTORS")
    re.compile(rf"^SECTION{SEP_ANY}+{ROMAN}{SEP_ANY}*RISK\s+FACTORS?\s*$",
               re.IGNORECASE),
    # C: letter numbering — "SECTION – B: RISK FACTORS" (Sai Silks 2009)
    re.compile(rf"^SECTION{SEP_ANY}+{LETTER}{SEP_ANY}*RISK\s+FACTORS?\s*$",
               re.IGNORECASE),
    # D: reversed word order — "II. SECTION – RISK FACTORS" (Atlanta)
    re.compile(rf"^{ROMAN}{SEP_ANY}+SECTION{SEP_ANY}+RISK\s+FACTORS?\s*$",
               re.IGNORECASE),
    # E: standalone all-caps heading — "RISK FACTORS" alone, no prefix
    #    (Aeroflex, Sanstar, Vibhor, Krystal). CASE-SENSITIVE — real
    #    section headers in DRHPs are always all-caps; a title-case
    #    "Risk Factors" appearing on a line by itself is a summary
    #    sub-heading and must be rejected (Krystal p.18, Sanstar p.30).
    re.compile(r"^RISK\s+FACTORS?\s*$"),   # NO re.IGNORECASE
]

# END markers: the next major-section header of any recognised form.
# Order matters — some prospectuses use "SECTION III", others use plain
# "THE OFFER" or "INTRODUCTION" without a section prefix.
END_PATTERNS = [
    re.compile(rf"^SECTION{SEP_ANY}+{ROMAN}\b", re.IGNORECASE),   # "SECTION III ..."
    re.compile(rf"^SECTION{SEP_ANY}+{LETTER}\b", re.IGNORECASE),  # "SECTION – C ..."
    re.compile(rf"^{ROMAN}{SEP_ANY}+SECTION\b", re.IGNORECASE),   # "III. SECTION ..."
    re.compile(r"^INTRODUCTION\s*$", re.IGNORECASE),
    re.compile(r"^THE\s+(OFFER|ISSUE)\s*$", re.IGNORECASE),
    re.compile(r"^GENERAL\s+INFORMATION\s*$", re.IGNORECASE),
    re.compile(r"^CAPITAL\s+STRUCTURE\s*$", re.IGNORECASE),
    re.compile(r"^OBJECTS\s+OF\s+THE\s+(OFFER|ISSUE)\s*$", re.IGNORECASE),
    re.compile(r"^SUMMARY\s+OF\s+THE\s+(OFFER\s+DOCUMENT|ISSUE)\s*$",
               re.IGNORECASE),
    re.compile(r"^OUR\s+BUSINESS\s*$", re.IGNORECASE),
    re.compile(r"^INDUSTRY\s+OVERVIEW\s*$", re.IGNORECASE),
]

# ToC lines to skip: dot leaders or a page number tail like "..... 20"
TOC_LEADER = re.compile(r"\.{5,}|\.\s*\d+\s*$|\[\s*•\s*\]")


@contextlib.contextmanager
def suppress_stdout():
    """FD-level stdout suppression (mupdf writes from C, not Python)."""
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


def is_scanned(doc, sample_pages=10):
    """Return True if the first N pages contain almost no extractable
    text (i.e. the PDF is an image-only scan with no OCR layer)."""
    n = min(sample_pages, doc.page_count)
    total_chars = 0
    for i in range(n):
        try:
            total_chars += len(doc.load_page(i).get_text("text") or "")
        except Exception:
            pass
    return total_chars < MIN_TEXT_CHARS_FIRST_10P


def is_end_marker(line, start_pattern):
    """A line is a valid end-marker if it matches ANY of END_PATTERNS
    AND it does NOT match the start pattern (avoids ending on a duplicate
    RISK FACTORS heading — see Barbeque-Nation, where P3 caught a
    sub-heading on p29 and then closed on the real header at p36)."""
    if start_pattern.match(line):
        return False
    return any(p.match(line) for p in END_PATTERNS)


def find_valid_bounds(doc, start_pattern):
    """
    Iterate over ALL positions where `start_pattern` matches, and for
    each, look for the next end marker. Accept the FIRST (start, end)
    range that is at least MIN_PAGES and at most MAX_PAGES long.
    Return (start, end, note). note is empty on success, or an
    explanation of why nothing valid was found.
    """
    total = doc.page_count

    # First, cache each page's lines to avoid re-extracting text.
    page_lines = []
    for i in range(total):
        try:
            t = doc.load_page(i).get_text("text") or ""
        except Exception:
            t = ""
        lines = []
        for raw in t.split("\n"):
            line = raw.strip()
            if not line or TOC_LEADER.search(line):
                continue
            lines.append(line)
        page_lines.append(lines)

    # Find all candidate start pages
    candidate_starts = [
        i for i, lines in enumerate(page_lines)
        if any(start_pattern.match(ln) for ln in lines)
    ]
    if not candidate_starts:
        return None, None, "no start match"

    # For each start, walk forward to find the first valid end marker.
    # Accept the first range that satisfies MIN_PAGES..MAX_PAGES.
    tried = []
    for s in candidate_starts:
        for e in range(s + 1, total):
            if any(is_end_marker(ln, start_pattern) for ln in page_lines[e]):
                span = e - s
                if MIN_PAGES <= span <= MAX_PAGES:
                    return s, e, ""
                tried.append(f"pp{s}-{e}(span={span},"
                             f"{'small' if span<MIN_PAGES else 'large'})")
                break   # for this start, only consider the FIRST end candidate
        else:
            # No end marker found for this start; fall back to EOF if reasonable
            span = total - s
            if MIN_PAGES <= span <= MAX_PAGES:
                return s, total, "eof_fallback"
            tried.append(f"pp{s}-EOF(span={span})")

    return None, None, "no valid range: " + " | ".join(tried[:6])


def extract_markdown(pdf_path, start, end):
    with suppress_stdout():
        return pymupdf4llm.to_markdown(
            pdf_path,
            pages=list(range(start, end)),
            show_progress=False,
        )


def extract_plaintext(doc, start, end):
    chunks = []
    for i in range(start, end):
        try:
            chunks.append(doc.load_page(i).get_text("text") or "")
        except Exception:
            chunks.append("")
    return "\n".join(chunks)


# ============================================================
# PER-PDF RECOVERY
# ============================================================
def recover_one(pdf_path):
    basename = os.path.basename(pdf_path)
    stem = basename[:-4] if basename.lower().endswith(".pdf") else basename
    out_path = os.path.join(OUT_DIR, f"{stem}.md")

    try:
        doc = pymupdf.open(pdf_path)
        if doc.is_encrypted:
            doc.authenticate("")
    except Exception as e:
        return dict(filename=basename, total_pages=0,
                    risk_start_page="", risk_end_page="", risk_pages=0,
                    chars=0, words=0, n_tables=0,
                    status="error", error=f"open_failed: {e}")

    total = doc.page_count

    # Scanned-PDF short-circuit
    if is_scanned(doc):
        doc.close()
        return dict(filename=basename, total_pages=total,
                    risk_start_page="", risk_end_page="", risk_pages=0,
                    chars=0, words=0, n_tables=0,
                    status="manual_review_ocr_needed",
                    error="pdf appears to be image-only "
                          "(no text layer in first 10 pages)")

    # Try each start pattern in order; accept first valid range
    attempts = []
    for label, pattern in [("A_strict",        START_PATTERNS[0]),
                           ("B_endash_pre",    START_PATTERNS[1]),
                           ("C_letter",        START_PATTERNS[2]),
                           ("D_reversed",      START_PATTERNS[3]),
                           ("E_standalone",    START_PATTERNS[4])]:
        start, end, note = find_valid_bounds(doc, pattern)
        if start is None:
            attempts.append(f"{label}=NO({note})")
            continue
        attempts.append(f"{label}=pp{start}-{end}"
                        f"{'(eof)' if note=='eof_fallback' else ''}")

        # Try markdown first
        md_text = None
        md_err = None
        try:
            md_text = extract_markdown(pdf_path, start, end)
        except Exception as e:
            md_err = f"{type(e).__name__}: {e}"

        if md_text and len(md_text) >= MIN_CHARS:
            doc.close()
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(md_text)
            return dict(filename=basename, total_pages=total,
                        risk_start_page=start, risk_end_page=end,
                        risk_pages=end - start,
                        chars=len(md_text), words=len(md_text.split()),
                        n_tables=md_text.count("|---"),
                        status=f"ok_{label}",
                        error=f"tried: {' | '.join(attempts)}")

        # Markdown failed or was too short — plaintext fallback
        pt_text = extract_plaintext(doc, start, end)
        if len(pt_text) >= MIN_CHARS:
            doc.close()
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(pt_text)
            return dict(filename=basename, total_pages=total,
                        risk_start_page=start, risk_end_page=end,
                        risk_pages=end - start,
                        chars=len(pt_text), words=len(pt_text.split()),
                        n_tables=0,
                        status=f"ok_{label}_plaintext",
                        error=f"md_fail: {md_err}; "
                              f"tried: {' | '.join(attempts)}")

        attempts[-1] += f"(md={len(md_text or '')},pt={len(pt_text)})"
        # both empty — try next start pattern

    doc.close()
    return dict(filename=basename, total_pages=total,
                risk_start_page="", risk_end_page="", risk_pages=0,
                chars=0, words=0, n_tables=0,
                status="manual_review",
                error=f"all_patterns_failed: {' | '.join(attempts)}")


# ============================================================
# MAIN
# ============================================================
def hr(c="-"):
    print(c * 76)


def main():
    hr("=")
    print("STEP 03a-PATCH-V2: Robust recovery of failed risk-section extractions")
    hr("=")

    if not os.path.exists(LOG_FILE):
        print(f"  [FATAL] {LOG_FILE} not found. Run 03a first.")
        sys.exit(1)

    with open(LOG_FILE, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        log_rows = list(reader)
    fieldnames = reader.fieldnames

    # Anything that isn't a clean "ok" from the ORIGINAL 03a is fair game.
    # Statuses in scope: no_start_header, error, ok_but_short, manual_review,
    # ok_plaintext_fallback (v1 may have grabbed too many pages).
    def in_scope(status):
        return status not in ("ok",)  # v2 re-checks EVERYTHING except plain "ok"

    todo = [r for r in log_rows if in_scope(r["status"])]
    print(f"  Existing log rows        : {len(log_rows)}")
    print(f"  Rows to re-process       : {len(todo)}")
    print()
    for r in todo:
        print(f"    - {r['filename']:60s} (was: {r['status']})")
    print()
    hr()

    recovered = []
    for i, r in enumerate(todo, 1):
        pdf_path = os.path.join(PDF_DIR, r["filename"])
        if not os.path.exists(pdf_path):
            print(f"  [{i:2d}/{len(todo)}] {r['filename']:60s} "
                  f"PDF NOT FOUND — skipping")
            continue
        new = recover_one(pdf_path)
        recovered.append(new)
        s = str(new["risk_start_page"]) if new["risk_start_page"] != "" else "--"
        e = str(new["risk_end_page"])   if new["risk_end_page"]   != "" else "--"
        rp = new["risk_pages"] if new["risk_pages"] else 0
        print(f"  [{i:2d}/{len(todo)}] {r['filename']:60s} "
              f"pp {s:>4}-{e:<4} ({rp:>3d}p, "
              f"{new['chars']:>7,}c, {new['n_tables']:>4d}t)  {new['status']}")

    # Rewrite log
    patched_by_name = {r["filename"]: r for r in recovered}
    updated_rows = []
    for r in log_rows:
        if r["filename"] in patched_by_name:
            updated_rows.append(patched_by_name[r["filename"]])
        else:
            updated_rows.append(r)

    with open(LOG_FILE, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in updated_rows:
            for k in fieldnames:
                row.setdefault(k, "")
            w.writerow(row)

    print()
    hr("=")
    print("SUMMARY")
    hr()
    by_status = {}
    for r in recovered:
        by_status.setdefault(r["status"], []).append(r["filename"])
    for s, names in sorted(by_status.items()):
        print(f"  {s:36s} {len(names):>3d}")
    print()

    still_broken = [r for r in recovered
                    if r["status"].startswith(("manual_review", "error"))]
    if still_broken:
        print("  Still need manual attention:")
        for r in still_broken:
            print(f"    - {r['filename']:60s}")
            print(f"        {r['status']}: {r['error']}")
    else:
        print("  All PDFs recovered.")

    print()
    print(f"  Updated log: {LOG_FILE}")
    hr("=")


if __name__ == "__main__":
    main()