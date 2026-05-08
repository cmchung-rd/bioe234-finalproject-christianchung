"""
tools/visualize_deck_state.py
==============================
Parse simulation logs and produce all visualisation outputs:
  • PDF report
  • Interactive Plotly HTML dashboard
  • GIF animation
  • Statistics PNG
"""

import json
import os
import time
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .._lib.visualizer.log_parser import parse_log
from .._lib.visualizer.state_tracker import build_snapshots
from .._lib.visualizer.report_generator import generate_report
from .._lib.visualizer.html_exporter import export_html
from .._lib.visualizer.deck_visualizer import create_gif
from .._lib.visualizer.stats_visualizer import render_stats_dashboard


class VisualizeDeckState:
    def initiate(self) -> None:
        self._output_root = os.path.join(os.getcwd(), "output")
        os.makedirs(self._output_root, exist_ok=True)

    def run(self, simulation_log: str, run_id: str = "") -> str:
        if not run_id:
            run_id = str(int(time.time()))

        out_dir = os.path.join(self._output_root, run_id)
        os.makedirs(out_dir, exist_ok=True)

        try:
            protocol = parse_log(simulation_log)
            snapshots = build_snapshots(protocol)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": f"Log parsing failed: {exc}"})

        outputs: dict = {}
        errors: dict = {}

        # PDF report
        pdf_path = os.path.join(out_dir, "report.pdf")
        try:
            generate_report(protocol, snapshots, pdf_path)
            outputs["pdf"] = pdf_path
        except Exception as exc:  # noqa: BLE001
            errors["pdf"] = str(exc)

        # Interactive HTML
        html_path = os.path.join(out_dir, "dashboard.html")
        try:
            export_html(protocol, snapshots, html_path)
            outputs["html"] = html_path
        except Exception as exc:  # noqa: BLE001
            errors["html"] = str(exc)

        # GIF animation
        gif_path = os.path.join(out_dir, "deck_animation.gif")
        try:
            create_gif(snapshots, protocol, gif_path, fps=2.0, verbose=False)
            outputs["gif"] = gif_path
        except Exception as exc:  # noqa: BLE001
            errors["gif"] = str(exc)

        # Statistics dashboard PNG
        stats_path = os.path.join(out_dir, "stats_dashboard.png")
        try:
            fig = render_stats_dashboard(protocol, snapshots)
            fig.savefig(stats_path, dpi=130, bbox_inches="tight", facecolor=fig.get_facecolor())
            plt.close(fig)
            outputs["stats_png"] = stats_path
        except Exception as exc:  # noqa: BLE001
            errors["stats_png"] = str(exc)

        return json.dumps({
            "protocol_name": protocol.protocol_name,
            "steps_parsed": len(protocol.steps),
            "snapshots": len(snapshots),
            "outputs": outputs,
            "errors": errors,
        })


_instance = VisualizeDeckState()
_instance.initiate()
visualize_deck_state = _instance.run
