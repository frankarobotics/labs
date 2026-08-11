import pytest

from pipeline_configs import PAD_VALUE, PADDING_WARN_FRACTION, LetterboxGeometry, compute_letterbox_geometry


def test_wide_source_binds_target_width() -> None:
    geometry = compute_letterbox_geometry((720, 1280), (480, 640))

    assert geometry == LetterboxGeometry(width=640, height=360, left=0, top=60, target_width=640, target_height=480)
    assert (geometry.right, geometry.bottom) == (0, 60)
    assert geometry.is_padded
    assert geometry.padding_fraction == pytest.approx(0.25)


def test_tall_source_binds_target_height() -> None:
    geometry = compute_letterbox_geometry((480, 640), (720, 1280))

    assert geometry == LetterboxGeometry(width=960, height=720, left=160, top=0, target_width=1280, target_height=720)
    assert (geometry.right, geometry.bottom) == (160, 0)


def test_matching_aspect_has_no_padding() -> None:
    geometry = compute_letterbox_geometry((480, 640), (240, 320))

    assert geometry == LetterboxGeometry(width=320, height=240, left=0, top=0, target_width=320, target_height=240)
    assert not geometry.is_padded
    assert geometry.padding_fraction == 0.0


def test_odd_padding_remainder_is_on_bottom_and_right() -> None:
    vertical_geometry = compute_letterbox_geometry((2, 3), (4, 4))
    horizontal_geometry = compute_letterbox_geometry((3, 2), (4, 4))

    assert (vertical_geometry.top, vertical_geometry.bottom) == (0, 1)
    assert (horizontal_geometry.left, horizontal_geometry.right) == (0, 1)


def test_minor_axis_is_clamped_to_one_pixel() -> None:
    geometry = compute_letterbox_geometry((1, 10_000), (10, 10))

    assert (geometry.height, geometry.width) == (1, 10)
    assert (geometry.top, geometry.bottom) == (4, 5)


@pytest.mark.parametrize("shape", [(0, 1), (1, 0), (-1, 1), (1, -1)])
def test_non_positive_dimensions_are_rejected(shape: tuple[int, int]) -> None:
    with pytest.raises(ValueError, match="dimensions must be positive"):
        compute_letterbox_geometry(shape, (1, 1))
    with pytest.raises(ValueError, match="dimensions must be positive"):
        compute_letterbox_geometry((1, 1), shape)


def test_exported_constants_define_black_padding_and_warning_threshold() -> None:
    assert PAD_VALUE == 0
    assert PADDING_WARN_FRACTION == 0.01
