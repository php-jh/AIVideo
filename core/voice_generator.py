"""
AI短剧生成器 - 配音生成模块
使用Edge TTS生成中文配音
"""
import os
import asyncio
from typing import Optional, List, Dict, Any
import edge_tts
from config import load_config
from logger import get_logger

logger = get_logger("voice_generator")


class VoiceGenerator:
    """配音生成器"""

    # 常用的中文Edge TTS音色
    VOICE_MAP: Dict[str, str] = {
        # 男声
        "zh-CN-YunxiNeural": "云希（男声，年轻，适合旁白）",
        "zh-CN-YunjianNeural": "云健（男声，成熟，适合霸总）",
        "zh-CN-YunyangNeural": "云扬（男声，新闻播报风）",
        "zh-CN-YunzeNeural": "云泽（男声，沉稳）",
        # 女声
        "zh-CN-XiaoxiaoNeural": "晓晓（女声，温柔，通用）",
        "zh-CN-XiaoyiNeural": "晓依（女声，知性）",
        "zh-CN-XiaohanNeural": "晓涵（女声，活泼）",
        "zh-CN-XiaomoNeural": "晓墨（女声，文艺）",
        "zh-CN-XiaoshuangNeural": "晓双（女声，少女）",
        "zh-CN-XiaochenNeural": "晓辰（女声，温柔）",
    }

    # 男声列表（用于角色分配）
    MALE_VOICES = [
        "zh-CN-YunxiNeural",
        "zh-CN-YunjianNeural",
        "zh-CN-YunyangNeural",
        "zh-CN-YunzeNeural",
    ]

    # 女声列表（用于角色分配，按温柔程度排序）
    FEMALE_VOICES = [
        "zh-CN-XiaochenNeural",  # 晓辰（最温柔）
        "zh-CN-XiaoxiaoNeural",  # 晓晓（温柔通用）
        "zh-CN-XiaomoNeural",    # 晓墨（文艺温柔）
        "zh-CN-XiaoyiNeural",    # 晓依（知性）
        "zh-CN-XiaoshuangNeural", # 晓双（少女）
        "zh-CN-XiaohanNeural",   # 晓涵（活泼）
    ]

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or load_config()
        self.narrator_voice: str = self.config.get(
            "tts_voice_narrator", "zh-CN-YunxiNeural"
        )
        self.male_voice: str = self.config.get(
            "tts_voice_male", "zh-CN-YunxiNeural"
        )
        self.female_voice: str = self.config.get(
            "tts_voice_female", "zh-CN-XiaoxiaoNeural"
        )
        # 角色音色映射表（同一角色始终使用同一音色）
        self._character_voice_map: Dict[str, str] = {}
        # 用于分配音色的计数器
        self._male_voice_index = 0
        self._female_voice_index = 0
        self._script_characters: List[dict] = []

    def _gender_for_character(self, character: str) -> str:
        for ch in self._script_characters:
            if isinstance(ch, dict) and (ch.get("name") or "").strip() == character:
                return (ch.get("gender") or "male").strip().lower()
        return "male"

    def _rate_for_character(self, character: str, gender: str) -> str:
        """老人略慢、大妈略快，增强区分度。"""
        if self.config.get("elderly_daily_mode"):
            g = gender or self._gender_for_character(character)
            if g == "female":
                return "-5%"
            # 默认男老人
            if character and any(k in character for k in ("大爷", "叔", "爷", "伯")):
                return "-12%"
            return "-8%"
        return "-10%" if gender == "female" else "+0%"

    def seed_voices_from_characters(self, script_characters: Optional[List[dict]] = None) -> None:
        """从剧本 characters[].tts_voice 预置角色音色。"""
        if not script_characters:
            return
        for ch in script_characters:
            if not isinstance(ch, dict):
                continue
            name = (ch.get("name") or "").strip()
            voice = (ch.get("tts_voice") or "").strip()
            if name and voice in self.VOICE_MAP:
                self._character_voice_map[name] = voice
                logger.info(
                    f"角色 [{name}] 使用指定音色: {self.VOICE_MAP.get(voice, voice)}"
                )

    def get_character_voice(self, character: str, gender: str) -> str:
        """
        获取角色的固定音色（同一角色始终返回同一音色）

        Args:
            character: 角色名称
            gender: 性别 (male/female)

        Returns:
            音色ID
        """
        # 如果该角色已经有分配的音色，直接返回
        if character in self._character_voice_map:
            return self._character_voice_map[character]

        # 根据性别分配音色
        if gender == "male":
            voice = self.MALE_VOICES[self._male_voice_index % len(self.MALE_VOICES)]
            self._male_voice_index += 1
        else:
            voice = self.FEMALE_VOICES[self._female_voice_index % len(self.FEMALE_VOICES)]
            self._female_voice_index += 1

        # 记录映射
        self._character_voice_map[character] = voice
        logger.info(f"为角色 [{character}] 分配音色: {self.VOICE_MAP.get(voice, voice)}")
        return voice

    async def _generate_audio_async(self, text: str, voice: str,
                                     output_path: str,
                                     rate: str = "+0%",
                                     volume: str = "+0%") -> float:
        """
        异步生成单条语音，带重试逻辑。

        Args:
            text: 要转换的文字
            voice: 音色
            output_path: 输出文件路径
            rate: 语速调整 (如 "+10%", "-10%")
            volume: 音量调整

        Returns:
            音频时长（秒）
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        clean_text = text.strip() if text else ""
        if not clean_text:
            # 文本为空，生成静音文件
            logger.warning(f"文本为空，生成静音文件: {output_path}")
            return self._create_silent_audio(output_path)

        communicate = edge_tts.Communicate(
            text=clean_text,
            voice=voice,
            rate=rate,
            volume=volume,
        )

        # 重试逻辑：Edge TTS 偶发 "No audio was received"
        max_retries = 2
        for attempt in range(max_retries):
            try:
                await communicate.save(output_path)
                logger.info(f"音频生成成功: {output_path}")
                break
            except Exception as e:
                err_msg = str(e)
                if attempt < max_retries - 1:
                    logger.warning(f"Edge TTS 重试中 ({attempt+1}/{max_retries})：{err_msg}")
                    await asyncio.sleep(2)
                else:
                    logger.error(f"Edge TTS 失败（已重试 {max_retries} 次）：{err_msg}")
                    return self._create_silent_audio(output_path)

        # 获取音频时长
        duration = await self._get_audio_duration(output_path)
        return duration

    def _create_silent_audio(self, output_path: str, duration: float = 1.0) -> float:
        """
        生成静音音频文件。
        优先用 moviepy AudioArrayClip；全部失败则写入最小有效 MP3 文件头。
        返回静音时长（秒）。
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # 方法1：moviepy AudioArrayClip
        try:
            from moviepy.audio.AudioClip import AudioArrayClip
            import numpy as np
            fps = 44100
            n_frames = int(duration * fps)
            # 立体声静音数据
            audio_data = np.zeros((n_frames, 2), dtype=np.float32)
            clip = AudioArrayClip(audio_data, fps=fps)
            clip.write_audiofile(output_path, verbose=False, logger=None)
            clip.close()
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logger.info(f"已生成静音文件（AudioArrayClip）：{output_path}")
                return duration
        except Exception as e:
            logger.warning(f"AudioArrayClip 静音失败：{e}")

        # 方法2：写入空文件标记（0字节），video_composer 会跳过
        try:
            with open(output_path, "wb") as f:
                pass
            logger.info(f"已生成空静音文件标记（video_composer 会跳过）：{output_path}")
            return 0.0
        except Exception as e2:
            logger.error(f"生成空静音文件失败：{e2}")
            return 0.0

    def _read_audio_duration_safe(self, filepath: str, fallback: float = 4.0) -> float:
        """读取音频实际时长，用于同步 scene.duration。"""
        try:
            from moviepy.editor import AudioFileClip
            audio = AudioFileClip(filepath)
            d = float(audio.duration or fallback)
            audio.close()
            return max(0.5, d)
        except Exception:
            return float(fallback)

    async def _get_audio_duration(self, filepath: str) -> float:
        """获取音频文件时长"""
        return self._read_audio_duration_safe(filepath, 1.0)

    def generate_narration(self, text: str, output_path: str,
                           on_progress=None) -> float:
        """
        生成旁白语音

        Args:
            text: 旁白文字
            output_path: 输出文件路径
            on_progress: 进度回调

        Returns:
            音频时长（秒）
        """
        if on_progress:
            on_progress("正在生成旁白...")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        return asyncio.run(
            self._generate_audio_async(text, self.narrator_voice, output_path)
        )

    def generate_dialogue(self, text: str, character: str,
                          gender: str, output_path: str,
                          on_progress=None) -> float:
        """
        生成角色对话语音

        Args:
            text: 台词文字
            character: 角色名
            gender: 性别 (male/female)
            output_path: 输出文件路径
            on_progress: 进度回调

        Returns:
            音频时长（秒）
        """
        # 使用角色固定音色，确保同一角色始终使用同一音色
        voice = self.get_character_voice(character, gender)
        rate = self._rate_for_character(character, gender)

        if on_progress:
            on_progress(f"正在生成 {character} 的配音...")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        return asyncio.run(
            self._generate_audio_async(text, voice, output_path, rate=rate)
        )

    def generate_scene_audio(self, scene, output_dir: str,
                             on_progress=None,
                             script_characters=None) -> str:
        """
        为单个场景生成完整音频（旁白+对话）

        Args:
            scene: 分镜场景对象
            output_dir: 输出目录
            on_progress: 进度回调

        Returns:
            生成的音频文件路径
        """
        os.makedirs(output_dir, exist_ok=True)
        if script_characters:
            self._script_characters = list(script_characters)
            self.seed_voices_from_characters(script_characters)

        has_narration = bool(scene.narration and scene.narration.strip())
        has_dialogues = bool(scene.dialogues)

        filepath = os.path.join(
            output_dir, f"audio_scene_{scene.scene_number:02d}.mp3"
        )

        if (
            os.path.exists(filepath)
            and os.path.getsize(filepath) > 100
            and not getattr(scene, "_force_regen_audio", False)
        ):
            if on_progress:
                on_progress(f"场景 {scene.scene_number} 配音已存在，跳过")
            scene.audio_path = filepath
            scene.duration = self._read_audio_duration_safe(filepath, scene.duration)
            return filepath

        if has_narration and not has_dialogues:
            # 只有旁白
            if on_progress:
                on_progress("正在生成旁白...")
            asyncio.run(
                self._generate_audio_async(
                    scene.narration, self.narrator_voice, filepath
                )
            )
            scene.audio_path = filepath
            scene.duration = self._read_audio_duration_safe(filepath, scene.duration)
            return filepath

        elif has_dialogues and not has_narration:
            # 只有对话
            if len(scene.dialogues) == 1:
                d = scene.dialogues[0]
                char = d.get("character", "")
                gender = d.get("gender") or self._gender_for_character(char)
                voice = self.get_character_voice(char, gender)
                rate = self._rate_for_character(char, gender)
                if on_progress:
                    on_progress(f"正在生成 {char} 的配音...")
                asyncio.run(
                    self._generate_audio_async(
                        d["line"], voice, filepath, rate=rate,
                    )
                )
                scene.audio_path = filepath
                scene.duration = self._read_audio_duration_safe(filepath, scene.duration)
                return filepath
            else:
                return self._merge_dialogues(scene, output_dir, on_progress)

        elif has_narration and has_dialogues:
            # 旁白+对话，分别生成后合并
            return self._merge_narration_and_dialogues(
                scene, output_dir, on_progress
            )

        else:
            # 没有任何文字，生成静音文件
            if on_progress:
                on_progress("无台词，生成静音...")
            self._create_silent_audio(filepath, duration=1.0)
            scene.audio_path = filepath
            return filepath

    def _merge_dialogues(self, scene, output_dir: str,
                         on_progress=None) -> str:
        """合并多条对话音频"""
        from moviepy.editor import concatenate_audioclips, AudioFileClip
        import tempfile

        temp_files = []
        clips = []

        try:
            for i, d in enumerate(scene.dialogues):
                temp_path = os.path.join(
                    output_dir,
                    f"temp_dialogue_{scene.scene_number}_{i}.mp3"
                )
                # 使用角色固定音色
                char = d.get("character", "")
                gender = d.get("gender") or self._gender_for_character(char)
                voice = self.get_character_voice(char, gender)
                rate = self._rate_for_character(char, gender)
                if on_progress:
                    on_progress(f"正在生成 {d['character']} 的配音...")
                asyncio.run(
                    self._generate_audio_async(d["line"], voice, temp_path, rate=rate)
                )
                temp_files.append(temp_path)
                clips.append(AudioFileClip(temp_path))

            # 在对话之间添加短暂停顿
            from moviepy.editor import AudioClip
            import numpy as np
            final_clips = []
            for j, clip in enumerate(clips):
                final_clips.append(clip)
                if j < len(clips) - 1:
                    # 0.5秒静音停顿
                    # AudioClip的lambda函数需要返回单个时间点的样本值
                    silence = AudioClip(lambda t: np.zeros(2), duration=0.5)
                    silence = silence.set_fps(clip.fps)
                    final_clips.append(silence)

            # 拼接所有片段
            final = concatenate_audioclips(final_clips)
            output_path = os.path.join(
                output_dir, f"audio_scene_{scene.scene_number:02d}.mp3"
            )
            final.write_audiofile(output_path, verbose=False, logger=None)
            final.close()

            scene.audio_path = output_path
            scene.duration = self._read_audio_duration_safe(output_path, scene.duration)
            return output_path

        finally:
            # 清理临时文件
            for f in temp_files:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except:
                        pass

    def _merge_narration_and_dialogues(self, scene, output_dir: str,
                                        on_progress=None) -> str:
        """合并旁白和对话音频"""
        from moviepy.editor import concatenate_audioclips, AudioFileClip

        clips = []
        temp_files = []

        try:
            # 先生成旁白
            if scene.narration:
                narration_path = os.path.join(
                    output_dir,
                    f"temp_narration_{scene.scene_number}.mp3"
                )
                self.generate_narration(
                    scene.narration, narration_path, on_progress
                )
                temp_files.append(narration_path)
                clips.append(AudioFileClip(narration_path))

            # 再生成对话
            for i, d in enumerate(scene.dialogues):
                dialogue_path = os.path.join(
                    output_dir,
                    f"temp_dialogue_{scene.scene_number}_{i}.mp3"
                )
                # 使用角色固定音色
                char = d.get("character", "")
                gender = d.get("gender") or self._gender_for_character(char)
                voice = self.get_character_voice(char, gender)
                rate = self._rate_for_character(char, gender)
                if on_progress:
                    on_progress(f"正在生成 {d['character']} 的配音...")
                asyncio.run(
                    self._generate_audio_async(d["line"], voice, dialogue_path, rate=rate)
                )
                temp_files.append(dialogue_path)
                clips.append(AudioFileClip(dialogue_path))

            final = concatenate_audioclips(clips)
            output_path = os.path.join(
                output_dir, f"audio_scene_{scene.scene_number:02d}.mp3"
            )
            final.write_audiofile(output_path, verbose=False, logger=None)
            final.close()

            scene.audio_path = output_path
            scene.duration = self._read_audio_duration_safe(output_path, scene.duration)
            return output_path

        finally:
            for f in temp_files:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except:
                        pass

    def generate_all_audio(
        self,
        scenes,
        output_dir: str,
        on_progress=None,
        script_characters=None,
    ) -> list:
        """
        为所有场景生成音频

        Args:
            scenes: 分镜场景列表
            output_dir: 输出目录
            on_progress: 进度回调 fn(current, total, message)
            script_characters: 剧本角色列表（含 tts_voice 时优先使用）

        Returns:
            音频路径列表
        """
        self._script_characters = list(script_characters or [])
        self.seed_voices_from_characters(script_characters)
        audio_paths = []
        total = len(scenes)

        for i, scene in enumerate(scenes):
            def progress_wrapper(msg):
                if on_progress:
                    on_progress(i + 1, total, msg)

            filepath = self.generate_scene_audio(
                scene, output_dir, progress_wrapper,
                script_characters=script_characters,
            )
            audio_paths.append(filepath)

        return audio_paths
