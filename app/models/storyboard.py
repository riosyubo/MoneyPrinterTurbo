"""Parse the user-facing storyboard format into narration and visual prompts."""

from __future__ import annotations

import re
from dataclasses import dataclass


MAX_STORYBOARD_SCENES = 50
MAX_STORYBOARD_FIELD_LENGTH = 2000

_SCENE_HEADING = re.compile(
    r"^(?:镜头|分镜|scene)\s*(?:[#：:\-]?\s*\d+)?\s*[.、:：\-]?\s*$",
    re.IGNORECASE,
)
_NARRATION_LABEL = re.compile(
    r"^(?:屏幕大字|大字|旁白|台词|解说|文案|narration|voiceover)\s*[:：]\s*(.*)$",
    re.IGNORECASE,
)
_VISUAL_LABEL = re.compile(
    r"^(?:画面|视觉|场景|visual|shot)\s*[:：]\s*(.*)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class StoryboardScene:
    index: int
    narration: str
    visual: str


def _validate_scene(narration: str, visual: str, index: int) -> StoryboardScene:
    narration = narration.strip()
    visual = visual.strip() or narration
    if not narration:
        raise ValueError(f"scene {index} is missing narration")
    if len(narration) > MAX_STORYBOARD_FIELD_LENGTH:
        raise ValueError(
            f"scene {index} narration exceeds {MAX_STORYBOARD_FIELD_LENGTH} characters"
        )
    if len(visual) > MAX_STORYBOARD_FIELD_LENGTH:
        raise ValueError(
            f"scene {index} visual prompt exceeds {MAX_STORYBOARD_FIELD_LENGTH} characters"
        )
    return StoryboardScene(index=index, narration=narration, visual=visual)


def _validate_scene_count(scenes: list[StoryboardScene]) -> list[StoryboardScene]:
    if not scenes:
        raise ValueError("storyboard must contain at least one scene")
    if len(scenes) > MAX_STORYBOARD_SCENES:
        raise ValueError(f"storyboard supports at most {MAX_STORYBOARD_SCENES} scenes")
    return scenes


def parse_storyboard_text(text: str) -> list[StoryboardScene]:
    """Parse compact ``narration || visual`` rows or labeled scene blocks.

    In labeled blocks, a missing visual prompt deliberately falls back to the
    narration so every downstream material provider still receives one prompt
    per scene.
    """
    lines = [line.rstrip() for line in str(text or "").replace("\r\n", "\n").split("\n")]
    meaningful = [line.strip() for line in lines if line.strip()]
    if not meaningful:
        raise ValueError("storyboard must contain at least one scene")

    # The compact form is convenient for pasting a storyboard from a spreadsheet.
    compact_lines = [line for line in meaningful if not _SCENE_HEADING.match(line)]
    if compact_lines and all("||" in line for line in compact_lines):
        scenes = []
        for index, line in enumerate(compact_lines, start=1):
            narration, visual = line.split("||", 1)
            scenes.append(_validate_scene(narration, visual, index))
        return _validate_scene_count(scenes)

    scenes: list[StoryboardScene] = []
    narration_parts: list[str] = []
    visual_parts: list[str] = []
    current_field: list[str] | None = None

    def flush_scene() -> None:
        nonlocal narration_parts, visual_parts, current_field
        if not narration_parts and not visual_parts:
            return
        scenes.append(
            _validate_scene(
                "\n".join(narration_parts),
                "\n".join(visual_parts),
                len(scenes) + 1,
            )
        )
        narration_parts = []
        visual_parts = []
        current_field = None

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            if narration_parts and visual_parts:
                flush_scene()
            continue
        if _SCENE_HEADING.match(line):
            flush_scene()
            continue
        narration_match = _NARRATION_LABEL.match(line)
        if narration_match:
            if narration_parts and visual_parts:
                flush_scene()
            narration_parts.append(narration_match.group(1).strip())
            current_field = narration_parts
            continue
        visual_match = _VISUAL_LABEL.match(line)
        if visual_match:
            visual_parts.append(visual_match.group(1).strip())
            current_field = visual_parts
            continue
        if current_field is None:
            raise ValueError(
                f"line {line_number} must start with 屏幕大字：, 旁白： or 画面：, "
                "or use 文本 || 画面"
            )
        current_field.append(line)

    flush_scene()
    return _validate_scene_count(scenes)


def storyboard_narration(scenes: list[StoryboardScene]) -> str:
    """Build the canonical TTS/subtitle script in scene order."""
    return "\n".join(scene.narration for scene in scenes)


def storyboard_visual_terms(scenes: list[StoryboardScene]) -> list[str]:
    """Build one material prompt per scene, preserving scene order."""
    return [scene.visual for scene in scenes]
