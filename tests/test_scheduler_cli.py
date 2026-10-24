import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import sau_cli
from sau_commands.scheduler_config import parse_schedule_times
from sau_commands.scheduler_runner import (
    FAILED_STATUS,
    PUBLISHED_STATUS,
    _ensure_accounts,
    _update_status_fields_with_fallback,
    is_unpublished_status,
    normalize_tags,
    parse_record_date,
    should_process_record,
)


class SchedulerCliParserTests(unittest.TestCase):
    def test_scheduler_parser_accepts_run_once(self):
        parser = sau_cli.build_parser()
        args = parser.parse_args(["scheduler", "run-once", "--env-file", ".env.local"])
        self.assertEqual(args.platform, "scheduler")
        self.assertEqual(args.action, "run-once")
        self.assertEqual(args.env_file, ".env.local")

    def test_scheduler_parser_accepts_run_daily(self):
        parser = sau_cli.build_parser()
        args = parser.parse_args(["scheduler", "run-daily"])
        self.assertEqual(args.platform, "scheduler")
        self.assertEqual(args.action, "run-daily")

    def test_scheduler_parser_accepts_inspect_feishu(self):
        parser = sau_cli.build_parser()
        args = parser.parse_args(["scheduler", "inspect-feishu", "--env-file", ".env.local", "--date", "2026-10-24"])
        self.assertEqual(args.platform, "scheduler")
        self.assertEqual(args.action, "inspect-feishu")
        self.assertEqual(args.env_file, ".env.local")
        self.assertEqual(args.date, "2026-10-24")


class SchedulerDataRuleTests(unittest.TestCase):
    def setUp(self):
        self.timezone = timezone(timedelta(hours=8), name="Asia/Shanghai")

        class _Config:
            date_field = "日期"
            summary_status_field = "发布状态"
            unpublished_values = {"", "未发布"}
            timezone = timezone(timedelta(hours=8), name="Asia/Shanghai")

        self.config = _Config()

    def test_parse_schedule_times_defaults(self):
        self.assertEqual(parse_schedule_times(None), ["07:00", "17:00"])

    def test_parse_schedule_times_validates(self):
        with self.assertRaises(ValueError):
            parse_schedule_times("25:00")

    def test_normalize_tags(self):
        self.assertEqual(
            normalize_tags("#荐书 #处世智慧, 鬼谷子， 中老年阅读"),
            "荐书,处世智慧,鬼谷子,中老年阅读",
        )

    def test_parse_record_date_from_millis(self):
        value = datetime(2026, 10, 24, 9, 0, tzinfo=self.timezone).timestamp() * 1000
        self.assertEqual(parse_record_date(value, self.timezone), date(2026, 10, 24))

    def test_unpublished_status_rule(self):
        self.assertTrue(is_unpublished_status("", {"", "未发布"}))
        self.assertTrue(is_unpublished_status("未发布", {"", "未发布"}))
        self.assertFalse(is_unpublished_status(PUBLISHED_STATUS, {"", "未发布"}))
        self.assertFalse(is_unpublished_status(FAILED_STATUS, {"", "未发布"}))

    def test_should_process_record_only_today_and_unpublished(self):
        fields = {"日期": "2026-10-24", "发布状态": ""}
        self.assertTrue(should_process_record(fields, self.config, date(2026, 10, 24)))
        self.assertFalse(should_process_record(fields, self.config, date(2026, 10, 25)))
        self.assertFalse(
            should_process_record(
                {"日期": "2026-10-24", "发布状态": "已发布"},
                self.config,
                date(2026, 10, 24),
            )
        )


class SchedulerWritebackFallbackTests(unittest.TestCase):
    def test_update_status_fields_with_fallback_skips_missing_fields(self):
        calls = []

        class _FakeFeishu:
            def update_record_fields(self, record_id, fields):
                calls.append((record_id, fields))
                if len(fields) > 1:
                    raise RuntimeError("FieldNameNotFound")
                if "视频号发布状态" in fields:
                    raise RuntimeError("FieldNameNotFound")

        missing = _update_status_fields_with_fallback(
            _FakeFeishu(),
            "rec_1",
            {
                "视频号发布状态": "已发布",
                "快手发布状态": "已发布",
                "发布状态": "已发布",
            },
        )
        self.assertEqual(missing, ["视频号发布状态"])
        self.assertIn(("rec_1", {"快手发布状态": "已发布"}), calls)
        self.assertIn(("rec_1", {"发布状态": "已发布"}), calls)


class SchedulerReloginNotifyTests(unittest.IsolatedAsyncioTestCase):
    async def test_ensure_accounts_auto_relogin_and_qrcode_notify(self):
        class _Config:
            tencent_account = "creator"
            kuaishou_account = "creator"
            headless = True

        class _Notifier:
            def __init__(self):
                self.messages = []
                self.photos = []

            def send(self, text, parse_mode=None):
                self.messages.append((text, parse_mode))

            def send_photo(self, photo_path, caption="", parse_mode=None):
                self.photos.append((photo_path, caption, parse_mode))

        notifier = _Notifier()

        async def _fake_login_tencent(account_name, headless=True, qrcode_callback=None):
            self.assertEqual(account_name, "creator")
            self.assertTrue(headless)
            self.assertIsNotNone(qrcode_callback)
            qrcode_callback({"image_path": "/tmp/tencent_qr.png"})
            return {"success": True, "message": "ok"}

        async def _fake_login_kuaishou(account_name, headless=True, qrcode_callback=None):
            self.assertEqual(account_name, "creator")
            self.assertTrue(headless)
            self.assertIsNotNone(qrcode_callback)
            qrcode_callback({"image_path": "/tmp/kuaishou_qr.png"})
            return {"success": True, "message": "ok"}

        with (
            patch("sau_commands.scheduler_runner.check_tencent_account", new=AsyncMock(return_value=False)),
            patch("sau_commands.scheduler_runner.check_kuaishou_account", new=AsyncMock(return_value=False)),
            patch("sau_commands.scheduler_runner.login_tencent_account", new=AsyncMock(side_effect=_fake_login_tencent)),
            patch("sau_commands.scheduler_runner.login_kuaishou_account", new=AsyncMock(side_effect=_fake_login_kuaishou)),
        ):
            await _ensure_accounts(_Config(), notifier)

        self.assertIn(("/tmp/tencent_qr.png", "<b>视频号 登录二维码</b>", "HTML"), notifier.photos)
        self.assertIn(("/tmp/kuaishou_qr.png", "<b>快手 登录二维码</b>", "HTML"), notifier.photos)


if __name__ == "__main__":
    unittest.main()
