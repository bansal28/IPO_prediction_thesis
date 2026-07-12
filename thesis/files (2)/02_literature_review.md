# 2. Literature Review

> **NOTE TO SELF (Hritik):** This chapter is a *scaffold* built from the five
> key papers identified in the project handoff. It gives you a working
> structure and paragraph-level content to expand. **Before submission, each
> paper must be re-read and this chapter re-written in your own voice.** In
> particular, do not cite claims that you have not personally verified against
> the original text — I have marked such claims below with
> `[VERIFY: HRITIK — check against original paper]`.

## 2.1 IPO underpricing: the classical view

The observation that initial public offerings systematically close their first
trading day above the issue price is one of the most consistently replicated
findings in empirical finance. Ritter (1991) established the pattern using
United States data, showing both a first-day pop and a longer-run
underperformance relative to seasoned firms. Subsequent work has examined the
economic reasons proposed for the pop — asymmetric information between issuer
and investor (Rock, 1986), signalling by underwriters, deliberate marketing
underpricing to build post-listing demand (Loughran and Ritter, 2004) — and
has replicated the pattern across most developed and emerging markets.

For India specifically, first-day underpricing has been documented in multiple
studies of the Bombay Stock Exchange and the National Stock Exchange, though
sample composition and methodology vary. The current study focuses on
mainboard IPOs listed 2019–2026 and finds a mean first-day return of
21.3 percent and a median of 11.5 percent, consistent with the direction of
prior Indian findings.

## 2.2 The grey-market premium

Unique to certain Asian markets including India, an unregulated **grey market**
in IPO shares operates between the closing of the book-building period and the
first day of listed trading. The grey-market premium (GMP), publicly reported
by trackers such as InvestorGain and Chittorgarh, represents the price at
which unofficial traders are willing to buy the yet-to-list shares above the
issue price. Practitioner accounts and industry reporting have long noted a
close correspondence between GMP at the eve of listing and the realised
first-day return, with correlations reported informally in the region of 0.8.
This study finds a correlation of 0.853 between `gmp_return = gmp_value /
issue_price` and the first-day return (calculated on the numeric feature set
in Chapter 6). Because GMP is such a powerful pre-listing signal, any
methodological claim about *incremental* predictive value from other features
must control for it explicitly. This motivates the dual reporting of results
both with and without GMP as a feature (Chapter 8).

[VERIFY: HRITIK — verify with a citable source that a published academic
paper documents the ~0.8 GMP correlation, or state clearly that this is an
industry-reported figure with no peer-reviewed source at time of writing.]

## 2.3 Text-based signals from financial disclosures

Loughran and McDonald (2011) established that generic sentiment lexicons
performed poorly on financial text and constructed a domain-specific
dictionary that separated tonal categories including *negative*, *positive*,
*uncertainty*, *litigious*, and *modal*. Their dictionary and its subsequent
refinements have become standard baselines for lexicon-based analysis of
10-K filings, earnings calls, and prospectuses. However, lexicon-based
approaches are inherently limited to counting: they cannot represent *what*
a risk is about, only whether the language surrounding it is broadly negative
or uncertain.

## 2.4 Retrieval-augmented representations of long financial documents

Ghosh, Zheng, and Lopez-Lira (2024, arXiv:2412.16174) applied retrieval-
augmented generation to Indian IPO prospectuses, embedding chunks of the offer
document and using nearest-neighbour retrieval to construct feature vectors
for downstream prediction of first-day return. Their approach represents the
current published state of the art for LLM-based prospectus modelling on
Indian data.

[VERIFY: HRITIK — read Ghosh et al. carefully before submission. Confirm
their exact target definition, their sample size, their date range, and their
reported R² or MAE. Report those numbers in a comparison paragraph.]

The Ghosh approach has two limitations that motivate the present study.
First, the resulting features are *opaque*: an embedding-based
representation cannot be examined by a human reader to determine what aspect
of a prospectus drove a particular prediction. Second, the interpretability
required for regulatory audit and investment-committee use is entirely absent.

## 2.5 Structured extraction and FinTagging

FinTagging (arXiv:2505.20650) explores schema-driven extraction of typed
financial facts from disclosures. The general programme of *schema-guided
LLM extraction* — where the model is constrained to produce output conforming
to a predefined typed schema (for example via Pydantic or JSON Schema) — has
been shown to yield higher precision and easier downstream auditability than
free-form generation on financial text.

[VERIFY: HRITIK — read the FinTagging paper (arXiv:2505.20650) and confirm
that its findings support this framing. If it makes stronger or different
claims, adjust accordingly.]

## 2.6 Financial-domain embeddings and model selection

Fin-E5 (arXiv:2502.10990, associated with the FinMTEB benchmark) reports that
finance-tuned embeddings outperform general-purpose embeddings on financial
retrieval tasks by approximately 4.5 percent, with frontier large language
models substantially outperforming smaller models on zero-shot financial
extraction. These findings inform the model-selection decisions of the
present study (Chapter 7): a frontier model is used for extraction, and any
embedding-based baselines use finance-appropriate embeddings rather than
general web-trained embeddings.

[VERIFY: HRITIK — check the exact wording of the Fin-E5 finding before
citing the 4.5 percent figure.]

## 2.7 Positioning of the present work

To the author's knowledge, no published work applies **schema-guided structured
extraction** to Indian IPO prospectuses, evaluates the resulting features for
*incremental* predictive value over a strong numeric baseline (including GMP),
tests the improvement with a Clark-West statistic, and reports SHAP-based
interpretability. This dissertation attempts to fill that gap.

## 2.8 References

[TODO: HRITIK — assemble a proper BibTeX file at `thesis/references.bib`.
Placeholder entries listed below to be replaced with full citations.]

- Ghosh, S., Zheng, X., and Lopez-Lira, A. (2024). *[Full title]*. arXiv:2412.16174.
- Ritter, J. R. (1991). *The long-run performance of initial public offerings*.
  Journal of Finance, 46(1), 3–27.
- Rock, K. (1986). *Why new issues are underpriced*. Journal of Financial
  Economics, 15(1–2), 187–212.
- Loughran, T. and Ritter, J. (2004). *Why has IPO underpricing changed over
  time?* Financial Management, 33(3), 5–37.
- Loughran, T. and McDonald, B. (2011). *When is a liability not a liability?
  Textual analysis, dictionaries, and 10-Ks*. Journal of Finance, 66(1), 35–65.
- Lundberg, S. M. and Lee, S.-I. (2017). *A unified approach to interpreting
  model predictions*. NeurIPS.
- Clark, T. E. and West, K. D. (2007). *Approximately normal tests for equal
  predictive accuracy in nested models*. Journal of Econometrics, 138(1),
  291–311.
- FinTagging authors (2025). *[Full title]*. arXiv:2505.20650.
- Fin-E5 / FinMTEB authors (2025). *[Full title]*. arXiv:2502.10990.
