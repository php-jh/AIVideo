"""
AI短剧生成器 - 设置对话框
"""
import os
import json
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QPushButton,
    QDialogButtonBox, QTabWidget, QWidget, QSpinBox,
    QDoubleSpinBox, QMessageBox, QFileDialog, QCheckBox,
)
from PyQt5.QtCore import Qt

from config import load_config, save_config
from core.voice_generator import VoiceGenerator


class SettingsDialog(QDialog):
    """设置对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = load_config()
        self.voice_gen = VoiceGenerator()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("设置")
        self.setMinimumWidth(550)
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #1a1a2e, stop:1 #16213e);
            }
            QTabWidget::pane {
                background: transparent;
                border: 1px solid #3a3a5c;
                border-radius: 6px;
            }
            QTabWidget::tab-bar {
                alignment: center;
            }
            QTabBar::tab {
                background: #252545;
                color: #8892b0;
                padding: 8px 20px;
                border: 1px solid #3a3a5c;
                border-bottom: none;
                border-radius: 6px 6px 0 0;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #1a1a2e;
                color: #64ffda;
            }
            QLabel {
                color: #8892b0;
            }
            QLineEdit {
                background: #252545;
                border: 1px solid #3a3a5c;
                border-radius: 4px;
                color: #e6e6e6;
                padding: 6px;
            }
            QComboBox {
                background: #252545;
                border: 1px solid #3a3a5c;
                border-radius: 4px;
                color: #e6e6e6;
                padding: 6px;
            }
            QComboBox::drop-down {
                border-left: 1px solid #3a3a5c;
            }
            QComboBox QAbstractItemView {
                background: #252545;
                border: 1px solid #3a3a5c;
                selection-background-color: #4a69bd;
            }
            QSpinBox, QDoubleSpinBox {
                background: #252545;
                border: 1px solid #3a3a5c;
                border-radius: 4px;
                color: #e6e6e6;
                padding: 6px;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #4a69bd, stop:1 #3a59ad);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #5a79cd, stop:1 #4a69bd);
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Tab widget
        tabs = QTabWidget()

        # --- API设置 ---
        api_tab = QWidget()
        api_layout = QFormLayout(api_tab)
        api_layout.setSpacing(10)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setText(self.config.get("deepseek_api_key", ""))
        self.api_key_edit.setPlaceholderText("请输入DeepSeek API Key...")
        api_layout.addRow("DeepSeek API Key:", self.api_key_edit)

        self.base_url_edit = QLineEdit()
        self.base_url_edit.setText(
            self.config.get("deepseek_base_url", "https://api.deepseek.com")
        )
        api_layout.addRow("基础URL:", self.base_url_edit)

        self.model_combo = QComboBox()
        self.model_combo.addItems(["deepseek-chat", "deepseek-reasoner"])
        current_model = self.config.get("deepseek_model", "deepseek-chat")
        idx = self.model_combo.findText(current_model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        api_layout.addRow("模型:", self.model_combo)

        # 图片API设置
        self.image_api_combo = QComboBox()
        self.image_api_combo.addItems([
            "deepseek", "siliconflow", "zhipu", "pollinations", "dall-e", "none",
        ])
        current_image_api = self.config.get("image_api", "deepseek")
        idx = self.image_api_combo.findText(current_image_api)
        if idx >= 0:
            self.image_api_combo.setCurrentIndex(idx)
        api_layout.addRow("图片API:", self.image_api_combo)

        self.image_api_key_edit = QLineEdit()
        self.image_api_key_edit.setText(self.config.get("image_api_key", ""))
        self.image_api_key_edit.setPlaceholderText(
            "选 SiliconFlow 时填 SiliconFlow Key；选 DALL-E 时填 OpenAI Key"
        )
        api_layout.addRow("图片API Key:", self.image_api_key_edit)

        self.zhipu_api_key_edit = QLineEdit()
        self.zhipu_api_key_edit.setEchoMode(QLineEdit.Password)
        self.zhipu_api_key_edit.setText(self.config.get("zhipu_api_key", ""))
        self.zhipu_api_key_edit.setPlaceholderText(
            "智谱开放平台 API Key（GLM-Image 生图 + 清影视频共用）"
        )
        api_layout.addRow("智谱 API Key:", self.zhipu_api_key_edit)

        self.zhipu_image_model_edit = QLineEdit()
        self.zhipu_image_model_edit.setText(
            self.config.get("zhipu_image_model", "glm-image")
        )
        self.zhipu_image_model_edit.setPlaceholderText("glm-image")
        self.zhipu_image_model_edit.setToolTip(
            "智谱文生图模型，定妆照/分镜选 image_api=zhipu 时使用。\n"
            "文档: https://docs.bigmodel.cn/cn/guide/models/image-generation/glm-image"
        )
        api_layout.addRow("智谱生图模型:", self.zhipu_image_model_edit)

        self.zhipu_image_size_portrait_edit = QLineEdit()
        self.zhipu_image_size_portrait_edit.setText(
            self.config.get("zhipu_image_size_portrait", "1056x1568")
        )
        self.zhipu_image_size_portrait_edit.setPlaceholderText("1056x1568 竖版人像")
        api_layout.addRow("智谱定妆照尺寸:", self.zhipu_image_size_portrait_edit)

        self.zhipu_image_size_edit = QLineEdit()
        self.zhipu_image_size_edit.setText(
            self.config.get("zhipu_image_size", "1088x1472")
        )
        self.zhipu_image_size_edit.setPlaceholderText("1088x1472 竖屏分镜")
        api_layout.addRow("智谱分镜图尺寸:", self.zhipu_image_size_edit)

        self.pollinations_model_combo = QComboBox()
        self.pollinations_model_combo.addItems(["flux", "turbo"])
        self.pollinations_model_combo.setToolTip(
            "Pollinations 模型：flux 更自然细腻（推荐）；turbo 更快但易有 AI 感"
        )
        pm = self.config.get("pollinations_model", "flux")
        idx_pm = self.pollinations_model_combo.findText(pm)
        if idx_pm >= 0:
            self.pollinations_model_combo.setCurrentIndex(idx_pm)
        api_layout.addRow("Pollinations 模型:", self.pollinations_model_combo)

        self.siliconflow_image_model_edit = QLineEdit()
        self.siliconflow_image_model_edit.setText(
            self.config.get("siliconflow_image_model", "Kwai-Kolors/Kolors")
        )
        self.siliconflow_image_model_edit.setPlaceholderText("Kwai-Kolors/Kolors")
        self.siliconflow_image_model_edit.setToolTip(
            "SiliconFlow 文生图模型 ID，与控制台「模型广场」to-image 列表一致。\n"
            "若报错 Model disabled(30003)，请更换为当前上架的模型。\n"
            "接口说明见官方文档（images/generations）。"
        )
        api_layout.addRow("SiliconFlow 生图模型:", self.siliconflow_image_model_edit)

        self.siliconflow_image_size_edit = QLineEdit()
        self.siliconflow_image_size_edit.setText(
            self.config.get("siliconflow_image_size", "720x1280")
        )
        self.siliconflow_image_size_edit.setPlaceholderText("720x1280（竖屏）或 1024x1024")
        self.siliconflow_image_size_edit.setToolTip(
            "宽高格式 widthxheight，需与所选模型文档中的推荐分辨率一致。"
        )
        api_layout.addRow("SiliconFlow 生图尺寸:", self.siliconflow_image_size_edit)

        self.image_fit_mode_combo = QComboBox()
        self.image_fit_mode_combo.addItem("留边适配（推荐，减少裁切错位）", "letterbox")
        self.image_fit_mode_combo.addItem("裁切铺满（可能切头切脚）", "crop")
        ifm = self.config.get("image_fit_mode", "letterbox")
        idx_ifm = self.image_fit_mode_combo.findData(ifm)
        if idx_ifm >= 0:
            self.image_fit_mode_combo.setCurrentIndex(idx_ifm)
        api_layout.addRow("导出竖图适配:", self.image_fit_mode_combo)

        self.character_ref_image_mode_combo = QComboBox()
        self.character_ref_image_mode_combo.addItem(
            "参考图 + 分镜描述 AI 融合（推荐）", "blend"
        )
        self.character_ref_image_mode_combo.addItem(
            "直接使用参考图作分镜图（最快，场景不变）", "direct"
        )
        crim = self.config.get("character_ref_image_mode", "blend")
        idx_crim = self.character_ref_image_mode_combo.findData(crim)
        if idx_crim >= 0:
            self.character_ref_image_mode_combo.setCurrentIndex(idx_crim)
        self.character_ref_image_mode_combo.setToolTip(
            "需在菜单「角色参考图」中为角色上传照片；生图方式须为 SiliconFlow（blend 模式）。"
        )
        api_layout.addRow("角色参考图生图:", self.character_ref_image_mode_combo)

        self.character_consistency_combo = QComboBox()
        self.character_consistency_combo.addItem("开启（定妆照 + 分镜图生图锁脸，推荐）", True)
        self.character_consistency_combo.addItem("关闭", False)
        cc = self.config.get("character_consistency", True)
        idx_cc = self.character_consistency_combo.findData(cc)
        if idx_cc >= 0:
            self.character_consistency_combo.setCurrentIndex(idx_cc)
        self.character_consistency_combo.setToolTip(
            "开启后先为每个角色生成/复用一张定妆照，各分镜基于该图生图；需 SiliconFlow。"
        )
        api_layout.addRow("全片角色一致:", self.character_consistency_combo)

        self.character_img2img_strength_spin = QDoubleSpinBox()
        self.character_img2img_strength_spin.setRange(0.2, 0.7)
        self.character_img2img_strength_spin.setSingleStep(0.05)
        self.character_img2img_strength_spin.setValue(
            float(self.config.get("character_scene_img2img_strength", 0.4))
        )
        self.character_img2img_strength_spin.setToolTip(
            "越小越像同一人，越大场景变化越大。推荐 0.35~0.45。"
        )
        api_layout.addRow("分镜相对定妆照变化:", self.character_img2img_strength_spin)

        sf_doc = QLabel(
            '<a href="https://docs.siliconflow.cn/cn/userguide/introduction">产品简介</a> · '
            '<a href="https://docs.siliconflow.cn/cn/api-reference/images/images-generations">'
            "文生图 API（/v1/images/generations）</a> · "
            '<a href="https://docs.siliconflow.cn/llms.txt">文档索引 llms.txt</a>'
        )
        sf_doc.setOpenExternalLinks(True)
        sf_doc.setTextInteractionFlags(Qt.TextBrowserInteraction)
        sf_doc.setWordWrap(True)
        api_layout.addRow("SiliconFlow 文档:", sf_doc)

        self.sf_route_label = QLabel("")
        self.sf_route_label.setWordWrap(True)
        self.sf_route_label.setStyleSheet("color: #64ffda;")
        api_layout.addRow("实际将调用:", self.sf_route_label)

        self.image_api_key_edit.textChanged.connect(self._refresh_api_route_hint)
        self.image_api_combo.currentTextChanged.connect(self._refresh_api_route_hint)

        tabs.addTab(api_tab, "API设置")

        # --- 声音设置 ---
        voice_tab = QWidget()
        voice_layout = QFormLayout(voice_tab)
        voice_layout.setSpacing(10)

        self.narrator_combo = QComboBox()
        for voice_id, desc in self.voice_gen.VOICE_MAP.items():
            self.narrator_combo.addItem(f"{desc} ({voice_id})", voice_id)
        current_narrator = self.config.get("tts_voice_narrator", "zh-CN-YunxiNeural")
        idx = self.narrator_combo.findData(current_narrator)
        if idx >= 0:
            self.narrator_combo.setCurrentIndex(idx)
        voice_layout.addRow("旁白音色:", self.narrator_combo)

        self.male_combo = QComboBox()
        for voice_id, desc in self.voice_gen.VOICE_MAP.items():
            if "男" in desc or "male" in desc.lower() or "Yun" in voice_id:
                self.male_combo.addItem(f"{desc} ({voice_id})", voice_id)
        current_male = self.config.get("tts_voice_male", "zh-CN-YunxiNeural")
        idx = self.male_combo.findData(current_male)
        if idx >= 0:
            self.male_combo.setCurrentIndex(idx)
        voice_layout.addRow("男性角色音色:", self.male_combo)

        self.female_combo = QComboBox()
        for voice_id, desc in self.voice_gen.VOICE_MAP.items():
            if "女" in desc or "female" in desc.lower() or "Xiao" in voice_id:
                self.female_combo.addItem(f"{desc} ({voice_id})", voice_id)
        # 默认使用最温柔的女声（晓辰）
        current_female = self.config.get("tts_voice_female", "zh-CN-XiaochenNeural")
        idx = self.female_combo.findData(current_female)
        if idx >= 0:
            self.female_combo.setCurrentIndex(idx)
        self.female_combo.setToolTip("推荐晓辰或晓晓，声音更温柔")
        voice_layout.addRow("女性角色音色:", self.female_combo)

        self.bgm_enabled_check = QCheckBox("合成成片时叠加背景音乐")
        self.bgm_enabled_check.setChecked(bool(self.config.get("bgm_enabled", False)))
        voice_layout.addRow("", self.bgm_enabled_check)

        self.bgm_path_edit = QLineEdit()
        self.bgm_path_edit.setText(self.config.get("bgm_path", ""))
        self.bgm_path_edit.setPlaceholderText("选择 mp3/wav 等本地音乐文件")
        bgm_browse = QPushButton("浏览…")
        bgm_browse.clicked.connect(self._browse_bgm)
        bgm_row = QHBoxLayout()
        bgm_row.addWidget(self.bgm_path_edit)
        bgm_row.addWidget(bgm_browse)
        voice_layout.addRow("BGM 文件:", bgm_row)

        self.bgm_volume_spin = QDoubleSpinBox()
        self.bgm_volume_spin.setRange(0.05, 0.5)
        self.bgm_volume_spin.setSingleStep(0.05)
        self.bgm_volume_spin.setValue(float(self.config.get("bgm_volume", 0.18)))
        self.bgm_volume_spin.setToolTip("相对配音音量，越小 BGM 越弱（推荐 0.15~0.25）")
        voice_layout.addRow("BGM 音量:", self.bgm_volume_spin)

        tabs.addTab(voice_tab, "声音设置")

        # --- 视频设置 ---
        video_tab = QWidget()
        video_layout = QFormLayout(video_tab)
        video_layout.setSpacing(10)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(480, 3840)
        self.width_spin.setValue(self.config.get("video_width", 1080))
        video_layout.addRow("视频宽度:", self.width_spin)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(480, 3840)
        self.height_spin.setValue(self.config.get("video_height", 1920))
        video_layout.addRow("视频高度:", self.height_spin)

        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(12, 60)
        self.fps_spin.setValue(self.config.get("video_fps", 24))
        video_layout.addRow("帧率:", self.fps_spin)

        self.visual_style_combo = QComboBox()
        self.visual_style_combo.addItem("真人纪实（默认）", "live_action")
        self.visual_style_combo.addItem("动漫短片 2D（画风+剧本偏动画，对话推荐）", "anime_cartoon")
        self.visual_style_combo.setToolTip(
            "选「动漫短片 2D」：剧本会写举手/说话等动作；默认生成分镜动态视频（需 SiliconFlow Key）。"
            "说话=配音+字幕；图生视频尽量做口型与手势。无 Key 时回退本地轻量动效。"
        )
        vs = self.config.get("visual_style", "live_action")
        idx_vs = self.visual_style_combo.findData(vs)
        if idx_vs >= 0:
            self.visual_style_combo.setCurrentIndex(idx_vs)
        video_layout.addRow("成片画面风格:", self.visual_style_combo)

        self.scene_clip_fallback_combo = QComboBox()
        self.scene_clip_fallback_combo.addItem("自动（动漫→本地动效；真人→Ken Burns）", "auto")
        self.scene_clip_fallback_combo.addItem("无分镜视频时：始终本地动效 MP4", "local_motion")
        self.scene_clip_fallback_combo.addItem("无分镜视频时：始终静图 Ken Burns", "ken_burns")
        scf = self.config.get("scene_clip_fallback", "auto")
        idx_scf = self.scene_clip_fallback_combo.findData(scf)
        if idx_scf >= 0:
            self.scene_clip_fallback_combo.setCurrentIndex(idx_scf)
        video_layout.addRow("静图时的合成方式:", self.scene_clip_fallback_combo)

        self.video_mode_combo = QComboBox()
        self.video_mode_combo.addItem("关闭（仅用静图 + Ken Burns 合成）", "static")
        self.video_mode_combo.addItem("开启（生图后额外生成分镜动态视频）", "animated")
        self.video_mode_combo.setToolTip(
            "开启后为每镜生成动态短视频（角色动、说话表演）。动漫风格下会自动视为开启。"
        )
        vm = self.config.get("video_mode", "static")
        idx_vm = self.video_mode_combo.findData(vm)
        if idx_vm >= 0:
            self.video_mode_combo.setCurrentIndex(idx_vm)
        video_layout.addRow("分镜动态视频:", self.video_mode_combo)

        self.character_ref_video_first_frame_combo = QComboBox()
        self.character_ref_video_first_frame_combo.addItem(
            "用分镜图作图生视频首帧（推荐，场景更丰富）", "scene_keyframe"
        )
        self.character_ref_video_first_frame_combo.addItem(
            "直接用角色参考照作首帧（更像本人，背景变化小）", "reference"
        )
        crvf = self.config.get("character_ref_video_first_frame", "scene_keyframe")
        idx_crvf = self.character_ref_video_first_frame_combo.findData(crvf)
        if idx_crvf >= 0:
            self.character_ref_video_first_frame_combo.setCurrentIndex(idx_crvf)
        video_layout.addRow("图生视频首帧:", self.character_ref_video_first_frame_combo)

        self.video_animated_backend_combo = QComboBox()
        self.video_animated_backend_combo.addItem("本地 MoviePy 特效（无需排队）", "local")
        self.video_animated_backend_combo.addItem("SiliconFlow 图生视频（耗额度、较慢）", "siliconflow")
        self.video_animated_backend_combo.addItem("智谱清影图生视频（CogVideoX）", "zhipu")
        self.video_animated_backend_combo.setToolTip(
            "选 SiliconFlow 时请在 API 设置中填写 SiliconFlow 的「图片API Key」；\n"
            "选智谱清影时请填写「智谱 API Key」。"
        )
        vb = self.config.get("video_animated_backend", "local")
        idx_vb = self.video_animated_backend_combo.findData(vb)
        if idx_vb >= 0:
            self.video_animated_backend_combo.setCurrentIndex(idx_vb)
        video_layout.addRow("动态视频生成方式:", self.video_animated_backend_combo)

        self.siliconflow_video_model_edit = QLineEdit()
        self.siliconflow_video_model_edit.setText(
            self.config.get("siliconflow_video_model", "Wan-AI/Wan2.2-I2V-A14B")
        )
        self.siliconflow_video_model_edit.setPlaceholderText("Wan-AI/Wan2.2-I2V-A14B")
        video_layout.addRow("SiliconFlow 视频模型:", self.siliconflow_video_model_edit)

        self.zhipu_video_model_combo = QComboBox()
        self.zhipu_video_model_combo.addItems([
            "cogvideox-flash (免费推荐)",
            "cogvideox-3 (最高质量1元/次)",
            "cogvideox-2",
            "vidu2-image (1.25元/次4秒)",
            "viduq1-image",
        ])
        current_zhipu_model = self.config.get("zhipu_video_model", "cogvideox-flash")
        # 匹配模型名称（去掉括号部分）
        for i in range(self.zhipu_video_model_combo.count()):
            item_text = self.zhipu_video_model_combo.itemText(i)
            if item_text.startswith(current_zhipu_model):
                self.zhipu_video_model_combo.setCurrentIndex(i)
                break
        self.zhipu_video_model_combo.setToolTip(
            "cogvideox-flash: 免费，质量不错（推荐）\n"
            "cogvideox-3: 最高质量，1元/次\n"
            "vidu2-image: 1.25元/次，4秒时长"
        )
        video_layout.addRow("智谱清影视频模型:", self.zhipu_video_model_combo)

        self.transition_spin = QDoubleSpinBox()
        self.transition_spin.setRange(0.0, 2.0)
        self.transition_spin.setSingleStep(0.1)
        self.transition_spin.setValue(self.config.get("transition_duration", 0.5))
        video_layout.addRow("转场时长(秒):", self.transition_spin)

        self.ffmpeg_path_edit = QLineEdit()
        self.ffmpeg_path_edit.setText(self.config.get("ffmpeg_path", ""))
        self.ffmpeg_path_edit.setPlaceholderText(
            "留空则自动使用 imageio-ffmpeg 内置；或选择 ffmpeg.exe"
        )
        ffmpeg_browse = QPushButton("浏览…")
        ffmpeg_browse.clicked.connect(self._browse_ffmpeg)
        ffmpeg_row = QHBoxLayout()
        ffmpeg_row.addWidget(self.ffmpeg_path_edit)
        ffmpeg_row.addWidget(ffmpeg_browse)
        video_layout.addRow("FFmpeg 路径:", ffmpeg_row)

        from core.ffmpeg_utils import resolve_ffmpeg_path
        detected = resolve_ffmpeg_path(self.config)
        ffmpeg_hint = QLabel(
            f"当前可用: {detected}" if detected else "当前未检测到 FFmpeg，合成视频将失败"
        )
        ffmpeg_hint.setWordWrap(True)
        ffmpeg_hint.setStyleSheet("color: #64ffda; font-size: 11px;")
        video_layout.addRow("", ffmpeg_hint)

        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setText(self.config.get("output_dir", ""))
        self.output_dir_edit.setPlaceholderText("默认: project/output/")
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self.browse_output_dir)
        output_layout = QHBoxLayout()
        output_layout.addWidget(self.output_dir_edit)
        output_layout.addWidget(browse_btn)
        video_layout.addRow("输出目录:", output_layout)

        tabs.addTab(video_tab, "视频设置")

        # --- 配置总览 ---
        overview_tab = QWidget()
        overview_layout = QVBoxLayout(overview_tab)
        overview_layout.setSpacing(10)

        overview_label = QLabel("当前配置的所有模型和API Key信息：")
        overview_label.setStyleSheet("color: #64ffda; font-weight: bold; font-size: 14px;")
        overview_layout.addWidget(overview_label)

        self.overview_text = QLabel()
        self.overview_text.setWordWrap(True)
        self.overview_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.overview_text.setStyleSheet("""
            QLabel {
                background: #252545;
                border: 1px solid #3a3a5c;
                border-radius: 6px;
                padding: 15px;
                color: #e6e6e6;
                font-family: Consolas, Monaco, monospace;
                font-size: 12px;
                line-height: 1.6;
            }
        """)
        overview_layout.addWidget(self.overview_text)

        refresh_btn = QPushButton("刷新配置总览")
        refresh_btn.clicked.connect(self._refresh_overview)
        overview_layout.addWidget(refresh_btn)

        overview_layout.addStretch()
        tabs.addTab(overview_tab, "配置总览")

        self.video_animated_backend_combo.currentIndexChanged.connect(
            self._refresh_api_route_hint
        )
        self.video_animated_backend_combo.currentIndexChanged.connect(self._refresh_overview)
        self.video_mode_combo.currentIndexChanged.connect(self._refresh_api_route_hint)
        self.video_mode_combo.currentIndexChanged.connect(self._refresh_overview)
        self.visual_style_combo.currentIndexChanged.connect(self._refresh_api_route_hint)
        self.visual_style_combo.currentIndexChanged.connect(self._refresh_overview)
        self.api_key_edit.textChanged.connect(self._refresh_overview)
        self.image_api_key_edit.textChanged.connect(self._refresh_overview)
        self.zhipu_api_key_edit.textChanged.connect(self._refresh_overview)
        self.image_api_combo.currentTextChanged.connect(self._refresh_overview)

        main_layout.addWidget(tabs)

        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.test_btn = QPushButton("测试 DeepSeek")
        self.test_btn.clicked.connect(self.test_api)
        button_layout.addWidget(self.test_btn)

        self.test_sf_btn = QPushButton("测试 SiliconFlow")
        self.test_sf_btn.clicked.connect(self.test_siliconflow)
        button_layout.addWidget(self.test_sf_btn)

        self.test_zhipu_btn = QPushButton("测试智谱清影")
        self.test_zhipu_btn.clicked.connect(self.test_zhipu)
        button_layout.addWidget(self.test_zhipu_btn)

        self.test_glm_image_btn = QPushButton("测试 GLM-Image")
        self.test_glm_image_btn.setToolTip("测试智谱 GLM-Image 人物肖像生图")
        self.test_glm_image_btn.clicked.connect(self.test_glm_image)
        button_layout.addWidget(self.test_glm_image_btn)

        self.ok_btn = QPushButton("确定")
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setDefault(True)
        button_layout.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        main_layout.addLayout(button_layout)

        self._refresh_api_route_hint()
        self._refresh_overview()

    def _mask_key(self, key: str) -> str:
        """遮蔽API Key，只显示前6位和后4位"""
        if not key or len(key) < 12:
            return key if key else "（未设置）"
        return f"{key[:6]}****{key[-4:]}"

    def _refresh_overview(self):
        """刷新配置总览显示"""
        draft = load_config()
        # 从UI获取最新值（如果有）
        if self.api_key_edit.text().strip():
            draft["deepseek_api_key"] = self.api_key_edit.text().strip()
        if self.image_api_key_edit.text().strip():
            draft["image_api_key"] = self.image_api_key_edit.text().strip()
        if self.zhipu_api_key_edit.text().strip():
            draft["zhipu_api_key"] = self.zhipu_api_key_edit.text().strip()
        draft["image_api"] = self.image_api_combo.currentText()
        draft["video_animated_backend"] = self.video_animated_backend_combo.currentData()
        draft["video_mode"] = self.video_mode_combo.currentData()
        draft["visual_style"] = self.visual_style_combo.currentData()

        # 判断实际使用的后端
        from core.api_routing import get_effective_image_api, get_effective_video_backend
        actual_image_api = get_effective_image_api(draft)
        actual_video_backend = get_effective_video_backend(draft)

        overview = []
        overview.append("=" * 50)
        overview.append("【剧本生成】")
        overview.append(f"  模型: {draft.get('deepseek_model', 'deepseek-chat')}")
        overview.append(f"  API地址: {draft.get('deepseek_base_url', 'https://api.deepseek.com')}")
        overview.append(f"  API Key: {self._mask_key(draft.get('deepseek_api_key', ''))}")
        overview.append("")
        overview.append("【图片生成】")
        overview.append(f"  配置后端: {draft.get('image_api', 'deepseek')}")
        overview.append(f"  实际后端: {actual_image_api}")
        if actual_image_api == "siliconflow":
            overview.append(f"  模型: {draft.get('siliconflow_image_model', 'Kwai-Kolors/Kolors')}")
            overview.append(f"  尺寸: {draft.get('siliconflow_image_size', '720x1280')}")
            overview.append(f"  API Key: {self._mask_key(draft.get('image_api_key', ''))}")
        elif actual_image_api == "dall-e":
            overview.append(f"  API Key: {self._mask_key(draft.get('image_api_key', ''))}")
        elif actual_image_api == "zhipu":
            overview.append(f"  模型: {draft.get('zhipu_image_model', 'glm-image')}")
            overview.append(
                f"  定妆照尺寸: {draft.get('zhipu_image_size_portrait', '1056x1568')}"
            )
            overview.append(f"  分镜尺寸: {draft.get('zhipu_image_size', '1088x1472')}")
            overview.append(f"  API Key: {self._mask_key(draft.get('zhipu_api_key', ''))}")
            overview.append("  计费: 约 0.1 元/张（以智谱控制台为准）")
        overview.append("")
        overview.append("【视频生成】")
        overview.append(f"  配置后端: {draft.get('video_animated_backend', 'local')}")
        overview.append(f"  实际后端: {actual_video_backend}")
        overview.append(f"  视频模式: {draft.get('video_mode', 'static')}")
        overview.append(f"  画面风格: {'动漫' if draft.get('visual_style') == 'anime_cartoon' else '真人'}")
        if actual_video_backend == "siliconflow":
            overview.append(f"  SiliconFlow模型: {draft.get('siliconflow_video_model', 'Wan-AI/Wan2.2-I2V-A14B')}")
            overview.append(f"  API Key: {self._mask_key(draft.get('image_api_key', ''))}")
        elif actual_video_backend == "zhipu":
            overview.append(f"  智谱模型: {draft.get('zhipu_video_model', 'cogvideox-flash')}")
            overview.append(f"  尺寸: {draft.get('zhipu_video_size', '720x1280')}")
            overview.append(f"  帧率: {draft.get('zhipu_video_fps', 30)}")
            overview.append(f"  时长: {draft.get('zhipu_video_duration', 5)}秒")
            overview.append(f"  API Key: {self._mask_key(draft.get('zhipu_api_key', ''))}")
        overview.append("")
        overview.append("【语音合成】")
        overview.append(f"  服务: Edge TTS（免费，无需API Key）")
        overview.append(f"  旁白音色: {draft.get('tts_voice_narrator', 'zh-CN-YunxiNeural')}")
        overview.append(f"  男角色: {draft.get('tts_voice_male', 'zh-CN-YunxiNeural')}")
        overview.append(f"  女角色: {draft.get('tts_voice_female', 'zh-CN-XiaochenNeural')}")
        overview.append("")
        overview.append("【输出设置】")
        overview.append(f"  分辨率: {draft.get('video_width', 1080)}x{draft.get('video_height', 1920)}")
        overview.append(f"  帧率: {draft.get('video_fps', 24)}")
        overview.append(f"  转场: {draft.get('transition_duration', 0.5)}秒")
        overview.append("=" * 50)

        if hasattr(self, 'overview_text'):
            self.overview_text.setText("\n".join(overview))

    def _refresh_api_route_hint(self):
        from core.api_routing import describe_active_apis
        draft = load_config()
        draft["image_api"] = self.image_api_combo.currentText()
        draft["image_api_key"] = self.image_api_key_edit.text().strip()
        draft["video_animated_backend"] = self.video_animated_backend_combo.currentData()
        draft["video_mode"] = self.video_mode_combo.currentData()
        if hasattr(self, "sf_route_label"):
            self.sf_route_label.setText(describe_active_apis(draft))

    def _browse_ffmpeg(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 ffmpeg.exe",
            "",
            "FFmpeg (ffmpeg.exe);;所有文件 (*.*)",
        )
        if path:
            self.ffmpeg_path_edit.setText(path)

    def _browse_bgm(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择背景音乐",
            "",
            "音频文件 (*.mp3 *.wav *.m4a *.aac *.ogg);;所有文件 (*.*)",
        )
        if path:
            self.bgm_path_edit.setText(path)
            self.bgm_enabled_check.setChecked(True)

    def browse_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择输出目录"
        )
        if dir_path:
            self.output_dir_edit.setText(dir_path)

    def test_api(self):
        """测试API连接"""
        api_key = self.api_key_edit.text().strip()
        if not api_key:
            QMessageBox.warning(self, "警告", "请先输入API Key！")
            return

        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=api_key,
                base_url=self.base_url_edit.text().strip(),
            )
            response = client.chat.completions.create(
                model=self.model_combo.currentText(),
                messages=[{"role": "user", "content": "用中文说'测试成功'"}],
                max_tokens=20,
            )
            result = response.choices[0].message.content
            QMessageBox.information(self, "成功", f"API测试通过！\n\n响应: {result}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"API测试失败:\n{e}")

    def test_siliconflow(self):
        """测试 SiliconFlow 文生图 API 是否可用。"""
        import requests
        api_key = self.image_api_key_edit.text().strip()
        if not api_key:
            QMessageBox.warning(self, "警告", "请先填写「图片API Key」（SiliconFlow 密钥）！")
            return
        model = self.siliconflow_image_model_edit.text().strip() or "Kwai-Kolors/Kolors"
        try:
            r = requests.post(
                "https://api.siliconflow.cn/v1/images/generations",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "prompt": "a simple red circle on white background, test",
                    "image_size": "512x512",
                    "batch_size": 1,
                },
                timeout=120,
            )
            data = r.json() if r.text else {}
            if r.status_code == 200 and (data.get("images") or data.get("data")):
                QMessageBox.information(
                    self, "SiliconFlow 可用",
                    f"文生图接口调用成功（HTTP 200）。\n模型: {model}\n\n"
                    "保存设置后，生成图片/动效将走 SiliconFlow。",
                )
                return
            msg = data.get("message") if isinstance(data, dict) else r.text[:300]
            QMessageBox.critical(
                self, "SiliconFlow 失败",
                f"HTTP {r.status_code}\n{msg}",
            )
        except Exception as e:
            QMessageBox.critical(self, "SiliconFlow 失败", str(e))

    def test_zhipu(self):
        """测试智谱清影 API 是否可用。"""
        import requests
        # 优先使用UI输入框的值，如果为空则从配置读取
        api_key = self.zhipu_api_key_edit.text().strip()
        if not api_key:
            api_key = self.config.get("zhipu_api_key", "").strip()
        if not api_key:
            QMessageBox.warning(self, "警告", "请先填写「智谱 API Key」！")
            return
        try:
            from core.http_client import request_with_retry, zhipu_ssl_hint

            r = request_with_retry(
                "GET",
                "https://open.bigmodel.cn/api/paas/v4/models",
                headers={
                    "Authorization": f"Bearer {api_key}",
                },
                timeout=30,
                max_attempts=5,
            )
            if r.status_code == 200:
                QMessageBox.information(
                    self, "智谱清影可用",
                    f"智谱 API 连接成功（HTTP 200）。\n"
                    f"Key: {api_key[:10]}...\n\n"
                    "保存设置后，生成视频将走智谱清影。",
                )
                return
            data = r.json() if r.text else {}
            msg = data.get("error", {}).get("message") if isinstance(data, dict) else r.text[:300]
            QMessageBox.critical(
                self, "智谱清影失败",
                f"HTTP {r.status_code}\n{msg}\n\n"
                f"当前Key: {api_key[:10]}...",
            )
        except Exception as e:
            from core.http_client import zhipu_ssl_hint

            QMessageBox.critical(self, "智谱清影失败", f"{e}\n{zhipu_ssl_hint()}")

    def test_glm_image(self):
        """测试智谱 GLM-Image 人物肖像生图。"""
        api_key = self.zhipu_api_key_edit.text().strip()
        if not api_key:
            QMessageBox.warning(self, "警告", "请先填写「智谱 API Key」！")
            return
        model = self.zhipu_image_model_edit.text().strip() or "glm-image"
        size = self.zhipu_image_size_portrait_edit.text().strip() or "1056x1568"
        try:
            from core.zhipu_image import generate_glm_image
            generate_glm_image(
                api_key,
                "竖屏纪实人物肖像，中国农村老人，头肩构图，真实皮肤皱纹，自然光，高清照片",
                model=model,
                size=size,
            )
            QMessageBox.information(
                self,
                "GLM-Image 可用",
                f"智谱 GLM-Image 调用成功。\n模型: {model}\n尺寸: {size}\n\n"
                "请在「图片API」中选择 zhipu 并保存设置后生成定妆照。",
            )
        except Exception as e:
            QMessageBox.critical(self, "GLM-Image 失败", str(e))

    def accept(self):
        """保存设置（合并写入，保留配置文件中未在界面展示的项目）"""
        merged = load_config()
        sf_key = self.image_api_key_edit.text().strip()
        image_api = self.image_api_combo.currentText()
        video_backend = self.video_animated_backend_combo.currentData()
        if sf_key:
            if image_api == "deepseek":
                image_api = "siliconflow"
            if video_backend == "local" and self.video_mode_combo.currentData() == "animated":
                video_backend = "siliconflow"
        merged.update({
            "deepseek_api_key": self.api_key_edit.text().strip(),
            "deepseek_base_url": self.base_url_edit.text().strip(),
            "deepseek_model": self.model_combo.currentText(),
            "image_api": image_api,
            "image_api_key": sf_key,
            "zhipu_api_key": self.zhipu_api_key_edit.text().strip(),
            "zhipu_image_model": self.zhipu_image_model_edit.text().strip(),
            "zhipu_image_size_portrait": self.zhipu_image_size_portrait_edit.text().strip(),
            "zhipu_image_size": self.zhipu_image_size_edit.text().strip(),
            "pollinations_model": self.pollinations_model_combo.currentText(),
            "siliconflow_image_model": self.siliconflow_image_model_edit.text().strip(),
            "siliconflow_image_size": self.siliconflow_image_size_edit.text().strip(),
            "image_fit_mode": self.image_fit_mode_combo.currentData(),
            "character_ref_image_mode": self.character_ref_image_mode_combo.currentData(),
            "character_ref_video_first_frame": self.character_ref_video_first_frame_combo.currentData(),
            "character_consistency": self.character_consistency_combo.currentData(),
            "character_scene_img2img_strength": self.character_img2img_strength_spin.value(),
            "tts_voice_narrator": self.narrator_combo.currentData(),
            "tts_voice_male": self.male_combo.currentData(),
            "tts_voice_female": self.female_combo.currentData(),
            "bgm_enabled": self.bgm_enabled_check.isChecked(),
            "bgm_path": self.bgm_path_edit.text().strip(),
            "bgm_volume": self.bgm_volume_spin.value(),
            "video_width": self.width_spin.value(),
            "video_height": self.height_spin.value(),
            "video_fps": self.fps_spin.value(),
            "visual_style": self.visual_style_combo.currentData(),
            "scene_clip_fallback": self.scene_clip_fallback_combo.currentData(),
            "video_mode": self.video_mode_combo.currentData(),
            "video_animated_backend": video_backend,
            "siliconflow_video_model": self.siliconflow_video_model_edit.text().strip(),
            "zhipu_video_model": self.zhipu_video_model_combo.currentText().split(" ")[0].strip(),
            "transition_duration": self.transition_spin.value(),
            "ffmpeg_path": self.ffmpeg_path_edit.text().strip(),
            "output_dir": self.output_dir_edit.text().strip(),
        })
        save_config(merged)
        self.config = merged
        from core.ffmpeg_utils import configure_ffmpeg
        configure_ffmpeg(merged)
        super().accept()