"""飞书多维表定时发布命令。"""
from __future__ import annotations

import asyncio

from sau_commands.scheduler_config import load_scheduler_config
from sau_commands.scheduler_runner import next_run_seconds, run_once


def register(platform_parsers):
    parser = platform_parsers.add_parser("scheduler", help="Feishu scheduled publisher")
    actions = parser.add_subparsers(dest="action", required=True)

    run_once_parser = actions.add_parser("run-once", help="Run one publish batch immediately")
    run_once_parser.add_argument("--env-file", default=".env", help="Path to env file")

    run_daily_parser = actions.add_parser("run-daily", help="Run batch on configured schedule")
    run_daily_parser.add_argument("--env-file", default=".env", help="Path to env file")


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

    raise RuntimeError(f"Unsupported scheduler action: {args.action}")
