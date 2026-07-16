"""The N-panel "RE" tab: project, element list, validation report (§8).

Panels draw state and fire operators; they hold no logic of their own, so
everything visible here is equally reachable headlessly (§7).
"""

from __future__ import annotations

import bpy

from ..model import schema

_SEVERITY_ICONS = {"error": "CANCEL", "warning": "ERROR"}  # ERROR = the ⚠ icon
_KIND_ICONS = {
    "knob": "MESH_CIRCLE",
    "button_toggle": "CHECKBOX_HLT",
    "button_momentary": "RADIOBUT_ON",
    "fader_handle": "ARROW_LEFTRIGHT",
    "selector": "LINENUMBERS_ON",
    "lamp": "LIGHT",
    "backdrop": "MESH_PLANE",
    "static": "OBJECT_HIDDEN",
    "socket": "PLUGIN",
}


class REBLEND_PT_project(bpy.types.Panel):
    bl_label = "RE Project"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RE"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.reblend
        layout.prop(settings, "project_root")
        row = layout.row(align=True)
        row.prop(settings, "ppb")
        row.prop(settings, "rack_units")
        layout.operator("reblend.import_project", icon="IMPORT")

        layout.separator()
        layout.operator("reblend.validate", icon="CHECKMARK")
        col = layout.column(align=True)
        col.operator("reblend.render_elements", text="Render All",
                     icon="RENDER_ANIMATION").scope = "ALL"
        col.operator("reblend.render_elements", text="Render Active",
                     icon="RENDER_STILL").scope = "ACTIVE"


class REBLEND_PT_elements(bpy.types.Panel):
    bl_label = "RE Elements"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RE"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.reblend
        elements = [c for c in bpy.data.collections if schema.is_element(c)]
        if not elements:
            layout.label(text="No elements — import a project", icon="INFO")
            return

        unsized = sum(
            1 for c in elements if not schema.props_to_data(c).has_frame_size
        )
        for collection in sorted(elements, key=lambda c: c.name):
            data = schema.props_to_data(collection)
            row = layout.row(align=True)
            row.label(text=data.path or collection.name,
                      icon=_KIND_ICONS.get(data.kind, "QUESTION"))
            row.label(text=f"{data.kind} · {data.frames}f")
            if not data.has_frame_size:
                row.label(text="", icon="ERROR")

        # Frame pixel size isn't in the RE Lua (§5.2), so fresh imports land
        # unsized. Offer a bulk fill so the designer isn't hand-editing dozens
        # of elements to clear the expected per-element warnings.
        if unsized:
            box = layout.box()
            box.label(text=f"{unsized} element(s) need a frame size",
                      icon="ERROR")
            row = box.row(align=True)
            row.prop(settings, "frame_w")
            row.prop(settings, "frame_h")
            box.operator("reblend.set_frame_size",
                         text="Set All Missing Sizes",
                         icon="FULLSCREEN_ENTER").scope = "MISSING"

        active = context.collection
        if active is not None and schema.is_element(active):
            box = layout.box()
            data = schema.props_to_data(active)
            box.label(text=f"Active: {data.path}", icon="OUTLINER_COLLECTION")
            box.label(text=f"node '{data.node}' · {data.frame_w}x{data.frame_h}px")
            row = box.row(align=True)
            row.prop(active, '["re_frame_w"]', text="Frame W")
            row.prop(active, '["re_frame_h"]', text="Frame H")
            box.operator("reblend.generate_rig", icon="DRIVER")


class REBLEND_PT_validation(bpy.types.Panel):
    bl_label = "Validation Report"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RE"

    def draw(self, context):
        layout = self.layout
        findings = context.scene.reblend.findings
        if not findings:
            layout.label(text="No report yet — run Validate", icon="INFO")
            return

        errors = sum(1 for f in findings if f.severity == "error")
        layout.label(
            text=f"{errors} error(s), {len(findings) - errors} warning(s)",
            icon="CANCEL" if errors else "CHECKMARK",
        )
        # Collapse repeats of the same code (e.g. an unsized fresh import fires
        # one frame-size warning per element) into a single counted box, so a
        # wall of identical findings can't bury the ones that differ.
        for (severity, code), group in _group_by_code(findings):
            box = layout.box()
            icon = _SEVERITY_ICONS.get(severity, "QUESTION")
            if len(group) == 1:
                finding = group[0]
                box.label(text=f"{code}: {finding.subject or finding.panel}",
                          icon=icon)
                for line in _wrap(finding.message):
                    box.label(text=line)
                continue

            box.label(text=f"{code}: {len(group)} items", icon=icon)
            messages = {f.message for f in group}
            if len(messages) == 1:
                # Identical text (the frame-size case): show it once, then
                # list who it applies to.
                for line in _wrap(next(iter(messages))):
                    box.label(text=line)
                subjects = ", ".join(
                    sorted(f.subject or f.panel for f in group if f.subject or f.panel)
                )
                for line in _wrap(subjects):
                    box.label(text=line, icon="BLANK1")
            else:
                # Same code, different detail per subject: keep every line.
                for finding in group:
                    who = finding.subject or finding.panel
                    prefix = f"{who}: " if who else ""
                    for line in _wrap(f"{prefix}{finding.message}"):
                        box.label(text=line, icon="BLANK1")


def _group_by_code(findings):
    """Group findings by (severity, code), preserving first-seen order.

    Returns a list of ((severity, code), [findings]) so the report can show one
    box per code with a count, instead of one box per finding.
    """
    groups: dict[tuple[str, str], list] = {}
    for finding in findings:
        groups.setdefault((finding.severity, finding.code), []).append(finding)
    return list(groups.items())


def _wrap(text: str, width: int = 55) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


CLASSES = (REBLEND_PT_project, REBLEND_PT_elements, REBLEND_PT_validation)
