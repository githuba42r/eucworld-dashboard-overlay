import math
from typing import Callable, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from .widgets import Widget

LABELS = {
    0: "N", 45: "NE", 90: "E", 135: "SE",
    180: "S", 225: "SW", 270: "W", 315: "NW",
}


class HeadingTape(Widget):

    def __init__(
        self,
        width: int,
        height: int,
        reading: Callable[[], Optional[float]],
        font: ImageFont,
        tick_interval: int = 10,
        label_interval: int = 30,
        visible_range: int = 90,
        show_values: bool = True,
        show_border: bool = True,
        bg: Tuple[int, ...] = (0, 0, 0),
        fg: Tuple[int, ...] = (255, 255, 255),
        marker_rgb: Tuple[int, ...] = (255, 0, 0),
        opacity: int = 180,
    ):
        self.width = width
        self.height = height
        self.reading = reading
        self.font = font
        self.tick_interval = tick_interval
        self.label_interval = label_interval
        self.visible_range = max(10, visible_range)
        self.show_values = show_values
        self.show_border = show_border
        self.bg = bg
        self.fg = fg
        self.marker_rgb = marker_rgb
        self.opacity = opacity
        self.last_reading = None
        self.image = None

    def _redraw_no_data(self) -> Image.Image:
        """Draw a placeholder tape when heading data is unavailable."""
        image = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        bg_colour = self.bg[:3] + (self.opacity,) if len(self.bg) < 4 else self.bg
        outline = self.fg if self.show_border else None
        draw.rectangle([(0, 0), (self.width - 1, self.height - 1)], fill=bg_colour, outline=outline, width=1)
        draw.text((self.width / 2, self.height / 2), "---", font=self.font, anchor="mm", fill=self.fg)

        # Dimmed upward-pointing marker at bottom
        dimmed = tuple(max(0, c // 2) for c in self.marker_rgb[:3])
        marker_h = max(4, int(self.height * 0.2))
        marker_half_w = max(3, marker_h // 2)
        cx = self.width // 2
        draw.polygon([
            (cx, self.height - 1 - marker_h),
            (cx - marker_half_w, self.height - 1),
            (cx + marker_half_w, self.height - 1),
        ], fill=dimmed)

        return image

    def _redraw(self, heading: float) -> Image.Image:
        """Produce the tape image for a given heading."""
        width = self.width
        height = self.height
        ppd = width / self.visible_range  # pixels per degree

        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Background with opacity
        bg_colour = self.bg[:3] + (self.opacity,) if len(self.bg) < 4 else self.bg
        outline = self.fg if self.show_border else None
        draw.rectangle([(0, 0), (width - 1, height - 1)], fill=bg_colour, outline=outline, width=1)

        # Marker at bottom — upward-pointing triangle
        marker_h = max(4, int(height * 0.2))
        marker_half_w = max(3, marker_h // 2)
        cx = width // 2
        marker_top = height - 1 - marker_h
        draw.polygon([
            (cx, marker_top),
            (cx - marker_half_w, height - 1),
            (cx + marker_half_w, height - 1),
        ], fill=self.marker_rgb)

        # Solid line above the marker
        line_y = marker_top - 1
        draw.line([(0, line_y), (width - 1, line_y)], fill=self.fg, width=1)

        # Ticks grow upward from the line, labels at the top
        tape_h = line_y - 1

        # Tick heights relative to tape area
        major_tick_h = int(tape_h * 0.45)
        minor_tick_h = int(tape_h * 0.2)

        # Visible degree range
        half_range = self.visible_range / 2
        start_deg = heading - half_range
        end_deg = heading + half_range

        floor_start = int(math.floor(start_deg))
        ceil_end = int(math.ceil(end_deg))

        for deg in range(floor_start, ceil_end + 1):
            x = (deg - heading) * ppd + width / 2
            if x < -1 or x > width + 1:
                continue

            norm = deg % 360

            # Determine what to draw at this degree
            is_cardinal = norm in LABELS and norm % 90 == 0
            is_intercardinal = norm in LABELS and norm % 90 != 0
            is_label_tick = (self.label_interval > 0 and self.tick_interval > 0
                            and norm % self.label_interval == 0)
            is_minor_tick = (self.tick_interval > 0 and norm % self.tick_interval == 0)

            if is_cardinal or is_intercardinal:
                tick_h = major_tick_h
            elif is_label_tick or is_minor_tick:
                tick_h = minor_tick_h
            else:
                continue

            ix = int(round(x))

            # Draw tick from line upward
            draw.line([(ix, line_y), (ix, line_y - tick_h)], fill=self.fg, width=1)

            # Draw label above the tick (at the top)
            label = None
            if is_cardinal or is_intercardinal:
                label = LABELS[norm]
            elif is_label_tick and self.show_values:
                label = str(norm)

            if label is not None:
                label_y = line_y - tick_h - 2
                draw.text((ix, label_y), label, font=self.font, anchor="mb", fill=self.fg)

        return image

    def draw(self, image: Image.Image, draw: ImageDraw.Draw):
        heading_raw = self.reading()

        if heading_raw is None:
            if self.last_reading != "none":
                self.last_reading = "none"
                self.image = self._redraw_no_data()
            image.alpha_composite(self.image, (0, 0))
            return

        heading = int(round(heading_raw))

        if self.image is None or heading != self.last_reading:
            self.last_reading = heading
            self.image = self._redraw(heading)

        image.alpha_composite(self.image, (0, 0))
