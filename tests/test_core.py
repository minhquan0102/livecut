import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from project.model import Group, GroupItem, Project, Segment, Transition
from subtitle.srt import Cue, parse_srt, serialize_srt, validate_cues
from timeline.scale import TimeScale, pick_tick_step
from utils.text import fold
from utils.timecode import format_clock, format_srt_time, parse_timecode

SAMPLE = "\ufeff1\r\n00:00:01,000 --> 00:00:03,500\r\nXin chào các bạn\r\n\r\n2\r\n00:00:04,000 --> 00:00:06,000\r\nSản phẩm này rất đẹp\r\nvà bền\r\n\r\nrác không có thời gian\r\n\r\n4\r\n00:01:00,5 --> 00:01:02,000\r\nĐẹp quá\r\n"


class TimecodeTests(unittest.TestCase):
    def test_format(self):
        self.assertEqual(format_clock(65_000), "01:05")
        self.assertEqual(format_clock(3_725_000), "1:02:05")
        self.assertEqual(format_srt_time(3_725_042), "01:02:05,042")

    def test_parse(self):
        self.assertEqual(parse_timecode("1:02:05.042"), 3_725_042)
        self.assertEqual(parse_timecode("02:05"), 125_000)
        self.assertEqual(parse_timecode("45"), 45_000)
        self.assertEqual(parse_timecode("00:00:01,5"), 1_500)
        for bad in ("", "abc", "1:99", "1:2:3:4", "1:75:00"):
            with self.assertRaises(ValueError):
                parse_timecode(bad)


class SrtTests(unittest.TestCase):
    def test_parse_tolerant(self):
        r = parse_srt(SAMPLE)
        self.assertEqual(len(r.cues), 3)
        self.assertEqual(len(r.warnings), 1)
        self.assertEqual(r.cues[0].start_ms, 1000)
        self.assertEqual(r.cues[1].text, "Sản phẩm này rất đẹp\nvà bền")
        self.assertEqual(r.cues[2].start_ms, 60_500)

    def test_roundtrip(self):
        cues = parse_srt(SAMPLE).cues
        again = parse_srt(serialize_srt(cues)).cues
        self.assertEqual([(c.start_ms, c.end_ms, c.text) for c in cues],
                         [(c.start_ms, c.end_ms, c.text) for c in again])

    def test_validate_mismatch(self):
        cues = parse_srt(SAMPLE).cues
        self.assertEqual(validate_cues(cues, 120_000), [])
        self.assertEqual(validate_cues(cues, 30_000)[0].level, "error")
        self.assertEqual(validate_cues(cues, 3_600_000)[0].level, "warning")
        self.assertEqual(validate_cues([])[0].level, "error")

    def test_fold(self):
        self.assertEqual(fold("Đẹp Quá"), "dep qua")


class ScaleTests(unittest.TestCase):
    def make(self):
        s = TimeScale()
        s.set_width(1000)
        s.set_duration(3_600_000)
        return s

    def test_fit_and_zoom_keeps_anchor(self):
        s = self.make()
        self.assertAlmostEqual(s.visible_ms, 3_600_000)
        t = s.x_to_ms(500)
        s.zoom_at(500, 0.1)
        self.assertAlmostEqual(s.x_to_ms(500), t, delta=1)
        self.assertLess(s.visible_ms, 3_600_000)

    def test_clamp(self):
        s = self.make()
        s.zoom_at(0, 0.01)
        s.pan_px(10 ** 9)
        self.assertLessEqual(s.start_ms + s.visible_ms, 3_600_000 + 1)
        s.zoom_at(0, 10 ** 6)
        self.assertEqual(s.start_ms, 0)

    def test_ticks(self):
        self.assertEqual(pick_tick_step(3600), 600_000)
        self.assertGreaterEqual(pick_tick_step(0.05) / 0.05, 90)


class ProjectTests(unittest.TestCase):
    def test_save_load(self):
        p = Project(name="Buổi live 1", video_path="a.mp4", srt_path="a.srt",
                    cues=parse_srt(SAMPLE).cues)
        seg = Segment(1000, 3500, source="srt", cue_indexes=[1])
        p.segments.append(seg)
        g = p.add_group("Nhóm sản phẩm A")
        g.items.append(GroupItem(seg.id, Transition("crossfade", 700)))
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "x.livecut")
            p.save(f)
            q = Project.load(f)
        self.assertEqual(q.to_dict(), p.to_dict())
        self.assertEqual(q.groups[0].items[0].transition.kind, "crossfade")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "không có ffmpeg")
class ProbeTests(unittest.TestCase):
    def test_probe_real_clip(self):
        from services.ffprobe import probe
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "t.mp4")
            cmd = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=d=3:s=320x240:r=25",
                   "-f", "lavfi", "-i", "sine=d=3", "-shortest", "-c:v", "mpeg4", "-c:a", "aac", out]
            subprocess.run(cmd, check=True)
            info = probe(out)
        self.assertEqual((info.width, info.height), (320, 240))
        self.assertTrue(info.has_audio)
        self.assertAlmostEqual(info.fps, 25, delta=0.1)
        self.assertAlmostEqual(info.duration_ms, 3000, delta=200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
