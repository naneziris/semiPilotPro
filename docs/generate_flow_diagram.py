#!/usr/bin/env python3
"""Generate the SemiPilot Pro flow diagram as a PNG.

Run: python3 generate_flow_diagram.py
Output: flow.png (alongside this script)
"""
from pathlib import Path

import matplotlib.patches as patches
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

# Colors
C_USER = "#1f77b4"
C_PROMPT = "#2ca02c"
C_AGENT = "#9467bd"
C_GATE = "#d62728"
C_WIKI = "#ff7f0e"
C_SKILL = "#17becf"
C_ARTIFACT = "#7f7f7f"
C_BG = "#fafafa"
C_TEXT = "#222222"


def box(ax, x, y, w, h, text, fc, fontsize=10, fontweight="normal", text_color="white"):
    rect = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.5,
        facecolor=fc,
        edgecolor=fc,
    )
    ax.add_patch(rect)
    ax.text(
        x + w / 2, y + h / 2, text,
        ha="center", va="center",
        fontsize=fontsize, fontweight=fontweight, color=text_color,
    )


def arrow(ax, x1, y1, x2, y2, color="#333333", lw=1.8, style="->", linestyle="solid"):
    arr = FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle=style,
        mutation_scale=18,
        linewidth=lw,
        color=color,
        linestyle=linestyle,
    )
    ax.add_patch(arr)


def sync_bar(ax, x, y, w, label):
    rect = patches.Rectangle(
        (x, y), w, 0.22,
        linewidth=1,
        facecolor="#fff7cc",
        edgecolor="#c9a227",
    )
    ax.add_patch(rect)
    ax.text(x + w / 2, y + 0.11, label, ha="center", va="center",
            fontsize=9.5, fontweight="bold", color="#7a5d00")


def main():
    # Wider canvas, better breathing room
    W, H = 22, 15
    fig, ax = plt.subplots(figsize=(W, H))
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.patch.set_facecolor(C_BG)

    # Title
    ax.text(W / 2, H - 0.5, "SemiPilot Pro — User Flow",
            ha="center", fontsize=22, fontweight="bold", color=C_TEXT)
    ax.text(W / 2, H - 1.0, "RPI + Critics + Scribe, anchored on the Karpathy Wiki",
            ha="center", fontsize=12, color="#666666", style="italic")

    # Horizontal legend at top
    legend_items = [
        (C_USER, "User"),
        (C_PROMPT, "Prompt (/slash)"),
        (C_AGENT, "Agent (@name)"),
        (C_GATE, "Critic Gate"),
        (C_SKILL, "Skill (#name)"),
        (C_WIKI, "Wiki file"),
        (C_ARTIFACT, "Artifact"),
    ]
    legend_y = H - 1.7
    item_w = 2.3
    total_w = item_w * len(legend_items)
    start_x = (W - total_w) / 2
    for i, (c, label) in enumerate(legend_items):
        x = start_x + i * item_w
        patch = patches.Rectangle((x, legend_y), 0.3, 0.25, facecolor=c, edgecolor=c)
        ax.add_patch(patch)
        ax.text(x + 0.5, legend_y + 0.12, label, fontsize=10, va="center", color="#333")

    # --- PIPELINE (center) ---
    cx = 11.0
    bw, bh = 5.2, 0.8

    # Stages (y descending)
    stages = [
        (12.3, C_USER,     "User Idea",                           "\"I want to add X\""),
        (11.0, C_PROMPT,   "1.  /refine-requirements",            "@refiner  •  Opus 4.6"),
        (9.9,  C_ARTIFACT, ".github/requirements/requirements.md","(intermediate artifact)"),
        (8.6,  C_GATE,     "GATE 1 — @spec-critic",               "Opus 4.6  •  binary APPROVED / REJECTED"),
        (7.05, C_PROMPT,   "2.  /create-implementation-plan",     "@planner  •  Sonnet 4.6"),
        (5.95, C_ARTIFACT, ".github/implementation-plan.md",      "(intermediate artifact)"),
        (4.85, C_PROMPT,   "3.  /implement-plan  (YAML rail)",    "draft code + tests"),
        (3.3,  C_GATE,     "GATE 2 — @pattern-critic",            "Opus 4.6  •  diff + .wiki/ check"),
        (1.9,  C_AGENT,    "@scribe",                             "updates .wiki/  +  CHANGELOG"),
        (0.8,  C_USER,     "Change Complete",                     "merged + documented"),
    ]

    for y, color, label, sub in stages:
        box(ax, cx - bw / 2, y - bh / 2, bw, bh, label, color, fontsize=11.5, fontweight="bold")
        ax.text(cx, y - bh / 2 - 0.22, sub, ha="center", fontsize=9, color="#555", style="italic")

    # Arrows between stages
    stage_ys = [s[0] for s in stages]
    for i in range(len(stages) - 1):
        arrow(ax, cx, stage_ys[i] - bh / 2 - 0.04,
                  cx, stage_ys[i + 1] + bh / 2 + 0.04)

    # --- HUMAN SYNC BARS ---
    sync_bar(ax, cx - bw / 2 - 0.3, 7.82, bw + 0.6,
             "↕  HUMAN SYNC  —  Dev approves spec (or rejects)")
    sync_bar(ax, cx - bw / 2 - 0.3, 2.55, bw + 0.6,
             "↕  HUMAN SYNC  —  Dev approves diff (or rejects)")

    # --- REJECTION LOOPS (now on the right, away from skills column) ---
    ax.annotate(
        "REJECTED →\nback to\n/refine-requirements",
        xy=(cx + bw / 2 + 0.05, 8.6), xytext=(cx + bw / 2 + 1.8, 9.9),
        fontsize=9, color=C_GATE, ha="center", fontweight="bold",
        arrowprops=dict(arrowstyle="->", color=C_GATE, lw=1.3,
                        connectionstyle="arc3,rad=0.3"),
    )
    ax.annotate(
        "REJECTED →\nback to\n/implement-plan",
        xy=(cx + bw / 2 + 0.05, 3.3), xytext=(cx + bw / 2 + 1.8, 4.5),
        fontsize=9, color=C_GATE, ha="center", fontweight="bold",
        arrowprops=dict(arrowstyle="->", color=C_GATE, lw=1.3,
                        connectionstyle="arc3,rad=0.3"),
    )

    # --- RIGHT COLUMN: THE WIKI ---
    wx = 17.8
    ax.text(wx + 1.5, H - 2.6, ".wiki/  (Karpathy Memory)",
            ha="center", fontsize=13, fontweight="bold", color=C_WIKI)
    ax.text(wx + 1.5, H - 2.95, "Bootstrap once with  #wiki-init",
            ha="center", fontsize=9.5, style="italic", color="#666")

    wiki_files = [
        ("OVERVIEW.md",       "tech stack, purpose"),
        ("ARCH_DECISIONS.md", "ADRs — why X over Y"),
        ("DATA_MODELS.md",    "schemas, key types"),
        ("PATTERNS.md",       "naming, DI, tests"),
        ("DEPENDENCIES.md",   "current / banned libs"),
        ("API.md",            "public signatures"),
        ("CHANGELOG.md",      "user-facing diff log"),
    ]
    wiki_top = 11.8
    wiki_step = 0.75
    wiki_ys = {}
    for i, (name, desc) in enumerate(wiki_files):
        y = wiki_top - i * wiki_step
        wiki_ys[name] = y + 0.2
        box(ax, wx, y, 2.8, 0.5, name, C_WIKI, fontsize=9.5, fontweight="bold")
        ax.text(wx + 2.9, y + 0.25, desc, fontsize=9, va="center", color="#555")

    # Wiki read arrows (dashed)
    reads = [
        (11.0, "OVERVIEW.md"),        # refiner
        (11.0, "DATA_MODELS.md"),
        (11.0, "API.md"),
        (8.6, "ARCH_DECISIONS.md"),   # spec-critic
        (8.6, "DATA_MODELS.md"),
        (8.6, "DEPENDENCIES.md"),
        (7.05, "PATTERNS.md"),        # planner
        (7.05, "DATA_MODELS.md"),
        (4.85, "PATTERNS.md"),        # implementer
        (3.3, "PATTERNS.md"),         # pattern-critic
        (3.3, "DEPENDENCIES.md"),
        (3.3, "API.md"),
    ]
    for stage_y, wiki_name in reads:
        wy = wiki_ys[wiki_name]
        arrow(ax, cx + bw / 2 + 0.05, stage_y,
              wx - 0.05, wy,
              color="#ffb472", lw=0.8, linestyle=(0, (3, 3)))

    # Scribe WRITE arrow (solid, purple, prominent)
    write_arr = FancyArrowPatch(
        (cx + bw / 2 + 0.05, 1.9),
        (wx - 0.05, wiki_ys["CHANGELOG.md"]),
        arrowstyle="->",
        mutation_scale=20,
        linewidth=2.2,
        color=C_AGENT,
    )
    ax.add_patch(write_arr)
    ax.text(16.0, 3.5, "scribe\nwrites all", fontsize=9,
            color=C_AGENT, fontweight="bold", ha="center",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=C_AGENT))

    # --- LEFT COLUMN: SKILLS ---
    sx = 0.3
    ax.text(sx + 1.4, H - 2.6, "Skills  (callable anywhere)",
            ha="center", fontsize=13, fontweight="bold", color=C_SKILL)

    skills = [
        ("#wiki-init",     "scaffold .wiki/ on first run"),
        ("#code-analyzer", "cyclomatic complexity + thresholds"),
        ("#llm-wiki",      "concat wiki  |  FAISS query (opt-in)"),
        ("#project-map",   "monorepo package + dep table"),
    ]
    for i, (name, desc) in enumerate(skills):
        y = 11.8 - i * 0.9
        box(ax, sx, y, 2.5, 0.5, name, C_SKILL, fontsize=9.5, fontweight="bold")
        ax.text(sx + 0.05, y - 0.22, desc, fontsize=8.5, color="#555")

    # YAML rail callout (bottom-left)
    rail_x, rail_y = 0.3, 3.0
    rail_w, rail_h = 4.2, 5.2
    rect = FancyBboxPatch(
        (rail_x, rail_y), rail_w, rail_h,
        boxstyle="round,pad=0.05,rounding_size=0.1",
        linewidth=1.8,
        facecolor="#f0f7ff",
        edgecolor=C_PROMPT,
    )
    ax.add_patch(rect)
    ax.text(rail_x + rail_w / 2, rail_y + rail_h - 0.3,
            "/implement-plan  YAML rail",
            ha="center", fontsize=11, fontweight="bold", color=C_PROMPT)
    rail_steps = [
        "1.  read_plan",
        "2.  read_wiki_patterns",
        "3.  write_tests_first  (TDD red)",
        "4.  write_code",
        "5.  lint  ✦ hard block",
        "6.  type_check  ✦ hard block",
        "      └─ tsc --noEmit / mypy",
        "7.  unit_tests  ✦ hard block",
        "8.  complexity_check",
        "      └─ #code-analyzer",
        "9.  wiki_pattern_check",
        "10. submit → @pattern-critic",
    ]
    for i, step in enumerate(rail_steps):
        ax.text(rail_x + 0.2,
                rail_y + rail_h - 0.75 - i * 0.37,
                step, fontsize=8.5, color="#333", family="monospace")

    # Enforces arrow from rail box to implement-plan stage
    arr = FancyArrowPatch(
        (rail_x + rail_w, rail_y + rail_h * 0.55),
        (cx - bw / 2 - 0.05, 4.85),
        arrowstyle="->",
        mutation_scale=16,
        linewidth=1.4,
        color=C_PROMPT,
        linestyle=(0, (2, 2)),
    )
    ax.add_patch(arr)
    ax.text(rail_x + rail_w + 0.4, rail_y + rail_h * 0.55 + 0.25,
            "enforces", fontsize=9, color=C_PROMPT, style="italic")

    # Footnote
    ax.text(W / 2, 0.2,
            "Exactly 2 human sync points  •  Critics block (binary APPROVED/REJECTED)  •  "
            "Tests written before code  •  Scribe owns all .wiki/ writes",
            ha="center", fontsize=10, color="#555", style="italic")

    out = Path(__file__).parent / "flow.png"
    plt.savefig(out, dpi=160, bbox_inches="tight", facecolor=C_BG)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
