#!/usr/bin/env python3
"""
05_risk_section_eda.py — Phase 6 EDA on the 416 risk-section markdowns.

Purpose
-------
Describe the risk-section corpus before designing the Phase 7 LLM
extraction schema:
  - length distribution (words, chars) overall, by year, by extraction status
  - number of numbered risk items per prospectus
  - regex prevalence of the tentative schema concepts
  - length-as-baseline signal (Spearman with first_day_return, train+val only)
  - temporal vocabulary drift (top TF-IDF n-grams per year)

Outputs
-------
    data/features/risk_section_summary.csv
        One row per IPO with length, item count, concept hit counts, and
        rupee-amount-in-context counts. This is the artifact carried into
        Phase 7 as the numeric baseline that any LLM extraction must beat.

    reports/tables/eda/05_risk_sections/*.csv
        Descriptive tables (length stats, prevalence, correlations, n-grams).

    reports/figures/eda/05_risk_sections/*.png
        Distribution plots, prevalence heatmap, length-vs-return scatter.

Leakage discipline
------------------
The length-vs-return Spearman is computed on year <= 2024 only
(train + val, n<=284), NEVER on test (2025-2026). This is asserted
in code. All other analyses are descriptive of the corpus and use
the full 416.

Author's note on the OCR file
-----------------------------
Manoj_Vaibhav_Gems__N__Jewellers_Ltd_.md was produced by Tesseract OCR
(the source PDF is image-only). The _extraction_log.csv row for this
file still shows chars=0/words=0 (log was not updated). This script
recomputes chars/words from the .md file directly and flags the row
with is_ocr=True. The extraction log is read but never written to.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import linregress, spearmanr
from sklearn.feature_extraction.text import (
    ENGLISH_STOP_WORDS,
    TfidfVectorizer,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MASTER_CSV = PROJECT_ROOT / "data" / "processed" / "master_ipo_dataset.csv"
RISK_DIR = PROJECT_ROOT / "data" / "processed" / "risk_sections"
LOG_CSV = RISK_DIR / "_extraction_log.csv"

OUT_ARTIFACT = PROJECT_ROOT / "data" / "features" / "risk_section_summary.csv"
OUT_TABLES = PROJECT_ROOT / "reports" / "tables" / "eda" / "05_risk_sections"
OUT_FIGURES = PROJECT_ROOT / "reports" / "figures" / "eda" / "05_risk_sections"

for p in (OUT_ARTIFACT.parent, OUT_TABLES, OUT_FIGURES):
    p.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
OCR_FILE_STEM = "Manoj_Vaibhav_Gems__N__Jewellers_Ltd_"
TRAIN_VAL_YEARS = {2019, 2020, 2021, 2022, 2023, 2024}
TEST_YEARS = {2025, 2026}
RNG_SEED = 42

# Plot style
sns.set_theme(style="whitegrid", context="notebook")
plt.rcParams["figure.dpi"] = 110
plt.rcParams["savefig.dpi"] = 150
plt.rcParams["savefig.bbox"] = "tight"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def company_to_stem(company_name: str) -> str:
    """Convert master's `company` column to the risk-section filename stem.

    Rule: preserve alphanumerics and hyphens, replace everything else with
    underscore. Verified deterministic on all 416 rows.
    """
    return re.sub(r"[^A-Za-z0-9\-]", "_", company_name)


_MARKDOWN_STRIP_PATTERNS = [
    re.compile(r"<!--.*?-->", flags=re.DOTALL),  # HTML comments
    re.compile(r"</?u>"),                          # underline tags
    re.compile(r"\*+"),                            # bold/italic asterisks
    re.compile(r"_+"),                             # italic underscores
    re.compile(r"`+"),                             # code ticks
    re.compile(r"^#+\s*", flags=re.MULTILINE),     # heading markers
    re.compile(r"^\s*\|.*\|\s*$", flags=re.MULTILINE),  # table rows
]


def strip_markdown(text: str) -> str:
    """Remove markdown syntax so char/word counts reflect content, not markup."""
    for pat in _MARKDOWN_STRIP_PATTERNS:
        text = pat.sub(" ", text)
    return text


def compute_length(text: str) -> tuple[int, int]:
    """Return (chars, words) after markdown stripping."""
    clean = strip_markdown(text)
    return len(clean), len(clean.split())


# ---------------------------------------------------------------------------
# Numbered-item detection
# ---------------------------------------------------------------------------
#
# Numbered risk items are formatted three different ways across the corpus:
#
#   A. Heading with number:   # **_2. Something..._**   or  # 3. Something
#   B. Inline bold(-italic):  **1. Something**          or  **_1. Something_**
#   C. Plain numbered:        1. Something              (OCR files only)
#
# We match all three, dedupe by integer, and report both the count of
# unique numbers found and any gaps in the 1..max range. Gaps signal
# a regex miss and get flagged in a diagnostic CSV.

PAT_HEADING_NUM = re.compile(
    r"^#+\s*\**_?(\d{1,3})[.\s*_]", flags=re.MULTILINE
)
PAT_INLINE_BOLD_NUM = re.compile(
    r"^\*\*_?(\d{1,3})\.", flags=re.MULTILINE
)
PAT_BLOCKQUOTE_NUM = re.compile(
    r"^>\s*\*\*_?(\d{1,3})\.", flags=re.MULTILINE
)
PAT_PLAIN_NUM = re.compile(
    r"^(\d{1,3})\.\s+[A-Z]", flags=re.MULTILINE
)

# Sanity cap: real risk sections rarely have >150 numbered items.
# Numbers above this are almost certainly page-number contamination.
MAX_PLAUSIBLE_ITEMS = 150


def count_numbered_items(text: str) -> dict:
    """Detect numbered risk items via multi-pattern union.

    Returns a dict with:
        n_items       -- count of unique integers detected
        max_number    -- largest integer detected
        n_gaps        -- count of missing integers in 1..max_number range
        gaps          -- comma-separated list of missing integers (str)
    """
    numbers: set[int] = set()
    for pat in (
        PAT_HEADING_NUM, PAT_INLINE_BOLD_NUM,
        PAT_BLOCKQUOTE_NUM, PAT_PLAIN_NUM,
    ):
        for m in pat.findall(text):
            try:
                n = int(m)
                if 1 <= n <= MAX_PLAUSIBLE_ITEMS:
                    numbers.add(n)
            except ValueError:
                continue

    if not numbers:
        return {"n_items": 0, "max_number": 0, "n_gaps": 0, "gaps": ""}

    max_n = max(numbers)
    expected = set(range(1, max_n + 1))
    gaps = sorted(expected - numbers)
    gaps_str = ",".join(str(g) for g in gaps[:20])  # truncate long lists
    return {
        "n_items": len(numbers),
        "max_number": max_n,
        "n_gaps": len(gaps),
        "gaps": gaps_str,
    }


# ---------------------------------------------------------------------------
# Concept regexes
# ---------------------------------------------------------------------------
#
# These patterns test the *tentative* Phase 7 schema for base-rate
# variance. A concept with ~100% hit rate is not usable as a flag
# (must become count/amount). A concept with ~0% hit rate is not
# usable at all (must be dropped or reformulated). Everything in
# between is a candidate for the schema.
#
# All matching is case-insensitive; input text is lower-cased in
# count_concept_hits().

CONCEPT_PATTERNS: dict[str, str] = {
    "criminal_proceedings": (
        r"criminal\s+(?:proceedings?|litigation|cases?|matters?|complaints?)"
    ),
    "regulatory_action": (
        r"(?:show[- ]cause\s+notice"
        r"|regulatory\s+action"
        r"|sebi\s+(?:notice|order|proceedings?)"
        r"|rbi\s+(?:notice|order))"
    ),
    "customer_concentration": (
        r"(?:customer\s+concentration"
        r"|top\s+(?:\d+|ten|five|three|twenty|twenty[- ]five)\s+customers?"
        r"|dependent?\s+on\s+(?:our\s+)?"
        r"(?:key|major|top|significant|limited\s+number\s+of)\s+customers?)"
    ),
    "supplier_concentration": (
        r"(?:supplier\s+concentration"
        r"|top\s+(?:\d+|ten|five|three|twenty|twenty[- ]five)\s+suppliers?"
        r"|dependent?\s+on\s+(?:our\s+)?"
        r"(?:key|major|top|significant|limited\s+number\s+of)\s+suppliers?)"
    ),
    "promoter_pledge_narrow": (
        r"(?:promoter[s]?[\'\u2019]?s?\s+(?:equity\s+)?shares?"
        r"\s+(?:have\s+been\s+|being\s+|are\s+)?pledged"
        r"|pledge\s+of\s+(?:the\s+|our\s+)?promoter[s]?[\'\u2019]?s?"
        r"\s+(?:shares?|equity))"
    ),
    "promoter_pledge_broad": r"pledg",
    "going_concern": r"going\s+concern",
    "auditor_qualification": (
        r"(?:auditor[s]?[\'\u2019]?s?\s+(?:qualification|observation"
        r"|remark|opinion|emphasis\s+of\s+matter|adverse\s+remark)"
        r"|qualified\s+(?:audit|opinion|report)"
        r"|emphasis\s+of\s+matter)"
    ),
    "contingent_liabilities": r"contingent\s+liabilit",
    "pending_approvals": r"pending\s+approval",
    "related_party": r"related\s+part(?:y|ies)\s+transaction",
    "litigation_general": (
        r"(?:pending\s+(?:legal\s+)?(?:proceedings?|litigation|cases?)"
        r"|outstanding\s+(?:legal\s+)?(?:proceedings?|litigation)"
        r"|material\s+(?:legal\s+)?(?:proceedings?|litigation))"
    ),
}

_COMPILED_CONCEPTS = {
    name: re.compile(pat, flags=re.IGNORECASE)
    for name, pat in CONCEPT_PATTERNS.items()
}


def count_concept_hits(text: str) -> dict[str, int]:
    """Count regex matches per concept."""
    return {
        f"n_{name}": len(pat.findall(text))
        for name, pat in _COMPILED_CONCEPTS.items()
    }


# ---------------------------------------------------------------------------
# Rupee-amount-in-context (crude version of Phase 7 extraction)
# ---------------------------------------------------------------------------
#
# For each concept where a ₹ amount is expected, count how many ₹ amounts
# appear within a 200-character window of the concept keyword. This is the
# regex baseline the LLM extraction must beat (candidate SQ4 baseline).

NUMERIC_CONTEXT_CONCEPTS: dict[str, tuple[str, int]] = {
    "rupee_near_litigation": (
        r"litigation|proceedings?|show[- ]cause|criminal", 200
    ),
    "rupee_near_contingent": (r"contingent\s+liabilit", 200),
    "rupee_near_related_party": (r"related\s+part(?:y|ies)", 200),
}

_COMPILED_NUMERIC_CONCEPTS = {
    name: (re.compile(pat, flags=re.IGNORECASE), window)
    for name, (pat, window) in NUMERIC_CONTEXT_CONCEPTS.items()
}

# Rupee amount: ₹ | Rs. | INR, then digits (with , and .), then unit.
RUPEE_AMOUNT = re.compile(
    r"(?:\u20b9|Rs\.?|INR)\s*[\d,]+(?:\.\d+)?\s*"
    r"(?:million|crore|lakh|lakhs|billion)",
    flags=re.IGNORECASE,
)


def count_numeric_in_context(text: str) -> dict[str, int]:
    """Count ₹ amounts within a window of each concept keyword."""
    out: dict[str, int] = {}
    for name, (pat, window) in _COMPILED_NUMERIC_CONCEPTS.items():
        count = 0
        for m in pat.finditer(text):
            start = max(0, m.start() - window)
            end = min(len(text), m.end() + window)
            count += len(RUPEE_AMOUNT.findall(text[start:end]))
        out[f"n_{name}"] = count
    return out


# ---------------------------------------------------------------------------
# Regex self-tests (fail loud on regressions)
# ---------------------------------------------------------------------------
def _self_test() -> None:
    """Assert the numbered-item detector catches known patterns."""
    samples = {
        "heading_bold": "# **_2. Our success..._**\n",
        "heading_plain": "# 3. Something\n",
        "inline_bold_italic": "**_1. First item_**\n",
        "inline_bold_plain": "**4.** Content\n",
        "blockquote_bold": "> **_45. Political factors..._**\n",
        "plain_ocr": "5. Something at start of line\n",
    }
    for label, text in samples.items():
        info = count_numbered_items(text)
        assert info["n_items"] >= 1, (
            f"Numbered-item detector missed pattern '{label}': {text!r}"
        )

    # Concept regex smoke tests
    smoke = "The company received a show-cause notice from SEBI in 2023."
    hits = count_concept_hits(smoke.lower())
    assert hits["n_regulatory_action"] >= 1, "regulatory_action regex broken"

    # Rupee amount
    amount_text = "outstanding litigation of \u20b9 1,273.70 million"
    ctx = count_numeric_in_context(amount_text.lower())
    assert ctx["n_rupee_near_litigation"] >= 1, (
        "rupee-in-context detector broken"
    )


# ---------------------------------------------------------------------------
# Pipeline: load master, read markdowns, compute per-IPO summary
# ---------------------------------------------------------------------------
def build_summary() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read all inputs and return (summary_df, master_df).

    summary_df has one row per IPO with all measurements. master_df is
    returned so downstream steps can access columns we didn't copy over.
    """
    master = pd.read_csv(MASTER_CSV)
    log = pd.read_csv(LOG_CSV)

    master["file_stem"] = master["company"].apply(company_to_stem)
    master["md_path"] = master["file_stem"].apply(
        lambda s: RISK_DIR / f"{s}.md"
    )

    # Existence check. Fail hard in production; warn in dev.
    exists = master["md_path"].apply(Path.exists)
    n_missing = int((~exists).sum())
    if n_missing:
        missing_list = master.loc[~exists, "file_stem"].tolist()
        print(
            f"[WARN] {n_missing} .md file(s) not found on disk. "
            f"Processing the {int(exists.sum())} available files.",
            file=sys.stderr,
        )
        print(f"       Missing stems (first 5): {missing_list[:5]}",
              file=sys.stderr)
        master = master[exists].copy()

    print(f"Processing {len(master)} risk-section files...")

    rows = []
    for _, m_row in master.iterrows():
        stem = m_row["file_stem"]
        try:
            text = m_row["md_path"].read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = m_row["md_path"].read_text(encoding="latin-1")

        chars, words = compute_length(text)
        num_info = count_numbered_items(text)
        concept_hits = count_concept_hits(text.lower())
        numeric_hits = count_numeric_in_context(text.lower())

        row = {
            "company": m_row["company"],
            "year": int(m_row["year"]),
            "listing_date": m_row["listing_date"],
            "first_day_return": m_row["first_day_return"],
            "file_stem": stem,
            "chars": chars,
            "words": words,
            "n_numbered_items": num_info["n_items"],
            "max_item_number": num_info["max_number"],
            "n_sequence_gaps": num_info["n_gaps"],
            "sequence_gaps": num_info["gaps"],
            "is_ocr": stem == OCR_FILE_STEM,
            **concept_hits,
            **numeric_hits,
        }
        rows.append(row)

    df = pd.DataFrame(rows)

    # Attach extraction status from the log
    log_slim = log[["filename", "status"]].copy()
    log_slim["file_stem"] = log_slim["filename"].str.replace(
        r"\.pdf$", "", regex=True
    )
    df = df.merge(
        log_slim[["file_stem", "status"]], on="file_stem", how="left"
    )
    df.rename(columns={"status": "extraction_status"}, inplace=True)

    # Group patched extractions under a coarse category for plotting
    df["extraction_family"] = df["extraction_status"].apply(_status_family)

    return df, master


def _status_family(status: str) -> str:
    if pd.isna(status):
        return "unknown"
    if status == "ok":
        return "ok"
    if status.startswith("ok_"):
        return "ok_patched"
    if "ocr" in status.lower():
        return "ocr"
    return "other"


# ---------------------------------------------------------------------------
# Analysis 1: Length distribution
# ---------------------------------------------------------------------------
def length_distribution(df: pd.DataFrame) -> None:
    """Descriptive stats and plots for chars/words."""
    stats_overall = df[["chars", "words"]].describe(
        percentiles=[0.05, 0.25, 0.5, 0.75, 0.95]
    ).round(1)
    stats_overall.to_csv(OUT_TABLES / "length_summary_overall.csv")

    stats_by_year = (
        df.groupby("year")[["chars", "words"]]
        .agg(["count", "mean", "median", "std", "min", "max"])
        .round(1)
    )
    stats_by_year.to_csv(OUT_TABLES / "length_summary_by_year.csv")

    stats_by_status = (
        df.groupby("extraction_family")[["chars", "words"]]
        .agg(["count", "mean", "median", "std"])
        .round(1)
    )
    stats_by_status.to_csv(OUT_TABLES / "length_summary_by_status.csv")

    # Plot 1: overall histogram of words
    fig, ax = plt.subplots(figsize=(9, 5))
    non_ocr = df[~df["is_ocr"]]
    sns.histplot(
        data=non_ocr, x="words", bins=40, kde=True, ax=ax, color="#3b7dd8"
    )
    if df["is_ocr"].any():
        ocr_words = df.loc[df["is_ocr"], "words"].iloc[0]
        ax.axvline(
            ocr_words, color="crimson", linestyle="--",
            label=f"OCR file ({ocr_words:,} words)"
        )
        ax.legend()
    ax.set(
        title="Risk-section word count distribution (n={})".format(len(df)),
        xlabel="Word count (markdown stripped)",
        ylabel="Number of prospectuses",
    )
    fig.savefig(OUT_FIGURES / "length_distribution_overall.png")
    plt.close(fig)

    # Plot 2: violin by year
    fig, ax = plt.subplots(figsize=(11, 5.5))
    sns.violinplot(
        data=df, x="year", y="words", inner="quartile",
        ax=ax, color="#3b7dd8"
    )
    sns.stripplot(
        data=df[df["is_ocr"]], x="year", y="words",
        color="crimson", size=8, marker="X", ax=ax, label="OCR"
    )
    ax.set(
        title="Risk-section word count by listing year",
        xlabel="Listing year",
        ylabel="Word count",
    )
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(handles=handles[:1], labels=labels[:1])
    fig.savefig(OUT_FIGURES / "length_distribution_by_year.png")
    plt.close(fig)

    # Plot 3: box by extraction family
    fig, ax = plt.subplots(figsize=(8, 5))
    order = ["ok", "ok_patched", "ocr", "other"]
    order = [o for o in order if o in df["extraction_family"].unique()]
    sns.boxplot(
        data=df, x="extraction_family", y="words", order=order, ax=ax,
        color="#3b7dd8"
    )
    ax.set(
        title="Word count by extraction strategy",
        xlabel="Extraction family",
        ylabel="Word count",
    )
    fig.savefig(OUT_FIGURES / "length_distribution_by_status.png")
    plt.close(fig)

    print(
        "  Length: median {:,.0f} words, IQR {:,.0f}-{:,.0f}, range {:,}-{:,}"
        .format(
            df["words"].median(),
            df["words"].quantile(0.25),
            df["words"].quantile(0.75),
            df["words"].min(),
            df["words"].max(),
        )
    )


# ---------------------------------------------------------------------------
# Analysis 2: Numbered items
# ---------------------------------------------------------------------------
def numbered_items(df: pd.DataFrame) -> None:
    """Distribution of numbered risk items."""
    stats = df[["n_numbered_items", "max_item_number", "n_sequence_gaps"]] \
        .describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95]).round(1)
    stats.to_csv(OUT_TABLES / "numbered_items_summary.csv")

    by_year = df.groupby("year")["n_numbered_items"].agg(
        ["count", "mean", "median", "std", "min", "max"]
    ).round(1)
    by_year.to_csv(OUT_TABLES / "numbered_items_by_year.csv")

    # Diagnostic: files with sequence gaps or zero items
    problem_mask = (df["n_sequence_gaps"] > 0) | (df["n_numbered_items"] == 0)
    problem = df.loc[
        problem_mask,
        [
            "company", "year", "file_stem", "extraction_status",
            "n_numbered_items", "max_item_number", "n_sequence_gaps",
            "sequence_gaps",
        ],
    ].sort_values("n_sequence_gaps", ascending=False)
    problem.to_csv(
        OUT_TABLES / "numbered_items_diagnostic.csv", index=False
    )

    # Plot: violin by year
    fig, ax = plt.subplots(figsize=(11, 5.5))
    sns.violinplot(
        data=df, x="year", y="n_numbered_items", inner="quartile",
        ax=ax, color="#7fb069"
    )
    ax.set(
        title="Number of numbered risk items per prospectus, by year",
        xlabel="Listing year",
        ylabel="Numbered risk items",
    )
    fig.savefig(OUT_FIGURES / "numbered_items_by_year.png")
    plt.close(fig)

    print(
        "  Numbered items: median {:.0f}, range {}-{}, "
        "{} files with sequence gaps, {} files with zero detected"
        .format(
            df["n_numbered_items"].median(),
            int(df["n_numbered_items"].min()),
            int(df["n_numbered_items"].max()),
            int((df["n_sequence_gaps"] > 0).sum()),
            int((df["n_numbered_items"] == 0).sum()),
        )
    )


# ---------------------------------------------------------------------------
# Analysis 3: Concept prevalence
# ---------------------------------------------------------------------------
def concept_prevalence(df: pd.DataFrame) -> None:
    """Hit rate + median hits per concept, overall and by year."""
    concept_cols = [c for c in df.columns if c.startswith("n_") and c not in {
        "n_numbered_items", "n_sequence_gaps"
    }]

    # Overall: hit rate = fraction of files with >=1 hit; median hits among hits
    rows = []
    for c in concept_cols:
        s = df[c]
        hit_mask = s > 0
        rows.append({
            "concept": c.removeprefix("n_"),
            "hit_rate": round(hit_mask.mean(), 3),
            "n_files_with_hit": int(hit_mask.sum()),
            "median_hits_when_hit": (
                float(s[hit_mask].median()) if hit_mask.any() else 0.0
            ),
            "max_hits": int(s.max()),
        })
    prevalence = pd.DataFrame(rows).sort_values(
        "hit_rate", ascending=False
    )
    prevalence.to_csv(
        OUT_TABLES / "concept_prevalence_overall.csv", index=False
    )

    # By year: hit rate per concept per year
    year_rows = []
    for year, g in df.groupby("year"):
        for c in concept_cols:
            year_rows.append({
                "year": year,
                "concept": c.removeprefix("n_"),
                "hit_rate": round((g[c] > 0).mean(), 3),
                "n_files": len(g),
            })
    by_year = pd.DataFrame(year_rows)
    by_year_wide = by_year.pivot(
        index="concept", columns="year", values="hit_rate"
    )
    by_year_wide.to_csv(OUT_TABLES / "concept_prevalence_by_year.csv")

    # Figure: overall hit rate bar chart
    fig, ax = plt.subplots(figsize=(9, 6))
    plot_df = prevalence.sort_values("hit_rate")
    ax.barh(plot_df["concept"], plot_df["hit_rate"], color="#3b7dd8")
    ax.axvline(0.05, color="grey", linestyle="--", alpha=0.5,
               label="5% floor")
    ax.axvline(0.95, color="grey", linestyle="--", alpha=0.5,
               label="95% ceiling")
    ax.set(
        title="Concept hit rate across the corpus (n={})".format(len(df)),
        xlabel="Fraction of files with at least one hit",
    )
    ax.legend(loc="lower right")
    fig.savefig(OUT_FIGURES / "concept_prevalence.png")
    plt.close(fig)

    # Figure: heatmap by year
    fig, ax = plt.subplots(figsize=(10, 7))
    sns.heatmap(
        by_year_wide, annot=True, fmt=".2f", cmap="Blues",
        cbar_kws={"label": "Hit rate"}, ax=ax, vmin=0, vmax=1
    )
    ax.set(
        title="Concept hit rate by listing year",
        xlabel="Listing year",
        ylabel="Concept",
    )
    fig.savefig(OUT_FIGURES / "concept_prevalence_by_year.png")
    plt.close(fig)

    print("  Concept prevalence (top 5 by hit rate):")
    for _, r in prevalence.head(5).iterrows():
        print("    {:35s} hit_rate={:.2f}  median_hits={:.0f}".format(
            r["concept"], r["hit_rate"], r["median_hits_when_hit"]
        ))
    print("  Concept prevalence (bottom 3 by hit rate):")
    for _, r in prevalence.tail(3).iterrows():
        print("    {:35s} hit_rate={:.2f}".format(
            r["concept"], r["hit_rate"]
        ))


# ---------------------------------------------------------------------------
# Analysis 4: Length vs return (LEAKAGE-CONTROLLED)
# ---------------------------------------------------------------------------
def length_vs_return(df: pd.DataFrame) -> None:
    """Spearman correlation between word count and first_day_return.

    Computed on year <= 2024 ONLY (train + val). Never on test.
    """
    train_val = df[df["year"].isin(TRAIN_VAL_YEARS)].copy()
    assert (train_val["year"] <= 2024).all(), (
        "LEAKAGE GUARD FAILED: test-year rows leaked into length-vs-return"
    )

    valid = train_val.dropna(subset=["first_day_return", "words"])
    rho, pval = spearmanr(valid["words"], valid["first_day_return"])

    result = pd.DataFrame([{
        "n_train_val": len(valid),
        "spearman_rho": round(float(rho), 4),
        "p_value": float(pval),
        "note": (
            "Computed on year <= 2024 only (train + val). Test rows "
            "(2025-2026) excluded to preserve leakage discipline."
        ),
    }])
    result.to_csv(OUT_TABLES / "length_return_correlation.csv", index=False)

    # Scatter plot with regression line (train+val only, colored)
    fig, ax = plt.subplots(figsize=(9, 6))
    sns.scatterplot(
        data=valid, x="words", y="first_day_return",
        hue="year", palette="viridis", ax=ax, alpha=0.7
    )
    # OLS fit line for visual context (not a formal test — Spearman is the test)
    lr = linregress(valid["words"], valid["first_day_return"])
    xs = np.linspace(valid["words"].min(), valid["words"].max(), 100)
    ax.plot(
        xs, lr.slope * xs + lr.intercept,
        color="black", linewidth=1.2, linestyle="--",
        label=f"OLS fit (slope={lr.slope:.2e})"
    )
    ax.axhline(0, color="grey", linewidth=0.5)
    ax.set(
        title=(
            f"Word count vs first-day return (train+val only, n={len(valid)})"
            f"\nSpearman rho = {rho:+.3f} (p = {pval:.2e})"
        ),
        xlabel="Risk-section word count",
        ylabel="First-day return",
    )
    ax.legend(loc="upper right")
    fig.savefig(OUT_FIGURES / "length_vs_return.png")
    plt.close(fig)

    print(
        "  Length vs return (train+val, n={}): Spearman rho={:+.3f}, p={:.2e}"
        .format(len(valid), rho, pval)
    )


# ---------------------------------------------------------------------------
# Analysis 5: Temporal vocabulary drift
# ---------------------------------------------------------------------------
#
# Uses TF-IDF with unigrams + bigrams. Documents are pooled per year;
# top-30 highest-TF-IDF n-grams reported per year. Custom stopwords
# extend sklearn's English list with Indian regulatory jargon that
# would otherwise dominate every year.

REGULATORY_STOPWORDS = frozenset({
    "company", "companies", "offer", "offering", "prospectus", "drhp", "rhp",
    "equity", "shares", "share", "business", "financial", "condition",
    "conditions", "material", "materially", "results", "operations",
    "operation", "may", "us", "would", "could", "shall", "including",
    "including", "such", "certain", "also", "well", "part", "time",
    "period", "date", "dated", "respect", "respective", "respectively",
    "risk", "risks", "factor", "factors", "adverse", "adversely",
    "affect", "affected", "affects", "affecting", "impact", "impacts",
    "loss", "losses", "cash", "flows", "flow", "prospects", "prospective",
    "investor", "investors", "investment", "investments", "regulation",
    "regulations", "regulatory", "law", "laws", "act", "acts", "section",
    "sections", "page", "pages", "fiscal", "fiscals", "year", "years",
    "annual", "operations", "revenues", "revenue", "profit", "profits",
    "loss", "reserves", "capital", "fund", "funds", "amount", "amounts",
    "million", "millions", "crore", "crores", "lakh", "lakhs", "rupees",
    "rs", "inr", "\u20b9", "board", "directors", "director", "management",
    "managements", "employees", "employee", "operations", "operational",
    "india", "indian", "state", "states", "government", "central",
    "public", "listed", "listing", "issue", "issued", "issuance",
    "subject", "compliance", "comply", "compliant", "requirements",
    "required", "require", "requires", "including", "provided", "provide",
    "provides", "note", "notes", "see", "described", "described",
    "market", "markets", "product", "products", "service", "services",
    "customer", "customers", "supplier", "suppliers", "process",
    "processes", "sale", "sales", "further", "additional",
})


def temporal_vocabulary(df: pd.DataFrame, master: pd.DataFrame) -> None:
    """Top TF-IDF n-grams per listing year.

    OCR file is excluded (its noise distribution differs from
    pymupdf4llm outputs and would contaminate the vocabulary signal).
    """
    non_ocr = df[~df["is_ocr"]].copy()
    year_texts: dict[int, list[str]] = {}

    for _, row in non_ocr.iterrows():
        stem = row["file_stem"]
        path = RISK_DIR / f"{stem}.md"
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="latin-1")
        clean = strip_markdown(text).lower()
        year_texts.setdefault(int(row["year"]), []).append(clean)

    # One "document" per year (pooled)
    years_sorted = sorted(year_texts.keys())
    corpus = [" ".join(year_texts[y]) for y in years_sorted]

    # sklearn's English stopwords + our custom regulatory list
    stop_words = list(ENGLISH_STOP_WORDS | REGULATORY_STOPWORDS)

    vec = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=1,
        max_df=1.0,  # per-year pooling, so max_df across n=len(years) is fine
        stop_words=stop_words,
        max_features=5000,
        token_pattern=r"(?u)\b[a-z][a-z]+\b",  # letters only, len>=2
    )
    X = vec.fit_transform(corpus)
    vocab = np.array(vec.get_feature_names_out())

    rows = []
    for i, year in enumerate(years_sorted):
        row_arr = X[i].toarray().ravel()
        top_idx = np.argsort(row_arr)[::-1][:30]
        for rank, idx in enumerate(top_idx, start=1):
            if row_arr[idx] == 0:
                break
            rows.append({
                "year": year,
                "rank": rank,
                "ngram": vocab[idx],
                "tfidf": round(float(row_arr[idx]), 4),
            })
    ngrams_df = pd.DataFrame(rows)
    ngrams_df.to_csv(OUT_TABLES / "top_ngrams_by_year.csv", index=False)

    # Print top 5 per year to console
    print("  Top-5 distinctive n-grams per year (TF-IDF):")
    for year in years_sorted:
        top5 = ngrams_df[ngrams_df["year"] == year].head(5)["ngram"].tolist()
        print(f"    {year}: {', '.join(top5)}")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def main() -> int:
    print("=" * 72)
    print("Phase 6 EDA: risk-section corpus")
    print("=" * 72)

    _self_test()
    print("[OK] Regex self-tests passed")

    df, master = build_summary()
    df.to_csv(OUT_ARTIFACT, index=False)
    print(f"[OK] Wrote per-IPO summary: {OUT_ARTIFACT}")
    print(f"     shape: {df.shape}")

    print("\n--- Analysis 1: length distribution ---")
    length_distribution(df)

    print("\n--- Analysis 2: numbered items ---")
    numbered_items(df)

    print("\n--- Analysis 3: concept prevalence ---")
    concept_prevalence(df)

    print("\n--- Analysis 4: length vs return (train+val only) ---")
    length_vs_return(df)

    print("\n--- Analysis 5: temporal vocabulary drift ---")
    temporal_vocabulary(df, master)

    print("\n" + "=" * 72)
    print("Done.")
    print(f"  Artifact: {OUT_ARTIFACT}")
    print(f"  Tables:   {OUT_TABLES}")
    print(f"  Figures:  {OUT_FIGURES}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())