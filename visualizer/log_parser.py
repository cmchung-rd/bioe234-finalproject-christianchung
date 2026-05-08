"""
visualizer/log_parser.py
========================
Parse raw Opentrons simulation log text into structured Python objects (Christian Chung).
"""

import re
import warnings
from dataclasses import dataclass, field
from typing import Optional

ROWS = list("ABCDEFGH")
COLS = list(range(1, 13))

_VOLUME_HINTS: list[tuple] = [
    ("200 µl pcr",   200.0),
    ("200 ul pcr",   200.0),
    ("100 µl pcr",   100.0),
    ("100 ul pcr",   100.0),
    ("200 µl flat",  200.0),
    ("200 ul flat",  200.0),
    ("360 µl",       360.0),
    ("360 ul",       360.0),
    ("100 µl",       100.0),
    ("100 ul",       100.0),
    ("2 ml",        2000.0),
    ("96 deep well", 2000.0),
    ("reservoir",  float("inf")),
    ("tip rack",      0.0),
    ("tiprack",       0.0),
    ("fixed trash",   0.0),
    ("waste chute",   0.0),
]


def _get_max_volume(labware_name: str) -> float:
    name_lower = labware_name.lower()
    for hint, vol in _VOLUME_HINTS:
        if hint in name_lower:
            return vol
    warnings.warn(
        f"Could not infer max volume for labware {labware_name!r}. Defaulting to 200.0 µL.",
        stacklevel=2,
    )
    return 200.0


@dataclass
class PipettingStep:
    step_index: int
    action: str
    volume_ul: Optional[float]
    slot: Optional[str]
    well: Optional[str]
    labware: Optional[str]
    raw_line: str


@dataclass
class ParsedProtocol:
    protocol_name: str
    steps: list
    slot_labware: dict
    slot_max_volumes: dict
    init_volumes: dict
    liquid_map: dict


RE_PROTOCOL = re.compile(r"^#\s*PROTOCOL:\s*(.+)$")
RE_INIT = re.compile(
    r"^#\s*INIT\s+slot\s*(\w+)\s+([A-H]\d{1,2})\s+([\d.]+)\s*[uµ]L\s*$",
    re.IGNORECASE,
)
RE_LOAD = re.compile(r"^Loading (.+?) into slot (\w+)$")
RE_LOAD_ALT = re.compile(r"^Loading (.+?) on (\w+)$")

_SLOT  = r"(\w+)"
_SPEED = r"(?:\s+at\s+[\d.]+\s+(?:[uµ]L/sec|speed))?"

RE_ASPIRATE = re.compile(
    r"^Aspirating ([\d.]+) [uµ]L? from ([A-H]\d{1,2}) of (.+)"
    r" on (?:slot )?" + _SLOT + _SPEED + r"$",
    re.IGNORECASE,
)
RE_DISPENSE = re.compile(
    r"^Dispensing ([\d.]+) [uµ]L? into ([A-H]\d{1,2}) of (.+)"
    r" on (?:slot )?" + _SLOT + _SPEED + r"$",
    re.IGNORECASE,
)
RE_PICK_TIP = re.compile(
    r"^Picking up tip from ([A-H]\d{1,2}) of (.+) on (?:slot )?" + _SLOT + r"$",
    re.IGNORECASE,
)
RE_DROP_TIP = re.compile(
    r"^Dropping tip into (.+?)(?:\s+on\s+(?:slot\s+)?(\w+))?$",
    re.IGNORECASE,
)
RE_BLOWOUT = re.compile(
    r"^Blowing out (?:at|into) ([A-H]\d{1,2}) of (.+)"
    r" on (?:slot )?" + _SLOT + _SPEED + r"$",
    re.IGNORECASE,
)
RE_TOUCH_TIP = re.compile(
    r"^Touching tip at ([A-H]\d{1,2}) of (.+) on (?:slot )?" + _SLOT + r"$",
    re.IGNORECASE,
)
RE_LIQUID = re.compile(
    r"^#\s*LIQUID\s+(\w+)\s+([A-H]\d{1,2})\s+(\S+)(?:\s+(.+))?$",
    re.IGNORECASE,
)
RE_MOVE = re.compile(
    r"^Moving to ([A-H]\d{1,2}) of (.+) on (?:slot )?" + _SLOT + r"$",
    re.IGNORECASE,
)
RE_DELAY = re.compile(r"^Delaying for [\d.]+ minutes? and [\d.]+ seconds?", re.IGNORECASE)
RE_RETURN_TIP = re.compile(r"^Returning tip", re.IGNORECASE)
RE_MIX = re.compile(r"^Mixing \d+ times? with a volume of [\d.]+ [uµ]l", re.IGNORECASE)
RE_SET_TEMP = re.compile(r"^Setting (?:Thermocycler|Temperature Module|Heater-Shaker)", re.IGNORECASE)
RE_HEATER_SHAKER = re.compile(
    r"^(?:Latching|Unlatching) labware on Heater-Shaker"
    r"|^(?:Activating|Deactivating) (?:Shaker|Heater-Shaker)",
    re.IGNORECASE,
)
RE_THERMOCYCLER = re.compile(
    r"^(?:Opening|Closing) Thermocycler lid"
    r"|^Thermocycler (?:starting|waiting|finished)",
    re.IGNORECASE,
)
RE_PAUSE = re.compile(r"^Pausing robot operation", re.IGNORECASE)
RE_SKIP_LINE = re.compile(
    r"^={3,}$"
    r"|^-{3,}$"
    r"|^-->"
    r"|^Adding tiprack"
    r"|not found\. Loading defaults"   # calibration warnings
    r"|^Deck calibration"
    r"|^Calibration"
    r"|^Transferring "                 # parent line; aspirate/dispense already captured
    r"|^\t"                            # indented sub-steps already captured
    r"|^Collecting usage"
    r"|^Welcome to"
    r"|^Simulating",
    re.IGNORECASE,
)


def parse_log(text: str) -> ParsedProtocol:
    protocol_name = "Unnamed Protocol"
    slot_labware: dict = {}
    slot_max_volumes: dict = {}
    init_volumes: dict = {}
    liquid_map: dict = {}
    steps: list = []
    step_index = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        m = RE_PROTOCOL.match(line)
        if m:
            protocol_name = m.group(1).strip()
            continue

        m = RE_INIT.match(line)
        if m:
            slot, well, vol = m.group(1), m.group(2).upper(), float(m.group(3))
            init_volumes[(slot, well)] = vol
            continue

        m = RE_LIQUID.match(line)
        if m:
            slot, well, color, name = m.group(1), m.group(2).upper(), m.group(3), m.group(4)
            liquid_map[(slot, well)] = {"color": color, "name": (name or color).strip()}
            continue

        if line.startswith("#"):
            continue

        m = RE_LOAD.match(line) or RE_LOAD_ALT.match(line)
        if m:
            lw_name, slot = m.group(1).strip(), m.group(2)
            slot_labware[slot] = lw_name
            slot_max_volumes[slot] = _get_max_volume(lw_name)
            continue

        m = RE_PICK_TIP.match(line)
        if m:
            well = m.group(1).upper()
            lw   = m.group(2).strip()
            slot = m.group(3)
            _register_labware(slot, lw, slot_labware, slot_max_volumes)
            steps.append(PipettingStep(step_index=step_index, action="pick_up_tip",
                                       volume_ul=None, slot=slot, well=well, labware=lw, raw_line=raw_line))
            step_index += 1
            continue

        m = RE_ASPIRATE.match(line)
        if m:
            vol  = float(m.group(1))
            well = m.group(2).upper()
            lw   = m.group(3).strip()
            slot = m.group(4)
            _register_labware(slot, lw, slot_labware, slot_max_volumes)
            steps.append(PipettingStep(step_index=step_index, action="aspirate",
                                       volume_ul=vol, slot=slot, well=well, labware=lw, raw_line=raw_line))
            step_index += 1
            continue

        m = RE_DISPENSE.match(line)
        if m:
            vol  = float(m.group(1))
            well = m.group(2).upper()
            lw   = m.group(3).strip()
            slot = m.group(4)
            _register_labware(slot, lw, slot_labware, slot_max_volumes)
            steps.append(PipettingStep(step_index=step_index, action="dispense",
                                       volume_ul=vol, slot=slot, well=well, labware=lw, raw_line=raw_line))
            step_index += 1
            continue

        m = RE_DROP_TIP.match(line)
        if m:
            lw   = m.group(1).strip()
            slot = m.group(2)
            steps.append(PipettingStep(step_index=step_index, action="drop_tip",
                                       volume_ul=None, slot=slot, well=None, labware=lw, raw_line=raw_line))
            step_index += 1
            continue

        m = RE_BLOWOUT.match(line)
        if m:
            well = m.group(1).upper()
            lw   = m.group(2).strip()
            slot = m.group(3)
            _register_labware(slot, lw, slot_labware, slot_max_volumes)
            steps.append(PipettingStep(step_index=step_index, action="blow_out",
                                       volume_ul=None, slot=slot, well=well, labware=lw, raw_line=raw_line))
            step_index += 1
            continue

        m = RE_TOUCH_TIP.match(line)
        if m:
            well = m.group(1).upper()
            lw   = m.group(2).strip()
            slot = m.group(3)
            _register_labware(slot, lw, slot_labware, slot_max_volumes)
            steps.append(PipettingStep(step_index=step_index, action="touch_tip",
                                       volume_ul=None, slot=slot, well=well, labware=lw, raw_line=raw_line))
            step_index += 1
            continue

        if RE_SKIP_LINE.match(line):
            continue

        m = RE_MOVE.match(line)
        if m:
            steps.append(PipettingStep(step_index=step_index, action="move",
                                       volume_ul=None, slot=m.group(3), well=m.group(1).upper(),
                                       labware=m.group(2).strip(), raw_line=raw_line))
            step_index += 1
            continue

        if RE_DELAY.match(line):
            steps.append(PipettingStep(step_index=step_index, action="delay",
                                       volume_ul=None, slot=None, well=None, labware=None, raw_line=raw_line))
            step_index += 1
            continue

        if RE_RETURN_TIP.match(line):
            steps.append(PipettingStep(step_index=step_index, action="return_tip",
                                       volume_ul=None, slot=None, well=None, labware=None, raw_line=raw_line))
            step_index += 1
            continue

        if RE_MIX.match(line):
            steps.append(PipettingStep(step_index=step_index, action="mix",
                                       volume_ul=None, slot=None, well=None, labware=None, raw_line=raw_line))
            step_index += 1
            continue

        if RE_SET_TEMP.match(line):
            steps.append(PipettingStep(step_index=step_index, action="set_temperature",
                                       volume_ul=None, slot=None, well=None, labware=None, raw_line=raw_line))
            step_index += 1
            continue

        if RE_HEATER_SHAKER.match(line):
            steps.append(PipettingStep(step_index=step_index, action="heater_shaker",
                                       volume_ul=None, slot=None, well=None, labware=None, raw_line=raw_line))
            step_index += 1
            continue

        if RE_THERMOCYCLER.match(line):
            steps.append(PipettingStep(step_index=step_index, action="thermocycler",
                                       volume_ul=None, slot=None, well=None, labware=None, raw_line=raw_line))
            step_index += 1
            continue

        if RE_PAUSE.match(line):
            steps.append(PipettingStep(step_index=step_index, action="pause",
                                       volume_ul=None, slot=None, well=None, labware=None, raw_line=raw_line))
            step_index += 1
            continue

        # Skip unrecognised lines (calibration warnings, runtime messages, etc.)
        pass

    return ParsedProtocol(
        protocol_name=protocol_name,
        steps=steps,
        slot_labware=slot_labware,
        slot_max_volumes=slot_max_volumes,
        init_volumes=init_volumes,
        liquid_map=liquid_map,
    )


def _register_labware(slot, lw_name, slot_labware, slot_max_volumes):
    if slot not in slot_labware:
        slot_labware[slot] = lw_name
        slot_max_volumes[slot] = _get_max_volume(lw_name)
