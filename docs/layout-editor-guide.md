# Layout Editor Guide

`gopro-layout-editor.py` is a tkinter-based visual layout editor for designing overlay layouts. It lets you drag and resize components on a video preview, configure component properties, synchronise GPX and video timing, and run encoding -- all from a single GUI.

## Starting the Editor

```bash
python bin/gopro-layout-editor.py [workdir] [options]
```

### CLI Arguments

| Argument | Description |
|---|---|
| `workdir` | (positional, optional) Working folder for file dialogs. Also settable via the `GOPRO_WORKDIR` environment variable. |
| `--gpx FILE` | Load a GPX or FIT route file on startup. |
| `--xlsx FILE` | Load an EUC World XLSX file as the route on startup. |
| `--videos FILE [FILE ...]` | Load one or more video files on startup. |
| `--layout FILE` | Load a layout XML file on startup. Also settable via the `GOPRO_LAYOUT_XML` environment variable. |
| `--env-file FILE` | Path to a `.env` file containing API keys (`API_KEY_THUNDERFOREST`, `API_KEY_GEOAPIFY`). |
| `--thunderforest-key KEY` | Thunderforest API key for `tf-*` map styles. |
| `--geoapify-key KEY` | Geoapify API key for `geo-*` map styles. |

### Example

```bash
python bin/gopro-layout-editor.py ~/rides \
    --gpx ~/rides/today.gpx \
    --videos ~/rides/GX010042.MP4 ~/rides/GX010043.MP4 \
    --layout ~/rides/my-layout.xml \
    --env-file ~/rides/.env
```

## Loading Route Files

The editor accepts GPX, FIT, and XLSX route files. Load them via:

- The `--gpx` or `--xlsx` CLI arguments at startup.
- The file dialog within the editor (File menu or toolbar).

When a route file is loaded, the editor:

1. Displays the file name and type (GPX/FIT/XLSX) in the sidebar.
2. Extracts the first GPS coordinate for map tile previews.
3. Scans the route data for metric ranges (speed, battery, voltage, current, power) used to auto-scale gauge components.

## Loading Videos

Add video files via `--videos` at startup or through the file dialog. The editor uses `ffprobe` to analyse each video, extracting:

- Raw and effective dimensions (accounting for rotation).
- Duration in seconds.
- Creation time from MP4 metadata.

When a video is selected, a frame is extracted and displayed as the canvas background. The canvas scales the video to fit within a maximum of 960x800 pixels, with a scale factor applied to all component coordinates.

## The Preview Canvas

The canvas shows a scaled view of the video frame with overlay components drawn as coloured rectangles.

### Dragging Components

Click and drag any component rectangle to reposition it on the canvas. The component's full-resolution coordinates are updated based on the canvas scale factor.

### Resize Handles

Each component has three resize handles:

- **Bottom-right corner** -- Resize both width and height simultaneously.
- **Right edge** -- Resize width only.
- **Bottom edge** -- Resize height only.

Drag any handle to change the component's bounding box. Font sizes and gauge sizes are automatically recalculated from the new dimensions (see Auto Font Sizing below).

### Component Checkboxes

The sidebar lists all available components with checkboxes. Checking a component enables it (it will appear in the generated XML); unchecking disables it. Disabled components are not drawn on the canvas.

## Right-Click Properties Dialog

Right-clicking a component on the canvas opens the **ComponentOptionsDialog** -- a modal dialog for editing that component's specific properties.

Each component type has its own set of configurable fields (defined in `COMPONENT_OPTIONS`). Field types include:

- **combo** / **combo_editable** -- Dropdown selection (editable variants allow custom values).
- **spinbox** -- Numeric value with min/max/step constraints.
- **slider** / **slider_float** -- Slider for integer or floating-point ranges.
- **checkbox** -- Boolean toggle.
- **colour_select** -- Colour picker (R,G,B or R,G,B,A format).
- **font_select** -- Font file selection dialog.
- **combo_preview** -- Combo with live map tile preview (used for map style selection).

Changes are stored in the component's `custom_props` dictionary and take precedence over auto-calculated values.

## Auto Font Sizing

When a component is resized, font sizes are automatically derived from the new dimensions by the `_auto_font_sizes` function. The rules vary by component type:

- **Gauge components** (speed_gauge, battery_gauge, etc.): `gauge_size` is set to `min(width, height)`.
- **Speed display** (big_mph): `speed_font_size` equals the component height; label size is height / 10.
- **Value displays** (battery_value, voltage_value, etc., plus gradient, altitude, temperature, cadence, heartbeat): Icon size is 91% of height, value font is 46% of height, label font is 23% of height, and the value Y offset is calculated from these.
- **Date + Time**: Date text is 33% of height, time text is 67%, with a gap between lines.
- **Date Only / Time Only**: Font size fills the component height.

Manual overrides set via the properties dialog always take precedence over auto-calculated sizes.

## Saving and Loading Layout XML

### Saving

Use File > Save Layout XML (or the toolbar button) to save the current component arrangement as an XML file. The generated XML includes:

- Position (`x`, `y`) and size (`width`, `height`) for each enabled component.
- All template variables resolved (font sizes, gauge ranges, colour attributes, etc.).

### Loading

Use File > Load Layout XML, the `--layout` CLI argument, or the `GOPRO_LAYOUT_XML` environment variable. When loading:

1. Component positions and sizes are read from the XML element attributes (`x`, `y`, `width`, `height`, `size`).
2. Components found in the XML are enabled; components not found are disabled.
3. Any custom properties stored in the XML are restored.

This round-trip preserves component sizes -- if you resize a component in the editor, save, and reload, the sizes are retained.

## Exporting Self-Contained Shell Scripts

The editor can generate a self-contained bash script that encodes all loaded videos. The script:

1. Embeds the full layout XML in a heredoc, written to a temp file at runtime.
2. Sets a `trap` to clean up the temp file on exit.
3. Generates one `gopro-dashboard.py` invocation per video, with all necessary flags (`--use-gpx-only`, `--video-time-start video-created`, `--layout xml`, `--layout-xml`, etc.).
4. Automatically uses `--xlsx` or `--gpx` depending on the route file extension.
5. Includes `--gpx-time-offset` and `--sample-duration` if configured.
6. Includes `--profile` for GPU acceleration if detected.

Output filenames follow the pattern `{input_stem}_overlay{input_suffix}`.

## Running Encoding from the Editor

The editor can launch encoding directly via the **EncodingDialog**. This:

1. Writes the layout XML to a temporary file.
2. Runs `gopro-dashboard.py` as a subprocess for each loaded video.
3. Shows a progress bar (parsing `Render: N [P%]` output lines).
4. Displays a scrolling log of encoder output.
5. Supports cancellation (terminates the subprocess).
6. Cleans up the temporary layout XML file when done.

The encoding command includes `--use-gpx-only --video-time-start video-created` and passes through the configured speed unit, font, map style, GPU profile, GPX time offset, and sample duration.

## GPX / Video Time Sync Dialog

Accessible from the Settings menu, the **SyncDialog** helps align video and GPX data visually. It requires both a video and a GPX route file to be loaded.

### Interface Layout

The dialog has four main sections:

1. **Video preview** -- Shows the current video frame. The preview resizes with the dialog window and maintains the video's aspect ratio.

2. **Video scrub controls** -- A slider to scrub through the video, plus playback buttons:
   - `<<` / `>>` -- Jump 30 seconds back/forward.
   - `<` / `>` -- Jump 5 seconds back/forward.
   - `Play 1x` -- Toggle 1x playback. Additional buttons for `2x`, `4x`, `8x` speed.

3. **Altitude chart** -- A scrolling altitude profile drawn from the GPX elevation data. A red marker shows the current video position on the GPX timeline (calculated from the video's creation time plus the current offset and scrub position). The chart includes:
   - A scrollbar to pan along the GPX timeline.
   - Zoom controls: `-`/`+` buttons and preset durations (`30s`, `2m`, `10m`, `30m`, `All`).
   - Default visible window is 10 minutes (600 seconds).
   - The chart auto-follows the marker during video scrubbing, but switches to manual scroll mode when the user drags the chart scrollbar.

4. **Offset fine-tune** -- Controls for adjusting the time offset:
   - `-1s` / `-0.1s` / `+0.1s` / `+1s` nudge buttons.
   - A slider ranging from -3600 to +3600 seconds.
   - A direct-entry field (press Enter to apply).
   - Current offset and altitude readouts.

### Buttons

- **Apply** -- Saves the offset and closes the dialog.
- **Cancel** -- Closes without saving.
- **Reset to 0** -- Resets the offset to zero.

### Keyboard Shortcuts

| Key | Action |
|---|---|
| Space | Toggle playback |
| Left / Right | Scrub video 5 seconds back/forward |
| Shift+Left / Shift+Right | Scrub video 0.5 seconds back/forward |
| Up / Down | Nudge offset +1s / -1s |
| Shift+Up / Shift+Down | Nudge offset +0.1s / -0.1s |
| `+` / `=` | Zoom in on altitude chart |
| `-` | Zoom out on altitude chart |
| Escape | Close dialog (cancel) |
| Enter | Apply and close |

## Sample Duration

When a sample duration is configured, the editor passes `--sample-duration` to the encoding command. This limits the render to the specified number of seconds, which is useful for quickly previewing overlay positioning without encoding the full video.

## GPU Detection

The editor checks for NVIDIA GPU encoding support by running `nvidia-smi` and checking `ffmpeg -encoders` for `h264_nvenc`. If available, it passes `--profile nvgpu` to the encoding command.

## Font Detection

The editor searches common font paths for a usable font:

1. DejaVu Sans (TTF)
2. Roboto Medium
3. Liberation Sans

If none are found, it falls back to using `fc-match` to locate DejaVu Sans, or defaults to `Roboto-Medium.ttf`.
