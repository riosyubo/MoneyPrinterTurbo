"""Official Douyin Open Platform video publishing integration."""

import os
from typing import Any, Optional

import requests
from loguru import logger

from app.config import config


class DouyinAPIError(RuntimeError):
    """A stable, user-facing error returned by the Douyin Open Platform."""


class DouyinService:
    API_BASE = "https://open.douyin.com"
    VIDEO_UPLOAD_PATH = "/api/douyin/v1/video/upload_video/"
    IMAGE_UPLOAD_PATH = "/api/douyin/v1/video/upload_image/"
    VIDEO_CREATE_PATH = "/api/douyin/v1/video/create_video/"
    TOKEN_REFRESH_PATH = "/oauth/refresh_token/"

    @property
    def enabled(self) -> bool:
        return bool(config.app.get("douyin_enabled", False))

    @property
    def auto_publish(self) -> bool:
        return bool(config.app.get("douyin_auto_publish", False))

    @property
    def access_token(self) -> str:
        return str(config.app.get("douyin_access_token", "") or "").strip()

    @property
    def open_id(self) -> str:
        return str(config.app.get("douyin_open_id", "") or "").strip()

    @property
    def client_key(self) -> str:
        return str(config.app.get("douyin_client_key", "") or "").strip()

    @property
    def refresh_token(self) -> str:
        return str(config.app.get("douyin_refresh_token", "") or "").strip()

    @property
    def private_status(self) -> int:
        value = config.app.get("douyin_private_status", 0)
        return value if isinstance(value, int) and value in {0, 1, 2} else 0

    @property
    def allow_download(self) -> bool:
        return bool(config.app.get("douyin_allow_download", True))

    def is_configured(self) -> bool:
        has_token = bool(self.access_token) or bool(self.client_key and self.refresh_token)
        return bool(self.enabled and self.open_id and has_token)

    @staticmethod
    def _payload_data(response: requests.Response, stage: str) -> dict[str, Any]:
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        data = data if isinstance(data, dict) else {}
        extra = payload.get("extra") if isinstance(payload, dict) else None
        extra = extra if isinstance(extra, dict) else {}
        error_code = data.get("error_code") or extra.get("error_code") or 0
        if int(error_code) != 0:
            description = (
                data.get("description")
                or extra.get("description")
                or extra.get("sub_description")
                or "unknown Douyin API error"
            )
            raise DouyinAPIError(f"{stage} failed ({error_code}): {description}")
        return data

    def _resolve_access_token(self) -> str:
        if self.client_key and self.refresh_token:
            response = requests.post(
                f"{self.API_BASE}{self.TOKEN_REFRESH_PATH}",
                data={
                    "client_key": self.client_key,
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            data = self._payload_data(response, "Douyin token refresh")
            token = str(data.get("access_token") or "").strip()
            if not token:
                raise DouyinAPIError("Douyin token refresh returned no access_token")
            return token
        if self.access_token:
            return self.access_token
        raise DouyinAPIError("Douyin access token is not configured")

    def _upload_binary(
        self,
        endpoint: str,
        field_name: str,
        file_path: str,
        token: str,
        stage: str,
    ) -> dict[str, Any]:
        with open(file_path, "rb") as binary_file:
            response = requests.post(
                f"{self.API_BASE}{endpoint}",
                params={"open_id": self.open_id},
                headers={"access-token": token},
                files={field_name: (os.path.basename(file_path), binary_file)},
                timeout=600,
            )
        return self._payload_data(response, stage)

    def upload_video(
        self,
        video_path: str,
        title: str,
        cover_path: Optional[str] = None,
    ) -> dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "platform": "douyin", "error": "Douyin is not configured"}
        if not os.path.isfile(video_path):
            return {
                "success": False,
                "platform": "douyin",
                "error": f"Video file not found: {video_path}",
            }

        try:
            token = self._resolve_access_token()
            upload_data = self._upload_binary(
                self.VIDEO_UPLOAD_PATH,
                "video",
                video_path,
                token,
                "Douyin video upload",
            )
            video_id = str((upload_data.get("video") or {}).get("video_id") or "")
            if not video_id:
                raise DouyinAPIError("Douyin video upload returned no video_id")

            create_body: dict[str, Any] = {
                "video_id": video_id,
                "text": str(title or "")[:1000],
                "private_status": self.private_status,
                "download_type": 0 if self.allow_download else 1,
            }
            cover_uploaded = False
            cover_error = None
            if cover_path and os.path.isfile(cover_path):
                try:
                    image_data = self._upload_binary(
                        self.IMAGE_UPLOAD_PATH,
                        "image",
                        cover_path,
                        token,
                        "Douyin cover upload",
                    )
                    image_id = str((image_data.get("image") or {}).get("image_id") or "")
                    if not image_id:
                        raise DouyinAPIError("Douyin cover upload returned no image_id")
                    create_body["custom_cover_image_url"] = image_id
                    cover_uploaded = True
                except (DouyinAPIError, requests.RequestException, ValueError) as exc:
                    cover_error = str(exc)
                    create_body["cover_tsp"] = 0.2
                    logger.warning(f"Douyin custom cover skipped: {exc}")
            else:
                create_body["cover_tsp"] = 0.2

            response = requests.post(
                f"{self.API_BASE}{self.VIDEO_CREATE_PATH}",
                params={"open_id": self.open_id},
                headers={"access-token": token, "Content-Type": "application/json"},
                json=create_body,
                timeout=60,
            )
            create_data = self._payload_data(response, "Douyin video creation")
            result = {
                "success": True,
                "platform": "douyin",
                "item_id": create_data.get("item_id"),
                "video_id": create_data.get("video_id"),
                "cover_uploaded": cover_uploaded,
            }
            if cover_error:
                result["cover_warning"] = cover_error
            logger.success("Video submitted to Douyin for review")
            return result
        except (DouyinAPIError, requests.RequestException, ValueError) as exc:
            logger.error(f"Douyin publishing failed: {exc}")
            return {"success": False, "platform": "douyin", "error": str(exc)}


douyin_service = DouyinService()


def publish_video(video_path: str, title: str, cover_path: Optional[str] = None) -> dict:
    return douyin_service.upload_video(video_path, title, cover_path)
