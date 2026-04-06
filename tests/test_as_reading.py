import pytest

from gopro_overlay.layout_xml_cairo import as_reading


def test_as_reading_zero_to_one():
    r = as_reading(lambda: 50, 0, 100)
    assert r().value() == pytest.approx(0.5)


def test_as_reading_at_min():
    r = as_reading(lambda: 0, 0, 100)
    assert r().value() == pytest.approx(0.0)


def test_as_reading_at_max():
    r = as_reading(lambda: 100, 0, 100)
    assert r().value() == pytest.approx(1.0)


def test_as_reading_negative_value_regen():
    # (-20 - (-50)) / (100 - (-50)) = 30 / 150 = 0.2
    r = as_reading(lambda: -20, -50, 100)
    assert r().value() == pytest.approx(0.2)


def test_as_reading_min_not_zero():
    # (60 - 20) / (120 - 20) = 40 / 100 = 0.4
    r = as_reading(lambda: 60, 20, 120)
    assert r().value() == pytest.approx(0.4)


def test_as_reading_negative_min():
    # (0 - (-500)) / (2000 - (-500)) = 500 / 2500 = 0.2
    r = as_reading(lambda: 0, -500, 2000)
    assert r().value() == pytest.approx(0.2)


def test_as_reading_negative_value_low():
    # (-250 - (-500)) / (2000 - (-500)) = 250 / 2500 = 0.1
    r = as_reading(lambda: -250, -500, 2000)
    assert r().value() == pytest.approx(0.1)


def test_as_reading_zero_range_clamps():
    # range = max(5 - 5, 1) = 1, result = (5 - 5) / 1 = 0.0
    r = as_reading(lambda: 5, 5, 5)
    assert r().value() == pytest.approx(0.0)
