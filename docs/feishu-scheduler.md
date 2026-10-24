# 飞书多维表定时发布

该能力用于每天固定时间扫描飞书多维表，自动下载当天未发布视频，并发布到视频号与快手。发布后会回写状态并发送 Telegram 通知。

## 功能范围

- 平台：`tencent`（视频号）、`kuaishou`（快手）
- 触发时间：默认 `07:00,17:00`（北京时间）
- 筛选规则：`日期=今天` 且 `发布状态` 为空/未发布
- 状态回写：
  - `视频号发布状态`：`已发布` / `发布失败`
  - `快手发布状态`：`已发布` / `发布失败`
  - `发布状态`：两个平台都成功才写 `已发布`，否则写 `发布失败`
- 通知：每条记录结果 + 每批次汇总发送到 Telegram

## 前置准备

1. 完成环境安装并确保 `sau` 可用
2. 提前登录两个平台账号

```powershell
uv run sau tencent login --account creator --headless
uv run sau kuaishou login --account creator --headless
```

3. vps上
```
.venv/bin/sau tencent login --account creator --headless
.venv/bin/sau kuaishou login --account creator --headless
```

3. 准备 `.env`（仓库根目录）

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_APP_TOKEN=bascnxxx
FEISHU_TABLE_ID=tblxxx

TELEGRAM_BOT_TOKEN=123456:abc
TELEGRAM_CHAT_ID=123456789

SCHED_TIMES=07:00,17:00
SCHED_TZ=Asia/Shanghai

SAU_TENCENT_ACCOUNT=creator
SAU_KUAISHOU_ACCOUNT=creator
SAU_HEADLESS=true
```

## 字段映射（默认）

- `日期`
- `视频`（附件字段）
- `发布状态`
- `视频号发布状态`
- `快手发布状态`
- `视频号标题` / `视频号描述` / `视频号话题`
- `快手标题` / `快手描述` / `快手话题`

可通过环境变量覆盖字段名：

- `FEISHU_FIELD_DATE`
- `FEISHU_FIELD_VIDEO`
- `FEISHU_FIELD_STATUS`
- `FEISHU_FIELD_TENCENT_STATUS`
- `FEISHU_FIELD_KUAISHOU_STATUS`
- `FEISHU_FIELD_TENCENT_TITLE`
- `FEISHU_FIELD_TENCENT_DESC`
- `FEISHU_FIELD_TENCENT_TAGS`
- `FEISHU_FIELD_KUAISHOU_TITLE`
- `FEISHU_FIELD_KUAISHOU_DESC`
- `FEISHU_FIELD_KUAISHOU_TAGS`

## 运行命令

执行单轮（建议先验收）：

```powershell
uv run sau scheduler run-once --env-file .env
```

启动常驻定时：

```powershell
uv run sau scheduler run-daily --env-file .env
```

### vps上运行
```
.venv/bin/sau scheduler run-once --env-file .env
```

启动常驻定时:
```
.venv/bin/sau scheduler run-daily --env-file .env
```

### systemd 常用运维命令（VPS）

服务名：`sau-scheduler.service`

```bash
# 查看服务状态
systemctl status sau-scheduler.service

# 查看实时日志
journalctl -u sau-scheduler.service -f

# 重启服务
systemctl restart sau-scheduler.service

# 停止服务
systemctl stop sau-scheduler.service

# 启动服务
systemctl start sau-scheduler.service

# 开机自启
systemctl enable sau-scheduler.service

# 取消开机自启
systemctl disable sau-scheduler.service
```

## 常见问题

- 平台 cookie 失效：`scheduler` 会自动触发重新登录，并通过 Telegram 发送二维码图片，扫码后自动继续流程
- 飞书接口报权限错误：确认应用已开通多维表与云文档下载权限，并授权到目标表格
- Telegram 无通知：检查 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID` 是否正确
