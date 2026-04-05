#!/usr/bin/env python3
"""
GoPro Dashboard Overlay — Visual Layout Editor

A tkinter GUI for visually positioning overlay components on video frames,
generating XML layouts, and launching encoding with gopro-dashboard-overlay.
"""

import io
import json
import math
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from PIL import Image, ImageTk


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class VideoEntry:
    path: Path
    raw_width: int
    raw_height: int
    rotation: int
    eff_width: int
    eff_height: int
    duration_seconds: float
    creation_time: str  # ISO string

    @property
    def basename(self):
        return self.path.name


@dataclass
class OverlayComponent:
    name: str
    label: str
    x: int  # full-res coords
    y: int
    width: int  # full-res bounding box
    height: int
    enabled: bool = True
    color: str = "#4488ff"
    canvas_rect_id: Optional[int] = None
    canvas_text_id: Optional[int] = None
    xml_template: str = ""
    # Per-component custom properties (e.g. date/time formats)
    custom_props: dict = field(default_factory=dict)


# Component definitions: (name, label, ref_w, ref_h, colour, xml_template)
# Positions are set dynamically based on video dimensions
COMPONENT_DEFS = [
    ("date_and_time", "Date + Time", 200, 60, "#44aa88",
     '''    <composite x="{x}" y="{y}" width="{w}" height="{h}" name="date_and_time">
        <component type="datetime" x="0" y="0" format="{date_format}" size="16" align="right"/>
        <component type="datetime" x="0" y="24" format="{time_format}" truncate="5" size="32" align="right"/>
    </composite>'''),

    ("date_only", "Date Only", 200, 24, "#44aa66",
     '''    <composite x="{x}" y="{y}" width="{w}" height="{h}" name="date_only">
        <component type="datetime" x="0" y="0" format="{date_format}" size="24" align="right"/>
    </composite>'''),

    ("time_only", "Time Only", 200, 36, "#44aacc",
     '''    <composite x="{x}" y="{y}" width="{w}" height="{h}" name="time_only">
        <component type="datetime" x="0" y="0" format="{time_format}" truncate="5" size="32" align="right"/>
    </composite>'''),

    ("gps_info", "GPS (Full)", 280, 80, "#88aa44",
     '''    <composite x="{x}" y="{y}" width="{w}" height="{h}" name="gps_info">
        <frame name="gps-lock" x="226" y="24" width="32" height="32" bg="0,0,0,128" cr="5" opacity="0.4">
            <component type="gps-lock-icon" size="32"/>
         </frame>
        <composite y="36">
            <component type="text" x="0" y="0" size="{text_size}" align="left">GPS INFO</component>
            <component type="text" x="0" y="24" size="{text_size}" align="left">Lat: </component>
            <component type="text" x="128" y="24" size="{text_size}" align="left">Lon: </component>
            <component type="metric" x="118" y="24" metric="lat" dp="6" size="{text_size}" align="right" cache="False"/>
            <component type="metric" x="256" y="24" metric="lon" dp="6" size="{text_size}" align="right" cache="False"/>
        </composite>
    </composite>'''),

    ("gps_coords", "GPS Coordinates", 280, 24, "#88cc44",
     '''    <composite x="{x}" y="{y}" width="{w}" height="{h}" name="gps_coords">
        <component type="text" x="0" y="0" size="{text_size}" align="left">Lat: </component>
        <component type="text" x="128" y="0" size="{text_size}" align="left">Lon: </component>
        <component type="metric" x="118" y="0" metric="lat" dp="6" size="{text_size}" align="right" cache="False"/>
        <component type="metric" x="256" y="0" metric="lon" dp="6" size="{text_size}" align="right" cache="False"/>
    </composite>'''),

    ("gps_lock", "GPS Lock", 40, 40, "#88aa88",
     '''    <frame name="gps_lock" x="{x}" y="{y}" width="32" height="32" bg="0,0,0,128" cr="5" opacity="0.4">
        <component type="gps-lock-icon" size="32"/>
    </frame>'''),

    ("big_mph", "Speed", 208, 160, "#ff6644",
     '''    <composite x="{x}" y="{y}" width="{w}" height="{h}" name="big_mph">
        <component type="metric_unit" metric="speed" units="speed" size="{text_size}">{{:~c}}</component>
        <component type="metric" x="0" y="0" metric="speed" units="speed" dp="0" size="{speed_font_size}" />
    </composite>'''),

    ("gradient_chart", "Alt Chart", 600, 80, "#aa88cc",
     '''    <composite x="{x}" y="{y}" name="gradient_chart">
        <component type="chart" x="0" y="0" units="alt" width="{w}" height="{h}" filled="{chart_filled}" seconds="{chart_seconds}" bg="{chart_bg}" fill="{chart_fill}" line="{chart_line}"/>
    </composite>'''),

    ("gradient", "Gradient", 150, 70, "#ccaa44",
     '''    <composite x="{x}" y="{y}" width="{w}" height="{h}" name="gradient">
        <component type="text" x="70" y="0" size="{text_size}">SLOPE(%)</component>
        <component type="icon" x="0" y="0" file="slope-triangle.png" size="64"/>
        <component type="metric" x="70" y="18" metric="gradient" dp="0" size="{value_font_size}" />
    </composite>'''),

    ("altitude", "Altitude", 150, 70, "#44ccaa",
     '''    <composite x="{x}" y="{y}" width="{w}" height="{h}" name="altitude">
        <component type="metric_unit" x="70" y="0" metric="alt" units="alt" size="{text_size}">ALT({{:~C}})</component>
        <component type="icon" x="0" y="0" file="mountain.png" size="64"/>
        <component type="metric" x="70" y="18" metric="alt" units="alt" dp="0" size="{value_font_size}" />
    </composite>'''),

    ("temperature", "Temp", 150, 70, "#cc4444",
     '''    <composite x="{x}" y="{y}" width="{w}" height="{h}" name="temperature">
        <component type="metric_unit" x="-70" y="0" size="{text_size}" align="right" metric="temp" units="temp">TEMP({{:~C}})</component>
        <component type="icon" x="-64" y="0" file="thermometer.png" size="64"/>
        <component type="metric" x="-70" y="18" dp="0" size="{value_font_size}" align="right" metric="temp" units="temp"/>
    </composite>'''),

    ("cadence", "Cadence", 150, 70, "#44cc44",
     '''    <composite x="{x}" y="{y}" width="{w}" height="{h}" name="cadence">
        <component type="text" x="-70" y="0" size="{text_size}" align="right">RPM</component>
        <component type="icon" x="-64" y="0" file="gauge.png" size="64"/>
        <component type="metric" x="-70" y="18" metric="cadence" dp="0" size="{value_font_size}" align="right"/>
    </composite>'''),

    ("heartbeat", "Heart Rate", 150, 70, "#cc4488",
     '''    <composite x="{x}" y="{y}" width="{w}" height="{h}" name="heartbeat">
        <component type="text" x="-70" y="0" size="{text_size}" align="right">BPM</component>
        <component type="icon" x="-64" y="0" file="heartbeat.png" size="64"/>
        <component type="metric" x="-70" y="18" metric="hr" dp="0" size="{value_font_size}" align="right"/>
    </composite>'''),

    ("moving_map", "Moving Map", 256, 256, "#6688cc",
     '''    <component type="moving_map" name="moving_map" x="{x}" y="{y}" size="{map_size}" zoom="{map_zoom}" corner_radius="{map_corner_radius}" opacity="{map_opacity}" rotate="{map_rotate}"/>'''),

    ("journey_map", "Journey Map", 256, 256, "#8866cc",
     '''    <component type="journey_map" name="journey_map" x="{x}" y="{y}" size="{map_size}" corner_radius="{map_corner_radius}" opacity="{map_opacity}" fill="{jm_track_colour}" line-width="{jm_line_width}" loc-fill="{jm_loc_colour}" loc-outline="{jm_loc_outline}" loc-size="{jm_loc_size}"/>'''),
]

MAP_STYLES = [
    "osm",
    "cyclosm",
    "tf-cycle",
    "tf-outdoors",
    "tf-landscape",
    "tf-transport",
    "tf-transport-dark",
    "tf-atlas",
    "tf-pioneer",
    "tf-neighbourhood",
    "tf-spinal-map",
    "tf-mobile-atlas",
    "geo-osm-carto",
    "geo-osm-bright",
    "geo-osm-bright-grey",
    "geo-osm-bright-smooth",
    "geo-osm-liberty",
    "geo-positron",
    "geo-positron-blue",
    "geo-positron-red",
    "geo-dark-matter",
    "geo-dark-matter-brown",
    "geo-dark-matter-dark-grey",
    "geo-dark-matter-dark-purple",
    "geo-dark-matter-purple-roads",
    "geo-dark-matter-yellow-roads",
    "geo-toner",
    "geo-toner-grey",
    "geo-klokantech-basic",
    "geo-maptiler-3d",
]

# Map style descriptions and tile URL templates
# Sample tile: zoom=13, x=4823, y=3218 (approx Brisbane area)
MAP_STYLE_INFO = {
    "osm":            ("OpenStreetMap Standard", "free", "http://a.tile.openstreetmap.org/13/4823/3218.png"),
    "cyclosm":        ("CyclOSM - Cycling emphasis", "free", "https://a.tile-cyclosm.openstreetmap.fr/cyclosm/13/4823/3218.png"),
    "tf-cycle":       ("Thunderforest OpenCycleMap", "key:thunderforest", None),
    "tf-outdoors":    ("Thunderforest Outdoors - Hiking/trails", "key:thunderforest", None),
    "tf-landscape":   ("Thunderforest Landscape - Terrain", "key:thunderforest", None),
    "tf-transport":   ("Thunderforest Transport", "key:thunderforest", None),
    "tf-transport-dark": ("Thunderforest Transport Dark", "key:thunderforest", None),
    "tf-atlas":       ("Thunderforest Atlas", "key:thunderforest", None),
    "tf-pioneer":     ("Thunderforest Pioneer - Vintage", "key:thunderforest", None),
    "tf-neighbourhood": ("Thunderforest Neighbourhood", "key:thunderforest", None),
    "tf-spinal-map":  ("Thunderforest Spinal Map", "key:thunderforest", None),
    "tf-mobile-atlas": ("Thunderforest Mobile Atlas", "key:thunderforest", None),
    "geo-osm-carto":  ("Geoapify OSM Carto", "key:geoapify", None),
    "geo-osm-bright": ("Geoapify OSM Bright", "key:geoapify", None),
    "geo-osm-bright-grey": ("Geoapify OSM Bright Grey", "key:geoapify", None),
    "geo-osm-bright-smooth": ("Geoapify OSM Bright Smooth", "key:geoapify", None),
    "geo-osm-liberty": ("Geoapify OSM Liberty", "key:geoapify", None),
    "geo-positron":   ("Geoapify Positron - Light minimal", "key:geoapify", None),
    "geo-positron-blue": ("Geoapify Positron Blue", "key:geoapify", None),
    "geo-positron-red": ("Geoapify Positron Red", "key:geoapify", None),
    "geo-dark-matter": ("Geoapify Dark Matter", "key:geoapify", None),
    "geo-dark-matter-brown": ("Geoapify Dark Matter Brown", "key:geoapify", None),
    "geo-dark-matter-dark-grey": ("Geoapify Dark Matter Grey", "key:geoapify", None),
    "geo-dark-matter-dark-purple": ("Geoapify Dark Matter Purple", "key:geoapify", None),
    "geo-dark-matter-purple-roads": ("Geoapify Dark Purple Roads", "key:geoapify", None),
    "geo-dark-matter-yellow-roads": ("Geoapify Dark Yellow Roads", "key:geoapify", None),
    "geo-toner":      ("Geoapify Toner - B&W high contrast", "key:geoapify", None),
    "geo-toner-grey": ("Geoapify Toner Grey", "key:geoapify", None),
    "geo-klokantech-basic": ("Geoapify Klokantech Basic", "key:geoapify", None),
    "geo-maptiler-3d": ("Geoapify MapTiler 3D", "key:geoapify", None),
}

# Tile coordinate conversion
def _latlon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """Convert lat/lon to tile x/y coordinates at a given zoom level."""
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def _parse_gpx_points(gpx_path: Path) -> list[tuple[float, float, str]]:
    """Parse all track points from a GPX file. Returns list of (lat, lon, time_iso)."""
    import xml.etree.ElementTree as ET
    points = []
    try:
        tree = ET.parse(gpx_path)
        root = tree.getroot()
        ns = "http://www.topografix.com/GPX/1/1"
        for trkpt in root.iter(f"{{{ns}}}trkpt"):
            lat = float(trkpt.get("lat"))
            lon = float(trkpt.get("lon"))
            time_elem = trkpt.find(f"{{{ns}}}time")
            time_str = time_elem.text if time_elem is not None else ""
            points.append((lat, lon, time_str))
        if not points:
            for trkpt in root.iter("trkpt"):
                lat = float(trkpt.get("lat"))
                lon = float(trkpt.get("lon"))
                time_elem = trkpt.find("time")
                time_str = time_elem.text if time_elem is not None else ""
                points.append((lat, lon, time_str))
    except Exception:
        pass
    return points


def _extract_gpx_first_point(gpx_path: Path) -> Optional[tuple[float, float]]:
    """Extract the first lat/lon from a GPX file."""
    points = _parse_gpx_points(gpx_path)
    if points:
        return (points[0][0], points[0][1])
    return None


def _find_gpx_point_at_time(gpx_path: Path, video_creation_time: str) -> Optional[tuple[float, float]]:
    """Find the GPX point closest to a video's creation time."""
    from datetime import datetime, timezone
    points = _parse_gpx_points(gpx_path)
    if not points:
        return None

    # Parse video creation time
    try:
        # Handle formats like "2026-04-03T07:40:50.000000Z"
        vt = video_creation_time.replace("Z", "+00:00")
        video_dt = datetime.fromisoformat(vt)
        if video_dt.tzinfo is None:
            video_dt = video_dt.replace(tzinfo=timezone.utc)
    except Exception:
        # Can't parse video time, return first point
        return (points[0][0], points[0][1])

    # Find closest point by time
    best = None
    best_diff = None
    for lat, lon, time_str in points:
        if not time_str:
            continue
        try:
            pt = time_str.replace("Z", "+00:00")
            point_dt = datetime.fromisoformat(pt)
            if point_dt.tzinfo is None:
                point_dt = point_dt.replace(tzinfo=timezone.utc)
            diff = abs((point_dt - video_dt).total_seconds())
            if best_diff is None or diff < best_diff:
                best_diff = diff
                best = (lat, lon)
        except Exception:
            continue

    return best if best else (points[0][0], points[0][1])


# Map tile URL templates by provider
_TF_STYLES = {
    "tf-cycle": "cycle", "tf-outdoors": "outdoors", "tf-landscape": "landscape",
    "tf-transport": "transport", "tf-transport-dark": "transport-dark",
    "tf-atlas": "atlas", "tf-pioneer": "pioneer", "tf-neighbourhood": "neighbourhood",
    "tf-spinal-map": "spinal-map", "tf-mobile-atlas": "mobile-atlas",
}
_GEO_STYLES = {
    "geo-osm-carto": "osm-carto", "geo-osm-bright": "osm-bright",
    "geo-osm-bright-grey": "osm-bright-grey", "geo-osm-bright-smooth": "osm-bright-smooth",
    "geo-osm-liberty": "osm-liberty", "geo-positron": "positron",
    "geo-positron-blue": "positron-blue", "geo-positron-red": "positron-red",
    "geo-dark-matter": "dark-matter", "geo-dark-matter-brown": "dark-matter-brown",
    "geo-dark-matter-dark-grey": "dark-matter-dark-grey",
    "geo-dark-matter-dark-purple": "dark-matter-dark-purple",
    "geo-dark-matter-purple-roads": "dark-matter-purple-roads",
    "geo-dark-matter-yellow-roads": "dark-matter-yellow-roads",
    "geo-toner": "toner", "geo-toner-grey": "toner-grey",
    "geo-klokantech-basic": "klokantech-basic", "geo-maptiler-3d": "maptiler-3d",
}


def _get_api_keys() -> dict[str, str]:
    """Load API keys from config file and environment."""
    import json as _json
    keys = {}
    keys_file = Path.home() / ".gopro-graphics" / "map-api-keys.json"
    if keys_file.exists():
        try:
            keys = _json.loads(keys_file.read_text())
        except Exception:
            pass
    for ref in ("thunderforest", "geoapify"):
        env_val = os.environ.get(f"API_KEY_{ref.upper()}", "")
        if env_val:
            keys[ref] = env_val
    return keys


def _build_tile_url(style: str, lat: float, lon: float, zoom: int = 14) -> Optional[str]:
    """Build a tile preview URL for a given style centered on lat/lon."""
    tx, ty = _latlon_to_tile(lat, lon, zoom)
    keys = _get_api_keys()

    if style == "osm":
        return f"http://a.tile.openstreetmap.org/{zoom}/{tx}/{ty}.png"
    elif style == "cyclosm":
        return f"https://a.tile-cyclosm.openstreetmap.fr/cyclosm/{zoom}/{tx}/{ty}.png"
    elif style in _TF_STYLES:
        key = keys.get("thunderforest", "")
        if key:
            return f"https://a.tile.thunderforest.com/{_TF_STYLES[style]}/{zoom}/{tx}/{ty}.png?apikey={key}"
    elif style in _GEO_STYLES:
        key = keys.get("geoapify", "")
        if key:
            return f"https://maps.geoapify.com/v1/tile/{_GEO_STYLES[style]}/{zoom}/{tx}/{ty}.png?apiKey={key}"
    return None

# Date format presets (date only)
DATE_FORMATS = [
    "%Y/%m/%d",
    "%d %b %Y",
    "%d %B %Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y-%m-%d",
    "%a %d %b %Y",
    "%a %d %b",
    "%d %b",
]

# Time format presets (time only)
TIME_FORMATS = [
    "%H:%M:%S.%f",
    "%H:%M:%S",
    "%H:%M",
    "%I:%M:%S %p",
    "%I:%M %p",
]


# ---------------------------------------------------------------------------
# Video analysis via ffprobe
# ---------------------------------------------------------------------------

def analyse_video(video_path: Path) -> VideoEntry:
    """Analyse a video file using ffprobe, returning dimensions, rotation, duration."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", "-show_entries",
        "stream=width,height,duration,codec_type:stream_side_data=rotation:format=duration:format_tags=creation_time",
        str(video_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)

    raw_w = raw_h = 0
    rotation = 0
    duration = 0.0
    creation_time = ""

    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and raw_w == 0:
            raw_w = int(stream.get("width", 0))
            raw_h = int(stream.get("height", 0))
            if "side_data_list" in stream:
                for sd in stream["side_data_list"]:
                    if "rotation" in sd:
                        rotation = int(float(sd["rotation"]))

    fmt = data.get("format", {})
    duration = float(fmt.get("duration", 0))
    tags = fmt.get("tags", {})
    creation_time = tags.get("creation_time", "")

    # Effective dimensions after rotation
    if rotation in (-90, 90, -270, 270):
        eff_w, eff_h = raw_h, raw_w
    else:
        eff_w, eff_h = raw_w, raw_h

    return VideoEntry(
        path=video_path,
        raw_width=raw_w, raw_height=raw_h,
        rotation=rotation,
        eff_width=eff_w, eff_height=eff_h,
        duration_seconds=duration,
        creation_time=creation_time,
    )


def extract_frame(video_path: Path, time_seconds: float, eff_w: int, eff_h: int) -> Optional[Image.Image]:
    """Extract a single frame from a video at a given timestamp, auto-rotating."""
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-ss", str(time_seconds),
        "-i", str(video_path),
        "-frames:v", "1",
        "-vf", f"scale={eff_w}:{eff_h}",
        "-f", "rawvideo", "-pix_fmt", "rgba",
        "-"
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=15)
    expected = eff_w * eff_h * 4
    if len(result.stdout) != expected:
        return None
    return Image.frombytes("RGBA", (eff_w, eff_h), result.stdout)


def detect_gpu() -> Optional[str]:
    """Check for NVIDIA GPU encoding support."""
    try:
        subprocess.run(["nvidia-smi"], capture_output=True, check=True)
        result = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                                capture_output=True, text=True)
        if "h264_nvenc" in result.stdout:
            return "nvgpu"
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    return None


def detect_font() -> str:
    """Find a usable font."""
    candidates = [
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/Roboto-Medium.ttf",
        "/usr/share/fonts/truetype/roboto/Roboto-Medium.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    try:
        result = subprocess.run(["fc-match", "DejaVu Sans", "--format=%{file}"],
                                capture_output=True, text=True)
        if os.path.isfile(result.stdout.strip()):
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return "Roboto-Medium.ttf"


# ---------------------------------------------------------------------------
# Default component positions for a given resolution
# ---------------------------------------------------------------------------

def default_component_positions(eff_w: int, eff_h: int) -> list[OverlayComponent]:
    """Create overlay components with sensible default positions for the resolution."""
    # Scale component sizes relative to 1920x1080 baseline
    sx = eff_w / 1920.0
    sy = eff_h / 1080.0
    s = min(sx, sy)

    right_x = eff_w - int(280 * s)
    bottom_y = eff_h - int(100 * s)
    speed_y = eff_h - int(280 * s)

    defaults = {
        "date_and_time": (int(260 * s), 30),
        "date_only": (int(260 * s), 30),
        "time_only": (int(260 * s), 30),
        "gps_info": (right_x, 0),
        "gps_coords": (right_x, 0),
        "gps_lock": (right_x + int(226 * s), int(24 * s)),
        "big_mph": (16, speed_y),
        "gradient_chart": (int(400 * s), bottom_y),
        "gradient": (int(220 * s), bottom_y),
        "altitude": (16, bottom_y),
        "temperature": (eff_w - 20, speed_y),
        "cadence": (eff_w - 20, speed_y + int(80 * s)),
        "heartbeat": (eff_w - 20, speed_y + int(160 * s)),
        "moving_map": (right_x, int(100 * s)),
        "journey_map": (right_x, int(100 * s) + int(276 * s)),
    }

    # Default enabled/disabled
    disabled = {"heartbeat", "temperature", "cadence", "date_only", "time_only",
                 "gps_coords", "gps_lock"}

    components = []
    for name, label, ref_w, ref_h, color, xml_tmpl in COMPONENT_DEFS:
        # Use ref_w/ref_h as actual pixel sizes — they match the fixed pixel
        # values in the XML templates (font sizes, icon sizes, map sizes).
        # Don't scale by s; scaling is only for default positions.
        w = ref_w
        h = ref_h
        x, y = defaults.get(name, (0, 0))
        components.append(OverlayComponent(
            name=name, label=label,
            x=x, y=y, width=w, height=h,
            enabled=name not in disabled,
            color=color,
            xml_template=xml_tmpl,
        ))
    return components


# ---------------------------------------------------------------------------
# XML layout generation
# ---------------------------------------------------------------------------

def load_layout_xml(xml_path: Path, components: list[OverlayComponent]):
    """Load component positions and sizes from a layout XML file into existing components."""
    import xml.etree.ElementTree as ET
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Build a map of name -> dict of parsed properties from the XML
    comp_data: dict[str, dict] = {}

    for elem in root:
        name = elem.get("name", "")
        if not name:
            continue
        data = {
            "x": int(elem.get("x", "0")),
            "y": int(elem.get("y", "0")),
        }

        # Extract size info from the element itself
        # Square components (maps) use "size", composites use "width"/"height"
        if elem.get("size"):
            s = int(elem.get("size"))
            data["width"] = s
            data["height"] = s
        if elem.get("width"):
            data["width"] = int(elem.get("width"))
        if elem.get("height"):
            data["height"] = int(elem.get("height"))

        # Scan children for size-carrying attributes
        for child in elem:
            tag = child.tag.lower() if child.tag else ""
            child_type = child.get("type", "")

            # Chart: width and height on <component type="chart">
            if child_type == "chart":
                if child.get("width"):
                    data["width"] = int(child.get("width"))
                if child.get("height"):
                    data["height"] = int(child.get("height"))
                # Restore chart-specific props
                for attr in ("filled", "seconds", "bg", "fill", "line"):
                    val = child.get(attr)
                    if val is not None:
                        key = f"chart_{attr}"
                        data.setdefault("custom_props", {})[key] = val

            # Speed: font size from <component type="metric"> size attr
            if child_type == "metric" and child.get("size"):
                font_size = int(child.get("size"))
                data.setdefault("custom_props", {})["speed_font_size"] = font_size

            # Metric value font size for gradient/altitude
            if child_type == "metric" and name in ("gradient", "altitude"):
                if child.get("size"):
                    data.setdefault("custom_props", {})["value_font_size"] = int(child.get("size"))

            # Text/label font size
            if child_type in ("text", "datetime", "metric_unit") and child.get("size"):
                data.setdefault("custom_props", {})["text_size"] = int(child.get("size"))

        comp_data[name] = data

    # Apply parsed data to components
    for comp in components:
        if comp.name in comp_data:
            d = comp_data[comp.name]
            comp.x = d["x"]
            comp.y = d["y"]
            if "width" in d:
                comp.width = d["width"]
            if "height" in d:
                comp.height = d["height"]
            for k, v in d.get("custom_props", {}).items():
                comp.custom_props[k] = v
            comp.enabled = True
        else:
            comp.enabled = False


def generate_layout_xml(components: list[OverlayComponent], map_props: dict) -> str:
    """Generate layout XML from current component positions."""
    lines = ["<layout>"]
    for comp in components:
        if comp.enabled:
            # Merge global map_props with per-component overrides
            fmt_vars = dict(map_props)
            fmt_vars["x"] = comp.x
            fmt_vars["y"] = comp.y
            fmt_vars["w"] = comp.width
            fmt_vars["h"] = comp.height
            # Per-component overrides
            for k, v in comp.custom_props.items():
                fmt_vars[k] = v
            xml = comp.xml_template.format(**fmt_vars)
            lines.append(xml)
            lines.append("")
    lines.append("</layout>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Shell script generation
# ---------------------------------------------------------------------------

def generate_shell_script(
    videos: list[VideoEntry],
    gpx_path: Path,
    layout_xml_path: Path,
    speed_unit: str,
    font: str,
    gpu_profile: Optional[str],
    dashboard_script: Path,
    map_style: str = "osm",
    gpx_time_offset: float = 0.0,
) -> str:
    """Generate a bash script to process all videos."""
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]

    for video in videos:
        out_name = video.path.stem + "_overlay" + video.path.suffix
        out_path = video.path.parent / out_name

        cmd_parts = [
            f'python "{dashboard_script}"',
            f'--font "{font}"',
            f'--gpx "{gpx_path}"',
            "--use-gpx-only",
            "--video-time-start video-created",
            f"--overlay-size {video.eff_width}x{video.eff_height}",
            f"--units-speed {speed_unit}",
            "--layout xml",
            f'--layout-xml "{layout_xml_path}"',
            f"--map-style {map_style}",
        ]
        if gpx_time_offset:
            cmd_parts.append(f"--gpx-time-offset {gpx_time_offset}")
        if gpu_profile:
            cmd_parts.append(f"--profile {gpu_profile}")
        cmd_parts.append(f'"{video.path}"')
        cmd_parts.append(f'"{out_path}"')

        lines.append(f'echo "Processing {video.basename}..."')
        lines.append(" \\\n    ".join(cmd_parts))
        lines.append("")

    lines.append('echo "Done."')
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main GUI Application
# ---------------------------------------------------------------------------

class LayoutEditorApp(tk.Tk):

    CANVAS_MAX_W = 960
    CANVAS_MAX_H = 800

    def __init__(self):
        super().__init__()
        self.title("GoPro Dashboard — Layout Editor")
        self.geometry("1400x900")

        self.gpx_path: Optional[Path] = None
        self.gpx_location: Optional[tuple[float, float]] = None  # (lat, lon) from GPX
        self.videos: list[VideoEntry] = []
        self.components: list[OverlayComponent] = []
        self.active_video_idx: int = -1
        self.scale_factor: float = 1.0
        self.current_photo: Optional[ImageTk.PhotoImage] = None
        self.speed_unit = tk.StringVar(value="kph")
        self.map_style = tk.StringVar(value="osm")
        self.map_size = tk.IntVar(value=256)
        self.map_zoom = tk.IntVar(value=16)
        self.map_corner_radius = tk.IntVar(value=35)
        self.map_opacity = tk.DoubleVar(value=0.7)
        self.map_rotate = tk.BooleanVar(value=True)  # rotate map to heading (north pointer)
        # Journey map specific
        self.jm_track_colour = tk.StringVar(value="255,0,0")
        self.jm_line_width = tk.IntVar(value=4)
        self.jm_loc_colour = tk.StringVar(value="0,0,255")
        self.jm_loc_outline = tk.StringVar(value="0,0,0")
        self.jm_loc_size = tk.IntVar(value=6)
        self.date_format = tk.StringVar(value="%Y/%m/%d")
        self.time_format = tk.StringVar(value="%H:%M:%S.%f")
        self.gpx_time_offset = tk.DoubleVar(value=0.0)
        self.gpu_profile = detect_gpu()
        self.use_gpu = tk.BooleanVar(value=self.gpu_profile is not None)
        self.font_path = detect_font()
        self.workdir: Optional[str] = None  # initial directory for file dialogs
        self.snap_enabled = tk.BooleanVar(value=False)
        self.snap_size = tk.IntVar(value=20)
        self.frame_queue: queue.Queue = queue.Queue()

        # Drag state
        self._drag_component: Optional[OverlayComponent] = None
        self._drag_offset_x = 0
        self._drag_offset_y = 0

        # Scrub debounce
        self._scrub_after_id = None

        self._script_dir = Path(__file__).resolve().parent
        self._dashboard_script = self._script_dir / "gopro-dashboard.py"

        self._build_ui()

    def _build_ui(self):
        # Menu bar
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open GPX File...", command=self._open_gpx, accelerator="Ctrl+G")
        file_menu.add_command(label="Clear GPX File", command=self._clear_gpx)
        file_menu.add_separator()
        file_menu.add_command(label="Add Video Files...", command=self._add_videos, accelerator="Ctrl+O")
        file_menu.add_command(label="Remove Selected Video", command=self._remove_video, accelerator="Delete")
        file_menu.add_command(label="Clear All Videos", command=self._clear_videos)
        file_menu.add_separator()
        file_menu.add_command(label="Load Layout XML...", command=self._load_layout_xml)
        file_menu.add_command(label="Save Layout XML...", command=self._save_layout_xml)
        file_menu.add_command(label="Export Shell Script...", command=self._export_shell_script)
        file_menu.add_separator()
        file_menu.add_command(label="Select Font...", command=self._select_font)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.quit, accelerator="Ctrl+Q")
        menubar.add_cascade(label="File", menu=file_menu)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="API Keys...", command=self._show_api_keys_dialog)
        menubar.add_cascade(label="Settings", menu=settings_menu)

        self.config(menu=menubar)

        self.bind_all("<Control-g>", lambda e: self._open_gpx())
        self.bind_all("<Control-o>", lambda e: self._add_videos())
        self.bind_all("<Control-q>", lambda e: self.quit())
        self.bind_all("<Delete>", lambda e: self._remove_video())

        # Main layout: left panel | canvas + slider | right panel
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # -- Left panel: videos + components --
        left_frame = ttk.Frame(main_pane, width=220)
        main_pane.add(left_frame, weight=0)

        # GPX display
        gpx_frame = ttk.LabelFrame(left_frame, text="GPX File")
        gpx_frame.pack(fill=tk.X, padx=4, pady=2)
        self.gpx_label = ttk.Label(gpx_frame, text="(none)", wraplength=200)
        self.gpx_label.pack(padx=4, pady=2)
        gpx_btn_frame = ttk.Frame(gpx_frame)
        gpx_btn_frame.pack(padx=4, pady=2)
        ttk.Button(gpx_btn_frame, text="Browse...", command=self._open_gpx).pack(side=tk.LEFT, padx=2)
        ttk.Button(gpx_btn_frame, text="Clear", command=self._clear_gpx).pack(side=tk.LEFT, padx=2)

        # Video list
        vid_frame = ttk.LabelFrame(left_frame, text="Videos")
        vid_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        self.video_listbox = tk.Listbox(vid_frame, height=6, exportselection=False)
        self.video_listbox.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        self.video_listbox.bind("<<ListboxSelect>>", self._on_video_select)
        vid_btn_frame = ttk.Frame(vid_frame)
        vid_btn_frame.pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(vid_btn_frame, text="Add...", command=self._add_videos).pack(side=tk.LEFT, padx=2)
        ttk.Button(vid_btn_frame, text="Remove", command=self._remove_video).pack(side=tk.LEFT, padx=2)
        ttk.Button(vid_btn_frame, text="Clear All", command=self._clear_videos).pack(side=tk.LEFT, padx=2)

        # Video info
        self.video_info_label = ttk.Label(vid_frame, text="", wraplength=200, justify=tk.LEFT)
        self.video_info_label.pack(padx=4, pady=2)

        # Components
        comp_frame = ttk.LabelFrame(left_frame, text="Components")
        comp_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        self.comp_checks_frame = ttk.Frame(comp_frame)
        self.comp_checks_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        self.comp_vars: dict[str, tk.BooleanVar] = {}

        # -- Centre: canvas + slider --
        centre_frame = ttk.Frame(main_pane)
        main_pane.add(centre_frame, weight=1)

        self.canvas = tk.Canvas(centre_frame, bg="#1a1a1a", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        slider_frame = ttk.Frame(centre_frame)
        slider_frame.pack(fill=tk.X, padx=4, pady=2)
        self.scrub_slider = ttk.Scale(slider_frame, from_=0, to=100, orient=tk.HORIZONTAL,
                                       command=self._on_scrub)
        self.scrub_slider.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.time_label = ttk.Label(slider_frame, text="00:00:00", width=10)
        self.time_label.pack(side=tk.RIGHT, padx=4)

        # -- Right panel: settings --
        right_frame = ttk.Frame(main_pane, width=200)
        main_pane.add(right_frame, weight=0)

        settings_frame = ttk.LabelFrame(right_frame, text="Settings")
        settings_frame.pack(fill=tk.X, padx=4, pady=2)

        ttk.Label(settings_frame, text="Speed Unit:").pack(padx=4, pady=(4, 0), anchor=tk.W)
        speed_combo = ttk.Combobox(settings_frame, textvariable=self.speed_unit,
                                    values=["kph", "mph", "knots"], state="readonly", width=10)
        speed_combo.pack(padx=4, pady=2, anchor=tk.W)

        ttk.Label(settings_frame, text="GPX Time Offset (s):").pack(padx=4, pady=(4, 0), anchor=tk.W)
        offset_frame = ttk.Frame(settings_frame)
        offset_frame.pack(fill=tk.X, padx=4, pady=2)
        self.gpx_offset_entry = ttk.Entry(offset_frame, width=7)
        self.gpx_offset_entry.insert(0, "0.0")
        self.gpx_offset_entry.pack(side=tk.RIGHT, padx=(4, 0))
        self.gpx_offset_entry.bind("<Return>", self._on_gpx_offset_entry)
        self.gpx_offset_entry.bind("<FocusOut>", self._on_gpx_offset_entry)
        gpx_offset_scale = ttk.Scale(offset_frame, from_=-120, to=120, orient=tk.HORIZONTAL,
                                      variable=self.gpx_time_offset,
                                      command=self._on_gpx_offset_change)
        gpx_offset_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        gpu_text = f"GPU: {self.gpu_profile or 'not detected'}"
        ttk.Label(settings_frame, text=gpu_text).pack(padx=4, pady=(4, 0), anchor=tk.W)
        ttk.Checkbutton(settings_frame, text="Use GPU encoding",
                         variable=self.use_gpu,
                         state=tk.NORMAL if self.gpu_profile else tk.DISABLED).pack(padx=4, pady=2, anchor=tk.W)

        font_row = ttk.Frame(settings_frame)
        font_row.pack(fill=tk.X, padx=4, pady=(4, 0))
        ttk.Label(font_row, text="Font:").pack(side=tk.LEFT)
        self.font_label = ttk.Label(font_row, text=Path(self.font_path).name, foreground="#4488ff")
        self.font_label.pack(side=tk.LEFT, padx=4)
        ttk.Button(font_row, text="...", width=3, command=self._select_font).pack(side=tk.LEFT)

        # Snap grid
        snap_frame = ttk.LabelFrame(right_frame, text="Snap Grid")
        snap_frame.pack(fill=tk.X, padx=4, pady=4)

        ttk.Checkbutton(snap_frame, text="Enable snap to grid",
                         variable=self.snap_enabled,
                         command=self._on_snap_toggle).pack(padx=4, pady=2, anchor=tk.W)

        grid_row = ttk.Frame(snap_frame)
        grid_row.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(grid_row, text="Grid size:").pack(side=tk.LEFT)
        self.snap_size_label = ttk.Label(grid_row, text="20", width=4)
        self.snap_size_label.pack(side=tk.RIGHT)
        self.snap_size_scale = ttk.Scale(grid_row, from_=5, to=100, orient=tk.HORIZONTAL,
                                          variable=self.snap_size,
                                          command=self._on_snap_size_change)
        self.snap_size_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        # Map settings
        map_frame = ttk.LabelFrame(right_frame, text="Map Settings")
        map_frame.pack(fill=tk.X, padx=4, pady=4)

        ttk.Label(map_frame, text="Map Style:").pack(padx=4, pady=(4, 0), anchor=tk.W)
        map_style_combo = ttk.Combobox(map_frame, textvariable=self.map_style,
                                        values=MAP_STYLES, state="readonly", width=24)
        map_style_combo.pack(padx=4, pady=2, anchor=tk.W)

        ttk.Label(map_frame, text="Map Size (px):").pack(padx=4, pady=(4, 0), anchor=tk.W)
        size_frame = ttk.Frame(map_frame)
        size_frame.pack(fill=tk.X, padx=4, pady=2)
        self.map_size_label = ttk.Label(size_frame, text="256", width=4)
        self.map_size_label.pack(side=tk.RIGHT)
        map_size_scale = ttk.Scale(size_frame, from_=128, to=512, orient=tk.HORIZONTAL,
                                    variable=self.map_size,
                                    command=self._on_map_size_change)
        map_size_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Label(map_frame, text="Map Zoom:").pack(padx=4, pady=(4, 0), anchor=tk.W)
        zoom_frame = ttk.Frame(map_frame)
        zoom_frame.pack(fill=tk.X, padx=4, pady=2)
        self.map_zoom_label = ttk.Label(zoom_frame, text="16", width=4)
        self.map_zoom_label.pack(side=tk.RIGHT)
        map_zoom_scale = ttk.Scale(zoom_frame, from_=10, to=20, orient=tk.HORIZONTAL,
                                    variable=self.map_zoom,
                                    command=self._on_map_zoom_change)
        map_zoom_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Action buttons
        action_frame = ttk.LabelFrame(right_frame, text="Actions")
        action_frame.pack(fill=tk.X, padx=4, pady=8)
        ttk.Button(action_frame, text="Save Layout XML...", command=self._save_layout_xml).pack(
            fill=tk.X, padx=8, pady=4)
        ttk.Button(action_frame, text="Export Shell Script...", command=self._export_shell_script).pack(
            fill=tk.X, padx=8, pady=4)
        ttk.Button(action_frame, text="Run Encoding...", command=self._run_encoding).pack(
            fill=tk.X, padx=8, pady=4)

        # Status bar
        self.status_var = tk.StringVar(value="Ready. Open a GPX file and add videos to begin.")
        status_bar = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=2, pady=2)

    # -- File operations --

    def _open_gpx(self):
        path = filedialog.askopenfilename(
            title="Select GPX File",
            initialdir=self.workdir,
            filetypes=[("GPX files", "*.gpx"), ("FIT files", "*.fit"), ("All files", "*.*")])
        if path:
            self.gpx_path = Path(path)
            self.gpx_label.config(text=self.gpx_path.name)
            loc = _extract_gpx_first_point(self.gpx_path)
            if loc:
                self.gpx_location = loc
                self.status_var.set(f"GPX: {self.gpx_path.name} (lat={loc[0]:.4f}, lon={loc[1]:.4f})")
            else:
                self.status_var.set(f"GPX: {self.gpx_path.name}")

    def _clear_gpx(self):
        self.gpx_path = None
        self.gpx_location = None
        self.gpx_label.config(text="(none)")
        self.status_var.set("GPX file cleared.")

    def _remove_video(self):
        sel = self.video_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        removed = self.videos.pop(idx)
        self.video_listbox.delete(idx)

        # Reset canvas if the active video was removed
        if idx == self.active_video_idx:
            self.active_video_idx = -1
            self.canvas.delete("all")
            self.current_photo = None
            self.components = []
            self._rebuild_component_checkboxes()
            self.video_info_label.config(text="")
            # Select next available video
            if self.videos:
                new_idx = min(idx, len(self.videos) - 1)
                self.video_listbox.selection_set(new_idx)
                self._select_video(new_idx)
        elif idx < self.active_video_idx:
            self.active_video_idx -= 1

        self.status_var.set(f"Removed {removed.basename}. {len(self.videos)} video(s) remaining.")

    def _clear_videos(self):
        if not self.videos:
            return
        if not messagebox.askyesno("Clear Videos", f"Remove all {len(self.videos)} video(s)?"):
            return
        self.videos.clear()
        self.video_listbox.delete(0, tk.END)
        self.active_video_idx = -1
        self.canvas.delete("all")
        self.current_photo = None
        self.components = []
        self._rebuild_component_checkboxes()
        self.video_info_label.config(text="")
        self.status_var.set("All videos cleared.")

    def _select_font(self):
        FontSelectorDialog(self)

    def _on_gpx_offset_change(self, value):
        v = round(float(value), 1)
        self.gpx_time_offset.set(v)
        self.gpx_offset_entry.delete(0, tk.END)
        self.gpx_offset_entry.insert(0, str(v))

    def _on_gpx_offset_entry(self, event=None):
        try:
            v = float(self.gpx_offset_entry.get())
            self.gpx_time_offset.set(v)
        except ValueError:
            self.gpx_offset_entry.delete(0, tk.END)
            self.gpx_offset_entry.insert(0, str(self.gpx_time_offset.get()))

    def _on_map_size_change(self, value):
        size = int(float(value))
        self.map_size.set(size)
        self.map_size_label.config(text=str(size))
        # Update map component bounding boxes on canvas
        for comp in self.components:
            if comp.name in ("moving_map", "journey_map"):
                comp.width = size
                comp.height = size
        self._redraw_components()

    def _on_map_zoom_change(self, value):
        zoom = int(float(value))
        self.map_zoom.set(zoom)
        self.map_zoom_label.config(text=str(zoom))

    def _get_map_props(self) -> dict:
        """Build the template variables dict for XML generation."""
        return {
            "map_size": self.map_size.get(),
            "map_zoom": self.map_zoom.get(),
            "map_corner_radius": self.map_corner_radius.get(),
            "map_opacity": self.map_opacity.get(),
            "map_rotate": str(self.map_rotate.get()).lower(),
            "jm_track_colour": self.jm_track_colour.get(),
            "jm_line_width": self.jm_line_width.get(),
            "jm_loc_colour": self.jm_loc_colour.get(),
            "jm_loc_outline": self.jm_loc_outline.get(),
            "jm_loc_size": self.jm_loc_size.get(),
            "date_format": self.date_format.get(),
            "time_format": self.time_format.get(),
            # Text defaults (overridable per-component via custom_props)
            "text_size": 16,
            "value_font_size": 32,
            "speed_font_size": 160,
            "text_rgb": "255,255,255",
            # Chart defaults
            "chart_height": 64,
            "chart_filled": "true",
            "chart_seconds": 300,
            "chart_corner_radius": 0,
            "chart_outline": "0,0,0,0",
            "chart_bg": "0,0,0,170",
            "chart_fill": "91,113,146,170",
            "chart_line": "255,255,255,170",
        }

    def _on_snap_toggle(self):
        self._draw_snap_grid()
        self._redraw_components()

    def _on_snap_size_change(self, value):
        size = int(float(value))
        self.snap_size.set(size)
        self.snap_size_label.config(text=str(size))
        if self.snap_enabled.get():
            self._draw_snap_grid()

    def _snap_value(self, val: int) -> int:
        """Snap a value to the nearest grid point."""
        grid = self.snap_size.get()
        return round(val / grid) * grid

    def _draw_snap_grid(self):
        """Draw or clear the snap grid overlay on the canvas."""
        self.canvas.delete("snap_grid")
        if not self.snap_enabled.get() or self.active_video_idx < 0:
            return

        video = self.videos[self.active_video_idx]
        s = self.scale_factor
        grid = self.snap_size.get()
        w = int(video.eff_width * s)
        h = int(video.eff_height * s)

        # Vertical lines
        x = 0
        while x <= video.eff_width:
            cx = int(x * s)
            self.canvas.create_line(cx, 0, cx, h,
                                     fill="#444444", dash=(2, 4),
                                     tags="snap_grid")
            x += grid

        # Horizontal lines
        y = 0
        while y <= video.eff_height:
            cy = int(y * s)
            self.canvas.create_line(0, cy, w, cy,
                                     fill="#444444", dash=(2, 4),
                                     tags="snap_grid")
            y += grid

        # Ensure grid is above background but below components
        self.canvas.tag_raise("snap_grid", "bg_image")
        self.canvas.tag_raise("overlay_comp", "snap_grid")

    def _show_api_keys_dialog(self):
        ApiKeysDialog(self)

    def _add_videos(self):
        paths = filedialog.askopenfilenames(
            title="Select Video Files",
            initialdir=self.workdir,
            filetypes=[("Video files", "*.mp4 *.MP4 *.mov *.MOV *.avi"), ("All files", "*.*")])
        if not paths:
            return
        for p in paths:
            self.status_var.set(f"Analysing {Path(p).name}...")
            self.update_idletasks()
            try:
                entry = analyse_video(Path(p))
                self.videos.append(entry)
                self.video_listbox.insert(tk.END, entry.basename)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to analyse {Path(p).name}:\n{e}")

        if self.videos and self.active_video_idx < 0:
            self.video_listbox.selection_set(0)
            self._select_video(0)

        self.status_var.set(f"{len(self.videos)} video(s) loaded.")

    def _on_video_select(self, event):
        sel = self.video_listbox.curselection()
        if sel:
            self._select_video(sel[0])

    def _select_video(self, idx: int):
        self.active_video_idx = idx
        video = self.videos[idx]

        # Update GPX location to match video start time
        if self.gpx_path and video.creation_time:
            loc = _find_gpx_point_at_time(self.gpx_path, video.creation_time)
            if loc:
                self.gpx_location = loc

        # Update info label
        orient = "Portrait" if video.eff_height > video.eff_width else "Landscape"
        dur = _format_time(video.duration_seconds)
        self.video_info_label.config(
            text=f"{video.eff_width}x{video.eff_height} ({orient})\n"
                 f"Rotation: {video.rotation}\u00b0\nDuration: {dur}")

        # Update slider range
        self.scrub_slider.config(to=max(1, int(video.duration_seconds)))

        # Reset components for this resolution
        self.components = default_component_positions(video.eff_width, video.eff_height)
        self._rebuild_component_checkboxes()

        # Calculate scale
        self._update_scale()
        self._draw_snap_grid()

        # Extract and show first frame
        self._extract_and_show(0.0)

    def _update_scale(self):
        if self.active_video_idx < 0:
            return
        video = self.videos[self.active_video_idx]
        cw = self.canvas.winfo_width() or self.CANVAS_MAX_W
        ch = self.canvas.winfo_height() or self.CANVAS_MAX_H
        self.scale_factor = min(cw / video.eff_width, ch / video.eff_height)

    def _on_canvas_resize(self, event):
        self._update_scale()
        self._redraw_components()
        self._draw_snap_grid()
        # Re-show current frame if we have one
        if self.current_photo:
            self._show_current_frame()

    # -- Frame extraction --

    def _extract_and_show(self, time_seconds: float):
        if self.active_video_idx < 0:
            return
        video = self.videos[self.active_video_idx]
        self.status_var.set(f"Extracting frame at {_format_time(time_seconds)}...")
        self.update_idletasks()

        # Run extraction in background thread
        def _extract():
            img = extract_frame(video.path, time_seconds, video.eff_width, video.eff_height)
            self.frame_queue.put(img)

        threading.Thread(target=_extract, daemon=True).start()
        self._poll_frame_queue()

    def _poll_frame_queue(self):
        try:
            img = self.frame_queue.get_nowait()
            if img:
                self._display_frame(img)
            else:
                self.status_var.set("Failed to extract frame.")
        except queue.Empty:
            self.after(50, self._poll_frame_queue)

    def _display_frame(self, img: Image.Image):
        self._update_scale()
        scaled_w = int(img.width * self.scale_factor)
        scaled_h = int(img.height * self.scale_factor)
        scaled = img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
        self.current_photo = ImageTk.PhotoImage(scaled)
        self._show_current_frame()
        self._redraw_components()
        self.status_var.set("Ready.")

    def _show_current_frame(self):
        self.canvas.delete("bg_image")
        if self.current_photo:
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.current_photo, tags="bg_image")
            self.canvas.tag_lower("bg_image")

    # -- Scrub slider --

    def _on_scrub(self, value):
        t = float(value)
        self.time_label.config(text=_format_time(t))
        # Debounce frame extraction
        if self._scrub_after_id:
            self.after_cancel(self._scrub_after_id)
        self._scrub_after_id = self.after(300, lambda: self._extract_and_show(t))

    # -- Component checkboxes --

    def _rebuild_component_checkboxes(self):
        for widget in self.comp_checks_frame.winfo_children():
            widget.destroy()
        self.comp_vars.clear()

        for comp in self.components:
            var = tk.BooleanVar(value=comp.enabled)
            self.comp_vars[comp.name] = var
            cb = ttk.Checkbutton(
                self.comp_checks_frame, text=comp.label, variable=var,
                command=lambda c=comp, v=var: self._toggle_component(c, v))
            cb.pack(anchor=tk.W, padx=2, pady=1)

    def _toggle_component(self, comp: OverlayComponent, var: tk.BooleanVar):
        comp.enabled = var.get()
        self._redraw_components()

    # -- Component drawing and dragging --

    def _redraw_components(self):
        self.canvas.delete("overlay_comp")
        for comp in self.components:
            comp.canvas_rect_id = None
            comp.canvas_text_id = None
            if not comp.enabled:
                continue
            self._draw_component(comp)

    def _draw_component(self, comp: OverlayComponent):
        s = self.scale_factor
        cx = int(comp.x * s)
        cy = int(comp.y * s)
        cw = int(comp.width * s)
        ch = int(comp.height * s)

        rect_id = self.canvas.create_rectangle(
            cx, cy, cx + cw, cy + ch,
            outline=comp.color, fill=comp.color, stipple="gray25",
            width=2, tags="overlay_comp")

        text_id = self.canvas.create_text(
            cx + cw // 2, cy + ch // 2,
            text=comp.label, fill="white", font=("sans-serif", 9, "bold"),
            tags="overlay_comp")

        comp.canvas_rect_id = rect_id
        comp.canvas_text_id = text_id

        # Bind drag events and right-click
        for item_id in (rect_id, text_id):
            self.canvas.tag_bind(item_id, "<ButtonPress-1>",
                                  lambda e, c=comp: self._drag_start(e, c))
            self.canvas.tag_bind(item_id, "<B1-Motion>",
                                  lambda e, c=comp: self._drag_motion(e, c))
            self.canvas.tag_bind(item_id, "<ButtonRelease-1>",
                                  lambda e, c=comp: self._drag_end(e, c))
            self.canvas.tag_bind(item_id, "<ButtonPress-3>",
                                  lambda e, c=comp: self._component_context_menu(e, c))

    def _drag_start(self, event, comp: OverlayComponent):
        self._drag_component = comp
        s = self.scale_factor
        self._drag_offset_x = event.x - int(comp.x * s)
        self._drag_offset_y = event.y - int(comp.y * s)

    def _drag_motion(self, event, comp: OverlayComponent):
        if self._drag_component is not comp:
            return
        s = self.scale_factor
        new_x = (event.x - self._drag_offset_x) / s
        new_y = (event.y - self._drag_offset_y) / s

        # Clamp to video bounds
        if self.active_video_idx >= 0:
            video = self.videos[self.active_video_idx]
            new_x = max(0, min(new_x, video.eff_width - comp.width))
            new_y = max(0, min(new_y, video.eff_height - comp.height))

        comp.x = int(new_x)
        comp.y = int(new_y)

        # Snap to grid if enabled
        if self.snap_enabled.get():
            comp.x = self._snap_value(comp.x)
            comp.y = self._snap_value(comp.y)

        # Move canvas items
        cx = int(comp.x * s)
        cy = int(comp.y * s)
        cw = int(comp.width * s)
        ch = int(comp.height * s)
        self.canvas.coords(comp.canvas_rect_id, cx, cy, cx + cw, cy + ch)
        self.canvas.coords(comp.canvas_text_id, cx + cw // 2, cy + ch // 2)

    def _drag_end(self, event, comp: OverlayComponent):
        self._drag_component = None
        if self.active_video_idx >= 0:
            video = self.videos[self.active_video_idx]
            self.status_var.set(
                f"{comp.label}: ({comp.x}, {comp.y}) on {video.eff_width}x{video.eff_height}")

    def _component_context_menu(self, event, comp: OverlayComponent):
        """Show right-click context menu for a component."""
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label=f"Properties: {comp.label}...",
                         command=lambda: ComponentOptionsDialog(self, comp))
        menu.add_separator()
        menu.add_command(label="Disable", command=lambda: self._disable_component(comp))
        menu.add_separator()

        # Quick position presets
        if self.active_video_idx >= 0:
            video = self.videos[self.active_video_idx]
            menu.add_command(label="Move to Top-Left",
                             command=lambda: self._move_component(comp, 16, 16))
            menu.add_command(label="Move to Top-Right",
                             command=lambda: self._move_component(comp, video.eff_width - comp.width - 16, 16))
            menu.add_command(label="Move to Bottom-Left",
                             command=lambda: self._move_component(comp, 16, video.eff_height - comp.height - 16))
            menu.add_command(label="Move to Bottom-Right",
                             command=lambda: self._move_component(
                                 comp, video.eff_width - comp.width - 16, video.eff_height - comp.height - 16))
            menu.add_command(label="Centre",
                             command=lambda: self._move_component(
                                 comp, (video.eff_width - comp.width) // 2, (video.eff_height - comp.height) // 2))

        menu.tk_popup(event.x_root, event.y_root)

    def _disable_component(self, comp: OverlayComponent):
        comp.enabled = False
        if comp.name in self.comp_vars:
            self.comp_vars[comp.name].set(False)
        self._redraw_components()

    def _move_component(self, comp: OverlayComponent, x: int, y: int):
        if self.snap_enabled.get():
            x = self._snap_value(x)
            y = self._snap_value(y)
        comp.x = x
        comp.y = y
        self._redraw_components()

    # -- Save / Export --

    def _load_layout_xml(self, path: Optional[str] = None):
        if not self.components:
            messagebox.showinfo("Info", "Add a video first to initialise components.")
            return
        if not path:
            path = filedialog.askopenfilename(
                title="Load Layout XML",
                initialdir=self.workdir,
                filetypes=[("XML files", "*.xml"), ("All files", "*.*")])
        if not path:
            return
        try:
            load_layout_xml(Path(path), self.components)
            # Sync global settings from loaded component state
            for comp in self.components:
                if comp.name == "moving_map" and comp.enabled:
                    self.map_size.set(comp.width)
                    self.map_size_label.config(text=str(comp.width))
            self._rebuild_component_checkboxes()
            self._redraw_components()
            self.status_var.set(f"Layout loaded: {Path(path).name}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load layout:\n{e}")

    def _save_layout_xml(self):
        if not self.components:
            messagebox.showinfo("Info", "No layout to save. Add a video first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save Layout XML",
            defaultextension=".xml",
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")])
        if path:
            xml = generate_layout_xml(self.components, self._get_map_props())
            Path(path).write_text(xml)
            self.status_var.set(f"Layout saved: {Path(path).name}")

    def _export_shell_script(self):
        if not self._validate_for_encoding():
            return
        path = filedialog.asksaveasfilename(
            title="Export Shell Script",
            defaultextension=".sh",
            filetypes=[("Shell scripts", "*.sh"), ("All files", "*.*")])
        if not path:
            return

        # Save layout XML alongside the script
        xml_path = Path(path).with_suffix(".xml")
        xml = generate_layout_xml(self.components, self._get_map_props())
        xml_path.write_text(xml)

        gpu = self.gpu_profile if self.use_gpu.get() else None
        script = generate_shell_script(
            videos=self.videos,
            gpx_path=self.gpx_path,
            layout_xml_path=xml_path,
            speed_unit=self.speed_unit.get(),
            font=self.font_path,
            gpu_profile=gpu,
            dashboard_script=self._dashboard_script,
            map_style=self.map_style.get(),
            gpx_time_offset=self.gpx_time_offset.get(),
        )
        Path(path).write_text(script)
        os.chmod(path, 0o755)
        self.status_var.set(f"Script exported: {Path(path).name}")

    def _validate_for_encoding(self) -> bool:
        if not self.gpx_path:
            messagebox.showwarning("Missing GPX", "Please open a GPX file first.")
            return False
        if not self.videos:
            messagebox.showwarning("No Videos", "Please add at least one video.")
            return False
        if not self.components:
            messagebox.showwarning("No Layout", "No layout components configured.")
            return False
        return True

    # -- In-app encoding --

    def _run_encoding(self):
        if not self._validate_for_encoding():
            return

        # Save layout XML to temp location
        import tempfile
        xml_dir = tempfile.mkdtemp(prefix="gopro-layout-")
        xml_path = Path(xml_dir) / "layout.xml"
        xml_path.write_text(generate_layout_xml(self.components, self._get_map_props()))

        EncodingDialog(self, self.videos, self.gpx_path, xml_path,
                       self.speed_unit.get(), self.font_path,
                       self.gpu_profile if self.use_gpu.get() else None,
                       self._dashboard_script,
                       self.map_style.get(),
                       self.gpx_time_offset.get())


# ---------------------------------------------------------------------------
# Component options dialog (right-click properties)
# ---------------------------------------------------------------------------

# Per-component configurable options
COMPONENT_OPTIONS = {
    "date_and_time": {
        "title": "Date + Time Display Options",
        "fields": [
            ("date_format", "Date Format", "combo_editable", "%Y/%m/%d", DATE_FORMATS),
            ("time_format", "Time Format", "combo_editable", "%H:%M:%S.%f", TIME_FORMATS),
        ],
        "has_datetime_preview": True,
    },
    "date_only": {
        "title": "Date Display Options",
        "fields": [
            ("date_format", "Date Format", "combo_editable", "%Y/%m/%d", DATE_FORMATS),
        ],
        "has_datetime_preview": True,
    },
    "time_only": {
        "title": "Time Display Options",
        "fields": [
            ("time_format", "Time Format", "combo_editable", "%H:%M:%S.%f", TIME_FORMATS),
        ],
        "has_datetime_preview": True,
    },
    "gps_info": {
        "title": "GPS Info Options",
        "fields": [
            ("text_size", "Font Size", "spinbox", 16, (8, 48, 2)),
        ],
    },
    "gps_coords": {
        "title": "GPS Coordinates Options",
        "fields": [
            ("text_size", "Font Size", "spinbox", 16, (8, 48, 2)),
        ],
    },
    "big_mph": {
        "title": "Speed Display Options",
        "fields": [
            ("speed_unit", "Speed Unit", "combo", "kph", ["kph", "mph", "knots"]),
            ("speed_font_size", "Speed Font Size", "spinbox", 160, (32, 256, 8)),
            ("text_size", "Label Font Size", "spinbox", 16, (8, 48, 2)),
            ("comp_font", "Font", "font_select", "", []),
        ],
    },
    "gradient": {
        "title": "Gradient Options",
        "fields": [
            ("value_font_size", "Value Font Size", "spinbox", 32, (12, 96, 4)),
            ("text_size", "Label Font Size", "spinbox", 16, (8, 48, 2)),
        ],
    },
    "altitude": {
        "title": "Altitude Options",
        "fields": [
            ("value_font_size", "Value Font Size", "spinbox", 32, (12, 96, 4)),
            ("text_size", "Label Font Size", "spinbox", 16, (8, 48, 2)),
        ],
    },
    "temperature": {
        "title": "Temperature Options",
        "fields": [
            ("value_font_size", "Value Font Size", "spinbox", 32, (12, 96, 4)),
            ("text_size", "Label Font Size", "spinbox", 16, (8, 48, 2)),
        ],
    },
    "cadence": {
        "title": "Cadence Options",
        "fields": [
            ("value_font_size", "Value Font Size", "spinbox", 32, (12, 96, 4)),
            ("text_size", "Label Font Size", "spinbox", 16, (8, 48, 2)),
        ],
    },
    "heartbeat": {
        "title": "Heart Rate Options",
        "fields": [
            ("value_font_size", "Value Font Size", "spinbox", 32, (12, 96, 4)),
            ("text_size", "Label Font Size", "spinbox", 16, (8, 48, 2)),
        ],
    },
    "moving_map": {
        "title": "Moving Map Options",
        "fields": [
            ("map_zoom", "Zoom Level", "slider", 16, (8, 20)),
            ("map_corner_radius", "Rounded Corners (0=off)", "spinbox", 35, (0, 128, 5)),
            ("map_opacity", "Opacity", "slider_float", 0.7, (0.0, 1.0)),
            ("map_rotate", "Rotate Map to Heading", "checkbox", True, []),
            ("map_style", "Map Style", "combo_preview", "osm", MAP_STYLES),
        ],
    },
    "journey_map": {
        "title": "Journey Map Options",
        "fields": [
            ("map_corner_radius", "Rounded Corners (0=off)", "spinbox", 35, (0, 128, 5)),
            ("map_opacity", "Opacity", "slider_float", 0.7, (0.0, 1.0)),
            ("jm_track_colour", "Track Colour", "colour_select", "255,0,0", []),
            ("jm_line_width", "Track Width", "slider", 4, (1, 12)),
            ("jm_loc_colour", "Location Fill", "colour_select", "0,0,255", []),
            ("jm_loc_outline", "Location Outline", "colour_select", "0,0,0", []),
            ("jm_loc_size", "Location Marker Size", "slider", 6, (2, 20)),
            ("map_style", "Map Style", "combo_preview", "osm", MAP_STYLES),
        ],
    },
    "altitude": {
        "title": "Altitude Options",
        "fields": [
            ("units", "Units", "combo", "metres", ["metres", "feet"]),
        ],
    },
    "gradient_chart": {
        "title": "Altitude Chart Options",
        "fields": [
            ("chart_corner_radius", "Corner Radius", "spinbox", 0, (0, 64, 5)),
            ("chart_outline", "Border (R,G,B,A)", "colour_select", "0,0,0,0", []),
            ("chart_seconds", "Time Window (sec)", "spinbox", 300, (60, 1800, 30)),
            ("chart_filled", "Filled", "checkbox", True, []),
            ("chart_bg", "Background (R,G,B,A)", "colour_select", "0,0,0,170", []),
            ("chart_fill", "Fill Colour (R,G,B,A)", "colour_select", "91,113,146,170", []),
            ("chart_line", "Line Colour (R,G,B,A)", "colour_select", "255,255,255,170", []),
        ],
    },
}

# Default options for any component
DEFAULT_COMPONENT_OPTIONS = {
    "title": "Component Options",
    "fields": [],
}


class ComponentOptionsDialog(tk.Toplevel):
    """Modal dialog for editing properties of a specific overlay component."""

    def __init__(self, parent: LayoutEditorApp, comp: OverlayComponent):
        super().__init__(parent)
        self.parent_app = parent
        self.comp = comp
        self.result_vars: dict[str, tk.Variable] = {}
        self._tile_photo: Optional[ImageTk.PhotoImage] = None  # prevent GC
        self._tile_raw_img: Optional[Image.Image] = None  # raw fetched tile for re-rendering

        opts = COMPONENT_OPTIONS.get(comp.name, DEFAULT_COMPONENT_OPTIONS)
        self.title(opts["title"])
        # Size dialog based on content
        field_count = len(opts.get("fields", []))
        has_map = any(wt == "combo_preview" for _, _, wt, _, _ in opts.get("fields", []))
        if has_map:
            height = 750 + max(0, (field_count - 4)) * 40
        else:
            height = 300 + field_count * 45
        self.geometry(f"520x{min(height, 950)}")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._build_ui(opts)

    def _build_ui(self, opts: dict):
        # Scrollable content area
        outer = ttk.Frame(self)
        outer.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        self._scroll_frame = ttk.Frame(canvas)

        self._scroll_frame.bind("<Configure>",
                                 lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._scroll_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Enable mousewheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(-1 * (event.delta // 120 or (1 if event.num == 4 else -1)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", _on_mousewheel)
        canvas.bind_all("<Button-5>", _on_mousewheel)
        self.bind("<Destroy>", lambda e: (canvas.unbind_all("<MouseWheel>"),
                                           canvas.unbind_all("<Button-4>"),
                                           canvas.unbind_all("<Button-5>")))

        container = self._scroll_frame

        # Component name header
        ttk.Label(container, text=self.comp.label,
                  font=("sans-serif", 13, "bold")).pack(padx=12, pady=(12, 4), anchor=tk.W)

        # Position fields (always present)
        pos_frame = ttk.LabelFrame(container, text="Position & Size")
        pos_frame.pack(fill=tk.X, padx=12, pady=4)

        row = ttk.Frame(pos_frame)
        row.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(row, text="X:").pack(side=tk.LEFT)
        self.x_var = tk.IntVar(value=self.comp.x)
        ttk.Spinbox(row, from_=0, to=9999, textvariable=self.x_var, width=6).pack(side=tk.LEFT, padx=4)
        ttk.Label(row, text="Y:").pack(side=tk.LEFT, padx=(8, 0))
        self.y_var = tk.IntVar(value=self.comp.y)
        ttk.Spinbox(row, from_=0, to=9999, textvariable=self.y_var, width=6).pack(side=tk.LEFT, padx=4)
        ttk.Label(row, text="W:").pack(side=tk.LEFT, padx=(8, 0))
        self.w_var = tk.IntVar(value=self.comp.width)
        ttk.Spinbox(row, from_=16, to=2048, textvariable=self.w_var, width=6).pack(side=tk.LEFT, padx=4)
        ttk.Label(row, text="H:").pack(side=tk.LEFT, padx=(8, 0))
        self.h_var = tk.IntVar(value=self.comp.height)
        ttk.Spinbox(row, from_=16, to=2048, textvariable=self.h_var, width=6).pack(side=tk.LEFT, padx=4)

        # Component-specific fields
        fields = opts.get("fields", [])
        if fields:
            specific_frame = ttk.LabelFrame(container, text="Options")
            specific_frame.pack(fill=tk.X, padx=12, pady=4)

            for field_id, label, widget_type, default, params in fields:
                field_row = ttk.Frame(specific_frame)
                field_row.pack(fill=tk.X, padx=8, pady=3)
                ttk.Label(field_row, text=f"{label}:").pack(side=tk.LEFT)

                current = self._get_current_value(field_id, default)

                if widget_type == "spinbox":
                    from_, to_, inc = params
                    var = tk.IntVar(value=current)
                    ttk.Spinbox(field_row, from_=from_, to=to_, increment=inc,
                                textvariable=var, width=8).pack(side=tk.LEFT, padx=4)
                    # Live-update tile preview when relevant fields change
                    if field_id in ("map_corner_radius", "jm_line_width", "jm_loc_size"):
                        var.trace_add("write", lambda *_: self._render_tile_preview())

                elif widget_type == "slider":
                    from_, to_ = params
                    var = tk.IntVar(value=int(current))
                    val_label = ttk.Label(field_row, text=str(int(current)), width=4)
                    val_label.pack(side=tk.RIGHT)
                    def _make_slider_cmd(vl):
                        def _cmd(v):
                            vl.config(text=str(int(float(v))))
                            if self._tile_raw_img:
                                self._render_tile_preview()
                        return _cmd
                    scale = ttk.Scale(field_row, from_=from_, to=to_, orient=tk.HORIZONTAL,
                                      variable=var, command=_make_slider_cmd(val_label))
                    scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

                elif widget_type == "slider_float":
                    from_, to_ = params
                    var = tk.DoubleVar(value=float(current))
                    val_label = ttk.Label(field_row, text=f"{float(current):.1f}", width=4)
                    val_label.pack(side=tk.RIGHT)
                    scale = ttk.Scale(field_row, from_=from_, to=to_, orient=tk.HORIZONTAL,
                                      variable=var,
                                      command=lambda v, vl=val_label: vl.config(text=f"{float(v):.1f}"))
                    scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

                elif widget_type == "checkbox":
                    current_bool = str(current).lower() in ("true", "1", "yes")
                    var = tk.StringVar(value="true" if current_bool else "false")
                    cb = ttk.Checkbutton(field_row, text="",
                                          command=lambda v=var: v.set("true" if v.get() == "false" else "false"))
                    if current_bool:
                        cb.state(["selected"])
                    else:
                        cb.state(["!selected"])
                    # Sync checkbox state with var
                    def _make_cb_cmd(v, c):
                        def _toggle():
                            if "selected" in c.state():
                                v.set("true")
                            else:
                                v.set("false")
                        return _toggle
                    cb.config(command=_make_cb_cmd(var, cb))
                    cb.pack(side=tk.LEFT, padx=4)

                elif widget_type == "combo":
                    var = tk.StringVar(value=current)
                    combo = ttk.Combobox(field_row, textvariable=var, values=params,
                                          state="readonly", width=24)
                    combo.pack(side=tk.LEFT, padx=4)

                elif widget_type == "combo_editable":
                    # Editable combobox — select from presets or type custom format
                    var = tk.StringVar(value=current)
                    combo = ttk.Combobox(field_row, textvariable=var, values=params, width=24)
                    combo.pack(side=tk.LEFT, padx=4)
                    # Inline preview of the format
                    preview = ttk.Label(field_row, text="", foreground="#888888")
                    preview.pack(side=tk.LEFT, padx=4)
                    combo.bind("<<ComboboxSelected>>",
                               lambda e, v=var, p=preview: self._update_format_preview(v, p))
                    combo.bind("<KeyRelease>",
                               lambda e, v=var, p=preview: self._update_format_preview(v, p))
                    self._update_format_preview(var, preview)

                elif widget_type == "combo_preview":
                    # Combo with tile image preview (for map styles)
                    var = tk.StringVar(value=current)
                    combo = ttk.Combobox(field_row, textvariable=var, values=params,
                                          state="readonly", width=24)
                    combo.pack(side=tk.LEFT, padx=4)

                    desc_label = ttk.Label(specific_frame, text="", wraplength=440,
                                           foreground="#888888")
                    desc_label.pack(padx=8, pady=2, anchor=tk.W)

                    self._tile_canvas = tk.Canvas(specific_frame, width=256, height=256,
                                                   bg="#2a2a2a", highlightthickness=1,
                                                   highlightbackground="#555555")
                    self._tile_canvas.pack(padx=8, pady=4)

                    # API key help area below the preview
                    self._api_help_frame = ttk.Frame(specific_frame)
                    self._api_help_frame.pack(fill=tk.X, padx=8, pady=(0, 4))

                    combo.bind("<<ComboboxSelected>>",
                               lambda e, v=var, dl=desc_label: self._on_map_style_change(v, dl))
                    self._on_map_style_change(var, desc_label)
                elif widget_type == "colour_select":
                    # Colour picker with swatch preview
                    var = tk.StringVar(value=current)
                    # Convert R,G,B[,A] string to hex for the swatch
                    try:
                        parts = [int(c.strip()) for c in str(current).split(",")]
                        hex_col = f"#{parts[0]:02x}{parts[1]:02x}{parts[2]:02x}"
                    except Exception:
                        hex_col = "#ffffff"
                    swatch = tk.Label(field_row, text="  ", bg=hex_col, width=3,
                                      relief=tk.RAISED, borderwidth=2)
                    swatch.pack(side=tk.LEFT, padx=4)
                    val_label = ttk.Label(field_row, text=str(current), width=12)
                    val_label.pack(side=tk.LEFT, padx=2)
                    ttk.Button(field_row, text="Choose...",
                               command=lambda v=var, sw=swatch, vl=val_label:
                                   self._pick_colour(v, sw, vl)).pack(side=tk.LEFT, padx=2)

                elif widget_type == "font_select":
                    # Font selector — shows current font name + browse button
                    current_font = current or self.parent_app.font_path
                    var = tk.StringVar(value=current_font)
                    font_label = ttk.Label(field_row,
                                           text=Path(current_font).name if current_font else "(global)",
                                           foreground="#4488ff", width=20, anchor=tk.W)
                    font_label.pack(side=tk.LEFT, padx=4)
                    ttk.Button(field_row, text="Select...",
                               command=lambda v=var, fl=font_label: self._pick_font(v, fl)
                               ).pack(side=tk.LEFT, padx=2)
                    ttk.Button(field_row, text="Reset",
                               command=lambda v=var, fl=font_label: self._reset_font(v, fl)
                               ).pack(side=tk.LEFT, padx=2)

                else:
                    var = tk.StringVar(value=str(current))
                    ttk.Entry(field_row, textvariable=var, width=12).pack(side=tk.LEFT, padx=4)

                self.result_vars[field_id] = var

            # Hint for date/time format fields only
            if any(fid in ("date_format", "time_format") and wt == "combo_editable"
                   for fid, _, wt, _, _ in fields):
                ttk.Label(specific_frame,
                          text="Codes: %Y=year %m=month %d=day %b=abbr month %B=full month\n"
                               "%H=24h %I=12h %M=min %S=sec %p=AM/PM %a=weekday",
                          foreground="#666666", font=("monospace", 8),
                          justify=tk.LEFT).pack(padx=8, pady=(0, 4), anchor=tk.W)

        # Date/time combined preview
        if opts.get("has_datetime_preview"):
            preview_frame = ttk.LabelFrame(container, text="Preview")
            preview_frame.pack(fill=tk.X, padx=12, pady=4)
            self.dt_preview_label = tk.Label(preview_frame, text="",
                                              font=("monospace", 14), bg="#2a2a2a", fg="white",
                                              height=2, anchor=tk.W, padx=8)
            self.dt_preview_label.pack(fill=tk.X, padx=8, pady=4)
            self._update_full_datetime_preview()

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=12)
        ttk.Button(btn_frame, text="Apply", command=self._apply).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=4)

    def _pick_colour(self, var: tk.StringVar, swatch: tk.Label, val_label: ttk.Label):
        """Open colour chooser dialog. Preserves alpha channel if present."""
        from tkinter import colorchooser
        parts = [int(c.strip()) for c in var.get().split(",")]
        try:
            initial = f"#{parts[0]:02x}{parts[1]:02x}{parts[2]:02x}"
        except Exception:
            initial = "#ffffff"
        alpha = parts[3] if len(parts) > 3 else None
        result = colorchooser.askcolor(color=initial, parent=self, title="Choose Colour")
        if result and result[0]:
            r, g, b = [int(c) for c in result[0]]
            if alpha is not None:
                rgb_str = f"{r},{g},{b},{alpha}"
            else:
                rgb_str = f"{r},{g},{b}"
            var.set(rgb_str)
            swatch.config(bg=result[1])
            val_label.config(text=rgb_str)
            # Re-render tile preview if we have one
            if self._tile_raw_img:
                self._render_tile_preview()

    def _pick_font(self, var: tk.StringVar, label: ttk.Label):
        """Open file dialog to pick a font file."""
        path = filedialog.askopenfilename(
            title="Select Font File",
            parent=self,
            filetypes=[("Font files", "*.ttf *.otf *.TTF *.OTF"), ("All files", "*.*")])
        if path and os.path.isfile(path):
            var.set(path)
            label.config(text=Path(path).name)

    def _reset_font(self, var: tk.StringVar, label: ttk.Label):
        """Reset to global font."""
        var.set("")
        label.config(text="(global)")

    def _update_format_preview(self, var: tk.StringVar, preview_label: ttk.Label):
        """Show a live example of the selected strftime format."""
        import datetime as _dt
        fmt = var.get()
        try:
            example = _dt.datetime(2026, 4, 3, 17, 40, 50, 123456).strftime(fmt)
            preview_label.config(text=example)
        except Exception:
            preview_label.config(text="(invalid)")
        if hasattr(self, "dt_preview_label"):
            self._update_full_datetime_preview()

    def _update_full_datetime_preview(self):
        """Update the combined date + time preview."""
        import datetime as _dt
        sample = _dt.datetime(2026, 4, 3, 17, 40, 50, 123456)
        date_fmt = self.result_vars.get("date_format")
        time_fmt = self.result_vars.get("time_format")
        lines = []
        if date_fmt:
            try:
                lines.append(sample.strftime(date_fmt.get()))
            except Exception:
                lines.append("(invalid date format)")
        if time_fmt:
            try:
                lines.append(sample.strftime(time_fmt.get()))
            except Exception:
                lines.append("(invalid time format)")
        self.dt_preview_label.config(text="\n".join(lines))

    def _on_map_style_change(self, var: tk.StringVar, desc_label: ttk.Label):
        """Update map style description, tile preview from GPX location, and API key help."""
        style = var.get()
        info = MAP_STYLE_INFO.get(style)

        # Clear help area
        if hasattr(self, "_api_help_frame"):
            for w in self._api_help_frame.winfo_children():
                w.destroy()

        if not info:
            desc_label.config(text="")
            return

        desc, access, _ = info

        # Build tile URL dynamically from GPX location
        loc = self.parent_app.gpx_location
        if loc:
            tile_url = _build_tile_url(style, loc[0], loc[1], zoom=14)
        else:
            # Fallback: generic location if no GPX loaded
            tile_url = _build_tile_url(style, -27.47, 153.02, zoom=13)

        key_note = ""
        if access.startswith("key:"):
            provider = access.split(":")[1]
            if tile_url:
                key_note = f" (API key: {provider})"
            else:
                key_note = f" (requires {provider} API key - no preview)"
        desc_label.config(text=f"{desc}{key_note}")

        if tile_url:
            self._fetch_tile_preview(tile_url)
            if access.startswith("key:"):
                provider = access.split(":")[1]
                ttk.Label(self._api_help_frame,
                          text=f"{provider} API key active",
                          foreground="#44aa44").pack(anchor=tk.W)
            if loc:
                ttk.Label(self._api_help_frame,
                          text=f"Preview centred on GPX start: {loc[0]:.4f}, {loc[1]:.4f}",
                          foreground="#888888").pack(anchor=tk.W)
        else:
            self._tile_canvas.delete("all")
            self._tile_canvas.create_text(128, 128,
                                           text="No preview available\n(API key required)",
                                           fill="#666666", font=("sans-serif", 10),
                                           justify=tk.CENTER)

            # Show help with clickable link
            provider = access.split(":")[1] if access.startswith("key:") else ""
            _API_KEY_HELP = {
                "thunderforest": {
                    "url": "https://www.thunderforest.com/pricing/",
                    "label": "thunderforest.com/pricing",
                    "env": "API_KEY_THUNDERFOREST",
                    "cli": "--thunderforest-key",
                },
                "geoapify": {
                    "url": "https://myprojects.geoapify.com/",
                    "label": "myprojects.geoapify.com",
                    "env": "API_KEY_GEOAPIFY",
                    "cli": "--geoapify-key",
                },
            }
            pinfo = _API_KEY_HELP.get(provider)
            if pinfo:
                ttk.Label(self._api_help_frame,
                          text=f"A free {provider} API key is required for this style.",
                          foreground="#cc8844").pack(anchor=tk.W, pady=(2, 0))

                ttk.Label(self._api_help_frame,
                          text="Get your free key at:").pack(anchor=tk.W)

                link = tk.Label(self._api_help_frame, text=pinfo["label"],
                                fg="#4488ff", cursor="hand2",
                                font=("sans-serif", 10, "underline"))
                link.pack(anchor=tk.W)
                link.bind("<Button-1>", lambda e, u=pinfo["url"]: _open_url(u))

                ttk.Label(self._api_help_frame,
                          text=f"Then set it via:\n"
                               f"  CLI:  {pinfo['cli']} YOUR_KEY\n"
                               f"  Env:  export {pinfo['env']}=YOUR_KEY\n"
                               f"  Settings panel: API Keys section",
                          foreground="#888888",
                          font=("monospace", 8),
                          justify=tk.LEFT).pack(anchor=tk.W, pady=(2, 0))

    def _fetch_tile_preview(self, url: str):
        """Fetch a map tile in a background thread and display it."""
        self._tile_canvas.delete("all")
        self._tile_canvas.create_text(128, 128, text="Loading...", fill="#666666")

        def _fetch():
            import urllib.request
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "gopro-layout-editor/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = resp.read()
                img = Image.open(io.BytesIO(data)).convert("RGBA")
                return img
            except Exception:
                return None

        def _on_fetched(img):
            if img:
                self._tile_raw_img = img.resize((256, 256), Image.Resampling.LANCZOS)
                self._render_tile_preview()
            else:
                self._tile_canvas.delete("all")
                self._tile_canvas.create_text(128, 128, text="Failed to load",
                                               fill="#cc4444", font=("sans-serif", 10))

        def _run():
            result = _fetch()
            self.after(0, lambda: _on_fetched(result))

        threading.Thread(target=_run, daemon=True).start()

    def _render_tile_preview(self):
        """Render the cached tile with current settings, route, and marker."""
        if not self._tile_raw_img:
            return
        self._tile_canvas.delete("all")
        img = self._tile_raw_img.copy()

        from PIL import ImageDraw as PilDraw

        # Draw route and marker for journey_map, or position marker for moving_map
        if self.comp.name == "journey_map" and self.parent_app.gpx_path:
            self._draw_route_on_tile(img)
        elif self.comp.name == "moving_map":
            self._draw_position_marker(img)

        # Read corner radius from dialog field if present, else from app
        cr = 0
        if "map_corner_radius" in self.result_vars:
            try:
                cr = int(self.result_vars["map_corner_radius"].get())
            except (ValueError, TypeError):
                cr = self.parent_app.map_corner_radius.get()
        else:
            cr = self.parent_app.map_corner_radius.get()

        if cr > 0:
            img = _apply_rounded_corners(img, cr)

        bordered = img.copy()
        draw = PilDraw.Draw(bordered)
        draw.rounded_rectangle([0, 0, 255, 255], radius=cr,
                                outline=(180, 180, 180), width=3)
        self._tile_photo = ImageTk.PhotoImage(bordered)
        self._tile_canvas.create_image(0, 0, anchor=tk.NW, image=self._tile_photo)

    def _draw_route_on_tile(self, img: Image.Image):
        """Draw GPX route and location marker on the tile preview image."""
        from PIL import ImageDraw as PilDraw
        points = _parse_gpx_points(self.parent_app.gpx_path)
        if len(points) < 2:
            return

        # Get current colours from dialog fields
        def _get_rgb(field_id, default):
            if field_id in self.result_vars:
                try:
                    parts = [int(c.strip()) for c in self.result_vars[field_id].get().split(",")]
                    return tuple(parts[:3])
                except Exception:
                    pass
            return default

        def _get_int(field_id, default):
            if field_id in self.result_vars:
                try:
                    return int(self.result_vars[field_id].get())
                except Exception:
                    pass
            return default

        track_colour = _get_rgb("jm_track_colour", (255, 0, 0))
        line_width = _get_int("jm_line_width", 4)
        loc_colour = _get_rgb("jm_loc_colour", (0, 0, 255))
        loc_outline = _get_rgb("jm_loc_outline", (0, 0, 0))
        loc_size = _get_int("jm_loc_size", 6)

        # Find bounding box of all points to fit them into the tile
        lats = [p[0] for p in points]
        lons = [p[1] for p in points]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)

        # Add padding
        lat_range = max_lat - min_lat or 0.001
        lon_range = max_lon - min_lon or 0.001
        pad = 0.1
        min_lat -= lat_range * pad
        max_lat += lat_range * pad
        min_lon -= lon_range * pad
        max_lon += lon_range * pad
        lat_range = max_lat - min_lat
        lon_range = max_lon - min_lon

        # Convert lat/lon to pixel coords on the 256x256 tile
        def to_px(lat, lon):
            x = int((lon - min_lon) / lon_range * 240 + 8)
            y = int((max_lat - lat) / lat_range * 240 + 8)
            return (x, y)

        # Draw track line
        draw = PilDraw.Draw(img)
        pixel_points = [to_px(lat, lon) for lat, lon, _ in points]
        if len(pixel_points) >= 2:
            draw.line(pixel_points, fill=track_colour, width=line_width)

        # Draw current location marker (at video start position)
        loc = self.parent_app.gpx_location
        if loc:
            mx, my = to_px(loc[0], loc[1])
            r = loc_size
            draw.ellipse([mx - r, my - r, mx + r, my + r],
                         fill=loc_colour, outline=loc_outline, width=1)


    def _draw_position_marker(self, img: Image.Image):
        """Draw a centre position marker on the moving_map tile preview."""
        from PIL import ImageDraw as PilDraw
        draw = PilDraw.Draw(img)
        cx, cy = 128, 128
        # Blue dot with black outline — matches the default moving_map marker
        r = 6
        draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                     fill=(0, 0, 255), outline=(0, 0, 0), width=2)
        # Crosshair lines
        draw.line([cx - 12, cy, cx - r - 2, cy], fill=(0, 0, 255, 180), width=1)
        draw.line([cx + r + 2, cy, cx + 12, cy], fill=(0, 0, 255, 180), width=1)
        draw.line([cx, cy - 12, cx, cy - r - 2], fill=(0, 0, 255, 180), width=1)
        draw.line([cx, cy + r + 2, cx, cy + 12], fill=(0, 0, 255, 180), width=1)

    # Map field_id to the app's tk variable name
    _APP_VAR_MAP = {
        "map_size": "map_size", "map_zoom": "map_zoom",
        "map_corner_radius": "map_corner_radius", "map_opacity": "map_opacity",
        "map_rotate": "map_rotate", "map_style": "map_style",
        "jm_track_colour": "jm_track_colour", "jm_line_width": "jm_line_width",
        "jm_loc_colour": "jm_loc_colour", "jm_loc_outline": "jm_loc_outline",
        "jm_loc_size": "jm_loc_size",
        "date_format": "date_format", "time_format": "time_format",
        "speed_unit": "speed_unit",
    }

    def _get_current_value(self, field_id: str, default):
        """Get current value — check component custom_props first, then app state."""
        if field_id in self.comp.custom_props:
            return self.comp.custom_props[field_id]
        if field_id == "chart_width":
            return self.comp.width
        attr = self._APP_VAR_MAP.get(field_id)
        if attr and hasattr(self.parent_app, attr):
            return getattr(self.parent_app, attr).get()
        return default

    def _apply(self):
        self.comp.x = self.x_var.get()
        self.comp.y = self.y_var.get()
        self.comp.width = self.w_var.get()
        self.comp.height = self.h_var.get()

        # Sync W/H to chart dimensions
        if self.comp.name == "gradient_chart":
            self.comp.custom_props["chart_width"] = self.comp.width
            self.comp.custom_props["chart_height"] = self.comp.height

        # Sync W/H to map_size for map components (maps are always square)
        if self.comp.name in ("moving_map", "journey_map"):
            size = min(self.comp.width, self.comp.height)
            self.comp.width = size
            self.comp.height = size
            self.parent_app.map_size.set(size)
            self.parent_app.map_size_label.config(text=str(size))
            for c in self.parent_app.components:
                if c.name in ("moving_map", "journey_map"):
                    c.width = size
                    c.height = size

        for field_id, var in self.result_vars.items():
            value = var.get()

            # Map size updates both map components' bounding boxes
            if field_id == "map_size":
                size = int(value)
                self.parent_app.map_size.set(size)
                self.parent_app.map_size_label.config(text=str(size))
                for c in self.parent_app.components:
                    if c.name in ("moving_map", "journey_map"):
                        c.width = size
                        c.height = size
            elif field_id == "map_zoom":
                self.parent_app.map_zoom.set(int(value))
                self.parent_app.map_zoom_label.config(text=str(int(value)))
            elif field_id == "chart_width":
                self.comp.width = int(value)
            elif field_id in ("date_format", "time_format"):
                self.comp.custom_props[field_id] = value
                getattr(self.parent_app, field_id).set(value)
            else:
                # Try updating the app-level variable if mapped
                attr = self._APP_VAR_MAP.get(field_id)
                if attr and hasattr(self.parent_app, attr):
                    app_var = getattr(self.parent_app, attr)
                    try:
                        app_var.set(type(app_var.get())(value))
                    except (ValueError, TypeError):
                        app_var.set(value)
                else:
                    # Store as per-component custom property
                    try:
                        self.comp.custom_props[field_id] = int(value)
                    except (ValueError, TypeError):
                        self.comp.custom_props[field_id] = value

        self.parent_app._redraw_components()
        self.destroy()


# ---------------------------------------------------------------------------
# API Keys dialog
# ---------------------------------------------------------------------------

class ApiKeysDialog(tk.Toplevel):
    """Modal dialog for viewing and editing map API keys."""

    def __init__(self, parent: LayoutEditorApp):
        super().__init__(parent)
        self.parent_app = parent
        self.title("API Keys")
        self.geometry("500x450")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        ttk.Label(self, text="Map Tile API Keys",
                  font=("sans-serif", 13, "bold")).pack(padx=16, pady=(16, 8), anchor=tk.W)

        ttk.Label(self, text="API keys are needed for Thunderforest (tf-*) and Geoapify (geo-*) map styles.\n"
                             "The osm and cyclosm styles work without any key.",
                  foreground="#888888", wraplength=460,
                  justify=tk.LEFT).pack(padx=16, pady=(0, 8), anchor=tk.W)

        # Thunderforest
        tf_frame = ttk.LabelFrame(self, text="Thunderforest (tf-* styles)")
        tf_frame.pack(fill=tk.X, padx=16, pady=4)

        self.tf_var = tk.StringVar(value=os.environ.get("API_KEY_THUNDERFOREST", ""))
        ttk.Entry(tf_frame, textvariable=self.tf_var, width=50).pack(fill=tk.X, padx=8, pady=4)

        tf_link_row = ttk.Frame(tf_frame)
        tf_link_row.pack(fill=tk.X, padx=8, pady=(0, 4))
        ttk.Label(tf_link_row, text="Get a free key:").pack(side=tk.LEFT)
        tf_link = tk.Label(tf_link_row, text="thunderforest.com/pricing",
                           fg="#4488ff", cursor="hand2",
                           font=("sans-serif", 10, "underline"))
        tf_link.pack(side=tk.LEFT, padx=4)
        tf_link.bind("<Button-1>", lambda e: _open_url("https://www.thunderforest.com/pricing/"))
        ttk.Label(tf_frame, text="Env var: API_KEY_THUNDERFOREST",
                  foreground="#888888", font=("monospace", 9)).pack(padx=8, pady=(0, 4), anchor=tk.W)

        # Geoapify
        geo_frame = ttk.LabelFrame(self, text="Geoapify (geo-* styles)")
        geo_frame.pack(fill=tk.X, padx=16, pady=4)

        self.geo_var = tk.StringVar(value=os.environ.get("API_KEY_GEOAPIFY", ""))
        ttk.Entry(geo_frame, textvariable=self.geo_var, width=50).pack(fill=tk.X, padx=8, pady=4)

        geo_link_row = ttk.Frame(geo_frame)
        geo_link_row.pack(fill=tk.X, padx=8, pady=(0, 4))
        ttk.Label(geo_link_row, text="Get a free key:").pack(side=tk.LEFT)
        geo_link = tk.Label(geo_link_row, text="myprojects.geoapify.com",
                            fg="#4488ff", cursor="hand2",
                            font=("sans-serif", 10, "underline"))
        geo_link.pack(side=tk.LEFT, padx=4)
        geo_link.bind("<Button-1>", lambda e: _open_url("https://myprojects.geoapify.com/"))
        ttk.Label(geo_frame, text="Env var: API_KEY_GEOAPIFY",
                  foreground="#888888", font=("monospace", 9)).pack(padx=8, pady=(0, 4), anchor=tk.W)

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=12)
        ttk.Button(btn_frame, text="Apply", command=self._apply).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=4)

    def _apply(self):
        tf = self.tf_var.get().strip()
        geo = self.geo_var.get().strip()
        if tf:
            os.environ["API_KEY_THUNDERFOREST"] = tf
        elif "API_KEY_THUNDERFOREST" in os.environ:
            del os.environ["API_KEY_THUNDERFOREST"]
        if geo:
            os.environ["API_KEY_GEOAPIFY"] = geo
        elif "API_KEY_GEOAPIFY" in os.environ:
            del os.environ["API_KEY_GEOAPIFY"]
        self.parent_app.status_var.set("API keys updated.")
        self.destroy()


# ---------------------------------------------------------------------------
# Font selector dialog
# ---------------------------------------------------------------------------

class FontSelectorDialog(tk.Toplevel):
    """Modal dialog for selecting a font from system fonts or browsing for a file."""

    def __init__(self, parent: LayoutEditorApp):
        super().__init__(parent)
        self.parent_app = parent
        self.title("Select Font")
        self.geometry("500x450")
        self.transient(parent)
        self.grab_set()

        self.selected_path: Optional[str] = None

        self._build_ui()
        self._load_fonts()

    def _build_ui(self):
        ttk.Label(self, text="Select a font for the overlay:",
                  font=("sans-serif", 11)).pack(padx=12, pady=(12, 4), anchor=tk.W)

        # Search/filter
        filter_frame = ttk.Frame(self)
        filter_frame.pack(fill=tk.X, padx=12, pady=4)
        ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", self._on_filter)
        filter_entry = ttk.Entry(filter_frame, textvariable=self.filter_var)
        filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        filter_entry.focus_set()

        # Font list
        list_frame = ttk.Frame(self)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.font_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set,
                                        font=("monospace", 10))
        self.font_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.font_listbox.yview)
        self.font_listbox.bind("<<ListboxSelect>>", self._on_select)
        self.font_listbox.bind("<Double-1>", lambda e: self._apply())

        # Current selection display
        self.selection_label = ttk.Label(self, text=f"Current: {self.parent_app.font_path}",
                                          wraplength=460)
        self.selection_label.pack(padx=12, pady=4, anchor=tk.W)

        # Preview
        self.preview_label = tk.Label(self, text="0123456789 km/h",
                                       font=("sans-serif", 20), bg="#2a2a2a", fg="white",
                                       height=2)
        self.preview_label.pack(fill=tk.X, padx=12, pady=4)

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=8)
        ttk.Button(btn_frame, text="Browse File...", command=self._browse).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Apply", command=self._apply).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=4)

        self.all_fonts: list[tuple[str, str]] = []  # (display_name, path)

    def _load_fonts(self):
        """Load system fonts using fc-list."""
        self.all_fonts = []
        try:
            result = subprocess.run(
                ["fc-list", "--format=%{file}\t%{family}\t%{style}\n"],
                capture_output=True, text=True, timeout=10)
            seen_paths = set()
            for line in sorted(result.stdout.strip().split("\n")):
                parts = line.split("\t")
                if len(parts) >= 2:
                    fpath = parts[0].strip()
                    family = parts[1].strip().split(",")[0]
                    style = parts[2].strip().split(",")[0] if len(parts) > 2 else ""
                    # Only show .ttf and .otf files
                    if fpath.lower().endswith((".ttf", ".otf")) and fpath not in seen_paths:
                        seen_paths.add(fpath)
                        display = f"{family} {style}".strip()
                        self.all_fonts.append((display, fpath))

            self.all_fonts.sort(key=lambda x: x[0].lower())
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        self._populate_list(self.all_fonts)

    def _populate_list(self, fonts: list[tuple[str, str]]):
        self.font_listbox.delete(0, tk.END)
        self._filtered_fonts = fonts
        for display, path in fonts:
            self.font_listbox.insert(tk.END, display)

    def _on_filter(self, *args):
        query = self.filter_var.get().lower()
        if not query:
            self._populate_list(self.all_fonts)
        else:
            filtered = [(d, p) for d, p in self.all_fonts if query in d.lower()]
            self._populate_list(filtered)

    def _on_select(self, event):
        sel = self.font_listbox.curselection()
        if sel and sel[0] < len(self._filtered_fonts):
            display, path = self._filtered_fonts[sel[0]]
            self.selected_path = path
            self.selection_label.config(text=f"Selected: {display}\n{path}")
            # Try to update preview with the selected font
            try:
                from tkinter.font import Font as TkFont
                preview_font = TkFont(family=display.split()[0], size=20)
                self.preview_label.config(font=preview_font)
            except Exception:
                pass

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select Font File",
            filetypes=[("Font files", "*.ttf *.otf *.TTF *.OTF"), ("All files", "*.*")])
        if path:
            self.selected_path = path
            self.selection_label.config(text=f"Selected: {Path(path).name}\n{path}")

    def _apply(self):
        if self.selected_path and os.path.isfile(self.selected_path):
            self.parent_app.font_path = self.selected_path
            self.parent_app.font_label.config(text=Path(self.selected_path).name)
            self.parent_app.status_var.set(f"Font: {Path(self.selected_path).name}")
            self.destroy()
        else:
            messagebox.showwarning("Invalid Font", "Please select a valid font file.", parent=self)


# ---------------------------------------------------------------------------
# Encoding progress dialog
# ---------------------------------------------------------------------------

class EncodingDialog(tk.Toplevel):

    def __init__(self, parent, videos: list[VideoEntry], gpx_path: Path,
                 layout_xml_path: Path, speed_unit: str, font: str,
                 gpu_profile: Optional[str], dashboard_script: Path,
                 map_style: str = "osm", gpx_time_offset: float = 0.0):
        super().__init__(parent)
        self.title("Encoding Progress")
        self.geometry("600x400")
        self.transient(parent)

        self.videos = videos
        self.gpx_path = gpx_path
        self.layout_xml_path = layout_xml_path
        self.speed_unit = speed_unit
        self.font = font
        self.gpu_profile = gpu_profile
        self.dashboard_script = dashboard_script
        self.map_style = map_style
        self.gpx_time_offset = gpx_time_offset
        self.process: Optional[subprocess.Popen] = None
        self.cancelled = False

        self._build_ui()
        self.after(100, self._start_encoding)

    def _build_ui(self):
        ttk.Label(self, text="Encoding Videos", font=("sans-serif", 14, "bold")).pack(pady=8)

        self.overall_label = ttk.Label(self, text="Preparing...")
        self.overall_label.pack(padx=16, pady=4, anchor=tk.W)

        self.overall_progress = ttk.Progressbar(self, mode="determinate", length=550)
        self.overall_progress.pack(padx=16, pady=4)

        self.current_label = ttk.Label(self, text="")
        self.current_label.pack(padx=16, pady=4, anchor=tk.W)

        self.current_progress = ttk.Progressbar(self, mode="determinate", length=550)
        self.current_progress.pack(padx=16, pady=4)

        # Log output
        self.log_text = tk.Text(self, height=10, state=tk.DISABLED, bg="#1a1a1a", fg="#cccccc",
                                font=("monospace", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=8)
        self.cancel_btn = ttk.Button(btn_frame, text="Cancel", command=self._cancel)
        self.cancel_btn.pack(side=tk.LEFT, padx=8)
        self.close_btn = ttk.Button(btn_frame, text="Close", command=self.destroy, state=tk.DISABLED)
        self.close_btn.pack(side=tk.LEFT, padx=8)

    def _log(self, msg: str):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _start_encoding(self):
        self.overall_progress.config(maximum=len(self.videos))
        threading.Thread(target=self._encode_all, daemon=True).start()

    def _encode_all(self):
        for i, video in enumerate(self.videos):
            if self.cancelled:
                self._ui_update(lambda: self._log("Cancelled."))
                break

            self._ui_update(lambda v=video, idx=i: self._update_labels(v, idx))

            success = self._encode_one(video)

            self._ui_update(lambda idx=i: self.overall_progress.config(value=idx + 1))

            if not success and not self.cancelled:
                self._ui_update(lambda v=video: self._log(f"FAILED: {v.basename}"))

        self._ui_update(self._encoding_complete)

    def _update_labels(self, video: VideoEntry, idx: int):
        self.overall_label.config(text=f"Video {idx + 1} of {len(self.videos)}")
        self.current_label.config(text=f"Processing: {video.basename}")
        self.current_progress.config(value=0)
        self._log(f"Starting: {video.basename} ({video.eff_width}x{video.eff_height})")

    def _encode_one(self, video: VideoEntry) -> bool:
        out_path = video.path.parent / (video.path.stem + "_overlay" + video.path.suffix)

        cmd = [
            sys.executable, str(self.dashboard_script),
            "--font", self.font,
            "--gpx", str(self.gpx_path),
            "--use-gpx-only",
            "--video-time-start", "video-created",
            "--overlay-size", f"{video.eff_width}x{video.eff_height}",
            "--units-speed", self.speed_unit,
            "--layout", "xml",
            "--layout-xml", str(self.layout_xml_path),
            "--map-style", self.map_style,
        ]
        if self.gpx_time_offset:
            cmd.extend(["--gpx-time-offset", str(self.gpx_time_offset)])
        if self.gpu_profile:
            cmd.extend(["--profile", self.gpu_profile])
        cmd.extend([str(video.path), str(out_path)])

        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1)

            total_frames = None
            for line in self.process.stdout:
                if self.cancelled:
                    self.process.terminate()
                    return False

                line = line.strip()

                # Parse "Render: N [ P%]" lines
                if line.startswith("Render:"):
                    try:
                        parts = line.split("[")
                        if len(parts) >= 2:
                            pct_str = parts[1].split("%")[0].strip()
                            pct = int(pct_str)
                            self._ui_update(
                                lambda p=pct: self.current_progress.config(value=p, maximum=100))
                    except (ValueError, IndexError):
                        pass
                elif "Timeseries has" in line:
                    # "Timeseries has N data points"
                    try:
                        n = int(line.split("has")[1].split("data")[0].strip())
                        total_frames = n
                    except (ValueError, IndexError):
                        pass
                elif line and not line.startswith("frame="):
                    self._ui_update(lambda l=line: self._log(l))

            self.process.wait()
            return self.process.returncode == 0

        except Exception as e:
            self._ui_update(lambda: self._log(f"Error: {e}"))
            return False

    def _cancel(self):
        self.cancelled = True
        if self.process:
            self.process.terminate()
        self.cancel_btn.config(state=tk.DISABLED)

    def _encoding_complete(self):
        self.cancel_btn.config(state=tk.DISABLED)
        self.close_btn.config(state=tk.NORMAL)
        if not self.cancelled:
            self._log("All encoding complete.")
            self.current_label.config(text="Complete!")
        else:
            self.current_label.config(text="Cancelled.")

    def _ui_update(self, func):
        """Schedule a function to run on the main UI thread."""
        self.after(0, func)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply_rounded_corners(img: Image.Image, radius: int) -> Image.Image:
    """Apply rounded corners to a PIL image using an alpha mask."""
    from PIL import ImageDraw as PilDraw
    mask = Image.new("L", img.size, 0)
    draw = PilDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, img.size[0] - 1, img.size[1] - 1],
                           radius=radius, fill=255)
    img = img.copy()
    img.putalpha(mask)
    return img


def _open_url(url: str):
    """Open a URL in the default browser."""
    import webbrowser
    webbrowser.open(url)


def _format_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _load_dotenv(path: str):
    """Load key=value pairs from a .env file into os.environ."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    os.environ[key] = value
    except FileNotFoundError:
        print(f"Warning: .env file not found: {path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GoPro Dashboard Overlay — Visual Layout Editor")
    parser.add_argument("workdir", nargs="?", default=None,
                        help="Working folder — sets initial directory for file dialogs (or set GOPRO_WORKDIR env var)")
    parser.add_argument("--videos", nargs="+", default=[], help="Video files to add on startup")
    parser.add_argument("--thunderforest-key", help="Thunderforest API key for tf-* map styles")
    parser.add_argument("--geoapify-key", help="Geoapify API key for geo-* map styles")
    parser.add_argument("--env-file", help="Path to .env file with API keys (API_KEY_THUNDERFOREST, API_KEY_GEOAPIFY)")
    parser.add_argument("--gpx", help="GPX file to open on startup")
    parser.add_argument("--layout", help="Load layout XML file (or set GOPRO_LAYOUT_XML env var)")
    cli_args = parser.parse_args()

    # Load .env file if specified
    if cli_args.env_file:
        _load_dotenv(cli_args.env_file)

    # Set API keys from CLI args into environment
    if cli_args.thunderforest_key:
        os.environ["API_KEY_THUNDERFOREST"] = cli_args.thunderforest_key
    if cli_args.geoapify_key:
        os.environ["API_KEY_GEOAPIFY"] = cli_args.geoapify_key

    app = LayoutEditorApp()

    # Set working directory
    if cli_args.workdir:
        app.workdir = os.path.abspath(cli_args.workdir)
    elif os.environ.get("GOPRO_WORKDIR"):
        app.workdir = os.path.abspath(os.environ["GOPRO_WORKDIR"])

    # Load files from CLI args
    if cli_args.gpx:
        app.gpx_path = Path(cli_args.gpx)
        app.gpx_label.config(text=app.gpx_path.name)
        loc = _extract_gpx_first_point(app.gpx_path)
        if loc:
            app.gpx_location = loc

    for v in (cli_args.videos or []):
        try:
            entry = analyse_video(Path(v))
            app.videos.append(entry)
            app.video_listbox.insert(tk.END, entry.basename)
        except Exception as e:
            print(f"Warning: failed to load {v}: {e}")
    if app.videos:
        app.video_listbox.selection_set(0)
        app._select_video(0)

    # Load layout XML from CLI arg or env var
    layout_xml = cli_args.layout or os.environ.get("GOPRO_LAYOUT_XML")
    if layout_xml and app.components:
        app._load_layout_xml(layout_xml)

    app.mainloop()
