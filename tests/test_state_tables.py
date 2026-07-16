"""State tables: defaults per kind, compilation totality, JSON persistence (§4.3)."""

import pytest

from reblend.model import kinds, state_tables
from reblend.model.state_tables import (
    State,
    StateAction,
    StateTable,
    default_state_table,
    emission_color,
    emission_strength,
    location,
    shape_key_value,
    visibility,
)


def test_default_tables_use_conventional_names():
    lamp = default_state_table(kinds.LAMP, 2)
    assert [s.name for s in lamp.states] == ["unlit", "lit"]
    fader = default_state_table(kinds.FADER_HANDLE, 3)
    assert [s.name for s in fader.states] == ["off", "on", "bypass"]
    toggle = default_state_table(kinds.BUTTON_TOGGLE, 2)
    assert [s.name for s in toggle.states] == ["off", "on"]


def test_default_table_falls_back_to_indexed_names():
    selector = default_state_table(kinds.SELECTOR, 4)
    assert [s.name for s in selector.states] == ["state_0", "state_1", "state_2", "state_3"]
    long_fader = default_state_table(kinds.FADER_HANDLE, 8)
    assert [s.name for s in long_fader.states] == [f"state_{i}" for i in range(8)]


def test_kinds_without_state_rig_get_no_table():
    assert default_state_table(kinds.KNOB, 61) is None
    assert default_state_table(kinds.STATIC, 1) is None
    assert default_state_table(kinds.BACKDROP, 1) is None
    assert default_state_table(kinds.SOCKET, 1) is None


def _lamp_table():
    return StateTable(states=[
        State("unlit", (emission_strength("mat_led", 0.0),) + visibility("halo", False)),
        State("lit", (emission_strength("mat_led", 30.0),) + visibility("halo", True)),
    ])


def test_compile_emits_one_key_per_action_per_frame():
    keys = _lamp_table().compile()
    assert len(keys) == 6  # 2 states x (1 emission + 2 visibility)
    assert {k.frame for k in keys} == {0, 1}
    lit_emission = [k for k in keys if k.frame == 1 and k.id_type == "materials"]
    assert lit_emission[0].value == 30.0
    assert 'nodes["Emission"]' in lit_emission[0].data_path


def test_compile_rejects_partial_tables():
    # 'lit' keys the emission but 'unlit' does not: constant interpolation
    # would leak frame 1's look into frame 0 -> must refuse.
    table = StateTable(states=[
        State("unlit"),
        State("lit", (emission_strength("mat_led", 30.0),)),
    ])
    with pytest.raises(ValueError, match="not total"):
        table.compile()


def test_compile_rejects_unknown_id_type():
    table = StateTable(states=[
        State("only", (StateAction("scenes", "Scene", "frame_start", 1.0),)),
    ])
    with pytest.raises(ValueError, match="id_type"):
        table.compile()


def test_action_constructors():
    show, hide = visibility("cap", True)
    assert show.data_path == "hide_render" and show.value == 0.0
    move = location("handle", axis=2, value=0.35)
    assert (move.data_path, move.index, move.value) == ("location", 2, 0.35)
    shape = shape_key_value("cap", "pressed", 1.0)
    assert 'key_blocks["pressed"]' in shape.data_path
    color = emission_color("mat_led", (1.0, 0.5, 0.0, 1.0))
    assert color.value == (1.0, 0.5, 0.0, 1.0)


def test_json_roundtrip_preserves_tuples():
    table = StateTable(states=[
        State("unlit", (emission_color("mat_led", (0.1, 0.1, 0.1, 1.0)),)),
        State("lit", (emission_color("mat_led", (1.0, 0.5, 0.0, 1.0)),)),
    ])
    back = StateTable.from_json(table.to_json())
    assert back == table
    assert back.states[1].actions[0].value == (1.0, 0.5, 0.0, 1.0)


def test_from_json_rejects_garbage():
    with pytest.raises(ValueError, match="JSON"):
        StateTable.from_json("{nope")


def test_frames_property():
    assert _lamp_table().frames == 2
    assert state_tables.StateTable().frames == 0


# -- editing (the state playground) -----------------------------------------


def _named_only():
    """A named-but-empty table, as default_state_table seeds it."""
    return StateTable(states=[State("off"), State("on")])


def test_add_actions_keeps_the_table_total():
    table = _named_only()
    table.add_actions([emission_strength("mat_led", 0.0)])
    # Both states now carry the channel, so compile() no longer refuses.
    assert len(table.channels()) == 1
    keys = table.compile()
    assert len(keys) == 2 and {k.frame for k in keys} == {0, 1}


def test_add_actions_rejects_duplicate_channel():
    table = _named_only()
    table.add_actions([emission_strength("mat_led", 0.0)])
    with pytest.raises(ValueError, match="already in the table"):
        table.add_actions([emission_strength("mat_led", 5.0)])


def test_add_actions_rejects_empty_table():
    with pytest.raises(ValueError, match="no states"):
        StateTable().add_actions([emission_strength("mat_led", 0.0)])


def test_set_value_only_touches_one_state():
    table = _named_only()
    table.add_actions([emission_strength("mat_led", 0.0)])
    channel = table.channels()[0]
    table.set_value(1, channel, 30.0)
    assert table.value_in(0, channel) == 0.0
    assert table.value_in(1, channel) == 30.0
    lit = [k for k in table.compile() if k.frame == 1]
    assert lit[0].value == 30.0


def test_set_value_rejects_missing_channel():
    table = _named_only()
    bogus = ("materials", "nope", "x", -1)
    with pytest.raises(KeyError):
        table.set_value(0, bogus, 1.0)


def test_remove_channel_drops_it_from_every_state():
    table = _named_only()
    table.add_actions([emission_strength("mat_led", 0.0)])
    table.add_actions(visibility("halo", True))
    assert len(table.channels()) == 3  # emission + hide_render + hide_viewport
    table.remove_channel(("materials", "mat_led",
                          'node_tree.nodes["Emission"].inputs["Strength"].default_value',
                          -1))
    assert len(table.channels()) == 2
    assert all(not any(a.id_type == "materials" for a in s.actions) for s in table.states)


def test_controls_collapse_the_visibility_pair():
    table = _named_only()
    table.add_actions(visibility("halo", True))          # two channels
    table.add_actions([emission_strength("mat_led", 0.0)])
    assert len(table.channels()) == 3
    controls = table.controls()
    assert len(controls) == 2                             # visibility is one unit
    assert len(controls[0]) == 2                          # hide_render + hide_viewport
    assert len(controls[1]) == 1


def test_describe_channel_reads_in_designer_terms():
    d = state_tables.describe_channel
    assert d(("objects", "cap", "hide_render", -1)) == "cap: visibility"
    assert "emission strength" in d(emission_strength("led", 0.0).key())
    assert "emission colour" in d(emission_color("led", (0, 0, 0, 1)).key())
    assert d(location("handle", 2, 0.0).key()) == "handle: location Z"
    assert "shape key 'pressed'" in d(shape_key_value("cap", "pressed", 1.0).key())
