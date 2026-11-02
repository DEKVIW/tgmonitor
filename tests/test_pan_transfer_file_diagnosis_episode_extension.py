from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services.pan_transfer.file_diagnosis import (
    _DiagnosisStats,
    _FileEntry,
    _build_recommended_entries,
    _build_tracked_keys,
    _extract_episode_numbers_quick,
    _format_upgrade_is_not_lower_quality,
    _full_parse_entry,
    _infer_target_relative_path,
    _pick_best_entry,
    _prepare_quick_entries,
    _select_full_parse_candidates,
)
from app.services.pan_transfer.follow_sync import _augment_source_selection_target_relative_path
from app.services.pan_transfer.follow_sync import _extract_follow_sync_materialized_episode_numbers
from app.services.pan_transfer.follow_sync import _extract_follow_sync_materialized_format_kinds_by_episode
from app.services.pan_transfer.follow_tasks import _collect_follow_automation_selected_episode_set


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

    def test_theatre_archive_without_filename_episode_is_not_selected(self) -> None:
        entry = _FileEntry(
            side="source",
            name="2026.2160p.WEB-DL.H265.AAC-PanWEB.zip",
            entry_id="theatre",
            path="/遮天 [更新至187集]/剧场版/2026.2160p.WEB-DL.H265.AAC-PanWEB.zip",
            parent_entry_id="theatre-dir",
            parent_path="/遮天 [更新至187集]/剧场版",
            parent_name="剧场版",
            relative_parent_path="遮天 [更新至187集]/剧场版",
            updated_at=None,
            size_bytes=1024 * 1024 * 1024 * 20,
            extension=".zip",
            scan_order=1,
        )
        stats = _DiagnosisStats()

        videos = _prepare_quick_entries(
            [entry],
            stats=stats,
            tracked_keys=_build_tracked_keys({"resource_title": "遮天"}),
            tracked_episode=186,
        )

        self.assertEqual(videos, [])

    def test_numbered_disguised_file_uses_filename_episode(self) -> None:
        entry = _FileEntry(
            side="source",
            name="187.zip",
            entry_id="episode-187",
            path="/遮天 [更新至186集]/187.zip",
            parent_entry_id="source-dir",
            parent_path="/遮天 [更新至186集]",
            parent_name="遮天 [更新至186集]",
            relative_parent_path="遮天 [更新至186集]",
            updated_at=None,
            size_bytes=None,
            extension=".zip",
            scan_order=1,
        )
        stats = _DiagnosisStats()
        tracked_keys = _build_tracked_keys({"resource_title": "遮天"})

        videos = _prepare_quick_entries(
            [entry],
            stats=stats,
            tracked_keys=tracked_keys,
            tracked_episode=186,
        )
        _full_parse_entry(videos[0], tracked_keys=tracked_keys, tracked_season=None)

        self.assertEqual(videos[0].quick_episode_numbers, [187])
        self.assertEqual(videos[0].episode_numbers, [187])
        self.assertTrue(videos[0].accepted)

    def test_same_episode_selection_does_not_use_file_size(self) -> None:
        now = datetime(2026, 4, 18, 12, 0, 0)
        newer_smaller = _FileEntry(
            side="source",
            name="遮天 S01E187 1080p.mp4",
            entry_id="newer",
            path="/遮天 S01E187 1080p.mp4",
            parent_entry_id=None,
            parent_path=None,
            parent_name=None,
            relative_parent_path=None,
            updated_at=now,
            size_bytes=1,
            extension=".mp4",
            scan_order=1,
            episode_numbers=[187],
            quick_episode_numbers=[187],
            accepted=True,
        )
        older_larger = _FileEntry(
            side="source",
            name="剧场版 2026.2160p.zip",
            entry_id="older",
            path="/剧场版 2026.2160p.zip",
            parent_entry_id=None,
            parent_path=None,
            parent_name=None,
            relative_parent_path=None,
            updated_at=now - timedelta(days=1),
            size_bytes=1024 * 1024 * 1024 * 100,
            extension=".zip",
            scan_order=2,
            episode_numbers=[187],
            quick_episode_numbers=[187],
            accepted=True,
        )

        self.assertIs(_pick_best_entry([newer_smaller, older_larger]), newer_smaller)

    def test_same_episode_prefers_explicit_higher_quality_over_native_format(self) -> None:
        native_1080 = _FileEntry(
            side="source",
            name="22.mkv",
            entry_id="native",
            path="/22.mkv",
            parent_entry_id=None,
            parent_path=None,
            parent_name=None,
            relative_parent_path=None,
            updated_at=None,
            size_bytes=None,
            extension=".mkv",
            scan_order=1,
            episode_numbers=[22],
            quick_episode_numbers=[22],
            quality_tags=["1080P"],
            accepted=True,
        )
        disguised_4k = _FileEntry(
            side="source",
            name="S01E22.2160p.HDR.zip",
            entry_id="disguised",
            path="/S01E22.2160p.HDR.zip",
            parent_entry_id=None,
            parent_path=None,
            parent_name=None,
            relative_parent_path=None,
            updated_at=None,
            size_bytes=None,
            extension=".zip",
            scan_order=2,
            episode_numbers=[22],
            quick_episode_numbers=[22],
            quality_tags=["4K", "HDR"],
            accepted=True,
        )

        self.assertIs(_pick_best_entry([native_1080, disguised_4k]), disguised_4k)

    def test_playable_format_upgrade_does_not_lower_quality(self) -> None:
        current_4k_archive = _FileEntry(
            side="target",
            name="22.zip",
            entry_id="current",
            path="/22.zip",
            parent_entry_id=None,
            parent_path=None,
            parent_name=None,
            relative_parent_path=None,
            updated_at=None,
            size_bytes=None,
            scan_order=1,
            extension=".zip",
            quality_tags=["4K"],
            episode_numbers=[22],
            quick_episode_numbers=[22],
            accepted=True,
        )
        candidate_1080_video = _FileEntry(
            side="source",
            name="22.mkv",
            entry_id="candidate",
            path="/22.mkv",
            parent_entry_id=None,
            parent_path=None,
            parent_name=None,
            relative_parent_path=None,
            updated_at=None,
            size_bytes=None,
            scan_order=2,
            extension=".mkv",
            quality_tags=["1080P"],
            episode_numbers=[22],
            quick_episode_numbers=[22],
            accepted=True,
        )

        self.assertFalse(_format_upgrade_is_not_lower_quality(candidate_1080_video, current_4k_archive))

    def test_playable_format_upgrade_can_use_candidate_title_resolution(self) -> None:
        current_4k_archive = _FileEntry(
            side="target",
            name="22.zip",
            entry_id="current",
            path="/22.zip",
            parent_entry_id=None,
            parent_path=None,
            parent_name=None,
            relative_parent_path=None,
            updated_at=None,
            size_bytes=None,
            scan_order=1,
            extension=".zip",
            quality_tags=["4K"],
            episode_numbers=[22],
            quick_episode_numbers=[22],
            accepted=True,
        )
        candidate_native_video_without_quality_tag = _FileEntry(
            side="source",
            name="22.mkv",
            entry_id="candidate",
            path="/22.mkv",
            parent_entry_id=None,
            parent_path=None,
            parent_name=None,
            relative_parent_path=None,
            updated_at=None,
            size_bytes=None,
            scan_order=2,
            extension=".mkv",
            quality_tags=[],
            episode_numbers=[22],
            quick_episode_numbers=[22],
            accepted=True,
        )

        self.assertTrue(
            _format_upgrade_is_not_lower_quality(
                candidate_native_video_without_quality_tag,
                current_4k_archive,
                candidate_quality_tags=["4K"],
            )
        )
        self.assertFalse(
            _format_upgrade_is_not_lower_quality(
                candidate_native_video_without_quality_tag,
                current_4k_archive,
            )
        )

    def test_source_disguised_video_does_not_require_parent_title_match(self) -> None:
        entry = _FileEntry(
            side="source",
            name="2026.S01E22.2160p.HDR.60fps.10bit.DDP5.1-PanWEB.zip",
            entry_id="episode-22",
            path="/S 尙厷炷 [更新至22集]/2026.S01E22.2160p.HDR.60fps.10bit.DDP5.1-PanWEB.zip",
            parent_entry_id="source-dir",
            parent_path="/S 尙厷炷 [更新至22集]",
            parent_name="S 尙厷炷 [更新至22集]",
            relative_parent_path="S 尙厷炷 [更新至22集]",
            updated_at=None,
            size_bytes=None,
            extension=".zip",
            scan_order=1,
        )
        stats = _DiagnosisStats()

        videos = _prepare_quick_entries(
            [entry],
            stats=stats,
            tracked_keys=_build_tracked_keys({"resource_title": "尚公主"}),
            tracked_episode=22,
        )

        self.assertEqual([item.quick_episode_numbers for item in videos], [[22]])
        self.assertEqual(videos[0].quality_tags, ["4K", "HDR", "60FPS", "10BIT", "DDP5.1"])

    def test_materialized_progress_does_not_read_episode_from_parent_path(self) -> None:
        item = SimpleNamespace(
            extra_json={
                "source_selection": {
                    "selection_groups": [
                        {
                            "selected_entries": [
                                {
                                    "name": "2026.2160p.WEB-DL.H265.AAC-PanWEB.zip",
                                    "path": "/遮天 [更新至187集]/剧场版/2026.2160p.WEB-DL.H265.AAC-PanWEB.zip",
                                }
                            ]
                        }
                    ]
                }
            }
        )

        episodes, selected_count = _extract_follow_sync_materialized_episode_numbers(item)

        self.assertEqual(episodes, [])
        self.assertEqual(selected_count, 1)

    def test_materialized_format_kind_is_recorded_per_episode(self) -> None:
        item = SimpleNamespace(
            extra_json={
                "source_selection": {
                    "selected_count": 2,
                    "selection_groups": [
                        {
                            "selected_entries": [
                                {
                                    "name": "22.zip",
                                    "format_kind": "disguised_video",
                                    "episode_numbers": [22],
                                },
                                {
                                    "name": "23.mkv",
                                    "format_kind": "native_video",
                                    "episode_numbers": [23],
                                },
                            ]
                        }
                    ],
                }
            }
        )

        self.assertEqual(
            _extract_follow_sync_materialized_format_kinds_by_episode(item),
            {"22": ["disguised_video"], "23": ["native_video"]},
        )

    def test_automation_selection_does_not_read_episode_from_parent_path(self) -> None:
        groups = [
            {
                "selected_entries": [
                    {
                        "name": "2026.2160p.WEB-DL.H265.AAC-PanWEB.zip",
                        "path": "/遮天 [更新至187集]/剧场版/2026.2160p.WEB-DL.H265.AAC-PanWEB.zip",
                    }
                ]
            }
        ]

        self.assertEqual(_collect_follow_automation_selected_episode_set(groups), set())

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

    def test_source_explicit_episode_does_not_require_title_or_parent_context(self) -> None:
        entry = _FileEntry(
            side="source",
            name="S01E186.2026.2160p.WEB-DL.H265.AAC5.1.mp4",
            entry_id="186",
            path="/S01E186.2026.2160p.WEB-DL.H265.AAC5.1.mp4",
            parent_entry_id=None,
            parent_path=None,
            parent_name=None,
            relative_parent_path=None,
            updated_at=None,
            size_bytes=None,
            extension=".mp4",
            scan_order=1,
        )
        stats = _DiagnosisStats()
        tracked_keys = _build_tracked_keys({"resource_title": "混淆作品"})

        videos = _prepare_quick_entries(
            [entry],
            stats=stats,
            tracked_keys=tracked_keys,
            tracked_episode=185,
            tracked_season=4,
        )
        _full_parse_entry(videos[0], tracked_keys=tracked_keys, tracked_season=4)

        recommended_entries, recommended_episodes, stop_reason = _build_recommended_entries(
            videos,
            anchor_episode=185,
            inferred_target_relative_path=None,
        )

        self.assertEqual(videos[0].episode_numbers, [186])
        self.assertTrue(videos[0].accepted)
        self.assertEqual(videos[0].parse_reason, "source_explicit_episode")
        self.assertEqual([entry.name for entry in recommended_entries], [videos[0].name])
        self.assertEqual(recommended_episodes, [186])
        self.assertEqual(stop_reason, "contiguous_window_hit")

    def test_target_explicit_episode_without_title_stays_strict(self) -> None:
        entry = _FileEntry(
            side="target",
            name="S01E186.2026.2160p.WEB-DL.H265.AAC5.1.mp4",
            entry_id="186",
            path="/S01E186.2026.2160p.WEB-DL.H265.AAC5.1.mp4",
            parent_entry_id=None,
            parent_path=None,
            parent_name=None,
            relative_parent_path=None,
            updated_at=None,
            size_bytes=None,
            extension=".mp4",
            scan_order=1,
        )
        stats = _DiagnosisStats()
        videos = _prepare_quick_entries(
            [entry],
            stats=stats,
            tracked_keys=_build_tracked_keys({"resource_title": "混淆作品"}),
            tracked_episode=185,
            tracked_season=4,
        )
        _full_parse_entry(videos[0], tracked_keys=_build_tracked_keys({"resource_title": "混淆作品"}), tracked_season=4)

        self.assertFalse(videos[0].accepted)
        self.assertEqual(videos[0].parse_reason, "full_unmatched")

    def test_source_explicit_episode_ignores_untrusted_parent_season(self) -> None:
        entry = _FileEntry(
            side="source",
            name="S01E186.2026.2160p.WEB-DL.H265.AAC5.1.mp4",
            entry_id="186",
            path="/第5季/S01E186.2026.2160p.WEB-DL.H265.AAC5.1.mp4",
            parent_entry_id="season-5",
            parent_path="/第5季",
            parent_name="第5季",
            relative_parent_path="第5季",
            updated_at=None,
            size_bytes=None,
            extension=".mp4",
            scan_order=1,
        )
        stats = _DiagnosisStats()
        videos = _prepare_quick_entries(
            [entry],
            stats=stats,
            tracked_keys=_build_tracked_keys({"resource_title": "混淆作品"}),
            tracked_episode=185,
            tracked_season=4,
        )
        _full_parse_entry(videos[0], tracked_keys=_build_tracked_keys({"resource_title": "混淆作品"}), tracked_season=4)

        self.assertTrue(videos[0].accepted)
        self.assertEqual(videos[0].parse_reason, "source_explicit_episode")


if __name__ == "__main__":
    unittest.main()
