"""
STEP 07: Fetch the final 7 straggler prospectuses
==================================================
After step 06, 409 of 416 equity IPOs had valid prospectuses. This
script fetches the last 7, whose URLs were verified by hand because they
were edge cases the automatic matcher couldn't resolve:

  1-5: SEBI had TWO landing pages for the same RHP; the matcher picked the
       one whose PDF was a stub/amendment. These are the correct URLs:
         MSTC, SAMHI Hotels, Patel Retail, RailTel, Urban Company
  6:   Turtlemint - its RHP landing page listed the abridged PDF first;
       this is the full RHP link.
  7:   Exxaro Tiles - the PDF is AES-encrypted; it downloads fine and
       opens once `cryptography` is installed (empty password).

All 7 URLs below were verified to return real multi-hundred-page PDFs.

SETUP:
    pip install requests pypdf cryptography     # cryptography is REQUIRED
                                                # for the Exxaro (encrypted) PDF
RUN:
    python src/collection/07_fetch_final_7.py

OUTPUT:
    data/prospectus_pdfs/   (7 PDFs added)
"""

import requests
import os
import re
import time
import logging

logging.getLogger("pypdf").setLevel(logging.ERROR)
from pypdf import PdfReader

PDF_DIR = "data/prospectus_pdfs"
MIN_PDF_BYTES = 300_000
DOWNLOAD_TIMEOUT_S = 300
MAX_RETRIES = 6
HEADERS = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36")}

# company name  ->  (filename to save as, verified direct PDF URL)
# Filenames match step 06's safe_filename() output so nothing is duplicated.
FINAL_7 = {
    "MSTC Ltd.":
        "https://www.sebi.gov.in/sebi_data/attachdocs/mar-2019/1552043998036.pdf",
    "SAMHI Hotels Ltd.":
        "https://www.sebi.gov.in/sebi_data/attachdocs/sep-2023/1694002821599.pdf",
    "Patel Retail Ltd.":
        "https://www.sebi.gov.in/sebi_data/attachdocs/aug-2025/1754641439082.pdf",
    "RailTel Corp.of India Ltd.":
        "https://www.sebi.gov.in/sebi_data/attachdocs/feb-2021/1613387690368.pdf",
    "Urban Co.Ltd.":
        "https://www.sebi.gov.in/sebi_data/attachdocs/sep-2025/1757482211827.pdf",
    "Turtlemint Fintech Solutions Ltd.":
        "https://www.sebi.gov.in/sebi_data/attachdocs/jun-2026/1782360046043.pdf",
    "Exxaro Tiles Ltd.":
        "https://www.sebi.gov.in/sebi_data/attachdocs/jul-2021/1627629628713.pdf",
}


def safe_filename(company):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", company)[:80] + ".pdf"


def get_remote_size(url):
    try:
        r = requests.head(url, headers=HEADERS, timeout=60, allow_redirects=True)
        cl = r.headers.get("Content-Length")
        return int(cl) if cl and cl.isdigit() else None
    except Exception:
        return None


def download_resumable(url, dest_path):
    remote = get_remote_size(url)
    tmp = dest_path + ".part"
    for attempt in range(1, MAX_RETRIES + 1):
        have = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        if remote and have >= remote:
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
                    mode = "wb"; have = 0
                elif resp.status_code not in (200, 206):
                    if attempt < MAX_RETRIES:
                        time.sleep(3 * attempt); continue
                    return False, have, f"HTTP {resp.status_code}"
                with open(tmp, mode) as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait_s = 4 * attempt
                cur = os.path.getsize(tmp) if os.path.exists(tmp) else 0
                print(f"      drop {attempt} ({str(e)[:30]}); resume in {wait_s}s "
                      f"(have {cur}b)")
                time.sleep(wait_s); continue
            return False, have, f"connection failed"
    if not os.path.exists(tmp):
        return False, 0, "no data"
    final = os.path.getsize(tmp)
    if remote and final != remote:
        return False, final, f"size mismatch {final}/{remote}"
    if final < MIN_PDF_BYTES:
        return False, final, f"too small ({final})"
    os.replace(tmp, dest_path)
    return True, final, None


def validate(path):
    """Open (decrypt if needed), count pages, check for risk section."""
    try:
        r = PdfReader(path)
        if r.is_encrypted:
            r.decrypt("")  # empty password works for these SEBI PDFs
        pages = len(r.pages)
        head = ""
        for i in range(min(60, pages)):
            try:
                t = r.pages[i].extract_text()
                if t:
                    head += t + "\n"
            except Exception:
                pass
        return pages, ("risk factors" in head.lower())
    except Exception as e:
        return 0, False


def main():
    os.makedirs(PDF_DIR, exist_ok=True)
    print("=" * 60)
    print("STEP 07: Fetching the final 7 stragglers")
    print("=" * 60)

    ok = 0
    for company, url in FINAL_7.items():
        path = os.path.join(PDF_DIR, safe_filename(company))
        print(f"\n{company}")

        dok, size, derr = download_resumable(url, path)
        if not dok:
            print(f"   DOWNLOAD FAIL: {derr}")
            continue
        pages, has_risk = validate(path)
        if pages < 50:
            print(f"   INVALID: only {pages} pages")
            if os.path.exists(path):
                os.remove(path)
            continue
        ok += 1
        flag = "" if has_risk else "  [!] risk text not detected (encrypted/scanned - still valid)"
        print(f"   OK ({size/1024/1024:.1f}MB, {pages}p, risk={has_risk}){flag}")

    # Final tally of all PDFs on disk
    total = sum(1 for f in os.listdir(PDF_DIR)
                if f.endswith(".pdf") and
                os.path.getsize(os.path.join(PDF_DIR, f)) > MIN_PDF_BYTES)
    print(f"\n{'='*60}")
    print(f"  Fetched this run: {ok}/7")
    print(f"  TOTAL valid PDFs on disk: {total}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()