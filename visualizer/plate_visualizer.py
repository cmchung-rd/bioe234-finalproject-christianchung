"""
visualizer/plate_visualizer.py
================================
Render individual 96-well plates as heatmaps and well-volume timeseries (Christian Chung).
"""

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import Normalize, LinearSegmentedColormap
from matplotlib.figure import Figure
import numpy as np

from .state_tracker import DeckSnapshot
from .log_parser import ParsedProtocol

_BG    = "#FFFFFF"
_PANEL = "#F0F2F7"
_BORDER = "#C4C9D8"
_TEXT  = "#1E2130"
_DIM   = "#6B7280"
_BLUE  = "#2563EB"
_RED   = "#DC2626"
_GREEN = "#16A34A"

CMAP_VOLUME = LinearSegmentedColormap.from_list(
    "ot2vol",
    ["#FFFFFF", "#DBEAFE", "#93C5FD", "#3B82F6", "#1E3A8A"],
    N=256,
)

ROWS = list("ABCDEFGH")
COLS = list(range(1, 13))


def render_plate(snapshot: DeckSnapshot, slot: str, protocol: ParsedProtocol,
                 title_override: str | None = None, figsize: tuple = (11, 4)) -> Figure:
    max_vol  = snapshot.slot_max_volumes.get(slot, 200.0)
    lw_name  = protocol.slot_labware.get(slot, f"Slot {slot}")

    vol_grid  = np.zeros((8, 12), dtype=float)
    for r_idx, row_letter in enumerate(ROWS):
        for c_idx, col_num in enumerate(COLS):
            well = f"{row_letter}{col_num}"
            vol_grid[r_idx, c_idx] = snapshot.well_volumes.get((slot, well), 0.0)

    fill_grid = np.clip(vol_grid / max_vol if max_vol > 0 else vol_grid, 0.0, 1.0)

    fig, ax = plt.subplots(figsize=figsize, facecolor=_BG)
    ax.set_facecolor(_BG)

    im = ax.imshow(fill_grid, cmap=CMAP_VOLUME, vmin=0, vmax=1,
                   aspect="auto", interpolation="nearest")

    for r_idx in range(8):
        for c_idx in range(12):
            vol  = vol_grid[r_idx, c_idx]
            fill = fill_grid[r_idx, c_idx]
            if vol > 0.5:
                txt_color = "white" if fill > 0.5 else _TEXT
                label = f"{vol:.0f}" if vol < 1000 else f"{vol/1000:.1f}k"
                ax.text(c_idx, r_idx, label, ha="center", va="center",
                        fontsize=6.5, color=txt_color, fontweight="bold", fontfamily="monospace")

    liquid_map = getattr(protocol, "liquid_map", {})
    liquid_legend: dict = {}
    if liquid_map:
        import matplotlib.colors as mcolors
        for (s, w), liq in liquid_map.items():
            if s != slot:
                continue
            try:
                r_idx = ROWS.index(w[0].upper())
                c_idx = int(w[1:]) - 1
                rect = plt.Rectangle((c_idx - 0.5, r_idx - 0.5), 1, 1,
                                     color=liq["color"], alpha=0.35, zorder=2)
                ax.add_patch(rect)
                liquid_legend[liq["name"]] = liq["color"]
            except (ValueError, IndexError):
                pass
        if liquid_legend:
            patches = [mpatches.Patch(color=c, alpha=0.7, label=n) for n, c in liquid_legend.items()]
            ax.legend(handles=patches, fontsize=7, loc="lower right",
                      facecolor=_PANEL, edgecolor=_BORDER, labelcolor=_TEXT)

    if snapshot.active_slot == slot and snapshot.active_well:
        w = snapshot.active_well
        if len(w) >= 2 and w[0].upper() in ROWS:
            r_idx = ROWS.index(w[0].upper())
            c_idx = int(w[1:]) - 1
            rect = plt.Rectangle((c_idx - 0.5, r_idx - 0.5), 1, 1,
                                  fill=False, edgecolor=_BLUE, linewidth=2.5, zorder=5)
            ax.add_patch(rect)

    ax.set_yticks(range(8))
    ax.set_yticklabels(ROWS, color=_TEXT, fontsize=9, fontfamily="monospace")
    ax.yaxis.set_tick_params(length=0)
    ax.set_xticks(range(12))
    ax.set_xticklabels([str(c) for c in COLS], color=_TEXT, fontsize=9, fontfamily="monospace")
    ax.xaxis.set_tick_params(length=0)
    ax.xaxis.set_ticks_position("top")
    ax.xaxis.set_label_position("top")
    for spine in ax.spines.values():
        spine.set_edgecolor(_BORDER)
        spine.set_linewidth(0.8)

    if title_override:
        title = title_override
    else:
        step_label = (f"Step {snapshot.step_index}" if snapshot.step_index >= 0 else "Initial State")
        title = f"Slot {slot}: {lw_name}  [{step_label}]"
    ax.set_title(title, color=_TEXT, fontsize=9, pad=6, fontfamily="monospace")

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.01)
    cbar.set_label(f"Volume (µL)\nmax = {max_vol:.0f}", color=_TEXT, fontsize=7.5)
    cbar.ax.yaxis.set_tick_params(color=_TEXT)
    tick_fracs = [0.0, 0.25, 0.5, 0.75, 1.0]
    cbar.set_ticks(tick_fracs)
    cbar.set_ticklabels([f"{int(f * max_vol)}" for f in tick_fracs], color=_TEXT, fontsize=7)
    cbar.ax.set_facecolor(_BG)

    fig.tight_layout()
    return fig


def render_well_timeseries(snapshots: list, slot: str, well: str,
                           protocol: ParsedProtocol, figsize: tuple = (12, 3)) -> Figure:
    max_vol  = snapshots[-1].slot_max_volumes.get(slot, 200.0) if snapshots else 200.0
    lw_name  = protocol.slot_labware.get(slot, f"Slot {slot}")

    volumes = [s.well_volumes.get((slot, well), 0.0) for s in snapshots]
    x_vals  = list(range(len(snapshots)))

    step_map = {s.step_index: s for s in protocol.steps}
    asp_x, asp_y = [], []
    dis_x, dis_y = [], []
    for i, snap in enumerate(snapshots):
        if snap.step_index < 0:
            continue
        step = step_map.get(snap.step_index)
        if step and step.slot == slot and step.well == well:
            if step.action == "aspirate":
                asp_x.append(i); asp_y.append(volumes[i])
            elif step.action == "dispense":
                dis_x.append(i); dis_y.append(volumes[i])

    fig, ax = plt.subplots(figsize=figsize, facecolor=_BG)
    ax.set_facecolor(_BG)
    ax.step(x_vals, volumes, where="post", color=_BLUE, linewidth=1.8, label="Volume")
    ax.fill_between(x_vals, volumes, step="post", color=_BLUE, alpha=0.12)
    if asp_x:
        ax.scatter(asp_x, asp_y, marker="v", color=_RED, s=65, zorder=5, label="Aspirate")
    if dis_x:
        ax.scatter(dis_x, dis_y, marker="^", color=_GREEN, s=65, zorder=5, label="Dispense")
    ax.set_ylim(0, max_vol * 1.1)
    ax.set_xlim(0, max(len(volumes) - 1, 1))
    ax.set_xlabel("Snapshot index", color=_DIM, fontsize=8)
    ax.set_ylabel("Volume (µL)", color=_DIM, fontsize=8)
    ax.tick_params(colors=_TEXT, labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor(_BORDER)
        spine.set_linewidth(0.6)
    ax.set_title(f"Well {well} — Slot {slot}: {lw_name}", color=_TEXT, fontsize=9, fontfamily="monospace")
    ax.legend(fontsize=7.5, facecolor=_PANEL, edgecolor=_BORDER, labelcolor=_TEXT)
    ax.axhline(0, color=_DIM, linewidth=0.5, linestyle="--", alpha=0.4)
    fig.tight_layout()
    return fig
