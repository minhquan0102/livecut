"""Logic thuần của timeline: ánh xạ thời gian ↔ pixel, zoom, chọn bước chia vạch."""
from __future__ import annotations

NICE_STEPS = [100, 200, 500, 1000, 2000, 5000, 10_000, 15_000, 30_000, 60_000,
              120_000, 300_000, 600_000, 900_000, 1_800_000, 3_600_000, 7_200_000]


def pick_tick_step(ms_per_px: float, min_px: float = 90.0) -> int:
    for step in NICE_STEPS:
        if step / ms_per_px >= min_px:
            return step
    return NICE_STEPS[-1]


class TimeScale:
    MIN_MS_PER_PX = 0.05

    def __init__(self) -> None:
        self.duration_ms = 0
        self.start_ms = 0.0
        self.ms_per_px = 1.0
        self.width_px = 1

    @property
    def visible_ms(self) -> float:
        return self.width_px * self.ms_per_px

    def fit_ms_per_px(self) -> float:
        return max(self.duration_ms, 1) / self.width_px

    def set_duration(self, duration_ms: int) -> None:
        self.duration_ms = max(0, int(duration_ms))
        self.fit()

    def set_width(self, width_px: int) -> None:
        self.width_px = max(1, int(width_px))
        self._clamp()

    def fit(self) -> None:
        self.ms_per_px = self.fit_ms_per_px()
        self.start_ms = 0.0

    def _clamp(self) -> None:
        self.ms_per_px = min(max(self.ms_per_px, self.MIN_MS_PER_PX), self.fit_ms_per_px())
        self.start_ms = min(max(0.0, self.start_ms), max(0.0, self.duration_ms - self.visible_ms))

    def ms_to_x(self, ms: float) -> float:
        return (ms - self.start_ms) / self.ms_per_px

    def x_to_ms(self, x: float) -> float:
        return self.start_ms + x * self.ms_per_px

    def zoom_at(self, x: float, factor: float) -> None:
        """factor < 1 phóng to, > 1 thu nhỏ; giữ nguyên điểm đang trỏ chuột."""
        anchor = self.x_to_ms(x)
        self.ms_per_px = min(max(self.ms_per_px * factor, self.MIN_MS_PER_PX), self.fit_ms_per_px())
        self.start_ms = anchor - x * self.ms_per_px
        self._clamp()

    def pan_px(self, dx: float) -> None:
        self.start_ms += dx * self.ms_per_px
        self._clamp()

    def set_start(self, start_ms: float) -> None:
        self.start_ms = float(start_ms)
        self._clamp()

    def ensure_visible(self, ms: float) -> None:
        if ms < self.start_ms or ms > self.start_ms + self.visible_ms:
            self.start_ms = ms - self.visible_ms * 0.25
            self._clamp()
