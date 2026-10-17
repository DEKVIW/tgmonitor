from __future__ import annotations

import unittest

from app.services.pan_transfer.file_diagnosis import (
    _DiagnosisStats,
    _FileEntry,
    _build_recommended_entries,
    _build_tracked_keys,
    _extract_episode_numbers_quick,
    _full_parse_entry,
    _infer_target_relative_path,
    _prepare_quick_entries,
    _select_full_parse_candidates,
)
from app.services.pan_transfer.follow_sync import _augment_source_selection_target_relative_path


class FileDiagnosisEpisodeExtensionTests(unittest.TestCase):
    @staticmethod
    def _target_entry(name: str, relative_parent_path: str, episode: int, scan_order: int) -> _FileEntry:
        return _FileEntry(
            side="target",
            name=name,
            entry_id=str(scan_order),
            path=f"/{relative_parent_path}/{name}",
            parent_entry_id=relative_parent_path,
            parent_path=f"/{relative_parent_path}",
            parent_name=relative_parent_path.rsplit("/", 1)[-1],
            relative_parent_path=relative_parent_path,
            updated_at=None,
            size_bytes=None,
            extension=".mkv",
            scan_order=scan_order,
            quick_episode_numbers=[episode],
            accepted=True,
        )

    def test_target_path_follows_latest_contiguous_episode_directory(self) -> None:
        entries = [
            *(
                self._target_entry(f"S05E{episode}.mkv", "内容合集/上半部", episode, episode)
                for episode in range(1, 201)
            ),
            *(
                self._target_entry(f"S05E{episode}.mkv", "内容合集", episode, episode + 300)
                for episode in range(201, 215)
            ),
        ]

        self.assertEqual(_infer_target_relative_path(entries, anchor_episode=214), "内容合集")

    def test_target_path_uses_previous_contiguous_directory_for_arbitrary_names(self) -> None:
        entries = [
            self._target_entry("第200集.mkv", "第一部分", 200, 1),
            self._target_entry("第198集.mkv", "第一部分", 198, 2),
            self._target_entry("第199集.mkv", "第一部分", 199, 3),
            self._target_entry("第120集.mkv", "旧合集", 120, 4),
        ]

        self.assertEqual(_infer_target_relative_path(entries, anchor_episode=200), "第一部分")

    def test_target_path_returns_root_when_no_episode_evidence_exists(self) -> None:
        entry = _FileEntry(
            side="target",
            name="合集文件.mkv",
            entry_id="1",
            path="/内容合集/合集文件.mkv",
            parent_entry_id="内容合集",
            parent_path="/内容合集",
            parent_name="内容合集",
            relative_parent_path="内容合集",
            updated_at=None,
            size_bytes=None,
            extension=".mkv",
            scan_order=1,
        )

        self.assertIsNone(_infer_target_relative_path([entry], anchor_episode=214))

    def test_root_target_path_removes_stale_selection_subdirectory(self) -> None:
        source_selection = {
            "selection_groups": [
                {
                    "selected_count": 1,
                    "target_relative_path": "内容合集/101-200",
                }
            ],
            "selected_count": 1,
        }

        normalized = _augment_source_selection_target_relative_path(
            source_selection,
            preferred_target_relative_path=None,
            replace_existing=True,
        )

        self.assertNotIn("target_relative_path", normalized["selection_groups"][0])

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

    def test_s01e_episode_uses_semantic_parent_directory_season(self) -> None:
        entry = _FileEntry(
            side="source",
            name="凡人修仙传 S01E196 2160p.mp4",
            entry_id="196",
            path="/FANREN/年番4/凡人修仙传 S01E196 2160p.mp4",
            parent_entry_id="season-4",
            parent_path="/FANREN/年番4",
            parent_name="年番4",
            relative_parent_path="FANREN/年番4",
            updated_at=None,
            size_bytes=None,
            extension=".mp4",
            scan_order=1,
        )
        stats = _DiagnosisStats()
        tracked_keys = _build_tracked_keys({"resource_title": "凡人修仙传"})

        videos = _prepare_quick_entries(
            [entry],
            stats=stats,
            tracked_keys=tracked_keys,
            tracked_episode=195,
            tracked_season=4,
        )
        _full_parse_entry(videos[0], tracked_keys=tracked_keys, tracked_season=4)

        self.assertEqual(videos[0].quick_episode_numbers, [196])
        self.assertEqual(videos[0].quick_season, 4)
        self.assertEqual(videos[0].season, 4)
        self.assertTrue(videos[0].accepted)

    def test_s01e_episode_without_semantic_directory_has_no_season(self) -> None:
        entry = _FileEntry(
            side="source",
            name="凡人修仙传 S01E196 2160p.mp4",
            entry_id="196",
            path="/FANREN/凡人修仙传 S01E196 2160p.mp4",
            parent_entry_id="fanren",
            parent_path="/FANREN",
            parent_name="FANREN",
            relative_parent_path="FANREN",
            updated_at=None,
            size_bytes=None,
            extension=".mp4",
            scan_order=1,
        )
        stats = _DiagnosisStats()
        tracked_keys = _build_tracked_keys({"resource_title": "凡人修仙传"})

        videos = _prepare_quick_entries(
            [entry],
            stats=stats,
            tracked_keys=tracked_keys,
            tracked_episode=195,
            tracked_season=4,
        )
        _full_parse_entry(videos[0], tracked_keys=tracked_keys, tracked_season=4)

        self.assertEqual(videos[0].quick_episode_numbers, [196])
        self.assertIsNone(videos[0].quick_season)
        self.assertIsNone(videos[0].season)
        self.assertTrue(videos[0].accepted)


if __name__ == "__main__":
    unittest.main()
