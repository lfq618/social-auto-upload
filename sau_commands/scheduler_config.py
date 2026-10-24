"""定时发布任务的环境配置与解析。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta, timezone, tzinfo
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _read_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def parse_bool(raw_value: str | None, default: bool) -> bool:
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def parse_csv(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def parse_schedule_times(raw_value: str | None) -> list[str]:
    values = parse_csv(raw_value) if raw_value else ["07:00", "17:00"]
    parsed: list[str] = []
    for value in values:
        hour_minute = value.split(":")
        if len(hour_minute) != 2:
            raise ValueError(f"Invalid schedule time: {value}. Expected HH:MM.")
        hour, minute = hour_minute
        if not (hour.isdigit() and minute.isdigit()):
            raise ValueError(f"Invalid schedule time: {value}. Expected HH:MM.")
        hour_int = int(hour)
        minute_int = int(minute)
        if hour_int < 0 or hour_int > 23 or minute_int < 0 or minute_int > 59:
            raise ValueError(f"Invalid schedule time: {value}. Expected HH:MM.")
        parsed.append(f"{hour_int:02d}:{minute_int:02d}")
    return sorted(set(parsed))


def required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


@dataclass(slots=True)
class SchedulerConfig:
    feishu_app_id: str
    feishu_app_secret: str
    feishu_app_token: str
    feishu_table_id: str
    telegram_bot_token: str
    telegram_chat_id: str
    schedule_times: list[str]
    timezone: tzinfo
    headless: bool
    tencent_account: str
    kuaishou_account: str
    unpublished_values: set[str]
    date_field: str
    video_field: str
    summary_status_field: str
    tencent_status_field: str
    kuaishou_status_field: str
    tencent_title_field: str
    tencent_desc_field: str
    tencent_tags_field: str
    kuaishou_title_field: str
    kuaishou_desc_field: str
    kuaishou_tags_field: str


def _as_value_set(values: Iterable[str]) -> set[str]:
    return {value.strip() for value in values if value.strip()}


def load_scheduler_config(env_path: str = ".env") -> SchedulerConfig:
    _read_env_file(Path(env_path))

    timezone_name = os.getenv("SCHED_TZ", "Asia/Shanghai").strip()
    try:
        parsed_timezone: tzinfo = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        if timezone_name == "Asia/Shanghai":
            parsed_timezone = timezone(timedelta(hours=8), name="Asia/Shanghai")
        else:
            raise RuntimeError(f"Unsupported timezone in SCHED_TZ: {timezone_name}") from exc

    unpublished_defaults = {"", "未发布"}
    unpublished_values = _as_value_set(parse_csv(os.getenv("SAU_UNPUBLISHED_VALUES")))
    unpublished_values = unpublished_values or unpublished_defaults
    unpublished_values.update(unpublished_defaults)

    return SchedulerConfig(
        feishu_app_id=required_env("FEISHU_APP_ID"),
        feishu_app_secret=required_env("FEISHU_APP_SECRET"),
        feishu_app_token=required_env("FEISHU_APP_TOKEN"),
        feishu_table_id=required_env("FEISHU_TABLE_ID"),
        telegram_bot_token=required_env("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=required_env("TELEGRAM_CHAT_ID"),
        schedule_times=parse_schedule_times(os.getenv("SCHED_TIMES")),
        timezone=parsed_timezone,
        headless=parse_bool(os.getenv("SAU_HEADLESS"), True),
        tencent_account=os.getenv("SAU_TENCENT_ACCOUNT", "creator").strip() or "creator",
        kuaishou_account=os.getenv("SAU_KUAISHOU_ACCOUNT", "creator").strip() or "creator",
        unpublished_values=unpublished_values,
        date_field=os.getenv("FEISHU_FIELD_DATE", "日期").strip(),
        video_field=os.getenv("FEISHU_FIELD_VIDEO", "视频").strip(),
        summary_status_field=os.getenv("FEISHU_FIELD_STATUS", "发布状态").strip(),
        tencent_status_field=os.getenv("FEISHU_FIELD_TENCENT_STATUS", "视频号发布状态").strip(),
        kuaishou_status_field=os.getenv("FEISHU_FIELD_KUAISHOU_STATUS", "快手发布状态").strip(),
        tencent_title_field=os.getenv("FEISHU_FIELD_TENCENT_TITLE", "视频号标题").strip(),
        tencent_desc_field=os.getenv("FEISHU_FIELD_TENCENT_DESC", "视频号描述").strip(),
        tencent_tags_field=os.getenv("FEISHU_FIELD_TENCENT_TAGS", "视频号话题").strip(),
        kuaishou_title_field=os.getenv("FEISHU_FIELD_KUAISHOU_TITLE", "快手标题").strip(),
        kuaishou_desc_field=os.getenv("FEISHU_FIELD_KUAISHOU_DESC", "快手描述").strip(),
        kuaishou_tags_field=os.getenv("FEISHU_FIELD_KUAISHOU_TAGS", "快手话题").strip(),
    )
