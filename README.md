# AI Short Drama Generator / AI 短剧生成器

输入一段文字，自动生成短剧风格的剧本、分镜、配音和视频。

## 功能特性

- **AI 剧本生成**：基于 DeepSeek API，输入主题自动生成完整短剧剧本（霸总/复仇/悬疑/搞笑等风格）
- **分镜解析**：将剧本自动解析为分镜列表，包含场景描述、对话、旁白
- **AI 生图**：SiliconFlow / Pollinations 等云端生图（无需本地 GPU）
- **角色参考图**：可为各角色上传参考照，SiliconFlow 生图时尽量保持外形一致
- **AI 配音**：基于 Edge TTS（免费）生成中文配音，支持多角色不同音色
- **视频合成**：MoviePy + FFmpeg 合成竖屏 MP4；可选 SiliconFlow 图生视频或本地动效
- **PyQt5 桌面 GUI**：图形化操作界面，一键生成完整视频

## 安装依赖

```bash
cd ai-short-drama
pip install -r requirements.txt
```

### 系统依赖

- Python 3.9+（推荐 3.9-3.12）
- FFmpeg（MoviePy 合成需要，下载后加入 PATH）
- PyQt5 需要显示环境（Windows 直接运行即可）
- **无需本地 GPU**（生图、剧本均在云端完成）

### Conda 环境（推荐）

```bash
conda create -n video39 python=3.9
conda activate video39
pip install -r requirements.txt
```

## 配置

启动后在菜单 `设置` 中填入：

| 配置项 | 说明 |
|--------|------|
| DeepSeek API Key | 必填，在 https://platform.deepseek.com 获取 |
| 图片 API | 推荐 `siliconflow`（填 SiliconFlow Key）或 `pollinations`（免费） |
| 分镜动态视频 | 可选 SiliconFlow 图生视频（需 Key，云端 GPU） |

## 使用流程

### 一键生成（推荐）
1. 输入故事主题
2. 选择风格
3. 可选：在「角色参考图」为各角色上传照片
4. 点击 **一键生成视频**

### 分步生成
1. **生成剧本** → **生成图片** → **生成配音** → **合成视频**

## 项目结构

```
ai-short-drama/
├── main.py
├── config.py
├── core/
│   ├── story_generator.py
│   ├── storyboard.py
│   ├── image_generator.py
│   ├── voice_generator.py
│   ├── video_generator.py
│   ├── video_composer.py
│   └── character_refs.py
├── ui/
│   ├── main_window.py
│   ├── settings_dialog.py
│   └── character_refs_panel.py
└── output/
```

## 技术栈

| 模块 | 技术 |
|------|------|
| GUI | PyQt5 |
| 剧本 | DeepSeek API |
| 配音 | Edge TTS |
| 生图 | SiliconFlow / Pollinations |
| 合成 | MoviePy + FFmpeg |
