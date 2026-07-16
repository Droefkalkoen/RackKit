"""State tables: frame-indexed control states and their compilation (§4.3).

Multi-state controls (buttons, fader handles, selectors, lamps) map each
sprite frame to a named state, and each state to a set of *state actions*:
visibility toggles, material emission values, object transforms, shape keys.
The table compiles to constant-interpolation keyframe instructions so that
scrubbing the timeline previews exactly the discrete sheet, and rendering
frames ``0…N−1`` produces exactly the declared states.

This module is pure: it describes *what* to key, as data. Applying the
compiled keys to a live scene is :mod:`reblend.model.rigs`' job. Tables
serialise to JSON for storage in the element's ``re_states`` property.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from . import kinds

__all__ = [
    "StateAction",
    "State",
    "StateTable",
    "Key",
    "visibility",
    "emission_strength",
    "emission_color",
    "location",
    "shape_key_value",
    "default_state_table",
]

#: bpy.data collection names an action may target.
_ID_TYPES = ("objects", "materials")


@dataclass(frozen=True)
class StateAction:
    """One property assignment a state makes.

    ``id_type`` names the ``bpy.data`` collection (``objects`` /
    ``materials``), ``target`` the datablock, ``data_path`` the RNA path
    relative to it. ``index`` addresses one component of a vector property
    (−1 = whole value / scalar). ``value`` is a float or a float tuple.
    """

    id_type: str
    target: str
    data_path: str
    value: Any
    index: int = -1

    def key(self) -> tuple[str, str, str, int]:
        """Identity of the animated channel (what must appear in every state)."""
        return (self.id_type, self.target, self.data_path, self.index)


# -- convenience constructors (the vocabulary of design §4.3) ---------------


def visibility(obj: str, visible: bool) -> tuple[StateAction, ...]:
    """Show/hide an object in both render and viewport (preview = sheet)."""
    hide = not visible
    return (
        StateAction("objects", obj, "hide_render", float(hide)),
        StateAction("objects", obj, "hide_viewport", float(hide)),
    )


def emission_strength(material: str, value: float, node: str = "Emission") -> StateAction:
    """Emission strength on a named node of a material's tree (lamps, glows)."""
    path = f'node_tree.nodes["{node}"].inputs["Strength"].default_value'
    return StateAction("materials", material, path, float(value))


def emission_color(
    material: str, rgba: tuple[float, float, float, float], node: str = "Emission"
) -> StateAction:
    """Emission colour on a named node of a material's tree."""
    path = f'node_tree.nodes["{node}"].inputs["Color"].default_value'
    return StateAction("materials", material, path, tuple(float(c) for c in rgba))


def location(obj: str, axis: int, value: float) -> StateAction:
    """One location component of an object (a fader handle's detent position)."""
    return StateAction("objects", obj, "location", float(value), index=axis)


def shape_key_value(obj: str, key_name: str, value: float) -> StateAction:
    """A shape key's value on a mesh object (pressed caps, flexing parts)."""
    path = f'data.shape_keys.key_blocks["{key_name}"].value'
    return StateAction("objects", obj, path, float(value))


@dataclass(frozen=True)
class State:
    """One sprite frame's named state and the actions that realise it."""

    name: str
    actions: tuple[StateAction, ...] = ()


@dataclass(frozen=True)
class Key:
    """One compiled keyframe instruction (constant interpolation implied)."""

    frame: int
    id_type: str
    target: str
    data_path: str
    value: Any
    index: int = -1


@dataclass
class StateTable:
    """Frame-indexed states: ``states[i]`` is sprite frame ``i``."""

    states: list[State] = field(default_factory=list)

    @property
    def frames(self) -> int:
        return len(self.states)

    def compile(self) -> list[Key]:
        """Flatten to keyframe instructions, one per action per frame.

        Every animated channel must be set in *every* state: constant
        interpolation holds the previous key's value, so a channel missing
        from one state would silently leak a neighbouring frame's look into
        it — exactly the class of silent divergence RE-Blend exists to kill.
        Raises :class:`ValueError` naming the gaps instead.
        """
        for action in self._all_actions():
            if action.id_type not in _ID_TYPES:
                raise ValueError(
                    f"unknown id_type {action.id_type!r} (expected one of {_ID_TYPES})"
                )

        channels = {a.key() for a in self._all_actions()}
        missing = [
            f"state {i} ({state.name!r}): {chan}"
            for i, state in enumerate(self.states)
            for chan in sorted(channels - {a.key() for a in state.actions})
        ]
        if missing:
            raise ValueError(
                "state table is not total; every state must set every channel:\n  "
                + "\n  ".join(missing)
            )

        return [
            Key(
                frame=i,
                id_type=action.id_type,
                target=action.target,
                data_path=action.data_path,
                value=action.value,
                index=action.index,
            )
            for i, state in enumerate(self.states)
            for action in state.actions
        ]

    def _all_actions(self) -> Iterable[StateAction]:
        for state in self.states:
            yield from state.actions

    # -- persistence (element `re_states` property) --------------------------

    def to_json(self) -> str:
        return json.dumps(
            {
                "states": [
                    {
                        "name": state.name,
                        "actions": [
                            [a.id_type, a.target, a.data_path, a.index, a.value]
                            for a in state.actions
                        ],
                    }
                    for state in self.states
                ]
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> "StateTable":
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid state table JSON: {exc}") from exc
        states = []
        for entry in doc.get("states", []):
            actions = tuple(
                StateAction(
                    id_type=str(a[0]),
                    target=str(a[1]),
                    data_path=str(a[2]),
                    index=int(a[3]),
                    value=tuple(a[4]) if isinstance(a[4], list) else a[4],
                )
                for a in entry.get("actions", [])
            )
            states.append(State(name=str(entry.get("name", "")), actions=actions))
        return cls(states=states)


#: Default state names per kind. The designer fills in the actions; the
#:*names* encode the SDK-conventional meaning of each frame (§4.3).
_DEFAULT_NAMES: dict[str, tuple[str, ...]] = {
    kinds.LAMP: ("unlit", "lit"),
    kinds.BUTTON_TOGGLE: ("off", "on"),
    kinds.BUTTON_MOMENTARY: ("released", "pressed"),
    kinds.FADER_HANDLE: ("off", "on", "bypass"),  # the builtin_onoffbypass case
}


def default_state_table(kind: str, frames: int) -> StateTable | None:
    """A named-but-empty table for a multi-state kind, or None for no rig.

    Knobs get a driver instead of states; statics/backdrops/sockets get
    nothing. When the conventional names don't cover ``frames`` (a 5-step
    selector, an 8-frame fader), states fall back to ``state_0…state_N−1``.
    """
    if kinds.rig_for_kind(kind) != kinds.RIG_STATES:
        return None
    names = _DEFAULT_NAMES.get(kind, ())
    if len(names) != frames:
        names = tuple(f"state_{i}" for i in range(frames))
    return StateTable(states=[State(name=name) for name in names])
