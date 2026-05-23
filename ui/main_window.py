"""
AI短剧生成器 - 主窗口 (PyQt5)
"""
import os
import json
import uuid
import threading
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QProgressBar,
    QListWidget, QListWidgetItem, QMessageBox,
    QComboBox, QFileDialog, QGroupBox, QSizePolicy, QSplitter,
    QScrollArea, QFrame, QGraphicsPixmapItem,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QPalette, QColor, QPixmap

from config import load_config, save_config, get_output_dir
from logger import get_logger
from core.story_generator import StoryGenerator
from core.storyboard import StoryboardParser
from core.image_generator import ImageGenerator
from core.video_generator import VideoGenerator
from core.voice_generator import VoiceGenerator
from core.video_composer import VideoComposer
from core.history_manager import add_record as history_add_record

logger = get_logger("main_window")


class TaskCancelled(Exception):
    """用户取消后台任务。"""


# ===================== Worker Thread =====================

class Worker(QObject):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(bool, str)
    script_ready = pyqtSignal(object)

    def __init__(self, task_type, **kwargs):
        super().__init__()
        self.task_type = task_type
        self.kwargs = kwargs
        self.cancel_event = kwargs.get("cancel_event")
        self.output_video_path = ""

    def _check_cancel(self):
        if self.cancel_event and self.cancel_event.is_set():
            raise TaskCancelled("任务已取消")

    def _task_config(self):
        """按任务风格合并推荐配置（口播模式自动偏静图+纪实）。"""
        from config import load_config
        from core.style_presets import merge_config_for_style
        base = load_config()
        style = self.kwargs.get("style", "")
        return merge_config_for_style(base, style) if style else base

    def _normalize_script_if_tech(self, script):
        """旧多镜口播稿在生成/合成前合并为一镜到底。"""
        from core.style_presets import is_tech_explainer_style
        if not script or not is_tech_explainer_style(self.kwargs.get("style", "")):
            return script
        from core.tech_explainer_pipeline import normalize_tech_explainer_script
        return normalize_tech_explainer_script(script)

    def _normalize_script_if_elderly(self, script):
        from core.style_presets import is_elderly_daily_style
        if not script or not is_elderly_daily_style(self.kwargs.get("style", "")):
            return script
        from core.elderly_daily_pipeline import strengthen_elderly_daily_script
        return strengthen_elderly_daily_script(script)

    def _normalize_script_for_style(self, script):
        script = self._normalize_script_if_tech(script)
        return self._normalize_script_if_elderly(script)

    def run(self):
        try:
            if self.task_type == "generate_script":
                self._generate_script()
            elif self.task_type == "generate_images":
                self._generate_images()
            elif self.task_type == "generate_audio":
                self._generate_audio()
            elif self.task_type == "compose_video":
                self._compose_video()
            elif self.task_type == "full_pipeline":
                self._full_pipeline()
            elif self.task_type == "regenerate_scene_image":
                self._regenerate_scene_image()
            elif self.task_type == "regenerate_scene_audio":
                self._regenerate_scene_audio()
            elif self.task_type == "regenerate_scene_video":
                self._regenerate_scene_video()
            elif self.task_type == "rewrite_scene_script":
                self._rewrite_scene_script()
            else:
                raise ValueError(f"未知任务类型: {self.task_type}")
        except TaskCancelled as e:
            self.finished.emit(False, str(e))
        except Exception as e:
            self.finished.emit(False, str(e))

    def _prog(self, *args):
        if len(args) == 3:
            self.progress.emit(args[0], args[1], args[2])
        elif len(args) == 1:
            self.progress.emit(0, 0, args[0])

    def _parse_storyboard_for_scene(self, scene_index: int):
        script = self.kwargs["script"]
        parser = StoryboardParser()
        storyboard = parser.parse(script)
        if scene_index < 0 or scene_index >= len(storyboard.scenes):
            raise ValueError("无效的场景索引")
        return script, storyboard, storyboard.scenes[scene_index]

    def _regenerate_scene_image(self):
        scene_index = self.kwargs["scene_index"]
        script, storyboard, scene = self._parse_storyboard_for_scene(scene_index)
        self._check_cancel()
        out_dir = os.path.join(get_output_dir(), "images")
        from core.scene_regenerate import clear_scene_images, clear_scene_media_keys
        clear_scene_images(out_dir, scene.scene_number)
        if scene_index < len(script.get("scenes", [])):
            clear_scene_media_keys(script["scenes"][scene_index], ("image_path",))
        scene.image_path = None
        portrait_registry = {}
        image_gen = ImageGenerator()
        if image_gen.config.get("character_consistency", True):
            portrait_dir = os.path.join(out_dir, "character_portraits")
            portrait_registry = image_gen.ensure_character_portraits(
                script.get("characters", []), portrait_dir, on_progress=self._prog
            )
        self._check_cancel()
        image_gen.generate_scene_image(
            scene, out_dir, on_progress=self._prog,
            script_characters=script.get("characters", []),
            portrait_registry=portrait_registry,
        )
        from core.scene_paths import sync_storyboard_paths_to_script
        sync_storyboard_paths_to_script(storyboard, script)
        self.finished.emit(True, f"场景 {scene.scene_number} 图片已重新生成")

    def _regenerate_scene_audio(self):
        scene_index = self.kwargs["scene_index"]
        script, storyboard, scene = self._parse_storyboard_for_scene(scene_index)
        self._check_cancel()
        out_dir = os.path.join(get_output_dir(), "audio")
        from core.scene_regenerate import clear_scene_audio, clear_scene_media_keys
        clear_scene_audio(out_dir, scene.scene_number)
        if scene_index < len(script.get("scenes", [])):
            clear_scene_media_keys(script["scenes"][scene_index], ("audio_path",))
        scene.audio_path = None
        vg = VoiceGenerator()
        vg.seed_voices_from_characters(script.get("characters", []))
        scene._force_regen_audio = True
        vg.generate_scene_audio(scene, out_dir, on_progress=self._prog)
        from core.scene_paths import sync_storyboard_paths_to_script
        sync_storyboard_paths_to_script(storyboard, script)
        self.finished.emit(True, f"场景 {scene.scene_number} 配音已重新生成")

    def _regenerate_scene_video(self):
        scene_index = self.kwargs["scene_index"]
        script, storyboard, scene = self._parse_storyboard_for_scene(scene_index)
        self._check_cancel()
        if not scene.image_path or not os.path.isfile(scene.image_path):
            ip = script.get("scenes", [{}])[scene_index].get("image_path", "")
            if ip and os.path.isfile(ip):
                scene.image_path = ip
            else:
                raise ValueError("请先生成本镜图片，再生成动效")
        out_dir = os.path.join(get_output_dir(), "videos")
        from core.scene_regenerate import clear_scene_videos
        clear_scene_videos(out_dir, scene.scene_number)
        scene.video_path = None
        prev_scene = storyboard.scenes[scene_index - 1] if scene_index > 0 else None
        next_scene = (
            storyboard.scenes[scene_index + 1]
            if scene_index + 1 < len(storyboard.scenes) else None
        )
        story_meta = {
            "title": storyboard.title or "",
            "theme": storyboard.theme or "",
            "genre": storyboard.genre or "",
        }
        VideoGenerator().generate_scene_video(
            scene, out_dir, on_progress=self._prog,
            prev_scene=prev_scene, next_scene=next_scene,
            story_meta=story_meta,
            script_characters=script.get("characters", []),
        )
        from core.scene_paths import sync_storyboard_paths_to_script
        sync_storyboard_paths_to_script(storyboard, script)
        self.finished.emit(True, f"场景 {scene.scene_number} 动效已重新生成")

    def _rewrite_scene_script(self):
        scene_index = self.kwargs["scene_index"]
        instruction = self.kwargs["instruction"]
        script = self.kwargs["script"]
        self._check_cancel()
        StoryGenerator().regenerate_scene(
            script, scene_index, instruction, on_progress=self._prog
        )
        scene_data = script.get("scenes", [{}])[scene_index]
        if isinstance(scene_data, dict):
            for key in ("image_path", "video_path", "audio_path"):
                scene_data.pop(key, None)
        from core.storyboard import strengthen_script_continuity
        strengthen_script_continuity(script)
        num = script.get("scenes", [{}])[scene_index].get("scene_number", scene_index + 1)
        self.finished.emit(True, f"场景 {num} 剧本已 AI 改写，请重新生成图片/配音")

    def _generate_script(self):
        self._check_cancel()
        user_input = self.kwargs["user_input"]
        style = self.kwargs.get("style", "short_drama")
        generator = StoryGenerator()
        script = generator.generate(
            user_input, style,
            on_progress=self._prog
        )
        
        # 自动生成定妆照
        characters = script.get("characters", [])
        if characters:
            self._prog("正在生成角色定妆照...")
            from core.image_generator import ImageGenerator
            from config import get_output_dir
            output_dir = os.path.join(get_output_dir(), "images")
            portrait_dir = os.path.join(output_dir, "character_portraits")
            
            image_gen = ImageGenerator(self._task_config())
            try:
                registry = image_gen.ensure_character_portraits(
                    characters, portrait_dir,
                    on_progress=self._prog
                )
                # 将定妆照路径写入剧本
                for ch in characters:
                    name = ch.get("name", "")
                    if name in registry:
                        ch["portrait_path"] = registry[name]
                        if not (ch.get("reference_image") or "").strip():
                            ch["reference_image"] = registry[name]
                self._prog(f"定妆照生成完成，共 {len(registry)} 个角色")
            except Exception as e:
                self._prog(f"定妆照生成失败（不影响剧本）: {e}")
        
        self.kwargs["script"] = script
        self.script_ready.emit(script)
        self.finished.emit(True, "剧本生成完成！")

    def _generate_images(self):
        self._check_cancel()
        script = self._normalize_script_for_style(self.kwargs["script"])
        self.kwargs["script"] = script
        output_dir = self.kwargs["output_dir"]
        parser = StoryboardParser()
        storyboard = parser.parse(script)
        config = self._task_config()
        image_gen = ImageGenerator(config)
        image_gen.generate_all_images(
            storyboard.scenes, output_dir,
            on_progress=self._prog,
            script_characters=script.get("characters", []),
        )
        from core.motion_utils import effective_video_mode
        if effective_video_mode(config) == "animated":
            video_output = os.path.join(os.path.dirname(output_dir), "videos")
            video_gen = VideoGenerator(config)
            story_meta = {
                "title": storyboard.title or "",
                "theme": storyboard.theme or "",
                "genre": storyboard.genre or "",
            }
            video_gen.generate_all_videos(
                storyboard.scenes, video_output,
                on_progress=self._prog,
                story_meta=story_meta,
                script_characters=script.get("characters", []),
            )
            for scene, s in zip(storyboard.scenes, self.kwargs["script"].get("scenes", [])):
                vp = getattr(scene, "video_path", None)
                if vp:
                    s["video_path"] = vp
        from core.scene_paths import sync_storyboard_paths_to_script
        sync_storyboard_paths_to_script(storyboard, script)
        self.finished.emit(
            True,
            "图片生成完成！"
            + ("（含动态分镜，角色会动）" if effective_video_mode(config) == "animated" else ""),
        )

    def _generate_audio(self):
        script = self._normalize_script_for_style(self.kwargs["script"])
        self.kwargs["script"] = script
        output_dir = self.kwargs["output_dir"]
        parser = StoryboardParser()
        storyboard = parser.parse(script)
        voice_gen = VoiceGenerator(self._task_config())
        voice_gen.generate_all_audio(
            storyboard.scenes, output_dir,
            on_progress=self._prog,
            script_characters=script.get("characters", []),
        )
        from core.scene_paths import sync_storyboard_paths_to_script
        sync_storyboard_paths_to_script(storyboard, script)
        self.finished.emit(True, "音频生成完成！")

    def _compose_video(self):
        script = self._normalize_script_for_style(self.kwargs["script"])
        self.kwargs["script"] = script
        output_path = self.kwargs["output_path"]
        parser = StoryboardParser()
        storyboard = parser.parse(script)
        for scene, s in zip(storyboard.scenes, script.get("scenes", [])):
            vp = s.get("video_path")
            if vp and os.path.exists(vp):
                scene.video_path = vp
            ap = s.get("audio_path")
            if ap and os.path.exists(ap):
                scene.audio_path = ap
            ip = s.get("image_path")
            if ip and os.path.exists(ip):
                scene.image_path = ip
        from core.scene_paths import resolve_scene_media_from_disk
        resolve_scene_media_from_disk(storyboard.scenes, get_output_dir())
        out_base = os.path.dirname(output_path) or get_output_dir()
        from core.motion_utils import ensure_motion_clips_for_storyboard
        ensure_motion_clips_for_storyboard(
            storyboard, script, out_base,
            on_progress=self._prog,
            config=self._task_config(),
        )
        for scene, s in zip(storyboard.scenes, script.get("scenes", [])):
            vp = getattr(scene, "video_path", None)
            if vp:
                s["video_path"] = vp
        composer = VideoComposer(self._task_config())
        composer.compose(
            storyboard.scenes, output_path,
            on_progress=self._prog
        )
        from core.scene_paths import sync_storyboard_paths_to_script
        sync_storyboard_paths_to_script(storyboard, script)
        self.output_video_path = output_path
        self.finished.emit(True, "视频合成完成！\n" + output_path)

    def _full_pipeline(self):
        from core.motion_utils import effective_video_mode
        from core.pipeline_resume import analyze_pipeline
        from core.scene_paths import resolve_scene_media_from_disk

        output_dir = self.kwargs["output_dir"]
        os.makedirs(output_dir, exist_ok=True)
        config = self._task_config()
        resume = bool(self.kwargs.get("resume"))

        if resume:
            script = self.kwargs.get("script")
            if not script or not script.get("scenes"):
                raise ValueError("续跑需要已有剧本与分镜，请先生成或加载剧本。")
            status = analyze_pipeline(script, output_dir, config)
            self._prog(
                f"续跑：{status.next_step_label()}（"
                + "，".join(status.summary_lines()) + "）"
            )
        else:
            user_input = self.kwargs["user_input"]
            style = self.kwargs.get("style", "short_drama")
            self._prog("正在生成剧本...")
            generator = StoryGenerator()
            script = generator.generate(
                user_input, style,
                on_progress=self._prog
            )
            sync = self.kwargs.get("script_sync")
            self.script_ready.emit(script)
            if sync and sync.get("wait_for_refs"):
                sync["script"] = script
                evt = sync.get("event")
                if evt:
                    evt.clear()
                    if not evt.wait(timeout=600):
                        raise RuntimeError("等待角色参考图超时，请重新一键生成。")
                if sync.get("script"):
                    script = sync["script"]
                self._check_cancel()

        script = self._normalize_script_for_style(script)
        self.kwargs["script"] = script

        characters = script.get("characters", [])
        if characters:
            self._check_cancel()
            self._prog("正在生成角色定妆照...")
            image_output = os.path.join(output_dir, "images")
            portrait_dir = os.path.join(image_output, "character_portraits")
            image_gen = ImageGenerator(config)
            try:
                registry = image_gen.ensure_character_portraits(
                    characters, portrait_dir, on_progress=self._prog
                )
                for ch in characters:
                    if not isinstance(ch, dict):
                        continue
                    name = (ch.get("name") or "").strip()
                    if name in registry:
                        ch["portrait_path"] = registry[name]
                        if not (ch.get("reference_image") or "").strip():
                            ch["reference_image"] = registry[name]
                self._prog(f"定妆照生成完成，共 {len(registry)} 个角色")
            except Exception as e:
                self._prog(f"定妆照生成失败（继续生成分镜图）: {e}")

        parser = StoryboardParser()
        storyboard = parser.parse(script)
        resolve_scene_media_from_disk(storyboard.scenes, output_dir)

        self._check_cancel()
        self._prog("正在生成图片...")
        image_output = os.path.join(output_dir, "images")
        image_gen = ImageGenerator(config)
        image_gen.generate_all_images(
            storyboard.scenes, image_output,
            on_progress=self._prog,
            script_characters=script.get("characters", []),
        )

        if effective_video_mode(config) == "animated":
            self._prog("正在生成动态视频片段（角色动作）...")
            video_output_dir = os.path.join(output_dir, "videos")
            video_gen = VideoGenerator(config)
            story_meta = {
                "title": storyboard.title or "",
                "theme": storyboard.theme or "",
                "genre": storyboard.genre or "",
            }
            video_gen.generate_all_videos(
                storyboard.scenes, video_output_dir,
                on_progress=self._prog,
                story_meta=story_meta,
                script_characters=script.get("characters", []),
            )
            for scene, s in zip(storyboard.scenes, script.get("scenes", [])):
                vp = getattr(scene, "video_path", None)
                if vp:
                    s["video_path"] = vp
        from core.scene_paths import sync_storyboard_paths_to_script
        sync_storyboard_paths_to_script(storyboard, script)

        self._check_cancel()
        self._prog("正在生成配音...")
        audio_output = os.path.join(output_dir, "audio")
        voice_gen = VoiceGenerator(config)
        voice_gen.generate_all_audio(
            storyboard.scenes, audio_output,
            on_progress=self._prog,
            script_characters=script.get("characters", []),
        )
        sync_storyboard_paths_to_script(storyboard, script)

        if effective_video_mode(config) == "animated":
            for scene, s in zip(storyboard.scenes, script.get("scenes", [])):
                vp = s.get("video_path")
                if vp and os.path.exists(vp):
                    scene.video_path = vp

        self._check_cancel()
        self._prog("正在合成视频...")
        timestamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
        rand_suffix = uuid.uuid4().hex[:6]
        video_output = os.path.join(
            output_dir, f"short_drama_{timestamp}_{rand_suffix}.mp4"
        )
        composer = VideoComposer(config)
        self._check_cancel()
        composer.compose(
            storyboard.scenes, video_output,
            on_progress=self._prog
        )

        self.output_video_path = video_output
        prefix = "续跑" if resume else "全部"
        self.finished.emit(True, f"{prefix}完成！视频已保存到:\n" + video_output)


# ===================== Main Window =====================

class MainWindow(QMainWindow):
    """AI短剧生成器主窗口"""

    def __init__(self):
        super().__init__()
        self.current_script = None
        self.worker = None
        self.thread = None
        self._script_sync = None
        self._cancel_event = None
        self._current_task_type = ""
        self.init_ui()
        self.load_settings()
        self._run_startup_checks()
        self._on_style_changed(self.style_combo.currentText())

    def init_ui(self):
        self.setWindowTitle("AI短剧生成器")
        self.setMinimumSize(960, 640)
        self.resize(1280, 900)
        
        # 设置窗口样式（避免 Windows 下 QGroupBox/滚动区白底）
        self.setStyleSheet("""
            QMainWindow, QWidget#centralRoot, QWidget#scrollContent {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #1a1a2e, stop:1 #16213e);
            }
            QWidget {
                color: #e6e6e6;
            }
            QGroupBox {
                background-color: #1e2038;
                border: 1px solid #3a3a5c;
                border-radius: 8px;
                margin-top: 14px;
                padding: 20px 10px 10px 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                color: #a8b2d1;
                font-weight: bold;
                padding: 4px 10px;
                background-color: #1e2038;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #4a69bd, stop:1 #3a59ad);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 14px;
                font-weight: bold;
                min-height: 32px;
            }
            QPushButton#btnSecondary {
                background: #3a3a5c;
                color: #e6e6e6;
                font-weight: normal;
            }
            QPushButton#btnSecondary:hover {
                background: #4a4a6a;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #5a79cd, stop:1 #4a69bd);
            }
            QPushButton:pressed {
                background: #3a59ad;
            }
            QPushButton:disabled {
                background: #3a3a5c;
                color: #666;
            }
            QTextEdit {
                background: #252545;
                border: 1px solid #3a3a5c;
                border-radius: 6px;
                color: #e6e6e6;
                padding: 10px;
            }
            QTextEdit::placeholder-text {
                color: #666;
            }
            QListWidget {
                background: #252545;
                border: 1px solid #3a3a5c;
                border-radius: 6px;
                color: #e6e6e6;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #3a3a5c;
            }
            QListWidget::item:hover {
                background: #3a3a5c;
            }
            QListWidget::item:selected {
                background: #4a69bd;
            }
            QComboBox {
                background: #252545;
                border: 1px solid #3a3a5c;
                border-radius: 6px;
                color: #e6e6e6;
                padding: 5px;
                min-width: 120px;
            }
            QComboBox::drop-down {
                border-left: 1px solid #3a3a5c;
                border-radius: 0 6px 6px 0;
            }
            QComboBox QAbstractItemView {
                background: #252545;
                border: 1px solid #3a3a5c;
                selection-background-color: #4a69bd;
            }
            QProgressBar {
                background: #252545;
                border: 1px solid #3a3a5c;
                border-radius: 6px;
                text-align: center;
                color: #8892b0;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #4a69bd, stop:1 #6a89ed);
                border-radius: 4px;
            }
            QLabel {
                color: #8892b0;
            }
            QMenuBar {
                background: #1a1a2e;
                color: #8892b0;
            }
            QMenuBar::item {
                padding: 8px 16px;
            }
            QMenuBar::item:hover {
                background: #3a3a5c;
            }
            QMenu {
                background: #252545;
                border: 1px solid #3a3a5c;
            }
            QMenu::item {
                padding: 8px 24px;
                color: #e6e6e6;
            }
            QMenu::item:hover {
                background: #4a69bd;
            }
            QScrollArea {
                background-color: #252545;
                border: 1px solid #3a3a5c;
                border-radius: 6px;
            }
            QScrollArea > QWidget > QWidget {
                background-color: #252545;
            }
            QSplitter::handle {
                background: #3a3a5c;
                height: 4px;
            }
            QLineEdit {
                background: #252545;
                color: #e6e6e6;
                border: 1px solid #3a3a5c;
                border-radius: 4px;
                padding: 6px;
            }
        """)

        # 全局：主内容可纵向滚动，底部进度条固定可见
        central = QWidget()
        central.setObjectName("centralRoot")
        self.setCentralWidget(central)
        shell_layout = QVBoxLayout(central)
        shell_layout.setSpacing(0)
        shell_layout.setContentsMargins(0, 0, 0, 0)

        global_scroll = QScrollArea()
        global_scroll.setObjectName("globalScroll")
        global_scroll.setWidgetResizable(True)
        global_scroll.setFrameShape(QFrame.NoFrame)
        global_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        global_scroll.setStyleSheet(
            "QScrollArea#globalScroll { background: transparent; border: none; }"
        )

        scroll_content = QWidget()
        scroll_content.setObjectName("scrollContent")
        main_layout = QVBoxLayout(scroll_content)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 16, 20, 20)

        global_scroll.setWidget(scroll_content)
        shell_layout.addWidget(global_scroll, 1)

        # 标题栏
        title_layout = QHBoxLayout()
        title_label = QLabel("🎬 AI短剧生成器")
        title_label.setFont(QFont("Microsoft YaHei", 20, QFont.Bold))
        title_label.setStyleSheet("color: #64ffda;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        subtitle_label = QLabel("动漫短片 · 图生视频+配音 · 无需本地 GPU")
        subtitle_label.setStyleSheet("color: #8892b0; font-size: 12px;")
        subtitle_label.setMaximumWidth(360)
        title_layout.addWidget(subtitle_label)
        main_layout.addLayout(title_layout)

        # 输入区域
        input_group = QGroupBox("故事主题")
        input_layout = QVBoxLayout(input_group)

        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText(
            "【银发日常】例：年轻人问鸡柳是啥，大爷大妈已读乱回；小院包饺子唠嗑\n"
            "【AI科普口播】例：DeepSeek 三个必会功能，程序员别再瞎用 ChatGPT\n"
            "【短剧喜剧】例：迪迦奥特曼送外卖总送错地址，被吐槽后倔强要证明自己…"
        )
        self.input_text.setMaximumHeight(100)
        input_layout.addWidget(self.input_text)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(QLabel("风格:"))
        self.style_combo = QComboBox()
        self.style_combo.addItems([
            "AI科普口播", "程序员口播",
            "银发日常", "老头们的快乐生活",
            "喜剧", "动漫短片", "短剧", "霸道总裁", "复仇", "悬疑",
            "古装", "都市", "科幻",
        ])
        self.style_combo.setCurrentText("AI科普口播")
        self.style_combo.currentTextChanged.connect(self._on_style_changed)
        btn_layout.addWidget(self.style_combo)
        btn_layout.addStretch()

        self.btn_script = QPushButton("生成剧本")
        self.btn_script.clicked.connect(self.generate_script)
        btn_layout.addWidget(self.btn_script)

        self.btn_character_refs = QPushButton("管理参考图")
        self.btn_character_refs.setToolTip("在大窗口中编辑各角色参考图（主界面下方也可直接上传）")
        self.btn_character_refs.clicked.connect(self.open_character_refs)
        btn_layout.addWidget(self.btn_character_refs)

        self.btn_full = QPushButton("一键生成视频")
        self.btn_full.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #00b894, stop:1 #00a884);
                color: white;
                font-weight: bold;
                padding: 10px 24px;
                border-radius: 8px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #00c8a4, stop:1 #00b894);
            }
            QPushButton:pressed {
                background: #00a884;
            }
        """)
        self.btn_full.clicked.connect(self.full_pipeline)
        btn_layout.addWidget(self.btn_full)

        self.btn_resume = QPushButton("续跑生成")
        self.btn_resume.setObjectName("btnSecondary")
        self.btn_resume.setToolTip(
            "在已有剧本基础上，跳过已完成的分镜图/动效/配音，继续生成并合成成片"
        )
        self.btn_resume.clicked.connect(self.resume_pipeline)
        btn_layout.addWidget(self.btn_resume)

        self.btn_cancel = QPushButton("取消任务")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background: #c0392b;
                color: white;
                font-weight: bold;
                padding: 10px 16px;
                border-radius: 8px;
            }
            QPushButton:hover { background: #e74c3c; }
        """)
        self.btn_cancel.clicked.connect(self.cancel_current_task)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_open_folder = QPushButton("打开视频文件夹")
        self.btn_open_folder.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #f39c12, stop:1 #e67e22);
                color: white;
                font-weight: bold;
                padding: 10px 24px;
                border-radius: 8px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #f1c40f, stop:1 #f39c12);
            }
            QPushButton:pressed {
                background: #e67e22;
            }
        """)
        self.btn_open_folder.clicked.connect(self.open_output_folder)
        btn_layout.addWidget(self.btn_open_folder)

        input_layout.addLayout(btn_layout)
        main_layout.addWidget(input_group)

        # 工作区：纯垂直/水平布局（不用 QSplitter，避免在滚动区内挤压裁切按钮）
        from ui.character_refs_panel import CharacterRefsPanel, COMPACT_CARD_HEIGHT

        refs_group = QGroupBox("角色参考图（人物A → 图片A，人物B → 图片B）")
        refs_group.setAutoFillBackground(True)
        refs_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        refs_layout = QVBoxLayout(refs_group)
        refs_layout.setContentsMargins(8, 4, 8, 8)
        refs_layout.setSpacing(6)
        self.character_refs_panel = CharacterRefsPanel(self, large_cards=False)
        self.character_refs_panel.setEnabled(False)
        refs_layout.addWidget(self.character_refs_panel)
        main_layout.addWidget(refs_group, 0)

        story_row = QWidget()
        story_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        story_row_layout = QHBoxLayout(story_row)
        story_row_layout.setContentsMargins(0, 0, 0, 0)
        story_row_layout.setSpacing(12)

        list_h = 280
        btn_h = 40

        left_panel = QGroupBox("分镜场景")
        left_panel.setAutoFillBackground(True)
        left_panel.setMinimumWidth(300)
        left_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 4, 8, 8)
        left_layout.setSpacing(10)

        self.scene_list = QListWidget()
        self.scene_list.setFixedHeight(list_h)
        self.scene_list.itemClicked.connect(self.on_scene_selected)
        self.scene_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        left_layout.addWidget(self.scene_list)

        scene_btn_layout = QHBoxLayout()
        scene_btn_layout.setSpacing(8)
        self.btn_images = QPushButton("生成图片+动效")
        self.btn_images.clicked.connect(self.generate_images)
        self.btn_audio = QPushButton("生成配音")
        self.btn_audio.clicked.connect(self.generate_audio)
        for b in (self.btn_images, self.btn_audio):
            b.setFixedHeight(btn_h)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            scene_btn_layout.addWidget(b, 1)
        left_layout.addLayout(scene_btn_layout)
        story_row_layout.addWidget(left_panel, 2)

        right_panel = QGroupBox("场景详情")
        right_panel.setAutoFillBackground(True)
        right_panel.setMinimumWidth(320)
        right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 4, 8, 8)
        right_layout.setSpacing(10)

        # 场景图片预览
        self.scene_image_label = QLabel()
        self.scene_image_label.setFixedHeight(200)
        self.scene_image_label.setAlignment(Qt.AlignCenter)
        self.scene_image_label.setStyleSheet("""
            QLabel {
                background: #1a1a2e;
                border: 1px solid #3a3a5c;
                border-radius: 6px;
            }
        """)
        self.scene_image_label.setText("选择场景后显示图片")
        right_layout.addWidget(self.scene_image_label)

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setFixedHeight(list_h - 210)
        self.detail_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        right_layout.addWidget(self.detail_text)

        scene_regen_layout = QHBoxLayout()
        scene_regen_layout.setSpacing(8)
        self.btn_regen_image = QPushButton("重生本镜图")
        self.btn_regen_image.setObjectName("btnSecondary")
        self.btn_regen_image.setToolTip("仅重新生成当前选中分镜的图片")
        self.btn_regen_image.clicked.connect(self.regenerate_scene_image)
        self.btn_regen_audio = QPushButton("重生本镜配音")
        self.btn_regen_audio.setObjectName("btnSecondary")
        self.btn_regen_audio.clicked.connect(self.regenerate_scene_audio)
        self.btn_regen_video = QPushButton("重生本镜动效")
        self.btn_regen_video.setObjectName("btnSecondary")
        self.btn_regen_video.clicked.connect(self.regenerate_scene_video)
        for b in (self.btn_regen_image, self.btn_regen_audio, self.btn_regen_video):
            b.setFixedHeight(36)
            b.setEnabled(False)
            scene_regen_layout.addWidget(b, 1)
        right_layout.addLayout(scene_regen_layout)

        scene_edit_layout = QHBoxLayout()
        scene_edit_layout.setSpacing(8)
        self.btn_edit_scene = QPushButton("编辑本镜")
        self.btn_edit_scene.setObjectName("btnSecondary")
        self.btn_edit_scene.clicked.connect(self.edit_current_scene)
        self.btn_rewrite_scene = QPushButton("AI改写本镜")
        self.btn_rewrite_scene.clicked.connect(self.rewrite_current_scene)
        for b in (self.btn_edit_scene, self.btn_rewrite_scene):
            b.setFixedHeight(36)
            b.setEnabled(False)
            scene_edit_layout.addWidget(b, 1)
        right_layout.addLayout(scene_edit_layout)

        action_btn_layout = QHBoxLayout()
        action_btn_layout.setSpacing(8)
        self.btn_video = QPushButton("合成视频")
        self.btn_video.clicked.connect(self.compose_video)
        self.btn_save = QPushButton("保存剧本")
        self.btn_save.setObjectName("btnSecondary")
        self.btn_save.clicked.connect(self.save_script)
        self.btn_load = QPushButton("加载剧本")
        self.btn_load.setObjectName("btnSecondary")
        self.btn_load.clicked.connect(self.load_script)
        for b in (self.btn_video, self.btn_save, self.btn_load):
            b.setFixedHeight(btn_h)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            action_btn_layout.addWidget(b, 1)
        right_layout.addLayout(action_btn_layout)
        story_row_layout.addWidget(right_panel, 3)

        # 分镜区总高度 = 列表/详情 + 按钮 + 分组框边距（写入 sizeHint 供全局滚动计算）
        story_row.setMinimumHeight(list_h + btn_h + 56)
        main_layout.addWidget(story_row, 0)

        # 历史记录面板
        from ui.history_panel import HistoryPanel
        history_group = QGroupBox("历史记录")
        history_group.setAutoFillBackground(True)
        history_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        history_layout = QVBoxLayout(history_group)
        history_layout.setContentsMargins(8, 4, 8, 8)
        history_layout.setSpacing(6)
        self.history_panel = HistoryPanel(self)
        self.history_panel.setFixedHeight(240)
        self.history_panel.load_requested.connect(self._on_history_load)
        history_layout.addWidget(self.history_panel)
        main_layout.addWidget(history_group, 0)

        scroll_content.setMinimumHeight(
            520 + COMPACT_CARD_HEIGHT + list_h + btn_h + 280
        )

        # 底部进度条：固定在窗口最下方，不随滚动消失
        progress_group = QGroupBox("进度")
        progress_group.setMinimumHeight(88)
        progress_layout = QVBoxLayout(progress_group)
        progress_layout.setContentsMargins(12, 8, 12, 8)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #8892b0;")
        self.status_label.setWordWrap(True)
        progress_layout.addWidget(self.status_label)

        footer = QWidget()
        footer.setObjectName("footerBar")
        footer.setStyleSheet(
            "QWidget#footerBar { background: #1a1a2e; border-top: 1px solid #3a3a5c; }"
        )
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(16, 8, 16, 12)
        footer_layout.addWidget(progress_group)
        shell_layout.addWidget(footer, 0)

        self._create_menu()
        self.set_buttons_enabled(False)

    def _create_menu(self):
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("文件")
        save_action = file_menu.addAction("保存剧本")
        save_action.triggered.connect(self.save_script)
        load_action = file_menu.addAction("加载剧本")
        load_action.triggered.connect(self.load_script)
        file_menu.addSeparator()
        export_srt_action = file_menu.addAction("导出字幕 (SRT)")
        export_srt_action.triggered.connect(self.export_srt)
        resume_action = file_menu.addAction("续跑一键生成…")
        resume_action.triggered.connect(self.resume_pipeline)
        file_menu.addSeparator()
        exit_action = file_menu.addAction("退出")
        exit_action.triggered.connect(self.close)

        settings_menu = menubar.addMenu("设置")
        api_action = settings_menu.addAction("API设置")
        api_action.triggered.connect(self.open_settings)
        char_ref_action = settings_menu.addAction("角色参考图…")
        char_ref_action.triggered.connect(self.open_character_refs)

        help_menu = menubar.addMenu("帮助")
        about_action = help_menu.addAction("关于")
        about_action.triggered.connect(self.show_about)

    def set_buttons_enabled(self, enabled):
        self.btn_images.setEnabled(enabled)
        self.btn_audio.setEnabled(enabled)
        self.btn_video.setEnabled(enabled)
        self.btn_save.setEnabled(enabled)
        if hasattr(self, "btn_resume"):
            self.btn_resume.setEnabled(enabled and not self._is_task_running())
        running = self._is_task_running()
        for b in (
            self.btn_regen_image, self.btn_regen_audio, self.btn_regen_video,
            self.btn_edit_scene, self.btn_rewrite_scene,
        ):
            b.setEnabled(enabled and not running)

    def _is_task_running(self) -> bool:
        return self.thread is not None and self.thread.isRunning()

    def _on_style_changed(self, style_name: str):
        from core.style_presets import (
            is_tech_explainer_style, tech_explainer_ui_hints,
            is_elderly_daily_style, elderly_daily_ui_hints,
        )
        if is_tech_explainer_style(style_name):
            self.status_label.setText(tech_explainer_ui_hints())
        elif is_elderly_daily_style(style_name):
            self.status_label.setText(elderly_daily_ui_hints())
        else:
            from core.startup_check import startup_status_line
            self.status_label.setText(startup_status_line())

    def _pipeline_progress_hint(self) -> str:
        """当前剧本在 output 目录的完成度摘要（供状态栏）。"""
        if not self.current_script:
            return ""
        try:
            from core.pipeline_resume import analyze_pipeline
            st = analyze_pipeline(self.current_script, get_output_dir())
            return (
                f" | 进度：图{st.images_done}/{st.total_scenes}"
                + (f" 动效{st.videos_done}/{st.total_scenes}" if st.need_videos else "")
                + f" 音{st.audio_done}/{st.total_scenes}"
                + f" →可续跑:{st.next_step_label()}"
            )
        except Exception:
            return ""

    def _run_startup_checks(self):
        from core.startup_check import run_startup_checks
        issues = run_startup_checks()
        if issues:
            QMessageBox.warning(
                self, "环境检查",
                "\n\n".join(issues),
            )

    def _set_task_running(self, running: bool):
        self.btn_cancel.setVisible(running)
        task_buttons = [
            self.btn_script, self.btn_full, self.btn_resume, self.btn_images,
            self.btn_audio, self.btn_video, self.btn_save, self.btn_load,
            self.btn_character_refs,
        ]
        for btn in task_buttons:
            btn.setEnabled(not running)
        if self.current_script:
            self.set_buttons_enabled(not running)
        else:
            self.set_buttons_enabled(False)

    def cancel_current_task(self):
        if self._cancel_event:
            self._cancel_event.set()
        self.status_label.setText("正在取消，请等待当前步骤结束…")

    def _get_selected_scene_index(self) -> int:
        return self.scene_list.currentRow()

    def edit_current_scene(self):
        if not self.current_script:
            QMessageBox.warning(self, "警告", "请先生成或加载剧本！")
            return
        idx = self._get_selected_scene_index()
        if idx < 0:
            QMessageBox.warning(self, "警告", "请先选择一个场景。")
            return
        scenes = self.current_script.get("scenes", [])
        if idx >= len(scenes):
            return
        from ui.scene_edit_dialog import SceneEditDialog
        dialog = SceneEditDialog(scenes[idx], self)
        if dialog.exec_():
            dialog.apply_to_scene()
            self.update_scene_list()
            self.scene_list.setCurrentRow(idx)
            item = self.scene_list.item(idx)
            if item:
                self.on_scene_selected(item)
            self.status_label.setText(
                "本镜已保存。图片/配音/动效路径已清空，请按需重新生成。"
            )

    def rewrite_current_scene(self):
        if not self.current_script:
            QMessageBox.warning(self, "警告", "请先生成或加载剧本！")
            return
        idx = self._get_selected_scene_index()
        if idx < 0:
            QMessageBox.warning(self, "警告", "请先选择一个场景。")
            return
        scenes = self.current_script.get("scenes", [])
        if idx >= len(scenes):
            return
        from ui.scene_rewrite_dialog import SceneRewriteDialog
        dialog = SceneRewriteDialog(scenes[idx], self)
        if not dialog.exec_():
            return
        instruction = dialog.get_instruction()
        if not instruction:
            QMessageBox.warning(self, "警告", "请输入修改指令。")
            return
        self.status_label.setText("正在 AI 改写本镜剧本…")
        self._start_worker(
            "rewrite_scene_script",
            script=self.current_script,
            scene_index=idx,
            instruction=instruction,
        )

    def export_srt(self):
        if not self.current_script:
            QMessageBox.warning(self, "警告", "没有可导出的剧本！")
            return
        from core.storyboard import StoryboardParser
        from core.subtitle import SubtitleGenerator
        storyboard = StoryboardParser().parse(self.current_script)
        if not storyboard.scenes:
            QMessageBox.warning(self, "警告", "剧本中没有分镜。")
            return
        default_name = (self.current_script.get("title") or "subtitles") + ".srt"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出字幕", default_name, "SRT字幕 (*.srt)"
        )
        if not file_path:
            return
        content = SubtitleGenerator.generate_srt_content(storyboard.scenes)
        if not content.strip():
            QMessageBox.warning(self, "警告", "没有可导出的字幕内容（旁白/对话为空）。")
            return
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        QMessageBox.information(self, "完成", f"字幕已导出:\n{file_path}")

    def regenerate_scene_image(self):
        self._start_scene_regen("regenerate_scene_image", "正在重生本镜图片…")

    def regenerate_scene_audio(self):
        self._start_scene_regen("regenerate_scene_audio", "正在重生本镜配音…")

    def regenerate_scene_video(self):
        self._start_scene_regen("regenerate_scene_video", "正在重生本镜动效…")

    def _start_scene_regen(self, task_type: str, status_msg: str):
        if not self.current_script:
            QMessageBox.warning(self, "警告", "请先生成或加载剧本！")
            return
        idx = self._get_selected_scene_index()
        if idx < 0:
            QMessageBox.warning(self, "警告", "请先在左侧列表中选择一个场景。")
            return
        if task_type == "regenerate_scene_image" and not self._apply_character_refs():
            return
        self.status_label.setText(status_msg)
        self._start_worker(
            task_type,
            script=self.current_script,
            scene_index=idx,
        )

    def generate_script(self):
        user_input = self.input_text.toPlainText().strip()
        if not user_input:
            QMessageBox.warning(self, "警告", "请输入故事主题！")
            return
        style = self.style_combo.currentText()
        self.status_label.setText("正在生成剧本...")
        self._start_worker(
            "generate_script",
            script_ready_callback=self.on_script_ready,
            user_input=user_input, style=style
        )

    def on_script_ready(self, script):
        self.current_script = script
        self._sync_character_refs_panel(merge=True)
        if hasattr(self, "character_refs_panel"):
            self.character_refs_panel.refresh_images_from_script(script)
        self.update_scene_list()
        self.set_buttons_enabled(True)

        # 检查是否已有定妆照
        characters = script.get("characters", [])
        has_portraits = any(ch.get("portrait_path") for ch in characters if isinstance(ch, dict))

        sync = self._script_sync
        if sync and sync.get("wait_for_refs"):
            if has_portraits:
                # 已有定妆照，直接继续
                self._apply_character_refs()
                sync["script"] = self.current_script
                sync["event"].set()
                return
            
            reply = QMessageBox.question(
                self,
                "上传角色参考图",
                "剧本已生成。\n\n请在下方「角色参考图」区域为每个角色分别上传照片"
                "（例如：林晓 → 她的照片，陆辰 → 他的照片）。\n\n"
                "上传完成后点「是」继续一键生成；暂不传图点「否」直接继续。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                if not self._apply_character_refs():
                    sync["script"] = script
                    sync["event"].set()
                    return
            else:
                self._apply_character_refs()
            sync["script"] = self.current_script
            sync["event"].set()
            return

        bgm_tip = script.get("bgm_suggestion", "")
        bgm_suffix = f"\n建议 BGM：{bgm_tip}" if bgm_tip else ""
        progress_hint = self._pipeline_progress_hint()
        from core.style_presets import is_tech_explainer_style, tech_explainer_ui_hints
        style = self.style_combo.currentText() if hasattr(self, "style_combo") else ""
        tech_hint = ("\n" + tech_explainer_ui_hints()) if is_tech_explainer_style(style) else ""
        if has_portraits:
            self.status_label.setText(
                "剧本已就绪，定妆照已生成。可「生成图片」或「续跑生成」。"
                + bgm_suffix + progress_hint + tech_hint
            )
        else:
            self.status_label.setText(
                "剧本已就绪。请上传角色参考图，再「生成图片」或「续跑生成」。"
                + bgm_suffix + progress_hint + tech_hint
            )

    def _sync_character_refs_panel(self, merge: bool = False):
        if hasattr(self, "character_refs_panel"):
            enabled = self.current_script is not None
            self.character_refs_panel.setEnabled(enabled)
            if enabled:
                if merge:
                    self.character_refs_panel.merge_from_script(self.current_script)
                else:
                    self.character_refs_panel.set_script(self.current_script)
            else:
                self.character_refs_panel.set_script(None)

    def _apply_character_refs(self) -> bool:
        """生成/保存前把面板中的多图绑定写入剧本。"""
        if not self.current_script or not hasattr(self, "character_refs_panel"):
            return True
        return self.character_refs_panel.apply_to_script(self.current_script)

    def _hydrate_script_media_from_disk(self):
        """从 output 目录补全剧本中的定妆照与分镜图路径（供 UI 回显）。"""
        if not self.current_script:
            return
        from core.scene_paths import resolve_scene_paths_in_script
        from core.character_portraits import sync_portraits_from_disk_to_script

        base = get_output_dir()
        sync_portraits_from_disk_to_script(self.current_script, base)
        resolve_scene_paths_in_script(self.current_script, base)

    def _refresh_media_ui_after_task(self):
        """生图/剧本任务完成后刷新定妆照卡片与分镜预览。"""
        if not self.current_script:
            return
        self._hydrate_script_media_from_disk()
        if hasattr(self, "character_refs_panel"):
            self.character_refs_panel.refresh_images_from_script(self.current_script)
        row = self._get_selected_scene_index()
        self.update_scene_list()
        if row < 0 and self.scene_list.count() > 0:
            row = 0
        if row >= 0:
            self.scene_list.setCurrentRow(row)
            item = self.scene_list.item(row)
            if item:
                self.on_scene_selected(item)

    def on_task_finished(self, success, message):
        self._script_sync = None
        task_type = getattr(self, "_current_task_type", "")
        media_tasks = (
            "generate_script",
            "generate_images",
            "full_pipeline",
            "regenerate_scene_image",
        )
        if success and getattr(self, "worker", None):
            w_script = self.worker.kwargs.get("script")
            if w_script and isinstance(w_script, dict):
                self.current_script = w_script
            if task_type in media_tasks:
                self._hydrate_script_media_from_disk()
                self._sync_character_refs_panel(merge=True)
        self._set_task_running(False)
        self._cancel_event = None
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100 if success else 0)
        if success:
            self.status_label.setText("完成！")
            self._auto_save_history()
            if task_type in media_tasks:
                self._refresh_media_ui_after_task()
            elif task_type.startswith("regenerate_scene") or task_type == "rewrite_scene_script":
                row = self._get_selected_scene_index()
                if row >= 0:
                    self.update_scene_list()
                    self.scene_list.setCurrentRow(row)
                    item = self.scene_list.item(row)
                    if item:
                        self.on_scene_selected(item)
            QMessageBox.information(self, "完成", message)
        else:
            self.status_label.setText(message)
            if "取消" not in message:
                QMessageBox.critical(self, "错误", message)

    def on_progress(self, current, total, message):
        if total > 0:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(current / total * 100))
        self.status_label.setText(message)

    def _start_worker(self, task_type, script_ready_callback=None, **kwargs):
        if self._is_task_running():
            QMessageBox.warning(self, "提示", "已有任务在进行中，请等待完成或点击「取消任务」。")
            return
        if "style" not in kwargs and hasattr(self, "style_combo"):
            kwargs["style"] = self.style_combo.currentText()
        self._current_task_type = task_type
        self._cancel_event = threading.Event()
        kwargs["cancel_event"] = self._cancel_event
        self._set_task_running(True)
        self.progress_bar.setRange(0, 0)
        self.worker = Worker(task_type, **kwargs)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_task_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        if script_ready_callback:
            self.worker.script_ready.connect(script_ready_callback)
        self.thread.started.connect(self.worker.run)
        self.thread.start()

    def generate_images(self):
        if not self.current_script:
            QMessageBox.warning(self, "警告", "请先生成剧本！")
            return
        if not self._apply_character_refs():
            return
        output_dir = os.path.join(get_output_dir(), "images")
        self.status_label.setText("正在生成图片...")
        self._start_worker(
            "generate_images",
            script=self.current_script,
            output_dir=output_dir
        )

    def generate_audio(self):
        if not self.current_script:
            QMessageBox.warning(self, "警告", "请先生成剧本！")
            return
        output_dir = os.path.join(get_output_dir(), "audio")
        self.status_label.setText("正在生成配音...")
        self._start_worker(
            "generate_audio",
            script=self.current_script,
            output_dir=output_dir
        )

    def compose_video(self):
        if not self.current_script:
            QMessageBox.warning(self, "警告", "请先生成剧本！")
            return
        from core.storyboard import StoryboardParser
        from core.scene_paths import (
            count_scenes_with_visual_media,
            resolve_scene_media_from_disk,
            scenes_missing_visual_media,
        )
        storyboard = StoryboardParser().parse(self.current_script)
        for scene, s in zip(storyboard.scenes, self.current_script.get("scenes", [])):
            if not isinstance(s, dict):
                continue
            for key in ("image_path", "video_path", "audio_path"):
                p = s.get(key)
                if p and os.path.isfile(p):
                    setattr(scene, key, p)
        resolve_scene_media_from_disk(storyboard.scenes, get_output_dir())
        if count_scenes_with_visual_media(storyboard.scenes) == 0:
            QMessageBox.warning(
                self,
                "缺少分镜画面",
                "未找到任何分镜图片或动态视频。\n\n"
                "DeepSeek 只负责生成剧本文字，不会画图。\n"
                "请先点击「生成图片+动效」（需 SiliconFlow Key），"
                "或「一键生成视频」，再合成。\n\n"
                "若已生图仍提示此项，请检查 output/images 下是否有 scene_XX_*.png。",
            )
            return
        missing = scenes_missing_visual_media(storyboard.scenes)
        if missing:
            QMessageBox.information(
                self,
                "提示",
                f"以下场景尚无图片/视频，合成时将显示文字占位："
                f" {', '.join(str(n) for n in missing)}\n"
                "建议先对这些场景执行「生成图片+动效」。",
            )
        output_path, _ = QFileDialog.getSaveFileName(
            self, "保存视频", get_output_dir(), "MP4视频 (*.mp4)"
        )
        if not output_path:
            return
        self.status_label.setText("正在合成视频...")
        self._start_worker(
            "compose_video",
            script=self.current_script,
            output_path=output_path
        )

    def full_pipeline(self):
        user_input = self.input_text.toPlainText().strip()
        if not user_input:
            QMessageBox.warning(self, "警告", "请输入故事主题！")
            return
        style = self.style_combo.currentText()
        output_dir = get_output_dir()
        self._script_sync = {
            "wait_for_refs": True,
            "event": threading.Event(),
            "script": None,
        }
        self.status_label.setText("开始一键生成...")
        self._start_worker(
            "full_pipeline",
            script_ready_callback=self.on_script_ready,
            user_input=user_input,
            style=style,
            output_dir=output_dir,
            script_sync=self._script_sync,
            resume=False,
        )

    def resume_pipeline(self):
        if not self.current_script:
            QMessageBox.warning(self, "警告", "请先生成或加载剧本，再续跑。")
            return
        if not self._apply_character_refs():
            return
        from core.pipeline_resume import analyze_pipeline
        status = analyze_pipeline(self.current_script, get_output_dir())
        if status.total_scenes == 0:
            QMessageBox.warning(self, "警告", "剧本中没有分镜，无法续跑。")
            return
        msg = "\n".join(status.summary_lines())
        reply = QMessageBox.question(
            self,
            "续跑一键生成",
            f"{msg}\n\n下一步将：{status.next_step_label()}\n"
            "已存在的分镜图/配音/动效会自动跳过。\n\n是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return
        self.status_label.setText("续跑生成中…")
        self._start_worker(
            "full_pipeline",
            script=self.current_script,
            output_dir=get_output_dir(),
            resume=True,
        )

    def update_scene_list(self):
        self.scene_list.clear()
        if not self.current_script:
            return
        for scene in self.current_script.get("scenes", []):
            num = scene.get("scene_number", 0)
            loc = scene.get("location", "")
            narration = scene.get("narration", "")[:30]
            item_text = "场景 {} - {} | {}".format(num, loc, narration)
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, scene)
            self.scene_list.addItem(item)

    def on_scene_selected(self, item):
        scene = item.data(Qt.UserRole)
        if not scene:
            return
        
        video_path = scene.get("video_path", "")
        image_path = scene.get("image_path", "")
        showed_preview = False
        if video_path and os.path.exists(video_path) and not (
            image_path and os.path.exists(image_path)
        ):
            self.scene_image_label.setText(
                f"本镜已有动效视频\n{os.path.basename(video_path)}\n（合成时将使用视频片段）"
            )
            showed_preview = True
        elif image_path and os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.scene_image_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                self.scene_image_label.setPixmap(scaled)
                showed_preview = True
            else:
                self.scene_image_label.setText("图片加载失败")
                showed_preview = True
        if not showed_preview:
            self.scene_image_label.setText("暂无图片（请先生成图片）")
        
        lines = []
        lines.append("=== 场景 {} ===".format(scene.get("scene_number", "")))
        lines.append("地点: {}".format(scene.get("location", "")))
        lines.append("时间: {}".format(scene.get("time", "")))
        lines.append("氛围: {}".format(scene.get("mood", "")))
        lines.append("镜头: {}".format(scene.get("camera_movement", "")))
        lines.append("时长: {}秒".format(scene.get("duration", "")))
        beat = scene.get("story_beat", "")
        if beat:
            lines.append("本镜作用: {}".format(beat))
        cont = scene.get("continuity_from_previous", "")
        if cont:
            lines.append("承上: {}".format(cont))
        leads = scene.get("leads_to_next", "")
        if leads:
            lines.append("启下: {}".format(leads))
        lines.append("")
        lines.append("画面描述: {}".format(scene.get("visual_description", "")))
        lines.append("")
        narration = scene.get("narration", "")
        if narration:
            lines.append("旁白: {}".format(narration))
            lines.append("")
        dialogues = scene.get("dialogues", [])
        if dialogues:
            lines.append("对话:")
            for d in dialogues:
                lines.append("  {}: {}".format(d.get("character", ""), d.get("line", "")))
        self.detail_text.setText("\n".join(lines))

    def save_script(self):
        if not self.current_script:
            QMessageBox.warning(self, "警告", "没有剧本可保存！")
            return
        if not self._apply_character_refs():
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存剧本", "", "JSON文件 (*.json)"
        )
        if not file_path:
            return
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.current_script, f, ensure_ascii=False, indent=2)
        QMessageBox.information(self, "完成", "剧本已保存到:\n" + file_path)

    def load_script(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "加载剧本", "", "JSON文件 (*.json)"
        )
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                self.current_script = json.load(f)
            from core.storyboard import strengthen_script_continuity
            strengthen_script_continuity(self.current_script)
            self._hydrate_script_media_from_disk()
            self._sync_character_refs_panel()
            self.update_scene_list()
            if self.scene_list.count() > 0:
                self.scene_list.setCurrentRow(0)
                item = self.scene_list.item(0)
                if item:
                    self.on_scene_selected(item)
            self.set_buttons_enabled(True)
            QMessageBox.information(self, "完成", "剧本已加载: " + file_path)
        except Exception as e:
            QMessageBox.critical(self, "错误", "加载失败: " + str(e))

    def open_character_refs(self):
        if not self.current_script:
            QMessageBox.warning(self, "提示", "请先生成或加载剧本，再为角色设置参考图。")
            return
        from ui.character_refs_dialog import CharacterRefsDialog
        dialog = CharacterRefsDialog(self.current_script, self)
        if dialog.exec_():
            self.character_refs_panel.load_from_script(self.current_script)
            self.status_label.setText("角色参考图已保存")

    def open_settings(self):
        from ui.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self)
        if dialog.exec_():
            self.load_settings()
            QMessageBox.information(
                self, "设置已保存",
                "当前 API 路由：\n" + self.status_label.text(),
            )

    def load_settings(self):
        from core.startup_check import startup_status_line
        self.status_label.setText(startup_status_line())

    def show_about(self):
        QMessageBox.about(
            self, "关于",
            "AI短剧生成器 v1.0\n\n"
            "基于 DeepSeek API + Edge TTS + MoviePy\n"
            "输入文字即可自动生成完整短剧视频\n\n"
            "使用前请先配置 DeepSeek API Key。"
        )

    def open_output_folder(self):
        """打开输出文件夹"""
        import subprocess
        import platform
        output_dir = get_output_dir()
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        try:
            if platform.system() == "Windows":
                os.startfile(output_dir)
            elif platform.system() == "Darwin":
                subprocess.run(["open", output_dir])
            else:
                subprocess.run(["xdg-open", output_dir])
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开文件夹:\n{e}")

    def _auto_save_history(self):
        """任务完成时自动保存历史记录。"""
        if not self.current_script:
            return
        task_type = getattr(self, "_current_task_type", "")
        video_path = ""
        if self.worker:
            video_path = getattr(self.worker, "output_video_path", "") or ""
        if not video_path and task_type in ("compose_video", "full_pipeline"):
            from core.history_manager import find_latest_final_video
            video_path = find_latest_final_video()
        style = self.style_combo.currentText() if hasattr(self, "style_combo") else ""
        user_input = self.input_text.toPlainText().strip() if hasattr(self, "input_text") else ""
        try:
            history_add_record(
                script=self.current_script,
                video_path=video_path,
                style=style,
                user_input=user_input,
            )
            if hasattr(self, "history_panel"):
                self.history_panel.refresh()
        except Exception as e:
            logger.warning(f"自动保存历史记录失败: {e}")

    def _on_history_load(self, script):
        """从历史记录加载剧本。"""
        self.current_script = script
        from core.storyboard import strengthen_script_continuity
        strengthen_script_continuity(self.current_script)
        self._hydrate_script_media_from_disk()
        self._sync_character_refs_panel()
        if hasattr(self, "character_refs_panel"):
            self.character_refs_panel.refresh_images_from_script(self.current_script)
        self.update_scene_list()
        if self.scene_list.count() > 0:
            self.scene_list.setCurrentRow(0)
            item = self.scene_list.item(0)
            if item:
                self.on_scene_selected(item)
        self.set_buttons_enabled(True)
        self.status_label.setText(
            "已从历史记录加载剧本。" + self._pipeline_progress_hint()
        )

    def closeEvent(self, event):
        self.save_settings()
        event.accept()

    def save_settings(self):
        pass