"""
AI短剧生成器 - 字幕生成模块
生成SRT字幕文件并叠加到视频
使用PIL渲染字幕图片，不依赖ImageMagick
"""
import os
import textwrap
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont


class SubtitleEntry:
    """字幕条目"""

    def __init__(
        self,
        index: int,
        start_time: float,
        end_time: float,
        text: str,
    ):
        self.index = index
        self.start_time = start_time
        self.end_time = end_time
        self.text = text

    def to_srt(self) -> str:
        """转换为SRT格式单行"""
        start = self._format_time(self.start_time)
        end = self._format_time(self.end_time)
        return f"{self.index}\n{start} --> {end}\n{self.text}\n"

    @staticmethod
    def _format_time(seconds: float) -> str:
        """将秒转为SRT时间格式 HH:MM:SS,mmm"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds - int(seconds)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


class SubtitleGenerator:
    """字幕生成器（基于PIL，不依赖ImageMagick）"""

    # 尝试加载中文字体
    _FONT_PATH = None
    _FONT_SMALL_PATH = None
    for _fp in [
        "C:/Windows/Fonts/msyh.ttc",       # 微软雅黑
        "C:/Windows/Fonts/simhei.ttf",      # 黑体
        "C:/Windows/Fonts/simsun.ttc",      # 宋体
    ]:
        if os.path.exists(_fp):
            _FONT_PATH = _fp
            _FONT_SMALL_PATH = _fp
            break

    @staticmethod
    def _get_font(size: int):
        """获取字体"""
        if SubtitleGenerator._FONT_PATH:
            try:
                return ImageFont.truetype(SubtitleGenerator._FONT_PATH, size)
            except (OSError, IOError):
                pass
        return ImageFont.load_default()

    @staticmethod
    def _render_subtitle_image(text: str, width: int = 1000, fontsize: int = 50):
        """
        用PIL渲染字幕图片（带半透明黑底背景）

        Returns:
            PIL.Image 对象
        """
        font = SubtitleGenerator._get_font(fontsize)

        # 自动换行
        max_chars = max(1, (width - 60) // fontsize)
        wrapped_lines = []
        for line in text.split("\n"):
            wrapped_lines.extend(textwrap.wrap(line, width=max_chars) or [""])

        line_height = fontsize + 16
        padding = 20
        img_height = line_height * len(wrapped_lines) + padding * 2

        # 创建RGBA图片（支持透明背景）
        img = Image.new("RGBA", (width, img_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 绘制半透明黑色背景
        draw.rounded_rectangle(
            [(0, 0), (width, img_height)],
            radius=10,
            fill=(0, 0, 0, 140),
        )

        # 绘制文字
        y = padding
        for line in wrapped_lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            x = (width - text_w) // 2
            # 黑色描边效果
            for dx in [-2, -1, 0, 1, 2]:
                for dy in [-2, -1, 0, 1, 2]:
                    if dx != 0 or dy != 0:
                        draw.text((x + dx, y + dy), line, fill=(0, 0, 0, 200), font=font)
            # 白色文字
            draw.text((x, y), line, fill=(255, 255, 255, 255), font=font)
            y += line_height

        return img

    @staticmethod
    def generate_from_scenes(
        scenes: list,
        output_path: str,
    ) -> str:
        """
        根据分镜场景生成SRT字幕文件

        Args:
            scenes: 分镜场景列表（每个场景有audio_path、narration、dialogues等）
            output_path: SRT文件输出路径

        Returns:
            SRT文件路径
        """
        entries = []
        current_time = 0.0
        index = 1

        for scene in scenes:
            # 获取场景的文字内容
            text_parts = []

            narration = getattr(scene, "narration", "") or ""
            if narration:
                text_parts.append(narration)

            dialogues = getattr(scene, "dialogues", []) or []
            for d in dialogues:
                line = d.get("line", "")
                character = d.get("character", "")
                if character and line:
                    text_parts.append(f"{character}：{line}")
                elif line:
                    text_parts.append(line)

            if not text_parts:
                # 没有文字，跳过这个场景
                continue

            text = "\n".join(text_parts)

            # 获取场景时长
            duration = getattr(scene, "duration", 4.0)

            entry = SubtitleEntry(
                index=index,
                start_time=current_time,
                end_time=current_time + duration,
                text=text,
            )
            entries.append(entry)
            index += 1
            current_time += duration

        # 写入SRT文件
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(entry.to_srt())
                f.write("\n")

        return output_path

    @staticmethod
    def generate_srt_content(scenes: list) -> str:
        """
        生成SRT字幕内容（字符串）

        Args:
            scenes: 分镜场景列表

        Returns:
            SRT格式字符串
        """
        entries = []
        current_time = 0.0
        index = 1

        for scene in scenes:
            text_parts = []

            narration = getattr(scene, "narration", "") or ""
            if narration:
                text_parts.append(narration)

            dialogues = getattr(scene, "dialogues", []) or []
            for d in dialogues:
                line = d.get("line", "")
                character = d.get("character", "")
                if character and line:
                    text_parts.append(f"{character}：{line}")
                elif line:
                    text_parts.append(line)

            if not text_parts:
                continue

            text = "\n".join(text_parts)
            duration = getattr(scene, "duration", 4.0)

            entry = SubtitleEntry(index, current_time, current_time + duration, text)
            entries.append(entry)
            index += 1
            current_time += duration

        return "\n".join(e.to_srt() for e in entries)

    @staticmethod
    def create_subtitle_clip(
        text: str,
        duration: float,
        width: int = 1080,
        height: int = 1920,
    ):
        """
        创建字幕视频片段（用PIL渲染，不依赖ImageMagick）

        Returns:
            moviepy ImageClip
        """
        from moviepy.editor import ImageClip
        import numpy as np

        # 用PIL渲染字幕图片
        sub_width = width - 80
        pil_img = SubtitleGenerator._render_subtitle_image(text, width=sub_width, fontsize=48)

        # 转为numpy数组（RGBA→RGB，透明部分用黑色填充）
        bg = Image.new("RGB", pil_img.size, (0, 0, 0))
        bg.paste(pil_img, mask=pil_img.split()[3])
        frame = np.array(bg)

        txt_clip = ImageClip(frame, duration=duration)
        txt_clip = txt_clip.set_position(("center", height - 280))
        return txt_clip

    @staticmethod
    def create_subtitle_clips_for_scene(
        scene,
        scene_start_time: float,
        width: int = 1080,
        height: int = 1920,
    ) -> list:
        """
        为单个场景创建字幕clip列表（用PIL渲染，不依赖ImageMagick）

        Returns:
            moviepy ImageClip 列表
        """
        from moviepy.editor import ImageClip
        import numpy as np

        clips = []
        duration = getattr(scene, "duration", 4.0)

        # 合并文字
        text_parts = []
        narration = getattr(scene, "narration", "") or ""
        if narration:
            text_parts.append(narration)

        dialogues = getattr(scene, "dialogues", []) or []
        for d in dialogues:
            line = d.get("line", "")
            character = d.get("character", "")
            if character and line:
                text_parts.append(f"{character}：{line}")
            elif line:
                text_parts.append(line)

        if not text_parts:
            return clips

        full_text = "\n".join(text_parts)

        # 用PIL渲染字幕图片
        sub_width = width - 80
        pil_img = SubtitleGenerator._render_subtitle_image(full_text, width=sub_width, fontsize=50)

        # RGBA→RGB
        bg = Image.new("RGB", pil_img.size, (0, 0, 0))
        bg.paste(pil_img, mask=pil_img.split()[3])
        frame = np.array(bg)

        txt_clip = ImageClip(frame, duration=duration)
        subtitle_y = height - 280
        txt_clip = (
            txt_clip.set_position(("center", subtitle_y))
            .set_start(scene_start_time)
            .set_duration(duration)
        )
        clips.append(txt_clip)

        return clips
