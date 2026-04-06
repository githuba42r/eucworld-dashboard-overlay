# Heading Tape Widget - Implementation Specification

## Overview

A horizontal scrolling heading indicator, styled after aviation HUD heading tapes. The tape displays degree markings, cardinal/intercardinal labels, and tick marks that scroll horizontally as the heading changes. A fixed triangle marker at the centre indicates the current heading.

```
  250 ... 260 ... N ... 280 ... 290
                  v
```

## File Location

`gopro_overlay/widgets/heading_tape.py`

## Widget Class: `HeadingTape`

### Inheritance

Extends `Widget` from `gopro_overlay/widgets/widgets.py`.

### Constructor Signature

```python
class HeadingTape(Widget):

    def __init__(
        self,
        width: int,
        height: int,
        reading: Callable[[], Optional[float]],
        font: ImageFont,
        tick_interval: int = 10,
        bg: Tuple[int, ...] = (0, 0, 0),
        fg: Tuple[int, ...] = (255, 255, 255),
        marker_rgb: Tuple[int, ...] = (255, 0, 0),
        opacity: int = 180,
    ):
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `width` | int | (required) | Width of the tape strip in pixels |
| `height` | int | (required) | Height of the tape strip in pixels |
| `reading` | callable | (required) | Zero-arg callable returning current heading in degrees (float) or None |
| `font` | ImageFont | (required) | PIL font for degree numbers and cardinal labels |
| `tick_interval` | int | 10 | Degrees between minor tick marks |
| `bg` | tuple | (0,0,0) | Background colour (RGB) |
| `fg` | tuple | (255,255,255) | Foreground colour for ticks, numbers, and labels (RGB) |
| `marker_rgb` | tuple | (255,0,0) | Colour of the centre heading marker triangle (RGB) |
| `opacity` | int | 180 | Alpha value (0-255) for the background fill |

### Instance State for Caching

Follow the same caching pattern as `Compass` and `CompassArrow`: store `self.last_reading` and `self.image`, and only call `_redraw()` when the integer-rounded heading changes.

```python
self.last_reading = None
self.image = None
```

### Method: `draw(self, image: Image, draw: ImageDraw)`

Public entry point called by the layout engine.

1. Call `self.reading()` to get the current heading. If None, either skip drawing entirely or display a static "no data" state (dashes or empty tape).
2. Round heading to int for cache comparison.
3. If heading has changed since last frame (or first frame), call `self._redraw(heading)` and cache the result.
4. Composite the cached image onto the output: `image.alpha_composite(self.image, (0, 0))`.

### Method: `_redraw(self, heading: float) -> Image`

Internal method that produces the tape image for a given heading.

#### Drawing Algorithm

1. **Create RGBA image** of size `(width, height)`.

2. **Draw background rectangle** with the configured `bg` colour and `opacity` alpha. Optionally apply a 1-2px border in `fg` colour to visually frame the tape.

3. **Calculate the visible degree range.** The tape centre corresponds to the current heading. Define a `degrees_per_pixel` ratio that determines how many degrees of arc fit in the tape width. A sensible default is approximately `width / 3` total visible degrees (i.e., roughly 3 pixels per degree for a 400px-wide tape showing ~133 degrees). This ratio should feel readable without being too sparse.

   ```
   visible_degrees = width / pixels_per_degree
   start_deg = heading - visible_degrees / 2
   end_deg = heading + visible_degrees / 2
   ```

4. **Iterate through degree values** from `floor(start_deg)` to `ceil(end_deg)`, stepping by 1 degree (or by a smaller interval for sub-degree ticks if desired). For each degree value:

   a. **Normalise** the degree to 0-359 range using modulo: `norm = deg % 360`.

   b. **Calculate x position** relative to the tape:
      ```
      x = (deg - heading) * pixels_per_degree + width / 2
      ```
      Note: use the raw (unwrapped) `deg` value for position calculation, not the normalised value -- normalisation is only for label lookup.

   c. **Skip** if x falls outside `[0, width]`.

   d. **Determine tick type** based on normalised degree value:
      - **Major tick** (every 90 degrees: 0, 90, 180, 270): tallest tick, roughly `height * 0.5`. Draw the cardinal label (N, E, S, W) instead of a number.
      - **Intercardinal tick** (every 45 degrees: 45, 135, 225, 315): medium tick, roughly `height * 0.4`. Draw the intercardinal label (NE, SE, SW, NW).
      - **Numbered tick** (every `tick_interval` degrees, excluding cardinal/intercardinal positions): medium-short tick, roughly `height * 0.35`. Draw the degree number as text.
      - **Minor tick** (every degree or every 5 degrees, depending on resolution): short tick, roughly `height * 0.15`. No label.

   e. **Draw the tick line** from the top of the tape downward, centred at the calculated x.

   f. **Draw the label** (if any) below the tick, using `anchor="mt"` (middle-top) to centre horizontally on x.

5. **Draw the centre marker** -- a small downward-pointing filled triangle (inverted "V") at the bottom-centre of the tape, in `marker_rgb`. The triangle should be approximately `height * 0.2` tall and proportionally wide. Position it at `x = width / 2`.

6. **Return** the composed RGBA image.

#### Cardinal/Intercardinal Label Map

```python
LABELS = {
    0: "N", 45: "NE", 90: "E", 135: "SE",
    180: "S", 225: "SW", 270: "W", 315: "NW",
}
```

### Heading Wraparound (0/360 Boundary)

The critical edge case. When the heading is near 0 (or 360), the visible range spans across the boundary (e.g., 350 to 10).

The algorithm handles this naturally because:
- The iteration range uses raw (unwrapped) degree values, which can go below 0 or above 360.
- Only the label lookup normalises via `deg % 360`.
- The x-position formula uses the raw degree value relative to the current heading, so positions are continuous and correct across the boundary.

Example: heading = 5, visible range = -60 to +70. Degree -10 normalises to 350 for label lookup, but its x-position is correctly computed as `(-10 - 5) * ppd + w/2`.

### Missing Data Handling

When `self.reading()` returns `None`:
- Draw the background strip with border.
- Draw dashes ("---") centred on the tape in `fg` colour.
- Draw the centre marker in a dimmed version of `marker_rgb`.
- Cache this state so it is not redrawn every frame (use a sentinel like `self.last_reading = "none"`).

## XML Registration

### Component Type Name

`heading-tape` (maps to `create_heading_tape` via the existing `type.replace("-", "_")` convention in `component_type_of()`).

### Registration in `layout_xml.py`

Add a `create_heading_tape` method to the layout factory class, following existing patterns:

```python
@allow_attributes({"x", "y", "width", "height", "metric", "size", "tick-interval", "bg", "fg", "marker-rgb", "opacity"})
def create_heading_tape(self, element: ET.Element, entry, **kwargs) -> Widget:
    return HeadingTape(
        width=iattrib(element, "width", d=400),
        height=iattrib(element, "height", d=60),
        reading=lambda: nonesafe(entry().cog),  # default to cog; overridden by metric attr
        font=self._font(element, "size", d=16),
        tick_interval=iattrib(element, "tick-interval", d=10),
        bg=rgbattr(element, "bg", d=(0, 0, 0)),
        fg=rgbattr(element, "fg", d=(255, 255, 255)),
        marker_rgb=rgbattr(element, "marker-rgb", d=(255, 0, 0)),
        opacity=iattrib(element, "opacity", d=180),
    )
```

### Metric Attribute

The `metric` attribute should accept `"cog"` (default) or `"azi"` to select the heading data source. Use `metric_accessor_from()` + `nonesafe()` to resolve:

```python
accessor = metric_accessor_from(attrib(element, "metric", d="cog"))
reading = lambda: nonesafe(accessor(entry()))
```

### Required Import

Add to the imports at the top of `layout_xml.py`:

```python
from gopro_overlay.widgets.heading_tape import HeadingTape
```

### XML Attribute Reference

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `x`, `y` | int | 0 | Position (handled by parent composite) |
| `width` | int | 400 | Tape width in pixels |
| `height` | int | 60 | Tape height in pixels |
| `metric` | string | "cog" | Data source: "cog" or "azi" |
| `size` | int | 16 | Font size for labels and numbers |
| `tick-interval` | int | 10 | Degrees between numbered tick marks |
| `bg` | RGB | "0,0,0" | Background colour |
| `fg` | RGB | "255,255,255" | Foreground colour (ticks, text) |
| `marker-rgb` | RGB | "255,0,0" | Centre marker triangle colour |
| `opacity` | int | 180 | Background transparency (0=transparent, 255=opaque) |

## Layout Editor Integration

### Component Definition

Add to `COMPONENT_DEFS` in `bin/gopro-layout-editor.py`:

```python
("heading_tape", "Heading Tape", 400, 60, "#cc6644",
 '''    <composite x="{x}" y="{y}" width="{w}" height="{h}" name="heading_tape">
    <component type="heading-tape" width="{comp_width}" height="{comp_height}"/>
</composite>'''),
```

### Options Dialog

Add to `COMPONENT_OPTIONS` dict:

```python
"heading_tape": {
    "title": "Heading Tape Options",
    "fields": [
        ("comp_width", "Width", "spinbox", 400, (100, 800, 10)),
        ("comp_height", "Height", "spinbox", 60, (30, 120, 5)),
        ("font_size", "Font Size", "spinbox", 16, (8, 48, 2)),
        ("tick_interval", "Tick Interval", "spinbox", 10, (5, 45, 5)),
        ("opacity", "Opacity", "spinbox", 180, (0, 255, 10)),
    ],
},
```

### Default Position and Visibility

Add the heading tape to:
- The default position map (e.g., top-centre of the frame).
- The default enabled set, or leave it disabled by default if the component set is already crowded.
- The `_gauge_names` set is NOT appropriate for this widget since it is not square. It should use `comp_width`/`comp_height` rather than `gauge_size`.

### XML Template Variable Expansion

The heading tape's XML template must pass `comp_width` and `comp_height` through to the `width` and `height` attributes of the `<component>` element. Add the appropriate format logic in the template expansion section of the editor so that these custom properties propagate correctly (similar to how `gauge_size` is handled for gauge components).

## XML Configuration Examples

### Minimal (all defaults)

```xml
<component type="heading-tape"/>
```

Produces a 400x60px tape using course-over-ground, white on black, 180 alpha background.

### Custom Dimensions and Colour

```xml
<component type="heading-tape" width="600" height="80" size="20"
           bg="20,20,40" fg="0,255,0" marker-rgb="255,255,0" opacity="200"/>
```

A wider, taller tape with a dark blue background, green text, and yellow marker.

### Using Azimuth Instead of COG

```xml
<component type="heading-tape" metric="azi" width="500" height="50"/>
```

### Compact HUD Style

```xml
<component type="heading-tape" width="300" height="40" size="12"
           tick-interval="5" bg="0,0,0" fg="0,255,0" marker-rgb="0,255,0" opacity="128"/>
```

Small green-on-black tape with tighter tick spacing, low opacity -- suitable for a flight-sim HUD aesthetic.

### Positioned Within a Composite

```xml
<composite x="200" y="10" width="600" height="80">
    <component type="heading-tape" width="600" height="80" size="18"
               fg="255,255,255" marker-rgb="255,80,80"/>
</composite>
```

## Edge Cases and Considerations

1. **Heading wraparound at 0/360**: Handled by iterating over raw (unwrapped) degree values and normalising only for label lookup. See "Heading Wraparound" section above.

2. **Missing data (None reading)**: Display a dashed placeholder and dimmed marker. Cache this state.

3. **Very small widget sizes**: At small `width` values (e.g., < 150px), there may not be room for many labels. The algorithm naturally handles this -- labels that fall outside the visible range are simply not drawn. At very small sizes, consider whether the font size should be clamped or a minimum width enforced.

4. **Large tick intervals**: If `tick_interval` exceeds half the visible degree range, very few or no numbered ticks will appear. This is acceptable -- the cardinal labels at 0/90/180/270 still provide orientation.

5. **Font sizing**: The font must fit within the tape height alongside the tick marks. The tick marks occupy roughly the top half of the tape, and labels the bottom half. If the font is too large relative to height, labels will be clipped. No runtime enforcement is needed -- the user controls both `size` and `height`.

6. **Fractional headings**: The `reading()` callable may return a float. The cache key should be rounded to integer precision (matching the existing compass widgets' approach) to avoid excessive redraws for sub-degree changes.

7. **Performance**: The tape is redrawn only when the integer-rounded heading changes, matching the caching strategy of `Compass` and `CompassArrow`. Each redraw creates a new RGBA image and composites it, which is consistent with the project's existing approach.

## Testing

Unit tests should cover:
- Instantiation with default and custom parameters.
- `_redraw()` produces an image of the correct dimensions.
- Wraparound: headings near 0 and 360 produce correct label positions.
- None reading produces a valid (placeholder) image.
- Cache behaviour: identical readings do not trigger redraws.
