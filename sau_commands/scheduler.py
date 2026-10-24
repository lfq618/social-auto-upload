"""飞书多维表定时发布命令。"""
from __future__ import annotations

import asyncio
from datetime import datetime

from sau_commands.scheduler_config import load_scheduler_config
from sau_commands.scheduler_feishu import FeishuBitableClient
from sau_commands.scheduler_runner import next_run_seconds, parse_record_date, run_once, should_process_record


def register(platform_parsers):
    parser = platform_parsers.add_parser("scheduler", help="Feishu scheduled publisher")
    actions = parser.add_subparsers(dest="action", required=True)

    run_once_parser = actions.add_parser("run-once", help="Run one publish batch immediately")
    run_once_parser.add_argument("--env-file", default=".env", help="Path to env file")

    run_daily_parser = actions.add_parser("run-daily", help="Run batch on configured schedule")
    run_daily_parser.add_argument("--env-file", default=".env", help="Path to env file")

    inspect_feishu_parser = actions.add_parser(
        "inspect-feishu",
        help="Inspect Feishu records and scheduler hit rules without publishing",
    )
    inspect_feishu_parser.add_argument("--env-file", default=".env", help="Path to env file")
    inspect_feishu_parser.add_argument(
        "--date",
        help="Target date in YYYY-MM-DD. Default is today in scheduler timezone.",
    )


def _strip_text(raw_value) -> str:
    if raw_value is None:
        return ""
    return raw_value.strip() if isinstance(raw_value, str) else str(raw_value).strip()


def _resolve_target_date(date_text: str | None, timezone):
    if not date_text:
        return datetime.now(timezone).date()
    try:
        return datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise RuntimeError(f"Invalid --date value: {date_text}. Expected YYYY-MM-DD.") from exc


def _build_skip_reason(parsed_date, target_date, summary_status: str, unpublished_values: set[str]) -> str:
    if parsed_date != target_date:
        return "date_mismatch"
    if summary_status not in unpublished_values:
        return "status_filtered"
    return "selected"


async def _inspect_feishu(env_file: str, date_text: str | None) -> int:
    config = load_scheduler_config(env_file)
    target_date = _resolve_target_date(date_text, config.timezone)

    feishu = FeishuBitableClient(
        app_id=config.feishu_app_id,
        app_secret=config.feishu_app_secret,
        app_token=config.feishu_app_token,
        table_id=config.feishu_table_id,
    )
    records = feishu.list_records()
    print(
        f"inspect-feishu target_date={target_date} scanned={len(records)} "
        f"date_field={config.date_field} status_field={config.summary_status_field} "
        f"unpublished_values={sorted(config.unpublished_values)}"
    )

    selected_count = 0
    for index, record in enumerate(records, start=1):
        record_id = str(record.get("record_id") or "")
        fields = record.get("fields") or {}
        raw_date = fields.get(config.date_field)
        parsed_date = parse_record_date(raw_date, config.timezone)
        summary_status = _strip_text(fields.get(config.summary_status_field))
        selected = should_process_record(fields, config, target_date)
        if selected:
            selected_count += 1
        reason = _build_skip_reason(parsed_date, target_date, summary_status, config.unpublished_values)
        print(
            f"[{index}] record_id={record_id} raw_date={raw_date!r} parsed_date={parsed_date} "
            f"status={summary_status!r} selected={selected} reason={reason}"
        )
    print(f"inspect-feishu completed: selected={selected_count}, skipped={len(records) - selected_count}")
    return 0


async def _run_daily(env_file: str) -> int:
    config = load_scheduler_config(env_file)
    while True:
        wait_seconds = next_run_seconds(config.schedule_times, config.timezone)
        await asyncio.sleep(wait_seconds)
        await run_once(config)


async def run(args):
    if args.action == "run-once":
        config = load_scheduler_config(args.env_file)
        summary = await run_once(config)
        print(
            f"scheduler run-once completed: scanned={summary.scanned_records}, "
            f"processed={summary.processed_records}, success={summary.success_records}, failed={summary.failed_records}"
        )
        return 0

    if args.action == "run-daily":
        return await _run_daily(args.env_file)

    if args.action == "inspect-feishu":
        return await _inspect_feishu(args.env_file, args.date)

    raise RuntimeError(f"Unsupported scheduler action: {args.action}")
