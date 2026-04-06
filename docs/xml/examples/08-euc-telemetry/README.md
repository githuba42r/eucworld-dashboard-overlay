# EUC Telemetry Components

These components are available when using EUC World data (via `--xlsx` or GPX with EUC extensions).

## Metrics

Three new metrics are available for use in `<component type="metric">` and `<component type="chart">`:

| Metric | Unit | Description |
|--------|------|-------------|
| `battery` | percent | Battery state of charge (%) |
| `voltage` | volt | Battery voltage (V) |
| `current` | ampere | Motor current draw (A, negative = regen) |

Power is available via the existing `power` metric (watts).

## Value Displays

Show instantaneous EUC telemetry values with label and unit.

### Battery Percentage

```xml
<composite x="100" y="100" width="150" height="70" name="battery_value">
    <component type="text" x="0" y="0" size="16" rgb="255,255,255">BATTERY</component>
    <component type="metric" x="0" y="32" metric="battery" dp="0" size="32" rgb="255,255,255" />
    <component type="text" x="150" y="32" size="32" rgb="255,255,255" align="right">%</component>
</composite>
```

### Voltage

```xml
<composite x="100" y="180" width="150" height="70" name="voltage_value">
    <component type="text" x="0" y="0" size="16" rgb="255,255,255">VOLTAGE</component>
    <component type="metric" x="0" y="32" metric="voltage" dp="1" size="32" rgb="255,255,255" />
    <component type="text" x="150" y="32" size="32" rgb="255,255,255" align="right">V</component>
</composite>
```

### Current

```xml
<composite x="100" y="260" width="150" height="70" name="current_value">
    <component type="text" x="0" y="0" size="16" rgb="255,255,255">CURRENT</component>
    <component type="metric" x="0" y="32" metric="current" dp="1" size="32" rgb="255,255,255" />
    <component type="text" x="150" y="32" size="32" rgb="255,255,255" align="right">A</component>
</composite>
```

### Power

```xml
<composite x="100" y="340" width="150" height="70" name="power_value">
    <component type="text" x="0" y="0" size="16" rgb="255,255,255">POWER</component>
    <component type="metric" x="0" y="32" metric="power" dp="0" size="32" rgb="255,255,255" />
    <component type="text" x="150" y="32" size="32" rgb="255,255,255" align="right">W</component>
</composite>
```

## Time-Series Charts

Show rolling charts of EUC telemetry over a time window.

### Battery Chart

```xml
<composite x="300" y="100" name="battery_chart">
    <component type="chart" x="0" y="0" metric="battery" units="percent"
               width="400" height="80" filled="true" seconds="300"
               bg="0,0,0,170" fill="68,187,68,170" line="255,255,255,170"/>
</composite>
```

### Voltage Chart

```xml
<composite x="300" y="200" name="voltage_chart">
    <component type="chart" x="0" y="0" metric="voltage" units="volt"
               width="400" height="80" filled="true" seconds="300"
               bg="0,0,0,170" fill="187,187,68,170" line="255,255,255,170"/>
</composite>
```

### Power Chart

```xml
<composite x="300" y="300" name="power_chart">
    <component type="chart" x="0" y="0" metric="power" units="watt"
               width="400" height="80" filled="true" seconds="300"
               bg="0,0,0,170" fill="187,68,136,170" line="255,255,255,170"/>
</composite>
```

## Gauges

EUC telemetry can be displayed as gauges. Four gauge styles are available:

| Style | Type Name | Description |
|-------|-----------|-------------|
| Round | `cairo-gauge-round-annotated` | Speedometer-style circular gauge |
| Arc | `cairo-gauge-arc-annotated` | Arc sector gauge with optional range markers |
| Donut | `cairo-gauge-donut` | Ring/donut gauge |
| Marker | `cairo-gauge-marker` | Linear gauge with dot marker |

### Speed Gauge (Round Style)

```xml
<composite x="100" y="500" width="256" height="256" name="speed_gauge">
    <component type="cairo-gauge-round-annotated" size="256"
               metric="speed" units="kph" max="60" min="0"
               start="143" length="254" sectors="6"
               background-rgb="255,255,255,150"
               needle-rgb="255,0,0"
               major-tick-rgb="0,0,0" minor-tick-rgb="0,0,0"
               major-ann-rgb="0,0,0" minor-ann-rgb="0,0,0"/>
</composite>
```

### Battery Gauge (Donut Style)

```xml
<composite x="400" y="500" width="256" height="256" name="battery_gauge">
    <component type="cairo-gauge-donut" size="256"
               metric="battery" units="percent" max="100" min="0"
               start="90" length="270" sectors="5"
               needle-rgb="255,0,0"
               major-tick-rgb="0,0,0" minor-tick-rgb="0,0,0"
               major-ann-rgb="0,0,0" minor-ann-rgb="0,0,0"/>
</composite>
```

### Power Gauge (Arc Style)

Power can be negative (regenerative braking), so set `min` below zero:

```xml
<composite x="700" y="500" width="256" height="256" name="power_gauge">
    <component type="cairo-gauge-arc-annotated" size="256"
               metric="power" units="watt" max="2000" min="-500"
               start="150" length="240" sectors="6"
               background-rgb="255,255,255,150"
               needle-rgb="255,0,0"
               major-tick-rgb="0,0,0" minor-tick-rgb="0,0,0"
               major-ann-rgb="0,0,0" minor-ann-rgb="0,0,0"/>
</composite>
```

### Voltage Gauge (Marker Style)

```xml
<composite x="100" y="800" width="256" height="256" name="voltage_gauge">
    <component type="cairo-gauge-marker" size="256"
               metric="voltage" units="volt" max="100" min="60"
               start="150" length="240" sectors="5"
               tick-rgb="255,255,255"
               background-rgb="0,0,0,100"
               gauge-rgb="0,191,255"/>
</composite>
```

### Gauge Colour Attributes by Style

Different gauge styles accept different colour attributes:

| Attribute | Round | Arc | Donut | Marker |
|-----------|-------|-----|-------|--------|
| `background-rgb` | Yes | Yes | No* | Yes |
| `needle-rgb` | Yes | Yes | Yes | No |
| `major-tick-rgb` | Yes | Yes | Yes | No |
| `minor-tick-rgb` | Yes | Yes | Yes | No |
| `major-ann-rgb` | Yes | Yes | Yes | No |
| `minor-ann-rgb` | Yes | Yes | Yes | No |
| `tick-rgb` | No | No | No | Yes |
| `gauge-rgb` | No | No | No | Yes |
| `dot-outer-rgb` | No | No | No | Yes |
| `dot-inner-rgb` | No | No | No | Yes |
| `arc-inner-rgb` | No | Yes | Yes | No |
| `arc-outer-rgb` | No | Yes | Yes | No |

*Donut uses `background-inner-rgb` and `background-outer-rgb` instead.

## Bars

Horizontal fill bars for EUC metrics.

### Speed Bar

```xml
<composite x="100" y="450" width="400" height="30" name="speed_bar">
    <component type="bar" width="400" height="30"
               metric="speed" units="kph" max="60" min="0"
               outline="255,255,255,128" fill="255,136,68,200"/>
</composite>
```

### Battery Bar

```xml
<composite x="100" y="490" width="400" height="30" name="battery_bar">
    <component type="bar" width="400" height="30"
               metric="battery" units="percent" max="100" min="0"
               outline="255,255,255,128" fill="68,187,68,200"/>
</composite>
```

## Data Source

EUC telemetry data comes from EUC World exports:

- **XLSX**: Use `--xlsx ride.xlsx` — reads Battery, Voltage, Current, Power, Temperature, Speed columns directly
- **GPX**: Use `--gpx ride.gpx` — reads `euc:battery`, `euc:voltage`, `euc:current` from `<euc:TelemetryExtension>` in track point extensions

See [EUC World Guide](../../euc-world-guide.md) for details on exporting data.
