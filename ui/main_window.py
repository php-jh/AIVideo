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
    QScrollArea, QFrame,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QPalette, QColor

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


# ===================== Worker Thread =====================

class Worker(QObject):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(bool, str)
    script_ready = pyqtSignal(object)

    def __init__(self, task_type, **kwargs):
        super().__init__()
        self.task_type = task_type
        self.kwargs = kwargs

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
        except Exception as e:
            self.finished.emit(False, str(e))

    def _prog(self, *args):
        if len(args) == 3:
            self.progress.emit(args[0], args[1], args[2])
        elif len(args) == 1:
            self.progress.emit(0, 0, args[0])

    def _generate_script(self):
        user_input = self.kwargs["user_input"]
        style = self.kwargs.get("style", "short_drama")
        generator = StoryGenerator()
        script = generator.generate(
            user_input, style,
            on_progress=self._prog
        )
        self.script_ready.emit(script)
        self.finished.emit(True, "剧本生成完成！")

    def _generate_images(self):
        script = self.kwargs["script"]
        output_dir = self.kwargs["output_dir"]
        parser = StoryboardParser()
        storyboard = parser.parse(script)
        image_gen = ImageGenerator()
        image_gen.generate_all_images(
            storyboard.scenes, output_dir,
            on_progress=self._prog,
            script_characters=script.get("characters", []),
        )
        from config import load_config
        from core.motion_utils import effective_video_mode
        config = load_config()
        if effective_video_mode(config) == "animated":
            video_output = os.path.join(os.path.dirname(output_dir), "videos")
            video_gen = VideoGenerator()
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
        script = self.kwargs["script"]
        output_dir = self.kwargs["output_dir"]
        parser = StoryboardParser()
        storyboard = parser.parse(script)
        voice_gen = VoiceGenerator()
        voice_gen.generate_all_audio(
            storyboard.scenes, output_dir,
            on_progress=self._prog
        )
        from core.scene_paths import sync_storyboard_paths_to_script
        sync_storyboard_paths_to_script(storyboard, script)
        self.finished.emit(True, "音频生成完成！")

    def _compose_video(self):
        script = self.kwargs["script"]
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
            storyboard, script, out_base, on_progress=self._prog
        )
        for scene, s in zip(storyboard.scenes, script.get("scenes", [])):
            vp = getattr(scene, "video_path", None)
            if vp:
                s["video_path"] = vp
        composer = VideoComposer()
        composer.compose(
            storyboard.scenes, output_path,
            on_progress=self._prog
        )
        from core.scene_paths import sync_storyboard_paths_to_script
        sync_storyboard_paths_to_script(storyboard, script)
        self.finished.emit(True, "视频合成完成！")

    def _full_pipeline(self):
        user_input = self.kwargs["user_input"]
        style = self.kwargs.get("style", "short_drama")
        output_dir = self.kwargs["output_dir"]
        os.makedirs(output_dir, exist_ok=True)

        from config import load_config
        from core.motion_utils import effective_video_mode
        config = load_config()

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

        parser = StoryboardParser()
        storyboard = parser.parse(script)

        self._prog("正在生成图片...")
        image_output = os.path.join(output_dir, "images")
        image_gen = ImageGenerator()
        image_gen.generate_all_images(
            storyboard.scenes, image_output,
            on_progress=self._prog,
            script_characters=script.get("characters", []),
        )

        if effective_video_mode(config) == "animated":
            self._prog("正在生成动态视频片段（角色动作）...")
            video_output_dir = os.path.join(output_dir, "videos")
            video_gen = VideoGenerator()
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

        self._prog("正在生成配音...")
        audio_output = os.path.join(output_dir, "audio")
        voice_gen = VoiceGenerator()
        voice_gen.generate_all_audio(
            storyboard.scenes, audio_output,
            on_progress=self._prog
        )
        sync_storyboard_paths_to_script(storyboard, script)

        if effective_video_mode(config) == "animated":
            for scene, s in zip(storyboard.scenes, script.get("scenes", [])):
                vp = s.get("video_path")
                if vp and os.path.exists(vp):
                    scene.video_path = vp

        self._prog("正在合成视频...")
        timestamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
        rand_suffix = uuid.uuid4().hex[:6]
        video_output = os.path.join(
            output_dir, f"short_drama_{timestamp}_{rand_suffix}.mp4"
        )
        composer = VideoComposer()
        composer.compose(
            storyboard.scenes, video_output,
            on_progress=self._prog
        )

        self.finished.emit(True, "全部完成！视频已保存到:\n" + video_output)


# ===================== Main Window =====================

class MainWindow(QMainWindow):
    """AI短剧生成器主窗口"""

    def __init__(self):
        super().__init__()
        self.current_script = None
        self.worker = None
        self.thread = None
        self._script_sync = None
        self.init_ui()
        self.load_settings()
        from core.api_routing import describe_active_apis
        if "未填写" in describe_active_apis():
            self.status_label.setText(
                describe_active_apis() + " — 请在设置中填写 SiliconFlow Key"
            )

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
            "请输入故事主题或关键词（建议选「喜剧」风格）...\n"
            "例如：迪迦奥特曼来地球送外卖却总送错地址，被吐槽后倔强要证明自己…"
        )
        self.input_text.setMaximumHeight(100)
        input_layout.addWidget(self.input_text)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(QLabel("风格:"))
        self.style_combo = QComboBox()
        self.style_combo.addItems([
            "喜剧", "动漫短片", "短剧", "霸道总裁", "复仇", "悬疑",
            "古装", "都市", "科幻",
        ])
        self.style_combo.setCurrentText("喜剧")
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

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setFixedHeight(list_h)
        self.detail_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        right_layout.addWidget(self.detail_text)

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

    def generate_script(self):
        user_input = self.input_text.toPlainText().strip()
        if not user_input:
            QMessageBox.warning(self, "警告", "请输入故事主题！")
            return
        style = self.style_combo.currentText()
        self.status_label.setText("正在生成剧本...")
        self.progress_bar.setRange(0, 0)
        self._start_worker(
            "generate_script",
            script_ready_callback=self.on_script_ready,
            user_input=user_input, style=style
        )

    def on_script_ready(self, script):
        self.current_script = script
        self._sync_character_refs_panel(merge=True)
        self.update_scene_list()
        self.set_buttons_enabled(True)

        sync = self._script_sync
        if sync and sync.get("wait_for_refs"):
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

        self.status_label.setText(
            "剧本已就绪。请在下方为各角色上传参考图，再点「生成图片」。"
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

    def on_task_finished(self, success, message):
        self._script_sync = None
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        if success:
            self.status_label.setText("完成！")
            self._auto_save_history()
            QMessageBox.information(self, "完成", message)
            self._load_portraits_after_task()
        else:
            self.status_label.setText("错误: " + message)
            QMessageBox.critical(self, "错误", message)

    def _load_portraits_after_task(self):
        """图片生成完成后，将定妆照加载到角色参考图面板。"""
        task_type = getattr(self, "_current_task_type", "")
        if task_type not in ("generate_images", "full_pipeline"):
            return
        if not hasattr(self, "character_refs_panel"):
            return
        portrait_dir = os.path.join(get_output_dir(), "images", "character_portraits")
        matched = self.character_refs_panel.load_portraits_from_dir(portrait_dir)
        if matched > 0:
            logger.info(f"已从定妆照目录加载 {matched} 个角色头像")

    def on_progress(self, current, total, message):
        if total > 0:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(current / total * 100))
        self.status_label.setText(message)

    def _start_worker(self, task_type, script_ready_callback=None, **kwargs):
        self._current_task_type = task_type
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
        self.progress_bar.setRange(0, 0)
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
        self.progress_bar.setRange(0, 0)
        self._start_worker(
            "full_pipeline",
            script_ready_callback=self.on_script_ready,
            user_input=user_input,
            style=style,
            output_dir=output_dir,
            script_sync=self._script_sync,
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
            self._sync_character_refs_panel()
            self.update_scene_list()
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
        from core.api_routing import describe_active_apis
        self.status_label.setText(describe_active_apis())

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
        if task_type in ("compose_video", "full_pipeline"):
            out_dir = get_output_dir()
            vid_dir = os.path.join(out_dir, "videos")
            if os.path.isdir(vid_dir):
                vids = sorted(
                    [f for f in os.listdir(vid_dir) if f.endswith(".mp4")],
                    key=lambda f: os.path.getmtime(os.path.join(vid_dir, f)),
                    reverse=True,
                )
                if vids:
                    video_path = os.path.join(vid_dir, vids[0])
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
        self._sync_character_refs_panel()
        self.update_scene_list()
        self.set_buttons_enabled(True)
        self.status_label.setText("已从历史记录加载剧本")

    def closeEvent(self, event):
        self.save_settings()
        event.accept()

    def save_settings(self):
        pass