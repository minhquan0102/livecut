"""Từ các dòng phụ đề đã chọn -> các đoạn video; và bộ theo dõi vị trí khi xem thử liên tiếp.

Không phụ thuộc Qt nên kiểm thử được độc lập.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from subtitle.srt import Cue
from utils.timecode import parse_timecode


@dataclass
class Range:
    start_ms: int
    end_ms: int
    cue_indexes: list[int] = field(default_factory=list)
    key: int | None = None          # None = đoạn từ phụ đề (khóa là dòng đầu); âm = khoảng thủ công

    @property
    def manual(self) -> bool:
        return self.key is not None and self.key < 0

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


def range_key(r: Range) -> int:
    """Định danh ổn định của một đoạn: dòng phụ đề đầu tiên; khoảng thủ công dùng số âm (-id)."""
    return r.key if r.key is not None else r.cue_indexes[0]


MIN_MANUAL_MS = 100


def manual_ranges(manual, duration_ms: int = 0) -> list[Range]:
    """Khoảng thủ công -> Range: kẹp trong [0, duration], bỏ khoảng quá ngắn; không đệm, không gộp."""
    out: list[Range] = []
    for m in manual:
        s, e = max(0, m.start_ms), m.end_ms
        if duration_ms > 0:
            s, e = min(s, duration_ms), min(e, duration_ms)
        if e - s >= MIN_MANUAL_MS:
            out.append(Range(s, e, [], key=-m.id))
    return out


def validate_range(start_text: str, end_text: str, duration_ms: int) -> tuple[int, int]:
    """Đọc và kiểm tra hai mốc; ném ValueError kèm lời nhắc tiếng Việt nếu sai."""
    start, end = parse_timecode(start_text), parse_timecode(end_text)
    if duration_ms > 0 and start >= duration_ms:
        raise ValueError("Thời gian bắt đầu nằm sau cuối video.")
    if end <= start:
        raise ValueError("Thời gian kết thúc phải lớn hơn thời gian bắt đầu.")
    if duration_ms > 0:
        end = min(end, duration_ms)
    if end - start < MIN_MANUAL_MS:
        raise ValueError("Khoảng quá ngắn (tối thiểu 0,1 giây).")
    return start, end


def combine(srt_ranges: list[Range], manual: list[Range]) -> list[Range]:
    """Gộp hai nguồn đoạn, xếp theo thời gian (ổn định)."""
    return sorted([*srt_ranges, *manual], key=lambda r: r.start_ms)


def apply_order(ranges: list[Range], order: list[int]) -> list[Range]:
    """Sắp theo thứ tự người dùng đã kéo thả. Đoạn mới (chưa có trong `order`) nối vào cuối, theo thời gian."""
    remaining = {range_key(r): r for r in ranges}
    out = [remaining.pop(k) for k in order if k in remaining]
    out.extend(r for r in ranges if range_key(r) in remaining)
    return out


MIN_OVERLAP_MS = 250


def cut_cues(ranges: list[tuple[int, int]], cues: list[Cue], chosen: set[int]) -> list[Cue]:
    """Phụ đề khớp với video đã cắt: dời mốc thời gian theo vị trí mới của từng đoạn.

    Dòng được chọn luôn có mặt; dòng lân cận chỉ bị lọt vào phần đệm thì chỉ giữ khi hiện đủ lâu.
    """
    ordered = sorted(cues, key=lambda c: c.start_ms)
    out: list[Cue] = []
    offset = 0
    for start, end in ranges:
        for c in ordered:
            a, b = max(c.start_ms, start), min(c.end_ms, end)
            overlap = b - a
            if overlap <= 0:
                continue
            if c.index in chosen or overlap >= min(MIN_OVERLAP_MS, c.end_ms - c.start_ms):
                out.append(Cue(len(out) + 1, a - start + offset, b - start + offset, c.text))
        offset += end - start
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
