# 4. Data Cleaning

This chapter documents the transformation of raw collected data into the
cleaned, analysis-ready master dataset used by all downstream steps in the
dissertation. The cleaning pipeline is implemented in
`src/processing/00_pre_cleaning_audit.py` (a read-only diagnostic pass) and
`src/processing/01_data_cleaning.py` (the actual cleaning), and it produces
`data/processed/master_ipo_dataset.csv` with 419 rows and 29 columns.

## 4.1 Design principles

Three principles govern the cleaning pipeline.

**Reproducibility.** Every step is a scripted transformation of raw inputs
into a versioned output CSV. There is no manual editing of the master file
at any point. If a decision changes, the cleaning script is re-run and the
master is regenerated.

**Zero leakage.** Under no circumstances does a variable computed from
listing-day trading enter the master as a candidate predictor. The listing
open, high, low, and close values are retained in the master strictly for
computing the target and for reproducibility, and are explicitly excluded
from any downstream feature set. Market context (Nifty and India VIX) is
merged as strictly prior-day values via a leakage-safe join
(`merge_asof(direction='backward', allow_exact_matches=False)`).

**Evidence-based rules over intuition.** Every non-trivial cleaning
decision — such as the treatment of GMP equal to zero — is grounded in an
inspection of the underlying data, and the evidence is recorded together
with the decision in Appendix A.

## 4.2 Cleaning pipeline

The pipeline executes nine steps.

1. **Load.** `raw_ipo_details.csv` is read (434 rows × 30 columns).
2. **Parse strings to numbers.** Columns delivered as human-readable strings
   (issue price with currency symbols, subscription multiples with "x"
   suffixes) are parsed into numeric columns.
3. **Drop non-equity vehicles.** REITs, InvITs, and similar trusts are
   removed by name pattern (see Section 4.3).
4. **Compute the target.** `first_day_return = (listing_close − issue_price)
   / issue_price`, using the detail-page `listing_close` (locked decision,
   Section 4.4).
5. **Parse listing dates** into pandas `Timestamp` objects.
6. **Merge market context.** Nifty 50 and India VIX values from the trading
   day immediately preceding listing are merged in via `merge_asof`; a
   seven-day and thirty-day trailing Nifty return are computed from the same
   source.
7. **Merge grey-market data.** GMP is merged from `raw_gmp_data.csv` using a
   name-aware join with an eleven-item override dictionary for
   brand-to-legal-name mappings (see Section 4.6).
8. **Cross-validation join with Ghosh et al.** 175 IPOs overlap; issue-price
   concordance is checked (100 percent agreement observed).
9. **Column selection and write.** The final 29 columns are selected and
   written to `data/processed/master_ipo_dataset.csv`.

## 4.3 Removal of non-equity vehicles

Real Estate Investment Trusts (REITs), Infrastructure Investment Trusts
(InvITs), and similar hybrid instruments are outside the scope of this study
because their pricing, disclosure requirements, and expected first-day
behaviour differ substantially from ordinary equity IPOs. A single regex-
based rule identifies them:

```
name matches: REIT | Trust | InvIT | Embassy Office | Mindspace Business
```

Fifteen listings are matched and removed:

1. Embassy Office Parks
2. Mindspace Business Parks
3. POWERGRID InvIT
4. Brookfield India Real Estate Trust
5. Nexus Select Trust
6. PropShare Platina
7. Bharat Highways InvIT
8. Anantam Highways Trust
9. Knowledge Realty Trust
10. PropShare Titania
11. Capital Infra Trust
12. Bagmane Prime Office REIT
13. Citius Transnet Investment Trust
14. PropShare Celestia
15. Raajmarg Infra Investment Trust

Post-removal the working dataset contains 434 − 15 = 419 IPOs.

## 4.4 Listing-close: detail page, never tracker

Early sanity checking revealed seven IPOs on which the yearly tracker CSV
reported a `listing_close` materially different from the detail-page value.
For every one of the seven checked, the detail page agreed with the primary-
exchange record (for example Mankind Pharma's detail page correctly showed
₹1,424.05 while the tracker showed ₹1,080). Accordingly, a locked decision
is recorded that the detail-page value is authoritative and the tracker
value is ignored for `listing_close`.

## 4.5 Grey-market premium: the GMP-equal-to-zero rule

Grey-market premium equal to zero is *ambiguous* on its own. It could mean
either "the market is signalling that no premium is expected" (a genuine
signal, comparable to a low positive GMP) or "GMP was not tracked for this
IPO" (a data availability gap that should be treated as missing).

The cleaning pipeline resolves this ambiguity by year, based on an
inspection of the outcomes.

- **2019.** All GMP values are set to missing, because InvestorGain's GMP
  tracking was not established for this period. This is supported by the
  observation that IPOs recorded as GMP = 0 in 2019 (e.g. IRCTC, with a
  first-day return of +95 percent) show that the zero clearly does not
  reflect a genuine no-premium market signal.
- **2020.** GMP = 0 is set to missing *only if* the observed first-day
  return exceeds 15 percent. This conservative rule assumes that any 2020
  IPO with GMP = 0 that nevertheless popped more than 15 percent had an
  untracked GMP, while retaining as genuine any GMP = 0 that was consistent
  with a small-return outcome.
- **2021 and later.** GMP = 0 is kept as a genuine signal. Inspection of the
  data supports this: 2021+ IPOs with reported GMP = 0 subsequently listed
  at approximately 0 percent average return on the first day, consistent
  with GMP = 0 being an informative signal rather than a missing value.

A companion flag column `gmp_available` is set for every IPO to distinguish
"GMP was tracked and reported" from "GMP is missing". This flag is retained
as a candidate feature (Chapter 6) because whether or not GMP is tracked is
itself informative — untracked GMP correlates with earlier and smaller IPOs.

## 4.6 Name-aware GMP merge and the collision fix

Merging GMP into the master by (company name, listing date) is not entirely
reliable because Indian IPOs are widely known by trading names (Paytm,
Firstcry, Policybazaar) that differ from the legal names that appear on
Chittorgarh (One 97 Communications, Brainbees Solutions, PB Fintech). An
override dictionary of eleven mappings is applied before matching.

| Trading name (as on InvestorGain) | Legal name (as on Chittorgarh) |
|---|---|
| CAMS | Computer Age Management Services |
| Paytm | One 97 Communications |
| Policybazaar | PB Fintech |
| KIMS | Krishna Institute of Medical Sciences |
| Firstcry | Brainbees Solutions |
| Leela Hotels | Schloss Bangalore |
| NSDL | National Securities Depository |
| [TODO: HRITIK — complete the list of 11 by inspecting the cleaning script] | |

A *collision fix* was also applied. In an initial version of the pipeline,
GMP was merged on a (issue price, listing date) key. Two IPOs — GNG
Electronics and Indiqube Spaces — both listed on 30 July 2025 at an issue
price of ₹237, and the join therefore incorrectly assigned GNG's GMP of ₹85
to Indiqube Spaces. The fix disambiguates collisions by company-name
token overlap. After the fix, GNG retains GMP = 85 and Indiqube receives
GMP = 0, matching the source data on InvestorGain.

## 4.7 Ghosh et al. cross-validation

The Ghosh et al. supplementary dataset (Section 3.7) is joined to the master
by normalised company name (lowercased, whitespace-collapsed, " ipo" suffix
stripped). 175 IPOs overlap. On the overlap, `Final_Issue_Price` in Ghosh
agrees with `issue_price` in the master to 100 percent concordance. This
provides an independent cross-check that the issue-price extraction from
Chittorgarh detail pages is faithful.

An earlier version of the join produced zero overlaps because the auto-
detector selected `Issuer Company` as the price column (its column heading
contained the substring "issue") and because the " IPO" suffix in Ghosh's
company names was not stripped. Both defects are corrected in the final
pipeline. The details are logged in Appendix A.

## 4.8 Columns and coverage of the master dataset

The master dataset `data/processed/master_ipo_dataset.csv` contains 419
IPOs and 29 columns. The columns are grouped as follows.

| Group | Columns |
|---|---|
| Identifiers | `company`, `listing_date`, `year` |
| Targets | `first_day_return`, `first_day_open_return` |
| Issue structure | `issue_price`, `face_value`, `lot_size`, `total_issue_size`, `fresh_issue`, `ofs` |
| Demand | `sub_total` |
| Grey market | `gmp_value`, `gmp_available` |
| Financials | `revenue`, `profit`, `assets`, `net_worth`, `borrowing` |
| Broker sentiment | `brokers_subscribe`, `brokers_avoid` |
| Market context | `nifty_close`, `vix_close`, `nifty_7d_return`, `nifty_30d_return` |
| Listing OHLC (retained for reproducibility; NOT features) | `listing_open`, `listing_close`, `listing_high`, `listing_low` |

Non-listing columns achieve close to 100 percent coverage. The columns with
material missingness are: `fresh_issue` (81 percent), `ofs` (80 percent),
`gmp_value` (95 percent), `borrowing` (88 percent), `net_worth` (96 percent),
and `revenue` / `profit` / `assets` (99 percent each).

**Note on units.** `total_issue_size`, `fresh_issue`, and `ofs` are recorded
in *number of shares*, not rupees. Deal size in rupees is obtained by
multiplying by `issue_price`. This is an important interpretive point for
any downstream feature that uses issue size as a proxy for deal scale, and
it is discussed in Chapter 6.

## 4.9 Verification of the cleaned master

Six checks were performed on the final master, all of which pass.

1. **Zero leakage.** For every one of the 419 IPOs, the joined `nifty_close`
   date is strictly *before* the listing date. This is verified explicitly
   by asserting `nifty_join_date < listing_date` on every row.
2. **Target integrity.** Recomputing `first_day_return` from `issue_price` and
   `listing_close` on the master reproduces the stored value to a maximum
   absolute error of 2 × 10⁻¹⁶ (numerical precision).
3. **GMP spot-checks.** Zomato → 22, Sigachi → 225, Tata Technologies → 475,
   Swiggy → 0. All match the source at InvestorGain.
4. **Structural integrity.** No duplicate `company` values;
   `face_value ∈ {1, 2, 4, 5, 10}`; `issue_price ≥ face_value` for every row.
5. **Financial sign checks.** Forty-five IPOs report a negative `profit`
   (loss-making), which is retained as valid data. Five IPOs report a
   negative `net_worth`, which is retained but flagged for special treatment
   in feature engineering (Chapter 6).
6. **Sanity on market columns.** VIX range 9.7 to 51.5. Worst trailing 30-day
   Nifty return −18 percent (SBI Cards, listed 16 March 2020, coinciding with
   the COVID-19 market crash — sanity confirmed).

The distributional properties of the target on this cleaned master —
mean 21.3 percent, median 11.5 percent, minimum −35.9 percent (Om Freight),
maximum +270.4 percent (Sigachi), positive share 71.1 percent — form the
subject of Chapter 5.

## 4.10 Temporal split preview

Because all evaluation in this dissertation is strictly time-based, the
temporal split induced by the cleaned master is presented here for reference.
The split is applied at modelling time (Chapter 8), not at cleaning time,
but the counts are useful for planning.

| Split | Years | IPO count |
|---|---|---|
| Train | 2019–2023 | 196 |
| Validation | 2024 | 91 |
| Test | 2025–2026 | 132 |
| **Total** | 2019–2026 | **419** |

No random splitting is used at any point in this dissertation.
