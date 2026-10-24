import unittest
from datetime import date, datetime, timedelta, timezone

import sau_cli
from sau_commands.scheduler_config import parse_schedule_times
from sau_commands.scheduler_runner import (
    FAILED_STATUS,
    PUBLISHED_STATUS,
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


if __name__ == "__main__":
    unittest.main()
