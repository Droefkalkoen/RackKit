"""The validation report: the full cross-check table of design §6.3.

Everything RE-Blend promises — art, Lua, and rig that cannot disagree — is
enforced here as explicit checks over the parsed config, the scene's
elements, and the sheets on disk. The engine is pure: the Blender side turns
element collections into :class:`~reblend.model.schema.ElementData` and a
:class:`SceneInfo`, tests build them directly, and (in M3) the headless CLI
exits non-zero when :attr:`Report.errors` is non-empty.

Render-time pixel checks (alpha classification, per-frame overflow) live in
:mod:`reblend.render.validators` and are merged into the same report by the
render queue — one list, one place to look.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from ..model import calibration, schema
from ..render.validators import check_frame_bounds
from . import link as link_mod
from .lua_reader import PANELS, Device2D, Graphic, HDGui2D, Node2D
from .png_meta import PngError, PngMeta, read_png_meta

__all__ = [
    "ERROR",
    "WARNING",
    "Finding",
    "Report",
    "SceneInfo",
    "validate_project",
    "validate_link",
]

ERROR = "error"
WARNING = "warning"

#: The only view transform that keeps palette hex values intact (§5.2).
STANDARD_VIEW_TRANSFORM = "Standard"


@dataclass(frozen=True)
class Finding:
    """One validation result. ``subject`` is a node or sprite path name."""

    severity: str
    code: str
    message: str
    subject: str = ""
    panel: str = ""

    def __str__(self) -> str:
        where = f" [{self.panel}]" if self.panel else ""
        who = f" {self.subject}:" if self.subject else ""
        return f"{self.severity.upper()}{where}{who} {self.message}"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, severity: str, code: str, message: str, subject: str = "", panel: str = "") -> None:
        self.findings.append(Finding(severity, code, message, subject, panel))


@dataclass(frozen=True)
class SceneInfo:
    """Scene-level facts only Blender knows; None = not available (headless tests)."""

    view_transform: str | None = None


def validate_link(
    link: link_mod.ProjectLink,
    elements: Sequence[schema.ElementData],
    scene: SceneInfo | None = None,
) -> Report:
    """Validate a scene's elements against a loaded project."""
    return validate_project(
        device=link.device,
        hdgui=link.hdgui,
        elements=elements,
        gui2d_dir=link.gui2d_dir,
        property_steps=link.property_steps,
        scene=scene,
    )


def validate_project(
    device: Device2D,
    hdgui: HDGui2D,
    elements: Sequence[schema.ElementData],
    gui2d_dir: Path | None = None,
    property_steps: Mapping[str, int] | None = None,
    scene: SceneInfo | None = None,
) -> Report:
    report = Report()
    by_path = {element.path: element for element in elements}
    lua_graphics = list(_iter_graphics(device))
    lua_paths = {graphic.path for _, _, graphic in lua_graphics}

    _check_art_coverage(report, lua_graphics, by_path, lua_paths, elements)
    _check_widget_links(report, device, hdgui)
    _check_steps(report, device, hdgui, dict(property_steps or {}))
    _check_kinds(report, device, hdgui, elements)
    _check_frame_geometry(report, elements)
    if gui2d_dir is not None:
        _check_files(report, elements, gui2d_dir)
    _check_layout(report, elements, gui2d_dir)

    if scene is not None and scene.view_transform is not None:
        if scene.view_transform != STANDARD_VIEW_TRANSFORM:
            report.add(
                WARNING,
                "view-transform",
                f"scene view transform is '{scene.view_transform}', expected "
                f"'{STANDARD_VIEW_TRANSFORM}' — palette colours will shift in the file",
            )
    return report


# ---------------------------------------------------------------------------
# individual checks
# ---------------------------------------------------------------------------


def _iter_graphics(device: Device2D) -> Iterable[tuple[str, Node2D, Graphic]]:
    for panel in PANELS:
        for root in device.panels.get(panel, {}).values():
            for node in root.walk():
                for graphic in node.graphics:
                    yield panel, node, graphic


def _check_art_coverage(
    report: Report,
    lua_graphics: list[tuple[str, Node2D, Graphic]],
    by_path: Mapping[str, schema.ElementData],
    lua_paths: set[str],
    elements: Sequence[schema.ElementData],
) -> None:
    missing_seen: set[str] = set()
    for panel, node, graphic in lua_graphics:
        element = by_path.get(graphic.path)
        if element is None:
            if graphic.path not in missing_seen:
                missing_seen.add(graphic.path)
                report.add(
                    ERROR,
                    "missing-art",
                    f"device_2D node '{node.name}' needs sheet '{graphic.path}.png' "
                    "but no RE Element in the scene produces it",
                    subject=graphic.path,
                    panel=panel,
                )
        elif element.frames != graphic.frames:
            report.add(
                ERROR,
                "frame-count",
                f"element renders {element.frames} frames but device_2D node "
                f"'{node.name}' declares frames = {graphic.frames}",
                subject=graphic.path,
                panel=panel,
            )

    for element in elements:
        if element.path not in lua_paths:
            report.add(
                WARNING,
                "orphan-element",
                f"RE Element '{element.path}' has no node in device_2D.lua — "
                "its sheet would render but never be used",
                subject=element.path,
            )


def _check_widget_links(report: Report, device: Device2D, hdgui: HDGui2D) -> None:
    # RE2DRender enforces this link at render time (M0 finding 4); catching it
    # here means catching it before a render is wasted.
    for panel_name, panel in hdgui.panels.items():
        for widget in panel.widgets:
            node = widget.node
            if node and device.node(panel_name, node) is None:
                report.add(
                    ERROR,
                    "widget-node",
                    f"hdgui_2D {widget.kind} points at node '{node}' which does "
                    "not exist in device_2D.lua",
                    subject=node,
                    panel=panel_name,
                )


_STEPPED_WIDGETS = ("sequence_fader", "step_button", "radio_button", "up_down_button")


def _check_steps(
    report: Report, device: Device2D, hdgui: HDGui2D, steps: dict[str, int]
) -> None:
    if not steps:
        return
    for panel_name, panel in hdgui.panels.items():
        for widget in panel.widgets:
            if widget.kind not in _STEPPED_WIDGETS or not widget.node or not widget.value:
                continue
            declared = steps.get(widget.value)
            if declared is None:
                continue
            handle = widget.attrs.get("handle_size", 0)
            if widget.kind == "sequence_fader" and isinstance(handle, (int, float)) and handle > 0:
                continue  # 1-frame moving handle: frames independent of steps (§10.4)
            node = device.node(panel_name, widget.node)
            if node is not None and node.frames != declared:
                report.add(
                    WARNING,
                    "steps",
                    f"{widget.kind} on node '{widget.node}' has {node.frames} frames "
                    f"but its property {widget.value} has {declared} steps",
                    subject=widget.node,
                    panel=panel_name,
                )


def _check_kinds(
    report: Report,
    device: Device2D,
    hdgui: HDGui2D,
    elements: Sequence[schema.ElementData],
) -> None:
    # Re-deriving the specs reuses the exact import-time logic, so "what kind
    # should this element be" can never drift between import and validation.
    expected = {spec.path: spec.kind for spec in link_mod.derive_specs(device, hdgui)}
    for element in elements:
        want = expected.get(element.path)
        if want is not None and element.kind != want:
            report.add(
                WARNING,
                "kind",
                f"element kind is '{element.kind}' but its hdgui_2D widgets imply "
                f"'{want}' — the rig may not match what Reason does with the sheet",
                subject=element.path,
            )


def _check_frame_geometry(report: Report, elements: Sequence[schema.ElementData]) -> None:
    for element in elements:
        if not element.has_frame_size:
            report.add(
                WARNING,
                "frame-size",
                "per-frame pixel size not set yet — set it before rendering",
                subject=element.path,
            )
            continue
        for problem in check_frame_bounds(element.frame_w, element.frame_h, element.frames):
            report.add(ERROR, "frame-bounds", problem, subject=element.path)


def _check_files(
    report: Report, elements: Sequence[schema.ElementData], gui2d_dir: Path
) -> None:
    try:
        actual_names = {entry.name for entry in gui2d_dir.iterdir() if entry.is_file()}
    except OSError:
        actual_names = set()

    for name in sorted(actual_names):
        if name.lower().endswith("-reframed.png"):
            # RE2DRender reframed a sheet it was given (M0 finding 6): the
            # authored pixels were NOT used and registration is broken.
            report.add(
                ERROR,
                "reframed",
                f"RE2DRender wrote '{name}' — a sheet had unsupported frame bounds "
                "and was silently reframed; fix the frame size and re-render",
                subject=name,
            )

    by_fold = {name.casefold(): name for name in actual_names}
    for element in elements:
        expected = f"{element.path}.png"
        if expected in actual_names:
            _check_png(report, element, gui2d_dir / expected)
        elif expected.casefold() in by_fold:
            report.add(
                ERROR,
                "case",
                f"sheet on disk is named '{by_fold[expected.casefold()]}' but the Lua "
                f"path says '{expected}' — case mismatch breaks case-sensitive builds",
                subject=element.path,
            )
        else:
            report.add(
                WARNING,
                "png-missing",
                f"'{expected}' not found in GUI2D (expected until first render)",
                subject=element.path,
            )


def _check_png(report: Report, element: schema.ElementData, path: Path) -> None:
    try:
        meta = read_png_meta(path)
    except PngError as exc:
        report.add(ERROR, "png-dims", f"unreadable PNG: {exc}", subject=element.path)
        return
    if element.has_frame_size:
        want_w = element.frame_w
        want_h = element.frame_h * element.frames
        if (meta.width, meta.height) != (want_w, want_h):
            report.add(
                ERROR,
                "png-dims",
                f"sheet is {meta.width}x{meta.height} but {element.frames} frames of "
                f"{element.frame_w}x{element.frame_h} require {want_w}x{want_h}",
                subject=element.path,
            )
    if not meta.is_8bit_rgba:
        report.add(
            WARNING,
            "png-format",
            f"sheet is not 8-bit RGBA (bit depth {meta.bit_depth}, "
            f"colour type {meta.color_type}) — the SDK expects 8-bit straight-alpha RGBA",
            subject=element.path,
        )


def _check_layout(
    report: Report, elements: Sequence[schema.ElementData], gui2d_dir: Path | None
) -> None:
    panel_sizes = _panel_sizes(elements, gui2d_dir)

    rects: dict[str, list[tuple[str, str, float, float, int, int]]] = {}
    for element in elements:
        if element.kind == "backdrop" or not element.has_frame_size:
            continue
        for placement in element.placements:
            rects.setdefault(placement.panel, []).append(
                (
                    element.path,
                    placement.node,
                    placement.x,
                    placement.y,
                    element.frame_w,
                    element.frame_h,
                )
            )

    for panel, panel_rects in rects.items():
        size = panel_sizes.get(panel)
        if size is not None:
            for path, node, x, y, w, h in panel_rects:
                if x < 0 or y < 0 or x + w > size.width or y + h > size.height:
                    report.add(
                        WARNING,
                        "bounds",
                        f"node '{node}' at ({x:g}, {y:g}) size {w}x{h} extends outside "
                        f"the {size.width}x{size.height} panel",
                        subject=path,
                        panel=panel,
                    )
        for i, (path_a, node_a, xa, ya, wa, ha) in enumerate(panel_rects):
            for path_b, node_b, xb, yb, wb, hb in panel_rects[i + 1 :]:
                if xa < xb + wb and xb < xa + wa and ya < yb + hb and yb < ya + ha:
                    report.add(
                        WARNING,
                        "overlap",
                        f"nodes '{node_a}' and '{node_b}' overlap",
                        subject=f"{node_a}+{node_b}",
                        panel=panel,
                    )


def _panel_sizes(
    elements: Sequence[schema.ElementData], gui2d_dir: Path | None
) -> dict[str, calibration.PanelSize]:
    """Panel pixel sizes, taken from each panel's backdrop element or sheet.

    RE2DRender derives the device's rack height from the backdrop PNGs
    (M0 finding 7), so the backdrop *is* the authority on panel size here too.
    Panels whose backdrop size is unknown are skipped by the layout checks.
    """
    sizes: dict[str, calibration.PanelSize] = {}
    for element in elements:
        if element.kind != "backdrop":
            continue
        size: calibration.PanelSize | None = None
        if element.has_frame_size:
            size = calibration.PanelSize(element.frame_w, element.frame_h)
        elif gui2d_dir is not None:
            try:
                meta: PngMeta = read_png_meta(gui2d_dir / f"{element.path}.png")
                size = calibration.PanelSize(meta.width, meta.height)
            except PngError:
                size = None
        if size is None:
            continue
        for placement in element.placements:
            sizes.setdefault(placement.panel, size)
    return sizes
