# Christian Chung — Visualization

**BIOE 234 Final Project · Spring 2026**

## Role

Christian built the **visualization layer**, a 7-module package that transforms a raw simulation log into four distinct output artefacts: a multi-page PDF report, an interactive HTML dashboard, a GIF animation, and a statistics PNG.

---

## How it fits into the pipeline

```
  simulation log (plain text)  (Adriann)
          ↓
[ log_parser.py ]       — parses log into structured Python objects
          ↓
[ state_tracker.py ]    — builds per-step deck snapshots
          ↓
    ┌─────┴──────────────────────┐
    ↓                            ↓
[ report_generator.py ]   [ html_exporter.py ]
[ deck_visualizer.py  ]   [ stats_visualizer.py ]
[ plate_visualizer.py ]
    ↓                            ↓
  report.pdf              dashboard.html
  deck_animation.gif      stats_dashboard.png
```

All four outputs are downloaded automatically to `~/Downloads/OT2_outputs/<run_id>/` after each pipeline run.

---

## Files

| File | Description |
|------|-------------|
| `log_parser.py` | Parses raw simulation log text into `PipettingStep` and `ParsedProtocol` objects |
| `state_tracker.py` | Replays steps to build a list of `DeckSnapshot` objects, one per step |
| `deck_visualizer.py` | Renders deck layouts as matplotlib figures; exports GIF animations |
| `plate_visualizer.py` | Renders 96-well plate heatmaps showing volume distribution |
| `report_generator.py` | Generates multi-page PDF using ReportLab |
| `html_exporter.py` | Generates self-contained interactive HTML dashboard using Plotly |
| `stats_visualizer.py` | Generates 4-panel statistics figure (volume per slot, action breakdown, tip timeline, well activity heatmap) |
| `visualize_deck_state.py` | MCP tool wrapper (Function Object pattern) |
| `visualize_deck_state.json` | C9 JSON schema |

---

## What was built

### Log parser (`log_parser.py`)

Converts unstructured `opentrons_simulate` output into structured Python objects using a library of compiled regex patterns:

- **`PipettingStep`**: dataclass holding `action`, `volume_ul`, `slot`, `well`, `labware`, `raw_line`
- **`ParsedProtocol`**: top-level container holding all steps, slot-to-labware mapping, initial volumes, and liquid metadata
- Recognises 12+ action types: aspirate, dispense, pick_up_tip, drop_tip, blow_out, touch_tip, mix, move, delay, return_tip, set_temperature, thermocycler, heater_shaker, pause
- Skips calibration warnings, runtime messages, and indented sub-steps via `RE_SKIP_LINE`
- `_get_max_volume`: infers well capacity from labware name using a vocabulary of ~15 common labware types

### State tracker (`state_tracker.py`)

Replays the parsed steps in sequence, maintaining a running volume ledger per (slot, well) pair. At each pipetting step, produces a `DeckSnapshot` — a dict mapping every slot to a 96-element volume array. This enables frame-by-frame visualisation of how liquid moves across the deck.

### Deck visualizer (`deck_visualizer.py`)

- Renders OT-2 deck layout (11 slots in a 3×4 grid) as a matplotlib figure
- Colour-codes each slot by labware type
- Animates the sequence of snapshots into a GIF at configurable FPS using Pillow

### Plate visualizer (`plate_visualizer.py`)

- Renders individual 96-well plates as colour-mapped heatmaps (seaborn/matplotlib)
- Supports before/after comparison for a single plate across the protocol

### Report generator (`report_generator.py`)

Produces a multi-page PDF using ReportLab:
1. Cover page (protocol name, author, date, summary metrics)
2. Initial and final deck state figures
3. Per-plate volume heatmaps (before and after)
4. Full step log table (step index, action, volume, slot, well, labware)

### HTML exporter (`html_exporter.py`)

Produces a self-contained HTML file using Plotly:
- Animated 96-well plate heatmaps with a play/pause slider
- No external dependencies — the entire dashboard is embedded in a single `.html` file

### Statistics visualizer (`stats_visualizer.py`)

Produces a 4-panel matplotlib figure:
1. Total volume dispensed per slot (bar chart)
2. Action type breakdown (pie chart)
3. Tip usage timeline (step index vs. tip state)
4. Well activity heatmap (how many times each well was visited)

---

## Example outputs

Two real pipeline runs are included in `examples/` to illustrate what the visualizer produces.

### Serial dilution (`examples/serial_dilution/`)

Template-based protocol: 8-step serial dilution (180 µL transfers, plate slot 3 → plate slot 2).

| File | What it shows |
|------|--------------|
| `stats_dashboard.png` | 4-panel figure — volume per slot, action breakdown, tip timeline, well activity heatmap |
| `deck_animation.gif` | Frame-by-frame GIF of liquid moving across the OT-2 deck |
| `report.pdf` | Multi-page PDF: cover page, deck state figures, plate heatmaps, full step table |
| `dashboard.html` | Self-contained interactive Plotly dashboard with animated plate heatmaps |

### Reagent addition (`examples/reagent_addition/`)

Freeform protocol: 50 µL reagent dispensed from a 195 mL reservoir into 48 wells of a 96-well plate (192 pipetting actions).

Same four output files, demonstrating the visualizer on a denser, higher-step-count protocol.

---

## Key technical decisions

- **7-module separation**: Each output format is its own module. This makes it easy to extend (e.g. add a new export format) without touching the others.
- **Snapshot-based state model**: Rather than computing state on-demand during rendering, `state_tracker.py` pre-computes all snapshots upfront. This makes the GIF and HTML dashboard O(1) per frame.
- **Regex-based log parsing**: The log parser uses a compiled regex library rather than trying to import Opentrons — keeping the visualizer independent of the Opentrons venv.
- **`RE_SKIP_LINE` pattern**: A single compiled regex that matches all known non-pipetting log lines, preventing them from appearing as unclassified "Note" steps in reports.
