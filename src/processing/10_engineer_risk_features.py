#!/usr/bin/env python3
"""
10_engineer_risk_features.py — turn raw LLM risk extractions into a modelling-ready
feature matrix.  Phase 7 -> Phase 8 bridge.

    python src/processing/10_engineer_risk_features.py

INPUTS  (paths relative to project root)
  data/features/features_llm_risk.csv   — the 416 raw extractions (Phase 7 output)
  data/features/features_numeric.csv    — numeric baseline; used ONLY for the size
                                          variable `assets_log1p` and the join key.

OUTPUT
  data/features/features_risk_engineered.csv  — 416 rows, keyed by stem + company,
                                          ready to join to the numeric baseline.

================================================================================
TARGET-BLIND GUARANTEE (this is the SQ1 guardrail — read before editing)
================================================================================
This script NEVER reads `first_day_return` or any outcome. Whether the risk block
predicts the target is the thesis question; if we tuned or selected features against
the target here, we would bias that test. Every transform below is justified only by
economic mechanism, coverage, variance, or redundancy — never by correlation with
the outcome. From features_numeric.csv we deliberately load ONLY two columns:
`company` (join key) and `assets_log1p` (a size covariate). Nothing else.

WHAT EACH TRANSFORM DOES AND WHY
  counts (criminal / regulatory / tax)
      - log1p(count): counts are heavily right-skewed (median ~2, max ~476).
      - *_missing flag: null = "no litigation table in the risk section" (~4-7%),
        which is NOT zero. We keep the flag and leave the value blank; DO NOT
        zero-fill blindly at modelling — impute with the flag present.
      - CAVEAT (documented, not fixed): criminal & regulatory counts INCLUDE
        promoter/director matters, so issuers with giant promoters (e.g. ICICI
        Bank, HDFC Bank, Airtel) show counts driven by the promoter's litigation,
        not their own. tax_count is company+subsidiaries only, so it is the
        cleanest of the three. Interpret criminal/regulatory with this in mind.

  amounts (total_litigation / contingent, in Rs crore)
      - log1p(amount): 5-6 orders of magnitude of skew.
      - *_size_adj = log1p(amount_cr) - assets_log1p: an (approximate) size-
        normalised "risk intensity" so the feature measures exposure RELATIVE to
        firm size rather than just firm size. (A constant unit offset is absorbed
        as a global shift and does not affect ranking/variance.)
      - REDUNDANCY: total_litigation and contingent correlate r~0.95 (both scale
        with size; Indian "contingent liabilities" typically INCLUDE litigation
        claims). They are ~one signal. Keep ONE at modelling, or let a regulariser
        handle it; do not read their two SHAP values as independent.

  concentration (customer)
      - top5 and top10 correlate r~0.98 -> we keep ONLY top10 (marginally better
        coverage) as `customer_concentration_top10_pct`. top5 is dropped here.
      - It is a %, so no scaling. ~61% null (many issuers do not disclose company-
        wide concentration) -> missing flag; sparse, expect limited power.

  going_concern_status (90% "not_mentioned" -> near-constant)
      - collapsed to two flags rather than a mostly-constant category:
        going_concern_uncertainty_flag = 1 if issuer OR group/subsidiary doubt.
        going_concern_issuer_flag      = 1 only if the ISSUER's own doubt (rarest,
                                         strongest signal).

  auditor_report_status (effectively binary + 3% severe)
      - encoded as ordinal severity 0/1/2 (clean/absent < CARO/emphasis < modified
        opinion) plus a binary auditor_modified_flag for the severe tier.

  DROPPED from the modelling matrix (kept in the raw CSV for audit only):
      extraction_reasoning, source_currency_unit, and all run metadata
      (model, tokens, cost, timestamp, status). issuer_name is kept for reference.
"""

from __future__ import annotations
import csv, math, os, re, sys

LLM_CSV = "data/features/features_llm_risk.csv"
NUM_CSV = "data/features/features_numeric.csv"
OUT_CSV = "data/features/features_risk_engineered.csv"


def norm_key(s: str) -> str:
    """Canonical company key: lowercase, strip punctuation and corporate suffixes.
    Verified to align all 416 stems <-> company names with no collisions."""
    s = s.lower()
    s = re.sub(r"[^a-z0-9]", " ", s)
    s = re.sub(r"\b(ltd|limited|pvt|private|the|and)\b", " ", s)
    return re.sub(r"\s+", "", s)


def fnum(v):
    v = (v or "").strip()
    if v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def log1p(x):
    return None if x is None else math.log1p(x)


def main() -> int:
    for p in (LLM_CSV, NUM_CSV):
        if not os.path.exists(p):
            print(f"ERROR: missing {p} (run from project root).", file=sys.stderr)
            return 1

    llm = list(csv.DictReader(open(LLM_CSV, encoding="utf-8")))

    # --- load ONLY company + assets_log1p from the numeric file (target-blind) ---
    assets = {}
    with open(NUM_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            assets[norm_key(r["company"])] = fnum(r.get("assets_log1p"))
    # (first_day_return is intentionally never touched.)

    out_rows = []
    n_size_adj = 0
    for r in llm:
        k = norm_key(r["stem"])
        a_log = assets.get(k)  # size covariate, may be None (4 issuers)

        crim = fnum(r.get("criminal_cases_against_count"))
        reg = fnum(r.get("regulatory_actions_against_count"))
        tax = fnum(r.get("tax_proceedings_against_count"))
        litig = fnum(r.get("total_litigation_against_amount_cr"))
        cont = fnum(r.get("contingent_liabilities_total_cr"))
        t10 = fnum(r.get("top10_customer_revenue_pct"))

        def size_adj(amt):
            nonlocal n_size_adj
            if amt is None or a_log is None:
                return None
            n_size_adj += 1
            return log1p(amt) - a_log

        gc = r.get("going_concern_status") or ""
        gc_unc = 1 if gc in ("issuer_material_uncertainty",
                             "group_or_subsidiary_only") else 0
        gc_iss = 1 if gc == "issuer_material_uncertainty" else 0

        aud = r.get("auditor_report_status") or ""
        aud_sev = {"qualified_adverse_or_disclaimer": 2,
                   "caro_or_emphasis_of_matter_only": 1,
                   "unmodified_clean": 0,
                   "not_mentioned": 0}.get(aud, 0)
        aud_mod = 1 if aud == "qualified_adverse_or_disclaimer" else 0

        def blank(x):
            return "" if x is None else x

        out_rows.append({
            "stem": r["stem"],
            "issuer_name_as_stated": r.get("issuer_name_as_stated", ""),
            # counts
            "criminal_count": blank(crim),
            "criminal_log1p": blank(log1p(crim)),
            "criminal_missing": int(crim is None),
            "regulatory_count": blank(reg),
            "regulatory_log1p": blank(log1p(reg)),
            "regulatory_missing": int(reg is None),
            "tax_count": blank(tax),
            "tax_log1p": blank(log1p(tax)),
            "tax_missing": int(tax is None),
            # amounts
            "litigation_amount_cr": blank(litig),
            "litigation_amount_log1p": blank(log1p(litig)),
            "litigation_amount_size_adj": blank(size_adj(litig)),
            "litigation_amount_missing": int(litig is None),
            "contingent_cr": blank(cont),
            "contingent_log1p": blank(log1p(cont)),
            "contingent_size_adj": blank(size_adj(cont)),
            "contingent_missing": int(cont is None),
            # concentration (top10 kept; top5 dropped for collinearity)
            "customer_concentration_top10_pct": blank(t10),
            "concentration_missing": int(t10 is None),
            # collapsed enums
            "going_concern_uncertainty_flag": gc_unc,
            "going_concern_issuer_flag": gc_iss,
            "auditor_severity": aud_sev,
            "auditor_modified_flag": aud_mod,
        })

    cols = list(out_rows[0].keys())
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)

    # --- summary ---
    n = len(out_rows)
    print(f"Wrote {OUT_CSV}: {n} rows x {len(cols)} columns\n")
    print("Missingness in engineered features:")
    for f in ["criminal_missing", "regulatory_missing", "tax_missing",
              "litigation_amount_missing", "contingent_missing",
              "concentration_missing"]:
        m = sum(int(r[f]) for r in out_rows)
        print(f"  {f:28} {m:4} ({100*m/n:.0f}%)")
    print("\nCollapsed-flag positives:")
    for f in ["going_concern_uncertainty_flag", "going_concern_issuer_flag",
              "auditor_modified_flag"]:
        m = sum(int(r[f]) for r in out_rows)
        print(f"  {f:34} {m:4} ({100*m/n:.0f}%)")
    miss_assets = sum(1 for r in llm if assets.get(norm_key(r["stem"])) is None)
    print(f"\nIssuers with no assets_log1p (size_adj blank for them): {miss_assets}")
    print("\nREMINDER: *_missing=1 means NOT DISCLOSED, not zero. Impute with the")
    print("flag present; keep only ONE of {litigation_amount, contingent} (r~0.95)")
    print("and interpret criminal/regulatory counts with the promoter caveat.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())