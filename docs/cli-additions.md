# CLI Additions

This document covers new command-line options added to `gopro-dashboard.py` in this fork.

## --xlsx

**Defined in:** `gopro_overlay/arguments.py` (GPX argument group)

```
--xlsx PATH
```

Load an EUC World XLSX export directly as the route data source. Use instead of `--gpx` when you have an XLSX file from EUC World.

The XLSX file is loaded via `load_xlsx_timeseries` in `gopro_overlay/gpx.py`, which reads GPS coordinates, speed, battery, voltage, current, power, and temperature columns. Speed values are converted from km/h to m/s internally. Requires `openpyxl` (`pip install openpyxl`).

Internally, `--xlsx` feeds into the same code path as `--gpx`. The `load_external` function in `gopro_overlay/loading.py` dispatches based on file extension: `.gpx` uses the GPX loader, `.fit` uses the FIT loader, `.xlsx` uses the XLSX loader.

### Usage Examples

```bash
# Use XLSX as sole data source (no GoPro GPS)
python gopro-dashboard.py \
    --xlsx ride.xlsx \
    --use-gpx-only \
    --video-time-start video-created \
    --overlay-size 1920x1080 \
    --layout xml --layout-xml layout.xml \
    video.mp4 output.mp4

# Use XLSX to extend GoPro data (merge mode)
python gopro-dashboard.py \
    --xlsx ride.xlsx \
    --gpx-merge EXTEND \
    video.mp4 output.mp4
```

**Validation:** `--use-gpx-only` requires either `--gpx` or `--xlsx` to be set. If neither is provided, the parser exits with an error.

---

## --gpx-time-offset

**Defined in:** `gopro_overlay/arguments.py` (GPX Only argument group)

```
--gpx-time-offset SECONDS
```

**Type:** float | **Default:** `0.0`

Offset in seconds to apply to the GPX/video time alignment. This shifts when the overlay data appears relative to the video.

- **Positive values** advance the overlay (shift GPX data earlier relative to video). Use when the video starts after the GPX recording.
- **Negative values** retard the overlay (shift GPX data later relative to video). Use when the video starts before the GPX recording.

The offset is applied in `bin/gopro-dashboard.py` after the video start/end dates are determined (from `--video-time-start` or `--video-time-end`). Both `start_date` and `end_date` are shifted by adding a `timedelta(seconds=gpx_time_offset)`:

```python
if start_date is not None and args.gpx_time_offset:
    offset_td = datetime.timedelta(seconds=args.gpx_time_offset)
    start_date = start_date + offset_td
    end_date = end_date + offset_td
```

The applied offset is logged: `GPX time offset: +30.0s`

### Usage Examples

```bash
# Video starts 30 seconds after GPX recording began
python gopro-dashboard.py \
    --gpx ride.gpx \
    --use-gpx-only \
    --video-time-start video-created \
    --gpx-time-offset 30 \
    video.mp4 output.mp4

# Video is 15.5 seconds ahead of GPX data
python gopro-dashboard.py \
    --gpx ride.gpx \
    --use-gpx-only \
    --video-time-start file-modified \
    --gpx-time-offset -15.5 \
    video.mp4 output.mp4
```

**Note:** This option only has effect when `--use-gpx-only` is used with either `--video-time-start` or `--video-time-end`. The layout editor's Sync Dialog provides a visual interface for determining the correct offset value.

---

## --sample-duration

**Defined in:** `gopro_overlay/arguments.py` (Rendering argument group)

```
--sample-duration SECONDS
```

**Type:** float | **Default:** `None` (render full video)

Only render this many seconds of video. Useful for quickly testing overlay layout and positioning without encoding the full video.

### How It Works

The sample duration affects rendering in two ways:

1. **Frame limiting:** The number of overlay frames is capped:
   ```python
   max_frames = int(args.sample_duration / (0.1 * timelapse_correction))
   ```
   The frame loop breaks after `max_frames` iterations.

2. **FFmpeg input truncation:** The ffmpeg command receives `-t {sample_duration}` as an input option, telling it to stop reading the source video after that many seconds.

3. **GPX window trimming (--use-gpx-only mode):** When using `--use-gpx-only` with a video file, the GPX timeseries window is trimmed to match the sample duration:
   ```python
   if args.sample_duration and duration is not None:
       sample_tu = timeunits(seconds=args.sample_duration)
       if sample_tu < duration:
           effective_duration = sample_tu
   ```

### Usage Examples

```bash
# Render only the first 10 seconds to check positioning
python gopro-dashboard.py \
    --gpx ride.gpx \
    --use-gpx-only \
    --video-time-start video-created \
    --sample-duration 10 \
    --layout xml --layout-xml layout.xml \
    video.mp4 test_output.mp4

# Quick 30-second preview with full overlay
python gopro-dashboard.py \
    --sample-duration 30 \
    video.mp4 preview.mp4
```

This option is also exposed in the layout editor and is passed through to the encoding command when running from the GUI.
