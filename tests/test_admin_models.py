from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.schemas.admin_models import (
    BulkUsernamesRequest,
    ChannelCreate,
    LinkCheckTaskCreate,
    LinkCleanupApplyRequest,
    SystemConfigUpdate,
    UserCreate,
)


class AdminModelsTestCase(unittest.TestCase):
    def test_channel_create_normalizes_telegram_urls(self) -> None:
        model = ChannelCreate(username=" https://t.me/+AbCdEf123456 ")
        self.assertEqual(model.username, "+AbCdEf123456")

        model = ChannelCreate(username="@example_channel")
        self.assertEqual(model.username, "example_channel")

    def test_bulk_usernames_request_trims_and_deduplicates(self) -> None:
        model = BulkUsernamesRequest(usernames=[" alice ", "bob", "alice", "bob "])
        self.assertEqual(model.usernames, ["alice", "bob"])

    def test_channel_create_accepts_supported_parser_profile(self) -> None:
        model = ChannelCreate(username="@movie_channel", parser_profile="movie_default")
        self.assertEqual(model.username, "movie_channel")
        self.assertEqual(model.parser_profile, "movie_default")

    def test_channel_create_treats_auto_parser_profile_as_none(self) -> None:
        model = ChannelCreate(username="demo", parser_profile=" auto ")
        self.assertIsNone(model.parser_profile)

    def test_channel_create_rejects_unknown_parser_profile(self) -> None:
        with self.assertRaises(ValidationError):
            ChannelCreate(username="demo", parser_profile="unknown_profile")

    def test_link_check_task_create_validates_concurrency(self) -> None:
        with self.assertRaises(ValidationError):
            LinkCheckTaskCreate(period="today", max_concurrent=0)

    def test_link_cleanup_request_validates_mode(self) -> None:
        with self.assertRaises(ValidationError):
            LinkCleanupApplyRequest(mode="delete_everything")

    def test_system_config_update_rejects_default_concurrency_above_max(self) -> None:
        with self.assertRaises(ValidationError):
            SystemConfigUpdate(
                public_dashboard_enabled=True,
                public_ads_enabled=False,
                public_feed_top_ad_html_desktop="",
            public_feed_top_ad_html_mobile="",
            public_feed_inline_ad_html_desktop="",
            public_feed_inline_ad_html_mobile="",
            public_feed_inline_every_n=8,
            umami_enabled=False,
            umami_script_url="",
            umami_website_id="",
            umami_host_url="",
            umami_share_url="",
            link_check_default_max_concurrent=6,
            link_check_max_allowed_concurrent=5,
            link_check_max_allowed_links=1000,
            link_check_poll_interval_seconds=2,
            monitor_channel_refresh_interval_seconds=60,
                monitor_db_write_max_retries=3,
                monitor_db_write_retry_delay_seconds=1.0,
            )

    def test_system_config_update_trims_ad_html_fields(self) -> None:
        model = SystemConfigUpdate(
            site_name="  片库雷达  ",
            site_title="  片库雷达 - 频道监控  ",
            site_description="  一个站点描述  ",
            site_keywords="  影视,网盘,监控  ",
            brand_icon="  🎬  ",
            site_favicon_url=" /favicon-movie.svg ",
            public_dashboard_enabled=True,
            public_ads_enabled=True,
            public_feed_top_ad_html_desktop="  <a>desktop</a>  ",
            public_feed_top_ad_html_mobile="  ",
            public_feed_inline_ad_html_desktop="\n<a>inline</a>\n",
            public_feed_inline_ad_html_mobile="",
            public_feed_inline_every_n=6,
            umami_enabled=True,
            umami_script_url="  https://analytics.example.com/script.js  ",
            umami_website_id="  website-id  ",
            umami_host_url=" https://analytics.example.com ",
            umami_share_url=" https://analytics.example.com/share/abc ",
            link_check_default_max_concurrent=5,
            link_check_max_allowed_concurrent=10,
            link_check_max_allowed_links=1000,
            link_check_poll_interval_seconds=2,
            monitor_channel_refresh_interval_seconds=60,
            monitor_db_write_max_retries=3,
            monitor_db_write_retry_delay_seconds=1.0,
        )

        self.assertEqual(model.public_feed_top_ad_html_desktop, "<a>desktop</a>")
        self.assertEqual(model.public_feed_top_ad_html_mobile, "")
        self.assertEqual(model.public_feed_inline_ad_html_desktop, "<a>inline</a>")
        self.assertEqual(model.site_name, "片库雷达")
        self.assertEqual(model.site_title, "片库雷达 - 频道监控")
        self.assertEqual(model.site_description, "一个站点描述")
        self.assertEqual(model.site_keywords, "影视,网盘,监控")
        self.assertEqual(model.brand_icon, "🎬")
        self.assertEqual(model.site_favicon_url, "/favicon-movie.svg")
        self.assertEqual(model.umami_script_url, "https://analytics.example.com/script.js")
        self.assertEqual(model.umami_website_id, "website-id")
        self.assertEqual(model.umami_host_url, "https://analytics.example.com")
        self.assertEqual(model.umami_share_url, "https://analytics.example.com/share/abc")

    def test_system_config_update_allows_large_inline_interval(self) -> None:
        model = SystemConfigUpdate(
            public_dashboard_enabled=True,
            public_ads_enabled=True,
            public_feed_top_ad_html_desktop="",
            public_feed_top_ad_html_mobile="",
            public_feed_inline_ad_html_desktop="",
            public_feed_inline_ad_html_mobile="",
            public_feed_inline_every_n=120,
            umami_enabled=False,
            umami_script_url="",
            umami_website_id="",
            umami_host_url="",
            umami_share_url="",
            link_check_default_max_concurrent=5,
            link_check_max_allowed_concurrent=10,
            link_check_max_allowed_links=1000,
            link_check_poll_interval_seconds=2,
            monitor_channel_refresh_interval_seconds=60,
            monitor_db_write_max_retries=3,
            monitor_db_write_retry_delay_seconds=1.0,
        )

        self.assertEqual(model.public_feed_inline_every_n, 120)

    def test_system_config_update_requires_umami_fields_when_enabled(self) -> None:
        with self.assertRaises(ValidationError):
            SystemConfigUpdate(
                public_dashboard_enabled=True,
                public_ads_enabled=False,
                public_feed_top_ad_html_desktop="",
                public_feed_top_ad_html_mobile="",
                public_feed_inline_ad_html_desktop="",
                public_feed_inline_ad_html_mobile="",
                public_feed_inline_every_n=8,
                umami_enabled=True,
                umami_script_url="",
                umami_website_id="",
                umami_host_url="",
                umami_share_url="",
                link_check_default_max_concurrent=5,
                link_check_max_allowed_concurrent=10,
                link_check_max_allowed_links=1000,
                link_check_poll_interval_seconds=2,
                monitor_channel_refresh_interval_seconds=60,
                monitor_db_write_max_retries=3,
                monitor_db_write_retry_delay_seconds=1.0,
            )

    def test_system_config_update_rejects_invalid_umami_url(self) -> None:
        with self.assertRaises(ValidationError):
            SystemConfigUpdate(
                public_dashboard_enabled=True,
                public_ads_enabled=False,
                public_feed_top_ad_html_desktop="",
                public_feed_top_ad_html_mobile="",
                public_feed_inline_ad_html_desktop="",
                public_feed_inline_ad_html_mobile="",
                public_feed_inline_every_n=8,
                umami_enabled=True,
                umami_script_url="analytics.example.com/script.js",
                umami_website_id="website-id",
                umami_host_url="",
                umami_share_url="",
                link_check_default_max_concurrent=5,
                link_check_max_allowed_concurrent=10,
                link_check_max_allowed_links=1000,
                link_check_poll_interval_seconds=2,
                monitor_channel_refresh_interval_seconds=60,
                monitor_db_write_max_retries=3,
                monitor_db_write_retry_delay_seconds=1.0,
            )

    def test_system_config_update_rejects_invalid_site_favicon_url(self) -> None:
        with self.assertRaises(ValidationError):
            SystemConfigUpdate(
                site_favicon_url="favicon.ico",
                public_dashboard_enabled=True,
                public_ads_enabled=False,
                public_feed_top_ad_html_desktop="",
                public_feed_top_ad_html_mobile="",
                public_feed_inline_ad_html_desktop="",
                public_feed_inline_ad_html_mobile="",
                public_feed_inline_every_n=8,
                umami_enabled=False,
                umami_script_url="",
                umami_website_id="",
                umami_host_url="",
                umami_share_url="",
                link_check_default_max_concurrent=5,
                link_check_max_allowed_concurrent=10,
                link_check_max_allowed_links=1000,
                link_check_poll_interval_seconds=2,
                monitor_channel_refresh_interval_seconds=60,
                monitor_db_write_max_retries=3,
                monitor_db_write_retry_delay_seconds=1.0,
            )

    def test_user_create_rejects_space_in_username(self) -> None:
        with self.assertRaises(ValidationError):
            UserCreate(username="bad user", password="secret123")


if __name__ == "__main__":
    unittest.main()
