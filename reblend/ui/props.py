"""Scene-level RE-Blend settings and validation-report storage.

Element data lives as ``re_*`` custom properties on element collections
(:mod:`reblend.model.schema`); what lives here is per-scene: the project
link (§4.1) and the last validation report, so the panel can draw it.
"""

from __future__ import annotations

import bpy

from ..model import calibration


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
