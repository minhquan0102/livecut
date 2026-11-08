"""Mô hình dữ liệu dự án và lưu/đọc JSON. Không phụ thuộc Qt."""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from subtitle.srt import Cue

SCHEMA_VERSION = 1
TRANSITION_KINDS = ("hard_cut", "crossfade", "fade_black", "fade_in", "fade_out",
                    "white_flash", "zoom", "blur")


def new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class Transition:
    kind: str = "hard_cut"
    duration_ms: int = 500
    enabled: bool = True
    audio_fade: bool = True


@dataclass
class Segment:
    start_ms: int
    end_ms: int
    source: str = "manual"  # "srt" | "manual"
    id: str = field(default_factory=new_id)
    note: str = ""
    cue_indexes: list[int] = field(default_factory=list)
    pad_before_ms: int = 0
    pad_after_ms: int = 0

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass
class GroupItem:
    segment_id: str
    transition: Transition = field(default_factory=Transition)  # hiệu ứng vào đoạn này


@dataclass
class Group:
    name: str
    id: str = field(default_factory=new_id)
    items: list[GroupItem] = field(default_factory=list)


@dataclass
class ManualRange:
    """Khoảng do người dùng tự chọn trên timeline, không phụ thuộc phụ đề."""
    id: int
    start_ms: int
    end_ms: int


@dataclass
class Project:
    name: str = "Dự án mới"
    video_path: str = ""
    srt_path: str = ""
    cues: list[Cue] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    manual: list[ManualRange] = field(default_factory=list)   # các khoảng tự chọn (khóa đoạn = -id)
    order: list[int] = field(default_factory=list)   # thứ tự đoạn do người dùng kéo thả (khóa = dòng SRT đầu tiên)

    def add_manual(self, start_ms: int, end_ms: int) -> ManualRange:
        m = ManualRange(max((r.id for r in self.manual), default=0) + 1, int(start_ms), int(end_ms))
        self.manual.append(m)
        return m

    def manual_by_id(self, mid: int) -> ManualRange | None:
        return next((m for m in self.manual if m.id == mid), None)

    def add_group(self, name: str) -> Group:
        g = Group(name=name.strip() or "Nhóm mới")
        self.groups.append(g)
        return g

    def remove_group(self, group_id: str) -> None:
        self.groups = [g for g in self.groups if g.id != group_id]

    def segment(self, segment_id: str) -> Segment | None:
        return next((s for s in self.segments if s.id == segment_id), None)

    def to_dict(self) -> dict:
        return {
            "version": SCHEMA_VERSION,
            "name": self.name,
            "video_path": self.video_path,
            "srt_path": self.srt_path,
            "cues": [asdict(c) for c in self.cues],
            "segments": [asdict(s) for s in self.segments],
            "groups": [asdict(g) for g in self.groups],
            "manual": [asdict(m) for m in self.manual],
            "order": list(self.order),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        if d.get("version", 1) > SCHEMA_VERSION:
            raise ValueError("Dự án được tạo bởi phiên bản mới hơn của LiveCut Studio.")
        groups = []
        for g in d.get("groups", []):
            items = [GroupItem(i["segment_id"], Transition(**i.get("transition", {})))
                     for i in g.get("items", [])]
            groups.append(Group(name=g["name"], id=g.get("id") or new_id(), items=items))
        return cls(
            name=d.get("name", "Dự án mới"),
            video_path=d.get("video_path", ""),
            srt_path=d.get("srt_path", ""),
            cues=[Cue(**c) for c in d.get("cues", [])],
            segments=[Segment(**s) for s in d.get("segments", [])],
            groups=groups,
            manual=[ManualRange(int(m["id"]), int(m["start_ms"]), int(m["end_ms"])) for m in d.get("manual", [])],
            order=[int(k) for k in d.get("order", [])],
        )

    def save(self, path: str | Path) -> None:
        path = Path(path)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str | Path) -> "Project":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
