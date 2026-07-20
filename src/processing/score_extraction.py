#!/usr/bin/env python3
"""
score_extraction.py — score a trial extraction CSV against the adjudicated gold.

Usage:
    python src/processing/score_extraction.py --csv data/features/_trial_llm_risk.csv

Prints, per model, a PASS/FAIL for each scored field on each of the 5 trial files,
plus per-model and per-field accuracy. This is the seed of the SQ3 faithfulness
evaluation — later, replace GOLD with a hand-labelled gold CSV over ~20-30 files.

GOLD below is the corrected reference after adjudicating the first trial against the
source documents. NOTE: the tax_proceedings_against_count values are newly derived
(v3 field) and are my best manual counts; if both models agree with each other but
differ from these, re-check the source — the model may be right.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict

# field -> comparison kind
KIND = {
    "criminal_cases_against_count": "int",
    "regulatory_actions_against_count": "int",
    "tax_proceedings_against_count": "int",
    "total_litigation_against_amount_cr": "amount",
    "contingent_liabilities_total_cr": "amount",
    "going_concern_status": "enum",
    "auditor_report_status": "enum",
    "top5_customer_revenue_pct": "pct",
    "top10_customer_revenue_pct": "pct",
}
FIELDS = list(KIND.keys())

GOLD = {
    "Advance_Agrolife_Ltd_": {
        "criminal_cases_against_count": 10, "regulatory_actions_against_count": 0,
        "tax_proceedings_against_count": 4, "total_litigation_against_amount_cr": 0.333,
        "contingent_liabilities_total_cr": 0.297,
        "going_concern_status": "not_mentioned",
        "auditor_report_status": "caro_or_emphasis_of_matter_only",
        "top5_customer_revenue_pct": 51.70, "top10_customer_revenue_pct": 69.47,
    },
    "Capillary_Technologies_India_Ltd_": {
        "criminal_cases_against_count": 4, "regulatory_actions_against_count": 2,
        "tax_proceedings_against_count": 11, "total_litigation_against_amount_cr": 36.624,
        "contingent_liabilities_total_cr": 0.391,
        "going_concern_status": "not_mentioned",
        "auditor_report_status": "caro_or_emphasis_of_matter_only",
        "top5_customer_revenue_pct": 43.35, "top10_customer_revenue_pct": 58.71,
    },
    "Yatharth_Hospital___Trauma_Care_Services_Ltd_": {
        "criminal_cases_against_count": 6, "regulatory_actions_against_count": 0,
        "tax_proceedings_against_count": 0, "total_litigation_against_amount_cr": 0.574,
        "contingent_liabilities_total_cr": 235.844,
        "going_concern_status": "group_or_subsidiary_only",
        "auditor_report_status": "not_mentioned",
        "top5_customer_revenue_pct": None, "top10_customer_revenue_pct": None,
    },
    "Akums_Drugs___Pharmaceuticals_Ltd_": {
        "criminal_cases_against_count": 2, "regulatory_actions_against_count": 113,
        "tax_proceedings_against_count": 47, "total_litigation_against_amount_cr": 102.493,
        "contingent_liabilities_total_cr": 88.622,
        "going_concern_status": "not_mentioned",
        "auditor_report_status": "not_mentioned",
        "top5_customer_revenue_pct": None, "top10_customer_revenue_pct": None,
    },
    "G_R_Infraprojects_Ltd_": {
        "criminal_cases_against_count": 5, "regulatory_actions_against_count": 3,
        "tax_proceedings_against_count": 19, "total_litigation_against_amount_cr": 36.979,
        "contingent_liabilities_total_cr": 1013.399,
        "going_concern_status": "not_mentioned",
        "auditor_report_status": "caro_or_emphasis_of_matter_only",
        "top5_customer_revenue_pct": 97.83, "top10_customer_revenue_pct": None,
    },
}


def match(kind, gold, got_raw) -> bool:
    got_raw = (got_raw or "").strip()
    if gold is None:
        return got_raw == ""            # gold null -> must be blank (no over-extraction)
    if got_raw == "":
        return False                    # gold has a value -> blank is a miss
    try:
        if kind == "int":
            return int(float(got_raw)) == int(gold)
        if kind == "amount":
            g = float(got_raw)
            return abs(g - gold) <= max(0.01, 0.01 * abs(gold))   # 1% or 0.01
        if kind == "pct":
            return abs(float(got_raw) - gold) <= 0.5
        if kind == "enum":
            return got_raw.lower() == str(gold).lower()
    except ValueError:
        return False
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--model", default=None, help="score only this model_requested")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.csv, encoding="utf-8")))
    by = defaultdict(dict)
    for r in rows:
        by[r["model_requested"]][r["stem"]] = r

    models = [args.model] if args.model else sorted(by)
    field_hits = defaultdict(lambda: [0, 0])   # field -> [correct, total] across models

    for model in models:
        print("=" * 78)
        print(f"MODEL: {model}")
        print("=" * 78)
        hdr = f"{'file':40}" + "".join(f"{f.split('_')[0][:5]:>6}" for f in FIELDS)
        print(hdr)
        mcorrect = mtotal = 0
        for stem, gold in GOLD.items():
            row = by.get(model, {}).get(stem)
            if not row:
                print(f"{stem[:40]:40}  (no row in CSV)")
                continue
            marks = ""
            for f in FIELDS:
                ok = match(KIND[f], gold[f], row.get(f))
                marks += f"{'  ok ' if ok else '  XX '}"
                mcorrect += ok; mtotal += 1
                field_hits[f][0] += ok; field_hits[f][1] += 1
            print(f"{stem[:40]:40}{marks}")
        print(f"\n  {model} accuracy: {mcorrect}/{mtotal} "
              f"({100*mcorrect/mtotal:.0f}%)\n")

    print("=" * 78)
    print("PER-FIELD accuracy (across all scored models) — lowest = least reliable")
    print("=" * 78)
    for f in sorted(FIELDS, key=lambda x: field_hits[x][0] / max(1, field_hits[x][1])):
        c, t = field_hits[f]
        print(f"  {f:40} {c}/{t}  ({100*c/max(1,t):.0f}%)")

    print("\nMismatches to inspect (field: gold vs got):")
    for model in models:
        for stem, gold in GOLD.items():
            row = by.get(model, {}).get(stem)
            if not row:
                continue
            for f in FIELDS:
                if not match(KIND[f], gold[f], row.get(f)):
                    print(f"  [{model}] {stem[:30]:30} {f}: "
                          f"gold={gold[f]}  got={row.get(f) or '(blank)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())