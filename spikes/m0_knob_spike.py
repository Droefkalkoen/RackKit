"""M0 spike — render one knob element's sprite strip from the pilot .blend.

This is the *fixture generator* for the M0 acceptance test (ROADMAP.md "M0 —
Spike: prove the pixels"). It is deliberately throwaway: no operators, no
schema, no UI. It exists to produce ONE 61-frame knob strip so RE2DRender and
RE2DPreview can pass judgement on it. The real, tested render module lands in
M1 (design §5, §8); do not import this from `reblend`.

STATUS: unverified against Blender. The whole point of M0 is to run this on a
real machine with Blender 4.2 LTS+ and fix whatever the pixels tell you. The
correctness-critical block (COLOUR / ALPHA / DEPTH below) and the pixel
row-order flips are the parts most likely to need adjustment on first contact —
see docs/m0-acceptance-test.md for what each choice is defending against.

Run interactively (Scripting workspace) after editing the PARAMETERS block, or
headless:

    blender -b /path/to/pilot.blend --python spikes/m0_knob_spike.py

Requires numpy (ships with Blender). No other external image dependency.
"""

from __future__ import annotations

import math
import os

import bpy
import numpy as np
from mathutils import Vector

# ---------------------------------------------------------------------------
# PARAMETERS — read the real values from the pilot's GUI2D/device_2D.lua.
# The values below match tests/fixtures/silence_detector (a 63x63, 61-frame
# turntable knob) so the script is runnable as-is against a matching rig.
# ---------------------------------------------------------------------------
NODE = "knob_tone"          # device_2D.lua node name -> output basename
FRAME_W = 128                     # re_frame_w  (px)
FRAME_H = 128                     # re_frame_h  (px)
FRAMES = 61                      # re_frames   (must equal `frames` in device_2D.lua)
SWEEP_DEG = 300.0                # default -150..+150; per-element in the real tool
PPB = 100.0                      # calibration: panel pixels per Blender unit (§4.4)

# Scene objects that make up the element. Create/rename these in your pilot:
ROTOR = "knob_tone_rotor"   # the rotating mesh; its ORIGIN must sit on the axis
REG_EMPTY = "reg_knob_tone"  # registration empty marking the rotation axis (§4.2)

# Where the finished strip is written. Point this at the LINKED project's GUI2D
# so RE2DRender can pick it up. The basename must match device_2D.lua `path`.
OUT_DIR = os.path.expanduser("~/pilot/GUI2D")
FRAME_TMP = os.path.join(bpy.app.tempdir, "reblend_m0")

# Which world axis the knob spins around / the camera looks down. Default +Z
# (panel modelled in the XY plane, facing up). Change to match your pilot.
KNOB_AXIS = Vector((0.0, 1.0, 0.0))


def calibrate_camera(scene):
    """Per-element ortho camera centred on the registration empty (§4.2, §4.4).

    Registration is true by construction: the camera aims at the empty and
    never moves between frames, so every frame centres on the same X,Y.
    """
    reg = bpy.data.objects[REG_EMPTY]
    cam_data = bpy.data.cameras.new(f"cam_{NODE}")
    cam_data.type = "ORTHO"
    # ortho_scale = Blender units across the framed rect's longer side.
    cam_data.ortho_scale = max(FRAME_W, FRAME_H) / PPB
    cam = bpy.data.objects.new(f"cam_{NODE}", cam_data)
    scene.collection.objects.link(cam)

    axis = (reg.matrix_world.to_quaternion() @ KNOB_AXIS).normalized()
    cam.location = reg.matrix_world.translation + axis * 5.0
    # Camera looks down its local -Z; aim +Z along the axis so -Z faces the empty.
    cam.rotation_euler = axis.to_track_quat("Z", "Y").to_euler()
    scene.camera = cam
    return cam


def build_turntable_driver():
    """Rotation driver on the rotor: frame 0 -> min, frame FRAMES-1 -> max (§4.3).

    Linear; regenerated whenever FRAMES changes so the rig can never diverge
    from the frame count baked into the sheet.
    """
    rotor = bpy.data.objects[ROTOR]
    rotor.rotation_mode = "XYZ"
    rotor.driver_remove("rotation_euler")
    fcurve = rotor.driver_add("rotation_euler", 2)  # index 2 = local Z
    drv = fcurve.driver
    drv.type = "SCRIPTED"
    half = SWEEP_DEG / 2.0
    drv.expression = f"radians(-{half} + {SWEEP_DEG} * frame / {FRAMES - 1})"


def configure_render(scene):
    """The correctness-critical block (§5.2, risk §10.1).

    Every line here defends one of M0's failure modes. Change nothing without a
    reason you can name.
    """
    r = scene.render
    r.resolution_x = FRAME_W
    r.resolution_y = FRAME_H
    r.resolution_percentage = 100
    r.film_transparent = True                    # transparent film -> alpha
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGBA"
    r.image_settings.color_depth = "8"           # 8-bit PNG, enforced

    # Colour management pinned to Standard so palette hex survives to the file.
    scene.view_settings.view_transform = "Standard"  # NOT Filmic / AgX
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.display_settings.display_device = "sRGB"


def render_frames(scene):
    os.makedirs(FRAME_TMP, exist_ok=True)
    paths = []
    for f in range(FRAMES):
        scene.frame_set(f)
        path = os.path.join(FRAME_TMP, f"{NODE}_{f:04d}.png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        paths.append(path)
    return paths


# Non-transforming ("data") colorspaces, best first. Blender 4.x's default OCIO
# config dropped the legacy ``Raw`` name in favour of ``Non-Color``; older
# configs ship both. M0 runs on whatever Blender the workstation has, so we
# resolve the name against the config at runtime instead of hardcoding one.
_DATA_COLORSPACES = ("Non-Color", "Raw", "Generic Data", "data")


def _set_data_colorspace(colorspace_settings):
    """Pin an image to a non-transforming colorspace so Blender neither inverse-
    transforms on read nor tone-maps on write; stored values pass through as-is.

    Probes this OCIO config's enum and uses the first available name from
    ``_DATA_COLORSPACES``, so the spike works whether the build calls the data
    space ``Raw`` (legacy) or ``Non-Color`` (Blender 4.x default). Returns the
    name chosen so callers can log the finding (docs/m0-acceptance-test.md §6).
    """
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


def _read_raw(path):
    """Load a PNG and return its STORED pixels as top-down (H, W, 4) float RGBA.

    A data colorspace stops Blender inverse-transforming the sRGB values on
    read; Blender's pixel buffer is bottom-up, so we flip to top-down.
    """
    img = bpy.data.images.load(path, check_existing=False)
    _set_data_colorspace(img.colorspace_settings)
    h, w = img.size[1], img.size[0]
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(img)
    return px[::-1]  # bottom-up -> top-down


def stitch(paths):
    """Vertical strip, frame 0 on top, height = FRAME_H * FRAMES (§5.2)."""
    strip = np.zeros((FRAME_H * FRAMES, FRAME_W, 4), dtype=np.float32)
    for f, path in enumerate(paths):
        top = f * FRAME_H
        strip[top : top + FRAME_H] = _read_raw(path)
    return strip


def write_strip(strip):
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{NODE}.png")
    out = bpy.data.images.new(
        NODE, width=FRAME_W, height=FRAME_H * FRAMES, alpha=True
    )
    out.alpha_mode = "STRAIGHT"
    _set_data_colorspace(out.colorspace_settings)  # values are already display-space
    out.pixels[:] = strip[::-1].reshape(-1)  # top-down -> Blender bottom-up
    out.file_format = "PNG"
    out.filepath_raw = out_path
    # If 8-bit depth is not honoured here on your build, fall back to
    # out.save_render(out_path, scene=bpy.context.scene) and re-verify alpha.
    out.save()
    return out_path


def verify_straight_alpha(path):
    """Discriminate straight vs premultiplied alpha in the written file (§10.1).

    Premultiplied output has every channel <= its alpha everywhere. Straight
    alpha keeps edge colour independent of coverage, so a bright anti-aliased
    edge yields partial-alpha pixels with a channel BRIGHTER than their alpha.
    Needs a bright edge to trigger; if it can't decide, trust the halo eyeball
    test and RE2DRender.
    """
    px = _read_raw(path).reshape(-1, 4)
    rgb, alpha = px[:, :3], px[:, 3]
    partial = (alpha > 0.02) & (alpha < 0.98)
    n = int(partial.sum())
    if n == 0:
        return "inconclusive: no anti-aliased edge pixels found"
    over = bool((rgb[partial] > (alpha[partial, None] + 1e-3)).any())
    return "straight (PASS)" if over else "possibly premultiplied — inspect edges"


def main():
    scene = bpy.context.scene
    calibrate_camera(scene)
    build_turntable_driver()
    configure_render(scene)
    paths = render_frames(scene)
    strip = stitch(paths)
    out_path = write_strip(strip)
    print(f"[M0] wrote {out_path}  ({FRAME_W} x {FRAME_H * FRAMES}, {FRAMES} frames)")
    print(f"[M0] alpha check: {verify_straight_alpha(out_path)}")
    print("[M0] now run RE2DRender on the project and RE2DPreview to judge it.")


if __name__ == "__main__":
    main()
