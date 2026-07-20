# 7. Schema-Guided Risk Extraction

Chapter 6 produced the numeric feature matrix from structured deal and
financial data. This chapter constructs the second, and novel, feature
family: a set of typed risk-factor variables extracted from the 416
certified risk-section markdown files produced by the pipeline of
Chapter 3, §3.7. The extraction is carried out by a large language
model constrained to a fixed schema, and its output is engineered into
`data/features/features_risk_engineered.csv`, which the modelling of
Chapters 8 and 9 combines with the numeric matrix to form the augmented
feature set.

The methodological contribution of this chapter is the *form* of the
risk features, not merely their source. Ghosh, Zheng and Lopez-Lira
(2024), working on an overlapping universe of Indian IPOs, encode
prospectus text as dense retrieval-augmented embeddings — high-
dimensional, opaque vectors whose individual components carry no
interpretable meaning. The present design instead requires the model
to emit a small number of *named, typed, auditable* quantities: counts
of litigation of specified kinds, monetary exposures in a fixed unit,
and categorical financial-health flags. Every value can be traced to a
sentence in a source document and checked by hand. This is what makes
the sub-questions of the dissertation answerable: SQ2 (which risk
features carry signal) requires features that have identities, and SQ3
(did the model extract faithfully) requires features that can be
compared against a ground truth. An embedding has neither property.

The organisation is: the extraction schema (§7.2) and its empirical
revision (§7.3); the extraction prompt (§7.4); model and provider
selection (§7.5); the extraction run itself (§7.6); the faithfulness
audit that answers SQ3 (§7.7); risk-feature engineering (§7.8); the
output feature file and its missingness structure (§7.9); and the
caveats this chapter hands forward to modelling (§7.10). As in
Chapter 6, the design work is recorded as decisions in Appendix A
(D-36 through D-41); this chapter documents how those decisions were
operationalised and what the resulting file looks like.

## 7.1 Overview

The extraction is implemented in `src/processing/09_extract_llm_risk.py`,
a provider-agnostic runner whose inputs are the certified risk-section
corpus and a fixed schema, and whose output is the raw extraction file
`data/features/features_llm_risk.csv` (416 rows, one per IPO). A second
script, `src/processing/10_engineer_risk_features.py`, transforms that
raw file into the modelling-ready matrix `features_risk_engineered.csv`.
A third, `src/processing/qa_flag_risk_features.py`, produces a review
list of rows warranting manual inspection. The schema itself lives in
`src/processing/risk_extraction_schema.py` and the prompt in
`src/processing/system_prompt_risk_extraction.md`.

No listing-day information enters at any step, and — critically for the
integrity of SQ1 — no stage of extraction or feature engineering reads
the target `first_day_return`. The engineering script consults the
numeric feature file for exactly one variable, `assets_log1p`, used as a
size normaliser (§7.8); it reads no other column, and in particular
never reads the outcome. Whether these features predict the target is
the question the dissertation exists to answer, and answering it
honestly requires that the features be constructed without reference to
it.

## 7.2 The extraction schema

The schema is a single Pydantic v2 model, `RiskExtraction`, with twelve
fields. Two are free-text audit fields, one is a unit declaration, and
nine are the risk features proper. Field descriptions serve a dual
purpose: they are simultaneously the instruction given to the model
(lifted into the JSON schema via `use_attribute_docstrings=True`) and
the labelling rule used by the human annotator when constructing the
gold set of §7.7. Table 7.1 lists the fields.

| Field | Type | Role |
|---|---|---|
| `issuer_name_as_stated` | str | audit / identity |
| `extraction_reasoning` | str | audit trace (reasoning-first) |
| `source_currency_unit` | enum(6) | unit of monetary tables |
| `criminal_cases_against_count` | int? | litigation count |
| `regulatory_actions_against_count` | int? | litigation count |
| `tax_proceedings_against_count` | int? | litigation count |
| `total_litigation_against_amount_cr` | float? | monetary exposure (₹cr) |
| `contingent_liabilities_total_cr` | float? | monetary exposure (₹cr) |
| `going_concern_status` | enum(4) | financial-health flag |
| `auditor_report_status` | enum(4) | financial-health flag |
| `top5_customer_revenue_pct` | float? | revenue concentration |
| `top10_customer_revenue_pct` | float? | revenue concentration |

*Table 7.1. The twelve fields of the `RiskExtraction` schema. Numeric
fields are nullable (`?`); the null-versus-zero distinction is
load-bearing and is defined in §7.4.*

Three design choices in the schema deserve statement here because they
recur throughout the chapter.

**Reasoning-first field order.** The two audit fields precede the
numeric fields, and the model is instructed to write
`extraction_reasoning` *before* emitting any number. Because generation
is left-to-right, this forces the model to commit to a spoken account of
which table rows it is counting and how it is converting units before it
produces the counts themselves. The reasoning field is not a feature; it
is the artefact that makes the faithfulness audit of §7.7 possible on all
416 rows rather than only on the hand-labelled subset.

**Nullability with an explicit null-versus-zero semantics.** Every
numeric field is `Optional`. A null means the underlying disclosure is
*absent* (no litigation table in the risk section; no contingent-
liability total stated); a zero means the disclosure is present and
explicitly nil. This distinction is enforced in the prompt (§7.4) and is
essential downstream: a null must become a missingness indicator at
modelling time, never a zero (§7.8, §7.10).

**Validators encode bounds; the model config does not forbid extras.**
Non-negativity of counts and amounts, the 0–100 range of percentages,
and the `top5 ≤ top10` ordering are enforced by Pydantic validators
rather than by field constraints, so that the emitted JSON schema stays
within the subset both target providers accept. The model config
deliberately does *not* set `extra="forbid"`: doing so makes Pydantic
emit `additionalProperties: false`, which one provider's structured-
output mode requires but the other rejects. The chosen configuration
satisfies both, a compatibility point recorded as D-38.

## 7.3 Empirical revision of the schema (v1 → v3)

The schema was not designed in the abstract. It reached its final form
through two revisions driven by close reading of the corpus and by a
scored trial against a hand-labelled gold set (§7.7). The revisions are
recorded in full as D-37; the substance is as follows.

The **first revision** removed two fields that a naïve design included
but that the risk section does not actually support. A promoter-share-
pledge field was cut because the risk section contains only lock-in
boilerplate; the real pledge data lives in the Capital Structure
section, outside this corpus. A related-party-transaction *amount* field
was cut because the risk section discusses related-party dealings only
qualitatively, with the rupee figures residing in the financial
statements. Retaining either would have produced a feature that was
null or degenerate across the corpus — the risk-section analogue of the
`face_value` problem of Chapter 6, §6.3.

The **second revision** sharpened the three most error-prone
definitions after the first scored trial revealed systematic
disagreement between candidate models:

- *Litigation was split into three separate counts* — criminal,
  statutory/regulatory-enforcement, and tax — with the regulatory count
  explicitly *excluding* tax. In the pre-split design the single
  "regulatory" field produced wild disagreement (one file scored 0
  versus 7, another 162 versus 113) that resolved to a single cause:
  ambiguity about whether tax proceedings were regulatory. Giving tax
  its own field removed the ambiguity and added a feature.
- *The severe auditor category was tightened to require explicit
  opinion-modification wording.* Both trial models had tagged a file
  "qualified" on the strength of the vague phrase "qualifications and
  observations on certain matters"; the corrected definition reserves
  the severe tier for the literal language of a modified opinion
  ("qualified opinion", "adverse opinion", "disclaimer of opinion"),
  and routes CARO remarks and emphasis-of-matter paragraphs to a
  distinct, milder category.
- *Customer concentration was restricted to company-wide figures.* One
  trial file disclosed a segment-level concentration (39.31 percent for
  one business line) that is not comparable to a company-wide figure;
  the corrected definition maps segment-level disclosures to null.
- *A top-5-supplier concentration field was cut* for sparsity: it was
  usable in only one of five trial files, elsewhere blank or
  incomparable.

The entity scope of each field was fixed during this revision and is
deliberately *asymmetric*, a point that matters for interpretation in
§7.10. The criminal and regulatory counts include matters against the
company, its subsidiaries, promoters, directors and key personnel; the
tax count and the monetary aggregates are restricted to the company and
its subsidiaries, excluding promoter and director personal matters. The
rationale is that a promoter's criminal or regulatory history is a
governance signal attaching to the issue, whereas a promoter's personal
tax disputes are not a liability of the issuer.

## 7.4 The extraction prompt

The prompt (`system_prompt_risk_extraction.md`) is provider-agnostic
and encodes the counting conventions that the schema field descriptions
reference. Its load-bearing rules are: reasoning written before numbers;
the null-versus-zero token conventions (a count cell reading "Nil",
"-", "N.A." maps to 0; an amount reading "Nil" maps to 0.0; "Not
ascertainable" is excluded from an aggregate and maps to null; an
absent table maps to null); directional exclusion (count only matters
*against* the relevant parties, excluding every "By …" row such as
Section 138 cheque-bounce recovery suits the company itself files);
per-field entity scope as defined in §7.3; conversion of every monetary
figure to crore (1 crore = 10 million = 100 lakh); use of an explicitly
stated "Total" row rather than re-summing line items; and, for
concentration, a company-wide-only and most-recent-full-fiscal rule that
prefers a full year over an interim stub period.

These conventions are the difference between a feature and a
misleading number. Their correct application across 416 heterogeneous
documents is precisely what the audit of §7.7 tests.

## 7.5 Model and provider selection

Provider selection was constrained by three requirements that jointly
eliminated most candidates: a context window large enough for the
documents (which run to roughly 40,000–100,000 tokens each), support
for constrained structured output against the schema, and enough
throughput to process 416 large documents within the project timeline.

The throughput requirement proved decisive and is worth recording,
because it is counter-intuitive. The binding free-tier limit for
long-document extraction is not requests-per-day but *tokens-per-
minute*: several otherwise-attractive free tiers cap per-minute token
throughput below the size of a *single* one of these documents, making
them unable to process even one file, regardless of a generous daily
request allowance. Among surveyed providers only one free tier had a
per-minute token budget large enough to admit the documents at all, and
its per-day *request* cap on the relevant model was in turn too low to
complete 416 files within the timeline. The free-tier route was
therefore closed not by cost but by rate structure.

A five-file, three-model bake-off was run against the hand-adjudicated
gold set (§7.7) to choose among paid options. Table 7.2 reports the
result, scored field-by-field with counts and enums matched exactly and
amounts and percentages matched within tolerance.

| Model | Accuracy (of 45 cells) |
|---|---|
| `gpt-5.6-terra` | 44 / 45 (98%) |
| `gemini-2.5-flash` | 44 / 45 (98%) |
| `gpt-5.6-luna` | 43 / 45 (96%) |

*Table 7.2. Five files × nine scored fields. The five headline fields —
criminal-against, litigation total, contingent liabilities, going-
concern, and top-5 customer — were matched exactly by all three models.*

The cost-optimised `gpt-5.6-luna` was selected (D-38). Its 96 percent
trial accuracy is within two cells of the frontier models; the two
misses were a single hardest multi-row litigation sum and one
regulatory undercount, neither a systematic error. Decisively, the
model was reachable through pre-existing API credit, making the marginal
cost of the full run negligible against the alternative of provisioning
a new paid provider, and its synchronous throughput completed the corpus
in a single sitting. Reasoning effort was set to `low`: the task is
extraction, not multi-step reasoning; the trial confirmed low was
sufficient; and reasoning tokens bill as output, so a higher setting
would raise cost with no measured accuracy gain. The output-token
ceiling was set to a generous 16,000 to prevent truncation, which bills
only for tokens actually generated.

## 7.6 The extraction run

The full run processed all 416 files through `gpt-5.6-luna` at
`reasoning_effort = low`. The total input volume was 18,857,188 tokens,
priced in advance from an offline `tiktoken` count (no API calls) at an
expected \$22.60; the realised cost was \$21.13. Every row completed with
status `ok`; there were no refusals, no truncations, and no duplicate
rows. Per-row metadata — resolved model, token counts, cost, and a
timestamp — is recorded alongside the extracted fields, and the raw JSON
response for every file is retained under `data/features/llm_raw/` as
the reproducibility anchor: because a hosted model may change under a
fixed name, the retained raw outputs, not the model endpoint, are the
authoritative record of what was extracted.

The runner is resumable. It records completed rows as it goes and, on
restart, skips any file already marked `ok`, re-charging nothing. This
property was used during the run: a laptop-sleep event severed an
in-flight connection, and the run was resumed with the identical command,
continuing from the last completed file without loss or double billing.

## 7.7 Faithfulness audit (SQ3)

SQ3 asks whether the model extracted the schema faithfully. The audit
has two layers.

The **first layer** is a hand-labelled gold set. Five prospectuses were
read in full and annotated field-by-field directly from source, with the
annotations adjudicated against the schema definitions. The adjudication
itself corrected the initial hand-labels in several places where the
model proved *more* thorough than the annotator — for example, correctly
summing a criminal-case count across company, promoter and key-personnel
rows that a first hand pass had under-counted, while correctly excluding
sixty Section 138 recovery suits the company had filed. The gold set is
embedded in `src/processing/score_extraction.py`, which diffs any trial
extraction against it under the tolerances of Table 7.2.

The **second layer** exploits the reasoning-first design to audit all
416 rows, not merely the five gold files. Because every row carries the
model's own account of which rows it counted and how it converted units,
the extreme values — the rows where an error would matter most and where
a unit mistake would hide — can be adjudicated from the reasoning trace
directly. Every one of the largest extractions was checked this way and
found correct:

- The largest monetary value in the corpus, a ₹74,894 crore litigation
  aggregate, is the genuine stated total against the issuer, with 226
  "By" criminal matters correctly excluded and a subsidiary amount
  denominated in a foreign currency correctly dropped as non-convertible.
- The highest litigation counts belong, on inspection, to genuinely
  litigious financial firms; where a count is very large it is frequently
  driven by the issuer's *promoter* rather than the issuer itself (§7.10),
  which the trace makes explicit.
- One issuer's monetary tables were flagged `mixed`-unit because its
  promoter litigation was denominated in Korean Won while the company's
  own tables were in rupees; the model used only the rupee tables and
  excluded the Won figures.

Directional exclusion, asymmetric entity scope, unit conversion, and
full-fiscal-over-stub selection were all observed operating correctly on
these hardest cases. The audit's conclusion is that the extraction is
faithful and that the reasoning column is a genuine, per-row audit trail
rather than a post-hoc rationalisation.

Two limitations are recorded honestly. The gold set is five files; it is
a strong but not exhaustive ground truth, and expanding it is the natural
strengthening of the SQ3 claim. And on a small number of sparse SME
filings the model can, in the absence of a clean table, place a value in
a field where a null would be more defensible; twelve such rows are
surfaced by the QA script (§7.9) for manual inspection and are the only
extraction-quality caveat in the file.

## 7.8 Risk-feature engineering

`10_engineer_risk_features.py` transforms the raw extraction into the
modelling matrix. Every transformation is justified on target-blind
grounds — economic mechanism, skew, coverage, or redundancy — in exact
parallel with the discipline of Chapter 6, and is recorded as D-40. The
transformations are as follows.

**Skew reduction on counts and amounts.** The three counts and two
monetary fields are heavily right-skewed (a criminal count with median 2
and maximum 476; a litigation amount spanning five orders of magnitude).
Each receives a `log1p` transform, on the same bounded-below,
zero-preserving logic used for the numeric predictors in Chapter 6,
§6.2.

**Size normalisation of monetary fields.** The two rupee amounts scale
mechanically with firm size — a large litigation total is partly just a
statement that the firm is large, a confound already present in the
numeric size cluster. Each amount is additionally provided in a size-
adjusted form, `log1p(amount) − assets_log1p`, expressing exposure
relative to firm size. This is the single point at which the engineering
script reads the numeric feature file, and it reads only `assets_log1p`.

**Redundancy elimination, and a finding.** The two concentration
fields, top-5 and top-10 customer revenue, correlate at 0.98 by
construction; only top-10 is retained (marginally better coverage), with
top-5 dropped, exactly as `lot_size` was dropped in Chapter 6, §6.3. The
two monetary fields presented a subtler case. On the *raw* scale they
correlate at 0.95 — because Indian "contingent liabilities" typically
*include* litigation claims, and because both scale with size — which
would ordinarily argue for dropping one. But the transform that reduces
skew also dissolves this collinearity: after `log1p` the correlation
falls to 0.58, and after size-adjustment to 0.43. At 0.43 the two are
only moderately related and carry genuinely distinct information, so
both are retained in size-adjusted form (D-40). The raw-scale 0.95 was a
scale artefact driven by a handful of very large issuers, not a true
redundancy; this is recorded because it revised an earlier decision to
drop one of the pair.

**Collapse of low-variance categoricals.** The going-concern field is 90
percent "not mentioned"; rather than carry a near-constant four-level
category, it is collapsed to two flags — an any-uncertainty flag (issuer
or group doubt, 5.5 percent positive) and an issuer-only flag (1
percent). The auditor field, effectively binary with a 3 percent severe
tail, is encoded as an ordinal severity (0 clean/absent, 1 CARO or
emphasis, 2 modified opinion) plus a binary modified-opinion flag. The
counts, amounts, and their transforms are retained; the run metadata,
the reasoning trace, the unit declaration, and the raw enumerations are
kept in the raw file for audit but excluded from the modelling matrix.

## 7.9 The output feature file

`features_risk_engineered.csv` contains 416 rows and 25 columns. Table
7.3 gives the missingness of the six core features, which — as in
Chapter 6, §6.8 — is concentrated and well-understood.

| Feature | Missing | Interpretation of "missing" |
|---|---:|---|
| `tax_count` | 4% | no litigation table in risk section |
| `criminal_count` | 6% | " |
| `regulatory_count` | 7% | " |
| `litigation_amount` | 7% | no quantified against-total |
| `contingent` | 23% | no contingent-liability total stated |
| `customer_concentration_top10` | 61% | no company-wide figure disclosed |

*Table 7.3. Missingness of the six core risk features. Every missing
value is a genuine non-disclosure, carried as a `*_missing` indicator;
none is a zero.*

Two properties of this missingness structure govern the modelling of
Chapter 8. First, the litigation features are well populated (missing 4
to 7 percent), so the risk block has broad coverage. Second, and
critically, only 27 percent of issuers are complete across all six core
features simultaneously, because customer concentration is disclosed by
barely a third of issuers. Listwise deletion would therefore collapse
the sample from 416 to roughly 111 and destroy the temporal splits of
D-03. The modelling must instead impute with the missingness indicators
present, and treats concentration as a separable feature block tested
on its own rather than allowed to drive imputation noise into the core
model (§7.10).

The distributions of the engineered features are well behaved for
modelling: the `log1p` counts span 0 to roughly 6 with unit-order
standard deviations, the size-adjusted amounts centre near −4 with
comparable spread, and the retained concentration figure spans 11 to
100 percent where present.

The QA script `qa_flag_risk_features.py` writes `qa_flags_risk.csv`,
flagging 81 of 416 rows across six categories — non-standard units,
extreme values, identical litigation-and-contingent amounts, absent
litigation tables, likely-promoter-driven counts, and counts without a
quantified amount — each row accompanied by its reasoning trace so it
can be adjudicated quickly. Eighteen rows carry two or more flags; all
were inspected, and all resolve to correct extractions or to the
promoter-scope property of §7.10 rather than to error.

## 7.10 Caveats carried forward to modelling

Three properties of the risk features are not defects but must be
carried explicitly into the interpretation of Chapters 8 and 9.

**Promoter inflation of the count fields.** Because criminal and
regulatory counts include promoter and director matters (§7.3), an
issuer with a very large corporate promoter inherits that promoter's
litigation. In the two most extreme cases the issuer's own criminal
count is 2 and 87 respectively, while the reported counts of 476 and 475
are dominated by the promoters — each a major bank. These counts are
correct under the schema, but they measure promoter-group litigation as
much as issuer litigation, and SHAP readings in Chapter 9 must be
interpreted with this in mind. The tax count and the monetary
aggregates, restricted to the company and subsidiaries, are not subject
to this effect and are the cleaner exposure measures.

**Weak categoricals.** The going-concern and auditor features are
high-signal when they fire but rare (5.5 and 3 percent positive for the
strongest levels), so they are expected to contribute little in
aggregate. Reporting that a feature was available but did not carry
signal is a legitimate SQ2 finding, not a shortfall of the extraction.

**Sparse concentration.** Customer concentration is disclosed by roughly
a third of issuers. It is retained as a single top-10 feature and tested
as a separable block, so that the main SQ1 test rests on the well-
populated litigation and exposure features and the marginal contribution
of concentration is answered as a clean secondary question.

With the extraction validated and the feature matrix constructed under
the same target-blind discipline as the numeric matrix, the two feature
families are ready to be combined. Chapter 8 fits the numeric baseline
against the numeric-plus-risk augmentation on the locked temporal splits
and tests the nested forecasts, providing the direct answer to SQ1.