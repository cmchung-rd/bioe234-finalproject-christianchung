"""
visualizer/stats_visualizer.py
================================
Protocol statistics dashboard — four-panel summary figure (Christian Chung).
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.gridspec import GridSpec
from matplotlib.figure import Figure
import numpy as np

from .log_parser import ParsedProtocol
from .state_tracker import DeckSnapshot, is_tracked_plate

_BG     = "#FFFFFF"
_PANEL  = "#F0F2F7"
_BORDER = "#C4C9D8"
_ACCENT = "#2563EB"
_TEXT   = "#1E2130"
_DIM    = "#6B7280"

_ACTION_COLORS = {
    "aspirate": "#3B82F6", "dispense": "#16A34A",
    "pick_up_tip": "#F59E0B", "drop_tip": "#EF4444",
    "return_tip": "#FB923C", "blow_out": "#8B5CF6",
    "touch_tip": "#EC4899", "mix": "#06B6D4",
    "move": "#A3A3A3", "delay": "#6366F1",
    "pause": "#DC2626", "set_temperature": "#0EA5E9",
    "heater_shaker": "#10B981", "thermocycler": "#7C3AED",
    "note": "#E5E7EB", "unknown": "#D1D5DB",
}

CMAP_ACTIVITY = LinearSegmentedColormap.from_list(
    "activity", ["#FFFFFF", "#DBEAFE", "#3B82F6", "#1E3A8A"], N=256
)

ROWS = list("ABCDEFGH")
COLS = list(range(1, 13))


def render_stats_dashboard(protocol: ParsedProtocol, snapshots: list,
                           figsize: tuple = (16, 10)) -> Figure:
    fig = plt.figure(figsize=figsize, facecolor=_BG)
    gs = GridSpec(2, 3, figure=fig, hspace=0.50, wspace=0.38,
                  left=0.07, right=0.97, top=0.91, bottom=0.08)

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[0, 2])
    ax4 = fig.add_subplot(gs[1, :])

    _plot_volume_per_slot(ax1, protocol)
    _plot_action_breakdown(ax2, protocol)
    _plot_tip_timeline(ax3, snapshots)
    _plot_well_activity(ax4, protocol)

    n_known = sum(1 for s in protocol.steps if s.action != "unknown")
    total_vol = sum(s.volume_ul or 0 for s in protocol.steps if s.action == "dispense")

    fig.suptitle(
        f"{protocol.protocol_name}  ·  Statistics Dashboard"
        f"  ·  {n_known} steps  ·  {total_vol:.0f} µL dispensed",
        color=_TEXT, fontsize=12, y=0.975, fontfamily="monospace",
    )
    return fig


def _style_ax(ax):
    ax.set_facecolor(_PANEL)
    for spine in ax.spines.values():
        spine.set_edgecolor(_BORDER)
        spine.set_linewidth(0.7)
    ax.tick_params(colors=_TEXT, labelsize=8)
    ax.xaxis.label.set_color(_DIM)
    ax.yaxis.label.set_color(_DIM)


def _plot_volume_per_slot(ax, protocol):
    vol_per_slot: dict = {}
    for step in protocol.steps:
        if step.action == "dispense" and step.slot:
            vol_per_slot[step.slot] = vol_per_slot.get(step.slot, 0.0) + (step.volume_ul or 0.0)

    if not vol_per_slot:
        ax.text(0.5, 0.5, "No dispense data", transform=ax.transAxes,
                ha="center", va="center", color=_DIM, fontsize=9)
        ax.set_title("Volume per Slot", color=_TEXT, fontsize=9)
        return

    slot_key = lambda s: (0, int(s)) if s.isdigit() else (1, s)
    slots  = sorted(vol_per_slot, key=slot_key)
    values = [vol_per_slot[s] for s in slots]

    bars = ax.bar(slots, values, color=_ACCENT, alpha=0.85, edgecolor=_BORDER, linewidth=0.5)
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.015,
                f"{val:.0f}", ha="center", va="bottom", fontsize=7, color=_TEXT)

    ax.set_xlabel("Deck slot", fontsize=8)
    ax.set_ylabel("Total µL dispensed", fontsize=8)
    ax.set_title("Volume Dispensed per Slot", color=_TEXT, fontsize=9, fontfamily="monospace")
    _style_ax(ax)


def _plot_action_breakdown(ax, protocol):
    counts: dict = {}
    for step in protocol.steps:
        counts[step.action] = counts.get(step.action, 0) + 1

    order = ["aspirate", "dispense", "mix", "blow_out", "touch_tip",
             "pick_up_tip", "drop_tip", "return_tip",
             "move", "delay", "pause", "set_temperature", "heater_shaker", "thermocycler",
             "note", "unknown"]
    actions = [a for a in order if a in counts]
    values  = [counts[a] for a in actions]
    colors  = [_ACTION_COLORS.get(a, _DIM) for a in actions]
    labels  = [a.replace("_", " ").title() for a in actions]

    bars = ax.barh(labels, values, color=colors, alpha=0.85, edgecolor=_BORDER, linewidth=0.5)
    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + max(values) * 0.012, bar.get_y() + bar.get_height() / 2,
                str(val), va="center", ha="left", fontsize=7.5, color=_TEXT)

    ax.set_xlabel("Count", fontsize=8)
    ax.set_title("Action Breakdown", color=_TEXT, fontsize=9, fontfamily="monospace")
    ax.invert_yaxis()
    _style_ax(ax)


def _plot_tip_timeline(ax, snapshots):
    xs = list(range(len(snapshots)))
    ys = [1 if s.active_tip else 0 for s in snapshots]

    ax.fill_between(xs, ys, step="post", color=_ACCENT, alpha=0.30)
    ax.step(xs, ys, where="post", color=_ACCENT, linewidth=1.5)
    ax.set_ylim(-0.1, 1.3)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["No tip", "Tip on"], fontsize=8)
    ax.set_xlabel("Snapshot index", fontsize=8)
    ax.set_title("Tip Usage Timeline", color=_TEXT, fontsize=9, fontfamily="monospace")
    _style_ax(ax)


def _plot_well_activity(ax, protocol):
    tracked_slots = sorted(
        [s for s, lw in protocol.slot_labware.items() if is_tracked_plate(lw)],
        key=lambda s: (0, int(s)) if s.isdigit() else (1, s),
    )

    if not tracked_slots:
        ax.text(0.5, 0.5, "No tracked plates", transform=ax.transAxes,
                ha="center", va="center", color=_DIM, fontsize=9)
        ax.set_title("Well Activity", color=_TEXT, fontsize=9)
        return

    touch_count: dict = {}
    for step in protocol.steps:
        if step.action in ("aspirate", "dispense") and step.slot and step.well:
            key = (step.slot, step.well)
            touch_count[key] = touch_count.get(key, 0) + 1

    n = len(tracked_slots)
    combined = np.zeros((8, 12 * n + (n - 1)))
    for p_idx, slot in enumerate(tracked_slots):
        offset = p_idx * 13
        for r_idx, row_l in enumerate(ROWS):
            for c_idx in range(12):
                well = f"{row_l}{c_idx + 1}"
                combined[r_idx, offset + c_idx] = touch_count.get((slot, well), 0)
        if p_idx > 0:
            combined[:, offset - 1] = np.nan

    masked = np.ma.masked_invalid(combined)
    vmax = max(masked.max(), 1)
    im = ax.imshow(masked, cmap=CMAP_ACTIVITY, aspect="auto",
                   vmin=0, vmax=vmax, interpolation="nearest")

    ax.set_yticks(range(8))
    ax.set_yticklabels(ROWS, fontsize=8, fontfamily="monospace", color=_TEXT)
    ax.yaxis.set_tick_params(length=0)

    for p_idx, slot in enumerate(tracked_slots):
        center = p_idx * 13 + 5.5
        lw_short = protocol.slot_labware.get(slot, "")[:20]
        ax.text(center, -1.2, f"Slot {slot}: {lw_short}", ha="center", va="bottom",
                fontsize=7.5, color=_TEXT, fontfamily="monospace",
                transform=ax.get_xaxis_transform())

    ax.set_xticks([])
    for spine in ax.spines.values():
        spine.set_edgecolor(_BORDER)
        spine.set_linewidth(0.7)

    fig = ax.get_figure()
    cbar = fig.colorbar(im, ax=ax, fraction=0.012, pad=0.01)
    cbar.set_label("Touch count", color=_TEXT, fontsize=7.5)
    cbar.ax.yaxis.set_tick_params(color=_TEXT, labelsize=7)
    cbar.ax.set_facecolor(_BG)

    ax.set_title("Well Activity Heatmap  (aspirate + dispense touches)",
                 color=_TEXT, fontsize=9, fontfamily="monospace")
    ax.set_facecolor(_BG)
