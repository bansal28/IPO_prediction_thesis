# Makefile for building the thesis PDF from Markdown sources.
#
# Requires pandoc (>= 2.14) and a LaTeX distribution (e.g. TeX Live or MacTeX)
# with the xelatex engine.
#
# Common usage:
#   make pdf         -- build the full thesis into build/thesis.pdf
#   make chapters    -- build each chapter as a standalone PDF
#   make clean       -- remove all generated files

# ---------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------
PANDOC        := pandoc
PDF_ENGINE    := xelatex
BUILD_DIR     := build
BIB           := references.bib

# Chapters, in the order they appear in the final PDF.
# Add later chapters (06_feature_engineering.md, ...) to this list as they
# are written.
CHAPTERS := \
  00_abstract.md \
  01_introduction.md \
  02_literature_review.md \
  03_data_collection.md \
  04_data_cleaning.md \
  05_exploratory_analysis.md \
  appendix_a_decisions_log.md \
  appendix_b_reproducibility.md

# Common pandoc options.
PANDOC_OPTS := \
  --pdf-engine=$(PDF_ENGINE) \
  --toc --toc-depth=2 \
  --number-sections \
  -V geometry:margin=1in \
  -V mainfont="DejaVu Serif" \
  -V monofont="DejaVu Sans Mono" \
  -V linestretch=1.15

# Add bibliography options only if references.bib exists.
ifneq ($(wildcard $(BIB)),)
  PANDOC_OPTS += --citeproc --bibliography=$(BIB)
endif

# ---------------------------------------------------------------
# Top-level targets
# ---------------------------------------------------------------
.PHONY: pdf chapters clean

pdf: $(BUILD_DIR)/thesis.pdf

$(BUILD_DIR)/thesis.pdf: $(CHAPTERS) | $(BUILD_DIR)
	$(PANDOC) $(PANDOC_OPTS) -o $@ $(CHAPTERS)

# Build each chapter as a standalone PDF (useful for supervisor review of
# one chapter at a time).
chapters: $(patsubst %.md,$(BUILD_DIR)/%.pdf,$(CHAPTERS))

$(BUILD_DIR)/%.pdf: %.md | $(BUILD_DIR)
	$(PANDOC) $(PANDOC_OPTS) -o $@ $<

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

clean:
	rm -rf $(BUILD_DIR)
