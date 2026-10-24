"""Telegram 通知客户端。"""
from __future__ import annotations

import requests


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str, timeout_seconds: int = 20) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout_seconds = timeout_seconds

    def send(self, text: str) -> None:
        response = requests.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            description = payload.get("description") or "Unknown Telegram API error"
            raise RuntimeError(f"Telegram notify failed: {description}")
