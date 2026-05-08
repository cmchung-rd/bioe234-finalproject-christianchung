"""
visualizer/html_exporter.py
============================
Export an interactive, self-contained HTML dashboard using Plotly (Christian Chung).
"""

import os
import numpy as np

from .log_parser import ParsedProtocol
from .state_tracker import DeckSnapshot, is_tracked_plate

_COLORSCALE = [
    [0.00, "#FFFFFF"], [0.25, "#DBEAFE"],
    [0.50, "#93C5FD"], [0.75, "#3B82F6"], [1.00, "#1E3A8A"],
]

_ROWS = list("ABCDEFGH")
_COLS = list(range(1, 13))
_MAX_FRAMES = 60


def export_html(protocol: ParsedProtocol, snapshots: list, output_path: str) -> None:
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        raise ImportError("HTML export requires plotly. pip install plotly")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    _slot_key = lambda s: (0, int(s)) if s.isdigit() else (1, s)
    tracked = sorted(
        [s for s, lw in protocol.slot_labware.items() if is_tracked_plate(lw)],
        key=_slot_key,
    )

    if not tracked:
        _write_no_plates_html(protocol, snapshots, output_path)
        return

    if len(snapshots) > _MAX_FRAMES:
        step = len(snapshots) / _MAX_FRAMES
        sampled = [snapshots[int(i * step)] for i in range(_MAX_FRAMES - 1)]
        sampled.append(snapshots[-1])
    else:
        sampled = list(snapshots)

    n_plates = len(tracked)
    n_cols   = min(3, n_plates)
    n_rows   = (n_plates + n_cols - 1) // n_cols

    subplot_titles = []
    for slot in tracked:
        lw = protocol.slot_labware.get(slot, "")
        short = lw[:35] + "…" if len(lw) > 35 else lw
        subplot_titles.append(f"Slot {slot}: {short}")

    fig = make_subplots(rows=n_rows, cols=n_cols, subplot_titles=subplot_titles,
                        vertical_spacing=0.22, horizontal_spacing=0.10)

    for i, slot in enumerate(tracked):
        row = i // n_cols + 1
        col = i % n_cols + 1
        z, text = _build_grids(sampled[0], slot, protocol)
        fig.add_trace(
            go.Heatmap(z=z, customdata=text, hovertemplate="%{customdata}<extra></extra>",
                       colorscale=_COLORSCALE, zmin=0, zmax=1, xgap=1, ygap=1,
                       showscale=(i == 0),
                       colorbar=dict(title="Fill %", tickformat=".0%", x=1.02, len=0.8) if i == 0 else None),
            row=row, col=col,
        )
        fig.update_xaxes(tickvals=list(range(12)), ticktext=[str(c) for c in _COLS],
                         side="top", row=row, col=col)
        fig.update_yaxes(tickvals=list(range(8)), ticktext=list(reversed(_ROWS)),
                         row=row, col=col, autorange="reversed")

    frames = []
    for snap in sampled:
        frame_data = []
        for slot in tracked:
            z, text = _build_grids(snap, slot, protocol)
            frame_data.append(go.Heatmap(z=z, customdata=text,
                                         hovertemplate="%{customdata}<extra></extra>",
                                         colorscale=_COLORSCALE, zmin=0, zmax=1,
                                         xgap=1, ygap=1, showscale=False))
        label = f"Step {snap.step_index}" if snap.step_index >= 0 else "Initial"
        frames.append(go.Frame(data=frame_data, name=label, traces=list(range(n_plates))))
    fig.frames = frames

    updatemenus = [dict(
        type="buttons", showactive=False, y=-0.12, x=0.0, xanchor="left", yanchor="top",
        buttons=[
            dict(label="▶ Play", method="animate",
                 args=[None, {"frame": {"duration": 350, "redraw": True},
                              "fromcurrent": True, "transition": {"duration": 0}}]),
            dict(label="⏸ Pause", method="animate",
                 args=[[None], {"frame": {"duration": 0}, "mode": "immediate",
                                "transition": {"duration": 0}}]),
        ],
    )]

    sliders = [dict(
        steps=[dict(args=[[f.name], {"frame": {"duration": 0, "redraw": True}, "mode": "immediate"}],
                    label=f.name, method="animate") for f in frames],
        transition={"duration": 0}, x=0.10, len=0.88,
        currentvalue=dict(prefix="Snapshot: ", font=dict(size=12), xanchor="center"),
        pad={"t": 60, "b": 10}, bgcolor="#F0F2F7", bordercolor="#C4C9D8", tickcolor="#6B7280",
    )]

    n_steps = sum(1 for s in protocol.steps if s.action != "unknown")
    tot_vol = sum(s.volume_ul or 0 for s in protocol.steps if s.action == "dispense")

    fig.update_layout(
        title=dict(
            text=(f"<b>{protocol.protocol_name}</b><br>"
                  f"<sup>{n_steps} steps · {tot_vol:.0f} µL dispensed · "
                  f"{len(tracked)} plate(s) · {len(sampled)} animation frames</sup>"),
            font=dict(size=15, color="#1E2130"),
        ),
        paper_bgcolor="#FFFFFF", plot_bgcolor="#F0F2F7",
        height=440 * n_rows + 300,
        updatemenus=updatemenus, sliders=sliders,
        margin=dict(t=140, b=180, l=60, r=60),
    )

    fig.write_html(output_path, include_plotlyjs=True, full_html=True)


def _build_grids(snapshot: DeckSnapshot, slot: str, protocol: ParsedProtocol):
    max_vol = snapshot.slot_max_volumes.get(slot, 200.0) or 200.0
    z    = np.zeros((8, 12), dtype=float)
    text = np.empty((8, 12), dtype=object)
    for r_idx, row_l in enumerate(_ROWS):
        for c_idx in range(12):
            well = f"{row_l}{c_idx + 1}"
            vol  = snapshot.well_volumes.get((slot, well), 0.0)
            fill = max(0.0, min(1.0, vol / max_vol))
            z[r_idx, c_idx] = fill
            text[r_idx, c_idx] = (f"<b>Well {well}</b><br>"
                                   f"Volume: {vol:.1f} µL<br>Fill: {fill * 100:.0f}%")
    return z, text


def _write_no_plates_html(protocol, snapshots, output_path):
    n_steps = sum(1 for s in protocol.steps if s.action != "unknown")
    html = (f"<!DOCTYPE html><html><head><title>{protocol.protocol_name}</title></head>"
            f"<body style='font-family:monospace;padding:2rem;'>"
            f"<h2>{protocol.protocol_name}</h2>"
            f"<p>{n_steps} steps parsed — no tracked 96-well plates found in this log.</p>"
            f"<p>Labware: {dict(protocol.slot_labware)}</p>"
            f"</body></html>")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
