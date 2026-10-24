"""飞书多维表格读取、附件下载与状态回写。"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests


class FeishuBitableClient:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        app_token: str,
        table_id: str,
        timeout_seconds: int = 30,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token
        self.table_id = table_id
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://open.feishu.cn/open-apis"
        self._tenant_token = ""
        self._token_expire_at = 0.0

    def _auth_headers(self) -> dict[str, str]:
        token = self.get_tenant_access_token()
        return {"Authorization": f"Bearer {token}"}

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target_headers = {"Content-Type": "application/json; charset=utf-8"}
        if headers:
            target_headers.update(headers)

        response = requests.request(
            method=method,
            url=f"{self.base_url}{path}",
            headers=target_headers,
            params=params,
            json=json_body,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            message = payload.get("msg") or payload.get("message") or "Unknown Feishu API error"
            raise RuntimeError(f"Feishu API error ({path}): {message}")
        return payload

    def get_tenant_access_token(self) -> str:
        now = time.time()
        if self._tenant_token and now < self._token_expire_at:
            return self._tenant_token

        payload = self._request_json(
            "POST",
            "/auth/v3/tenant_access_token/internal",
            json_body={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        token = payload.get("tenant_access_token")
        if not token:
            raise RuntimeError("Feishu tenant_access_token missing in response")
        expires_in = int(payload.get("expire", 7200))
        self._tenant_token = token
        self._token_expire_at = now + max(60, expires_in - 60)
        return token

    def list_records(self, page_size: int = 200) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_token = ""
        while True:
            params: dict[str, Any] = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            payload = self._request_json(
                "GET",
                f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records",
                headers=self._auth_headers(),
                params=params,
            )
            data = payload.get("data") or {}
            items = data.get("items") or []
            records.extend(items)
            if not data.get("has_more"):
                break
            page_token = data.get("page_token", "")
            if not page_token:
                break
        return records

    def update_record_fields(self, record_id: str, fields: dict[str, Any]) -> None:
        self._request_json(
            "PUT",
            f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/{record_id}",
            headers=self._auth_headers(),
            json_body={"fields": fields},
        )

    def _download_by_file_token(self, file_token: str, target_path: Path) -> bool:
        response = requests.get(
            f"{self.base_url}/drive/v1/medias/{file_token}/download",
            headers=self._auth_headers(),
            timeout=self.timeout_seconds,
            stream=True,
        )
        if response.status_code >= 400:
            return False
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("wb") as file_obj:
            for chunk in response.iter_content(chunk_size=1024 * 128):
                if chunk:
                    file_obj.write(chunk)
        return True

    def _download_by_url(self, url: str, target_path: Path) -> bool:
        response = requests.get(
            url,
            headers=self._auth_headers(),
            timeout=self.timeout_seconds,
            stream=True,
        )
        if response.status_code >= 400:
            return False
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("wb") as file_obj:
            for chunk in response.iter_content(chunk_size=1024 * 128):
                if chunk:
                    file_obj.write(chunk)
        return True

    def download_attachment(self, attachment: dict[str, Any], target_directory: Path) -> Path:
        filename = str(attachment.get("name") or attachment.get("file_name") or "video.mp4")
        safe_filename = Path(filename).name
        target_path = target_directory / safe_filename

        file_token = str(attachment.get("file_token") or "").strip()
        if file_token and self._download_by_file_token(file_token, target_path):
            return target_path

        for key in ("tmp_url", "url"):
            url = str(attachment.get(key) or "").strip()
            if url and self._download_by_url(url, target_path):
                return target_path

        raise RuntimeError(f"Unable to download Feishu attachment: {safe_filename}")
