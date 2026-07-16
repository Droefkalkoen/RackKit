"""RE-Blend operators: import, validate, render, rig generation.

UI-stateless by design (§7): every operator reads its inputs from scene
properties and its arguments, never from panel state, so the same operators
can be driven headlessly. The Blender-independent work (parsing, correlation,
cross-checking) all happens in the pure layers; these operators only
materialise the results into the scene and report.
"""

from __future__ import annotations

from pathlib import Path

import bpy
from mathutils import Vector

from ..model import calibration, kinds, rigs, schema, state_tables
from ..project import validation
from ..project.link import ElementSpec, ProjectLink, load_project
from ..project.lua_reader import LuaConfigError
from ..render import renderer
from . import props

#: Root collection name per panel (§4.2).
PANEL_ROOTS = {
    "front": "RE Front",
    "back": "RE Back",
    "folded_front": "RE Folded Front",
    "folded_back": "RE Folded Back",
}


def _settings(context):
    return context.scene.reblend


def _project_root(context) -> Path:
    raw = _settings(context).project_root
    if not raw:
        raise LuaConfigError("(unset)", "no RE project linked — set the project root first")
    return Path(bpy.path.abspath(raw))


def _element_collections() -> list[bpy.types.Collection]:
    return [c for c in bpy.data.collections if schema.is_element(c)]


def _collection_by_path(path: str) -> bpy.types.Collection | None:
    for collection in _element_collections():
        if str(collection.get("re_path", "")) == path:
            return collection
    return None


class REBLEND_OT_import_project(bpy.types.Operator):
    """Import (or re-read) the linked RE project's GUI2D config (§6.1).

    Read-only towards the project: parses device_2D.lua + hdgui_2D.lua and
    materialises panel guides, element collections with bounding boxes,
    registration empties, filled re_* properties, and default rigs. Lua files
    are never written (that is M2's patch mode).
    """

    bl_idname = "reblend.import_project"
    bl_label = "Import RE Project"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            link = load_project(_project_root(context))
        except LuaConfigError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        settings = _settings(context)
        created = updated = 0
        for spec in link.specs:
            was_new = self._materialise(context, link, spec, settings.ppb,
                                        settings.rack_units)
            created += was_new
            updated += not was_new
        self._panel_guides(context, link, settings.ppb, settings.rack_units)

        self.report(
            {"INFO"},
            f"imported {link.root.name}: {created} new elements, {updated} updated",
        )
        return {"FINISHED"}

    # -- materialisation ----------------------------------------------------

    def _materialise(self, context, link: ProjectLink, spec: ElementSpec,
                     ppb: float, rack_units: int) -> bool:
        collection = _collection_by_path(spec.path)
        is_new = collection is None
        if is_new:
            collection = bpy.data.collections.new(spec.path)

        # Fill/update the Lua-derived properties. User-owned properties
        # (sweep, states, registration) are only seeded on creation, and a
        # frame size the user already chose is never clobbered by "unknown".
        keep = set()
        if not is_new:
            keep = {"re_sweep_deg", "re_states", "re_registration"}
            if spec.frame_w == 0:
                keep |= {"re_frame_w", "re_frame_h"}
        for key, value in schema.data_to_props(spec.to_element_data()).items():
            if key not in keep:
                collection[key] = value
        if is_new:
            table = state_tables.default_state_table(spec.kind, spec.frames)
            collection["re_states"] = table.to_json() if table else ""

        for panel in spec.panels:
            root = self._panel_root(context, panel)
            if collection.name not in {c.name for c in root.children}:
                root.children.link(collection)

        if is_new:
            self._registration_empty(collection, spec, ppb)
            self._guide_boxes(collection, spec, ppb)
        return is_new

    def _panel_root(self, context, panel: str) -> bpy.types.Collection:
        name = PANEL_ROOTS[panel]
        root = bpy.data.collections.get(name)
        if root is None:
            root = bpy.data.collections.new(name)
        if name not in {c.name for c in context.scene.collection.children}:
            context.scene.collection.children.link(root)
        return root

    def _registration_empty(self, collection, spec: ElementSpec, ppb: float) -> None:
        primary = spec.placements[0]
        if spec.frame_w and spec.frame_h:
            cx, cy = calibration.element_center_px(primary.x, primary.y,
                                                   spec.frame_w, spec.frame_h)
        else:
            cx, cy = primary.x, primary.y
        empty = bpy.data.objects.new(f"reg_{spec.path}", None)
        empty.empty_display_type = "PLAIN_AXES"
        empty.empty_display_size = 0.1
        empty.location = Vector(calibration.panel_px_to_world(cx, cy, ppb))
        collection.objects.link(empty)
        collection["re_registration"] = empty.name

    def _guide_boxes(self, collection, spec: ElementSpec, ppb: float) -> None:
        """Wireframe rects at each declared placement — never rendered."""
        if not (spec.frame_w and spec.frame_h):
            return
        for index, placement in enumerate(spec.placements):
            corners_px = (
                (placement.x, placement.y),
                (placement.x + spec.frame_w, placement.y),
                (placement.x + spec.frame_w, placement.y + spec.frame_h),
                (placement.x, placement.y + spec.frame_h),
            )
            verts = [calibration.panel_px_to_world(x, y, ppb) for x, y in corners_px]
            mesh = bpy.data.meshes.new(f"box_{spec.path}_{index}")
            mesh.from_pydata(verts, [(0, 1), (1, 2), (2, 3), (3, 0)], [])
            obj = bpy.data.objects.new(mesh.name, mesh)
            obj.display_type = "WIRE"
            obj.hide_render = True
            obj.hide_select = True
            collection.objects.link(obj)

    def _panel_guides(self, context, link: ProjectLink, ppb: float,
                      rack_units: int) -> None:
        for panel in link.device.panels:
            name = f"RE Panel {panel}"
            if name in bpy.data.objects:
                continue
            size = self._panel_size(link, panel, rack_units)
            corners_px = ((0, 0), (size.width, 0),
                          (size.width, size.height), (0, size.height))
            verts = [calibration.panel_px_to_world(x, y, ppb) for x, y in corners_px]
            mesh = bpy.data.meshes.new(name)
            mesh.from_pydata(verts, [(0, 1), (1, 2), (2, 3), (3, 0)], [])
            obj = bpy.data.objects.new(name, mesh)
            obj.display_type = "WIRE"
            obj.hide_render = True
            obj.hide_select = True
            self._panel_root(context, panel).objects.link(obj)

    def _panel_size(self, link: ProjectLink, panel: str,
                    rack_units: int) -> calibration.PanelSize:
        for spec in link.specs:
            if spec.kind == kinds.BACKDROP and panel in spec.panels and spec.frame_w:
                return calibration.PanelSize(spec.frame_w, spec.frame_h)
        return calibration.panel_size_px(panel, rack_units)


class REBLEND_OT_validate(bpy.types.Operator):
    """Run the full cross-check table (§6.3) and store the report."""

    bl_idname = "reblend.validate"
    bl_label = "Validate"

    def execute(self, context):
        try:
            link = load_project(_project_root(context))
        except LuaConfigError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        elements = [schema.props_to_data(c) for c in _element_collections()]
        scene_info = validation.SceneInfo(
            view_transform=context.scene.view_settings.view_transform
        )
        report = validation.validate_link(link, elements, scene_info)
        props.store_report(_settings(context), report.findings)

        if report.ok and not report.warnings:
            self.report({"INFO"}, "validation clean: no errors, no warnings")
        else:
            level = {"INFO"} if report.ok else {"WARNING"}
            self.report(
                level,
                f"validation: {len(report.errors)} error(s), "
                f"{len(report.warnings)} warning(s) — see the RE panel",
            )
        return {"FINISHED"}


class REBLEND_OT_render_elements(bpy.types.Operator):
    """Batch-render element sheets into the linked project's GUI2D (§5.1)."""

    bl_idname = "reblend.render_elements"
    bl_label = "Render Elements"

    scope: bpy.props.EnumProperty(
        name="Scope",
        items=(
            ("ALL", "All", "Every RE Element in the scene"),
            ("ACTIVE", "Active", "Only the active collection's element"),
        ),
        default="ALL",
    )

    def execute(self, context):
        try:
            root = _project_root(context)
        except LuaConfigError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        out_dir = root / "GUI2D"

        if self.scope == "ACTIVE":
            active = context.collection
            if active is None or not schema.is_element(active):
                self.report({"ERROR"}, "active collection is not an RE Element")
                return {"CANCELLED"}
            collections = [active]
        else:
            collections = _element_collections()
        if not collections:
            self.report({"ERROR"}, "no RE Elements in the scene — import the project first")
            return {"CANCELLED"}

        settings = _settings(context)
        results = renderer.render_elements(
            context.scene, collections, out_dir, ppb=settings.ppb
        )
        findings = [f for result in results for f in result.findings]
        props.store_report(settings, findings)

        failed = [r.element for r in results if not r.ok]
        if failed:
            self.report(
                {"ERROR"},
                f"rendered {len(results) - len(failed)}/{len(results)} sheets; "
                f"failed: {', '.join(failed)} — see the RE panel",
            )
        else:
            self.report({"INFO"}, f"rendered {len(results)} sheet(s) into {out_dir}")
        return {"FINISHED"}


class REBLEND_OT_generate_rig(bpy.types.Operator):
    """(Re)generate the active element's rig from its re_* properties (§4.3).

    Knobs: rotation driver on the active object (the rotating part), around
    the registration empty's view axis. Multi-state kinds: the element's
    state table applied as constant-interpolation keyframes.
    """

    bl_idname = "reblend.generate_rig"
    bl_label = "Generate Rig"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        collection = context.collection
        if collection is None or not schema.is_element(collection):
            self.report({"ERROR"}, "active collection is not an RE Element")
            return {"CANCELLED"}
        data = schema.props_to_data(collection)
        rig = kinds.rig_for_kind(data.kind)

        if rig == kinds.RIG_DRIVER:
            rotor = context.active_object
            if rotor is None:
                self.report({"ERROR"}, "select the knob's rotating part first")
                return {"CANCELLED"}
            axis = self._knob_axis(collection)
            try:
                rigs.ensure_turntable_driver(
                    rotor,
                    frames=data.frames,
                    sweep_deg=float(collection.get("re_sweep_deg",
                                                   calibration.DEFAULT_SWEEP_DEG)),
                    axis=axis,
                )
            except ValueError as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            self.report({"INFO"}, f"turntable driver on '{rotor.name}': "
                                  f"{data.frames} frames")
            return {"FINISHED"}

        if rig == kinds.RIG_STATES:
            raw = str(collection.get("re_states", ""))
            if not raw:
                self.report({"ERROR"}, "element has no state table (re_states)")
                return {"CANCELLED"}
            try:
                table = state_tables.StateTable.from_json(raw)
                keys = table.compile()
                rigs.apply_state_table(table)
            except (ValueError, KeyError) as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            if table.frames != data.frames:
                self.report(
                    {"WARNING"},
                    f"state table has {table.frames} states but re_frames = "
                    f"{data.frames} — fix before rendering",
                )
            elif not keys:
                self.report(
                    {"WARNING"},
                    "state table has named states but no actions yet — add "
                    "visibility/emission/transform actions to each state",
                )
            else:
                self.report({"INFO"}, f"keyed {len(keys)} state action(s) over "
                                      f"{table.frames} frames")
            return {"FINISHED"}

        self.report({"INFO"}, f"'{data.kind}' elements need no rig")
        return {"FINISHED"}

    def _knob_axis(self, collection) -> tuple[float, float, float]:
        """The knob spins around the registration empty's view axis (§4.2)."""
        name = str(collection.get("re_registration", ""))
        empty = bpy.data.objects.get(name)
        if empty is None:
            return tuple(renderer.VIEW_AXIS)
        axis = empty.matrix_world.to_quaternion() @ renderer.VIEW_AXIS
        return tuple(axis.normalized())


CLASSES = (
    REBLEND_OT_import_project,
    REBLEND_OT_validate,
    REBLEND_OT_render_elements,
    REBLEND_OT_generate_rig,
)
