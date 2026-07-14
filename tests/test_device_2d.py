"""Reading device_2D.lua: nodes, offsets, frame counts, nesting, CableOrigin."""

import pytest

from reblend.project.lua_reader import Graphic, LuaConfigError, read_device_2d


@pytest.fixture
def device(silence_detector):
    return read_device_2d(silence_detector / "GUI2D" / "device_2D.lua")


def test_format_version(device):
    assert device.format_version == "2.0"


def test_all_four_panels_present(device):
    assert set(device.panels) == {"front", "back", "folded_front", "folded_back"}


def test_knob_node(device):
    knob = device.panels["front"]["knob_threshold"]
    assert knob.offset == (950, 120)
    assert knob.graphics == [Graphic(path="Knob_63x63_61frames", frames=61)]
    assert knob.frames == 61


def test_frames_defaults_to_one(device):
    bg = device.panels["front"]["Panel_front_bg"]
    assert bg.offset is None
    assert bg.frames == 1
    assert bg.graphics[0].path == "Panel_Front"


def test_nested_nodes(device):
    group = device.panels["front"]["lamp_group"]
    assert group.offset == (300, 100)
    assert set(group.children) == {"lamp_signal", "lamp_silence"}
    assert group.children["lamp_silence"].offset == (30, 0)
    assert group.children["lamp_silence"].frames == 2


def test_node_lookup_finds_nested(device):
    assert device.node("front", "lamp_silence") is not None
    assert device.node("front", "lamp_silence").frames == 2
    assert device.node("front", "nonexistent") is None


def test_cable_origin_is_plain_node_without_graphics(device):
    origin = device.panels["back"]["CableOrigin"]
    assert origin.offset == (1885, 172)
    assert origin.graphics == []


def test_walk_covers_descendants(device):
    names = {node.name for node in device.panels["front"]["lamp_group"].walk()}
    assert names == {"lamp_group", "lamp_signal", "lamp_silence"}


def test_missing_file_raises(tmp_path):
    with pytest.raises(LuaConfigError, match="cannot read file"):
        read_device_2d(tmp_path / "device_2D.lua")


def test_syntax_error_raises(tmp_path):
    bad = tmp_path / "device_2D.lua"
    bad.write_text('format_version = "2.0"\nfront = {', encoding="utf-8")
    with pytest.raises(LuaConfigError, match="Lua error"):
        read_device_2d(bad)


def test_missing_format_version_raises(tmp_path):
    bad = tmp_path / "device_2D.lua"
    bad.write_text("front = {}", encoding="utf-8")
    with pytest.raises(LuaConfigError, match="format_version"):
        read_device_2d(bad)


def test_invalid_frames_raises(tmp_path):
    bad = tmp_path / "device_2D.lua"
    bad.write_text(
        'format_version = "2.0"\n'
        'front = { k = { offset = {0, 0}, { path = "x", frames = 0 } } }',
        encoding="utf-8",
    )
    with pytest.raises(LuaConfigError, match="invalid frames"):
        read_device_2d(bad)
