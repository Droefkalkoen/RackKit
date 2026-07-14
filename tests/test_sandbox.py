"""The Lua sandbox: side-effect-free execution, isolation between reads."""

import pytest

from reblend.project.lua_reader import LuaConfigError, read_device_2d


def _write(tmp_path, body: str):
    path = tmp_path / "device_2D.lua"
    path.write_text(f'format_version = "2.0"\nfront = {{}}\n{body}', encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "body",
    [
        'os.execute("true")',
        'io.open("/etc/hostname")',
        'require("ffi")',
        "dofile('/etc/hostname')",
        "print('hello')",
    ],
)
def test_dangerous_globals_unavailable(tmp_path, body):
    with pytest.raises(LuaConfigError, match="Lua error"):
        read_device_2d(_write(tmp_path, body))


def test_safe_stdlib_available(tmp_path):
    # Real-world files compute offsets; math/string/table must work.
    path = _write(
        tmp_path,
        "front.k = { offset = { 100 + math.floor(10.5), 2 * 50 },"
        ' { path = string.upper("knob"), frames = #("abc") } }',
    )
    device = read_device_2d(path)
    node = device.panels["front"]["k"]
    assert node.offset == (110, 100)
    assert node.graphics[0].path == "KNOB"
    assert node.frames == 3


def test_globals_do_not_leak_between_reads(tmp_path):
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir(), second.mkdir()
    (first / "device_2D.lua").write_text(
        'format_version = "2.0"\nleaked = 42\nfront = {}', encoding="utf-8"
    )
    (second / "device_2D.lua").write_text(
        'format_version = "2.0"\nfront = { k = { offset = { leaked or 7, 0 },'
        ' { path = "p" } } }',
        encoding="utf-8",
    )
    read_device_2d(first / "device_2D.lua")
    device = read_device_2d(second / "device_2D.lua")
    assert device.panels["front"]["k"].offset == (7, 0)


def test_sandbox_base_is_not_reported_as_globals(tmp_path):
    path = _write(tmp_path, "")
    device = read_device_2d(path)
    # Only the panels the file defines come back — no math/string/jbox noise.
    assert set(device.panels) == {"front"}
