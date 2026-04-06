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
        self.bg = bg
        self.fg = fg
        self.marker_rgb = marker_rgb
        self.opacity = opacity
        self.last_reading = None
        self.image = None

        # Pixels per degree — roughly 3px/deg gives a readable tape
        self.pixels_per_degree = 3.0

    def _redraw_no_data(self) -> Image.Image:
        """Draw a placeholder tape when heading data is unavailable."""
        image = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Background with opacity
        bg_colour = self.bg[:3] + (self.opacity,) if len(self.bg) < 4 else self.bg
        draw.rectangle([(0, 0), (self.width - 1, self.height - 1)], fill=bg_colour, outline=self.fg, width=1)

        # Centred dashes
        draw.text((self.width / 2, self.height / 2), "---", font=self.font, anchor="mm", fill=self.fg)

        # Dimmed centre marker
        dimmed = tuple(max(0, c // 2) for c in self.marker_rgb[:3])
        marker_h = max(4, int(self.height * 0.2))
        marker_half_w = max(3, marker_h // 2)
        cx = self.width // 2
        draw.polygon([
            (cx, self.height - 1),
            (cx - marker_half_w, self.height - 1 - marker_h),
            (cx + marker_half_w, self.height - 1 - marker_h),
        ], fill=dimmed)

        return image

    def _redraw(self, heading: float) -> Image.Image:
        """Produce the tape image for a given heading."""
        width = self.width
        height = self.height
        ppd = self.pixels_per_degree

        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Background with opacity
        bg_colour = self.bg[:3] + (self.opacity,) if len(self.bg) < 4 else self.bg
        draw.rectangle([(0, 0), (width - 1, height - 1)], fill=bg_colour, outline=self.fg, width=1)

        # Visible degree range
        visible_degrees = width / ppd
        start_deg = heading - visible_degrees / 2
        end_deg = heading + visible_degrees / 2

        # Tick heights
        major_tick_h = int(height * 0.5)
        intercardinal_tick_h = int(height * 0.4)
        numbered_tick_h = int(height * 0.35)
        minor_tick_h = int(height * 0.15)

        floor_start = int(math.floor(start_deg))
        ceil_end = int(math.ceil(end_deg))

        for deg in range(floor_start, ceil_end + 1):
            x = (deg - heading) * ppd + width / 2
            if x < -1 or x > width + 1:
                continue

            norm = deg % 360

            # Determine tick type and label
            label = None
            if norm in LABELS and norm % 90 == 0:
                # Cardinal direction
                tick_h = major_tick_h
                label = LABELS[norm]
            elif norm in LABELS:
                # Intercardinal direction
                tick_h = intercardinal_tick_h
                label = LABELS[norm]
            elif self.tick_interval > 0 and norm % self.tick_interval == 0:
                # Numbered tick
                tick_h = numbered_tick_h
                label = str(norm)
            elif norm % 5 == 0:
                # Minor tick every 5 degrees
                tick_h = minor_tick_h
            else:
                continue

            ix = int(round(x))

            # Draw tick line from top downward
            draw.line([(ix, 0), (ix, tick_h)], fill=self.fg, width=1)

            # Draw label below tick
            if label is not None:
                label_y = tick_h + 2
                draw.text((ix, label_y), label, font=self.font, anchor="mt", fill=self.fg)

        # Centre marker — downward-pointing triangle at bottom
        marker_h = max(4, int(height * 0.2))
        marker_half_w = max(3, marker_h // 2)
        cx = width // 2
        draw.polygon([
            (cx, height - 1),
            (cx - marker_half_w, height - 1 - marker_h),
            (cx + marker_half_w, height - 1 - marker_h),
        ], fill=self.marker_rgb)

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
