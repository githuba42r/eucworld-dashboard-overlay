# EUC Overlay Components Reference

This document covers all EUC-specific overlay components added to the layout editor and XML layout system, plus supporting infrastructure (metric accessors, auto-scaling).

## Metric Accessors

Three metric accessors were added to `gopro_overlay/layout_xml.py` in the `metric_accessor_from` function:

| Metric name | Accessor | Unit |
|---|---|---|
| `battery` | `e.battery` | percent |
| `voltage` | `e.voltage` | volt |
| `current` | `e.current` | ampere |

These can be used in any XML layout element that accepts a `metric` attribute (e.g. `<component type="metric" metric="battery" .../>`, `<component type="chart" metric="voltage" .../>`, gauge components, bar components).

The values originate from GPX extensions or XLSX columns and are loaded with appropriate pint units (`units.percent`, `units.volt`, `units.ampere`).

---

## Value Displays

### battery_value -- Battery %

Displays the current battery percentage as a labelled numeric value.

**Default size:** 150 x 70 px | **Colour:** `#44bb44` | **Disabled by default**

**XML template:**
```xml
<composite x="{x}" y="{y}" width="{w}" height="{h}" name="battery_value">
    <component type="text" x="0" y="0" size="{text_size}" rgb="{label_rgb}">BATTERY</component>
    <component type="metric" x="0" y="{value_y}" metric="battery" dp="0" size="{value_font_size}" rgb="{value_rgb}" />
    <component type="text" x="{w}" y="{value_y}" size="{value_font_size}" rgb="{value_rgb}" align="right">%</component>
</composite>
```

**Configurable properties:**

| Property | Label | Type | Default |
|---|---|---|---|
| `value_font_size` | Value Font Size | spinbox | 32 (range 12-96, step 4) |
| `text_size` | Label Font Size | spinbox | 16 (range 8-48, step 2) |
| `value_y` | Value Y Offset | spinbox | 18 (range 0-100, step 2) |
| `label_rgb` | Label Colour (R,G,B) | colour_select | `255,255,255` |
| `value_rgb` | Value Colour (R,G,B) | colour_select | `255,255,255` |

**Auto-sizing:** Icon size = 91% of height, value font = 46% of height, label font = 23% of height, value_y derived from these.

---

### voltage_value -- Voltage

Displays the current pack voltage with one decimal place.

**Default size:** 150 x 70 px | **Colour:** `#bbbb44` | **Disabled by default**

**XML template:**
```xml
<composite x="{x}" y="{y}" width="{w}" height="{h}" name="voltage_value">
    <component type="text" x="0" y="0" size="{text_size}" rgb="{label_rgb}">VOLTAGE</component>
    <component type="metric" x="0" y="{value_y}" metric="voltage" dp="1" size="{value_font_size}" rgb="{value_rgb}" />
    <component type="text" x="{w}" y="{value_y}" size="{value_font_size}" rgb="{value_rgb}" align="right">V</component>
</composite>
```

**Configurable properties:** Same as battery_value.

**Auto-sizing:** Same rules as battery_value.

---

### current_value -- Current

Displays the current draw in amps with one decimal place.

**Default size:** 150 x 70 px | **Colour:** `#bb8844` | **Disabled by default**

**XML template:**
```xml
<composite x="{x}" y="{y}" width="{w}" height="{h}" name="current_value">
    <component type="text" x="0" y="0" size="{text_size}" rgb="{label_rgb}">CURRENT</component>
    <component type="metric" x="0" y="{value_y}" metric="current" dp="1" size="{value_font_size}" rgb="{value_rgb}" />
    <component type="text" x="{w}" y="{value_y}" size="{value_font_size}" rgb="{value_rgb}" align="right">A</component>
</composite>
```

**Configurable properties:** Same as battery_value.

**Auto-sizing:** Same rules as battery_value.

---

### power_value -- Power

Displays the current power consumption in watts (integer).

**Default size:** 150 x 70 px | **Colour:** `#bb4488` | **Disabled by default**

**XML template:**
```xml
<composite x="{x}" y="{y}" width="{w}" height="{h}" name="power_value">
    <component type="text" x="0" y="0" size="{text_size}" rgb="{label_rgb}">POWER</component>
    <component type="metric" x="0" y="{value_y}" metric="power" dp="0" size="{value_font_size}" rgb="{value_rgb}" />
    <component type="text" x="{w}" y="{value_y}" size="{value_font_size}" rgb="{value_rgb}" align="right">W</component>
</composite>
```

**Configurable properties:** Same as battery_value.

**Auto-sizing:** Same rules as battery_value.

---

## Charts

### battery_chart -- Battery Chart

A time-series chart of battery percentage.

**Default size:** 300 x 80 px | **Colour:** `#44bb44` | **Disabled by default**

**XML template:**
```xml
<composite x="{x}" y="{y}" name="battery_chart">
    <component type="chart" x="0" y="0" metric="battery" units="percent"
               width="{w}" height="{h}" filled="true" seconds="300"
               bg="0,0,0,170" fill="68,187,68,170" line="255,255,255,170"/>
</composite>
```

**Configurable properties:** None (uses component dimensions directly).

---

### voltage_chart -- Voltage Chart

A time-series chart of pack voltage.

**Default size:** 300 x 80 px | **Colour:** `#bbbb44` | **Disabled by default**

**XML template:**
```xml
<composite x="{x}" y="{y}" name="voltage_chart">
    <component type="chart" x="0" y="0" metric="voltage" units="volt"
               width="{w}" height="{h}" filled="true" seconds="300"
               bg="0,0,0,170" fill="187,187,68,170" line="255,255,255,170"/>
</composite>
```

**Configurable properties:** None.

---

### power_chart -- Power Chart

A time-series chart of power consumption.

**Default size:** 300 x 80 px | **Colour:** `#bb4488` | **Disabled by default**

**XML template:**
```xml
<composite x="{x}" y="{y}" name="power_chart">
    <component type="chart" x="0" y="0" metric="power" units="watt"
               width="{w}" height="{h}" filled="true" seconds="300"
               bg="0,0,0,170" fill="187,68,136,170" line="255,255,255,170"/>
</composite>
```

**Configurable properties:** None.

---

## Gauges

All gauge components share a common XML template structure and support four interchangeable gauge styles. Each gauge type has a different default style suited to its metric.

### Common Gauge Template

```xml
<composite x="{x}" y="{y}" width="{w}" height="{h}" name="{component_name}">
    <component type="{gauge_style}" size="{gauge_size}"
               metric="{metric}" units="{units}"
               max="{gauge_max}" min="{gauge_min}"
               start="{gauge_start}" length="{gauge_length}"
               sectors="{gauge_sectors}"
               {gauge_colour_attrs}/>
</composite>
```

### Gauge Styles

| Style | Description |
|---|---|
| `cairo-gauge-round-annotated` | Full circular gauge with background disc, needle, tick marks, and numeric annotations. |
| `cairo-gauge-arc-annotated` | Arc-shaped gauge (partial circle) with tick marks and annotations. No full background disc. |
| `cairo-gauge-donut` | Donut/ring gauge with a coloured arc fill and needle. |
| `cairo-gauge-marker` | Minimalist gauge with a marker indicator on a track. |

### Gauge Colour Attributes

The colour attributes generated depend on the selected style:

**cairo-gauge-round-annotated and cairo-gauge-arc-annotated:**
```
background-rgb="{gauge_bg}" needle-rgb="{gauge_needle}"
major-tick-rgb="{gauge_tick}" minor-tick-rgb="{gauge_tick}"
major-ann-rgb="{gauge_ann}" minor-ann-rgb="{gauge_ann}"
```

**cairo-gauge-donut:**
```
needle-rgb="{gauge_needle}"
major-tick-rgb="{gauge_tick}" minor-tick-rgb="{gauge_tick}"
major-ann-rgb="{gauge_ann}" minor-ann-rgb="{gauge_ann}"
```

**cairo-gauge-marker:**
```
tick-rgb="{gauge_tick}" background-rgb="{gauge_bg}"
gauge-rgb="{gauge_fill}"
```

### Gauge Auto-Sizing

`gauge_size` is set to `min(width, height)` of the component bounding box. When you resize a gauge component, the gauge diameter updates automatically.

### Auto-Scaling from Route Data

The `_auto_gauge_ranges` function scans the loaded route file (XLSX or GPX) and automatically sets `gauge_max` and `gauge_min` based on the actual data ranges. Manual overrides in custom_props always take precedence. The `_scan_route_ranges` function extracts min/max values for speed, battery, voltage, current, and power from the route file.

The auto-scaling rules per component:

| Component | gauge_min | gauge_max |
|---|---|---|
| speed_gauge, speed_bar | 0 | `ceil(max_speed * 1.1)` rounded up to nearest 10 |
| battery_gauge, battery_bar | 0 | 100 |
| voltage_gauge | `floor(min_voltage * 0.95)` rounded down to nearest 5 | `ceil(max_voltage * 1.05)` rounded up to nearest 5 |
| power_gauge | `floor(min(min_power, 0))` rounded down to nearest 100 | `ceil(max(max_power, 100))` rounded up to nearest 100 |

Default fallback values when no route data is available: speed_max=60, voltage_max=100, voltage_min=60, power_max=2000, power_min=-500.

---

### speed_gauge -- Speed Gauge

**Default size:** 256 x 256 px | **Colour:** `#ff6644` | **Disabled by default**

**Metric:** `speed` | **Units:** `kph` | **Default style:** `cairo-gauge-round-annotated`

**Configurable properties:**

| Property | Label | Type | Default |
|---|---|---|---|
| `gauge_style` | Gauge Style | combo | `cairo-gauge-round-annotated` |
| `gauge_size` | Size | spinbox | 256 (range 64-512, step 16) |
| `gauge_max` | Max Value | spinbox | 60 (range 10-300, step 5) |
| `gauge_min` | Min Value | spinbox | 0 (range -100 to 100, step 5) |
| `gauge_start` | Start Angle | spinbox | 143 (range 0-360, step 5) |
| `gauge_length` | Arc Length | spinbox | 254 (range 90-360, step 10) |
| `gauge_sectors` | Sectors | spinbox | 6 (range 2-20, step 1) |
| `gauge_bg` | Background (R,G,B,A) | colour_select | `255,255,255,150` |
| `gauge_needle` | Needle (R,G,B) | colour_select | `255,0,0` |
| `gauge_tick` | Tick Marks (R,G,B) | colour_select | `0,0,0` |
| `gauge_ann` | Annotations (R,G,B) | colour_select | `0,0,0` |
| `gauge_fill` | Gauge Fill (R,G,B) | colour_select | `0,191,255` |

---

### battery_gauge -- Battery Gauge

**Default size:** 256 x 256 px | **Colour:** `#44bb44` | **Disabled by default**

**Metric:** `battery` | **Units:** `percent` | **Default style:** `cairo-gauge-donut`

**Configurable properties:**

| Property | Label | Type | Default |
|---|---|---|---|
| `gauge_style` | Gauge Style | combo | `cairo-gauge-donut` |
| `gauge_size` | Size | spinbox | 256 (range 64-512, step 16) |
| `gauge_max` | Max Value (%) | spinbox | 100 (range 50-100, step 5) |
| `gauge_min` | Min Value (%) | spinbox | 0 (range 0-50, step 5) |
| `gauge_start` | Start Angle | spinbox | 90 (range 0-360, step 5) |
| `gauge_length` | Arc Length | spinbox | 270 (range 90-360, step 10) |
| `gauge_sectors` | Sectors | spinbox | 5 (range 2-20, step 1) |
| `gauge_bg` | Background (R,G,B,A) | colour_select | `255,255,255,150` |
| `gauge_needle` | Needle (R,G,B) | colour_select | `255,0,0` |
| `gauge_tick` | Tick Marks (R,G,B) | colour_select | `0,0,0` |
| `gauge_ann` | Annotations (R,G,B) | colour_select | `0,0,0` |
| `gauge_fill` | Gauge Fill (R,G,B) | colour_select | `0,191,255` |

---

### power_gauge -- Power Gauge

**Default size:** 256 x 256 px | **Colour:** `#bb4488` | **Disabled by default**

**Metric:** `power` | **Units:** `watt` | **Default style:** `cairo-gauge-arc-annotated`

**Configurable properties:**

| Property | Label | Type | Default |
|---|---|---|---|
| `gauge_style` | Gauge Style | combo | `cairo-gauge-arc-annotated` |
| `gauge_size` | Size | spinbox | 256 (range 64-512, step 16) |
| `gauge_max` | Max Power (W) | spinbox | 2000 (range 100-10000, step 100) |
| `gauge_min` | Min Power (W) | spinbox | -500 (range -5000 to 0, step 100) |
| `gauge_start` | Start Angle | spinbox | 150 (range 0-360, step 5) |
| `gauge_length` | Arc Length | spinbox | 240 (range 90-360, step 10) |
| `gauge_sectors` | Sectors | spinbox | 6 (range 2-20, step 1) |
| `gauge_bg` | Background (R,G,B,A) | colour_select | `255,255,255,150` |
| `gauge_needle` | Needle (R,G,B) | colour_select | `255,0,0` |
| `gauge_tick` | Tick Marks (R,G,B) | colour_select | `0,0,0` |
| `gauge_ann` | Annotations (R,G,B) | colour_select | `0,0,0` |
| `gauge_fill` | Gauge Fill (R,G,B) | colour_select | `0,191,255` |

---

### voltage_gauge -- Voltage Gauge

**Default size:** 256 x 256 px | **Colour:** `#bbbb44` | **Disabled by default**

**Metric:** `voltage` | **Units:** `volt` | **Default style:** `cairo-gauge-marker`

**Configurable properties:**

| Property | Label | Type | Default |
|---|---|---|---|
| `gauge_style` | Gauge Style | combo | `cairo-gauge-marker` |
| `gauge_size` | Size | spinbox | 256 (range 64-512, step 16) |
| `gauge_max` | Max Voltage (V) | spinbox | 100 (range 48-150, step 1) |
| `gauge_min` | Min Voltage (V) | spinbox | 60 (range 30-100, step 1) |
| `gauge_start` | Start Angle | spinbox | 150 (range 0-360, step 5) |
| `gauge_length` | Arc Length | spinbox | 240 (range 90-360, step 10) |
| `gauge_sectors` | Sectors | spinbox | 5 (range 2-20, step 1) |
| `gauge_bg` | Background (R,G,B,A) | colour_select | `255,255,255,150` |
| `gauge_needle` | Needle (R,G,B) | colour_select | `255,0,0` |
| `gauge_tick` | Tick Marks (R,G,B) | colour_select | `0,0,0` |
| `gauge_ann` | Annotations (R,G,B) | colour_select | `0,0,0` |
| `gauge_fill` | Gauge Fill (R,G,B) | colour_select | `0,191,255` |

---

## Bars

### speed_bar -- Speed Bar

A horizontal bar indicator for speed.

**Default size:** 400 x 30 px | **Colour:** `#ff8844` | **Disabled by default**

**XML template:**
```xml
<composite x="{x}" y="{y}" width="{w}" height="{h}" name="speed_bar">
    <component type="bar" width="{w}" height="{h}" metric="speed" units="kph"
               max="{gauge_max}" min="0"
               outline="255,255,255,128" fill="255,136,68,200"/>
</composite>
```

**Configurable properties:**

| Property | Label | Type | Default |
|---|---|---|---|
| `gauge_max` | Max Speed (kph) | spinbox | 60 (range 20-200, step 10) |

**Auto-scaling:** Same as speed_gauge -- max is derived from route data if available.

---

### battery_bar -- Battery Bar

A horizontal bar indicator for battery percentage.

**Default size:** 400 x 30 px | **Colour:** `#44bb44` | **Disabled by default**

**XML template:**
```xml
<composite x="{x}" y="{y}" width="{w}" height="{h}" name="battery_bar">
    <component type="bar" width="{w}" height="{h}" metric="battery" units="percent"
               max="100" min="0"
               outline="255,255,255,128" fill="68,187,68,200"/>
</composite>
```

**Configurable properties:** None (fixed 0-100% range).

---

## Other Components

### compass_display -- Compass

A compass rose showing current heading direction.

**Default size:** 256 x 256 px | **Colour:** `#6688cc` | **Disabled by default**

**XML template:**
```xml
<composite x="{x}" y="{y}" width="{w}" height="{h}" name="compass_display">
    <component type="compass" size="{gauge_size}"/>
</composite>
```

**Configurable properties:**

| Property | Label | Type | Default |
|---|---|---|---|
| `gauge_size` | Size | spinbox | 256 (range 64-512, step 16) |

**Auto-sizing:** `gauge_size` = `min(width, height)`.

---

### compass_arrow_display -- Compass Arrow

A compass arrow indicator showing current heading.

**Default size:** 256 x 256 px | **Colour:** `#4466aa` | **Disabled by default**

**XML template:**
```xml
<composite x="{x}" y="{y}" width="{w}" height="{h}" name="compass_arrow_display">
    <component type="compass-arrow" size="{gauge_size}"/>
</composite>
```

**Configurable properties:**

| Property | Label | Type | Default |
|---|---|---|---|
| `gauge_size` | Size | spinbox | 256 (range 64-512, step 16) |

**Auto-sizing:** `gauge_size` = `min(width, height)`.

---

### circuit_map -- Circuit Map

A Cairo-rendered circuit/track map showing the full route outline.

**Default size:** 256 x 256 px | **Colour:** `#66aa88` | **Disabled by default**

**XML template:**
```xml
<composite x="{x}" y="{y}" width="{w}" height="{h}" name="circuit_map">
    <component type="cairo-circuit-map" size="{gauge_size}"/>
</composite>
```

**Configurable properties:**

| Property | Label | Type | Default |
|---|---|---|---|
| `gauge_size` | Size | spinbox | 256 (range 64-512, step 16) |

**Auto-sizing:** `gauge_size` = `min(width, height)`.

---

### moving_journey_map -- Moving Journey Map

A map that shows the journey track and follows the current position, combining the features of both moving_map and journey_map.

**Default size:** 256 x 256 px | **Colour:** `#7766cc` | **Disabled by default**

**XML template:**
```xml
<component type="moving-journey-map" name="moving_journey_map"
           x="{x}" y="{y}" size="{map_size}"
           zoom="{map_zoom}" corner_radius="{map_corner_radius}"
           opacity="{map_opacity}"/>
```

**Configurable properties:**

| Property | Label | Type | Default |
|---|---|---|---|
| `map_zoom` | Zoom Level | slider | 16 (range 8-20) |
| `map_corner_radius` | Rounded Corners (0=off) | spinbox | 35 (range 0-128, step 5) |
| `map_opacity` | Opacity | slider_float | 0.7 (range 0.0-1.0) |

---

### asi_gauge -- Airspeed Indicator

An aviation-style airspeed indicator gauge.

**Default size:** 256 x 256 px | **Colour:** `#448888` | **Disabled by default**

**XML template:**
```xml
<composite x="{x}" y="{y}" width="{w}" height="{h}" name="asi_gauge">
    <component type="asi" size="{gauge_size}" metric="speed" units="kph"/>
</composite>
```

**Configurable properties:**

| Property | Label | Type | Default |
|---|---|---|---|
| `gauge_size` | Size | spinbox | 256 (range 64-512, step 16) |

**Auto-sizing:** `gauge_size` = `min(width, height)`.

---

### msi_gauge -- Motor Speed Indicator

A motor speed indicator gauge (variant 2).

**Default size:** 256 x 256 px | **Colour:** `#884488` | **Disabled by default**

**XML template:**
```xml
<composite x="{x}" y="{y}" width="{w}" height="{h}" name="msi_gauge">
    <component type="msi2" size="{gauge_size}" metric="speed" units="kph"/>
</composite>
```

**Configurable properties:**

| Property | Label | Type | Default |
|---|---|---|---|
| `gauge_size` | Size | spinbox | 256 (range 64-512, step 16) |

**Auto-sizing:** `gauge_size` = `min(width, height)`.
