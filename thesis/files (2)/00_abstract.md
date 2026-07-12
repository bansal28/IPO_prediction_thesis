# Abstract

> **NOTE TO SELF (Hritik):** This is a *placeholder* abstract, written from the
> project plan before modelling is complete. The final abstract must be written
> **last**, after results exist, and must state actual numerical findings
> (e.g. "the augmented model reduced MAE by X% relative to the baseline;
> Clark-West test rejected the null of equal predictive accuracy at
> p = ...").
> Do not submit this version.

Initial public offerings (IPOs) in India have grown to over one hundred main-board
listings per calendar year, yet first-day price behaviour remains difficult to
predict from public pre-listing information. Prior work using large language
models on offer documents (e.g. Ghosh, Zheng, and Lopez-Lira, 2024) has treated
the prospectus as an opaque text through retrieval-augmented embeddings, losing
the interpretable, auditable structure that a financial regulator or an investor
committee would want to inspect.

This dissertation asks whether **schema-guided structured extraction** of risk
factors from Indian IPO prospectuses — where a large language model is
constrained to populate a fixed set of typed fields via a Pydantic schema —
yields statistically significant incremental predictive power for first-day
return over and above a strong baseline of numeric pre-listing features
(subscription, grey-market premium, broker sentiment, financials, and market
context). The evaluation is strictly time-based: training data ends in 2023,
validation is 2024, and testing is 2025–2026.

A dataset of 419 mainboard IPOs listed between February 2019 and July 2026 was
assembled from Chittorgarh IPO detail pages, SEBI DRHP/RHP filings
(416 verified prospectus PDFs), InvestorGain grey-market data, Yahoo Finance
market context, and Ghosh et al.'s public dataset for cross-validation. A
strictly leakage-controlled cleaned master file was produced, and exploratory
analysis identified a statistically significant regime shift between 2024 and
2025 in which the median first-day return fell from approximately 21 percent to
approximately 5 percent.

[TODO: HRITIK — one paragraph on methods, one on findings, one on
contribution — write **after** modelling is complete.]

**Keywords:** Indian IPO, first-day return, prospectus, large language model,
structured extraction, incremental predictive value, Clark-West test,
interpretability, SHAP.
