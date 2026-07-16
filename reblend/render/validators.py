"""Output validators: frame bounds, overflow, straight alpha (§5.2, M0 findings).

These run against the pixels RE-Blend just rendered (numpy arrays, top-down
RGBA as produced by the stitcher) and against the declared frame geometry
*before* rendering. They are the render-time half of the correctness story;
the project-level cross-checks live in :mod:`reblend.project.validation`.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

__all__ = [
    "FRAME_BOUNDS_MULTIPLE",
    "ALPHA_STRAIGHT",
    "ALPHA_PREMULTIPLIED",
    "ALPHA_INCONCLUSIVE",
    "check_frame_bounds",
    "overflow_frames",
    "classify_alpha",
]

#: RE2DRender silently reframes any sprite whose frame width or height is not
#: divisible by 5 (art is authored at 5× display size), shifting content and
#: breaking pixel-exact registration — see docs/findings-m0.md finding 6.
#: RE-Blend therefore treats non-multiple-of-5 frame bounds as an error.
FRAME_BOUNDS_MULTIPLE = 5


def check_frame_bounds(frame_w: int, frame_h: int, frames: int = 1) -> list[str]:
    """Errors that make a frame geometry unrenderable/unacceptable, or []."""
    problems = []
    if frames < 1:
        problems.append(f"frame count must be >= 1, got {frames}")
    if frame_w <= 0 or frame_h <= 0:
        problems.append(f"frame size must be positive, got {frame_w}x{frame_h}")
        return problems
    for label, size in (("width", frame_w), ("height", frame_h)):
        if size % FRAME_BOUNDS_MULTIPLE != 0:
            problems.append(
                f"frame {label} {size} is not a multiple of {FRAME_BOUNDS_MULTIPLE} — "
                "RE2DRender would reframe the sheet and break registration"
            )
    return problems


def overflow_frames(
    frames: Sequence[np.ndarray], threshold: float = 1.0 / 255.0
) -> list[int]:
    """Indices of frames whose alpha touches the frame border (§5.2).

    Non-zero border alpha means geometry, shadow, or glow bleeding outside
    the declared bounding box — it would clip in the sheet or misregister in
    Reason. Checked per frame so the report can say *which* state overflows
    (typically the lit/glowing one).
    """
    overflowing = []
    for index, frame in enumerate(frames):
        alpha = np.asarray(frame)[..., 3]
        border = np.concatenate(
            (alpha[0, :], alpha[-1, :], alpha[1:-1, 0], alpha[1:-1, -1])
        )
        if (border > threshold).any():
            overflowing.append(index)
    return overflowing


ALPHA_STRAIGHT = "straight"
ALPHA_PREMULTIPLIED = "premultiplied"
ALPHA_INCONCLUSIVE = "inconclusive"


def classify_alpha(pixels: np.ndarray, tolerance: float = 1e-3) -> str:
    """Discriminate straight vs premultiplied alpha in stored pixels (§10.1).

    Premultiplied storage has every channel <= its alpha everywhere. Straight
    alpha keeps edge colour independent of coverage, so a bright anti-aliased
    edge yields partial-alpha pixels with a channel *brighter* than their
    alpha. Needs partial-coverage pixels to discriminate; a sheet with only
    hard edges returns ``inconclusive`` (proven in M0: fall back to the
    RE2DPreview halo eyeball test).
    """
    flat = np.asarray(pixels, dtype=np.float32).reshape(-1, 4)
    rgb, alpha = flat[:, :3], flat[:, 3]
    partial = (alpha > 0.02) & (alpha < 0.98)
    if not partial.any():
        return ALPHA_INCONCLUSIVE
    if (rgb[partial] > (alpha[partial, None] + tolerance)).any():
        return ALPHA_STRAIGHT
    return ALPHA_PREMULTIPLIED
