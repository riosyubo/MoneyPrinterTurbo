import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models.schema import VideoConcatMode, VideoParams
from app.models.storyboard import (
    parse_storyboard_text,
    storyboard_narration,
    storyboard_visual_terms,
)
from app.services.task import apply_storyboard


class TestStoryboardParser(unittest.TestCase):
    def test_parses_labeled_scene_blocks_and_multiline_fields(self):
        scenes = parse_storyboard_text(
            """镜头 1
旁白：第一句旁白。
补充一句。
画面：老人正在整理药盒。

镜头 2
旁白：第二句旁白。
画面：手机闹钟响起。"""
        )

        self.assertEqual(len(scenes), 2)
        self.assertEqual(scenes[0].narration, "第一句旁白。\n补充一句。")
        self.assertEqual(scenes[0].visual, "老人正在整理药盒。")
        self.assertEqual(scenes[1].index, 2)

    def test_parses_compact_rows_and_falls_back_to_narration(self):
        scenes = parse_storyboard_text("第一段 || 药盒特写\n第二段 ||")

        self.assertEqual(storyboard_narration(scenes), "第一段\n第二段")
        self.assertEqual(storyboard_visual_terms(scenes), ["药盒特写", "第二段"])

    def test_screen_text_is_used_as_canonical_narration(self):
        scenes = parse_storyboard_text(
            "镜头1\n屏幕大字：先核对药名和剂量\n画面：老人查看药盒标签"
        )

        self.assertEqual(storyboard_narration(scenes), "先核对药名和剂量")
        self.assertEqual(storyboard_visual_terms(scenes), ["老人查看药盒标签"])

    def test_rejects_unlabeled_content(self):
        with self.assertRaisesRegex(ValueError, "line 1"):
            parse_storyboard_text("这不是受支持的分镜格式")

    def test_apply_storyboard_overrides_all_downstream_text_inputs(self):
        params = VideoParams(
            video_subject="用药安全",
            storyboard_enabled=True,
            storyboard_text="旁白一 || 画面一\n旁白二 || 画面二",
            video_script="旧文案",
            video_terms="旧关键词",
            video_concat_mode="random",
            match_materials_to_script=False,
        )

        scenes = apply_storyboard(params)

        self.assertEqual(len(scenes), 2)
        self.assertEqual(params.video_script, "旁白一\n旁白二")
        self.assertEqual(params.video_terms, ["画面一", "画面二"])
        self.assertTrue(params.match_materials_to_script)
        self.assertEqual(params.video_concat_mode, VideoConcatMode.sequential)


if __name__ == "__main__":
    unittest.main()
