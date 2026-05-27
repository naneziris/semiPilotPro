#!/usr/bin/env python3
"""Generate docs/flow.png — the SemiPilot Pro pipeline diagram.

Design: top-to-bottom spine, no side panels, minimal annotations.
Re-run after changing the pipeline shape.
"""

from __future__ import annotations

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

# ---- Colors ---------------------------------------------------------------
C_BG = "#FFFFFF"
C_STEP = "#3B82F6"      # blue — pipeline steps
C_CRITIC = "#DC2626"    # red — critic gates
C_SYNC = "#F59E0B"      # amber — human sync
C_TERM = "#475569"      # slate — start/end
C_SCRIBE = "#7C3AED"    # purple — writes to wiki
C_TEXT = "#FFFFFF"
C_ANNOT = "#6B7280"     # gray — annotations
C_REJECT = "#DC2626"    # red — rejection loop
C_WIKI = "#0F766E"      # teal — wiki writes

# ---- Layout ---------------------------------------------------------------
FIG_W = 8.0
FIG_H = 13.2
CENTER_X = 4.0
BOX_W = 3.4
BOX_H = 0.7
ROW_GAP = 1.05  # vertical step between rows

# Rows (from top): label, y-position, color, right-side annotation
STEPS = [
    ("User Idea",                            12.0, C_TERM,   None),
    ("@refiner",                             10.8, C_STEP,   "writes requirements.md\n+ Impact Analysis"),
    ("@spec-critic   (GATE 1)",               9.6, C_CRITIC, "binary verdict\nagainst .wiki/"),
    ("Sync 1  ·  Dev approves spec",          8.5, C_SYNC,   None),
    ("@planner",                              7.4, C_STEP,   "writes\nimplementation-plan.md"),
    ("/implement-plan   (YAML rail)",         6.2, C_STEP,   "tests-first → lint → type\n→ tests → complexity"),
    ("@pattern-critic   (GATE 2)",            5.0, C_CRITIC, "binary verdict\nagainst the diff"),
    ("Sync 2  ·  Dev approves diff",          3.9, C_SYNC,   None),
    ("@scribe",                               2.8, C_SCRIBE, "updates .wiki/\n+ CHANGELOG"),
    ("Change Complete",                       1.7, C_TERM,   None),
]


def draw_box(ax, label, y, color, *, annotation=None):
    x = CENTER_X - BOX_W / 2
    box = FancyBboxPatch(
        (x, y - BOX_H / 2), BOX_W, BOX_H,
        boxstyle="round,pad=0.02,rounding_size=0.12",
        linewidth=0, facecolor=color,
    )
    ax.add_patch(box)
    ax.text(
        CENTER_X, y, label,
        ha="center", va="center",
        fontsize=12, fontweight="bold", color=C_TEXT,
    )
    if annotation:
        ax.text(
            CENTER_X + BOX_W / 2 + 0.15, y, annotation,
            ha="left", va="center",
            fontsize=8.5, color=C_ANNOT, style="italic",
        )


def draw_down_arrow(ax, y_top, y_bot):
    arr = FancyArrowPatch(
        (CENTER_X, y_top - BOX_H / 2),
        (CENTER_X, y_bot + BOX_H / 2),
        arrowstyle="-|>",
        mutation_scale=14,
        color="#1F2937",
        linewidth=1.6,
    )
    ax.add_patch(arr)


def draw_rejection_loop(ax, y_from, y_to, label):
    """Curved arrow on the LEFT going from a critic back to its retry target."""
    side_x = CENTER_X - BOX_W / 2 - 0.45
    # Down from critic edge to side rail
    ax.plot(
        [CENTER_X - BOX_W / 2, side_x],
        [y_from, y_from],
        color=C_REJECT, linewidth=1.3,
    )
    # Vertical up
    ax.plot(
        [side_x, side_x],
        [y_from, y_to],
        color=C_REJECT, linewidth=1.3, linestyle="--",
    )
    # Arrow back into target
    arr = FancyArrowPatch(
        (side_x, y_to),
        (CENTER_X - BOX_W / 2, y_to),
        arrowstyle="-|>",
        mutation_scale=12,
        color=C_REJECT,
        linewidth=1.3,
    )
    ax.add_patch(arr)
    # Label
    ax.text(
        side_x - 0.1, (y_from + y_to) / 2, label,
        ha="right", va="center",
        fontsize=8.5, color=C_REJECT, fontweight="bold",
        rotation=90,
    )


def draw_scribe_to_wiki(ax, y_scribe):
    """Inline note that @scribe is the only writer to .wiki/.

    Kept minimal — no separate box; the annotation column already says it.
    A small teal underline on the scribe box reinforces the role visually.
    """
    x = CENTER_X - BOX_W / 2
    ax.plot(
        [x, x + BOX_W],
        [y_scribe - BOX_H / 2 - 0.04, y_scribe - BOX_H / 2 - 0.04],
        color=C_WIKI, linewidth=2.5,
    )
    ax.text(
        CENTER_X, y_scribe - BOX_H / 2 - 0.16,
        "only writer to .wiki/",
        ha="center", va="top",
        fontsize=7.5, color=C_WIKI, style="italic",
    )


def main():
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=200)
    ax.set_xlim(0, FIG_W)
    ax.set_ylim(0, FIG_H)
    ax.set_facecolor(C_BG)
    fig.patch.set_facecolor(C_BG)
    ax.axis("off")

    # Title
    ax.text(
        CENTER_X, 12.95, "SemiPilot Pro — Pipeline",
        ha="center", va="center",
        fontsize=17, fontweight="bold", color="#0F172A",
    )
    ax.text(
        CENTER_X, 12.65, "Refine  →  Spec Gate  →  Plan  →  Implement  →  Pattern Gate  →  Scribe",
        ha="center", va="center",
        fontsize=9.5, color=C_ANNOT, style="italic",
    )

    # Boxes
    for label, y, color, annot in STEPS:
        draw_box(ax, label, y, color, annotation=annot)

    # Arrows between boxes
    for i in range(len(STEPS) - 1):
        draw_down_arrow(ax, STEPS[i][1], STEPS[i + 1][1])

    # Rejection loops — small, left side
    # Spec critic (row 2) rejection loops back to refiner (row 1)
    draw_rejection_loop(
        ax,
        y_from=STEPS[2][1],
        y_to=STEPS[1][1],
        label="REJECTED",
    )
    # Pattern critic (row 6) rejection loops back to implement-plan (row 5)
    draw_rejection_loop(
        ax,
        y_from=STEPS[6][1],
        y_to=STEPS[5][1],
        label="REJECTED  /fix-rejection",
    )

    # Scribe-writes-wiki marker (replaces the separate wiki box)
    draw_scribe_to_wiki(ax, STEPS[8][1])

    # Footer note
    ax.text(
        CENTER_X, 0.85,
        "Two human sync points per successful cycle. Critics return binary verdicts.\n"
        "On rejection: spec returns to @refiner; pattern returns to /fix-rejection.",
        ha="center", va="center",
        fontsize=8.5, color=C_ANNOT, style="italic",
    )

    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    out_path = "docs/flow.png"
    fig.savefig(out_path, dpi=200, bbox_inches="tight", facecolor=C_BG)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
