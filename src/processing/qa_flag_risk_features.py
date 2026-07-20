#!/usr/bin/env python3
"""
qa_flag_risk_features.py — surface extraction rows worth a manual eyeball before
modelling.  These are NOT errors; they are "look at these" flags.

    python src/processing/qa_flag_risk_features.py

INPUT   data/features/features_llm_risk.csv
OUTPUT  data/features/qa_flags_risk.csv   (one row per flagged file, sorted by
        number of flags; includes the model's extraction_reasoning so you can
        adjudicate each quickly against the row's own audit trace)

FLAGS
  identical_litig_contingent  total_litigation == contingent (both > 0). Sometimes
                              genuine (the firm's only contingent item IS its
                              litigation claim), sometimes field conflation on
                              sparse filings (e.g. Fujiyama). Eyeball each.
  nonstandard_unit            source unit is mixed / not_stated / thousand / crore
                              -> conversion-risk; confirm the /10 (or /100) is right.
  no_litigation_table         criminal+regulatory+tax all null -> the risk section
                              had no summary table (table often lives in a later
                              section). Confirm it is genuinely absent; treat as
                              MISSING, never zero.
  extreme_value               a count or amount at/above the 99th percentile of its
                              field. Usually a genuinely huge issuer (LIC, a PSU,
                              a big bank) but the place a unit error would hide.
  large_promoter_suspect      criminal or regulatory count > 100 -> almost always
                              driven by a giant promoter's litigation (e.g. ICICI
                              Bank, HDFC Bank), not the issuer's own. Correct per
                              schema, but flag so it is not misread as issuer risk.
  cases_without_amount        litigation counts > 0 but no quantified against-amount
                              -> often "not ascertainable" in the source; check the
                              amount is truly undisclosed rather than missed.
"""

from __future__ import annotations
import csv, os, sys

IN_CSV = "data/features/features_llm_risk.csv"
OUT_CSV = "data/features/qa_flags_risk.csv"


def fnum(v):
    v = (v or "").strip()
    if v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def p99(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    k = int(round(0.99 * (len(vals) - 1)))
    return vals[k]


def main() -> int:
    if not os.path.exists(IN_CSV):
        print(f"ERROR: missing {IN_CSV} (run from project root).", file=sys.stderr)
        return 1
    rows = list(csv.DictReader(open(IN_CSV, encoding="utf-8")))

    AMT = ["total_litigation_against_amount_cr", "contingent_liabilities_total_cr"]
    CNT = ["criminal_cases_against_count", "regulatory_actions_against_count",
           "tax_proceedings_against_count"]
    thr = {f: p99([fnum(r.get(f)) for r in rows]) for f in AMT + CNT}

    flagged = []
    for r in rows:
        crim = fnum(r.get("criminal_cases_against_count"))
        reg = fnum(r.get("regulatory_actions_against_count"))
        tax = fnum(r.get("tax_proceedings_against_count"))
        litig = fnum(r.get("total_litigation_against_amount_cr"))
        cont = fnum(r.get("contingent_liabilities_total_cr"))
        unit = r.get("source_currency_unit") or ""
        flags = []

        if litig is not None and cont is not None and litig > 0 and abs(litig - cont) < 1e-6:
            flags.append("identical_litig_contingent")
        if unit in ("mixed", "not_stated", "thousand", "crore"):
            flags.append("nonstandard_unit")
        if all(x is None for x in (crim, reg, tax)):
            flags.append("no_litigation_table")
        if any(fnum(r.get(f)) is not None and thr[f] is not None and fnum(r.get(f)) >= thr[f]
               for f in AMT + CNT):
            flags.append("extreme_value")
        if (crim is not None and crim > 100) or (reg is not None and reg > 100):
            flags.append("large_promoter_suspect")
        cases = sum(v for v in (crim, reg, tax) if v is not None)
        if cases > 0 and (litig is None or litig == 0):
            flags.append("cases_without_amount")

        if flags:
            reason = (r.get("extraction_reasoning") or "").replace("\n", " ")
            flagged.append({
                "stem": r["stem"],
                "n_flags": len(flags),
                "flags": "; ".join(flags),
                "unit": unit,
                "criminal": "" if crim is None else crim,
                "regulatory": "" if reg is None else reg,
                "tax": "" if tax is None else tax,
                "litigation_cr": "" if litig is None else litig,
                "contingent_cr": "" if cont is None else cont,
                "reasoning": reason[:400],
            })

    flagged.sort(key=lambda x: -x["n_flags"])
    cols = ["stem", "n_flags", "flags", "unit", "criminal", "regulatory", "tax",
            "litigation_cr", "contingent_cr", "reasoning"]
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(flagged)

    from collections import Counter
    c = Counter(f for r in flagged for f in r["flags"].split("; "))
    print(f"Wrote {OUT_CSV}: {len(flagged)} of {len(rows)} files flagged for review\n")
    print("Flag frequency:")
    for k, v in c.most_common():
        print(f"  {k:28} {v:4}")
    multi = [r for r in flagged if r["n_flags"] >= 2]
    print(f"\nFiles with 2+ flags (highest priority): {len(multi)}")
    for r in multi[:15]:
        print(f"  [{r['n_flags']}] {r['stem']:42} {r['flags']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())