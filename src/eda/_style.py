"""
Shared plotting style + save helper for all EDA scripts.
Import this at the top of every src/eda/*.py:

    from _style import PAL, save_fig

Runs matplotlib in Agg mode (no interactive display needed).
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# Publication-friendly defaults
plt.rcParams.update({
    "figure.dpi":       100,
    "savefig.dpi":      300,
    "savefig.bbox":     "tight",
    "figure.facecolor": "white",
    "axes.facecolor":   "white",
    "axes.edgecolor":   "#333",
    "axes.grid":        True,
    "grid.alpha":       0.25,
    "grid.linestyle":   "--",
    "font.family":      "DejaVu Sans",
    "font.size":        10,
    "axes.titlesize":   11,
    "axes.labelsize":   10,
    "xtick.labelsize":  9,
    "ytick.labelsize":  9,
    "legend.fontsize":  9,
    "axes.spines.top":   False,
    "axes.spines.right": False,
})


# Colour palette (colourblind-safe, muted)
PAL = {
    "primary":  "#2E86AB",   # blue
    "accent":   "#E63946",   # red
    "positive": "#2A9D8F",   # teal
    "negative": "#E76F51",   # coral
    "neutral":  "#555555",
    "muted":    "#B0B0B0",
}


def save_fig(fig, name, out_dir):
    """Save a matplotlib figure as both 300-dpi PNG and vector PDF."""
    os.makedirs(out_dir, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(out_dir, f"{name}.{ext}"))