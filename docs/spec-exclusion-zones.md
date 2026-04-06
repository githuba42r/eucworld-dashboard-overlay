# Exclusion Zones - Implementation Specification

## Overview

Location-based exclusion zones allow users to define geographic regions where video frames and dashboard overlays are replaced with redacted (blacked-out) frames during rendering. This prevents sensitive locations (home, workplace, school) from appearing in published videos.

This extends the existing single-circle `--privacy` zone concept (which only hides map route segments) into a full frame-redaction system supporting multiple named zones of varying geometry, persisted in a standalone JSON file.

## Relationship to Existing Privacy Zones

The current `PrivacyZone` class in `gopro_overlay/privacy.py` provides:
- A single circle zone (centre point + radius)
- Used only by map widgets to exclude route segments from being drawn
- Passed through the layout XML system to `JourneyMap`, `MovingJourneyMap`, and `CircularJourneyMap`
- Does NOT redact video frames or overlay content

Exclusion zones are a separate, higher-level concept:
- Multiple named zones per file (circles and polygons)
- Redact the entire video frame AND overlay, not just map route lines
- Applied in the render loop, not in individual widgets
- The existing `--privacy` flag and `PrivacyZone` class remain unchanged

## JSON Storage Format

### File Extension

`.exclusion-zones.json` (recommended convention, not enforced)

### Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "GoPro Dashboard Overlay Exclusion Zones",
  "type": "object",
  "required": ["version", "zones"],
  "properties": {
    "version": {
      "type": "integer",
      "const": 1
    },
    "zones": {
      "type": "array",
      "items": {
        "oneOf": [
          { "$ref": "#/$defs/circle_zone" },
          { "$ref": "#/$defs/polygon_zone" }
        ]
      }
    },
    "redact_style": {
      "type": "object",
      "description": "Optional global defaults for redaction appearance",
      "properties": {
        "fill_colour": {
          "type": "array",
          "items": { "type": "integer", "minimum": 0, "maximum": 255 },
          "minItems": 3,
          "maxItems": 4,
          "default": [0, 0, 0, 255],
          "description": "RGBA fill colour for redacted frames"
        },
        "show_label": {
          "type": "boolean",
          "default": true,
          "description": "Whether to render REDACTED text on blacked-out frames"
        }
      }
    }
  },
  "$defs": {
    "latlon": {
      "type": "object",
      "required": ["lat", "lon"],
      "properties": {
        "lat": { "type": "number", "minimum": -90, "maximum": 90 },
        "lon": { "type": "number", "minimum": -180, "maximum": 180 }
      }
    },
    "circle_zone": {
      "type": "object",
      "required": ["name", "type", "center", "radius_m"],
      "properties": {
        "name": { "type": "string", "minLength": 1 },
        "type": { "type": "string", "const": "circle" },
        "center": { "$ref": "#/$defs/latlon" },
        "radius_m": { "type": "number", "exclusiveMinimum": 0, "description": "Radius in metres" },
        "buffer_m": { "type": "number", "minimum": 0, "default": 0, "description": "Hysteresis buffer in metres for enter/exit transitions" },
        "enabled": { "type": "boolean", "default": true }
      }
    },
    "polygon_zone": {
      "type": "object",
      "required": ["name", "type", "vertices"],
      "properties": {
        "name": { "type": "string", "minLength": 1 },
        "type": { "type": "string", "const": "polygon" },
        "vertices": {
          "type": "array",
          "items": { "$ref": "#/$defs/latlon" },
          "minItems": 3,
          "description": "Ordered vertices defining the polygon boundary. The polygon is implicitly closed (last vertex connects to first)."
        },
        "buffer_m": { "type": "number", "minimum": 0, "default": 0, "description": "Hysteresis buffer in metres for enter/exit transitions" },
        "enabled": { "type": "boolean", "default": true }
      }
    }
  }
}
```

### Example File

```json
{
  "version": 1,
  "zones": [
    {
      "name": "Home",
      "type": "circle",
      "center": {"lat": -27.4698, "lon": 153.0251},
      "radius_m": 200
    },
    {
      "name": "Office",
      "type": "polygon",
      "vertices": [
        {"lat": -27.4710, "lon": 153.0230},
        {"lat": -27.4710, "lon": 153.0260},
        {"lat": -27.4730, "lon": 153.0260},
        {"lat": -27.4730, "lon": 153.0230}
      ],
      "buffer_m": 50
    },
    {
      "name": "School",
      "type": "circle",
      "center": {"lat": -27.4500, "lon": 153.0100},
      "radius_m": 150,
      "enabled": false
    }
  ],
  "redact_style": {
    "fill_colour": [0, 0, 0, 255],
    "show_label": true
  }
}
```

## Python Module Design

### New Module: `gopro_overlay/exclusion.py`

This module contains all exclusion zone logic. It does not modify `privacy.py`.

```
gopro_overlay/exclusion.py
    ExclusionZone          (abstract base)
    CircleExclusionZone    (concrete - circle geometry)
    PolygonExclusionZone   (concrete - polygon geometry)
    ExclusionZoneSet       (collection with contains() check)
    RedactStyle            (dataclass for redaction appearance)
    load_exclusion_zones() (JSON file loader)
```

### Class: `ExclusionZone` (abstract base)

```python
class ExclusionZone:
    name: str
    enabled: bool
    buffer_m: float  # hysteresis buffer

    def contains(self, point: Point) -> bool:
        """Return True if the point is inside this zone (excluding buffer)."""
        raise NotImplementedError

    def contains_with_buffer(self, point: Point) -> bool:
        """Return True if the point is within zone + buffer distance."""
        raise NotImplementedError
```

### Class: `CircleExclusionZone`

Uses `geographiclib.geodesic.Geodesic.WGS84.Inverse()` for geodesic distance, consistent with the existing `PrivacyZone.encloses()` implementation.

```python
class CircleExclusionZone(ExclusionZone):
    center: Point
    radius_m: float

    def contains(self, point: Point) -> bool:
        dist = abs(Geodesic.WGS84.Inverse(
            self.center.lat, self.center.lon, point.lat, point.lon
        )['s12'])
        return dist <= self.radius_m
```

### Class: `PolygonExclusionZone`

Uses the ray-casting algorithm for point-in-polygon testing. This operates on lat/lon coordinates directly, which is acceptable for the small polygon sizes expected (neighbourhood-scale, not continental).

```python
class PolygonExclusionZone(ExclusionZone):
    vertices: list[Point]

    def contains(self, point: Point) -> bool:
        """Ray-casting algorithm on lat/lon plane."""
        ...

    def contains_with_buffer(self, point: Point) -> bool:
        """Check contains(), then if False check minimum geodesic distance
        to each polygon edge is within buffer_m."""
        ...
```

Ray-casting implementation detail: cast a ray from the test point along the positive longitude axis and count edge crossings. An odd count means inside. This is the standard O(n) algorithm where n is the number of vertices.

For the buffer check on polygons: if the point is outside the polygon, compute the minimum geodesic distance from the point to each polygon edge segment. If that distance is less than `buffer_m`, the point is within the buffer. This only needs to run when `buffer_m > 0` and the point is not already inside.

### Class: `ExclusionZoneSet`

```python
class ExclusionZoneSet:
    zones: list[ExclusionZone]
    redact_style: RedactStyle

    def is_excluded(self, point: Point) -> bool:
        """Return True if point falls inside any enabled zone."""
        return any(z.contains(z.point) for z in self.zones if z.enabled)

    def is_excluded_with_buffer(self, point: Point) -> bool:
        """Return True if point falls inside any enabled zone including buffer."""
        return any(z.contains_with_buffer(point) for z in self.zones if z.enabled)
```

### Class: `RedactStyle`

```python
@dataclass
class RedactStyle:
    fill_colour: tuple = (0, 0, 0, 255)
    show_label: bool = True
    label_text: str = "REDACTED"
```

### Function: `load_exclusion_zones()`

```python
def load_exclusion_zones(path: Path) -> ExclusionZoneSet:
    """Load and validate an exclusion zones JSON file.
    Raises ValueError on schema violations."""
```

Validation requirements:
- `version` must be 1
- Each zone must have `name`, `type`, and the fields required by its type
- Polygon vertices must have at least 3 points
- Circle radius must be positive
- Latitude in [-90, 90], longitude in [-180, 180]

### Sentinel: `NoExclusionZones`

```python
class NoExclusionZones:
    """Null object returned when no --exclusion-zones argument is provided."""
    def is_excluded(self, point) -> bool:
        return False
    def is_excluded_with_buffer(self, point) -> bool:
        return False
    redact_style = RedactStyle()
```

## Render Loop Integration

### Integration Point

The exclusion check operates in the main render loop in `bin/gopro-dashboard.py`, wrapping the existing `buffer.draw()` call. This is the correct level because exclusion must replace both the video frame AND the overlay.

Current render loop (line ~414 of `bin/gopro-dashboard.py`):

```python
for index, dt in enumerate(stepper.steps()):
    progress.update(index)
    draw_timer.time(lambda: buffer.draw(lambda frame: overlay.draw(dt, frame)))
```

Modified render loop:

```python
for index, dt in enumerate(stepper.steps()):
    progress.update(index)
    entry = frame_meta.get(dt)
    if entry.point and exclusion_zones.is_excluded_with_buffer(entry.point):
        draw_timer.time(lambda: buffer.draw(lambda frame: draw_redacted(frame, exclusion_zones.redact_style)))
    else:
        draw_timer.time(lambda: buffer.draw(lambda frame: overlay.draw(dt, frame)))
```

### Redacted Frame Rendering

A helper function `draw_redacted()` fills the frame with the configured colour and optionally draws centred "REDACTED" text:

```python
def draw_redacted(frame: Image.Image, style: RedactStyle):
    """Replace frame contents with a solid fill and optional label."""
    draw = ImageDraw.Draw(frame)
    draw.rectangle([0, 0, frame.width, frame.height], fill=style.fill_colour)
    if style.show_label:
        # Draw centred label text using the loaded font
        ...
```

This function lives in `gopro_overlay/exclusion.py`.

### GPS Lock Loss Handling

When the GPS position is `None` (lock lost), the system must decide whether to redact. The rule:

- Maintain a boolean `currently_in_exclusion_zone` state variable in the render loop
- When `entry.point is None`, use the previous state: if we were inside a zone, remain redacted
- When `entry.point` is available again, re-evaluate normally
- This prevents brief GPS dropouts from exposing frames that should be redacted

```python
in_zone = False
for index, dt in enumerate(stepper.steps()):
    entry = frame_meta.get(dt)
    if entry.point is not None:
        in_zone = exclusion_zones.is_excluded_with_buffer(entry.point)
    # else: in_zone retains its previous value
    if in_zone:
        buffer.draw(lambda frame: draw_redacted(frame, exclusion_zones.redact_style))
    else:
        buffer.draw(lambda frame: overlay.draw(dt, frame))
```

### Transition Buffering (Hysteresis)

The `buffer_m` field on each zone addresses transition frames. When approaching or leaving a zone:

- **Entering**: redaction begins when the position enters `zone + buffer_m`, before reaching the actual zone boundary
- **Leaving**: redaction continues until the position exits `zone + buffer_m`, after leaving the actual zone boundary

This provides a configurable safety margin. The default `buffer_m` is 0 (no buffer). A typical value would be 20-50 metres to account for GPS jitter at zone boundaries.

## CLI Integration

### New Argument

Add to the argument parser in `gopro_overlay/arguments.py`:

```python
parser.add_argument("--exclusion-zones", type=pathlib.Path,
                    help="JSON file defining geographic exclusion zones. "
                         "Video frames inside these zones are replaced with solid black.")
```

Place this adjacent to the existing `--privacy` argument.

### Loading in `bin/gopro-dashboard.py`

```python
if args.exclusion_zones:
    from gopro_overlay.exclusion import load_exclusion_zones
    exclusion_zones = load_exclusion_zones(assert_file_exists(args.exclusion_zones))
else:
    from gopro_overlay.exclusion import NoExclusionZones
    exclusion_zones = NoExclusionZones()
```

This goes after `args` is parsed and before the render loop, alongside the existing `--privacy` handling.

## Performance Considerations

### Frame Rate Context

The render loop generates one overlay frame every 0.1 seconds of video time. At 30fps output this means the exclusion check runs 10 times per second of video, not 30. This is already a favourable rate.

### Circle Check Cost

`Geodesic.WGS84.Inverse()` is a C-extension call. Benchmarks show it completes in ~5 microseconds per call. Even with 50 circle zones, the total per-frame cost is ~250 microseconds -- negligible compared to frame rendering (~10-50ms).

### Polygon Check Cost

Ray-casting is O(n) per polygon where n is the vertex count. For typical exclusion zones (4-20 vertices), this is sub-microsecond on the lat/lon plane. The buffer check (minimum distance to edges) is more expensive as it calls `Geodesic.WGS84.Inverse()` per edge, but it only runs when the point is outside the polygon and `buffer_m > 0`.

### Optimisation: Bounding Box Pre-filter

For each zone, precompute a lat/lon bounding box at load time. Before running the expensive geometry check, test whether the point falls within the bounding box (padded by `buffer_m` converted to approximate degrees). This is a simple four-comparison test that rejects the vast majority of frames immediately.

```python
class ExclusionZone:
    _bbox_min_lat: float
    _bbox_max_lat: float
    _bbox_min_lon: float
    _bbox_max_lon: float

    def _in_bbox(self, point: Point) -> bool:
        return (self._bbox_min_lat <= point.lat <= self._bbox_max_lat and
                self._bbox_min_lon <= point.lon <= self._bbox_max_lon)

    def contains(self, point: Point) -> bool:
        if not self._in_bbox(point):
            return False
        return self._contains_impl(point)
```

For the bounding box padding, use the approximation: 1 degree latitude ~ 111,320 metres. Longitude scaling varies by latitude but `111,320 * cos(lat)` is sufficient for padding purposes.

### Optimisation: Early Exit

`ExclusionZoneSet.is_excluded()` uses `any()` which short-circuits on the first matching zone. Order zones by likelihood of enclosing the current position (e.g., largest radius first, or by proximity to route centroid) if there are many zones. For typical use (2-5 zones) this is unnecessary.

## Editor Integration

### Scope

The exclusion zone editor is a panel/dialog within the existing `gopro-layout-editor.py`. It reuses the editor's existing tile-fetching infrastructure and GPX route display code.

### UI Location

Add an "Exclusion Zones" tab or a toolbar button that opens a dedicated editor panel. This panel contains:

1. **Zone List** - a `ttk.Treeview` listing all zones by name, type, and enabled state
2. **Map Canvas** - a larger tile canvas (512x512 or resizable) showing the route and all defined zones
3. **Zone Properties** - fields for editing the selected zone's name, type, geometry, buffer, and enabled state
4. **Drawing Tools** - buttons for "Add Circle" and "Add Polygon" drawing modes

### Map Canvas Behaviour

The map canvas reuses `_latlon_to_tile()` and `_build_tile_url()` to fetch and display OSM tiles. Zones are rendered as overlays on the tile image:

- **Circles**: drawn as ellipses, using `ImageDraw.ellipse()` with a semi-transparent fill. The pixel radius is computed from the map scale at the current zoom level.
- **Polygons**: drawn as filled polygons with `ImageDraw.polygon()` using a semi-transparent fill and a solid outline.
- **Route segments inside zones**: highlighted in a different colour (e.g., red dashed) to preview which parts will be redacted.

Multiple zoom levels should be loadable. The editor fetches a grid of tiles (e.g., 2x2 or 3x3) to provide enough context for zone drawing.

### Drawing Interactions

**Add Circle mode:**
1. User clicks "Add Circle" button
2. User clicks on the map canvas to set the centre point
3. User drags outward (or uses a radius input field) to set the radius
4. A name dialog prompts for the zone name
5. The zone is added to the list and drawn on the canvas

**Add Polygon mode:**
1. User clicks "Add Polygon" button
2. User clicks on the map canvas to add vertices sequentially
3. Double-click or press Enter to close the polygon
4. A name dialog prompts for the zone name
5. The zone is added to the list and drawn on the canvas

**Editing:**
- Select a zone in the list to highlight it on the map
- Drag the zone or its vertices to reposition
- Right-click context menu for "Delete Zone", "Edit Properties"
- The properties panel allows direct numeric editing of coordinates and radius

### File Operations

- **Load**: File > Open Exclusion Zones (or a dedicated button). Parses the JSON file using `load_exclusion_zones()` and populates the zone list and map overlay.
- **Save**: File > Save Exclusion Zones. Serialises the zone list back to JSON.
- **New**: Creates an empty zone set.

The editor stores the exclusion zones file path independently of the layout XML path.

### Coordinate Conversion in the Editor

The editor needs to convert between pixel coordinates on the canvas and lat/lon. The inverse of the tile projection is:

```python
def _pixel_to_latlon(px, py, bbox_min_lat, bbox_max_lat, bbox_min_lon, bbox_max_lon, canvas_w, canvas_h):
    lon = bbox_min_lon + (px / canvas_w) * (bbox_max_lon - bbox_min_lon)
    lat = bbox_max_lat - (py / canvas_h) * (bbox_max_lat - bbox_min_lat)
    return lat, lon
```

This reuses the same linear mapping that `_draw_route_on_tile()` already uses (with its `to_px()` helper), just inverted.

## Edge Cases

### Antimeridian Crossing

Zones that span the antimeridian (longitude +/-180) are not supported in version 1. This is documented as a known limitation. Users needing coverage near the antimeridian should define two adjacent zones, one on each side.

Rationale: antimeridian handling adds substantial complexity to both the ray-casting algorithm and bounding box pre-filter for a situation that affects very few users. It can be added in a future version by normalising longitudes or using a split-polygon approach.

### GPS Lock Lost While in Zone

Handled by the `in_zone` state variable as described in the render loop integration section. The previous exclusion state is maintained until a valid GPS fix re-evaluates the position.

### Multiple Overlapping Zones

Handled naturally by `any()` in `ExclusionZoneSet.is_excluded()`. If a point falls in any enabled zone, the frame is redacted. Zone names in the JSON must not be unique (though uniqueness is recommended for clarity).

### Empty Point Data

If `entry.point` is `None` from the start of the video (GPS not yet locked), the default `in_zone` state is `False` (not redacted). This is correct: if we have no position data, we cannot know whether we are in a zone, and the conservative choice is to show the frame. Users who need frames redacted before GPS lock should set `buffer_m` generously or use `--privacy` in combination.

### Zero-length Zones

A circle with radius 0 or a polygon with collinear vertices is valid but will never contain any point. The loader should accept these without error.

### Very Large Zones

No upper limit is imposed on zone size. A zone with a 50km radius is valid. The bounding box pre-filter handles performance for large zones that rarely enclose the current position.

## Testing Strategy

### Unit Tests for `gopro_overlay/exclusion.py`

- Circle containment: point inside, outside, on boundary
- Circle with buffer: point outside zone but within buffer
- Polygon containment: point inside, outside, on edge, on vertex
- Polygon with buffer: point outside polygon but within buffer distance of an edge
- Concave polygon: point inside concavity (outside polygon)
- Zone set with multiple zones: point in one, in none, in overlapping zones
- Disabled zone: point inside disabled zone returns False
- JSON loading: valid file, missing fields, wrong version, invalid coordinates
- Bounding box pre-filter: verify it does not produce false negatives

### Integration Tests

- Render loop with exclusion zones: verify redacted frames are solid fill
- GPS lock loss: verify state persistence
- No exclusion zones file: verify `NoExclusionZones` passthrough
- Combination with existing `--privacy` flag: both should work independently

## Summary of File Changes

| File | Change |
|------|--------|
| `gopro_overlay/exclusion.py` | New module (all zone logic) |
| `gopro_overlay/arguments.py` | Add `--exclusion-zones` argument |
| `bin/gopro-dashboard.py` | Load zones, integrate into render loop |
| `bin/gopro-layout-editor.py` | Exclusion zone editor panel |
| `tests/test_exclusion.py` | Unit tests for zone geometry and loading |
