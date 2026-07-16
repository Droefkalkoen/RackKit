"""Best-effort steps extraction from motherboard_def.lua."""

import pytest

from reblend.project.lua_reader import LuaConfigError
from reblend.project.motherboard_reader import BUILTIN_STEPS, read_motherboard_steps


def test_fixture_steps(silence_detector):
    steps = read_motherboard_steps(silence_detector / "motherboard_def.lua")
    assert steps["/custom_properties/mode"] == 4
    # unstepped properties don't appear
    assert "/custom_properties/threshold" not in steps
    assert "/custom_properties/silence_switch" not in steps


def test_builtins_are_merged(silence_detector):
    steps = read_motherboard_steps(silence_detector / "motherboard_def.lua")
    for path, count in BUILTIN_STEPS.items():
        assert steps[path] == count


def test_missing_file_raises(tmp_path):
    with pytest.raises(LuaConfigError):
        read_motherboard_steps(tmp_path / "motherboard_def.lua")


def test_degrades_to_builtins_only(tmp_path):
    bare = tmp_path / "motherboard_def.lua"
    bare.write_text("format_version = '3.0'\n", encoding="utf-8")
    assert read_motherboard_steps(bare) == BUILTIN_STEPS
