"""Chart rendering for report documents (matplotlib, headless Agg backend).
Every function returns PNG bytes ready for docx.add_picture(). Kept visually
consistent with the reference report style: clean sans-serif, muted
categorical colors, light gridlines, direct value labels where there are few
enough points for them to stay legible."""
import matplotlib
matplotlib.use("Agg")

import io
from matplotlib import pyplot as plt

# Fixed categorical order -- never reassigned per-chart, so a series keeps
# the same color across every chart it appears in.
PALETTE = ["#2E75B6", "#ED7D31", "#2CA678", "#E8A33D", "#8E6BB0", "#C2694F"]
GRID_COLOR = "#D9D9D9"
TEXT_COLOR = "#333333"
POSITIVE = "#2CA678"
NEGATIVE = "#C2694F"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "text.color": TEXT_COLOR,
    "axes.edgecolor": GRID_COLOR,
    "axes.labelcolor": TEXT_COLOR,
    "xtick.color": TEXT_COLOR,
    "ytick.color": TEXT_COLOR,
    "axes.titleweight": "bold",
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})


def _finish(fig, footnote: str = None, top: float = None) -> bytes:
    if footnote:
        fig.text(0.01, 0.01, footnote, fontsize=8, color="#777777")
    buf = io.BytesIO()
    rect = (0, 0.04 if footnote else 0, 1, top if top else 1)
    fig.tight_layout(rect=rect)
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def line_chart(title: str, x_labels: list, series: dict, ylabel: str,
                footnote: str = None, annotations: list = None) -> bytes:
    """series: {label: [values]}, all aligned to x_labels.
    annotations: [{"index": i, "text": "..."}] -- labels a specific point."""
    n = len(series)
    # Long series labels (a product's full tracked name) wrap the legend onto
    # multiple rows rather than overflowing the figure in one wide row.
    ncol = 2 if (n > 2 or any(len(label) > 18 for label in series)) else max(n, 1)
    legend_rows = -(-n // ncol) if ncol else 1
    fig, ax = plt.subplots(figsize=(9, 4.2 + 0.3 * max(0, legend_rows - 1)))
    for i, (label, values) in enumerate(series.items()):
        ax.plot(x_labels, values, label=label, color=PALETTE[i % len(PALETTE)],
                linewidth=2, marker="o" if len(x_labels) <= 12 else None, markersize=4)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=13, loc="left", pad=28 + 16 * max(0, legend_rows - 1))
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    if n > 1:
        ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0, 1.02), ncol=ncol, fontsize=9.5)
    if len(x_labels) > 8:
        import math
        step = math.ceil(len(x_labels) / 8)
        ticks = list(range(0, len(x_labels), step))
        ax.set_xticks(ticks)
        ax.set_xticklabels([x_labels[i] for i in ticks], rotation=0)
    plt.setp(ax.get_xticklabels(), fontsize=9)

    for note in (annotations or []):
        idx = note["index"]
        first_series = next(iter(series.values()))
        if 0 <= idx < len(first_series):
            y = first_series[idx]
            ax.annotate(
                note["text"], xy=(idx, y), xytext=(0, 22), textcoords="offset points",
                fontsize=8.5, ha="center", color="#555555",
                arrowprops=dict(arrowstyle="-", color="#999999", lw=0.8),
            )

    return _finish(fig, footnote)


def grouped_bar_chart(title: str, categories: list, series: dict, ylabel: str,
                       footnote: str = None) -> bytes:
    """series: {label: [values]}, one value per category."""
    fig, ax = plt.subplots(figsize=(9, 4.2))
    n = len(series)
    width = 0.8 / max(n, 1)
    x = range(len(categories))
    for i, (label, values) in enumerate(series.items()):
        offsets = [xi + (i - (n - 1) / 2) * width for xi in x]
        ax.bar(offsets, values, width=width, label=label, color=PALETTE[i % len(PALETTE)])
    ax.set_xticks(list(x))
    ax.set_xticklabels(categories)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=13, loc="left", pad=28)
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    if n > 1:
        ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0, 1.02), ncol=n)
    return _finish(fig, footnote)


def signed_bar_chart(title: str, categories: list, values: list, ylabel: str,
                      footnote: str = None) -> bytes:
    """Single series, colored green/red by sign, with the value labeled directly
    above/below each bar -- used for the KEC differential chart."""
    fig, ax = plt.subplots(figsize=(9, 4.0))
    colors = [POSITIVE if v >= 0 else NEGATIVE for v in values]
    bars = ax.bar(categories, values, color=colors)
    ax.axhline(0, color="#999999", linewidth=0.8)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=13, loc="left", pad=14)
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for bar, v in zip(bars, values):
        offset = 0.3 if v >= 0 else -0.3
        va = "bottom" if v >= 0 else "top"
        ax.annotate(f"{v:+.2f}", xy=(bar.get_x() + bar.get_width() / 2, v),
                    xytext=(0, offset * 10), textcoords="offset points",
                    ha="center", va=va, fontsize=9, fontweight="bold", color=TEXT_COLOR)
    return _finish(fig, footnote)
