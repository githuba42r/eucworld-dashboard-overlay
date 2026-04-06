# Unit Test Specification — Fork New Features

This document specifies unit tests for all new features added in this fork. Tests follow the conventions established by the existing suite:

- **Framework**: pytest (plain functions, no unittest classes except where grouping helps — see `TestWidth`, `TestCaching` patterns in `test_widgets_chart_unit.py`)
- **Assertions**: plain `assert`, `pytest.approx` for floats, `pytest.raises` for exceptions
- **Visual/approval tests**: `@pytest.mark.gfx` + `@approve_image` decorator, returning an Image
- **Unit tests**: no decorator, no image return — just assert on values
- **Helpers**: `datetime_of(epoch)` from `test_timeseries`, `Entry(...)` from `gopro_overlay.entry`/`gopro_overlay.timeseries`, `units` from `gopro_overlay.units`, `load_test_font()` from `font.py`
- **No mocking framework used**: the codebase uses lambdas and simple callables as test doubles

---

## 1. HeadingTape Widget

**File**: `tests/widgets/test_widgets_heading_tape.py`

**Fixtures / setup**:
```python
from PIL import Image, ImageDraw
from font import load_test_font
from gopro_overlay.widgets.heading_tape import HeadingTape

font = load_test_font().font_variant(size=16)

def draw_tape(tape, w=400, h=60):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    tape.draw(img, draw)
    return img
```

### Tests (unit — no `@pytest.mark.gfx`)

| Function name | What it verifies | Priority |
|---|---|---|
| `test_construction_defaults` | HeadingTape can be constructed with only required args (width, height, reading, font); attributes match defaults (visible_range=90, label_interval=30, etc.) | critical |
| `test_visible_range_clamped_to_minimum` | `visible_range=5` is stored as 10 (the minimum) | important |
| `test_draw_with_valid_heading` | `draw()` with `reading=lambda: 90.0` produces an image without error; image has non-zero alpha pixels (something was drawn) | critical |
| `test_draw_heading_north_zero` | `reading=lambda: 0.0` — no crash, image produced | critical |
| `test_draw_heading_360_wraps_to_0` | `reading=lambda: 360.0` — functionally identical to 0; cached image reused if called again with 0 | important |
| `test_draw_heading_negative_wraps` | `reading=lambda: -10.0` — no crash (negative values are valid; the modulo in _redraw handles them) | important |
| `test_draw_none_heading_shows_placeholder` | `reading=lambda: None` — draws "---" placeholder; image produced | critical |
| `test_caching_same_heading_reuses_image` | Two consecutive `draw()` calls with same heading reuse the same image object (`id()` equality) | important |
| `test_caching_different_heading_rebuilds` | Heading changes from 90 to 180 — image object is different | important |
| `test_caching_none_to_value_rebuilds` | Transition from None to a heading value — image changes | important |
| `test_caching_value_to_none_rebuilds` | Transition from heading value to None — switches to placeholder | important |
| `test_show_values_false_suppresses_numeric_labels` | With `show_values=False`, only cardinal/intercardinal labels are drawn (verify by checking that numeric degree text is absent — check pixel content at expected label positions, or just verify no crash) | nice-to-have |
| `test_custom_colours` | Custom `bg`, `fg`, `marker_rgb` — no crash, image produced | nice-to-have |

### Approval tests (with `@pytest.mark.gfx` + `@approve_image`)

| Function name | What it verifies | Priority |
|---|---|---|
| `test_render_heading_tape_north` | Visual: tape centered on N (0) | nice-to-have |
| `test_render_heading_tape_east` | Visual: tape centered on E (90) | nice-to-have |
| `test_render_heading_tape_no_data` | Visual: placeholder "---" display | nice-to-have |

---

## 2. Average Speed Processing

**File**: `tests/test_timeseries.py` (append to existing file — matches existing `test_process_*` patterns)

**Fixtures / setup**: Uses existing `datetime_of`, `metres`, `Entry`, `Timeseries`, `units`.

### Tests

| Function name | What it verifies | Priority |
|---|---|---|
| `test_calculate_avg_speed_basic` | Two entries with known dist/time produce correct running average. Create Timeseries with 3 entries, process with `calculate_avg_speed()`, verify `avg_speed` on each entry. | critical |
| `test_calculate_avg_speed_first_frame_zero` | First entry has elapsed=0 so avg_speed should be `0 mps` | critical |
| `test_calculate_avg_speed_no_dist` | Entries with `dist=None` — total_dist stays 0, avg_speed is 0 | important |
| `test_calculate_avg_speed_accumulates` | Three entries with dist 10m, 20m, 30m at 1s intervals — avg_speed at entry[2] = 30m / 2s = 15 m/s | critical |
| `test_calculate_avg_speed_moving_basic` | Entries above threshold contribute to moving_time; entries below do not. Verify avg_speed_moving reflects only moving time. | critical |
| `test_calculate_avg_speed_moving_all_stopped` | All entries below threshold — avg_speed_moving = 0 | important |
| `test_calculate_avg_speed_moving_custom_threshold` | Threshold of 5.0 m/s — entries at 4.9 are stopped, entries at 5.1 are moving | important |
| `test_calculate_avg_speed_moving_uses_cspeed_fallback` | When `speed` is None but `cspeed` is set, uses cspeed | important |
| `test_calculate_avg_speed_moving_first_frame` | First entry — no last_dt so no moving_time increment; avg_speed_moving = 0 | important |

### Data pattern for avg_speed tests

```python
from gopro_overlay.timeseries_process import calculate_avg_speed, calculate_avg_speed_moving

ts = Timeseries()
ts.add(
    Entry(datetime_of(1), point=Point(51.50186, -0.14056), dist=metres(0)),
    Entry(datetime_of(2), point=Point(51.50186, -0.14056), dist=metres(100),
          speed=units.Quantity(10, units.mps)),
    Entry(datetime_of(3), point=Point(51.50186, -0.14056), dist=metres(200),
          speed=units.Quantity(20, units.mps)),
)
ts.process(calculate_avg_speed())
# entry at t=1: avg_speed = 0 (first frame, elapsed=0)
# entry at t=2: avg_speed = 100m / 1s = 100 m/s
# entry at t=3: avg_speed = 300m / 2s = 150 m/s
```

---

## 3. GPX Preprocessing and XLSX Loading

**File**: `tests/test_gpx.py` (append to existing file)

### `_preprocess_gpx()` tests

| Function name | What it verifies | Priority |
|---|---|---|
| `test_preprocess_gpx_euc_world_speed_relocated` | XML with `<speed>36</speed>` as direct child of `<trkpt>` is relocated into `<extensions><gpxtpx:TrackPointExtension><gpxtpx:speed>10.00</gpxtpx:speed>` (36 km/h = 10 m/s) | critical |
| `test_preprocess_gpx_speed_conversion_kmh_to_mps` | Speed value is converted from km/h to m/s (divide by 3.6) | critical |
| `test_preprocess_gpx_no_change_when_already_in_extensions` | XML where speed is already inside TrackPointExtension is not modified | critical |
| `test_preprocess_gpx_no_speed_element_unchanged` | XML with no `<speed>` element is returned unchanged | important |
| `test_preprocess_gpx_zero_speed` | `<speed>0</speed>` converts to `0.00 m/s` | important |

### `load_xml()` with new fields

| Function name | What it verifies | Priority |
|---|---|---|
| `test_load_xml_battery_voltage_current` | GPX XML with `<battery>85</battery>`, `<voltage>67.2</voltage>`, `<current>5.1</current>` in extensions parses correctly with units (percent, volt, ampere) | critical |
| `test_load_xml_battery_none_when_absent` | Standard GPX without battery/voltage/current fields returns None for those | important |

### `load_xlsx()` tests

| Function name | What it verifies | Priority |
|---|---|---|
| `test_load_xlsx_basic` | Load a minimal XLSX fixture with required columns (GPS Latitude, GPS Longitude, Date & Time) and optional columns (Speed, Battery, Voltage, Current). Verify returned list of GPX namedtuples has correct values with units. | critical |
| `test_load_xlsx_missing_required_columns` | XLSX without lat/lon/time raises IOError with descriptive message | critical |
| `test_load_xlsx_speed_converted_to_mps` | Speed [km/h] column value of 36.0 yields speed = 10.0 m/s | critical |
| `test_load_xlsx_missing_openpyxl` | When openpyxl is not importable, raises ImportError with helpful message | nice-to-have |

### XLSX test fixture

Create a minimal XLSX fixture at `tests/gpx/test_euc.xlsx` using openpyxl in a one-time setup, or create a conftest fixture:

```python
@pytest.fixture
def xlsx_path(tmp_path):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["GPS Latitude [°]", "GPS Longitude [°]", "Date & Time",
               "GPS Altitude [m]", "Speed [km/h]", "Battery [%]",
               "Voltage [V]", "Current [A]", "Power [W]"])
    ws.append([51.5, -0.14, "2024-01-01 12:00:00", 100.0, 36.0, 85.0, 67.2, 5.1, 340.0])
    ws.append([51.501, -0.141, "2024-01-01 12:00:01", 101.0, 72.0, 84.0, 66.8, 10.2, 680.0])
    path = tmp_path / "test.xlsx"
    wb.save(path)
    return path
```

---

## 4. Metric Accessors

**File**: `tests/layout/test_layout_xml.py` (append to existing file)

Follows the exact pattern of existing `test_metric_accessor_speed`, `test_metric_accessor_gears`, etc.

| Function name | What it verifies | Priority |
|---|---|---|
| `test_metric_accessor_battery` | `metric_accessor_from("battery")(entry)` returns the battery quantity | critical |
| `test_metric_accessor_voltage` | `metric_accessor_from("voltage")(entry)` returns the voltage quantity | critical |
| `test_metric_accessor_current` | `metric_accessor_from("current")(entry)` returns the current quantity | critical |
| `test_metric_accessor_avg_speed` | `metric_accessor_from("avg-speed")(entry)` returns the avg_speed quantity | critical |
| `test_metric_accessor_avg_speed_moving` | `metric_accessor_from("avg-speed-moving")(entry)` returns the avg_speed_moving quantity | critical |
| `test_metric_accessor_battery_none` | Entry without battery attribute returns None | important |

### Data pattern

```python
def test_metric_accessor_battery():
    battery = units.Quantity(85, units.percent)
    entry = Entry(datetime_of(0), battery=battery)
    assert metric_accessor_from("battery")(entry) == battery

def test_metric_accessor_avg_speed():
    avg = units.Quantity(15, units.mps)
    entry = Entry(datetime_of(0), avg_speed=avg)
    assert metric_accessor_from("avg-speed")(entry) == avg
```

---

## 5. Layout XML Changes

**File**: `tests/layout/test_layout_xml.py` (append) and `tests/layout/test_layout.py` (for integration)

### Frame validation

| Function name | What it verifies | Priority |
|---|---|---|
| `test_frame_missing_width_raises_valueerror` | XML `<frame name="test"><component ... /></frame>` without width/height raises ValueError mentioning the frame name | critical |
| `test_frame_with_dimensions_ok` | XML `<frame name="test" width="100" height="50">...` parses without error | critical |

### Composite width/height

| Function name | What it verifies | Priority |
|---|---|---|
| `test_composite_allows_width_height_attributes` | XML `<composite x="0" y="0" width="400" height="300">` parses without "unexpected attribute" error | important |

### HeadingTape component

| Function name | What it verifies | Priority |
|---|---|---|
| `test_heading_tape_element_parsed` | XML `<component type="heading-tape" metric="cog" width="400" height="60"/>` produces a widget without error | critical |
| `test_heading_tape_default_metric` | When `metric` attribute is omitted, defaults to "cog" | important |
| `test_heading_tape_custom_attributes` | `visible-range`, `label-interval`, `show-values`, `bg`, `fg`, `marker-rgb`, `opacity` are accepted | important |

---

## 6. `as_reading` Fix

**File**: `tests/layout/test_layout_xml_cairo.py` (append to existing file)

| Function name | What it verifies | Priority |
|---|---|---|
| `test_as_reading_zero_to_one` | `as_reading(lambda: 50, 0, 100)` returns Reading with value 0.5 | critical |
| `test_as_reading_at_min` | `as_reading(lambda: 0, 0, 100)` returns Reading(0.0) | critical |
| `test_as_reading_at_max` | `as_reading(lambda: 100, 0, 100)` returns Reading(1.0) | critical |
| `test_as_reading_negative_value_regen` | `as_reading(lambda: -20, -50, 100)` returns Reading((-20 - -50) / 150) = Reading(0.2) | critical |
| `test_as_reading_min_not_zero` | `as_reading(lambda: 60, 20, 120)` returns Reading((60-20)/100) = Reading(0.4) | critical |
| `test_as_reading_zero_range_clamps` | `as_reading(lambda: 5, 5, 5)` — range is max(0,1)=1, returns Reading((5-5)/1) = Reading(0.0) — no division by zero | important |

### Data pattern

```python
from gopro_overlay.layout_xml_cairo import as_reading

def test_as_reading_zero_to_one():
    r = as_reading(lambda: 50, 0, 100)
    assert r().value == pytest.approx(0.5)

def test_as_reading_negative_value_regen():
    r = as_reading(lambda: -20, -50, 100)
    assert r().value == pytest.approx(0.2)
```

---

## 7. Chart Label Positioning

**File**: `tests/widgets/test_widgets_chart_unit.py` (append to existing file)

| Function name | What it verifies | Priority |
|---|---|---|
| `test_labels_rendered_at_right_side` | Chart with `font` and known view data — verify label text is positioned on the right portion of the chart image (check pixel content in rightmost region is non-transparent) | nice-to-have |

This is a visual behaviour change that is better covered by approval tests than unit assertions. Low priority for unit testing.

---

## 8. CLI Arguments

**File**: `tests/test_arguments.py` (append to existing file)

Follows the exact pattern of existing `test_input_output`, `test_overlay_size`, etc.

| Function name | What it verifies | Priority |
|---|---|---|
| `test_xlsx_argument` | `do_args("--xlsx", "data.xlsx")` — `args.xlsx == Path("data.xlsx")` | critical |
| `test_xlsx_default_none` | `do_args()` — `args.xlsx is None` | critical |
| `test_gpx_time_offset_default` | `do_args()` — `args.gpx_time_offset == 0.0` | critical |
| `test_gpx_time_offset_positive` | `do_args("--gpx-time-offset", "30.5")` — `args.gpx_time_offset == 30.5` | critical |
| `test_gpx_time_offset_negative` | `do_args("--gpx-time-offset", "-15")` — `args.gpx_time_offset == -15.0` | important |
| `test_sample_duration_default_none` | `do_args()` — `args.sample_duration is None` | critical |
| `test_sample_duration_set` | `do_args("--sample-duration", "60")` — `args.sample_duration == 60.0` | critical |
| `test_moving_threshold_default` | `do_args()` — `args.moving_threshold == 2.0` | critical |
| `test_moving_threshold_custom` | `do_args("--moving-threshold", "5.0")` — `args.moving_threshold == 5.0` | important |

---

## 9. Layout Editor (`bin/gopro-layout-editor.py`)

**File**: `tests/test_layout_editor.py` (new file)

The layout editor is a standalone GUI tool. Testing focuses on the pure functions that can be exercised without Tk or a running display.

**Setup note**: Tests import directly from `bin/gopro-layout-editor.py`. If that's not on the path, use `importlib` or add to `sys.path`.

| Function name | What it verifies | Priority |
|---|---|---|
| `test_generate_layout_xml_minimal` | `generate_layout_xml()` with minimal config produces valid XML with root `<layout>` element | critical |
| `test_generate_layout_xml_has_components` | Generated XML contains expected component types (e.g. `<component type="metric" ... />`) for each enabled gauge | critical |
| `test_auto_font_sizes_scales_with_resolution` | `_auto_font_sizes(1920, 1080)` returns larger sizes than `_auto_font_sizes(640, 480)` | important |
| `test_auto_gauge_ranges_with_route_data` | `_auto_gauge_ranges()` with known min/max route data produces sensible ranges (speed_max > speed_min, etc.) | important |
| `test_gauge_colour_attrs_per_style` | `_gauge_colour_attrs("dark")` returns different colours than `_gauge_colour_attrs("light")` | important |
| `test_load_layout_xml_roundtrip` | `generate_layout_xml()` output can be parsed by `load_layout_xml()` without error | critical |
| `test_scan_route_ranges_from_xlsx` | `_scan_route_ranges()` with a test XLSX file returns a dict with speed, battery, voltage, current ranges | important |
| `test_preprocess_gpx_integration` | Full round-trip: EUC World GPX with `<speed>` in km/h -> preprocess -> load -> verify speed in m/s | important |

**Priority note**: These tests depend on the layout editor's internal functions being importable. If the editor is tightly coupled to Tk, some of these may need refactoring to extract pure logic. Mark as `pytest.mark.skipif` if Tk is unavailable.

---

## Implementation Priority

### Phase 1 — Critical (must have before merge)

1. `as_reading` fix tests (6) — validates a bug fix in gauge rendering
2. Average speed processing tests (9) — core data pipeline
3. CLI argument tests (9) — ensures new args don't break existing parsing
4. Metric accessor tests (6) — ensures new metrics are wired correctly
5. HeadingTape construction + draw tests (7) — new widget correctness

### Phase 2 — Important (should have)

6. GPX preprocessing tests (5) — EUC World compatibility
7. XLSX loading tests (4) — new data source
8. Layout XML frame validation and heading-tape parsing tests (6)

### Phase 3 — Nice to have

9. HeadingTape approval/visual tests (3)
10. Chart label positioning (1)
11. Layout editor pure function tests (8)

---

## Running Tests

```bash
# All unit tests (excluding visual/approval tests)
pytest tests/ -m "not gfx" -v

# Specific new test file
pytest tests/widgets/test_widgets_heading_tape.py -v

# With coverage for changed modules
pytest tests/ -m "not gfx" --cov=gopro_overlay.widgets.heading_tape --cov=gopro_overlay.timeseries_process --cov=gopro_overlay.gpx --cov=gopro_overlay.layout_xml --cov=gopro_overlay.layout_xml_cairo --cov=gopro_overlay.arguments -v
```
