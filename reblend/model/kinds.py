"""Element kinds and their derivation from hdgui_2D widget types (§4.2, §4.3).

An RE Element's ``re_kind`` decides which rig it gets: knobs get the
turntable driver, multi-state controls get a state table compiled to constant
keyframes, statics/backdrops/sockets get no rig at all. The kind is derived on
import from the ``jbox.<widget>{...}`` constructors bound to the node — the
widget type is what Reason will *do* with the sheet, so it is the best
available signal for what the sheet must *contain*.

There is no formal SDK reference for this mapping (design §12); it follows the
SDK example devices. Unknown widget types map to ``static`` — rendering one
frame is always safe — and the validation report carries a widget↔kind check
so a wrong guess is visible rather than silent.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

__all__ = [
    "KNOB",
    "BUTTON_TOGGLE",
    "BUTTON_MOMENTARY",
    "FADER_HANDLE",
    "SELECTOR",
    "LAMP",
    "BACKDROP",
    "STATIC",
    "SOCKET",
    "ALL_KINDS",
    "RIG_DRIVER",
    "RIG_STATES",
    "kind_for_node",
    "rig_for_kind",
]

KNOB = "knob"
BUTTON_TOGGLE = "button_toggle"
BUTTON_MOMENTARY = "button_momentary"
FADER_HANDLE = "fader_handle"
SELECTOR = "selector"
LAMP = "lamp"
BACKDROP = "backdrop"
STATIC = "static"
SOCKET = "socket"

ALL_KINDS = (
    KNOB,
    BUTTON_TOGGLE,
    BUTTON_MOMENTARY,
    FADER_HANDLE,
    SELECTOR,
    LAMP,
    BACKDROP,
    STATIC,
    SOCKET,
)

#: Rig flavours (§4.3). ``None`` means the element renders as-is, one frame.
RIG_DRIVER = "driver"  # auto-generated turntable rotation driver
RIG_STATES = "states"  # state table compiled to constant-interpolation keys

_RIGS = {
    KNOB: RIG_DRIVER,
    BUTTON_TOGGLE: RIG_STATES,
    BUTTON_MOMENTARY: RIG_STATES,
    FADER_HANDLE: RIG_STATES,
    SELECTOR: RIG_STATES,
    LAMP: RIG_STATES,
}

#: hdgui_2D widget constructor name -> element kind. Widgets whose art is a
#: single decorative frame (device_name tape, placeholders) map to STATIC.
_WIDGET_KINDS = {
    "analog_knob": KNOB,
    "toggle_button": BUTTON_TOGGLE,
    "momentary_button": BUTTON_MOMENTARY,
    "sequence_fader": FADER_HANDLE,
    "step_button": SELECTOR,
    "up_down_button": SELECTOR,
    "radio_button": SELECTOR,
    "audio_input_socket": SOCKET,
    "audio_output_socket": SOCKET,
    "cv_input_socket": SOCKET,
    "cv_output_socket": SOCKET,
    "device_name": STATIC,
    "placeholder": STATIC,
    "static_decoration": STATIC,
}

#: Kinds that outrank STATIC when several widgets bind one node (e.g. a node
#: drawn by both a toggle_button and a static_decoration is a button).
_INTERACTIVE = frozenset(ALL_KINDS) - {STATIC, BACKDROP}


def kind_for_node(
    widgets: Sequence[tuple[str, Mapping[str, Any]]],
    frames: int,
    is_backdrop: bool = False,
) -> str:
    """Derive the element kind for one device_2D node.

    ``widgets`` are the ``(constructor_name, attrs)`` pairs of the hdgui_2D
    widgets bound to the node (usually one, sometimes none, occasionally
    several). ``frames`` is the node's declared frame count.

    Special cases, all grounded in SDK-example usage:

    - The node named by a panel's ``graphics.node`` is the panel backdrop.
    - A ``sequence_fader`` with ``handle_size > 0`` uses a *1-frame moving
      handle* the SDK positions itself (risk §10.4) — a static sheet, not a
      state rig. ``handle_size = 0`` (or absent) means N baked frames.
    - A ``static_decoration`` over a multi-frame sheet is the SDK-example lamp
      pattern (indicator art whose frame Reason selects), as is a multi-frame
      node with no widget at all.
    """
    if is_backdrop:
        return BACKDROP

    derived: list[str] = []
    for name, attrs in widgets:
        kind = _WIDGET_KINDS.get(name)
        if kind is None:
            continue
        if kind == FADER_HANDLE and _handle_size(attrs) > 0:
            kind = STATIC
        derived.append(kind)

    for kind in derived:
        if kind in _INTERACTIVE:
            return kind
    if frames > 1:
        # Multi-frame art bound only by static widgets (or nothing): lamp.
        return LAMP
    return STATIC


def _handle_size(attrs: Mapping[str, Any]) -> float:
    value = attrs.get("handle_size", 0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def rig_for_kind(kind: str) -> str | None:
    """Which rig flavour a kind gets: driver, state table, or none."""
    return _RIGS.get(kind)
