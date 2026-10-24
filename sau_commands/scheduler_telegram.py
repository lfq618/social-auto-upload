"""Telegram 通知客户端。"""
from __future__ import annotations

from pathlib import Path

import requests


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str, timeout_seconds: int = 20) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout_seconds = timeout_seconds

    def send(self, text: str, parse_mode: str | None = None) -> None:
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        response = requests.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            description = payload.get("description") or "Unknown Telegram API error"
            raise RuntimeError(f"Telegram notify failed: {description}")

    def send_photo(self, photo_path: str, caption: str = "", parse_mode: str | None = None) -> None:
        path = Path(photo_path)
        if not path.exists():
            raise RuntimeError(f"Telegram photo not found: {photo_path}")
        data = {
            "chat_id": self.chat_id,
            "caption": caption,
        }
        if parse_mode:
            data["parse_mode"] = parse_mode
        with path.open("rb") as file_obj:
            response = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendPhoto",
                data=data,
                files={"photo": file_obj},
                timeout=self.timeout_seconds,
            )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            description = payload.get("description") or "Unknown Telegram API error"
            raise RuntimeError(f"Telegram send photo failed: {description}")
