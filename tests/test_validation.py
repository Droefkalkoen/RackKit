"""The validation report (§6.3): every row of the cross-check table.

Strategy: build a *correct* project on disk (fixture Lua + generated sheets
at the right sizes), assert the report is completely clean, then break one
thing per test and assert exactly that finding appears. A validator that
cannot produce a clean pass on a correct project is as broken as one that
misses an error.
"""

import shutil
import struct
import zlib

import pytest

from reblend.project import validation
from reblend.project.link import load_project
from reblend.project.png_meta import write_rgba_png
from reblend.project.validation import SceneInfo, validate_link

#: Per-frame pixel sizes for every sheet in the silence_detector fixture —
#: all multiples of 5 (M0 finding 6). Backdrops define a 2U device.
SHEET_SIZES = {
    "Panel_Front": (3770, 690),
    "Panel_Back": (3770, 690),
    "Panel_Folded_Front": (3770, 130),
    "Panel_Folded_Back": (3770, 130),
    "Knob_65x65_61frames": (65, 65),
    "Button_50x35_2frames": (50, 35),
    "Lamp_15x15_2frames": (15, 15),
    "Tape_Horizontal_1frames": (390, 40),
    "Fader_25x60_3frames": (25, 60),
    "SharedAudioJack": (105, 105),
}


@pytest.fixture
def project_dir(silence_detector, tmp_path):
    """Fixture project with every sheet rendered at correct dimensions."""
    root = tmp_path / "device"
    shutil.copytree(silence_detector, root)
    link = load_project(root)
    for spec in link.specs:
        w, h = SHEET_SIZES[spec.path]
        write_rgba_png(root / "GUI2D" / f"{spec.path}.png", w, h * spec.frames,
                       bytes(w * h * spec.frames * 4))
    return root


def make_scene(root):
    """(link, elements) as the Blender side would hand them to validation."""
    link = load_project(root)
    return link, [spec.to_element_data() for spec in link.specs]


def codes(report):
    return [f.code for f in report.findings]


# ---------------------------------------------------------------------------


def test_correct_project_is_completely_clean(project_dir):
    link, elements = make_scene(project_dir)
    report = validate_link(link, elements, SceneInfo(view_transform="Standard"))
    assert report.findings == []
    assert report.ok


def test_missing_art_is_an_error(project_dir):
    link, elements = make_scene(project_dir)
    elements = [e for e in elements if e.path != "Knob_65x65_61frames"]
    report = validate_link(link, elements)
    missing = [f for f in report.errors if f.code == "missing-art"]
    assert len(missing) == 1
    assert missing[0].subject == "Knob_65x65_61frames"
    assert "knob_threshold" in missing[0].message


def test_orphan_element_is_a_warning(project_dir):
    link, elements = make_scene(project_dir)
    elements.append(validation.schema.ElementData(node="ghost", path="Unused_Thing"))
    report = validate_link(link, elements)
    assert "orphan-element" in codes(report)
    assert report.ok  # warning, not error


def test_frame_count_mismatch_is_an_error(project_dir):
    link, elements = make_scene(project_dir)
    next(e for e in elements if e.path == "Knob_65x65_61frames").frames = 31
    report = validate_link(link, elements)
    assert any(f.code == "frame-count" and f.severity == "error" for f in report.findings)


def test_widget_pointing_at_missing_node_is_an_error(project_dir):
    hdgui = project_dir / "GUI2D" / "hdgui_2D.lua"
    hdgui.write_text(
        hdgui.read_text(encoding="utf-8").replace(
            'node = "knob_threshold"', 'node = "knob_gone"'
        ),
        encoding="utf-8",
    )
    link, elements = make_scene(project_dir)
    report = validate_link(link, elements)
    assert any(f.code == "widget-node" and f.subject == "knob_gone" for f in report.errors)


def test_frames_vs_steps_mismatch_is_a_warning(project_dir):
    device = project_dir / "GUI2D" / "device_2D.lua"
    device.write_text(
        device.read_text(encoding="utf-8").replace(
            '{ path = "Fader_25x60_3frames", frames = 3 }',
            '{ path = "Fader_25x60_3frames", frames = 4 }',
        ),
        encoding="utf-8",
    )
    link, elements = make_scene(project_dir)
    report = validate_link(link, elements)
    steps = [f for f in report.warnings if f.code == "steps"]
    assert steps and "builtin_onoffbypass" in steps[0].message


def test_png_dimension_mismatch_is_an_error(project_dir):
    write_rgba_png(project_dir / "GUI2D" / "Knob_65x65_61frames.png",
                   65, 65 * 61 - 65, bytes(65 * 65 * 60 * 4))  # one frame short
    link, elements = make_scene(project_dir)
    # keep the declared size: the probe won't fill it from the short sheet
    knob = next(e for e in elements if e.path == "Knob_65x65_61frames")
    knob.frame_w, knob.frame_h = 65, 65
    report = validate_link(link, elements)
    assert any(f.code == "png-dims" and f.severity == "error" for f in report.findings)


def test_missing_png_is_a_warning_until_first_render(project_dir):
    (project_dir / "GUI2D" / "Lamp_15x15_2frames.png").unlink()
    link, elements = make_scene(project_dir)
    lamp = next(e for e in elements if e.path == "Lamp_15x15_2frames")
    lamp.frame_w, lamp.frame_h = 15, 15
    report = validate_link(link, elements)
    assert any(f.code == "png-missing" and f.severity == "warning" for f in report.findings)


def test_case_mismatch_is_an_error(project_dir):
    gui2d = project_dir / "GUI2D"
    (gui2d / "Lamp_15x15_2frames.png").rename(gui2d / "lamp_15x15_2frames.png")
    link, elements = make_scene(project_dir)
    lamp = next(e for e in elements if e.path == "Lamp_15x15_2frames")
    lamp.frame_w, lamp.frame_h = 15, 15
    report = validate_link(link, elements)
    assert any(f.code == "case" and f.severity == "error" for f in report.findings)


def test_unset_frame_size_is_a_warning(project_dir):
    (project_dir / "GUI2D" / "Lamp_15x15_2frames.png").unlink()
    link, elements = make_scene(project_dir)
    report = validate_link(link, elements)
    assert any(f.code == "frame-size" and f.subject == "Lamp_15x15_2frames"
               for f in report.warnings)


def test_frame_bounds_not_multiple_of_five_is_an_error(project_dir):
    link, elements = make_scene(project_dir)
    knob = next(e for e in elements if e.path == "Knob_65x65_61frames")
    knob.frame_w = knob.frame_h = 63
    report = validate_link(link, elements)
    bounds = [f for f in report.errors if f.code == "frame-bounds"]
    assert len(bounds) == 2  # width and height each flagged
    # and the sheet on disk (65 px wide) now disagrees with the declared size
    assert any(f.code == "png-dims" for f in report.errors)


def test_reframed_artifact_is_an_error(project_dir):
    write_rgba_png(project_dir / "GUI2D" / "Knob_65x65_61frames-reframed.png",
                   65, 65, bytes(65 * 65 * 4))
    link, elements = make_scene(project_dir)
    report = validate_link(link, elements)
    assert any(f.code == "reframed" for f in report.errors)


def test_non_standard_view_transform_is_a_warning(project_dir):
    link, elements = make_scene(project_dir)
    report = validate_link(link, elements, SceneInfo(view_transform="AgX"))
    assert any(f.code == "view-transform" for f in report.warnings)
    assert validate_link(link, elements, SceneInfo(view_transform=None)).findings == []


def test_element_outside_panel_is_a_warning(project_dir):
    device = project_dir / "GUI2D" / "device_2D.lua"
    device.write_text(
        device.read_text(encoding="utf-8").replace(
            "offset = { 1810, 145 }", "offset = { 3760, 145 }"
        ),
        encoding="utf-8",
    )
    link, elements = make_scene(project_dir)
    report = validate_link(link, elements)
    assert any(f.code == "bounds" and f.subject == "Button_50x35_2frames"
               for f in report.warnings)


def test_overlapping_elements_are_a_warning(project_dir):
    device = project_dir / "GUI2D" / "device_2D.lua"
    device.write_text(
        device.read_text(encoding="utf-8").replace(
            "offset = { 30, 0 }", "offset = { 5, 0 }"
        ),
        encoding="utf-8",
    )
    link, elements = make_scene(project_dir)
    report = validate_link(link, elements)
    overlap = [f for f in report.warnings if f.code == "overlap"]
    assert overlap and "lamp_signal" in overlap[0].subject


def test_kind_mismatch_is_a_warning(project_dir):
    link, elements = make_scene(project_dir)
    next(e for e in elements if e.path == "Knob_65x65_61frames").kind = "lamp"
    report = validate_link(link, elements)
    assert any(f.code == "kind" and f.subject == "Knob_65x65_61frames"
               for f in report.warnings)


def test_non_rgba_png_is_a_warning(project_dir):
    # Hand-build a 16-bit RGB PNG header: read_png_meta only needs the IHDR.
    def chunk(ctype, payload):
        return (struct.pack(">I", len(payload)) + ctype + payload
                + struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", 390, 40, 16, 2, 0, 0, 0)
    blob = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")
    (project_dir / "GUI2D" / "Tape_Horizontal_1frames.png").write_bytes(blob)

    link, elements = make_scene(project_dir)
    tape = next(e for e in elements if e.path == "Tape_Horizontal_1frames")
    tape.frame_w, tape.frame_h = 390, 40
    report = validate_link(link, elements)
    assert any(f.code == "png-format" for f in report.warnings)


def test_report_severity_partition(project_dir):
    link, elements = make_scene(project_dir)
    elements = [e for e in elements if e.path != "Knob_65x65_61frames"]
    report = validate_link(link, elements, SceneInfo(view_transform="Filmic"))
    assert not report.ok
    assert {f.severity for f in report.errors} == {"error"}
    assert {f.severity for f in report.warnings} == {"warning"}
    assert len(report.errors) + len(report.warnings) == len(report.findings)
