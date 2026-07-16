"""Render-output validators: frame bounds, overflow, alpha classification (§5.2)."""

import numpy as np

from reblend.render.validators import (
    ALPHA_INCONCLUSIVE,
    ALPHA_PREMULTIPLIED,
    ALPHA_STRAIGHT,
    check_frame_bounds,
    classify_alpha,
    overflow_frames,
)


def test_frame_bounds_multiples_of_five():
    # RE2DRender reframes anything else (M0 finding 6)
    assert check_frame_bounds(65, 65, 61) == []
    assert check_frame_bounds(3770, 690) == []
    problems = check_frame_bounds(63, 63)
    assert len(problems) == 2
    assert "multiple of 5" in problems[0]


def test_frame_bounds_degenerate_input():
    assert any("frame count" in p for p in check_frame_bounds(65, 65, 0))
    assert any("positive" in p for p in check_frame_bounds(0, 65))


def _frame_with_alpha_at(h, w, row, col):
    frame = np.zeros((h, w, 4), dtype=np.float32)
    frame[row, col, 3] = 1.0
    return frame


def test_overflow_detects_border_alpha_per_frame():
    clean = _frame_with_alpha_at(10, 10, 5, 5)
    top = _frame_with_alpha_at(10, 10, 0, 5)
    bottom = _frame_with_alpha_at(10, 10, 9, 5)
    left = _frame_with_alpha_at(10, 10, 5, 0)
    right = _frame_with_alpha_at(10, 10, 5, 9)
    assert overflow_frames([clean, top, clean, bottom, left, right]) == [1, 3, 4, 5]
    assert overflow_frames([clean]) == []


def test_overflow_threshold_ignores_noise():
    noisy = np.zeros((10, 10, 4), dtype=np.float32)
    noisy[0, :, 3] = 1.0 / 512.0  # below one 8-bit step
    assert overflow_frames([noisy]) == []


def _edge_pixels(edge_rgb, edge_alpha):
    px = np.zeros((4, 4, 4), dtype=np.float32)
    px[1:3, 1:3] = [1.0, 1.0, 1.0, 1.0]        # solid white core
    px[0, :, :3] = edge_rgb                     # anti-aliased edge row
    px[0, :, 3] = edge_alpha
    return px


def test_classify_alpha():
    # straight: edge colour stays bright at partial coverage
    assert classify_alpha(_edge_pixels(1.0, 0.5)) == ALPHA_STRAIGHT
    # premultiplied: every channel <= alpha
    assert classify_alpha(_edge_pixels(0.5, 0.5)) == ALPHA_PREMULTIPLIED
    # no partial-coverage pixels -> cannot tell (M0-proven fallback path)
    hard = np.zeros((2, 2, 4), dtype=np.float32)
    hard[0, 0] = [1, 1, 1, 1]
    assert classify_alpha(hard) == ALPHA_INCONCLUSIVE
