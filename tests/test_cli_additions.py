from pathlib import Path
from typing import Optional

from gopro_overlay.arguments import gopro_dashboard_arguments


def do_args(*args, input: Optional[str] = "input", output: Optional[str] = "output"):
    all_args = [a for a in [input, output, *args] if a]
    return gopro_dashboard_arguments(all_args)


def test_xlsx_argument():
    args = do_args("--xlsx", "/tmp/x.xlsx")
    assert args.xlsx == Path("/tmp/x.xlsx")


def test_xlsx_default_none():
    args = do_args()
    assert args.xlsx is None


def test_gpx_time_offset_default():
    args = do_args()
    assert args.gpx_time_offset == 0.0


def test_gpx_time_offset_positive():
    args = do_args("--gpx-time-offset", "30.5")
    assert args.gpx_time_offset == 30.5


def test_gpx_time_offset_negative():
    args = do_args("--gpx-time-offset", "-15")
    assert args.gpx_time_offset == -15.0


def test_sample_duration_default_none():
    args = do_args()
    assert args.sample_duration is None


def test_sample_duration_set():
    args = do_args("--sample-duration", "60")
    assert args.sample_duration == 60.0


def test_moving_threshold_default():
    args = do_args()
    assert args.moving_threshold == 2.0


def test_moving_threshold_custom():
    args = do_args("--moving-threshold", "5.0")
    assert args.moving_threshold == 5.0
