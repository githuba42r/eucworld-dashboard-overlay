import collections
import gzip
import re
from pathlib import Path
from typing import List

import gpxpy

from .gpmf import GPSFix
from .point import Point
from .timeseries import Timeseries, Entry

GPX = collections.namedtuple("GPX", "time lat lon alt hr cad atemp power speed")


def _preprocess_gpx(xml_str: str) -> str:
    """Move non-standard <speed> elements (e.g. from EUC World) into
    TrackPointExtension so gpxpy can parse them.

    EUC World exports <speed> as a direct child of <trkpt>, which is not
    valid GPX 1.1.  This rewrites each occurrence into the standard
    Garmin TrackPointExtension namespace.
    """
    tpx_ns = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"

    # Match <speed>VALUE</speed> that is a direct child of <trkpt> (not inside <extensions>).
    # Use a simple regex that handles both namespaced and non-namespaced variants.
    def _move_speed(match):
        # EUC World exports speed in km/h; GPX standard expects m/s
        speed_kph = float(match.group(1))
        speed_mps = speed_kph / 3.6
        ext_block = (
            f'<extensions>'
            f'<gpxtpx:TrackPointExtension xmlns:gpxtpx="{tpx_ns}">'
            f'<gpxtpx:speed>{speed_mps:.2f}</gpxtpx:speed>'
            f'</gpxtpx:TrackPointExtension>'
            f'</extensions>'
        )
        return ext_block

    # Remove <speed> from trkpt body and add it to extensions.
    # Handle both with and without GPX namespace prefix.
    # First check if this GPX has speed as direct child (not in extensions)
    if re.search(r'<(?:[a-z]+:)?trkpt[^>]*>.*?<(?:[a-z]+:)?speed>', xml_str[:5000], re.DOTALL):
        # Extract and relocate speed elements
        # Pattern: match <speed>...</speed> (with optional namespace prefix)
        ns_pattern = r'<(?:{[^}]+})?speed>([^<]+)</(?:{[^}]+})?speed>\s*'
        plain_pattern = r'<speed>([^<]+)</speed>\s*'

        # Only process if there are no existing <extensions> blocks with speed
        if 'TrackPointExtension' not in xml_str:
            # Replace each <speed>val</speed> with extension block
            xml_str = re.sub(plain_pattern, _move_speed, xml_str)
            # Handle namespace-prefixed version too
            xml_str = re.sub(ns_pattern, _move_speed, xml_str)

    return xml_str


def fudge(gpx):
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                data = {
                    "time": point.time,
                    "lat": point.latitude,
                    "lon": point.longitude,
                    "alt": point.elevation,
                    "atemp": None,
                    "hr": None,
                    "cad": None,
                    "power": None,
                    "speed": None
                }
                for extension in point.extensions:
                    for element in extension.iter():
                        tag = element.tag[element.tag.find("}") + 1:]
                        if tag in ("atemp", "hr", "cad", "power", "speed"):
                            data[tag] = float(element.text)
                yield GPX(**data)


def with_unit(gpx, units):
    return GPX(
        gpx.time,
        gpx.lat,
        gpx.lon,
        units.Quantity(gpx.alt, units.m) if gpx.alt is not None else None,
        units.Quantity(gpx.hr, units.bpm) if gpx.hr is not None else None,
        units.Quantity(gpx.cad, units.rpm) if gpx.cad is not None else None,
        units.Quantity(gpx.atemp, units.celsius) if gpx.atemp is not None else None,
        units.Quantity(gpx.power, units.watt) if gpx.power is not None else None,
        units.Quantity(gpx.speed, units.mps) if gpx.speed is not None else None,
    )


def load(filepath: Path, units):
    if filepath.suffix == ".gz":
        with gzip.open(filepath, 'rb') as gpx_file:
            xml_str = gpx_file.read().decode('utf-8')
    else:
        with filepath.open('r') as gpx_file:
            xml_str = gpx_file.read()
    xml_str = _preprocess_gpx(xml_str)
    return load_xml(xml_str, units)


def load_xml(file_or_str, units) -> List[GPX]:
    gpx = gpxpy.parse(file_or_str)

    return [with_unit(p, units) for p in fudge(gpx)]


def gpx_to_timeseries(gpx: List[GPX], units):
    gpx_timeseries = Timeseries()

    points = [
        Entry(
            point.time,
            point=Point(point.lat, point.lon),
            alt=point.alt,
            hr=point.hr,
            cad=point.cad,
            atemp=point.atemp,
            power=point.power,
            speed=point.speed,
            packet=units.Quantity(index),
            packet_index=units.Quantity(0),
            # we should set the gps fix or Journey.accept() will skip the point:
            gpsfix=GPSFix.LOCK_3D.value,
            gpslock=units.Quantity(GPSFix.LOCK_3D.value)
        )
        for index, point in enumerate(gpx)
    ]

    gpx_timeseries.add(*points)

    return gpx_timeseries


def load_timeseries(filepath: Path, units) -> Timeseries:
    return gpx_to_timeseries(load(filepath, units), units)
