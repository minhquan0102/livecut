"""Từ các dòng phụ đề đã chọn -> các đoạn video; và bộ theo dõi vị trí khi xem thử liên tiếp.

Không phụ thuộc Qt nên kiểm thử được độc lập.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Range:
    start_ms: int
    end_ms: int
    cue_indexes: list[int] = field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


def build_ranges(cues, pad_before_ms: int = 300, pad_after_ms: int = 300,
                 duration_ms: int = 0, merge_gap_ms: int = 0) -> list[Range]:
    """Sắp theo thời gian, thêm đệm, kẹp trong [0, duration], gộp các đoạn chạm/chồng nhau."""
    out: list[Range] = []
    for c in sorted((c for c in cues if c.end_ms > c.start_ms), key=lambda c: c.start_ms):
        s = max(0, c.start_ms - pad_before_ms)
        e = c.end_ms + pad_after_ms
        if duration_ms > 0:
            s, e = min(s, duration_ms), min(e, duration_ms)
        if e <= s:
            continue
        if out and s <= out[-1].end_ms + merge_gap_ms:
            out[-1].end_ms = max(out[-1].end_ms, e)
            out[-1].cue_indexes.append(c.index)
        else:
            out.append(Range(s, e, [c.index]))
    return out


def total_ms(ranges: list[Range]) -> int:
    return sum(r.duration_ms for r in ranges)


class SequenceTracker:
    """Máy trạng thái cho việc phát lần lượt các đoạn.

    Cấp cho nó vị trí phát hiện tại; nó trả về việc cần làm:
      ("none", -1)   không làm gì
      ("goto", i)    nhảy tới đầu đoạn i
      ("stop", -1)   người dùng tua đi chỗ khác -> dừng xem thử
      ("done", -1)   đã hết đoạn cuối
    """
    END_TOL_MS = 40
    SETTLE_MS = 1500

    def __init__(self, ranges: list[tuple[int, int]]) -> None:
        self.ranges = list(ranges)
        self.index = 0
        self.settling = False

    def begin(self, index: int = 0) -> int:
        """Bắt đầu/đổi sang đoạn `index`; trả về vị trí (ms) cần seek tới."""
        self.index = max(0, min(index, len(self.ranges) - 1))
        self.settling = True       # chờ backend báo vị trí mới, bỏ qua vị trí cũ còn sót
        return self.ranges[self.index][0]

    def on_position(self, ms: int) -> tuple[str, int]:
        start, end = self.ranges[self.index]
        if self.settling:
            if abs(ms - start) > self.SETTLE_MS:
                return ("none", -1)
            self.settling = False
        if ms < start - self.SETTLE_MS or ms > end + self.SETTLE_MS:
            return ("stop", -1)
        if ms >= end - self.END_TOL_MS:
            if self.index + 1 < len(self.ranges):
                return ("goto", self.index + 1)
            return ("done", -1)
        return ("none", -1)
