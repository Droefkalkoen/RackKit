"""World calibration math (§4.4) and the SDK panel geometry constants."""

import pytest

from reblend.model import calibration as cal


def test_panel_sizes():
    assert cal.panel_size_px("front", rack_units=2) == cal.PanelSize(3770, 690)
    assert cal.panel_size_px("back", rack_units=1) == cal.PanelSize(3770, 345)
    # folded panels are 130 px regardless of rack height (M0 finding 7)
    assert cal.panel_size_px("folded_front", rack_units=3) == cal.PanelSize(3770, 130)
    assert cal.panel_size_px("folded_back") == cal.PanelSize(3770, 130)


def test_bad_rack_units_raise():
    with pytest.raises(ValueError):
        cal.panel_size_px("front", rack_units=0)


def test_rack_units_from_backdrop_height():
    assert cal.rack_units_for_height(345) == 1
    assert cal.rack_units_for_height(690) == 2
    assert cal.rack_units_for_height(700) is None
    assert cal.rack_units_for_height(0) is None


def test_ortho_scale_frames_the_longer_side():
    assert cal.ortho_scale(65, 65, ppb=100.0) == pytest.approx(0.65)
    assert cal.ortho_scale(25, 60, ppb=100.0) == pytest.approx(0.60)


def test_ortho_scale_rejects_degenerate_input():
    with pytest.raises(ValueError):
        cal.ortho_scale(0, 65)
    with pytest.raises(ValueError):
        cal.ortho_scale(65, 65, ppb=0)


def test_world_roundtrip():
    world = cal.panel_px_to_world(950, 120, ppb=100.0)
    assert world == pytest.approx((9.5, 0.0, -1.2))
    assert cal.world_to_panel_px(world, ppb=100.0) == pytest.approx((950, 120))


def test_dominant_axis():
    assert cal.dominant_axis((0.0, -1.0, 0.0)) == (1, -1.0)
    assert cal.dominant_axis((0.0, 0.1, 0.9)) == (2, 1.0)
    assert cal.dominant_axis((-1.0, 0.0, 0.0)) == (0, -1.0)
    with pytest.raises(ValueError):
        cal.dominant_axis((0.0, 0.0, 0.0))


def test_element_center():
    # device_2D offset is the frame's top-left; registration sits at centre
    assert cal.element_center_px(950, 120, 65, 65) == (982.5, 152.5)
