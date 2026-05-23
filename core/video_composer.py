"""
AI短剧生成器 - 视频合成模块
使用MoviePy合成图片+配音+字幕→MP4视频
支持 Ken Burns、本地动效 MP4 片段、转场；动漫模式下可自动用本地动效替代纯静图
"""
import os
import shutil
import tempfile
from typing import List, Optional, Dict, Any
import gc

from config import load_config
from logger import get_logger
from core.storyboard import StoryboardScene
from core.subtitle import SubtitleGenerator

logger = get_logger("video_composer")


class VideoComposer:
    """视频合成器"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or load_config()
        self.width = self.config.get("video_width", 1080)
        self.height = self.config.get("video_height", 1920)
        self.fps = self.config.get("video_fps", 24)
        self.transition_duration = self.config.get("transition_duration", 0.5)

    def _should_use_local_motion_fallback(self) -> bool:
        """无分镜 video 文件时，是否用本地 MoviePy 短片代替 Ken Burns。"""
        mode = (self.config.get("scene_clip_fallback") or "auto").strip().lower()
        if mode == "local_motion":
            return True
        if mode == "ken_burns":
            return False
        return (self.config.get("visual_style") or "live_action").strip().lower() == "anime_cartoon"

    def compose(
        self,
        scenes: List[StoryboardScene],
        output_path: str,
        on_progress=None,
    ) -> str:
        """
        合成完整视频

        如果场景有 video_path，使用动态视频片段（更真实）。
        若开启 scene_clip_fallback（动漫 auto 默认），无 video 时临时生成本地动效 MP4，减少「PPT 切图」感。
        否则使用 image_path + Ken Burns 效果。

        Args:
            scenes: 分镜场景列表
            output_path: 输出MP4路径
            on_progress: 进度回调 fn(current, total, message)

        Returns:
            输出文件路径
        """
        logger.info(f"开始合成视频，共 {len(scenes)} 个场景")
        
        from moviepy.editor import (
            ImageClip, AudioFileClip, CompositeVideoClip,
            concatenate_videoclips, ColorClip, VideoFileClip
        )

        total = len(scenes)
        clips = []
        motion_tmpdir = None

        self.config = load_config()

        if on_progress:
            on_progress(0, total, "开始合成视频...")

        for i, scene in enumerate(scenes):
            if on_progress:
                on_progress(i, total, f"处理场景 {i+1}/{total}...")

            logger.debug(f"处理场景 {i+1}/{total}")

            # 优先使用动态视频片段
            video_path = getattr(scene, "video_path", None)
            clip = None

            if video_path and os.path.exists(video_path):
                try:
                    clip = VideoFileClip(video_path)
                    if clip.size != (self.width, self.height):
                        clip = clip.resize((self.width, self.height))
                    logger.debug(f"使用视频片段: {video_path}")
                except Exception as e:
                    logger.warning(f"加载视频失败 {video_path}: {e}")
                    clip = None
            elif scene.image_path and os.path.exists(scene.image_path):
                if self._should_use_local_motion_fallback():
                    if motion_tmpdir is None:
                        motion_tmpdir = tempfile.mkdtemp(prefix="ai_short_drama_motion_")
                    if on_progress:
                        on_progress(i, total, f"场景 {i+1}/{total}：生成本地动效片段…")
                    saved_vp = getattr(scene, "video_path", None) or ""
                    try:
                        from core.video_generator import VideoGenerator
                        vg = VideoGenerator()
                        vg.generate_scene_video(
                            scene,
                            motion_tmpdir,
                            on_progress=lambda m: on_progress(i, total, m) if on_progress else None,
                            force_local=True,
                        )
                        vp2 = getattr(scene, "video_path", None)
                        if vp2 and os.path.exists(vp2) and os.path.getsize(vp2) > 1000:
                            clip = VideoFileClip(vp2)
                            if clip.size != (self.width, self.height):
                                clip = clip.resize((self.width, self.height))
                            logger.debug(f"使用本地动效片段: {vp2}")
                    except Exception as e:
                        logger.warning(f"本地动效片段失败，使用 Ken Burns：{e}")
                    finally:
                        scene.video_path = saved_vp
                if clip is None:
                    clip = self._create_image_clip_with_ken_burns(
                        scene.image_path, scene.duration
                    )
                    logger.debug(f"使用 Ken Burns 效果: {scene.image_path}")
            else:
                # 都没有，生成占位图片
                from PIL import Image, ImageDraw, ImageFont
                placeholder_path = os.path.join(
                    os.path.dirname(output_path),
                    f"placeholder_{scene.scene_number:02d}.png"
                )
                self._create_placeholder(scene, placeholder_path)
                scene.image_path = placeholder_path
                clip = self._create_image_clip_with_ken_burns(
                    placeholder_path, scene.duration
                )
                logger.debug(f"使用占位图片: {placeholder_path}")

            # 先对齐音频时长（避免 set_duration 拉长后出现 4–5 秒黑屏+仍有声音）
            audio_clip = None
            if (scene.audio_path and
                    os.path.exists(scene.audio_path) and
                    os.path.getsize(scene.audio_path) > 100):
                try:
                    audio_clip = AudioFileClip(scene.audio_path)
                    scene.duration = float(audio_clip.duration)
                    clip = self._fit_visual_clip_to_duration(clip, scene.duration)
                    logger.debug(f"加载音频: {scene.audio_path}")
                except Exception as e:
                    logger.warning(f"加载音频失败 {scene.audio_path}：{e}")
                    audio_clip = None

            # 添加字幕（时长已与配音一致）
            subtitle_clips = SubtitleGenerator.create_subtitle_clips_for_scene(
                scene, 0, self.width, self.height
            )
            if subtitle_clips:
                clip = CompositeVideoClip([clip] + subtitle_clips)

            if audio_clip is not None:
                try:
                    clip = clip.set_audio(audio_clip)
                except Exception as e:
                    logger.warning(f"绑定音频失败：{e}")

            clips.append(clip)

        if on_progress:
            on_progress(total, total, "正在拼接所有场景...")

        logger.info("拼接所有场景...")

        # 拼接所有场景（带转场效果）
        final_clip = self._concatenate_with_transitions(clips)

        if self.config.get("bgm_enabled") and (self.config.get("bgm_path") or "").strip():
            if on_progress:
                on_progress(total, total, "正在叠加背景音乐…")
            from core.bgm_mixer import apply_bgm_to_clip
            bgm_mixed = apply_bgm_to_clip(
                final_clip,
                self.config["bgm_path"].strip(),
                volume=float(self.config.get("bgm_volume", 0.18)),
            )
            if bgm_mixed is not final_clip:
                final_clip.close()
                final_clip = bgm_mixed

        # 写入文件
        if on_progress:
            on_progress(total, total, "正在编码输出视频（可能需要几分钟）...")

        logger.info("编码输出视频...")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        try:
            final_clip.write_videofile(
                output_path,
                fps=self.fps,
                codec="libx264",
                audio_codec="aac",
                temp_audiofile=os.path.join(tempfile.gettempdir(), "temp-audio.m4a"),
                remove_temp=True,
                preset="medium",
                threads=4,
                logger=None,
            )
            logger.info(f"视频编码完成: {output_path}")
        finally:
            final_clip.close()
            for clip in clips:
                clip.close()
            if motion_tmpdir and os.path.isdir(motion_tmpdir):
                shutil.rmtree(motion_tmpdir, ignore_errors=True)
            
            # 强制垃圾回收
            gc.collect()

        if on_progress:
            on_progress(total, total, f"视频生成完成！保存至：{output_path}")

        logger.info(f"视频合成完成: {output_path}")
        return output_path

    def _create_image_clip_with_ken_burns(self, image_path: str, duration: float):
        """
        创建带Ken Burns效果的图片剪辑

        Ken Burns效果：图片缓慢缩放和平移，增加动感
        改进版：避免图片被切割，增强动画效果
        """
        from moviepy.editor import ImageClip, CompositeVideoClip, ColorClip

        clip = ImageClip(image_path, duration=duration)

        # 先调整图片尺寸以适应视频比例，保持宽高比
        img_ratio = clip.w / clip.h
        target_ratio = self.width / self.height

        if img_ratio > target_ratio:
            new_h = self.height
            new_w = int(new_h * img_ratio)
        else:
            new_w = self.width
            new_h = int(new_w / img_ratio)

        clip = clip.resize((new_w, new_h))

        # 随机/交替选择Ken Burns方向
        import random
        effect_type = random.choice(["zoom_in", "zoom_out", "pan_right", "pan_left", "diagonal"])

        if effect_type == "zoom_in":
            # 缓慢放大，从中心开始
            clip = clip.resize(lambda t: 1.0 + 0.15 * (t / duration))
            clip = clip.set_position(
                lambda t: (
                    (self.width - clip.w) / 2,
                    (self.height - clip.h) / 2
                )
            )

        elif effect_type == "zoom_out":
            # 缓慢缩小
            clip = clip.resize(lambda t: 1.15 - 0.15 * (t / duration))
            clip = clip.set_position(
                lambda t: (
                    (self.width - clip.w) / 2,
                    (self.height - clip.h) / 2
                )
            )

        elif effect_type == "pan_right":
            # 从左边缓慢向右边平移
            clip = clip.resize(1.15)
            clip = clip.set_position(
                lambda t: (
                    -(clip.w - self.width) * (t / duration),
                    (self.height - clip.h) / 2
                )
            )

        elif effect_type == "pan_left":
            # 从右边缓慢向左边平移
            clip = clip.resize(1.15)
            clip = clip.set_position(
                lambda t: (
                    -(clip.w - self.width) * (1 - t / duration),
                    (self.height - clip.h) / 2
                )
            )

        elif effect_type == "diagonal":
            # 对角线移动 + 缩放
            clip = clip.resize(lambda t: 1.0 + 0.1 * (t / duration))
            clip = clip.set_position(
                lambda t: (
                    -(clip.w - self.width) * (t / duration) * 0.3,
                    -(clip.h - self.height) * (t / duration) * 0.3
                )
            )

        # 创建黑色背景
        background = ColorClip(size=(self.width, self.height), color=(0, 0, 0), duration=duration)

        # 组合背景和图片
        final_clip = CompositeVideoClip([background, clip], size=(self.width, self.height))
        final_clip = final_clip.set_duration(duration)

        return final_clip

    def _fit_visual_clip_to_duration(self, clip, target_duration: float):
        """
        将画面时长与配音对齐：过长则截断，过短则循环/定格末帧（禁止黑屏填充）。
        """
        from moviepy.editor import concatenate_videoclips, ImageClip

        target_duration = max(0.1, float(target_duration))
        video_d = float(clip.duration or 0)

        if video_d <= 0:
            return clip

        if target_duration <= video_d + 0.05:
            return clip.subclip(0, target_duration)

        # 配音更长：末帧定格 + 必要时循环，避免 MoviePy set_duration 拉出黑场
        parts = []
        remaining = target_duration
        loops = 0
        while remaining > 0.02 and loops < 20:
            if remaining >= video_d - 0.05:
                parts.append(clip)
                remaining -= video_d
                loops += 1
            else:
                parts.append(clip.subclip(0, remaining))
                remaining = 0
        if not parts:
            return clip.subclip(0, min(video_d, target_duration))

        if len(parts) == 1:
            merged = parts[0]
        else:
            merged = concatenate_videoclips(parts, method="chain")

        if merged.duration > target_duration + 0.05:
            merged = merged.subclip(0, target_duration)
        elif merged.duration < target_duration - 0.05:
            try:
                t_last = max(0.0, merged.duration - 1.0 / max(self.fps, 1))
                frame = merged.get_frame(t_last)
                tail = ImageClip(frame).set_duration(target_duration - merged.duration)
                merged = concatenate_videoclips([merged, tail], method="chain")
            except Exception:
                pass
        return merged

    def _concatenate_with_transitions(self, clips: list):
        """
        顺序拼接分镜（不单独 crossfadein，避免转场处露出黑底）。
        可选极短交叉淡入淡出：padding 为负，使片段重叠而非插入黑场。
        """
        from moviepy.editor import concatenate_videoclips

        if len(clips) == 1:
            return clips[0]

        td = min(max(float(self.transition_duration), 0), 0.4)
        if td <= 0.05:
            return concatenate_videoclips(clips, method="compose")

        faded = [clips[0]]
        for c in clips[1:]:
            faded.append(c.crossfadein(td))
        return concatenate_videoclips(faded, method="compose", padding=-td)
    
    def _apply_soft_slide(self, clip, duration):
        """对单个片段应用轻微滑动效果"""
        import random
        direction = random.choice(["left", "right", "up", "down"])
        slide_distance = 50
        
        if direction == "left":
            clip = clip.set_position(lambda t: (slide_distance * (1 - min(t / duration, 1.0)), 0))
        elif direction == "right":
            clip = clip.set_position(lambda t: (-slide_distance * (1 - min(t / duration, 1.0)), 0))
        elif direction == "up":
            clip = clip.set_position(lambda t: (0, slide_distance * (1 - min(t / duration, 1.0))))
        else:
            clip = clip.set_position(lambda t: (0, -slide_distance * (1 - min(t / duration, 1.0))))
        
        return clip
    
    def _apply_soft_zoom(self, clip, duration):
        """对单个片段应用轻微缩放效果"""
        import random
        zoom_type = random.choice(["in", "out"])
        zoom_factor = 0.05
        
        if zoom_type == "in":
            clip = clip.resize(lambda t: (1.0 + zoom_factor) - zoom_factor * min(t / duration, 1.0))
        else:
            clip = clip.resize(lambda t: (1.0 - zoom_factor) + zoom_factor * min(t / duration, 1.0))
        
        return clip

    def _transition_crossfade(self, prev_clip, curr_clip, duration):
        """交叉淡入淡出转场（电视剧最常用的转场）"""
        from moviepy.editor import concatenate_videoclips
        
        # 创建淡入淡出效果
        curr_with_fade = curr_clip.crossfadein(duration)
        prev_with_fade = prev_clip.crossfadeout(duration)
        
        # 拼接时确保没有黑色间隙
        result = concatenate_videoclips([prev_with_fade, curr_with_fade], method="compose")
        return result

    def _transition_soft_slide(self, prev_clip, curr_clip, duration):
        """轻微滑动转场（电视剧风格，不夸张）"""
        from moviepy.editor import concatenate_videoclips
        
        # 只滑动很小的距离，保持自然
        slide_distance = 50  # 只滑动50像素
        
        # 随机选择滑动方向
        import random
        direction = random.choice(["left", "right", "up", "down"])
        
        if direction == "left":
            curr_slide = curr_clip.set_position(
                lambda t: (
                    slide_distance * (1 - min(t / duration, 1.0)),
                    0
                )
            )
        elif direction == "right":
            curr_slide = curr_clip.set_position(
                lambda t: (
                    -slide_distance * (1 - min(t / duration, 1.0)),
                    0
                )
            )
        elif direction == "up":
            curr_slide = curr_clip.set_position(
                lambda t: (
                    0,
                    slide_distance * (1 - min(t / duration, 1.0))
                )
            )
        else:  # down
            curr_slide = curr_clip.set_position(
                lambda t: (
                    0,
                    -slide_distance * (1 - min(t / duration, 1.0))
                )
            )
        
        # 配合淡入淡出，更加平滑
        prev_fade = prev_clip.crossfadeout(duration * 0.7)
        curr_fade = curr_slide.crossfadein(duration * 0.7)
        
        result = concatenate_videoclips([prev_fade, curr_fade], method="compose")
        return result

    def _transition_soft_zoom(self, prev_clip, curr_clip, duration):
        """轻微缩放转场（电视剧风格，不夸张）"""
        from moviepy.editor import concatenate_videoclips
        
        # 只缩放很小的比例
        zoom_factor = 0.05  # 只缩放5%
        
        # 随机选择放大或缩小
        import random
        zoom_type = random.choice(["in", "out"])
        
        if zoom_type == "in":
            # 当前片段从轻微放大状态缩小到正常
            curr_zoom = curr_clip.resize(lambda t: (1.0 + zoom_factor) - zoom_factor * min(t / duration, 1.0))
            curr_zoom = curr_zoom.crossfadein(duration)
            prev_fade = prev_clip.crossfadeout(duration)
        else:
            # 当前片段从轻微缩小状态放大到正常
            curr_zoom = curr_clip.resize(lambda t: (1.0 - zoom_factor) + zoom_factor * min(t / duration, 1.0))
            curr_zoom = curr_zoom.crossfadein(duration)
            prev_fade = prev_clip.crossfadeout(duration)
        
        result = concatenate_videoclips([prev_fade, curr_zoom], method="compose")
        return result

    def _create_placeholder(self, scene: StoryboardScene, output_path: str):
        """创建占位图片"""
        from PIL import Image, ImageDraw, ImageFont
        import textwrap

        img = Image.new('RGB', (self.width, self.height), color=(40, 40, 70))
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 48)
            small_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 32)
        except (OSError, IOError):
            font = ImageFont.load_default()
            small_font = font

        # 场景编号
        draw.text(
            (self.width // 2 - 60, self.height // 3),
            f"场景 {scene.scene_number}",
            font=font,
            fill=(220, 220, 220),
        )

        # 描述文字
        desc = scene.visual_description or "暂无描述"
        wrapped = textwrap.wrap(desc, width=16)
        y = self.height // 2
        for line in wrapped[:10]:
            draw.text(
                (80, y),
                line,
                font=small_font,
                fill=(180, 180, 220),
            )
            y += 40

        img.save(output_path, 'PNG')

    def preview_scene(
        self,
        scene: StoryboardScene,
        output_path: Optional[str] = None,
    ) -> str:
        """
        生成单个场景的预览视频（无音频，仅画面）

        Args:
            scene: 分镜场景
            output_path: 输出路径

        Returns:
            预览视频路径
        """
        from moviepy.editor import ImageClip

        if not output_path:
            output_path = os.path.join(
                self.config.get("output_dir", "."),
                "preview",
                f"scene_{scene.scene_number:02d}.mp4"
            )

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        if not scene.image_path or not os.path.exists(scene.image_path):
            self._create_placeholder(scene, os.path.join(
                os.path.dirname(output_path),
                f"placeholder_{scene.scene_number:02d}.png"
            ))
            scene.image_path = os.path.join(
                os.path.dirname(output_path),
                f"placeholder_{scene.scene_number:02d}.png"
            )

        clip = self._create_image_clip_with_ken_burns(
            scene.image_path, scene.duration
        )

        # 添加字幕
        subtitle_clips = SubtitleGenerator.create_subtitle_clips_for_scene(
            scene, 0, self.width, self.height
        )
        if subtitle_clips:
            from moviepy.editor import CompositeVideoClip
            clip = CompositeVideoClip([clip] + subtitle_clips)

        clip.write_videofile(
            output_path,
            fps=self.fps,
            codec="libx264",
            logger=None,
        )
        clip.close()

        return output_path

    def compose_from_srt(
        self,
        image_paths: List[str],
        audio_paths: List[str],
        srt_path: str,
        output_path: str,
        durations: Optional[List[float]] = None,
        on_progress=None,
    ) -> str:
        """
        通过SRT字幕文件和图片/音频列表合成视频

        这是一个更底层的接口，适合精细控制
        """
        from moviepy.editor import (
            ImageClip, AudioFileClip, TextClip,
            CompositeVideoClip, concatenate_videoclips
        )

        if durations is None:
            durations = [4.0] * len(image_paths)

        clips = []
        current_time = 0.0

        for i, (img_path, audio_path, duration) in enumerate(
            zip(image_paths, audio_paths, durations)
        ):
            if on_progress:
                on_progress(i, len(image_paths), f"合成场景 {i+1}...")

            img_clip = ImageClip(img_path, duration=duration)
            img_clip = img_clip.resize((self.width, self.height))

            if os.path.exists(audio_path):
                audio_clip = AudioFileClip(audio_path)
                img_clip = img_clip.set_audio(audio_clip)

            clips.append(img_clip)

        final = concatenate_videoclips(clips, method="compose")

        if on_progress:
            on_progress(len(clips), len(clips), "正在编码...")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        final.write_videofile(
            output_path,
            fps=self.fps,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            logger=None,
        )
        final.close()

        return output_path
