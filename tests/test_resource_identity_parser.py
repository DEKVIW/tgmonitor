from __future__ import annotations

import unittest

from app.services.resource_identity import compare_follow_candidate, parse_resource_identity


class ResourceIdentityParserTests(unittest.TestCase):
    def test_provider_label_cannot_override_real_message_title(self) -> None:
        identity = parse_resource_identity(
            "国剧 《黑岛监狱》（2026）剧情 / 悬疑 / 犯罪 夸克网盘",
            alternate_titles=["夸克网盘"],
        )

        self.assertEqual(identity.core_title, "黑岛监狱")
        self.assertFalse(identity.should_skip_ai)

    def test_standalone_provider_label_is_not_a_work(self) -> None:
        identity = parse_resource_identity("夸克网盘")

        self.assertIsNone(identity.core_title)
        self.assertTrue(identity.should_skip_ai)
        self.assertEqual(identity.reason, "link_platform_label")

    def test_generic_episode_words_do_not_become_identity_keys(self) -> None:
        identity = parse_resource_identity(
            "月鳞绮纪 更22集",
            alternate_titles=["集", "更新"],
        )

        self.assertNotIn("集", identity.aliases)
        self.assertNotIn("更新", identity.aliases)
        self.assertNotIn("集", identity.normalized_keys)
        self.assertNotIn("更新", identity.normalized_keys)

    def test_different_works_do_not_promote_by_episode_number(self) -> None:
        tracked = parse_resource_identity("大主宰 更95集")
        candidate = parse_resource_identity("斗破苍穹 更215集")

        decision = compare_follow_candidate(tracked, candidate)

        self.assertFalse(decision.is_same_work)
        self.assertFalse(decision.should_promote)

    def test_metadata_words_do_not_become_shared_aliases(self) -> None:
        tracked = parse_resource_identity(
            "尚公主 (2026) 更至04集 60帧 类型: 剧情/爱情/古装 主演: 孟子义/李昀锐"
        )
        candidate = parse_resource_identity(
            "嫁金钗 (2026) 更至16集 60帧 类型: 剧情/爱情/古装 主演: 田曦薇/闫桉"
        )

        self.assertEqual(tracked.core_title, "尚公主")
        self.assertEqual(candidate.core_title, "嫁金钗")
        self.assertNotIn("古装 主演", tracked.aliases)
        self.assertNotIn("古装 主演", candidate.aliases)
        self.assertNotIn("古装 主演", tracked.search_queries)
        self.assertFalse(compare_follow_candidate(tracked, candidate).is_same_work)

    def test_same_core_title_replaces_same_episode_source(self) -> None:
        tracked = parse_resource_identity("尚公主 (2026) 更至04集")
        candidate = parse_resource_identity("尚公主 2026 更新04集 60帧")

        decision = compare_follow_candidate(tracked, candidate)

        self.assertTrue(decision.is_same_work)
        self.assertFalse(decision.should_promote)
        self.assertTrue(decision.same_episode_replace)

    def test_same_core_title_promotes_newer_episode(self) -> None:
        tracked = parse_resource_identity("尚公主 (2026) 更至04集")
        candidate = parse_resource_identity("尚公主 2026 更新05集")

        decision = compare_follow_candidate(tracked, candidate)

        self.assertTrue(decision.is_same_work)
        self.assertTrue(decision.is_newer)
        self.assertTrue(decision.should_promote)

    def test_same_core_title_skips_older_episode(self) -> None:
        tracked = parse_resource_identity("尚公主 (2026) 更至04集")
        candidate = parse_resource_identity("尚公主 2026 更新03集")

        decision = compare_follow_candidate(tracked, candidate)

        self.assertTrue(decision.is_same_work)
        self.assertFalse(decision.should_promote)
        self.assertFalse(decision.same_episode_replace)

    def test_core_title_suffix_is_not_the_same_work(self) -> None:
        tracked = parse_resource_identity("尚公主 (2026) 更至04集")
        candidate = parse_resource_identity("尚公主外传 (2026) 更至08集")

        decision = compare_follow_candidate(tracked, candidate)

        self.assertFalse(decision.is_same_work)
        self.assertFalse(decision.should_promote)

    def test_same_core_title_with_different_year_is_the_same_work(self) -> None:
        tracked = parse_resource_identity("边水往事 (2024) 更至16集")
        candidate = parse_resource_identity("边水往事 (2026) 更至18集")

        decision = compare_follow_candidate(tracked, candidate)

        self.assertTrue(decision.is_same_work)
        self.assertTrue(decision.should_promote)

    def test_core_title_keeps_title_punctuation_and_genre_words(self) -> None:
        cases = {
            "爱情有烟火 (2026) 更至36集完结 都市爱情 檀健次/王楚然": "爱情有烟火",
            "好，我们离婚吧 (2026) 更至E10 韩语": "好,我们离婚吧",
            "国剧 《三更雪》（2025） 夸克网盘": "三更雪",
            "国剧 《蝉》（2026）剧情 / 悬疑 / 犯罪": "蝉",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                identity = parse_resource_identity(title)
                self.assertEqual(identity.core_title, expected)

    def test_core_title_strips_collection_and_final_season_markers(self) -> None:
        self.assertEqual(
            parse_resource_identity("诛仙最终季2026 +1080 更13").core_title,
            "诛仙",
        )
        self.assertEqual(
            parse_resource_identity("一念永恒完结季2026 +1080 更17").core_title,
            "一念永恒",
        )

    def test_core_title_stops_before_quality_and_metadata_chain(self) -> None:
        cases = {
            "师兄啊师兄 4K更新至165集": ("师兄啊师兄", 165),
            "牧神记 无标 更新至107集": ("牧神记", 107),
            "尚公主 4K臻彩MAX HDR60fps 内封简繁字幕 更新至20集": ("尚公主", 20),
            "大理寺日志第3季2026 1080 更8": ("大理寺日志", 8),
            "东京复仇者 三天战争篇 東京リベンジャーズ 三天戦争編 (2026) 更至5集": ("东京复仇者 三天战争篇", 5),
        }
        for title, (expected_core, expected_episode) in cases.items():
            with self.subTest(title=title):
                identity = parse_resource_identity(title)
                self.assertEqual(identity.core_title, expected_core)
                self.assertEqual(identity.episode, expected_episode)

    def test_missing_title_is_not_invented_from_episode_or_year(self) -> None:
        for title in ("更新至160集", "（2025） 更新至162集", "年番3 (2025) 更新至187集"):
            with self.subTest(title=title):
                identity = parse_resource_identity(title)
                self.assertIsNone(identity.core_title)
                self.assertTrue(identity.needs_ai_review)

        self.assertEqual(parse_resource_identity("1921 (2021) 内封简繁").core_title, "1921")

    def test_title_ending_with_movie_or_drama_is_not_treated_as_prefix(self) -> None:
        self.assertEqual(parse_resource_identity("半个喜剧 (2019)").core_title, "半个喜剧")
        self.assertEqual(parse_resource_identity("超级马力欧银河大电影 (2026)").core_title, "超级马力欧银河大电影")

    def test_non_video_material_is_not_sent_to_title_fallback(self) -> None:
        for title in ("2027考季花生套题冲刺2期", "女生的第一堂商学课（音频完结）", "漫画 完结 《自杀岛》台版 1-17卷 PDF"):
            with self.subTest(title=title):
                identity = parse_resource_identity(title)
                self.assertFalse(identity.is_target_work)
                self.assertTrue(identity.should_skip_ai)


if __name__ == "__main__":
    unittest.main()
