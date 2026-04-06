# EUC World Integration Guide

This guide covers how to use data from [EUC World](https://euc.world/) -- the popular Electric Unicycle logging app -- with gopro-dashboard-overlay.

## Exporting Data from EUC World

EUC World can export ride data in two formats:

- **XLSX** -- A spreadsheet containing all telemetry columns (GPS, speed, battery, voltage, current, power, temperature, etc.)
- **GPX** -- A standard GPS track format. EUC World's GPX exports include a non-standard `<speed>` element as a direct child of `<trkpt>`, with speed values in km/h.

Both formats are supported by the dashboard tool.

## Using --xlsx (Recommended for EUC Data)

The `--xlsx` flag loads an EUC World XLSX export directly, with no conversion step required:

```bash
python gopro-dashboard.py \
    --xlsx ride.xlsx \
    --use-gpx-only \
    --video-time-start video-created \
    --overlay-size 1920x1080 \
    --layout xml --layout-xml my-layout.xml \
    input.mp4 output.mp4
```

### How the XLSX Loader Works

The XLSX loader (`load_xlsx` in `gopro_overlay/gpx.py`) reads the following columns from the active worksheet:

**Required columns:**
- `Date & Time` -- Timestamp for each data point
- `GPS Latitude [°]` -- Latitude in degrees
- `GPS Longitude [°]` -- Longitude in degrees

**Optional columns:**
- `GPS Altitude [m]` -- Elevation in metres
- `Speed [km/h]` -- Wheel speed (preferred over GPS speed)
- `GPS Speed [km/h]` -- GPS-derived speed (used as fallback if wheel speed is absent)
- `Battery [%]` -- Battery percentage
- `Voltage [V]` -- Pack voltage
- `Current [A]` -- Current draw
- `Power [W]` -- Power consumption
- `Temperature [°C]` -- Motor/board temperature

**Timezone handling:**

EUC World exports timestamps in the device's local time without timezone information. The XLSX loader handles this as follows:

1. If the `Date & Time` value is a Python `datetime` object (as returned by openpyxl for Excel date cells), it is used directly.
2. If it is a string, it is parsed with the format `%Y-%m-%d %H:%M:%S`.
3. If the resulting datetime has no timezone, the system's local timezone is applied.
4. All timestamps are then converted to UTC for internal use.

**Speed conversion:**

Speed values from the XLSX are in km/h. The loader converts them to m/s (dividing by 3.6) before creating internal data points, since the overlay engine works in SI units.

**Dependencies:**

The XLSX loader requires the `openpyxl` package:

```bash
pip install openpyxl
```

## Using --gpx with EUC World GPX Files

If you have a GPX file exported from EUC World, use the standard `--gpx` flag:

```bash
python gopro-dashboard.py \
    --gpx ride.gpx \
    --use-gpx-only \
    --video-time-start video-created \
    --overlay-size 1920x1080 \
    input.mp4 output.mp4
```

### GPX Preprocessing

EUC World GPX files require preprocessing because they place `<speed>` as a direct child of `<trkpt>`, which is not valid GPX 1.1. The `_preprocess_gpx` function in `gopro_overlay/gpx.py` handles this automatically:

1. **Detection** -- The function checks whether the GPX file contains `<speed>` elements as direct children of `<trkpt>` (examining the first 5000 characters).

2. **Relocation** -- Each `<speed>VALUE</speed>` element is replaced with a properly structured `<extensions>` block using the Garmin TrackPointExtension namespace (`http://www.garmin.com/xmlschemas/TrackPointExtension/v1`).

3. **Unit conversion** -- EUC World exports speed in km/h. During relocation, the value is converted to m/s (dividing by 3.6), which is the GPX standard unit for speed.

4. **Namespace handling** -- Both plain `<speed>` and namespace-prefixed variants are handled. The preprocessing only runs if there are no existing `TrackPointExtension` blocks in the file.

The result is a standard GPX 1.1 document that gpxpy can parse correctly, with speed available in the extensions.

### Extended Metric Parsing

When parsing GPX track points, the loader extracts these extension elements (from any namespace):

- `speed` -- Speed in m/s (after preprocessing)
- `battery` -- Battery percentage
- `voltage` -- Pack voltage in volts
- `current` -- Current in amps
- `power` -- Power in watts
- `atemp` -- Ambient/motor temperature
- `hr` -- Heart rate
- `cad` -- Cadence

## Standalone XLSX-to-GPX Converter

The script `bin/euc-xlsx-to-gpx.py` converts an EUC World XLSX export to a GPX file with extended telemetry. This is useful if you want a GPX file for use with other tools, or to inspect the converted data.

### Usage

```bash
# Convert with auto-named output (ride.xlsx -> ride.gpx)
python bin/euc-xlsx-to-gpx.py ride.xlsx

# Specify output filename
python bin/euc-xlsx-to-gpx.py ride.xlsx output.gpx
```

### What the Converter Produces

The output GPX file includes:

- Standard GPX 1.1 track points with `lat`, `lon`, `<ele>`, and `<time>` elements.
- **Speed** in the Garmin TrackPointExtension namespace (`gpxtpx:speed`) in m/s, converted from the XLSX km/h value. Temperature is also placed here as `gpxtpx:atemp` if present.
- **EUC-specific telemetry** in a custom namespace (`euc:` with URI `https://euc.world/gpx/1/0`), inside an `euc:TelemetryExtension` block:
  - `euc:battery` -- Battery percentage
  - `euc:voltage` -- Voltage in volts
  - `euc:current` -- Current in amps
  - `euc:power` -- Power in watts
  - `euc:wheel_speed` -- Wheel speed in m/s (included only when both wheel speed and GPS speed are present in the source data)

### Columns Read

The converter reads the same columns as the XLSX loader:

- `Date & Time`, `GPS Latitude [°]`, `GPS Longitude [°]` (required)
- `GPS Altitude [m]`, `Speed [km/h]`, `GPS Speed [km/h]`, `Battery [%]`, `Voltage [V]`, `Current [A]`, `Power [W]`, `Temperature [°C]`, `GPS Bearing [°]` (optional)

### Timezone Handling

The converter uses the same approach as the XLSX loader: naive timestamps from the XLSX are treated as local time (using the system's timezone), then converted to UTC for the GPX `<time>` elements.
