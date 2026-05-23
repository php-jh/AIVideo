"""
AI短剧生成器 - 分镜解析器
将剧本解析为视频制作所需的分镜列表
"""
from dataclasses import dataclass, field
from typing import List, Optional


_GENERIC_CONTINUITY_MARKERS = (
    "承接上一镜",
    "保持叙事连续",
    "开场镜头，建立人物",
    "情绪与空间",
    "叙事连续",
    "承上启下",
)


def _scene_tail_text(scene: dict) -> str:
    """上一镜结尾可用于衔接的文本（台词/旁白/画面）。"""
    dialogues = scene.get("dialogues") or []
    if dialogues:
        d = dialogues[-1]
        char = (d.get("character") or "").strip()
        line = (d.get("line") or "").strip()
        return f"{char}：{line}" if char else line
    narration = (scene.get("narration") or "").strip()
    if narration:
        return narration
    return (scene.get("visual_description") or "").strip()[:60]


def _is_weak_bridge_text(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 12:
        return True
    if any(m in t for m in _GENERIC_CONTINUITY_MARKERS) and len(t) < 28:
        return True
    return False


def _build_continuity_from_previous(prev: dict, curr: dict) -> str:
    prev_loc = (prev.get("location") or "").strip()
    curr_loc = (curr.get("location") or "").strip()
    tail = _scene_tail_text(prev)
    tail_short = tail[:48] + ("…" if len(tail) > 48 else "")
    if prev_loc and curr_loc and prev_loc == curr_loc:
        return (
            f"承上：仍在「{prev_loc}」，紧接上一镜结尾「{tail_short}」之后，"
            f"本镜同一空间内动作/情绪延续。"
        )
    reason = (curr.get("continuity_from_previous") or "").strip()
    if reason and not _is_weak_bridge_text(reason):
        return reason
    return (
        f"承上：上一镜在「{prev_loc or '前一场景'}」以「{tail_short}」收束；"
        f"本镜转至「{curr_loc or '下一场景'}」，因该情节发展而切换，因果连贯。"
    )


def _build_leads_to_next(curr: dict, nxt: dict) -> str:
    curr_loc = (curr.get("location") or "").strip()
    nxt_loc = (nxt.get("location") or "").strip()
    tail = _scene_tail_text(curr)
    tail_short = tail[:48] + ("…" if len(tail) > 48 else "")
    beat = (curr.get("story_beat") or "").strip()
    beat_part = f"（本镜作用：{beat}）" if beat else ""
    if curr_loc and nxt_loc and curr_loc == nxt_loc:
        return (
            f"启下：本镜以「{tail_short}」结束{beat_part}，"
            f"下一镜仍在「{curr_loc}」接着演后续反应。"
        )
    return (
        f"启下：本镜结尾「{tail_short}」{beat_part}，"
        f"下一镜将进入「{nxt_loc or '下一场景'}」推进主线。"
    )


def strengthen_script_continuity(script: dict) -> None:
    """
    强化分镜承上启下：补全/改写空洞的 continuity_from_previous、leads_to_next。
    旧剧本加载或 AI 套话时也会执行。
    """
    scenes = script.get("scenes") or []
    for i, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue

        if not str(scene.get("story_beat", "")).strip():
            if i == 0:
                scene["story_beat"] = "开场建立人物与冲突"
            elif i == len(scenes) - 1:
                scene["story_beat"] = "高潮收束或反转落点"
            else:
                scene["story_beat"] = "推进主线并制造期待"

        if i == 0:
            if _is_weak_bridge_text(scene.get("continuity_from_previous", "")):
                scene["continuity_from_previous"] = (
                    "开场：建立人物、场景与本集核心矛盾/目标。"
                )
        else:
            prev = scenes[i - 1]
            if isinstance(prev, dict) and _is_weak_bridge_text(
                scene.get("continuity_from_previous", "")
            ):
                scene["continuity_from_previous"] = _build_continuity_from_previous(
                    prev, scene
                )

        if i < len(scenes) - 1:
            nxt = scenes[i + 1]
            if isinstance(nxt, dict) and _is_weak_bridge_text(
                scene.get("leads_to_next", "")
            ):
                scene["leads_to_next"] = _build_leads_to_next(scene, nxt)
        else:
            if not str(scene.get("leads_to_next", "")).strip():
                scene["leads_to_next"] = "全片收束：交代结局或留悬念。"

        if not str(scene.get("motion_intent", "")).strip():
            scene["motion_intent"] = (
                "角色说话时口型张合、手部有轻微手势，眨眼与表情变化，头发衣摆轻摆"
                if i > 0
                else "角色面向镜头，开口说话并配合手势，建立动画表演感"
            )
        if not str(scene.get("visual_anchor", "")).strip():
            scene["visual_anchor"] = "与剧情一致的角色造型与场景主色调，多镜保持一致"


def ensure_scene_continuity_fields(script: dict) -> None:
    """为缺少连贯字段的旧剧本补默认值，并强化承上启下描述。"""
    strengthen_script_continuity(script)


@dataclass
class StoryboardScene:
    """单个分镜场景"""
    scene_number: int
    location: str = ""
    time: str = ""
    visual_description: str = ""  # 用于生图的详细描述
    visual_anchor: str = ""  # 全片统一的人物/场景外观锚点（多镜一致）
    continuity_from_previous: str = ""  # 承上：与上一镜的衔接说明
    leads_to_next: str = ""  # 启下：为下一镜铺垫
    story_beat: str = ""  # 本镜在主线中的作用
    motion_intent: str = ""  # 本镜内连贯微动（供图生视频/动效）
    camera_movement: str = "静态"  # 镜头运动
    mood: str = ""  # 情绪氛围
    narration: str = ""  # 旁白
    dialogues: List[dict] = field(default_factory=list)  # 对话列表
    characters: List[dict] = field(default_factory=list)  # 角色列表
    duration: float = 4.0  # 持续时间(秒)
    image_path: str = ""  # 生成的图片路径
    video_path: str = ""  # 生成的短视频路径
    audio_path: str = ""  # 生成的音频路径
    subtitle_text: str = ""  # 合并后的字幕文字

    def get_subtitle_text(self) -> str:
        """获取合并后的字幕文字"""
        if self.subtitle_text:
            return self.subtitle_text
        parts = []
        if self.narration:
            parts.append(self.narration)
        for d in self.dialogues:
            parts.append(f"{d.get('character', '')}：{d.get('line', '')}")
        self.subtitle_text = "\n".join(parts)
        return self.subtitle_text

    def get_full_audio_text(self) -> str:
        """获取完整需要转语音的文字"""
        parts = []
        if self.narration:
            parts.append(self.narration)
        for d in self.dialogues:
            parts.append(d.get('line', ''))
        return "。".join(parts)


@dataclass
class Storyboard:
    """完整分镜脚本"""
    title: str = ""
    genre: str = ""
    theme: str = ""
    characters: List[dict] = field(default_factory=list)
    scenes: List[StoryboardScene] = field(default_factory=list)
    total_duration: float = 0.0
    bgm_suggestion: str = ""

    def get_total_duration(self) -> float:
        """计算总时长"""
        return sum(s.duration for s in self.scenes)


class StoryboardParser:
    """分镜解析器"""

    def parse(self, script: dict) -> Storyboard:
        """
        将剧本字典解析为分镜对象

        Args:
            script: 从StoryGenerator返回的剧本字典

        Returns:
            Storyboard分镜对象
        """
        ensure_scene_continuity_fields(script)

        storyboard = Storyboard(
            title=script.get("title", "未命名短剧"),
            genre=script.get("genre", ""),
            theme=script.get("theme", ""),
            characters=script.get("characters", []),
            bgm_suggestion=script.get("bgm_suggestion", ""),
        )

        for scene_data in script.get("scenes", []):
            scene = StoryboardScene(
                scene_number=scene_data.get("scene_number",
                                            len(storyboard.scenes) + 1),
                location=scene_data.get("location", ""),
                time=scene_data.get("time", ""),
                visual_description=scene_data.get("visual_description", ""),
                visual_anchor=scene_data.get("visual_anchor", ""),
                continuity_from_previous=scene_data.get("continuity_from_previous", ""),
                leads_to_next=scene_data.get("leads_to_next", ""),
                story_beat=scene_data.get("story_beat", ""),
                motion_intent=scene_data.get("motion_intent", ""),
                camera_movement=scene_data.get("camera_movement", "静态"),
                mood=scene_data.get("mood", ""),
                narration=scene_data.get("narration", ""),
                dialogues=scene_data.get("dialogues", []),
                characters=scene_data.get("characters", []),
                duration=float(scene_data.get("duration", 4.0)),
                image_path=scene_data.get("image_path", ""),
                video_path=scene_data.get("video_path", ""),
                audio_path=scene_data.get("audio_path", ""),
            )
            storyboard.scenes.append(scene)

        storyboard.total_duration = storyboard.get_total_duration()
        return storyboard

    def to_dict(self, storyboard: Storyboard) -> dict:
        """将分镜对象转回字典（用于保存/编辑）"""
        scenes = []
        for s in storyboard.scenes:
            scene_dict = {
                "scene_number": s.scene_number,
                "location": s.location,
                "time": s.time,
                "visual_description": s.visual_description,
                "visual_anchor": s.visual_anchor,
                "continuity_from_previous": s.continuity_from_previous,
                "leads_to_next": s.leads_to_next,
                "story_beat": s.story_beat,
                "motion_intent": s.motion_intent,
                "camera_movement": s.camera_movement,
                "mood": s.mood,
                "narration": s.narration,
                "dialogues": s.dialogues,
                "duration": s.duration,
            }
            if s.image_path:
                scene_dict["image_path"] = s.image_path
            if s.video_path:
                scene_dict["video_path"] = s.video_path
            if s.audio_path:
                scene_dict["audio_path"] = s.audio_path
            scenes.append(scene_dict)

        return {
            "title": storyboard.title,
            "genre": storyboard.genre,
            "theme": storyboard.theme,
            "characters": storyboard.characters,
            "scenes": scenes,
            "bgm_suggestion": storyboard.bgm_suggestion,
            "total_duration": storyboard.total_duration,
        }

    def get_image_prompt(self, scene: StoryboardScene) -> str:
        """
        根据场景生成用于AI绘图的prompt

        Args:
            scene: 分镜场景

        Returns:
            适合生图API的prompt文本
        """
        # 构建英文生图prompt（大部分生图API英文效果更好）
        parts = []

        # 基础风格
        parts.append("cinematic shot, dramatic lighting, high quality, 8k resolution")

        # 场景描述
        if scene.visual_description:
            # 将中文描述翻译为生图关键词
            parts.append(scene.visual_description)

        # 情绪氛围
        if scene.mood:
            mood_map = {
                "紧张": "tense atmosphere, dark shadows",
                "温馨": "warm and cozy atmosphere, soft golden light",
                "悲伤": "melancholic mood, blue tones, tearful",
                "激烈": "intense action, dynamic composition",
                "浪漫": "romantic atmosphere, soft focus, warm light",
                "恐怖": "horror atmosphere, dark, eerie",
                "欢乐": "joyful atmosphere, bright colors",
                "愤怒": "angry mood, red tones, intense",
            }
            mood_en = mood_map.get(scene.mood, f"{scene.mood} mood")
            parts.append(mood_en)

        # 竖屏比例
        parts.append("vertical composition 9:16 aspect ratio")

        return ", ".join(parts)

    def estimate_duration(self, text: str) -> float:
        """
        根据文字长度估算语音时长

        中文每秒约4-5个字
        """
        if not text:
            return 2.0
        char_count = len(text.replace(" ", "").replace("\n", ""))
        # 中文语速约每秒4-5字
        estimated = char_count / 4.5
        # 加上适当的停顿时间
        return max(2.0, min(estimated + 1.0, 10.0))
