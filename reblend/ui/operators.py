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


def _set_world_location(obj, world_co) -> None:
    """Place ``obj`` at a world-space location, honouring any parent transform.

    Assigning ``obj.location`` sets the *local* offset, which lands a parented
    object in the wrong place; rewriting ``matrix_world`` sets the true world
    position and lets Blender back out the local transform.
    """
    matrix = obj.matrix_world.copy()
    matrix.translation = Vector(world_co)
    obj.matrix_world = matrix


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

    reposition: bpy.props.BoolProperty(
        name="Reposition Elements",
        description="Also move existing registration empties and guide boxes "
                    "to match the current Pixels/Unit and World Origin — a "
                    "fresh re-read otherwise leaves already-placed elements "
                    "where they were",
        default=False,
    )

    def execute(self, context):
        try:
            link = load_project(_project_root(context))
        except LuaConfigError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        settings = _settings(context)
        created = updated = 0
        for spec in link.specs:
            was_new = self._materialise(context, link, spec, settings,
                                        self.reposition)
            created += was_new
            updated += not was_new
        self._panel_guides(context, link, settings, self.reposition)

        verb = "re-imported" if self.reposition else "imported"
        placed = f", {updated} repositioned" if self.reposition else ""
        self.report(
            {"INFO"},
            f"{verb} {link.root.name}: {created} new elements, "
            f"{updated} updated{placed}",
        )
        return {"FINISHED"}

    # -- materialisation ----------------------------------------------------

    def _origin_offset(self, link: ProjectLink, settings, panel: str
                       ) -> tuple[float, float]:
        """The world-origin pixel offset for one panel (§4.4)."""
        size = self._panel_size(link, panel, settings.rack_units)
        return calibration.origin_offset_px(settings.origin, size.width,
                                            size.height)

    def _materialise(self, context, link: ProjectLink, spec: ElementSpec,
                     settings, reposition: bool) -> bool:
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
            self._registration_empty(collection, spec, link, settings)
            self._guide_boxes(collection, spec, link, settings)
        elif reposition:
            self._reposition(collection, spec, link, settings)
        return is_new

    def _reposition(self, collection, spec: ElementSpec, link: ProjectLink,
                    settings) -> None:
        """Move an already-materialised element onto the current calibration.

        Re-import keeps the registration empty (it is user-owned calibration),
        so a plain re-read never moves anything. Reposition deliberately snaps
        the element onto the freshly read placement, the current Pixels/Unit
        and the current World Origin.

        Everything is computed in *world* space (via ``matrix_world``), so an
        element whose empty or geometry is parented under an organising master
        empty still lands where it should instead of being nudged by only its
        local offset. With Move Geometry on (the default) the whole element
        travels by the same delta the empty moves, keeping modelled geometry
        registered; with it off only the empty moves. Guide boxes are always
        rebuilt at the new absolute coordinates.
        """
        empty = bpy.data.objects.get(str(collection.get("re_registration", "")))
        if empty is not None and spec.placements:
            primary = spec.placements[0]
            origin = self._origin_offset(link, settings, primary.panel)
            cx, cy = self._center_px(spec, primary)
            target = Vector(
                calibration.panel_px_to_world(cx, cy, settings.ppb, origin))
            delta = target - empty.matrix_world.translation
            if settings.reposition_geometry:
                self._translate_element(collection, delta)
            else:
                _set_world_location(empty, target)
        self._clear_guide_boxes(collection)
        self._guide_boxes(collection, spec, link, settings)

    @staticmethod
    def _translate_element(collection, delta: Vector) -> None:
        """Shift the element's objects by ``delta`` in world space.

        Each element *root* moves; a child parented to another object in the
        same collection is left alone so it rides its parent (moving both would
        double-shift it). A root parented to something *outside* the element —
        e.g. every empty parented under one organising master empty — still
        gets the delta, so those elements are not silently left behind. Guide
        boxes are skipped because reposition rebuilds them at new coordinates.
        """
        if delta.length == 0.0:
            return
        members = set(collection.objects)
        for obj in collection.objects:
            if obj.get("re_guide") == "box":
                continue
            if obj.parent is not None and obj.parent in members:
                continue  # rides an in-collection parent
            _set_world_location(obj, obj.matrix_world.translation + delta)

    def _panel_root(self, context, panel: str) -> bpy.types.Collection:
        name = PANEL_ROOTS[panel]
        root = bpy.data.collections.get(name)
        if root is None:
            root = bpy.data.collections.new(name)
        if name not in {c.name for c in context.scene.collection.children}:
            context.scene.collection.children.link(root)
        return root

    @staticmethod
    def _center_px(spec: ElementSpec, placement) -> tuple[float, float]:
        """Frame centre in panel px, or the raw offset when size is unknown."""
        if spec.frame_w and spec.frame_h:
            return calibration.element_center_px(placement.x, placement.y,
                                                 spec.frame_w, spec.frame_h)
        return (placement.x, placement.y)

    def _registration_empty(self, collection, spec: ElementSpec,
                            link: ProjectLink, settings) -> None:
        primary = spec.placements[0]
        origin = self._origin_offset(link, settings, primary.panel)
        cx, cy = self._center_px(spec, primary)
        empty = bpy.data.objects.new(f"reg_{spec.path}", None)
        empty.empty_display_type = "PLAIN_AXES"
        empty.empty_display_size = 0.1
        empty.location = Vector(
            calibration.panel_px_to_world(cx, cy, settings.ppb, origin))
        collection.objects.link(empty)
        collection["re_registration"] = empty.name

    def _guide_boxes(self, collection, spec: ElementSpec, link: ProjectLink,
                     settings) -> None:
        """Wireframe rects at each declared placement — never rendered."""
        if not (spec.frame_w and spec.frame_h):
            return
        for index, placement in enumerate(spec.placements):
            origin = self._origin_offset(link, settings, placement.panel)
            corners_px = (
                (placement.x, placement.y),
                (placement.x + spec.frame_w, placement.y),
                (placement.x + spec.frame_w, placement.y + spec.frame_h),
                (placement.x, placement.y + spec.frame_h),
            )
            verts = [calibration.panel_px_to_world(x, y, settings.ppb, origin)
                     for x, y in corners_px]
            mesh = bpy.data.meshes.new(f"box_{spec.path}_{index}")
            mesh.from_pydata(verts, [(0, 1), (1, 2), (2, 3), (3, 0)], [])
            obj = bpy.data.objects.new(mesh.name, mesh)
            obj.display_type = "WIRE"
            obj.hide_render = True
            obj.hide_select = True
            obj["re_guide"] = "box"
            collection.objects.link(obj)

    @staticmethod
    def _clear_guide_boxes(collection) -> None:
        """Remove the guide-box wireframes (marked ``re_guide``), leaving any
        user geometry (rotors, meshes) in the collection untouched."""
        for obj in [o for o in collection.objects if o.get("re_guide") == "box"]:
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)

    def _panel_guides(self, context, link: ProjectLink, settings,
                      reposition: bool) -> None:
        for panel in link.device.panels:
            name = f"RE Panel {panel}"
            existing = bpy.data.objects.get(name)
            if existing is not None and not reposition:
                continue
            size = self._panel_size(link, panel, settings.rack_units)
            origin = calibration.origin_offset_px(settings.origin, size.width,
                                                  size.height)
            corners_px = ((0, 0), (size.width, 0),
                          (size.width, size.height), (0, size.height))
            verts = [calibration.panel_px_to_world(x, y, settings.ppb, origin)
                     for x, y in corners_px]
            if existing is not None:
                # Reposition in place: same 4-vertex ring, new coordinates.
                for vert, co in zip(existing.data.vertices, verts):
                    vert.co = co
                continue
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


class REBLEND_OT_set_frame_size(bpy.types.Operator):
    """Fill in per-frame pixel size, which the RE Lua never carries (§5.2).

    Frame size is the designer's choice (or read from existing art at import),
    so a fresh import lands with every element unsized and the validator flags
    one ``frame-size`` warning per element. This applies the panel's Width and
    Height in bulk so the whole set can be cleared at once, or to just the
    active element. ``MISSING`` never clobbers a size already set (a probed or
    hand-picked one); ``ACTIVE`` overwrites the active element deliberately.
    """

    bl_idname = "reblend.set_frame_size"
    bl_label = "Set Frame Size"
    bl_options = {"REGISTER", "UNDO"}

    scope: bpy.props.EnumProperty(
        name="Scope",
        items=(
            ("MISSING", "Missing", "Every element that has no frame size yet"),
            ("ACTIVE", "Active", "Only the active collection's element"),
        ),
        default="MISSING",
    )

    def execute(self, context):
        settings = _settings(context)
        w, h = int(settings.frame_w), int(settings.frame_h)
        if w <= 0 or h <= 0:
            self.report({"ERROR"}, "set a positive Frame W and Frame H first")
            return {"CANCELLED"}

        if self.scope == "ACTIVE":
            active = context.collection
            if active is None or not schema.is_element(active):
                self.report({"ERROR"}, "active collection is not an RE Element")
                return {"CANCELLED"}
            targets = [active]
        else:
            targets = [c for c in _element_collections()
                       if not schema.props_to_data(c).has_frame_size]

        for collection in targets:
            collection["re_frame_w"] = w
            collection["re_frame_h"] = h

        if not targets:
            self.report({"INFO"}, "no elements needed a frame size")
        else:
            self.report({"INFO"}, f"set {w}x{h}px on {len(targets)} element(s)")
        return {"FINISHED"}


#: Which two world-axis indices are the camera's screen plane (width, height)
#: for a given Camera Axis — the pair perpendicular to the view direction.
_SCREEN_AXES = {
    "neg_y": (0, 2), "pos_y": (0, 2),   # front/back: X wide, Z tall
    "neg_x": (1, 2), "pos_x": (1, 2),   # side: Y wide, Z tall
    "neg_z": (0, 1), "pos_z": (0, 1),   # top/bottom: X wide, Y tall
}


class REBLEND_OT_scale_to_bounds(bpy.types.Operator):
    """Scale the active object to the active element's frame bounds (§5.2).

    Handy for backdrops: model a rough plane, then snap it to exactly
    ``re_frame_w × re_frame_h`` in world units (at the current Pixels/Unit)
    across the camera's screen plane. ``Stretch`` fills the bounds on both
    axes independently; ``Uniform`` keeps the object's aspect and fits inside.

    Scaling is applied along the object's local axes, so it is exact for an
    axis-aligned (un-rotated) object — the usual case for a panel plane.
    """

    bl_idname = "reblend.scale_to_bounds"
    bl_label = "Scale to Bounds"
    bl_options = {"REGISTER", "UNDO"}

    fit: bpy.props.EnumProperty(
        name="Fit",
        items=(
            ("STRETCH", "Stretch", "Fill the frame on both axes independently"),
            ("UNIFORM", "Uniform", "Preserve aspect ratio and fit inside the frame"),
        ),
        default="STRETCH",
    )

    def execute(self, context):
        collection = context.collection
        if collection is None or not schema.is_element(collection):
            self.report({"ERROR"}, "active collection is not an RE Element")
            return {"CANCELLED"}
        data = schema.props_to_data(collection)
        if not data.has_frame_size:
            self.report({"ERROR"}, f"'{data.path}': set a frame size first")
            return {"CANCELLED"}

        obj = context.active_object
        if obj is None:
            self.report({"ERROR"}, "select the object to scale first")
            return {"CANCELLED"}

        settings = _settings(context)
        w_idx, h_idx = _SCREEN_AXES[settings.camera_axis]
        dims = obj.dimensions
        cur_w, cur_h = dims[w_idx], dims[h_idx]
        if cur_w <= 0.0 or cur_h <= 0.0:
            self.report({"ERROR"}, "object has no extent across the camera plane")
            return {"CANCELLED"}

        target_w = data.frame_w / settings.ppb
        target_h = data.frame_h / settings.ppb
        sw, sh = target_w / cur_w, target_h / cur_h
        if self.fit == "UNIFORM":
            sw = sh = min(sw, sh)

        scale = list(obj.scale)
        scale[w_idx] *= sw
        scale[h_idx] *= sh
        obj.scale = scale
        self.report(
            {"INFO"},
            f"scaled '{obj.name}' to {data.frame_w}x{data.frame_h}px bounds",
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
            context.scene, collections, out_dir, ppb=settings.ppb,
            inactive_render=settings.inactive_render,
            view_axis=calibration.axis_vector(settings.camera_axis),
        )
        findings = [f for result in results for f in result.findings]
        props.store_report(settings, findings)

        failed = [r.element for r in results if not r.ok]
        warnings = sum(1 for f in findings if f.severity != validation.ERROR)
        if failed:
            self.report(
                {"ERROR"},
                f"rendered {len(results) - len(failed)}/{len(results)} sheets; "
                f"failed: {', '.join(failed)} — see the RE panel",
            )
        elif warnings:
            self.report(
                {"WARNING"},
                f"rendered {len(results)} sheet(s); {warnings} warning(s) "
                "— see the RE panel",
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
            axis = self._knob_axis(context, collection)
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

    def _knob_axis(self, context, collection) -> tuple[float, float, float]:
        """The world axis a knob spins around (§4.2).

        An explicit Knob Rotation Axis setting wins outright; otherwise the
        knob follows the Camera Axis through the registration empty, so it
        faces the camera and spins in view even when the empty is tilted.
        """
        settings = _settings(context)
        if settings.rotation_axis != "auto":
            return calibration.axis_vector(settings.rotation_axis)
        base = Vector(calibration.axis_vector(settings.camera_axis))
        empty = bpy.data.objects.get(str(collection.get("re_registration", "")))
        if empty is None:
            return tuple(base)
        axis = empty.matrix_world.to_quaternion() @ base
        return tuple(axis.normalized())


# ---------------------------------------------------------------------------
# state-table editing (the "state playground", §5.3)
# ---------------------------------------------------------------------------
#
# The persisted source of truth stays the ``re_states`` JSON string; these
# operators load it, mutate it through the pure StateTable helpers (which keep
# it total by construction), and write it back. No parallel live model, so the
# same edits are reproducible headlessly.


def _require_states_element(op, context):
    """The active collection if it's a state-rigged element, else report and None."""
    collection = context.collection
    if collection is None or not schema.is_element(collection):
        op.report({"ERROR"}, "active collection is not an RE Element")
        return None, None
    data = schema.props_to_data(collection)
    if kinds.rig_for_kind(data.kind) != kinds.RIG_STATES:
        op.report({"ERROR"}, f"'{data.kind}' elements have no state table")
        return None, None
    return collection, data


def _load_state_table(collection, data) -> state_tables.StateTable:
    """The element's state table, seeding the default names if it has none."""
    raw = str(collection.get("re_states", ""))
    if raw:
        return state_tables.StateTable.from_json(raw)  # may raise ValueError
    return state_tables.default_state_table(data.kind, data.frames) \
        or state_tables.StateTable()


def _value_kind(channel) -> str:
    """Which editing widget a channel needs: BOOL, COLOR, or FLOAT."""
    data_path = channel[2]
    if data_path in ("hide_render", "hide_viewport"):
        return "BOOL"
    if 'inputs["Color"]' in data_path:
        return "COLOR"
    return "FLOAT"


class REBLEND_OT_add_state_action(bpy.types.Operator):
    """Add a state action to every state of the active element (§4.3).

    A named-but-empty default table (the "no actions yet" warning) has states
    but nothing that visibly changes between them. This adds one channel —
    visibility, emission, a transform, a shape key — to *all* states at once so
    the table stays total, seeding it with a neutral value the designer then
    differentiates per state with Set Value.
    """

    bl_idname = "reblend.add_state_action"
    bl_label = "Add State Action"
    bl_options = {"REGISTER", "UNDO"}

    action: bpy.props.EnumProperty(
        name="Action",
        items=(
            ("VISIBILITY", "Visibility", "Show or hide an object per state"),
            ("EMISSION_STRENGTH", "Emission Strength",
             "A material node's emission strength (lamps, glows)"),
            ("EMISSION_COLOR", "Emission Colour", "A material node's emission colour"),
            ("LOCATION", "Location", "One axis of an object's position (fader detents)"),
            ("SHAPE_KEY", "Shape Key", "A shape key's value on a mesh (pressed caps)"),
        ),
        default="VISIBILITY",
    )
    target: bpy.props.StringProperty(
        name="Target", description="Object name (visibility/location/shape key) or "
                                   "material name (emission)")
    node: bpy.props.StringProperty(
        name="Node", default="Emission",
        description="Emission shader node inside the material")
    axis: bpy.props.EnumProperty(
        name="Axis", items=(("0", "X", ""), ("1", "Y", ""), ("2", "Z", "")),
        default="0")
    key_name: bpy.props.StringProperty(name="Shape Key", description="Shape key name")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "action")
        col.prop(self, "target")
        if self.action in {"EMISSION_STRENGTH", "EMISSION_COLOR"}:
            col.prop(self, "node")
        elif self.action == "LOCATION":
            col.prop(self, "axis")
        elif self.action == "SHAPE_KEY":
            col.prop(self, "key_name")

    def execute(self, context):
        collection, data = _require_states_element(self, context)
        if collection is None:
            return {"CANCELLED"}
        target = self.target.strip()
        if not target:
            self.report({"ERROR"}, "name the target object or material")
            return {"CANCELLED"}
        actions = self._build_actions(target)
        if actions is None:
            return {"CANCELLED"}
        try:
            table = _load_state_table(collection, data)
            table.add_actions(actions)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        collection["re_states"] = table.to_json()
        self.report(
            {"INFO"},
            f"added {self.action.replace('_', ' ').lower()} on '{target}' "
            f"to {table.frames} state(s)",
        )
        return {"FINISHED"}

    def _build_actions(self, target):
        if self.action == "VISIBILITY":
            return state_tables.visibility(target, True)
        if self.action == "EMISSION_STRENGTH":
            return (state_tables.emission_strength(target, 0.0, self.node or "Emission"),)
        if self.action == "EMISSION_COLOR":
            return (state_tables.emission_color(
                target, (0.0, 0.0, 0.0, 1.0), self.node or "Emission"),)
        if self.action == "LOCATION":
            return (state_tables.location(target, int(self.axis), 0.0),)
        if self.action == "SHAPE_KEY":
            key = self.key_name.strip()
            if not key:
                self.report({"ERROR"}, "name the shape key")
                return None
            return (state_tables.shape_key_value(target, key, 0.0),)
        return None


class REBLEND_OT_remove_state_action(bpy.types.Operator):
    """Remove a state action (control) from every state of the active element."""

    bl_idname = "reblend.remove_state_action"
    bl_label = "Remove State Action"
    bl_options = {"REGISTER", "UNDO"}

    control: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        collection, data = _require_states_element(self, context)
        if collection is None:
            return {"CANCELLED"}
        try:
            table = _load_state_table(collection, data)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        controls = table.controls()
        if not 0 <= self.control < len(controls):
            self.report({"ERROR"}, "no such state action")
            return {"CANCELLED"}
        label = state_tables.describe_channel(controls[self.control][0])
        for channel in controls[self.control]:
            table.remove_channel(channel)
        collection["re_states"] = table.to_json()
        self.report({"INFO"}, f"removed {label}")
        return {"FINISHED"}


class REBLEND_OT_set_state_value(bpy.types.Operator):
    """Set one state's value for one control on the active element (§4.3)."""

    bl_idname = "reblend.set_state_value"
    bl_label = "Set State Value"
    bl_options = {"REGISTER", "UNDO"}

    state: bpy.props.IntProperty(default=-1)
    control: bpy.props.IntProperty(default=-1)
    value_kind: bpy.props.StringProperty(default="FLOAT")
    bool_value: bpy.props.BoolProperty(name="Visible", default=True)
    float_value: bpy.props.FloatProperty(name="Value", default=0.0)
    color_value: bpy.props.FloatVectorProperty(
        name="Colour", size=4, subtype="COLOR", min=0.0, max=1.0,
        default=(0.0, 0.0, 0.0, 1.0))

    def invoke(self, context, event):
        collection, data = _require_states_element(self, context)
        if collection is None:
            return {"CANCELLED"}
        try:
            table = _load_state_table(collection, data)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        channel = self._channel(table)
        if channel is None:
            return {"CANCELLED"}
        current = table.value_in(self.state, channel)
        self.value_kind = _value_kind(channel)
        if self.value_kind == "BOOL":
            # The stored value is `hide` (1.0 = hidden); present it as Visible.
            self.bool_value = not bool(current)
        elif self.value_kind == "COLOR":
            self.color_value = tuple(current) if current else (0.0, 0.0, 0.0, 1.0)
        else:
            self.float_value = float(current) if current is not None else 0.0
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        col = self.layout.column()
        if self.value_kind == "BOOL":
            col.prop(self, "bool_value")
        elif self.value_kind == "COLOR":
            col.prop(self, "color_value")
        else:
            col.prop(self, "float_value")

    def execute(self, context):
        collection, data = _require_states_element(self, context)
        if collection is None:
            return {"CANCELLED"}
        try:
            table = _load_state_table(collection, data)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        channel = self._channel(table)
        if channel is None:
            return {"CANCELLED"}
        for chan in table.controls()[self.control]:
            table.set_value(self.state, chan, self._value_for(chan))
        collection["re_states"] = table.to_json()
        self.report({"INFO"}, f"set '{table.states[self.state].name}' value")
        return {"FINISHED"}

    def _channel(self, table):
        controls = table.controls()
        if not (0 <= self.state < table.frames and 0 <= self.control < len(controls)):
            self.report({"ERROR"}, "no such state value")
            return None
        return controls[self.control][0]

    def _value_for(self, channel):
        kind = _value_kind(channel)
        if kind == "BOOL":
            return float(not self.bool_value)  # Visible -> `hide` value
        if kind == "COLOR":
            return tuple(self.color_value)
        return float(self.float_value)


CLASSES = (
    REBLEND_OT_import_project,
    REBLEND_OT_validate,
    REBLEND_OT_set_frame_size,
    REBLEND_OT_scale_to_bounds,
    REBLEND_OT_render_elements,
    REBLEND_OT_generate_rig,
    REBLEND_OT_add_state_action,
    REBLEND_OT_remove_state_action,
    REBLEND_OT_set_state_value,
)
