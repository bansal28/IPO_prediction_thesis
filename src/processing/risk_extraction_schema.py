"""
risk_extraction_schema.py — Phase 7 schema (v3, revised after the 5-file GPT trial).

Each field description is BOTH the model instruction and the human labelling rule.

WHAT CHANGED FROM v2 (all driven by the 5-file trial on gpt-5.6 luna/terra)
---------------------------------------------------------------------------
FIX  regulatory_actions_against_count : now EXCLUDES tax proceedings. In v2 the
     models disagreed wildly (Advance 0 vs 7, Akums 162 vs 113, GRInfra 22 vs 3)
     purely because "regulatory" was ambiguous about tax. Tax now has its own
     field, so this counts statutory/regulatory ENFORCEMENT only.
ADD  tax_proceedings_against_count : gives tax a home (fixes the ambiguity above)
     and adds a real signal — the number of tax disputes against the group.
FIX  auditor_report_status : the severe category now requires EXPLICIT opinion-
     modification wording. In v2 both models tagged GRInfra "qualified" off the
     vague phrase "qualifications and observations on certain matters"; base rates
     and wording favor the milder CARO/emphasis reading.
FIX  concentration : COMPANY-WIDE only. Akums disclosed 39.31% for its CDMO
     SEGMENT, which is not comparable to a company-wide figure -> segment-level
     now maps to None. Denominator may be "revenue from operations" or "total
     income" (GRInfra used total income); note which in extraction_reasoning.
CUT  top5_supplier_purchase_pct : usable in only 1 of 5 trial files (elsewhere
     blank, segment-split, or vendor-%-of-expenses rather than supplier-%-of-
     purchases). Too sparse/incomparable to be a clean feature.

TOKEN CONVENTIONS (unchanged; apply everywhere)
-----------------------------------------------
  Count cell "Nil" / "-" / "N.A." / "Not applicable"    -> 0 for that cell.
  Amount cell "Nil"                                      -> 0.0 for that cell.
  Amount "Not ascertainable" / "Not quantifiable"        -> exclude from aggregate.
  Amount "5.00 + 9% interest"                           -> take numeric 5.00.
  Table absent from the risk section                    -> field is None.
  Explicit "Total" row present                          -> USE IT; don't re-sum.

None vs 0.0
-----------
  None  -> not disclosed / "not ascertainable" / absent.
  0.0/0 -> explicitly "Nil" / zero.

OPENAI STRICT-MODE NOTES (do not "fix" these)
---------------------------------------------
  * No Field(ge/le): bounds live in validators.
  * extra="forbid" -> additionalProperties:false.
  * use_attribute_docstrings=True lifts these docstrings into the JSON schema.
  * Pass this model to client.responses.parse(text_format=RiskExtraction).
  * Field ORDER is generation order -> reasoning/units first, then numbers.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class RiskExtraction(BaseModel):
    """Structured risk-factor extraction for one Indian IPO prospectus risk section."""

    # NOTE: do NOT set extra="forbid". It makes Pydantic emit
    # additionalProperties:false, which OpenAI strict mode requires but Gemini's
    # response_schema REJECTS (400 "Unknown name additional_properties"). The
    # OpenAI SDK re-adds additionalProperties:false itself during strict conversion,
    # so leaving it off here satisfies both providers.
    model_config = ConfigDict(use_attribute_docstrings=True)

    # ---- QA / reasoning (first) --------------------------------------------
    issuer_name_as_stated: str
    """Issuer company name exactly as written in this risk section. If the text only
    refers to "our Company", resolve it to the actual registered name stated
    elsewhere in the section; do not return "our Company"."""

    extraction_reasoning: str
    """3-6 sentences written BEFORE the numeric fields. State: (a) the litigation
    table's against-vs-by split and which rows you counted, keeping criminal,
    regulatory and tax separate; (b) the source of the contingent-liabilities figure
    (stated Total vs summed) and its date; (c) the fiscal period AND the denominator
    (revenue from operations vs total income) of any concentration %, and whether it
    is company-wide or only a business segment; (d) the source unit and conversion.
    Audit trace, not a feature."""

    source_currency_unit: Literal[
        "crore", "million", "lakh", "thousand", "mixed", "not_stated"
    ]
    """Unit the SOURCE uses for its litigation / contingent-liability monetary tables.
    All *_cr fields must be converted to CRORE (1 crore = 10 million = 100 lakh).
    'mixed' if different tables use different units -> flagged for manual review."""

    # ---- Litigation (directional) ------------------------------------------
    criminal_cases_against_count: Optional[int]
    """Number of criminal proceedings in which the company, its subsidiaries,
    promoters, directors, KMP or SMP are the ACCUSED/respondent (the 'Against ...'
    rows, summed across ALL those entities — do not stop at the company row).
    EXCLUDE every 'By ...' row (cases they filed, e.g. s.138 cheque-bounce recovery).
    None if the risk section has no litigation summary table; 0 if none against."""

    regulatory_actions_against_count: Optional[int]
    """Number of statutory/regulatory ENFORCEMENT proceedings (SEBI, RBI, ROC, and
    other regulators; the 'statutory/regulatory' column) AGAINST the company,
    subsidiaries, promoters or directors — the 'Against ...' rows, summed. EXCLUDE
    tax proceedings (they go in tax_proceedings_against_count) and exclude 'By ...'
    rows. None if no table; 0 if none."""

    tax_proceedings_against_count: Optional[int]
    """Number of direct + indirect TAX proceedings against the COMPANY and its
    SUBSIDIARIES (the tax column, 'Against ...'/'involving' rows for the company and
    subsidiaries; if tax is broken into income tax / GST / VAT / customs / excise
    sub-rows, sum those sub-rows). Exclude tax matters of promoters/directors in a
    personal capacity, and exclude 'By ...' rows. None if no table; 0 if none."""

    total_litigation_against_amount_cr: Optional[float]
    """Aggregate quantified amount (Rs CRORE) of outstanding matters AGAINST the
    COMPANY and its SUBSIDIARIES only (consolidated group), INCLUDING tax proceedings
    against the company. EXCLUDE promoter/director personal matters and all 'By ...'
    rows. Prefer an explicitly stated aggregate/total; else sum the quantified
    'Against company' + 'Against subsidiaries' amounts, skipping 'Not ascertainable'
    cells. None if nothing against the group is quantified; 0.0 only if explicitly nil.
    (This is the least-stable numeric field when many sub-rows must be summed — the
    reasoning trace should list the components so the sum can be audited.)"""

    # ---- Financial health --------------------------------------------------
    contingent_liabilities_total_cr: Optional[float]
    """Total contingent liabilities NOT provided for (Rs CRORE), as of the latest
    balance-sheet date shown in the risk section (an interim/stub date is acceptable
    if it is the latest shown). CONSOLIDATED figure if both are given. Use the stated
    'Total' row when present; do not re-sum line items. None if not disclosed; 0.0
    if explicitly nil."""

    going_concern_status: Literal[
        "issuer_material_uncertainty",
        "group_or_subsidiary_only",
        "no_uncertainty_stated",
        "not_mentioned",
    ]
    """Polarity + subject. 'issuer_material_uncertainty' ONLY if the auditor flags
    material uncertainty about the ISSUER's own ability to continue.
    'group_or_subsidiary_only' if the doubt attaches to a subsidiary/acquired/group
    entity, not the issuer. 'no_uncertainty_stated' if going concern is discussed but
    with no material uncertainty. 'not_mentioned' if the phrase is absent. The bare
    phrase 'going concern basis' in a normal clean opinion is NOT uncertainty."""

    auditor_report_status: Literal[
        "qualified_adverse_or_disclaimer",
        "caro_or_emphasis_of_matter_only",
        "unmodified_clean",
        "not_mentioned",
    ]
    """Status of the STATUTORY AUDITOR'S REPORT on the financial statements only (NOT
    staff, bidding, or equipment 'qualifications'). Choose 'qualified_adverse_or_
    disclaimer' ONLY when the text EXPLICITLY indicates a modified OPINION — wording
    such as 'qualified opinion', 'adverse opinion', 'disclaimer of opinion', or
    'the opinion is modified'. Vague wording like 'the auditors included certain
    qualifications and observations on certain matters', CARO-report remarks,
    'qualifications on other legal and regulatory reporting requirements', or an
    emphasis-of-matter paragraph -> 'caro_or_emphasis_of_matter_only' (these are NOT
    opinion qualifications). 'unmodified_clean' only if explicitly stated. Otherwise
    'not_mentioned'."""

    # ---- Concentration (company-wide only; numbers not flags) --------------
    top5_customer_revenue_pct: Optional[float]
    """COMPANY-WIDE revenue from the top 5 customers/clients as a % of revenue from
    operations (or of total income — note which in the reasoning), for the most
    recent FULL fiscal year shown (prefer a full year over an interim/stub period).
    0-100. None if only a BUSINESS-SEGMENT figure is given (e.g. 'top clients of our
    X business'), if discussed without a number, or if absent."""

    top10_customer_revenue_pct: Optional[float]
    """As above, company-wide top 10 customers, most recent full fiscal. 0-100. Must
    be >= top5_customer_revenue_pct when both present. None if only segment-level or
    not disclosed."""

    # ---- Validators (bounds here, NOT in Field) ----------------------------
    @field_validator(
        "total_litigation_against_amount_cr", "contingent_liabilities_total_cr"
    )
    @classmethod
    def _amounts_non_negative(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError("monetary amount cannot be negative")
        return v

    @field_validator(
        "criminal_cases_against_count",
        "regulatory_actions_against_count",
        "tax_proceedings_against_count",
    )
    @classmethod
    def _counts_non_negative(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("count cannot be negative")
        return v

    @field_validator("top5_customer_revenue_pct", "top10_customer_revenue_pct")
    @classmethod
    def _pct_in_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 100.0):
            raise ValueError("percentage must be between 0 and 100")
        return v

    @model_validator(mode="after")
    def _cross_field(self) -> "RiskExtraction":
        t5, t10 = self.top5_customer_revenue_pct, self.top10_customer_revenue_pct
        if t5 is not None and t10 is not None and t5 > t10 + 1e-6:
            raise ValueError("top5 customer % cannot exceed top10 customer %")
        return self


if __name__ == "__main__":
    from pydantic import ValidationError

    # Corrected reference: Advance Agrolife (2025), after trial adjudication.
    ok = RiskExtraction(
        issuer_name_as_stated="Advance Agrolife Limited",
        extraction_reasoning=(
            "Criminal against = company 5 + promoters 1 + KMP/SMP 4 = 10; the 60 "
            "'by company' s.138 suits excluded. Regulatory (enforcement) against = 0 "
            "(all '-'); tax proceedings against company = 4. Quantified against-amount "
            "= company tax 3.33m = 0.333 cr. Contingent liabilities stated total "
            "2.97m for Fiscal 2025 = 0.297 cr. Customer concentration Fiscal 2025 "
            "(company-wide, % of revenue from operations): top5 51.70, top10 69.47. "
            "Unit million; /10 to crore."
        ),
        source_currency_unit="million",
        criminal_cases_against_count=10,
        regulatory_actions_against_count=0,
        tax_proceedings_against_count=4,
        total_litigation_against_amount_cr=0.333,
        contingent_liabilities_total_cr=0.297,
        going_concern_status="not_mentioned",
        auditor_report_status="caro_or_emphasis_of_matter_only",
        top5_customer_revenue_pct=51.70,
        top10_customer_revenue_pct=69.47,
    )
    print("[OK] corrected Advance reference constructed")
    for bad, label in [
        ({"contingent_liabilities_total_cr": -1.0}, "negative amount"),
        ({"tax_proceedings_against_count": -3}, "negative count"),
        ({"top10_customer_revenue_pct": 130.0}, "pct > 100"),
        ({"top5_customer_revenue_pct": 80.0, "top10_customer_revenue_pct": 60.0},
         "top5 > top10"),
    ]:
        d = ok.model_dump(); d.update(bad)
        try:
            RiskExtraction(**d)
        except ValidationError:
            print(f"[OK] rejected: {label}")
        else:
            raise SystemExit(f"[FAIL] not rejected: {label}")
    print(f"\n[OK] field count = {len(RiskExtraction.model_fields)}")
    miss = [k for k, v in RiskExtraction.model_json_schema()["properties"].items()
            if "description" not in v]
    print("fields missing description:", miss if miss else "NONE")