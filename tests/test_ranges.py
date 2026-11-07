import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from editor.ranges import SequenceTracker, apply_order, build_ranges, cut_cues, range_key, total_ms
from subtitle.srt import Cue


def cue(i, s, e, text="x"):
    return Cue(i, s, e, text)


class BuildRangesTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(build_ranges([]), [])

    def test_padding_and_clamp(self):
        r = build_ranges([cue(1, 100, 1000)], 300, 300, duration_ms=1100)
        self.assertEqual((r[0].start_ms, r[0].end_ms), (0, 1100))

    def test_sorted_by_time_regardless_of_selection_order(self):
        r = build_ranges([cue(2, 50_000, 52_000), cue(1, 10_000, 12_000)], 0, 0)
        self.assertEqual([x.start_ms for x in r], [10_000, 50_000])

    def test_overlapping_padding_merges(self):
        r = build_ranges([cue(1, 10_000, 12_000), cue(2, 12_400, 14_000)], 300, 300)
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0].start_ms, r[0].end_ms), (9_700, 14_300))
        self.assertEqual(r[0].cue_indexes, [1, 2])

    def test_far_cues_stay_separate(self):
        r = build_ranges([cue(1, 10_000, 12_000), cue(2, 60_000, 62_000)], 300, 300)
        self.assertEqual(len(r), 2)
        self.assertEqual(total_ms(r), 2 * 2_600)

    def test_invalid_cue_ignored(self):
        self.assertEqual(build_ranges([cue(1, 5000, 5000), cue(2, 6000, 5000)]), [])


class SequenceTrackerTests(unittest.TestCase):
    def setUp(self):
        self.t = SequenceTracker([(10_000, 12_000), (50_000, 52_000)])

    def test_plays_through_and_advances(self):
        self.assertEqual(self.t.begin(0), 10_000)
        self.assertEqual(self.t.on_position(9_000)[0], "none")          # còn gần đầu đoạn
        self.assertEqual(self.t.on_position(10_100), ("none", -1))
        self.assertEqual(self.t.on_position(11_500), ("none", -1))
        self.assertEqual(self.t.on_position(11_980), ("goto", 1))

    def test_ignores_stale_position_while_settling(self):
        self.t.begin(0)
        self.t.on_position(10_200)
        self.t.on_position(11_990)                                       # -> goto 1
        self.assertEqual(self.t.begin(1), 50_000)
        self.assertEqual(self.t.on_position(11_995), ("none", -1))       # vị trí cũ còn sót: bỏ qua, không nhảy tiếp
        self.assertEqual(self.t.on_position(50_050), ("none", -1))       # đã tới đoạn mới
        self.assertEqual(self.t.on_position(51_990), ("done", -1))

    def test_user_seek_away_stops(self):
        self.t.begin(0)
        self.t.on_position(10_100)
        self.assertEqual(self.t.on_position(300_000), ("stop", -1))

    def test_single_range_done(self):
        t = SequenceTracker([(1_000, 2_000)])
        t.begin(0)
        t.on_position(1_050)
        self.assertEqual(t.on_position(1_990), ("done", -1))


class OrderTests(unittest.TestCase):
    def ranges(self):
        return build_ranges([cue(1, 10_000, 12_000), cue(2, 60_000, 62_000), cue(3, 120_000, 121_000)], 0, 0)

    def test_empty_order_is_chronological(self):
        self.assertEqual([range_key(r) for r in apply_order(self.ranges(), [])], [1, 2, 3])

    def test_custom_order(self):
        self.assertEqual([range_key(r) for r in apply_order(self.ranges(), [3, 1, 2])], [3, 1, 2])

    def test_new_range_appended_and_stale_keys_ignored(self):
        got = apply_order(self.ranges(), [3, 99, 1])          # 99 không còn; 2 là đoạn mới
        self.assertEqual([range_key(r) for r in got], [3, 1, 2])

    def test_duplicate_keys_do_not_duplicate_ranges(self):
        self.assertEqual(len(apply_order(self.ranges(), [1, 1, 2, 3])), 3)

    def test_project_roundtrip_keeps_order_and_marks(self):
        from project.model import Project
        pr = Project(cues=[cue(1, 0, 1000), cue(2, 2000, 3000)], order=[2, 1])
        pr.cues[1].mark = "selected"
        back = Project.from_dict(pr.to_dict())
        self.assertEqual(back.order, [2, 1])
        self.assertEqual(back.cues[1].mark, "selected")

    def test_old_project_without_order_loads(self):
        from project.model import Project
        d = Project().to_dict()
        d.pop("order")
        self.assertEqual(Project.from_dict(d).order, [])


class CutCuesTests(unittest.TestCase):
    def test_times_shift_by_output_position(self):
        cues = [cue(1, 10_000, 12_000, "a"), cue(2, 60_000, 62_000, "b")]
        out = cut_cues([(9_700, 12_300), (59_700, 62_300)], cues, {1, 2})
        self.assertEqual([(c.start_ms, c.end_ms, c.text) for c in out],
                         [(300, 2_300, "a"), (2_600 + 300, 2_600 + 2_300, "b")])
        self.assertEqual([c.index for c in out], [1, 2])

    def test_follows_custom_order(self):
        cues = [cue(1, 10_000, 12_000, "a"), cue(2, 60_000, 62_000, "b")]
        out = cut_cues([(60_000, 62_000), (10_000, 12_000)], cues, {1, 2})
        self.assertEqual([c.text for c in out], ["b", "a"])
        self.assertEqual(out[1].start_ms, 2_000)

    def test_neighbor_in_padding_only_dropped_if_too_short(self):
        cues = [cue(1, 10_000, 12_000, "chosen"), cue(2, 12_100, 14_000, "neighbor")]
        out = cut_cues([(9_700, 12_400)], cues, {1})           # neighbor chỉ lọt 300 ms
        self.assertEqual([c.text for c in out], ["chosen", "neighbor"])
        out = cut_cues([(9_700, 12_200)], cues, {1})           # neighbor chỉ lọt 100 ms -> bỏ
        self.assertEqual([c.text for c in out], ["chosen"])

    def test_clipped_to_range(self):
        out = cut_cues([(10_500, 11_000)], [cue(1, 10_000, 12_000, "a")], {1})
        self.assertEqual((out[0].start_ms, out[0].end_ms), (0, 500))


if __name__ == "__main__":
    unittest.main()
