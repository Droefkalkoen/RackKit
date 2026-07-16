"""Scene-level RE-Blend settings and validation-report storage.

Element data lives as ``re_*`` custom properties on element collections
(:mod:`reblend.model.schema`); what lives here is per-scene: the project
link (§4.1) and the last validation report, so the panel can draw it.
"""

from __future__ import annotations

import bpy

from ..model import calibration


#: Signed world axes offered by the Camera Axis / Knob Rotation Axis settings,
#: −Y first so the §4.4 front-view default leads the dropdown.
_AXIS_ITEMS = (
    ("neg_y", "-Y (Front View)", "Look along −Y — Blender's front orthographic view"),
    ("pos_y", "+Y (Back View)", "Look along +Y"),
    ("neg_x", "-X", "Look along −X"),
    ("pos_x", "+X", "Look along +X"),
    ("neg_z", "-Z (Top-Down)", "Look along −Z"),
    ("pos_z", "+Z (Bottom-Up)", "Look along +Z"),
)


class REBLEND_PG_finding(bpy.types.PropertyGroup):
    """One row of the last validation report (mirrors validation.Finding)."""

    severity: bpy.props.StringProperty()
    code: bpy.props.StringProperty()
    message: bpy.props.StringProperty()
    subject: bpy.props.StringProperty()
    panel: bpy.props.StringProperty()


class REBLEND_PG_settings(bpy.types.PropertyGroup):
    project_root: bpy.props.StringProperty(
        name="RE Project",
        description="Root of the linked RE project (the directory containing GUI2D/)",
        subtype="DIR_PATH",
    )
    ppb: bpy.props.FloatProperty(
        name="Pixels / Unit",
        description="World calibration: panel pixels per Blender unit (§4.4)",
        default=calibration.DEFAULT_PPB,
        min=1.0,
    )
    rack_units: bpy.props.IntProperty(
        name="Rack Units",
        description="Device height, used for panel guides when no backdrop sheet exists yet",
        default=1,
        min=1,
    )
    origin: bpy.props.EnumProperty(
        name="World Origin",
        description="Which panel pixel the Blender world origin lands on when "
                    "placing elements (§4.4). This only moves guides and "
                    "registration empties in Blender — re_offset and the RE Lua "
                    "stay top-left panel pixels. Change it, then Re-import & "
                    "Reposition to move existing elements onto the new origin",
        items=(
            (calibration.ORIGIN_TOP_LEFT, "Top-Left of Device",
             "Panel pixel (0,0) at the world origin — the native RE convention"),
            (calibration.ORIGIN_TOP_CENTER, "Top-Center",
             "World origin at the middle of the panel's top edge"),
            (calibration.ORIGIN_CENTER, "Center",
             "World origin at the panel centre"),
        ),
        default=calibration.ORIGIN_TOP_LEFT,
    )
    reposition_geometry: bpy.props.BoolProperty(
        name="Move Geometry Too",
        description="When Re-import & Reposition moves an element, also shift "
                    "its modelled geometry (backdrop plane, control meshes) by "
                    "the same amount so it stays registered to its empty. Turn "
                    "off to move only the registration empties and guide boxes "
                    "and leave your models where they are",
        default=True,
    )
    camera_axis: bpy.props.EnumProperty(
        name="Camera Axis",
        description="World axis each element's render camera looks along (§4.4). "
                    "The default −Y is Blender's front orthographic view; change "
                    "it if the device is modelled facing another way. Applied "
                    "through the registration empty, so per-element tilt still "
                    "works",
        items=_AXIS_ITEMS,
        default=calibration.DEFAULT_CAMERA_AXIS,
    )
    rotation_axis: bpy.props.EnumProperty(
        name="Knob Rotation Axis",
        description="World axis a knob's rotor spins around when Generate Rig "
                    "builds its turntable driver. Auto follows the Camera Axis "
                    "through the registration empty (the rotor faces the camera "
                    "and spins in view) — pick an explicit axis to override",
        items=(("auto", "Auto (Camera Axis)",
                "Spin around the camera axis through the registration empty"),)
              + _AXIS_ITEMS,
        default="auto",
    )
    frame_w: bpy.props.IntProperty(
        name="Frame W",
        description="Per-frame width in pixels applied by Set Frame Size. Frame "
                    "size isn't in the RE Lua (§5.2) — the designer picks it, so "
                    "fresh imports start unsized until this fills them in",
        default=0,
        min=0,
    )
    frame_h: bpy.props.IntProperty(
        name="Frame H",
        description="Per-frame height in pixels applied by Set Frame Size",
        default=0,
        min=0,
    )
    inactive_render: bpy.props.EnumProperty(
        name="Inactive Elements",
        description="How the other RE Elements behave while one element is "
                    "rendered (§5.1). Shadow-only keeps neighbouring geometry "
                    "shadowing the active element without appearing in its sheet",
        items=(
            ("SHADOW", "Cast Shadows",
             "Invisible to the camera but still cast shadows on the active "
             "element (and catch none themselves) — the default (Cycles ray "
             "visibility)"),
            ("HIDDEN", "Hidden",
             "Excluded from the render entirely; the active element renders alone"),
        ),
        default="SHADOW",
    )
    findings: bpy.props.CollectionProperty(type=REBLEND_PG_finding)
    findings_index: bpy.props.IntProperty(default=0)


def store_report(settings: REBLEND_PG_settings, findings) -> None:
    settings.findings.clear()
    for finding in findings:
        row = settings.findings.add()
        row.severity = finding.severity
        row.code = finding.code
        row.message = finding.message
        row.subject = finding.subject
        row.panel = finding.panel


def attach() -> None:
    bpy.types.Scene.reblend = bpy.props.PointerProperty(type=REBLEND_PG_settings)


def detach() -> None:
    del bpy.types.Scene.reblend


CLASSES = (REBLEND_PG_finding, REBLEND_PG_settings)
