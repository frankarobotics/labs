import pytest

from lerobot_conversion.fps_grid import NS_PER_S, grid_intervals, grid_timestamps_ns


@pytest.mark.parametrize("fps", [7, 15, 30])
def test_an_exact_span_counts_every_interval(fps: int) -> None:
    assert grid_intervals(NS_PER_S, fps) == fps


def test_a_partial_interval_is_not_counted() -> None:
    assert grid_intervals(NS_PER_S // 7 - 1, 7) == 0


def test_timestamps_step_exactly_one_interval_from_the_start() -> None:
    assert grid_timestamps_ns(1_000, 4, 3).tolist() == [1_000, 333_334_333, 666_667_667, 1_000_001_000]
