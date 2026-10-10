from __future__ import annotations

import unittest

from app.services.pan_transfer.file_diagnosis import (
    _DiagnosisStats,
    _FileEntry,
    _build_recommended_entries,
    _build_tracked_keys,
    _extract_episode_numbers_quick,
    _full_parse_entry,
    _prepare_quick_entries,
    _select_full_parse_candidates,
)


class FileDiagnosisEpisodeExtensionTests(unittest.TestCase):
    def test_video_extension_digits_are_not_parsed_as_episode_numbers(self) -> None:
        for filename, episode in (("31.mp4", 31), ("42.mp4", 42), ("43.mp4", 43)):
            with self.subTest(filename=filename):
                self.assertEqual(_extract_episode_numbers_quick(filename), [episode])

    def test_episode_label_is_preserved_before_video_extension(self) -> None:
        self.assertEqual(_extract_episode_numbers_quick("光阴之外 第43集.mp4"), [43])

    def test_leading_episode_is_not_confused_with_concatenated_quality_metadata(self) -> None:
        filenames = (
            ("35 4KHQHDR10 无人在意.mp4", 35),
            ("42 4KHQ.mp4", 42),
            ("43 4KHQ.mp4", 43),
        )
        for filename, episode in filenames:
            with self.subTest(filename=filename):
                self.assertEqual(_extract_episode_numbers_quick(filename), [episode])

    def test_quality_metadata_digits_are_not_guessed_as_episode_numbers(self) -> None:
        self.assertEqual(_extract_episode_numbers_quick("4KHQHDR10 无人在意.mp4"), [])
        self.assertEqual(_extract_episode_numbers_quick("光阴之外 HDR10 4K.mp4"), [])

    def test_candidate_range_recommends_episode_after_current_anchor(self) -> None:
        file_names = [
            *(f"{episode} 4KHQHDR10 无人在意.mp4" for episode in range(35, 42)),
            "42 4KHQ.mp4",
            "43 4KHQ.mp4",
        ]
        entries = [
            _FileEntry(
                side="source",
                name=name,
                entry_id=str(index),
                path=f"/{name}",
                parent_entry_id="source-dir",
                parent_path="/",
                parent_name="G.Y.Z.W.夸克。审核，是大傻比",
                relative_parent_path="G.Y.Z.W.夸克。审核，是大傻比",
                updated_at=None,
                size_bytes=None,
                extension=".mp4",
                scan_order=index,
            )
            for index, name in enumerate(file_names)
        ]
        tracked_keys = _build_tracked_keys({"resource_title": "光阴之外"})
        stats = _DiagnosisStats()
        videos = _prepare_quick_entries(
            entries,
            stats=stats,
            tracked_keys=tracked_keys,
            tracked_episode=42,
            tracked_season=None,
        )
        full_parse_candidates = _select_full_parse_candidates(
            videos,
            tracked_episode=42,
            near_episode_window=5,
            stats=stats,
        )
        for entry in full_parse_candidates:
            _full_parse_entry(entry, tracked_keys=tracked_keys, tracked_season=None)

        _recommended_entries, recommended_episodes, stop_reason = _build_recommended_entries(
            videos,
            anchor_episode=42,
            inferred_target_relative_path=None,
        )

        self.assertEqual(recommended_episodes, [43])
        self.assertEqual(stop_reason, "contiguous_window_hit")


if __name__ == "__main__":
    unittest.main()
