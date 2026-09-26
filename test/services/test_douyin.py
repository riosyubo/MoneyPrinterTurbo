import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.douyin import DouyinService


BASE_CONFIG = {
    "douyin_enabled": True,
    "douyin_auto_publish": True,
    "douyin_access_token": "access-token",
    "douyin_open_id": "open-id",
    "douyin_client_key": "",
    "douyin_refresh_token": "",
    "douyin_private_status": 0,
    "douyin_allow_download": True,
}


def response(data):
    result = MagicMock()
    result.raise_for_status = MagicMock()
    result.json.return_value = {"data": {"error_code": 0, **data}, "extra": {}}
    return result


class TestDouyinService(unittest.TestCase):
    @patch("app.services.douyin.config.app", BASE_CONFIG)
    @patch("app.services.douyin.os.path.isfile", return_value=True)
    @patch("builtins.open", mock_open(read_data=b"media"))
    @patch("app.services.douyin.requests.post")
    def test_uploads_video_and_cover_then_creates_post(self, post, _isfile):
        post.side_effect = [
            response({"video": {"video_id": "encrypted-video"}}),
            response({"image": {"image_id": "encrypted-image"}}),
            response({"item_id": "item-1", "video_id": "video-1"}),
        ]

        result = DouyinService().upload_video("final.mp4", "标题 #健康", "cover.jpg")

        self.assertTrue(result["success"])
        self.assertTrue(result["cover_uploaded"])
        self.assertEqual(result["item_id"], "item-1")
        create_call = post.call_args_list[2]
        self.assertTrue(create_call.args[0].endswith("/create_video/"))
        self.assertEqual(create_call.kwargs["json"]["custom_cover_image_url"], "encrypted-image")
        self.assertEqual(create_call.kwargs["json"]["private_status"], 0)
        self.assertEqual(create_call.kwargs["json"]["download_type"], 0)

    @patch("app.services.douyin.config.app", BASE_CONFIG)
    @patch("app.services.douyin.os.path.isfile", return_value=True)
    @patch("builtins.open", mock_open(read_data=b"media"))
    @patch("app.services.douyin.requests.post")
    def test_cover_failure_falls_back_to_video_frame(self, post, _isfile):
        cover_failure = response({"description": "cover rejected"})
        cover_failure.json.return_value["data"]["error_code"] = 2100005
        post.side_effect = [
            response({"video": {"video_id": "encrypted-video"}}),
            cover_failure,
            response({"item_id": "item-1", "video_id": "video-1"}),
        ]

        result = DouyinService().upload_video("final.mp4", "标题", "cover.jpg")

        self.assertTrue(result["success"])
        self.assertFalse(result["cover_uploaded"])
        self.assertIn("cover_warning", result)
        self.assertEqual(post.call_args_list[2].kwargs["json"]["cover_tsp"], 0.2)

    @patch(
        "app.services.douyin.config.app",
        {**BASE_CONFIG, "douyin_access_token": "", "douyin_client_key": "client", "douyin_refresh_token": "refresh"},
    )
    @patch("app.services.douyin.requests.post")
    def test_refreshes_access_token_when_refresh_credentials_exist(self, post):
        post.return_value = response({"access_token": "fresh-token"})

        token = DouyinService()._resolve_access_token()

        self.assertEqual(token, "fresh-token")
        self.assertTrue(post.call_args.args[0].endswith("/oauth/refresh_token/"))
        self.assertEqual(post.call_args.kwargs["data"]["grant_type"], "refresh_token")

    @patch("app.services.douyin.config.app", {**BASE_CONFIG, "douyin_open_id": ""})
    @patch("app.services.douyin.requests.post")
    def test_missing_configuration_does_not_call_api(self, post):
        result = DouyinService().upload_video("final.mp4", "标题")

        self.assertFalse(result["success"])
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
