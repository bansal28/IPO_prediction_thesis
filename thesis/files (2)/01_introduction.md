# 1. Introduction

## 1.1 Motivation

[TODO: HRITIK — personal motivation paragraph (~200 words). Why *you* chose
this topic. This chapter reads better if it opens with a real "why now, why
this?" hook rather than another IPO-market summary. Suggested prompts:
what first got you interested in the Indian IPO market; whether a specific
IPO or news event shaped the direction; what you hope a reader in industry
or in regulation would take away.]

Initial public offerings represent one of the most heavily-scrutinised events in
public equity markets. In India, the number of mainboard IPO listings roughly
doubled over the past two years, from 60 IPOs in calendar year 2023 to 108 in
calendar year 2025 [see Chapter 5 for the exact counts in this dataset], and the
market has attracted both first-time retail participation and institutional
capital at a scale that makes accurate pre-listing forecasting materially
useful. At the same time, media attention has concentrated on a small number
of extreme first-day gains, which are unrepresentative of the typical listing
experience: in the dataset assembled for this study, the median first-day
return is 11.4 percent while the mean is 21.3 percent, reflecting a distinctly
right-skewed distribution.

The pricing of an IPO is set in a book-building process during which
institutional demand, retail demand, and unofficial grey-market indications
are all observable *before* the stock begins trading. In principle, then, a
model trained on pre-listing information should be able to produce useful
forecasts of first-day return. In practice, the strongest single publicly
available signal — the grey-market premium (GMP) — is known to correlate
strongly with realised first-day return, but it is not always available (in
particular it was not tracked for most of 2019) and it embeds signals whose
sources are not directly interpretable to a regulator or an investment
committee.

Alongside these quantitative signals, every Indian IPO is accompanied by a
Draft Red Herring Prospectus (DRHP) and a Red Herring Prospectus (RHP) filed
with the Securities and Exchange Board of India (SEBI). These documents
contain a dedicated **Risk Factors** section — typically several dozen pages —
in which the issuer is required by regulation to disclose company-specific
risks including customer concentration, litigation, promoter pledges,
regulatory action, contingent liabilities, and going-concern threats. It is
plausible that a well-designed extraction of these disclosures yields
predictive information that is *not* already captured by numeric demand
signals. This dissertation tests that claim.

## 1.2 Research question and sub-questions

**Primary research question.**

> Do structured, interpretable risk-factor features extracted from Indian IPO
> offer documents by a large language model add statistically significant
> incremental predictive power for first-day return, beyond a strong baseline
> of pre-listing numeric and market features, under strictly leakage-controlled,
> time-based evaluation?

**Sub-questions.**

- **SQ1 — Incremental value.** Given a strong numeric baseline model, does
  augmenting it with LLM-extracted structured risk features improve predictive
  accuracy on a temporally held-out test set, and is that improvement
  statistically significant under a Clark-West test for nested forecast
  comparison (Clark and West, 2007)?
- **SQ2 — Interpretability.** Which extracted risk fields carry the greatest
  predictive weight, as measured by SHAP values (Lundberg and Lee, 2017), and
  are those weights consistent with prior finance literature on IPO underpricing
  (Ritter, 1991; Loughran and McDonald, 2011)?
- **SQ3 — Extraction validity.** Against a manually-labelled sample of 30–50
  prospectuses, what precision, recall, and F1 does the schema-guided LLM
  extraction achieve for each risk field?
- **SQ4 — Extraction methodology comparison** (optional, subject to time).
  How does schema-guided LLM extraction compare in cost, latency, and
  precision/recall to a regular-expression-based baseline extractor on the
  same risk fields?

## 1.3 Contribution and novelty

The novelty claim of this dissertation is methodological. Existing work on
IPO prospectus modelling either (a) uses opaque text embeddings via
retrieval-augmented generation, in the manner of Ghosh, Zheng, and Lopez-Lira
(2024), or (b) uses hand-crafted lexicon counts such as the Loughran-McDonald
financial dictionary (Loughran and McDonald, 2011). No published work of which
the author is aware applies **schema-guided structured extraction** of typed
risk fields to Indian IPO prospectuses and evaluates the resulting features
for *incremental* predictive value over a strong numeric baseline under
strictly leakage-controlled temporal evaluation.

The specific contributions are:

1. A reproducible pipeline for collecting, cleaning, and jointly analysing
   Indian mainboard IPO data from Chittorgarh, SEBI, InvestorGain, and Yahoo
   Finance, released with the code accompanying this dissertation.
2. A schema of typed risk-factor fields derived from Indian regulatory
   requirements, populated by LLM extraction from 416 verified prospectus PDFs.
3. Empirical evaluation of incremental predictive value under two model
   families (a linear Ridge baseline and a gradient-boosted tree), with formal
   testing via the Clark-West statistic and interpretability via SHAP.
4. A hand-labelled validation set of prospectus extractions and reported
   precision/recall per field, supporting reproducibility and third-party audit.

## 1.4 Scope and non-goals

**In scope.** Indian mainboard equity IPOs listed between February 2019 and
July 2026. First-day return, defined as `(listing_close - issue_price) /
issue_price`. Pre-listing information only: no listing-day open, high, or
low is used as a predictor.

**Out of scope.** SME-platform IPOs (which follow a different listing regime),
Real Estate Investment Trusts (REITs), Infrastructure Investment Trusts
(InvITs), follow-on public offerings (FPOs), and non-Indian markets. Long-term
post-listing performance (30-day, 90-day, 1-year returns) is not modelled.
Any trading or investment strategy that would result from the model is
explicitly not proposed and not endorsed.

## 1.5 Dissertation structure

- **Chapter 2** reviews prior work on IPO first-day return prediction, LLM
  extraction from financial documents, and structured versus embedding-based
  representations of long financial texts.
- **Chapter 3** describes the data collection pipeline — Chittorgarh IPO
  tracker and detail pages, SEBI DRHP/RHP downloads, InvestorGain grey-market
  data, Yahoo Finance market context, and the Ghosh et al. cross-validation
  dataset.
- **Chapter 4** documents data cleaning: leakage controls, target definition,
  handling of missing values, and locked methodological decisions.
- **Chapter 5** presents exploratory data analysis, including the observed
  regime shift between 2024 and 2025.
- **Chapter 6** describes feature engineering, motivated by the EDA findings.
- **Chapter 7** describes LLM-based structured extraction of risk factors.
- **Chapter 8** sets out the modelling methodology, temporal splits, and
  evaluation metrics.
- **Chapter 9** reports results.
- **Chapter 10** discusses implications, limitations, and threats to validity.
- **Chapter 11** concludes.

---

*Chapter placeholders in this section marked `[TODO: HRITIK — ...]` require
the author's own writing before submission.*