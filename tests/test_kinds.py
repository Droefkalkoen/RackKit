"""Element-kind derivation from hdgui_2D widget types (§4.2, §4.3)."""

from reblend.model import kinds


def test_widget_kind_mapping():
    assert kinds.kind_for_node([("analog_knob", {})], 61) == kinds.KNOB
    assert kinds.kind_for_node([("toggle_button", {})], 2) == kinds.BUTTON_TOGGLE
    assert kinds.kind_for_node([("momentary_button", {})], 2) == kinds.BUTTON_MOMENTARY
    assert kinds.kind_for_node([("step_button", {})], 4) == kinds.SELECTOR
    assert kinds.kind_for_node([("audio_input_socket", {})], 1) == kinds.SOCKET
    assert kinds.kind_for_node([("device_name", {})], 1) == kinds.STATIC


def test_backdrop_wins_over_everything():
    assert kinds.kind_for_node([("analog_knob", {})], 61, is_backdrop=True) == kinds.BACKDROP
    assert kinds.kind_for_node([], 1, is_backdrop=True) == kinds.BACKDROP


def test_sequence_fader_baked_frames_vs_moving_handle():
    # handle_size = 0 (or absent): N baked frames -> state rig (risk §10.4).
    assert kinds.kind_for_node([("sequence_fader", {"handle_size": 0})], 3) == kinds.FADER_HANDLE
    assert kinds.kind_for_node([("sequence_fader", {})], 3) == kinds.FADER_HANDLE
    # handle_size > 0: 1-frame handle the SDK moves itself -> static art.
    assert kinds.kind_for_node([("sequence_fader", {"handle_size": 60})], 1) == kinds.STATIC


def test_multiframe_static_decoration_is_a_lamp():
    assert kinds.kind_for_node([("static_decoration", {})], 2) == kinds.LAMP
    assert kinds.kind_for_node([("static_decoration", {})], 1) == kinds.STATIC


def test_unbound_node_defaults():
    assert kinds.kind_for_node([], 1) == kinds.STATIC
    assert kinds.kind_for_node([], 2) == kinds.LAMP


def test_unknown_widget_defaults_to_static():
    assert kinds.kind_for_node([("some_future_widget", {})], 1) == kinds.STATIC


def test_interactive_widget_outranks_static_companion():
    widgets = [("static_decoration", {}), ("toggle_button", {})]
    assert kinds.kind_for_node(widgets, 2) == kinds.BUTTON_TOGGLE


def test_rig_flavours():
    assert kinds.rig_for_kind(kinds.KNOB) == kinds.RIG_DRIVER
    for kind in (kinds.BUTTON_TOGGLE, kinds.BUTTON_MOMENTARY, kinds.FADER_HANDLE,
                 kinds.SELECTOR, kinds.LAMP):
        assert kinds.rig_for_kind(kind) == kinds.RIG_STATES
    for kind in (kinds.STATIC, kinds.BACKDROP, kinds.SOCKET):
        assert kinds.rig_for_kind(kind) is None
