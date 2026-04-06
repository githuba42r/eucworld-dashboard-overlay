from gopro_overlay.layout_xml import metric_accessor_from
from gopro_overlay.timeseries import Entry
from gopro_overlay.units import units
from test_timeseries import datetime_of


def test_metric_accessor_battery():
    battery = units.Quantity(85, units.percent)
    entry = Entry(datetime_of(0), battery=battery)
    assert metric_accessor_from("battery")(entry) == battery


def test_metric_accessor_voltage():
    voltage = units.Quantity(67.2, units.volt)
    entry = Entry(datetime_of(0), voltage=voltage)
    assert metric_accessor_from("voltage")(entry) == voltage


def test_metric_accessor_current():
    current = units.Quantity(5.1, units.ampere)
    entry = Entry(datetime_of(0), current=current)
    assert metric_accessor_from("current")(entry) == current


def test_metric_accessor_avg_speed():
    avg = units.Quantity(15, units.mps)
    entry = Entry(datetime_of(0), avg_speed=avg)
    assert metric_accessor_from("avg-speed")(entry) == avg


def test_metric_accessor_avg_speed_moving():
    avg = units.Quantity(12, units.mps)
    entry = Entry(datetime_of(0), avg_speed_moving=avg)
    assert metric_accessor_from("avg-speed-moving")(entry) == avg


def test_metric_accessor_battery_none():
    entry = Entry(datetime_of(0))
    assert metric_accessor_from("battery")(entry) is None
