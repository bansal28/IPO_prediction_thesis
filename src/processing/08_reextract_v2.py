#!/usr/bin/env python3
"""
08_reextract_v2.py — targeted fix for SEBI-2022 summary-section false matches
                     and Atlanta-style over-extraction.

Purpose
-------
After running 07_reextract_and_certify.py, the Phase 6 EDA revealed two
patterns that v1's audit couldn't detect (because the audit compared
markdown to plain text on the SAME page range — it can't tell if we
picked the wrong range):

  1. SEBI-2022 summary-section trap. Post-2022 Indian prospectuses have
     a mandated "Summary of Risk Factors" block in the executive summary,
     listing ~10 top risks. v1's start-detection matched this summary and
     stopped before reaching the actual Section II. Result: ~25 modern
     files with 1000-3000 words and n_numbered_items = 10.

  2. Atlanta-style unbounded end. For a handful of files, none of the
     end-of-Risk-Factors signals matched (unusual section title, encoding
     quirk, etc.), and extraction walked to end-of-document. Atlanta:
     77,000 words extending to the "Signed by Directors" declaration page.

v2 fixes both with two changes:

  Change 1 — MULTI-CANDIDATE start detection. Instead of picking the first
             page with score >= 3, find all such candidate pages, extract
             with each, and pick the (start, end) whose extraction is
             LONGEST. Real Section II wins over a summary block decisively
             on word count. Doesn't hurt older prospectuses because they
             only have one candidate anyway.

  Change 2 — HARD CAP on extraction length. No real Indian prospectus has
             a Risk Factors section > 85 pages. If end-detection fails,
             cap at start + 90 pages. Safety net for files where none of
             the section-title patterns match.

Targeted scope
--------------
Only re-extracts files with characteristics of the two failure modes:
  - words < 15000 AND n_numbered_items <= 15  (probable summary match)
  - words > 60000                              (probable over-extension)

All other files remain untouched. The ~380 already-clean files from v1
stay exactly as they are.

Safety
------
Same guarantees as v1: existing .md files are backed up before overwrite,
new extraction must pass audit (coverage 0.60-1.50, bigram jaccard >= 0.50)
before overwriting, log is written incrementally so Ctrl+C leaves a valid
partial log.

Runtime: ~5-10 minutes (only touches ~25-30 files).

Usage
-----
  python3 src/processing/08_reextract_v2.py

Reads data/features/risk_section_summary.csv to identify problematic files.
Must be run AFTER 05_risk_section_eda.py has produced that summary CSV.
"""

from __future__ import annotations

import contextlib
import csv
import datetime as _dt
import os
import re
import shutil
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import pymupdf
import pymupdf4llm


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PDF_DIR = PROJECT_ROOT / "data" / "prospectus_pdfs"
MD_DIR = PROJECT_ROOT / "data" / "processed" / "risk_sections"
SUMMARY_CSV = PROJECT_ROOT / "data" / "features" / "risk_section_summary.csv"
BACKUP_DIR = (
    MD_DIR.parent
    / f".backup-risk_sections-v2-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
)
OUT_DIR = PROJECT_ROOT / "reports" / "tables" / "eda" / "08_reextract_v2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Selection criteria for which files to re-process
SHORT_WORDS_THRESHOLD = 15000
SHORT_ITEMS_THRESHOLD = 15
BLOATED_WORDS_THRESHOLD = 60000
# Hard cap on extraction length — safety net if end-detection fails
MAX_RISK_PAGES = 90


# ---------------------------------------------------------------------------
# Suppress pymupdf's chatty MuPDF messages during pymupdf4llm extraction
# ---------------------------------------------------------------------------
@contextlib.contextmanager
def suppress_stdout():
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


# ---------------------------------------------------------------------------
# Detection patterns  (validated against Polycab, Delhivery, Go Fashion,
# Inventurus, Anand Rathi, Aeroflex, Motisons in prior testing)
# ---------------------------------------------------------------------------

# Broad separator class — includes ± (U+00B1) as observed in Go Fashion
SEP = r"[:\-\u2010-\u2015\u2212\u00B1.\s]"

# --- Start anchors ---
STRONG_ANCHORS = [
    (
        "high_degree_of_risk",
        re.compile(
            r"invest\w+.{0,120}?high\s+degree\s+of\s+risk",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "internal_risk_factors_header",
        re.compile(
            r"^\s*INTERNAL\s+RISK\s+FACTORS\s*$",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "carefully_consider_risks_described",
        re.compile(
            r"(?:carefully|prospective)\s+.{0,80}?risks?\s+described\s+below",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
]

WEAK_ANCHORS = [
    (
        "lose_all_or_part_investment",
        re.compile(
            r"lose\s+all\s+or\s+part\s+of\s+(?:your|their)\s+investment",
            re.IGNORECASE,
        ),
    ),
    (
        "material_adverse_effect_business",
        re.compile(
            r"material\s+adverse\s+effect\s+on\s+(?:the|our)\s+business",
            re.IGNORECASE,
        ),
    ),
]

HEADER_WITH_SECTION = re.compile(
    rf"^\s*SECTION\s+[IVX]+{SEP}*RISK\s+FACTORS?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
HEADER_BARE = re.compile(
    r"^\s*RISK\s+FACTORS?\s*$", re.IGNORECASE | re.MULTILINE,
)


# --- End patterns  ---
# Order matters: strong signals first, generic fallbacks later.
# Every pattern requires a MANDATORY separator to avoid false positives
# like "Section V of" body-text.
END_PATTERNS = [
    (
        "section_introduction",
        re.compile(
            rf"^\s*SECTION\s+[IVX]+\s*{SEP}+\s*INTRODUCTION",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "section_the_offer",
        re.compile(
            rf"^\s*SECTION\s+[IVX]+\s*{SEP}+\s*THE\s+OFFER",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "section_about_or_business",
        re.compile(
            rf"^\s*SECTION\s+[IVX]+\s*{SEP}+\s*(?:ABOUT|BUSINESS)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "section_financial_information",
        re.compile(
            rf"^\s*SECTION\s+[IVX]+\s*{SEP}+\s*FINANCIAL",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "the_offer_bare",
        re.compile(
            r"^\s*THE\s+OFFER\s*$",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "summary_financial_information",
        re.compile(
            r"^\s*SUMMARY\s+FINANCIAL\s+INFORMATION\s*$",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "industry_overview_bare",
        re.compile(
            r"^\s*INDUSTRY\s+OVERVIEW\s*$",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    # Catch-all: any strict "SECTION [Roman] - [UPPERCASE_TITLE]" pattern.
    # Mandatory separator + 2+ uppercase letters keeps out body-text
    # references like "Section V of the Companies Act".
    (
        "strict_next_section",
        re.compile(
            rf"^\s*SECTION\s+[IVX]+\s*{SEP}+\s*[A-Z]{{2,}}",
            re.MULTILINE,
        ),
    ),
]


# ---------------------------------------------------------------------------
# Markdown stripping (for word-count comparison)
# ---------------------------------------------------------------------------
_MD_STRIP_PATTERNS = [
    re.compile(r"<!--.*?-->", flags=re.DOTALL),
    re.compile(r"</?u>"),
    re.compile(r"</?mark>"),
    re.compile(r"</?su[pb]>"),
    re.compile(r"\*+"),
    re.compile(r"_+"),
    re.compile(r"`+"),
    re.compile(r"^#+\s*", flags=re.MULTILINE),
    re.compile(r"\|"),
    re.compile(r"^-{3,}$", flags=re.MULTILINE),
]


def strip_markdown(text: str) -> str:
    for pat in _MD_STRIP_PATTERNS:
        text = pat.sub(" ", text)
    return text


def bigrams(text: str) -> set[tuple[str, str]]:
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    return set(zip(words, words[1:]))


# ---------------------------------------------------------------------------
# Bounds detection
# ---------------------------------------------------------------------------
def score_page(page_text: str) -> tuple[int, list[str]]:
    score = 0
    hits: list[str] = []
    for name, pat in STRONG_ANCHORS:
        if pat.search(page_text):
            score += 3
            hits.append(name)
    if HEADER_WITH_SECTION.search(page_text):
        score += 2
        hits.append("header_section_risk_factors")
    if HEADER_BARE.search(page_text):
        score += 2
        hits.append("header_bare_risk_factors")
    for name, pat in WEAK_ANCHORS:
        if pat.search(page_text):
            score += 1
            hits.append(name)
    return score, hits


def find_end_from(doc: pymupdf.Document, start: int) -> tuple[int, str]:
    """Find the end page starting from `start`. Returns (end_page, end_signal).
    Hard-capped at start + MAX_RISK_PAGES pages regardless of what patterns
    match, as a safety net for prospectuses where end-detection fails."""
    hard_cap = min(doc.page_count, start + MAX_RISK_PAGES)
    for i in range(start + 1, hard_cap):
        txt = doc.load_page(i).get_text("text") or ""
        for name, pat in END_PATTERNS:
            if pat.search(txt):
                return i, name
    return hard_cap, ("hard_cap" if hard_cap < doc.page_count else "eof_fallback")


def find_bounds(doc: pymupdf.Document) -> tuple[int | None, int, str, str]:
    """Multi-candidate bounds detection.

    Strategy: score every page. Find all pages with score >= 3 (candidate
    starts). For each candidate, compute (start, end) using find_end_from.
    Extract text length for each candidate range. Pick the candidate whose
    range contains the MOST TEXT — real Section II wins over SEBI summary
    blocks decisively on word count, while older prospectuses (with only
    one candidate) get the same result as v1.
    """
    # Score every page
    scored: dict[int, tuple[int, list[str]]] = {}
    for i in range(doc.page_count):
        txt = doc.load_page(i).get_text("text") or ""
        s, h = score_page(txt)
        if s >= 3:
            scored[i] = (s, h)

    if not scored:
        return None, 0, "", ""

    # For each candidate start, compute end and cumulative word count
    candidates = []
    for start in sorted(scored.keys()):
        end, end_signal = find_end_from(doc, start)
        # Compute cumulative word count in the range
        word_count = 0
        for i in range(start, end):
            word_count += len((doc.load_page(i).get_text("text") or "").split())
        candidates.append({
            "start": start,
            "end": end,
            "end_signal": end_signal,
            "words": word_count,
            "score": scored[start][0],
            "hits": scored[start][1],
        })

    # Pick the candidate with the most words.
    # This naturally handles the SEBI-2022 summary trap: a 5-page summary
    # block extracts ~2000 words, while the real Section II extracts 25-40k.
    best = max(candidates, key=lambda c: c["words"])

    return best["start"], best["end"], ",".join(best["hits"]), best["end_signal"]


# ---------------------------------------------------------------------------
# Extraction and audit
# ---------------------------------------------------------------------------
def audit_md_against_gt(md_text: str, gt_text: str) -> tuple[float, float]:
    """Return (coverage, jaccard). Empty inputs return (0, 0)."""
    md_words = len(strip_markdown(md_text).split())
    gt_words = len(gt_text.split())
    if gt_words == 0:
        return 0.0, 0.0
    coverage = md_words / gt_words

    md_open = strip_markdown(md_text[:12000])
    gt_open = gt_text[:12000]
    md_bg = bigrams(md_open)
    gt_bg = bigrams(gt_open)
    if md_bg and gt_bg:
        jaccard = len(md_bg & gt_bg) / len(md_bg | gt_bg)
    else:
        jaccard = 0.0
    return coverage, jaccard


COVERAGE_MIN = 0.60
COVERAGE_MAX = 1.50
JACCARD_MIN = 0.50


def certify(coverage: float, jaccard: float) -> tuple[bool, str]:
    """Return (passed, reason). passed=True means the new extraction is safe
    to write over the existing .md."""
    if jaccard < JACCARD_MIN:
        return False, f"jaccard {jaccard:.2f} < {JACCARD_MIN} (content mismatch)"
    if coverage < COVERAGE_MIN:
        return False, f"coverage {coverage:.2f} < {COVERAGE_MIN} (truncated)"
    if coverage > COVERAGE_MAX:
        return False, f"coverage {coverage:.2f} > {COVERAGE_MAX} (bloated)"
    return True, "certified_clean"


# ---------------------------------------------------------------------------
# Per-PDF processing
# ---------------------------------------------------------------------------
def process_pdf(pdf_path: Path) -> dict:
    """Extract + audit + write. Returns a log row."""
    stem = pdf_path.stem
    existing_md = MD_DIR / f"{stem}.md"

    row: dict = {
        "filename": pdf_path.name,
        "total_pages": 0,
        "new_start": "",
        "new_end": "",
        "new_pages": 0,
        "new_md_words": 0,
        "gt_words": 0,
        "coverage": "",
        "jaccard": "",
        "start_signals": "",
        "end_signal": "",
        "action": "",
        "reason": "",
    }

    # ---- Open PDF ----
    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception as exc:
        row["action"] = "PDF_OPEN_FAIL"
        row["reason"] = f"{type(exc).__name__}: {exc}"
        return row

    if doc.is_encrypted:
        if not doc.authenticate(""):
            doc.close()
            row["action"] = "PDF_ENCRYPTED"
            row["reason"] = "encrypted; empty-password rejected"
            return row

    row["total_pages"] = doc.page_count

    # ---- Detect image-only PDF (OCR case — keep existing .md) ----
    sample_chars = sum(
        len(doc.load_page(i).get_text("text") or "")
        for i in range(min(10, doc.page_count))
    )
    if sample_chars < 200:
        doc.close()
        row["action"] = "SKIPPED_OCR"
        row["reason"] = (
            f"image-only PDF ({sample_chars} chars in first 10 pages); "
            f"existing .md kept as-is (Tesseract-OCR authoritative)"
        )
        return row

    # ---- Find bounds ----
    start, end, start_hits, end_signal = find_bounds(doc)

    if start is None:
        doc.close()
        row["action"] = "NO_ANCHOR"
        row["reason"] = (
            "no strong Risk Factors anchor found in any page; existing "
            ".md kept as-is; needs manual review"
        )
        return row

    row["new_start"] = start
    row["new_end"] = end
    row["new_pages"] = end - start
    row["start_signals"] = start_hits
    row["end_signal"] = end_signal

    # ---- Ground-truth text (from same bounds, plain pymupdf) ----
    gt_parts = []
    for i in range(start, end):
        gt_parts.append(doc.load_page(i).get_text("text") or "")
    gt_text = "\n".join(gt_parts)
    row["gt_words"] = len(gt_text.split())

    doc.close()

    if row["gt_words"] == 0:
        row["action"] = "GT_EMPTY"
        row["reason"] = "ground-truth pages have no extractable text"
        return row

    # ---- Extract with pymupdf4llm ----
    try:
        with suppress_stdout():
            new_md = pymupdf4llm.to_markdown(
                str(pdf_path),
                pages=list(range(start, end)),
                show_progress=False,
            )
    except Exception as exc:
        new_md = ""
        # Fall through to fallback below

    row["new_md_words"] = len(strip_markdown(new_md).split())

    # ---- Audit the new extraction ----
    coverage, jaccard = audit_md_against_gt(new_md, gt_text)
    row["coverage"] = round(coverage, 3)
    row["jaccard"] = round(jaccard, 3)

    passed, reason = certify(coverage, jaccard)

    # ---- Fallback: if pymupdf4llm output failed audit, try plain-text ----
    # Some PDFs (e.g., Go Fashion) trigger a pymupdf4llm quirk where the
    # markdown converter mangles text (words squished together, table parsing
    # failures). In these cases the plain-text extraction is clean; we lose
    # markdown table structure but preserve the full text content, which is
    # much better than a mangled or a wrong-pages original.
    if not passed and jaccard < JACCARD_MIN:
        # Wrap the plain-text GT as a minimal markdown document
        fallback_md = (
            f"# RISK FACTORS (plain-text fallback — pymupdf4llm output "
            f"was mangled on this PDF)\n\n" + gt_text
        )
        fallback_cov, fallback_jac = audit_md_against_gt(fallback_md, gt_text)
        # Fallback trivially passes coverage/jaccard, so require this to be
        # substantive: at least the original ground-truth text with normal
        # length. Length sanity: > 5000 words.
        if len(gt_text.split()) > 5000:
            new_md = fallback_md
            row["new_md_words"] = len(strip_markdown(new_md).split())
            row["coverage"] = round(fallback_cov, 3)
            row["jaccard"] = round(fallback_jac, 3)
            passed = True
            reason = "plaintext_fallback_used"

    row["reason"] = reason

    if not passed:
        row["action"] = "KEPT_ORIGINAL"
        return row

    # ---- Backup existing, write new ----
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if existing_md.exists():
        shutil.copy2(existing_md, BACKUP_DIR / existing_md.name)
    existing_md.write_text(new_md, encoding="utf-8")
    row["action"] = "WROTE_NEW"
    return row


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _load_problem_files() -> list[str]:
    """Read risk_section_summary.csv and return filenames matching the two
    known failure patterns (SEBI summary trap, unbounded end)."""
    import csv as _csv
    if not SUMMARY_CSV.exists():
        raise FileNotFoundError(
            f"Cannot find {SUMMARY_CSV} — run 05_risk_section_eda.py first"
        )
    problem_stems: list[str] = []
    with open(SUMMARY_CSV, encoding="utf-8") as f:
        reader = _csv.DictReader(f)
        for row in reader:
            try:
                words = int(row["words"])
                items = int(row["n_numbered_items"])
            except (KeyError, ValueError):
                continue
            file_stem = row.get("file_stem", "").strip()
            if not file_stem:
                continue
            # Skip the OCR file — it's Tesseract output, don't touch
            if row.get("is_ocr", "").strip().lower() in {"true", "1"}:
                continue
            short = words < SHORT_WORDS_THRESHOLD and items <= SHORT_ITEMS_THRESHOLD
            bloated = words > BLOATED_WORDS_THRESHOLD
            if short or bloated:
                problem_stems.append(file_stem)
    return problem_stems


def main() -> int:
    if not PDF_DIR.exists():
        print(f"ERROR: PDF directory not found: {PDF_DIR}", file=sys.stderr)
        return 1

    try:
        problem_stems = _load_problem_files()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if not problem_stems:
        print("No problematic files found — everything looks fine!")
        return 0

    print(f"Found {len(problem_stems)} files matching problem patterns:")
    print(f"  - words < {SHORT_WORDS_THRESHOLD} AND items <= {SHORT_ITEMS_THRESHOLD}"
          f" (SEBI-2022 summary trap)")
    print(f"  - words > {BLOATED_WORDS_THRESHOLD} (unbounded end)")
    print()
    print(f"Existing .md files will be BACKED UP to {BACKUP_DIR}")
    print(f"                       before any overwrite. Nothing is lost.\n")

    log_csv = OUT_DIR / "certification_log_v2.csv"
    log_fields = [
        "filename", "total_pages", "new_start", "new_end", "new_pages",
        "new_md_words", "gt_words", "coverage", "jaccard",
        "start_signals", "end_signal", "action", "reason",
    ]

    started = time.time()
    rows: list[dict] = []
    with open(log_csv, "w", encoding="utf-8", newline="") as log_f:
        writer = csv.DictWriter(log_f, fieldnames=log_fields)
        writer.writeheader()
        log_f.flush()

        for idx, stem in enumerate(problem_stems, start=1):
            pdf_path = PDF_DIR / f"{stem}.pdf"
            if not pdf_path.exists():
                row = {k: "" for k in log_fields}
                row["filename"] = f"{stem}.pdf"
                row["action"] = "PDF_NOT_FOUND"
                row["reason"] = f"expected {pdf_path}"
                rows.append(row)
                writer.writerow(row)
                log_f.flush()
                continue

            row = process_pdf(pdf_path)
            rows.append(row)
            writer.writerow(row)
            log_f.flush()

            elapsed = time.time() - started
            print(
                f"  [{idx:3d}/{len(problem_stems)}] {stem[:45]:45s}  "
                f"{row['action']:18s}  cov={row['coverage'] or '-':>5}  "
                f"jac={row['jaccard'] or '-':>5}  "
                f"words={row['new_md_words'] or '-':>6}  "
                f"({elapsed:.0f}s elapsed)"
            )

    still_broken = [
        r for r in rows
        if r["action"] not in {"WROTE_NEW", "SKIPPED_OCR"}
    ]
    review_csv = OUT_DIR / "still_needs_manual_review.csv"
    with open(review_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=log_fields)
        writer.writeheader()
        writer.writerows(still_broken)

    from collections import Counter
    actions = Counter(r["action"] for r in rows)
    print()
    print("=" * 72)
    print("v2 SUMMARY — targeted re-extraction")
    print("=" * 72)
    for action, count in actions.most_common():
        print(f"  {action:20s} : {count:>4d}")
    print()
    print(f"  Certification log:  {log_csv}")
    print(f"  Still broken:       {review_csv}  ({len(still_broken)} files)")
    print(f"  Backups:            {BACKUP_DIR}")
    print()
    if still_broken:
        print(f"  {len(still_broken)} files still need eyes after v2:")
        for r in still_broken[:15]:
            print(
                f"    {r['filename'][:55]:55s} "
                f"{r['action']:18s} words={r['new_md_words'] or '-'}"
            )
    else:
        print("  All targeted files re-extracted cleanly. Corpus is done.")
    print()
    print("Re-run 05_risk_section_eda.py after this to regenerate the")
    print("summary CSV against the corrected corpus.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())