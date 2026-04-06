"""
Exclusion zones for geographic redaction of video frames.

Provides circle-based exclusion zones that replace video frames with solid
black when the GPS position falls within a defined zone. Zones are loaded
from a JSON file (default: ~/.gopro-graphics/exclusion-zones.json).
"""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from geographiclib.geodesic import Geodesic

from gopro_overlay.point import Point

# 1 degree of latitude in metres (approximate)
_METRES_PER_DEGREE_LAT = 111_320.0


@dataclass
class RedactStyle:
    fill_colour: tuple = (0, 0, 0, 255)


@dataclass
class CircleExclusionZone:
    name: str
    center: Point
    radius_m: float
    buffer_m: float = 0.0
    enabled: bool = True
    _bbox: Optional[tuple] = field(default=None, repr=False)

    def __post_init__(self):
        self._compute_bbox()

    def _compute_bbox(self):
        """Precompute a lat/lon bounding box for fast rejection."""
        total_m = self.radius_m + self.buffer_m
        dlat = total_m / _METRES_PER_DEGREE_LAT
        # Longitude degrees vary with latitude
        cos_lat = math.cos(math.radians(self.center.lat))
        if cos_lat < 1e-10:
            dlon = 180.0  # near poles, accept everything
        else:
            dlon = total_m / (_METRES_PER_DEGREE_LAT * cos_lat)
        self._bbox = (
            self.center.lat - dlat,
            self.center.lat + dlat,
            self.center.lon - dlon,
            self.center.lon + dlon,
        )

    def _in_bbox(self, point: Point) -> bool:
        min_lat, max_lat, min_lon, max_lon = self._bbox
        return (min_lat <= point.lat <= max_lat and
                min_lon <= point.lon <= max_lon)

    def contains(self, point: Point) -> bool:
        """Return True if point is within the zone radius."""
        if not self._in_bbox(point):
            return False
        dist = abs(Geodesic.WGS84.Inverse(
            self.center.lat, self.center.lon, point.lat, point.lon
        )['s12'])
        return dist <= self.radius_m

    def contains_with_buffer(self, point: Point) -> bool:
        """Return True if point is within radius + buffer."""
        if self.buffer_m == 0.0:
            return self.contains(point)
        if not self._in_bbox(point):
            return False
        dist = abs(Geodesic.WGS84.Inverse(
            self.center.lat, self.center.lon, point.lat, point.lon
        )['s12'])
        return dist <= (self.radius_m + self.buffer_m)


class ExclusionZoneSet:
    def __init__(self, zones: List[CircleExclusionZone],
                 redact_style: Optional[RedactStyle] = None):
        self.zones = zones
        self.redact_style = redact_style or RedactStyle()

    def is_excluded(self, point: Point) -> bool:
        """Return True if point falls inside any enabled zone (with buffer)."""
        return any(z.contains_with_buffer(point)
                   for z in self.zones if z.enabled)

    def pre_scan(self, frame_meta, step_seconds=0.1) -> List[Tuple[float, float]]:
        """Pre-scan GPS data to find exclusion time windows.

        Returns list of (start_seconds, end_seconds) pairs where the
        position is inside an exclusion zone.
        """
        from gopro_overlay.timeunits import timeunits

        stepper = frame_meta.stepper(timeunits(seconds=step_seconds))
        windows = []
        in_zone = False
        window_start = 0.0

        for dt in stepper.steps():
            entry = frame_meta.get(dt)
            seconds = dt.magnitude if hasattr(dt, 'magnitude') else float(dt)

            if entry.point is not None:
                excluded = self.is_excluded(entry.point)
            else:
                excluded = False

            if excluded and not in_zone:
                window_start = seconds
                in_zone = True
            elif not excluded and in_zone:
                windows.append((window_start, seconds))
                in_zone = False

        # Close any open window
        if in_zone:
            windows.append((window_start, seconds))

        return windows


class NoExclusionZones:
    """Null object when no exclusion zones are configured."""

    redact_style = RedactStyle()

    def is_excluded(self, point) -> bool:
        return False

    def pre_scan(self, *args) -> list:
        return []


def default_exclusion_path() -> Path:
    """Return the default exclusion zones file path."""
    return Path.home() / ".gopro-graphics" / "exclusion-zones.json"


def load_exclusion_zones(path: Path) -> ExclusionZoneSet:
    """Load exclusion zones from a JSON file.

    Raises ValueError on schema violations.
    """
    with open(path) as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Exclusion zones file must contain a JSON object")

    version = data.get("version")
    if version != 1:
        raise ValueError(f"Unsupported exclusion zones version: {version} (expected 1)")

    raw_zones = data.get("zones", [])
    if not isinstance(raw_zones, list):
        raise ValueError("'zones' must be an array")

    zones = []
    for i, z in enumerate(raw_zones):
        ztype = z.get("type")
        if ztype != "circle":
            raise ValueError(
                f"Zone {i} has unsupported type '{ztype}' (only 'circle' is supported)")

        name = z.get("name")
        if not name:
            raise ValueError(f"Zone {i} is missing 'name'")

        center = z.get("center")
        if not center or "lat" not in center or "lon" not in center:
            raise ValueError(f"Zone '{name}' is missing 'center' with 'lat' and 'lon'")

        lat = float(center["lat"])
        lon = float(center["lon"])
        if not (-90 <= lat <= 90):
            raise ValueError(f"Zone '{name}': latitude {lat} out of range [-90, 90]")
        if not (-180 <= lon <= 180):
            raise ValueError(f"Zone '{name}': longitude {lon} out of range [-180, 180]")

        radius_m = z.get("radius_m")
        if radius_m is None or float(radius_m) < 0:
            raise ValueError(f"Zone '{name}': radius_m must be a non-negative number")
        radius_m = float(radius_m)

        buffer_m = float(z.get("buffer_m", 0))
        enabled = z.get("enabled", True)

        zones.append(CircleExclusionZone(
            name=name,
            center=Point(lat=lat, lon=lon),
            radius_m=radius_m,
            buffer_m=buffer_m,
            enabled=enabled,
        ))

    # Parse optional redact_style
    redact_style = RedactStyle()
    if "redact_style" in data:
        rs = data["redact_style"]
        if "fill_colour" in rs:
            redact_style.fill_colour = tuple(rs["fill_colour"])

    return ExclusionZoneSet(zones=zones, redact_style=redact_style)


def draw_redacted(frame, style: RedactStyle):
    """Fill frame with solid colour (black by default)."""
    from PIL import ImageDraw
    draw = ImageDraw.Draw(frame)
    draw.rectangle([0, 0, frame.width, frame.height], fill=style.fill_colour)
