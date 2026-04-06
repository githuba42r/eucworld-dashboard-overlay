from PIL import Image, ImageDraw

from .map import draw_marker
from .widgets import Widget


class SimpleChart(Widget):

    def __init__(
            self,
            value,
            font=None,
            filled=False,
            height=64,
            width=None,
            marker_time_fn=None,
            window_tick_ms=100,
            marker_size=4,
            bg=(0, 0, 0, 170),
            fill=(91, 113, 146),
            line=(255, 255, 255),
            text=(255, 255, 255),
    ):
        self.value = value
        self.filled = filled
        self.font = font
        self.height = height
        self.width = width
        self.marker_time_fn = marker_time_fn
        self.window_tick_ms = window_tick_ms
        self.marker_size = marker_size
        self.fill = fill
        self.bg = bg
        self.line = line
        self.text = text

        self.view = None
        self.chart_image = None  # cached body without marker

        # state preserved between frames for smooth marker interpolation
        self._data = None
        self._n = 0
        self._x_first = 0
        self._x_last = 0
        self._x_scale = 1.0
        self._min_val = 0
        self._scale_y = 1.0

    # ------------------------------------------------------------------
    # helpers (use stored state so they work outside the cache block)
    # ------------------------------------------------------------------

    def _x_pos(self, idx):
        return (idx - self._x_first) * self._x_scale

    def _y_pos(self, val):
        return self.height - 1 - (val - self._min_val) * self._scale_y

    # ------------------------------------------------------------------

    def draw(self, image: Image, draw: ImageDraw):
        view = self.value()

        if not (self.view and self.view.version == view.version):
            self.view = view
            data = view.data
            n = len(data)
            render_width = self.width if self.width is not None else n
            size = (render_width, self.height)
            self.chart_image = Image.new("RGBA", size, self.bg)
            chart_draw = ImageDraw.Draw(self.chart_image)

            values = [v for v in data if v is not None]
            max_val = max(values, default=0)
            min_val = min(values, default=0)
            range_val = max(max_val - min_val, 1)

            # store state needed for per-frame marker drawing
            self._data = data
            self._n = n
            self._min_val = min_val
            self._scale_y = size[1] / (range_val * 1.1)

            filtered = [(i, y) for i, y in enumerate(data) if y is not None]

            if self.width is not None and filtered:
                self._x_first = filtered[0][0]
                self._x_last = filtered[-1][0]
                self._x_scale = render_width / max(self._x_last - self._x_first, 1)
            else:
                self._x_first = 0
                self._x_last = n - 1
                self._x_scale = render_width / n if n > 0 else 1

            points = [(self._x_pos(i), self._y_pos(y)) for i, y in filtered]

            if self.filled and len(points) >= 2:
                baseline = size[1] - 1
                poly = points + [(points[-1][0], baseline), (points[0][0], baseline)]
                chart_draw.polygon(poly, fill=self.fill)

            if len(points) >= 2:
                chart_draw.line(points, width=2, fill=self.line)

            if self.font:
                rx = size[0] - 4
                chart_draw.text((rx, 4), f"{max_val:.0f}", font=self.font, fill=self.text,
                                stroke_width=2, stroke_fill=(0, 0, 0), anchor="rt")
                chart_draw.text((rx, self.height - 10), f"{min_val:.0f}", font=self.font,
                                fill=self.text, stroke_width=2, stroke_fill=(0, 0, 0), anchor="rb")

        # composite cached chart body
        image.alpha_composite(self.chart_image, (0, 0))

        # draw marker every frame with sub-tick interpolation for smooth movement
        if self._data is not None:
            if self.marker_time_fn is not None:
                raw_ms = self.marker_time_fn()
                frac = (raw_ms % self.window_tick_ms) / self.window_tick_ms
                marker_frac_idx = self._n // 2 + frac
            else:
                marker_frac_idx = float(self._n // 2)

            # clamp to the actual data range so the marker never escapes the chart
            marker_frac_idx = max(float(self._x_first), min(float(self._x_last), marker_frac_idx))

            lo = int(marker_frac_idx)
            hi = min(lo + 1, self._x_last)
            t = marker_frac_idx - lo
            data = self._data

            if 0 <= lo < self._n and 0 <= hi < self._n \
                    and data[lo] is not None and data[hi] is not None:
                y_val = data[lo] * (1 - t) + data[hi] * t
            elif 0 <= lo < self._n and data[lo] is not None:
                y_val = data[lo]
            elif 0 <= hi < self._n and data[hi] is not None:
                y_val = data[hi]
            else:
                y_val = None

            if y_val is not None:
                draw_marker(draw, (self._x_pos(marker_frac_idx), self._y_pos(y_val)),
                            self.marker_size, fill=(255, 0, 0))
