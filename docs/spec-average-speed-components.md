# Specification: Average Speed and Average-Speed-While-Moving Components

## Overview

Add two new derived metrics to the overlay system:

- **avg_speed** -- Average speed over total elapsed time (total distance / total time). Updates every frame.
- **avg_speed_moving** -- Average speed excluding stopped periods. Only counts time when speed exceeds a configurable threshold.

Both metrics are displayed as pint Quantities in m/s internally, and rendered in the user's chosen speed unit via `--units-speed`.

---

## 1. Data Computation Approach

### Recommendation: Option B -- Post-processing step in `timeseries_process.py`

**Rationale:**

- The existing pipeline already follows this pattern: `calculate_speeds()`, `calculate_odo()`, `calculate_accel()`, `calculate_gradient()`, and `filter_locked()` are all defined in `timeseries_process.py` and applied as post-processing steps via `framemeta.process()` or `framemeta.process_deltas()`.
- Average speed depends on cumulative odometer distance (`codo`) and the frame's datetime relative to the first frame. The `codo` field is populated by `calculate_odo()` which itself runs as a `framemeta.process()` step. Running average speed calculation after `calculate_odo()` guarantees the required data is present.
- Option A (compute inside `timeseries_to_framemeta`) would only cover the GPX input path, missing the GoPro GPMD path entirely. Option C (on-the-fly in accessor lambdas) would recompute on every frame access and would require the accessor to hold mutable state or reference external accumulators, which breaks the stateless lambda pattern used by `metric_accessor_from()`.

### Why not Option A

`timeseries_to_framemeta()` in `framemeta_gpx.py` only applies to the GPX-to-framemeta conversion path. The primary GoPro GPMD path (`framemeta_gpmd.py`) builds entries differently. A post-processing step runs against the unified `FrameMeta` regardless of input source.

### Why not Option C

The accessor lambdas in `metric_accessor_from()` are pure functions of a single `Entry`. They have no access to the start time of the recording or to accumulated state. Injecting that state would require either closures with mutable external references or changes to the accessor signature, both of which break the existing pattern.

---

## 2. New Functions in `timeseries_process.py`

### `calculate_avg_speed()`

A single-entry processor (used with `framemeta.process()`). Maintains running totals of cumulative distance and elapsed time.

**Logic:**

1. Capture the datetime of the first entry as `start_dt` (set on first call).
2. On each entry:
   - `elapsed = entry.dt - start_dt` (in seconds).
   - `distance = entry.codo` (cumulative odometer, already in metres).
   - If `elapsed > 0`: `avg_speed = distance / elapsed` (result in m/s).
   - If `elapsed == 0`: `avg_speed = Quantity(0, mps)`.
3. Store as `{"avg_speed": avg_speed}`.

**Depends on:** Must run after `calculate_odo()` so that `entry.codo` is populated.

### `calculate_avg_speed_moving(moving_threshold)`

A single-entry processor (used with `framemeta.process()`). Maintains running totals of distance-while-moving and time-while-moving.

**Parameters:**

- `moving_threshold` -- a `pint.Quantity` in speed units (e.g., `Quantity(2, 'kph')`). Converted to m/s internally for comparison.

**Logic:**

1. Capture the datetime of the first entry as `prev_dt` (set on first call).
2. Maintain accumulators: `moving_distance = Quantity(0, m)`, `moving_time = Quantity(0, seconds)`.
3. On each entry:
   - `dt_delta = entry.dt - prev_dt` (in seconds).
   - Determine current speed: use `entry.speed` if available, else `entry.cspeed`, else `None`.
   - If current speed is not `None` and `current_speed > moving_threshold`:
     - `moving_time += dt_delta`
     - `moving_distance += entry.dist` (if `entry.dist` is not `None`).
   - If `moving_time > 0`: `avg_speed_moving = moving_distance / moving_time`.
   - If `moving_time == 0`: `avg_speed_moving = Quantity(0, mps)`.
   - Update `prev_dt = entry.dt`.
4. Store as `{"avg_speed_moving": avg_speed_moving}`.

**Depends on:** Must run after `calculate_speeds()` and `calculate_odo()` so that `entry.speed`, `entry.cspeed`, and `entry.dist` are populated.

**Alternative accumulation approach:** Instead of summing `entry.dist` segments (which may have gaps from GPS lock filtering), use `entry.codo` difference between the first moving frame and the current frame, but only counting the moving segments. The segment-based approach (summing `dist` when moving) is more accurate because it excludes distance that may have been recorded during brief speed spikes at traffic lights.

---

## 3. Entry Fields

Each `Entry` gains the following fields via `entry.update()` during processing:

| Field | Type | Unit | Description |
|---|---|---|---|
| `avg_speed` | `pint.Quantity` | m/s | Total distance / total elapsed time |
| `avg_speed_moving` | `pint.Quantity` | m/s | Distance-while-moving / time-while-moving |

These are accessed via `entry.avg_speed` and `entry.avg_speed_moving` through the existing `__getattr__` mechanism on `Entry`.

---

## 4. Metric Accessors

Add two entries to the `accessors` dict in `metric_accessor_from()` in `layout_xml.py` (around line 281):

```
"avg-speed": lambda e: e.avg_speed,
"avg-speed-moving": lambda e: e.avg_speed_moving,
```

These follow the same pattern as existing metrics. The hyphenated names match the XML attribute convention used throughout (e.g., `gps-dop`, `gps-lock`).

---

## 5. Unit Handling

Average speed values are stored in m/s (the internal canonical speed unit). The existing unit conversion system handles display conversion automatically:

- `<component type="metric" metric="avg-speed" units="speed" .../>` will convert m/s to the user's `--units-speed` setting.
- No new unit definitions are needed.
- The `units="speed"` attribute on metric/gauge/bar components triggers the standard speed unit conversion path.

---

## 6. Pipeline Integration

### In `bin/gopro-dashboard.py` (around line 288)

Add after the existing `calculate_odo()` call and after `filter_locked()`:

```
frame_meta.process(timeseries_process.calculate_avg_speed())
frame_meta.process(timeseries_process.calculate_avg_speed_moving(moving_threshold))
```

**Ordering matters.** The full pipeline order should be:

1. `calculate_speeds()` (via `process_deltas`)
2. `calculate_odo()` (via `process`)
3. `calculate_accel()` (via `process_accel`)
4. `calculate_gradient()` (via `process_deltas`)
5. `filter_locked()` (via `process`)
6. **`calculate_avg_speed()`** (via `process`) -- NEW
7. **`calculate_avg_speed_moving(moving_threshold)`** (via `process`) -- NEW

Running after `filter_locked()` ensures that entries with bad GPS lock have their speed/dist fields nulled, so they do not contribute to the moving average.

### In `bin/gopro-layout.py` (around line 97)

Same additions, same ordering.

### In `bin/gopro-to-csv.py` (around line 84)

Same additions if average speed is desired in CSV export.

### In `gopro_overlay/fake.py` (around line 128)

Add after `calculate_odo()` so that fake/test data includes the new fields.

---

## 7. Moving Threshold Configuration

### CLI Argument

Add `--moving-threshold` to the argument parser in `gopro_overlay/arguments.py`:

- **Name:** `--moving-threshold`
- **Default:** `2` (interpreted as km/h)
- **Type:** `float`
- **Help text:** `"Speed threshold for 'moving' detection in km/h. Speeds at or below this value are treated as stopped. Default: 2"`

The argument value is converted to a pint Quantity at the call site:

```
moving_threshold = units.Quantity(args.moving_threshold, 'kph')
```

### Why a CLI argument rather than a fixed default

Different use cases have different thresholds. Cycling might use 2 km/h, driving might use 5 km/h, and walking/hiking might use 0.5 km/h. A reasonable default (2 km/h) covers most cases while allowing override.

### Layout editor

The layout editor does not need to expose this threshold in the GUI. It is a data-processing parameter, not a per-component visual parameter. It applies globally to the entire telemetry processing pipeline.

---

## 8. Layout Editor Components

Add the following entries to `COMPONENT_DEFS` in `bin/gopro-layout-editor.py`:

### Text value components

**`avg_speed_value`** -- "Avg Speed"

```
("avg_speed_value", "Avg Speed", 150, 70, "#ff9944",
 '''    <composite x="{x}" y="{y}" width="{w}" height="{h}" name="avg_speed_value">
    <component type="text" x="0" y="0" size="{text_size}" rgb="{label_rgb}">AVG SPEED</component>
    <component type="metric" x="0" y="{value_y}" metric="avg-speed" units="speed" dp="1" size="{value_font_size}" rgb="{value_rgb}" />
</composite>''')
```

**`avg_speed_moving_value`** -- "Avg Moving Speed"

```
("avg_speed_moving_value", "Avg Moving Speed", 150, 70, "#ff7744",
 '''    <composite x="{x}" y="{y}" width="{w}" height="{h}" name="avg_speed_moving_value">
    <component type="text" x="0" y="0" size="{text_size}" rgb="{label_rgb}">AVG MOVING</component>
    <component type="metric" x="0" y="{value_y}" metric="avg-speed-moving" units="speed" dp="1" size="{value_font_size}" rgb="{value_rgb}" />
</composite>''')
```

### Gauge components

**`avg_speed_gauge`** -- "Avg Speed Gauge"

```
("avg_speed_gauge", "Avg Speed Gauge", 256, 256, "#ff9944",
 '''    <composite x="{x}" y="{y}" width="{w}" height="{h}" name="avg_speed_gauge">
    <component type="{gauge_style}" size="{gauge_size}" metric="avg-speed" units="kph" max="{gauge_max}" min="{gauge_min}" start="{gauge_start}" length="{gauge_length}" sectors="{gauge_sectors}" background-rgb="{gauge_bg}" needle-rgb="{gauge_needle}" major-tick-rgb="{gauge_tick}" minor-tick-rgb="{gauge_tick}" major-ann-rgb="{gauge_ann}" minor-ann-rgb="{gauge_ann}" tick-rgb="{gauge_tick}" gauge-rgb="{gauge_fill}"/>
</composite>''')
```

**`avg_speed_moving_gauge`** -- "Avg Moving Speed Gauge"

```
("avg_speed_moving_gauge", "Avg Moving Speed Gauge", 256, 256, "#ff7744",
 '''    <composite x="{x}" y="{y}" width="{w}" height="{h}" name="avg_speed_moving_gauge">
    <component type="{gauge_style}" size="{gauge_size}" metric="avg-speed-moving" units="kph" max="{gauge_max}" min="{gauge_min}" start="{gauge_start}" length="{gauge_length}" sectors="{gauge_sectors}" background-rgb="{gauge_bg}" needle-rgb="{gauge_needle}" major-tick-rgb="{gauge_tick}" minor-tick-rgb="{gauge_tick}" major-ann-rgb="{gauge_ann}" minor-ann-rgb="{gauge_ann}" tick-rgb="{gauge_tick}" gauge-rgb="{gauge_fill}"/>
</composite>''')
```

### Bar components

**`avg_speed_bar`** -- "Avg Speed Bar"

```
("avg_speed_bar", "Avg Speed Bar", 400, 30, "#ff9944",
 '''    <composite x="{x}" y="{y}" width="{w}" height="{h}" name="avg_speed_bar">
    <component type="bar" width="{w}" height="{h}" metric="avg-speed" units="kph" max="{gauge_max}" min="0" outline="255,255,255,128" fill="255,153,68,200"/>
</composite>''')
```

**`avg_speed_moving_bar`** -- "Avg Moving Speed Bar"

```
("avg_speed_moving_bar", "Avg Moving Speed Bar", 400, 30, "#ff7744",
 '''    <composite x="{x}" y="{y}" width="{w}" height="{h}" name="avg_speed_moving_bar">
    <component type="bar" width="{w}" height="{h}" metric="avg-speed-moving" units="kph" max="{gauge_max}" min="0" outline="255,255,255,128" fill="255,119,68,200"/>
</composite>''')
```

### Component options

No component-specific options are needed in `COMPONENT_OPTIONS` for these components. They use the same shared options (gauge style, colours, sizes) as existing speed/metric components, which are covered by `DEFAULT_COMPONENT_OPTIONS` and the shared gauge/bar field system.

---

## 9. GPX and XLSX Considerations

### Speed source consistency

The average speed calculations use `entry.codo` (cumulative odometer from `calculate_odo()`) and `entry.dist` (per-frame distance from `calculate_speeds()`). These are GPS-derived values computed from point-to-point geodesic distance, regardless of input format.

For the moving threshold check, the speed value is read from the entry using the same fallback as the `"speed"` accessor: `entry.speed` first (which comes from GPX speed extension or XLSX speed column), falling back to `entry.cspeed` (GPS-derived calculated speed).

This means:
- **GoPro GPMD:** Uses GPS-derived speed and distance. Consistent.
- **GPX with speed extension:** Moving detection uses the GPX speed value; distance uses geodesic calculation. Consistent with how the rest of the overlay works.
- **EUC World XLSX:** The `Speed [km/h]` column (wheel speed) is loaded as `entry.speed`. Moving detection uses wheel speed. Distance is still geodesic from GPS points. This is acceptable because wheel speed is the most accurate indicator of whether the rider is actually moving.

### No special handling needed

The existing data flow already ensures the correct speed source is used. No XLSX-specific or GPX-specific code paths are required.

---

## 10. Edge Cases

### Zero elapsed time (first frame)

When `elapsed == 0` (the very first frame), both `avg_speed` and `avg_speed_moving` should be set to `Quantity(0, mps)`. Do not divide by zero.

### All-stopped data

If the entire recording has speed below the moving threshold, `avg_speed_moving` remains `Quantity(0, mps)` for every frame. This is correct behaviour -- there is no moving average to report.

### First few frames before accumulation

`avg_speed` is valid from the second frame onward (once elapsed > 0). On the first frame it is 0. This is acceptable -- the value converges quickly as frames accumulate.

`avg_speed_moving` may remain 0 for an extended period if the recording starts while stopped (e.g., waiting at a traffic light). This is correct and expected.

### GPS lock loss

Frames where GPS lock is lost have their speed and distance fields nulled by `filter_locked()`. Since `calculate_avg_speed()` and `calculate_avg_speed_moving()` run after `filter_locked()`:

- `calculate_avg_speed()` uses `entry.codo` which stops incrementing during lock loss (because `calculate_odo()` skips null `dist` values). Elapsed time still advances. This means GPS lock loss periods slightly reduce the overall average, which is the correct conservative behaviour.
- `calculate_avg_speed_moving()` checks speed before accumulating. Null speed means the frame is not counted as moving. Distance is not accumulated. Both accumulators are unaffected. Correct.

### Interpolated entries

`Entry.interpolate()` will interpolate `avg_speed` and `avg_speed_moving` between two entries. Since average speed is a slowly-changing monotonic-ish value, linear interpolation produces reasonable results.

---

## 11. Testing

### Unit tests for `timeseries_process.py`

- Test `calculate_avg_speed()` with a sequence of entries having known `codo` values and timestamps. Verify the output `avg_speed` matches `total_distance / elapsed_time`.
- Test `calculate_avg_speed_moving()` with entries where some have speed below threshold. Verify that stopped frames do not contribute to moving time or moving distance.
- Test edge case: single entry (elapsed = 0) produces `avg_speed = 0`.
- Test edge case: all entries below threshold produces `avg_speed_moving = 0`.

### Integration test

- Use `gopro_overlay/fake.py` to generate a `FrameMeta` with the new processing steps. Verify that entries have `avg_speed` and `avg_speed_moving` fields populated.

---

## 12. Files Modified

| File | Change |
|---|---|
| `gopro_overlay/timeseries_process.py` | Add `calculate_avg_speed()` and `calculate_avg_speed_moving()` |
| `gopro_overlay/layout_xml.py` | Add `"avg-speed"` and `"avg-speed-moving"` to `metric_accessor_from()` |
| `gopro_overlay/arguments.py` | Add `--moving-threshold` CLI argument |
| `bin/gopro-dashboard.py` | Wire up new processing steps after `filter_locked()` |
| `bin/gopro-layout.py` | Wire up new processing steps |
| `bin/gopro-to-csv.py` | Wire up new processing steps (optional) |
| `bin/gopro-layout-editor.py` | Add 6 new entries to `COMPONENT_DEFS` |
| `gopro_overlay/fake.py` | Add processing steps for test data |
