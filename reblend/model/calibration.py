"""World calibration: the fixed world-to-pixel convention (§4.4).

One scene-level convention makes everything else automatic: a fixed
world-to-pixel scale (default 1 Blender unit = 100 panel px). This module is
the single place that scale and the panel geometry constants live; camera
creation applies these numbers inside Blender, but the numbers themselves are
pure math and tested without ``bpy``.

Spatial convention (documented here because every Blender-side module leans
on it): the panel lies in the world X/Z plane facing −Y — Blender's front
orthographic view. Panel pixel (0, 0) (top-left) sits at the world origin,
+x panel px runs along +X, +y panel px (downward) runs along −Z. Cameras look
along +Y at the panel from −Y.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "PANEL_WIDTH_PX",
    "UNIT_HEIGHT_PX",
    "FOLDED_HEIGHT_PX",
    "DEFAULT_PPB",
    "DEFAULT_SWEEP_DEG",
    "CAMERA_DISTANCE",
    "PanelSize",
    "panel_size_px",
    "rack_units_for_height",
    "is_folded",
    "ortho_scale",
    "dominant_axis",
    "panel_px_to_world",
    "world_to_panel_px",
    "element_center_px",
]

#: The SDK's hi-res panel world (design §1): panels are 3770 px wide, 345 px
#: per rack unit tall, 130 px folded — confirmed against RE2DRender, which
#: derives the device's rack height from the backdrop PNGs (M0 finding 7).
PANEL_WIDTH_PX = 3770
UNIT_HEIGHT_PX = 345
FOLDED_HEIGHT_PX = 130

#: Default calibration: panel pixels per Blender unit.
DEFAULT_PPB = 100.0

#: Default knob sweep in degrees (−150°…+150°), configurable per element.
DEFAULT_SWEEP_DEG = 300.0

#: How far (Blender units) an element camera sits from its registration
#: empty. Orthographic, so the distance only needs to clear the geometry.
CAMERA_DISTANCE = 5.0


@dataclass(frozen=True)
class PanelSize:
    """A panel's pixel dimensions."""

    width: int
    height: int


def is_folded(panel: str) -> bool:
    return panel in ("folded_front", "folded_back")


def panel_size_px(panel: str, rack_units: int = 1) -> PanelSize:
    """Pixel size of a panel at a rack height (folded panels ignore units)."""
    if rack_units < 1:
        raise ValueError(f"rack_units must be >= 1, got {rack_units}")
    height = FOLDED_HEIGHT_PX if is_folded(panel) else UNIT_HEIGHT_PX * rack_units
    return PanelSize(width=PANEL_WIDTH_PX, height=height)


def rack_units_for_height(height_px: int) -> int | None:
    """Rack units implied by a front/back backdrop height, None if not a
    whole number of units (which validation should flag)."""
    units, remainder = divmod(height_px, UNIT_HEIGHT_PX)
    return units if remainder == 0 and units >= 1 else None


def ortho_scale(frame_w: int, frame_h: int, ppb: float = DEFAULT_PPB) -> float:
    """Blender ortho_scale framing exactly ``frame_w × frame_h`` panel px.

    ``ortho_scale`` is the world size of the sensor's *larger* side; Blender
    fits the smaller side from the render aspect ratio, so one number plus
    the resolution pins the framing exactly.
    """
    if frame_w <= 0 or frame_h <= 0:
        raise ValueError(f"frame size must be positive, got {frame_w}x{frame_h}")
    if ppb <= 0:
        raise ValueError(f"ppb must be positive, got {ppb}")
    return max(frame_w, frame_h) / ppb


def dominant_axis(axis: tuple[float, float, float]) -> tuple[int, float]:
    """Map an axis vector to a ``rotation_euler`` component index and a sign.

    A knob spins around whichever world axis dominates its registration
    empty's axis (X=0, Y=1, Z=2); a negative dominant component flips the
    sweep so min→max still runs the way the axis points. Proven in the M0
    spike (axis-driven rotation fix).
    """
    magnitudes = tuple(abs(c) for c in axis)
    if max(magnitudes) == 0.0:
        raise ValueError("axis must be non-zero")
    index = magnitudes.index(max(magnitudes))
    return index, (1.0 if axis[index] >= 0.0 else -1.0)


def panel_px_to_world(
    x: float, y: float, ppb: float = DEFAULT_PPB
) -> tuple[float, float, float]:
    """Panel pixel (top-left origin, +y down) → world XYZ on the panel plane."""
    return (x / ppb, 0.0, -y / ppb)


def world_to_panel_px(
    location: tuple[float, float, float], ppb: float = DEFAULT_PPB
) -> tuple[float, float]:
    """World XYZ → panel pixel (inverse of :func:`panel_px_to_world`)."""
    return (location[0] * ppb, -location[2] * ppb)


def element_center_px(
    offset_x: float, offset_y: float, frame_w: int, frame_h: int
) -> tuple[float, float]:
    """Centre of an element's frame rect in panel px.

    The registration empty (and therefore the camera) sits at the frame
    centre: the device_2D ``offset`` is the frame's top-left corner.
    """
    return (offset_x + frame_w / 2.0, offset_y + frame_h / 2.0)
