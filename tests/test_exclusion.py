"""Tests for gopro_overlay.exclusion module."""

import json
import tempfile
from pathlib import Path

import pytest

from gopro_overlay.exclusion import (
    CircleExclusionZone,
    ExclusionZoneSet,
    NoExclusionZones,
    RedactStyle,
    draw_redacted,
    load_exclusion_zones,
    default_exclusion_path,
)
from gopro_overlay.point import Point


# ---------------------------------------------------------------------------
# CircleExclusionZone
# ---------------------------------------------------------------------------

class TestCircleExclusionZone:

    def test_point_inside_zone(self):
        zone = CircleExclusionZone(
            name="Home",
            center=Point(lat=-27.47, lon=153.03),
            radius_m=200,
        )
        # Same point as centre — clearly inside
        assert zone.contains(Point(lat=-27.47, lon=153.03))

    def test_point_outside_zone(self):
        zone = CircleExclusionZone(
            name="Home",
            center=Point(lat=-27.47, lon=153.03),
            radius_m=200,
        )
        # ~1 degree away (~111 km) — clearly outside
        assert not zone.contains(Point(lat=-26.47, lon=153.03))

    def test_point_near_boundary_inside(self):
        zone = CircleExclusionZone(
            name="Test",
            center=Point(lat=0.0, lon=0.0),
            radius_m=1000,
        )
        # ~100m north of centre — inside 1000m radius
        assert zone.contains(Point(lat=0.0009, lon=0.0))

    def test_point_near_boundary_outside(self):
        zone = CircleExclusionZone(
            name="Test",
            center=Point(lat=0.0, lon=0.0),
            radius_m=100,
        )
        # ~200m north — outside 100m radius
        assert not zone.contains(Point(lat=0.0018, lon=0.0))

    def test_contains_with_buffer_inside_buffer(self):
        zone = CircleExclusionZone(
            name="Test",
            center=Point(lat=0.0, lon=0.0),
            radius_m=100,
            buffer_m=150,
        )
        # ~200m away — outside radius (100m) but inside radius+buffer (250m)
        assert not zone.contains(Point(lat=0.0018, lon=0.0))
        assert zone.contains_with_buffer(Point(lat=0.0018, lon=0.0))

    def test_contains_with_buffer_outside_buffer(self):
        zone = CircleExclusionZone(
            name="Test",
            center=Point(lat=0.0, lon=0.0),
            radius_m=100,
            buffer_m=50,
        )
        # ~200m away — outside radius+buffer (150m)
        assert not zone.contains_with_buffer(Point(lat=0.0018, lon=0.0))

    def test_contains_with_zero_buffer_same_as_contains(self):
        zone = CircleExclusionZone(
            name="Test",
            center=Point(lat=0.0, lon=0.0),
            radius_m=100,
            buffer_m=0.0,
        )
        p_inside = Point(lat=0.0005, lon=0.0)
        p_outside = Point(lat=0.0018, lon=0.0)
        assert zone.contains(p_inside) == zone.contains_with_buffer(p_inside)
        assert zone.contains(p_outside) == zone.contains_with_buffer(p_outside)

    def test_zero_radius_never_contains(self):
        zone = CircleExclusionZone(
            name="ZeroRadius",
            center=Point(lat=0.0, lon=0.0),
            radius_m=0,
        )
        # Even the exact centre point: geodesic distance is 0, and 0 <= 0 is True
        # so this should contain the exact centre
        assert zone.contains(Point(lat=0.0, lon=0.0))
        # But any offset should not
        assert not zone.contains(Point(lat=0.001, lon=0.0))


# ---------------------------------------------------------------------------
# ExclusionZoneSet
# ---------------------------------------------------------------------------

class TestExclusionZoneSet:

    def test_is_excluded_single_zone(self):
        zones = ExclusionZoneSet(zones=[
            CircleExclusionZone(
                name="Home",
                center=Point(lat=-27.47, lon=153.03),
                radius_m=200,
            )
        ])
        assert zones.is_excluded(Point(lat=-27.47, lon=153.03))
        assert not zones.is_excluded(Point(lat=-26.47, lon=153.03))

    def test_is_excluded_multiple_zones(self):
        zones = ExclusionZoneSet(zones=[
            CircleExclusionZone(
                name="Home",
                center=Point(lat=-27.47, lon=153.03),
                radius_m=200,
            ),
            CircleExclusionZone(
                name="Office",
                center=Point(lat=-27.50, lon=153.00),
                radius_m=200,
            ),
        ])
        assert zones.is_excluded(Point(lat=-27.47, lon=153.03))
        assert zones.is_excluded(Point(lat=-27.50, lon=153.00))
        assert not zones.is_excluded(Point(lat=-26.00, lon=153.00))

    def test_disabled_zone_not_excluded(self):
        zones = ExclusionZoneSet(zones=[
            CircleExclusionZone(
                name="Disabled",
                center=Point(lat=-27.47, lon=153.03),
                radius_m=200,
                enabled=False,
            )
        ])
        # Inside the zone, but it's disabled
        assert not zones.is_excluded(Point(lat=-27.47, lon=153.03))

    def test_empty_zone_set(self):
        zones = ExclusionZoneSet(zones=[])
        assert not zones.is_excluded(Point(lat=-27.47, lon=153.03))


# ---------------------------------------------------------------------------
# NoExclusionZones
# ---------------------------------------------------------------------------

class TestNoExclusionZones:

    def test_never_excluded(self):
        nz = NoExclusionZones()
        assert not nz.is_excluded(Point(lat=0.0, lon=0.0))

    def test_pre_scan_empty(self):
        nz = NoExclusionZones()
        assert nz.pre_scan() == []

    def test_has_redact_style(self):
        nz = NoExclusionZones()
        assert isinstance(nz.redact_style, RedactStyle)


# ---------------------------------------------------------------------------
# JSON loading
# ---------------------------------------------------------------------------

class TestLoadExclusionZones:

    def _write_json(self, data):
        """Write JSON to a temp file and return its Path."""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(data, f)
        f.close()
        return Path(f.name)

    def test_load_valid_file(self):
        path = self._write_json({
            "version": 1,
            "zones": [
                {
                    "name": "Home",
                    "type": "circle",
                    "center": {"lat": -27.47, "lon": 153.03},
                    "radius_m": 200,
                    "buffer_m": 50,
                    "enabled": True,
                }
            ]
        })
        zs = load_exclusion_zones(path)
        assert len(zs.zones) == 1
        assert zs.zones[0].name == "Home"
        assert zs.zones[0].radius_m == 200
        assert zs.zones[0].buffer_m == 50
        assert zs.zones[0].enabled is True
        path.unlink()

    def test_load_with_redact_style(self):
        path = self._write_json({
            "version": 1,
            "zones": [],
            "redact_style": {"fill_colour": [255, 0, 0, 255]},
        })
        zs = load_exclusion_zones(path)
        assert zs.redact_style.fill_colour == (255, 0, 0, 255)
        path.unlink()

    def test_load_wrong_version(self):
        path = self._write_json({"version": 99, "zones": []})
        with pytest.raises(ValueError, match="version"):
            load_exclusion_zones(path)
        path.unlink()

    def test_load_unsupported_type(self):
        path = self._write_json({
            "version": 1,
            "zones": [{"name": "X", "type": "polygon", "vertices": []}]
        })
        with pytest.raises(ValueError, match="unsupported type"):
            load_exclusion_zones(path)
        path.unlink()

    def test_load_missing_name(self):
        path = self._write_json({
            "version": 1,
            "zones": [{"type": "circle", "center": {"lat": 0, "lon": 0}, "radius_m": 100}]
        })
        with pytest.raises(ValueError, match="missing 'name'"):
            load_exclusion_zones(path)
        path.unlink()

    def test_load_missing_center(self):
        path = self._write_json({
            "version": 1,
            "zones": [{"name": "X", "type": "circle", "radius_m": 100}]
        })
        with pytest.raises(ValueError, match="missing 'center'"):
            load_exclusion_zones(path)
        path.unlink()

    def test_load_invalid_latitude(self):
        path = self._write_json({
            "version": 1,
            "zones": [{"name": "X", "type": "circle",
                        "center": {"lat": 91, "lon": 0}, "radius_m": 100}]
        })
        with pytest.raises(ValueError, match="latitude"):
            load_exclusion_zones(path)
        path.unlink()

    def test_load_invalid_longitude(self):
        path = self._write_json({
            "version": 1,
            "zones": [{"name": "X", "type": "circle",
                        "center": {"lat": 0, "lon": 181}, "radius_m": 100}]
        })
        with pytest.raises(ValueError, match="longitude"):
            load_exclusion_zones(path)
        path.unlink()

    def test_load_disabled_zone(self):
        path = self._write_json({
            "version": 1,
            "zones": [{
                "name": "Off",
                "type": "circle",
                "center": {"lat": 0, "lon": 0},
                "radius_m": 100,
                "enabled": False,
            }]
        })
        zs = load_exclusion_zones(path)
        assert zs.zones[0].enabled is False
        path.unlink()

    def test_load_defaults_buffer_and_enabled(self):
        path = self._write_json({
            "version": 1,
            "zones": [{
                "name": "Defaults",
                "type": "circle",
                "center": {"lat": 0, "lon": 0},
                "radius_m": 100,
            }]
        })
        zs = load_exclusion_zones(path)
        assert zs.zones[0].buffer_m == 0.0
        assert zs.zones[0].enabled is True
        path.unlink()


# ---------------------------------------------------------------------------
# draw_redacted
# ---------------------------------------------------------------------------

class TestDrawRedacted:

    def test_fills_frame_black(self):
        from PIL import Image
        frame = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
        draw_redacted(frame, RedactStyle())
        # Check centre pixel is black
        assert frame.getpixel((50, 50)) == (0, 0, 0, 255)
        # Check corner
        assert frame.getpixel((0, 0)) == (0, 0, 0, 255)

    def test_fills_frame_custom_colour(self):
        from PIL import Image
        frame = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
        draw_redacted(frame, RedactStyle(fill_colour=(255, 0, 0, 255)))
        assert frame.getpixel((50, 50)) == (255, 0, 0, 255)


# ---------------------------------------------------------------------------
# default_exclusion_path
# ---------------------------------------------------------------------------

class TestDefaultPath:

    def test_returns_expected_path(self):
        p = default_exclusion_path()
        assert p.name == "exclusion-zones.json"
        assert ".gopro-graphics" in str(p)
