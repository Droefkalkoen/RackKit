"""Strip stitching geometry (§5.1, §5.2): computed, never manual."""

import numpy as np
import pytest

from reblend.render import stitcher
from reblend.render.stitcher import StitchError, split_strip, stitch, unpremultiply


def _frame(h, w, value):
    frame = np.zeros((h, w, 4), dtype=np.float32)
    frame[..., 0] = value  # red channel marks the frame
    return frame


def test_strip_geometry_and_order():
    frames = [_frame(10, 20, v) for v in (0.1, 0.2, 0.3)]
    strip = stitch(frames)
    assert strip.shape == (30, 20, 4)  # height = frame_h * frames
    # frame 0 on top
    assert strip[0, 0, 0] == pytest.approx(0.1)
    assert strip[10, 0, 0] == pytest.approx(0.2)
    assert strip[29, 0, 0] == pytest.approx(0.3)


def test_mismatched_frames_refuse():
    with pytest.raises(StitchError, match="all frames must match"):
        stitch([_frame(10, 20, 0.1), _frame(10, 21, 0.2)])


def test_empty_and_malformed_input_refuse():
    with pytest.raises(StitchError, match="no frames"):
        stitch([])
    with pytest.raises(StitchError, match="RGBA"):
        stitch([np.zeros((10, 20, 3), dtype=np.float32)])


def test_split_strip_inverts_stitch():
    frames = [_frame(10, 20, v) for v in (0.1, 0.2)]
    parts = split_strip(stitch(frames), frame_h=10)
    assert len(parts) == 2
    assert np.array_equal(parts[0], frames[0])
    assert np.array_equal(parts[1], frames[1])


def test_split_strip_rejects_indivisible_height():
    with pytest.raises(StitchError, match="not a multiple"):
        split_strip(np.zeros((25, 20, 4), dtype=np.float32), frame_h=10)


def test_unpremultiply():
    px = np.array([[[0.25, 0.0, 0.0, 0.5],    # premultiplied half-covered red
                    [0.0, 0.0, 0.0, 0.0],     # fully transparent stays zero
                    [1.0, 1.0, 1.0, 1.0]]], dtype=np.float32)
    out = unpremultiply(px)
    assert out[0, 0] == pytest.approx([0.5, 0.0, 0.0, 0.5])
    assert out[0, 1] == pytest.approx([0.0, 0.0, 0.0, 0.0])
    assert out[0, 2] == pytest.approx([1.0, 1.0, 1.0, 1.0])


def test_frame_height_contract():
    # the "strip height = frameHeight x frameCount" rule as one authority
    assert stitcher.frame_height(305, 61) == 5
    assert stitcher.frame_height(130, 1) == 130
    assert stitcher.frame_height(305, 60) is None   # does not divide
    assert stitcher.frame_height(305, 0) is None    # no frames, no height
    assert stitcher.frame_height(305, -3) is None
    assert stitcher.frame_height(0, 4) is None      # empty strip
