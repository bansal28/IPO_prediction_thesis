"""
03_llm_extraction.py
=====================
Reads prospectus PDFs, extracts the Risk Factors section,
and uses an LLM to extract ~12 structured risk fields per IPO.

Extraction schema:
  - going_concern_flag (bool)
  - customer_concentration_pct (float)
  - pending_litigation_count (int)
  - promoter_pledge_pct (float)
  - related_party_transactions_flag (bool)
  - negative_cash_flow_years (int)
  - contingent_liabilities_to_networth (float)
  - regulatory_action_flag (bool)
  - supplier_concentration_flag (bool)
  - promoter_criminal_proceedings_flag (bool)
  - number_of_risk_factors (int)
  - ofs_dominant_flag (bool)

Input:  data/prospectus_pdfs/*.pdf
Output: data/features/features_llm_risk.csv
"""

# TODO: implement
