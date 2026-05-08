"""
visualizer/deck_visualizer.py
==============================
Render the full OT-2 deck layout as a matplotlib Figure (Christian Chung).
"""

import os
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize, LinearSegmentedColormap
from matplotlib.gridspec import GridSpec
from matplotlib.figure import Figure
import numpy as np

from .state_tracker import DeckSnapshot, is_tracked_plate
from .log_parser import ParsedProtocol

_BG      = "#FFFFFF"
_PANEL   = "#F0F2F7"
_BORDER  = "#C4C9D8"
_ACTIVE  = "#2563EB"
_TEXT    = "#1E2130"
_DIM     = "#6B7280"
_TRASH   = "#FEE2E2"
_TIP_DOT = "#B4B8C8"

CMAP_VOLUME = LinearSegmentedColormap.from_list(
    "ot2vol",
    ["#FFFFFF", "#DBEAFE", "#93C5FD", "#3B82F6", "#1E3A8A"],
    N=256,
)

SLOT_POSITIONS: dict = {
    "1":  (0, 0), "2":  (0, 1), "3":  (0, 2),
    "4":  (1, 0), "5":  (1, 1), "6":  (1, 2),
    "7":  (2, 0), "8":  (2, 1), "9":  (2, 2),
    "10": (3, 0), "11": (3, 1), "12": (3, 2),
}
SLOT_ORDER = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]
TRASH_SLOT = "12"

FLEX_SLOT_POSITIONS: dict = {
    "A1": (0, 0), "A2": (0, 1), "A3": (0, 2),
    "B1": (1, 0), "B2": (1, 1), "B3": (1, 2),
    "C1": (2, 0), "C2": (2, 1), "C3": (2, 2),
    "D1": (3, 0), "D2": (3, 1), "D3": (3, 2),
}
FLEX_SLOT_ORDER = ["A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3", "D1", "D2", "D3"]

ROWS = list("ABCDEFGH")
COLS = list(range(1, 13))


def render_deck_snapshot(snapshot: DeckSnapshot, protocol: ParsedProtocol, figsize: tuple = (14, 10)) -> Figure:
    is_flex = any(s[:1].isalpha() for s in protocol.slot_labware)
    slot_positions = FLEX_SLOT_POSITIONS if is_flex else SLOT_POSITIONS
    slot_order     = FLEX_SLOT_ORDER     if is_flex else SLOT_ORDER
    trash_slot     = None                if is_flex else TRASH_SLOT

    fig = plt.figure(figsize=figsize, facecolor=_BG)
    gs = GridSpec(4, 4, figure=fig, width_ratios=[1, 1, 1, 0.07],
                  hspace=0.20, wspace=0.12, left=0.03, right=0.97, top=0.91, bottom=0.04)
    norm = Normalize(vmin=0, vmax=1)

    slot_to_ax: dict = {}
    for slot in slot_order:
        deck_row, col = slot_positions[slot]
        gs_row = 3 - deck_row
        ax = fig.add_subplot(gs[gs_row, col])
        _draw_slot(ax, slot, snapshot, protocol, norm, trash_slot)
        slot_to_ax[slot] = ax

    src = getattr(snapshot, "source_slot", None)
    dst = snapshot.active_slot
    if src and dst and src != dst and src in slot_to_ax and dst in slot_to_ax:
        _draw_transfer_arrow(fig, slot_to_ax[src], slot_to_ax[dst])

    cbar_ax = fig.add_subplot(gs[:, 3])
    sm = plt.cm.ScalarMappable(cmap=CMAP_VOLUME, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, cax=cbar_ax)
    cbar.set_label("Fill level", color=_TEXT, fontsize=8)
    cbar.ax.yaxis.set_tick_params(color=_TEXT)
    cbar.set_ticks([0, 0.25, 0.5, 0.75, 1.0])
    cbar.set_ticklabels(["0 %", "25 %", "50 %", "75 %", "100 %"], color=_TEXT, fontsize=7)
    cbar.ax.set_facecolor(_BG)

    step_label = (
        f"Step {snapshot.step_index}: {snapshot.step_description}"
        if snapshot.step_index >= 0 else "Initial State"
    )
    fig.suptitle(f"{protocol.protocol_name}  ·  {step_label}",
                 color=_TEXT, fontsize=11, y=0.975, fontfamily="monospace")
    return fig


def render_all_steps(snapshots: list, protocol: ParsedProtocol, output_dir: str,
                     dpi: int = 120, verbose: bool = True) -> None:
    os.makedirs(output_dir, exist_ok=True)
    total = len(snapshots)
    for i, snap in enumerate(snapshots):
        fig = render_deck_snapshot(snap, protocol)
        path = os.path.join(output_dir, f"deck_step_{i:04d}.png")
        fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)
        if verbose:
            print(f"  [{i + 1}/{total}] saved {path}", end="\r")
    if verbose:
        print()


def create_gif(snapshots: list, protocol: ParsedProtocol, output_path: str,
               fps: float = 2.0, dpi: int = 80, verbose: bool = True) -> None:
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("Pillow is required for GIF export. pip install Pillow")
    import io

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    ms_per_frame = max(20, int(1000 / fps))
    frames = []
    total = len(snapshots)
    for i, snap in enumerate(snapshots):
        fig = render_deck_snapshot(snap, protocol)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        frames.append(Image.open(buf).convert("RGB"))
        if verbose:
            print(f"  [{i + 1}/{total}] rendered frame", end="\r")
    if verbose:
        print()

    if not frames:
        return

    frames[0].save(output_path, save_all=True, append_images=frames[1:],
                   loop=0, duration=ms_per_frame, optimize=False)
    if verbose:
        print(f"  Saved -> {output_path}")


def create_mp4(snapshots: list, protocol, output_path: str,
               fps: float = 6.0, dpi: int = 100, verbose: bool = True) -> None:
    try:
        import imageio
    except ImportError:
        raise ImportError("MP4 export requires imageio[ffmpeg]. pip install 'imageio[ffmpeg]'")
    import io
    import numpy as np
    from PIL import Image

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    total = len(snapshots)
    frames = []
    for i, snap in enumerate(snapshots):
        fig = render_deck_snapshot(snap, protocol)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        frames.append(np.array(Image.open(buf).convert("RGB")))
        if verbose:
            print(f"  [{i + 1}/{total}] rendered frame", end="\r")
    if verbose:
        print()

    if not frames:
        return

    h = min(f.shape[0] for f in frames)
    w = min(f.shape[1] for f in frames)
    h -= h % 2
    w -= w % 2
    frames = [f[:h, :w] for f in frames]

    writer = imageio.get_writer(output_path, fps=fps, quality=5, macro_block_size=None)
    for frame in frames:
        writer.append_data(frame)
    writer.close()
    if verbose:
        print(f"  Saved -> {output_path}")


def _draw_slot(ax, slot, snapshot, protocol, norm, trash_slot=TRASH_SLOT):
    is_trash  = (trash_slot is not None) and (slot == trash_slot)
    is_active = slot == snapshot.active_slot
    lw_name   = protocol.slot_labware.get(slot, "")

    ax.set_facecolor(_TRASH if is_trash else _PANEL)
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 8)
    ax.set_aspect("equal")

    border_color = _ACTIVE if is_active else _BORDER
    border_lw    = 2.2  if is_active else 0.6
    for spine in ax.spines.values():
        spine.set_edgecolor(border_color)
        spine.set_linewidth(border_lw)

    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

    slot_display = "Trash" if is_trash else slot
    ax.text(0.03, 0.97, slot_display, transform=ax.transAxes,
            color=_DIM, fontsize=7, va="top", ha="left", fontfamily="monospace")

    short = _truncate(lw_name or ("Fixed Trash" if is_trash else ""), 22)
    ax.set_title(short, color=_DIM, fontsize=6.5, pad=2, fontfamily="monospace")

    if is_trash:
        ax.text(0.5, 0.5, "TRASH", transform=ax.transAxes,
                color="#DC2626", fontsize=10, ha="center", va="center",
                fontweight="bold", fontfamily="monospace")
    elif not lw_name:
        ax.text(0.5, 0.5, "empty", transform=ax.transAxes,
                color=_DIM, fontsize=8, ha="center", va="center",
                style="italic", fontfamily="monospace")
    elif is_tracked_plate(lw_name):
        _draw_mini_plate(ax, slot, snapshot, norm, is_active)
    else:
        _draw_tip_rack(ax)


def _draw_mini_plate(ax, slot, snapshot, norm, is_active):
    max_vol = snapshot.slot_max_volumes.get(slot, 200.0) or 1.0
    xs, ys, colors, sizes = [], [], [], []
    for r_idx, row_letter in enumerate(ROWS):
        for c_idx, col_num in enumerate(COLS):
            well = f"{row_letter}{col_num}"
            vol  = snapshot.well_volumes.get((slot, well), 0.0)
            fill = max(0.0, min(1.0, vol / max_vol))
            xs.append(c_idx + 0.5)
            ys.append(7 - r_idx + 0.5)
            colors.append(CMAP_VOLUME(norm(fill)))
            is_active_well = is_active and well == snapshot.active_well
            sizes.append(32 if is_active_well else 18)

    ax.scatter(xs, ys, c=colors, s=sizes, marker="o", linewidths=0, zorder=3)

    if is_active and snapshot.active_well:
        for r_idx, row_letter in enumerate(ROWS):
            for c_idx, col_num in enumerate(COLS):
                if f"{row_letter}{col_num}" == snapshot.active_well:
                    ax.scatter([c_idx + 0.5], [7 - r_idx + 0.5], s=72, marker="o",
                               facecolors="none", edgecolors=_ACTIVE, linewidths=1.8, zorder=4)


def _draw_transfer_arrow(fig, ax_src, ax_dst):
    from matplotlib.patches import FancyArrowPatch
    pos_src = ax_src.get_position()
    pos_dst = ax_dst.get_position()
    x_src = pos_src.x0 + pos_src.width  / 2
    y_src = pos_src.y0 + pos_src.height / 2
    x_dst = pos_dst.x0 + pos_dst.width  / 2
    y_dst = pos_dst.y0 + pos_dst.height / 2
    arrow = FancyArrowPatch(
        (x_src, y_src), (x_dst, y_dst),
        transform=fig.transFigure,
        arrowstyle="->,head_width=0.013,head_length=0.018",
        color=_ACTIVE, linewidth=2.0, connectionstyle="arc3,rad=0.25",
        zorder=20, clip_on=False,
    )
    fig.add_artist(arrow)


def _draw_tip_rack(ax):
    xs = [c + 0.5 for c in range(12) for _ in range(8)]
    ys = [r + 0.5 for _ in range(12) for r in range(8)]
    ax.scatter(xs, ys, c=_TIP_DOT, s=9, marker="o", linewidths=0, zorder=3)
    ax.text(0.5, 0.06, "tip rack", transform=ax.transAxes,
            color=_DIM, fontsize=6, ha="center", va="bottom", fontfamily="monospace")


def _truncate(name: str, maxlen: int) -> str:
    if len(name) <= maxlen:
        return name
    return name[: maxlen - 1] + "…"
