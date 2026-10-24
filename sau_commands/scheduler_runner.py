"""飞书 -> 平台发布 -> 回写 -> 通知 的编排逻辑。"""
from __future__ import annotations

import asyncio
import html
import traceback
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from sau_commands.kuaishou import (
    KuaishouVideoUploadRequest,
    check_kuaishou_account,
    login_kuaishou_account,
    upload_kuaishou_video,
)
from sau_commands.scheduler_config import SchedulerConfig
from sau_commands.scheduler_feishu import FeishuBitableClient
from sau_commands.scheduler_telegram import TelegramNotifier
from sau_commands.tencent import (
    TencentVideoUploadRequest,
    check_tencent_account,
    login_tencent_account,
    upload_tencent_video,
)


PUBLISHED_STATUS = "已发布"
FAILED_STATUS = "发布失败"


@dataclass(slots=True)
class PublishOutcome:
    status: str
    error: str = ""


@dataclass(slots=True)
class RecordRunResult:
    record_id: str
    summary_status: str
    tencent_status: str
    kuaishou_status: str
    tencent_error: str = ""
    kuaishou_error: str = ""


def _strip_text(raw_value: Any) -> str:
    if raw_value is None:
        return ""
    if isinstance(raw_value, str):
        return raw_value.strip()
    return str(raw_value).strip()


def normalize_tags(raw_value: Any) -> str:
    text = _strip_text(raw_value)
    if not text:
        return ""

    items: list[str] = []
    for chunk in text.replace("，", ",").split(","):
        for token in chunk.split():
            cleaned = token.strip().lstrip("#")
            if cleaned:
                items.append(cleaned)
    return ",".join(items)


def parse_record_date(raw_value: Any, timezone) -> date | None:
    if raw_value is None or raw_value == "":
        return None

    if isinstance(raw_value, (int, float)):
        timestamp = float(raw_value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000.0
        return datetime.fromtimestamp(timestamp, tz=timezone).date()

    text = _strip_text(raw_value)
    if not text:
        return None

    for parser in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(text, parser).date()
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone)
        return parsed.astimezone(timezone).date()
    except ValueError:
        return None


def is_unpublished_status(raw_value: Any, unpublished_values: set[str]) -> bool:
    if raw_value is None:
        return True
    value = _strip_text(raw_value)
    return value in unpublished_values


def should_process_record(record_fields: dict[str, Any], config: SchedulerConfig, today: date) -> bool:
    row_date = parse_record_date(record_fields.get(config.date_field), config.timezone)
    if row_date != today:
        return False
    return is_unpublished_status(record_fields.get(config.summary_status_field), config.unpublished_values)


def _pick_first_attachment(fields: dict[str, Any], video_field_name: str) -> dict[str, Any]:
    value = fields.get(video_field_name)
    if isinstance(value, list) and value:
        attachment = value[0]
        if isinstance(attachment, dict):
            return attachment
    raise RuntimeError(f"Record does not contain attachment in field: {video_field_name}")


def build_tencent_request(
    fields: dict[str, Any],
    video_path: Path,
    config: SchedulerConfig,
) -> TencentVideoUploadRequest:
    tags = normalize_tags(fields.get(config.tencent_tags_field))
    return TencentVideoUploadRequest(
        account_name=config.tencent_account,
        video_file=video_path,
        title=_strip_text(fields.get(config.tencent_title_field)),
        description=_strip_text(fields.get(config.tencent_desc_field)),
        tags=tags.split(",") if tags else [],
        publish_date=0,
        debug=True,
        headless=config.headless,
    )


def build_kuaishou_request(
    fields: dict[str, Any],
    video_path: Path,
    config: SchedulerConfig,
) -> KuaishouVideoUploadRequest:
    tags = normalize_tags(fields.get(config.kuaishou_tags_field))
    return KuaishouVideoUploadRequest(
        account_name=config.kuaishou_account,
        video_file=video_path,
        title=_strip_text(fields.get(config.kuaishou_title_field)),
        description=_strip_text(fields.get(config.kuaishou_desc_field)),
        tags=tags.split(",") if tags else [],
        publish_date=0,
        debug=True,
        headless=config.headless,
    )


async def publish_to_tencent(request: TencentVideoUploadRequest) -> PublishOutcome:
    try:
        await upload_tencent_video(request)
        return PublishOutcome(status=PUBLISHED_STATUS)
    except Exception as exc:
        return PublishOutcome(status=FAILED_STATUS, error=str(exc))


async def publish_to_kuaishou(request: KuaishouVideoUploadRequest) -> PublishOutcome:
    try:
        await upload_kuaishou_video(request)
        return PublishOutcome(status=PUBLISHED_STATUS)
    except Exception as exc:
        return PublishOutcome(status=FAILED_STATUS, error=str(exc))


def _build_notify_text(result: RecordRunResult) -> str:
    tencent_line = f"视频号: {result.tencent_status}" + (f" ({result.tencent_error})" if result.tencent_error else "")
    kuaishou_line = f"快手: {result.kuaishou_status}" + (f" ({result.kuaishou_error})" if result.kuaishou_error else "")
    summary_emoji = "✅" if result.summary_status == PUBLISHED_STATUS else "❌"
    tencent_emoji = "✅" if result.tencent_status == PUBLISHED_STATUS else "❌"
    kuaishou_emoji = "✅" if result.kuaishou_status == PUBLISHED_STATUS else "❌"
    base = [
        "<b>📣 自动发布结果</b>",
        f"<b>Record</b>: <code>{html.escape(result.record_id)}</code>",
        f"{tencent_emoji} " + (f"<b>{html.escape(tencent_line)}</b>" if result.tencent_status == FAILED_STATUS else html.escape(tencent_line)),
        f"{kuaishou_emoji} " + (f"<b>{html.escape(kuaishou_line)}</b>" if result.kuaishou_status == FAILED_STATUS else html.escape(kuaishou_line)),
        f"<b>{summary_emoji} 汇总</b>: {html.escape(result.summary_status)}",
    ]
    return "\n".join(base)


def _safe_notify_text(notifier: TelegramNotifier, text: str, parse_mode: str | None = "HTML") -> None:
    try:
        notifier.send(text, parse_mode=parse_mode)
    except Exception:
        # Keep scheduler flow alive when Telegram is temporarily unavailable.
        pass


def _notify_login_qrcode(notifier: TelegramNotifier, platform_name: str, payload: dict[str, Any]) -> None:
    image_path = str(payload.get("image_path") or "").strip()
    _safe_notify_text(
        notifier,
        f"<b>📷 {html.escape(platform_name)} 登录二维码</b>\n"
        "请在手机上扫码确认登录。"
        + (f"\n二维码文件: <code>{html.escape(image_path)}</code>" if image_path else ""),
    )
    if not image_path:
        return
    try:
        notifier.send_photo(
            image_path,
            caption=f"<b>{html.escape(platform_name)} 登录二维码</b>",
            parse_mode="HTML",
        )
    except Exception as exc:
        _safe_notify_text(
            notifier,
            f"<b>⚠️ {html.escape(platform_name)} 二维码图片发送失败（不中断本轮）</b>\n"
            f"{html.escape(str(exc))}",
        )


def _update_status_fields_with_fallback(
    feishu: FeishuBitableClient,
    record_id: str,
    field_values: dict[str, Any],
) -> list[str]:
    """Try bulk update first; if a field name is missing, degrade to per-field updates."""
    try:
        feishu.update_record_fields(record_id, field_values)
        return []
    except Exception as exc:
        if "FieldNameNotFound" not in str(exc):
            raise

    missing_fields: list[str] = []
    for field_name, field_value in field_values.items():
        try:
            feishu.update_record_fields(record_id, {field_name: field_value})
        except Exception as exc:
            if "FieldNameNotFound" in str(exc):
                missing_fields.append(field_name)
                continue
            raise
    return missing_fields


async def _ensure_accounts(config: SchedulerConfig, notifier: TelegramNotifier) -> None:
    tencent_valid, kuaishou_valid = await asyncio.gather(
        check_tencent_account(config.tencent_account),
        check_kuaishou_account(config.kuaishou_account),
    )

    if not tencent_valid:
        _safe_notify_text(
            notifier,
            f"<b>⚠️ 视频号登录态失效</b>\n开始自动拉起登录流程: <code>{html.escape(config.tencent_account)}</code>",
        )
        result = await login_tencent_account(
            config.tencent_account,
            headless=config.headless,
            qrcode_callback=lambda payload: _notify_login_qrcode(notifier, "视频号", payload),
        )
        if not result.get("success"):
            message = str(result.get("message") or "unknown error")
            _safe_notify_text(notifier, f"<b>❌ 视频号自动登录失败</b>\n{html.escape(message)}")
            raise RuntimeError(f"Tencent account relogin failed: {config.tencent_account}, {message}")
        _safe_notify_text(notifier, f"<b>✅ 视频号自动登录成功</b>\n账号: <code>{html.escape(config.tencent_account)}</code>")

    if not kuaishou_valid:
        _safe_notify_text(
            notifier,
            f"<b>⚠️ 快手登录态失效</b>\n开始自动拉起登录流程: <code>{html.escape(config.kuaishou_account)}</code>",
        )
        result = await login_kuaishou_account(
            config.kuaishou_account,
            headless=config.headless,
            qrcode_callback=lambda payload: _notify_login_qrcode(notifier, "快手", payload),
        )
        if not result.get("success"):
            message = str(result.get("message") or "unknown error")
            _safe_notify_text(notifier, f"<b>❌ 快手自动登录失败</b>\n{html.escape(message)}")
            raise RuntimeError(f"Kuaishou account relogin failed: {config.kuaishou_account}, {message}")
        _safe_notify_text(notifier, f"<b>✅ 快手自动登录成功</b>\n账号: <code>{html.escape(config.kuaishou_account)}</code>")


async def process_one_record(
    record: dict[str, Any],
    config: SchedulerConfig,
    feishu: FeishuBitableClient,
    notifier: TelegramNotifier,
) -> RecordRunResult:
    record_id = str(record.get("record_id") or "")
    if not record_id:
        raise RuntimeError("Feishu record missing record_id")

    fields = record.get("fields") or {}
    with TemporaryDirectory(prefix="sau_scheduler_") as temp_dir:
        video_attachment = _pick_first_attachment(fields, config.video_field)
        video_path = feishu.download_attachment(video_attachment, Path(temp_dir))

        tencent_request = build_tencent_request(fields, video_path, config)
        kuaishou_request = build_kuaishou_request(fields, video_path, config)

        tencent_outcome = await publish_to_tencent(tencent_request)
        kuaishou_outcome = await publish_to_kuaishou(kuaishou_request)

    summary_status = (
        PUBLISHED_STATUS
        if tencent_outcome.status == PUBLISHED_STATUS and kuaishou_outcome.status == PUBLISHED_STATUS
        else FAILED_STATUS
    )
    result = RecordRunResult(
        record_id=record_id,
        summary_status=summary_status,
        tencent_status=tencent_outcome.status,
        kuaishou_status=kuaishou_outcome.status,
        tencent_error=tencent_outcome.error,
        kuaishou_error=kuaishou_outcome.error,
    )

    missing_fields = _update_status_fields_with_fallback(
        feishu,
        record_id,
        {
            config.tencent_status_field: result.tencent_status,
            config.kuaishou_status_field: result.kuaishou_status,
            config.summary_status_field: result.summary_status,
        },
    )
    if missing_fields:
        _safe_notify_text(
            notifier,
            "<b>⚠️ 状态回写字段缺失</b>\n"
            f"<b>Record</b>: <code>{html.escape(record_id)}</code>\n"
            f"缺失字段: {html.escape(', '.join(missing_fields))}\n"
            "已自动跳过缺失字段，其余字段正常回写。"
        )
    _safe_notify_text(notifier, _build_notify_text(result))
    return result


@dataclass(slots=True)
class RunSummary:
    scanned_records: int
    processed_records: int
    success_records: int
    failed_records: int


async def run_once(config: SchedulerConfig) -> RunSummary:
    feishu = FeishuBitableClient(
        app_id=config.feishu_app_id,
        app_secret=config.feishu_app_secret,
        app_token=config.feishu_app_token,
        table_id=config.feishu_table_id,
    )
    notifier = TelegramNotifier(
        bot_token=config.telegram_bot_token,
        chat_id=config.telegram_chat_id,
    )
    await _ensure_accounts(config, notifier)

    records = feishu.list_records()
    today = datetime.now(config.timezone).date()
    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for record in records:
        record_id = str(record.get("record_id") or "")
        if not record_id or record_id in seen_ids:
            continue
        seen_ids.add(record_id)
        fields = record.get("fields") or {}
        if should_process_record(fields, config, today):
            selected.append(record)

    success_count = 0
    failed_count = 0
    for record in selected:
        try:
            result = await process_one_record(record, config, feishu, notifier)
            if result.summary_status == PUBLISHED_STATUS:
                success_count += 1
            else:
                failed_count += 1
        except Exception as exc:
            failed_count += 1
            record_id = str(record.get("record_id") or "unknown")
            message = (
                "<b>❌ 自动发布结果</b>\n"
                f"<b>Record</b>: <code>{html.escape(record_id)}</code>\n"
                f"<b>错误</b>: {html.escape(str(exc))}\n"
                f"<b>Traceback</b>:\n<pre>{html.escape(traceback.format_exc(limit=1))}</pre>"
            )
            _safe_notify_text(notifier, message)
            try:
                _update_status_fields_with_fallback(
                    feishu,
                    record_id,
                    {
                        config.tencent_status_field: FAILED_STATUS,
                        config.kuaishou_status_field: FAILED_STATUS,
                        config.summary_status_field: FAILED_STATUS,
                    },
                )
            except Exception:
                pass

    summary = RunSummary(
        scanned_records=len(records),
        processed_records=len(selected),
        success_records=success_count,
        failed_records=failed_count,
    )
    _safe_notify_text(
        notifier,
        "\n".join(
            [
                "<b>📦 自动发布批次完成</b>",
                f"扫描记录: <b>{summary.scanned_records}</b>",
                f"命中记录: <b>{summary.processed_records}</b>",
                f"✅ 成功: <b>{summary.success_records}</b>",
                f"❌ 失败: <b>{summary.failed_records}</b>",
            ]
        ),
    )
    return summary


def next_run_seconds(schedule_times: list[str], timezone) -> float:
    now = datetime.now(timezone)
    candidates: list[datetime] = []
    for raw in schedule_times:
        hour, minute = raw.split(":")
        run_dt = datetime.combine(now.date(), time(int(hour), int(minute)), tzinfo=timezone)
        if run_dt <= now:
            run_dt += timedelta(days=1)
        candidates.append(run_dt)
    next_run = min(candidates)
    return max(1.0, (next_run - now).total_seconds())
