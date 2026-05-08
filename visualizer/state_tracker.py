"""
visualizer/state_tracker.py
============================
Replay a ParsedProtocol step-by-step and build a timeline of DeckSnapshots (Christian Chung).
"""

import warnings
from dataclasses import dataclass
from typing import Optional

from .log_parser import ParsedProtocol, PipettingStep, _get_max_volume

ROWS = list("ABCDEFGH")
COLS = list(range(1, 13))
ALL_WELLS = [f"{r}{c}" for r in ROWS for c in COLS]

_EXCLUDE_KEYWORDS = ("tip rack", "tiprack", "fixed trash", "reservoir", "waste chute")


def is_tracked_plate(labware_name: str) -> bool:
    name_lower = labware_name.lower()
    return not any(kw in name_lower for kw in _EXCLUDE_KEYWORDS)


@dataclass
class DeckSnapshot:
    step_index: int
    step_description: str
    well_volumes: dict
    slot_max_volumes: dict
    active_tip: bool
    active_slot: Optional[str]
    active_well: Optional[str]
    source_slot: Optional[str] = None
    source_well: Optional[str] = None


def build_snapshots(protocol: ParsedProtocol) -> list:
    current_volumes: dict = {}
    slot_max_vols: dict = dict(protocol.slot_max_volumes)

    for slot, lw_name in protocol.slot_labware.items():
        if is_tracked_plate(lw_name):
            max_vol = slot_max_vols.get(slot, 200.0)
            for well in ALL_WELLS:
                key = (slot, well)
                current_volumes[key] = protocol.init_volumes.get(key, 0.0)

    active_tip = False
    tip_volume = 0.0
    last_asp_slot: Optional[str] = None
    last_asp_well: Optional[str] = None

    def snap(step_idx, desc, a_slot=None, a_well=None, s_slot=None, s_well=None):
        return DeckSnapshot(
            step_index=step_idx,
            step_description=desc,
            well_volumes=dict(current_volumes),
            slot_max_volumes=dict(slot_max_vols),
            active_tip=active_tip,
            active_slot=a_slot,
            active_well=a_well,
            source_slot=s_slot,
            source_well=s_well,
        )

    snapshots: list = [snap(-1, "Initial State")]

    for step in protocol.steps:
        if step.action == "unknown":
            continue

        key = (step.slot, step.well) if step.slot and step.well else None

        if step.slot and step.slot not in slot_max_vols and step.labware:
            max_vol = _get_max_volume(step.labware)
            slot_max_vols[step.slot] = max_vol
            if is_tracked_plate(step.labware):
                for well in ALL_WELLS:
                    current_volumes.setdefault((step.slot, well), 0.0)

        if step.action == "aspirate" and key:
            old_vol = current_volumes.get(key, 0.0)
            removed = min(old_vol, step.volume_ul or 0.0)
            if old_vol < (step.volume_ul or 0.0):
                warnings.warn(
                    f"Step {step.step_index}: aspirated {step.volume_ul} µL "
                    f"from {key} but only {old_vol:.1f} µL available. Clamping to 0.",
                    stacklevel=2,
                )
            current_volumes[key] = old_vol - removed
            tip_volume += step.volume_ul or 0.0
            last_asp_slot = step.slot
            last_asp_well = step.well

        elif step.action == "dispense" and key:
            current_volumes[key] = current_volumes.get(key, 0.0) + (step.volume_ul or 0.0)
            tip_volume = max(0.0, tip_volume - (step.volume_ul or 0.0))

        elif step.action == "pick_up_tip":
            active_tip = True
            tip_volume = 0.0

        elif step.action == "drop_tip":
            active_tip = False
            tip_volume = 0.0
            last_asp_slot = None
            last_asp_well = None

        elif step.action == "blow_out" and key:
            current_volumes[key] = current_volumes.get(key, 0.0) + tip_volume
            tip_volume = 0.0

        src_s = last_asp_slot if step.action == "dispense" else None
        src_w = last_asp_well if step.action == "dispense" else None
        snapshots.append(snap(
            step.step_index, _describe(step),
            a_slot=step.slot, a_well=step.well,
            s_slot=src_s, s_well=src_w,
        ))

    return snapshots


def _describe(step: PipettingStep) -> str:
    vol_str = f" {step.volume_ul:.1f} µL" if step.volume_ul is not None else ""
    loc_str = ""
    if step.well and step.slot:
        loc_str = f" at {step.well} / slot {step.slot}"
    elif step.slot:
        loc_str = f" at slot {step.slot}"
    verbs = {
        "aspirate": "Aspirate", "dispense": "Dispense",
        "pick_up_tip": "Pick up tip", "drop_tip": "Drop tip",
        "blow_out": "Blow out", "touch_tip": "Touch tip",
    }
    verb = verbs.get(step.action, step.action.replace("_", " ").title())
    return f"{verb}{vol_str}{loc_str}"
