import pytest

from gopro_overlay.entry import Entry
from gopro_overlay.point import Point
from gopro_overlay.timeseries import Timeseries
from gopro_overlay.timeseries_process import calculate_avg_speed, calculate_avg_speed_moving
from gopro_overlay.units import units
from test_timeseries import datetime_of, metres


def test_calculate_avg_speed_first_frame_zero():
    ts = Timeseries()
    ts.add(
        Entry(datetime_of(1), point=Point(51.50186, -0.14056), dist=metres(0)),
    )
    ts.process(calculate_avg_speed())
    assert ts.get(datetime_of(1)).avg_speed.magnitude == pytest.approx(0)


def test_calculate_avg_speed_basic():
    ts = Timeseries()
    ts.add(
        Entry(datetime_of(1), point=Point(51.50186, -0.14056), dist=metres(0)),
        Entry(datetime_of(2), point=Point(51.50186, -0.14056), dist=metres(100)),
    )
    ts.process(calculate_avg_speed())

    # First frame: elapsed=0, avg_speed=0
    assert ts.get(datetime_of(1)).avg_speed.magnitude == pytest.approx(0)
    # Second frame: total_dist=100m, elapsed=1s -> 100 m/s
    assert ts.get(datetime_of(2)).avg_speed.to("mps").magnitude == pytest.approx(100.0)


def test_calculate_avg_speed_accumulates():
    ts = Timeseries()
    ts.add(
        Entry(datetime_of(1), point=Point(51.50186, -0.14056), dist=metres(10)),
        Entry(datetime_of(2), point=Point(51.50186, -0.14056), dist=metres(20)),
        Entry(datetime_of(3), point=Point(51.50186, -0.14056), dist=metres(30)),
    )
    ts.process(calculate_avg_speed())

    # t=1: first frame, elapsed=0 -> 0
    assert ts.get(datetime_of(1)).avg_speed.magnitude == pytest.approx(0)
    # t=2: total_dist=10+20=30m, elapsed=1s -> 30 m/s
    assert ts.get(datetime_of(2)).avg_speed.to("mps").magnitude == pytest.approx(30.0)
    # t=3: total_dist=10+20+30=60m, elapsed=2s -> 30 m/s
    assert ts.get(datetime_of(3)).avg_speed.to("mps").magnitude == pytest.approx(30.0)


def test_calculate_avg_speed_no_dist():
    ts = Timeseries()
    ts.add(
        Entry(datetime_of(1), point=Point(51.50186, -0.14056)),
        Entry(datetime_of(2), point=Point(51.50186, -0.14056)),
    )
    ts.process(calculate_avg_speed())

    assert ts.get(datetime_of(1)).avg_speed.magnitude == pytest.approx(0)
    assert ts.get(datetime_of(2)).avg_speed.magnitude == pytest.approx(0)


def test_calculate_avg_speed_moving_basic():
    ts = Timeseries()
    ts.add(
        Entry(datetime_of(1), point=Point(51.50186, -0.14056), dist=metres(0),
              speed=units.Quantity(10, units.mps)),
        Entry(datetime_of(2), point=Point(51.50186, -0.14056), dist=metres(100),
              speed=units.Quantity(10, units.mps)),
        Entry(datetime_of(3), point=Point(51.50186, -0.14056), dist=metres(100),
              speed=units.Quantity(0, units.mps)),  # stopped
    )
    ts.process(calculate_avg_speed_moving(moving_threshold_mps=5.0))

    # t=1: first frame, no last_dt -> moving_time=0 -> 0
    assert ts.get(datetime_of(1)).avg_speed_moving.magnitude == pytest.approx(0)
    # t=2: speed=10 >= 5 threshold, moving_time=1s, total_dist=100 -> 100 m/s
    assert ts.get(datetime_of(2)).avg_speed_moving.to("mps").magnitude == pytest.approx(100.0)
    # t=3: speed=0 < 5 threshold, moving_time stays 1s, total_dist=200 -> 200 m/s
    assert ts.get(datetime_of(3)).avg_speed_moving.to("mps").magnitude == pytest.approx(200.0)


def test_calculate_avg_speed_moving_all_stopped():
    ts = Timeseries()
    ts.add(
        Entry(datetime_of(1), point=Point(51.50186, -0.14056), dist=metres(0),
              speed=units.Quantity(0, units.mps)),
        Entry(datetime_of(2), point=Point(51.50186, -0.14056), dist=metres(10),
              speed=units.Quantity(0, units.mps)),
    )
    ts.process(calculate_avg_speed_moving(moving_threshold_mps=1.0))

    assert ts.get(datetime_of(1)).avg_speed_moving.magnitude == pytest.approx(0)
    assert ts.get(datetime_of(2)).avg_speed_moving.magnitude == pytest.approx(0)


def test_calculate_avg_speed_moving_custom_threshold():
    ts = Timeseries()
    ts.add(
        Entry(datetime_of(1), point=Point(51.50186, -0.14056), dist=metres(0),
              speed=units.Quantity(4.9, units.mps)),
        Entry(datetime_of(2), point=Point(51.50186, -0.14056), dist=metres(50),
              speed=units.Quantity(5.1, units.mps)),
        Entry(datetime_of(3), point=Point(51.50186, -0.14056), dist=metres(50),
              speed=units.Quantity(4.9, units.mps)),
    )
    ts.process(calculate_avg_speed_moving(moving_threshold_mps=5.0))

    # t=1: first frame -> 0
    assert ts.get(datetime_of(1)).avg_speed_moving.magnitude == pytest.approx(0)
    # t=2: speed=5.1 >= 5.0, but previous speed=4.9 < 5.0 at t=1
    # The check is on current entry speed, so at t=2 speed=5.1 >= 5, moving_time += 1s
    assert ts.get(datetime_of(2)).avg_speed_moving.to("mps").magnitude == pytest.approx(50.0)
    # t=3: speed=4.9 < 5.0, not moving. moving_time stays 1s, total_dist=100
    assert ts.get(datetime_of(3)).avg_speed_moving.to("mps").magnitude == pytest.approx(100.0)


def test_calculate_avg_speed_moving_uses_cspeed_fallback():
    ts = Timeseries()
    ts.add(
        Entry(datetime_of(1), point=Point(51.50186, -0.14056), dist=metres(0),
              cspeed=units.Quantity(10, units.mps)),
        Entry(datetime_of(2), point=Point(51.50186, -0.14056), dist=metres(100),
              cspeed=units.Quantity(10, units.mps)),
    )
    ts.process(calculate_avg_speed_moving(moving_threshold_mps=5.0))

    # speed is None but cspeed is set -> uses cspeed
    assert ts.get(datetime_of(2)).avg_speed_moving.to("mps").magnitude == pytest.approx(100.0)


def test_calculate_avg_speed_moving_first_frame():
    ts = Timeseries()
    ts.add(
        Entry(datetime_of(1), point=Point(51.50186, -0.14056), dist=metres(0),
              speed=units.Quantity(10, units.mps)),
    )
    ts.process(calculate_avg_speed_moving(moving_threshold_mps=1.0))

    # First entry: no last_dt -> no moving_time increment
    assert ts.get(datetime_of(1)).avg_speed_moving.magnitude == pytest.approx(0)
