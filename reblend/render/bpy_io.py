"""Blender image I/O with pinned colour semantics (§5.2, proven in M0).

Reading a rendered PNG back for stitching, and writing the finished strip,
both have to defeat Blender's colour management: images are pinned to a
non-transforming ("data") colorspace so Blender neither inverse-transforms
the stored sRGB values on read nor tone-maps them on write — the bytes that
were rendered are the bytes that reach the file. This module is the tested
M0 spike behaviour, promoted to the real render path.
"""

from __future__ import annotations

from pathlib import Path

import bpy
import numpy as np

__all__ = ["set_data_colorspace", "load_raw_pixels", "save_strip"]

#: Non-transforming ("data") colorspaces, best first. Blender 4.x's default
#: OCIO config dropped the legacy ``Raw`` name in favour of ``Non-Color``;
#: older/custom configs may ship either, so resolve at runtime.
_DATA_COLORSPACES = ("Non-Color", "Raw", "Generic Data", "data")


def set_data_colorspace(colorspace_settings) -> str:
    """Pin an image to this OCIO config's data colorspace; returns the name."""
    available = {
        item.identifier
        for item in colorspace_settings.bl_rna.properties["name"].enum_items
    }
    for name in _DATA_COLORSPACES:
        if name in available:
            colorspace_settings.name = name
            return name
    raise RuntimeError(
        "no non-transforming colorspace found in this OCIO config; tried "
        f"{_DATA_COLORSPACES}. Available: {', '.join(sorted(available))}"
    )


def load_raw_pixels(path: Path | str) -> np.ndarray:
    """Load a PNG's *stored* pixels as top-down (H, W, 4) float RGBA.

    The data colorspace stops Blender inverse-transforming the sRGB values
    on read; Blender's pixel buffer is bottom-up, so flip to top-down.
    """
    img = bpy.data.images.load(str(path), check_existing=False)
    try:
        set_data_colorspace(img.colorspace_settings)
        height, width = img.size[1], img.size[0]
        pixels = np.array(img.pixels[:], dtype=np.float32).reshape(height, width, 4)
    finally:
        bpy.data.images.remove(img)
    return pixels[::-1]


def save_strip(strip: np.ndarray, path: Path | str, name: str = "reblend_strip") -> None:
    """Write a top-down (H, W, 4) float RGBA strip as an 8-bit straight-alpha PNG."""
    height, width = strip.shape[0], strip.shape[1]
    image = bpy.data.images.new(name, width=width, height=height, alpha=True)
    try:
        image.alpha_mode = "STRAIGHT"
        set_data_colorspace(image.colorspace_settings)  # values are display-space already
        image.pixels[:] = strip[::-1].reshape(-1)  # top-down -> Blender bottom-up
        image.file_format = "PNG"
        image.filepath_raw = str(path)
        image.save()
    finally:
        bpy.data.images.remove(image)
