# AI Short Drama Generator / AI 短剧生成器

输入一段文字，自动生成短剧风格的剧本、分镜、配音和视频。

## 功能特性

- **AI 剧本生成**：基于 DeepSeek API，输入主题自动生成完整短剧剧本（霸总/复仇/悬疑/搞笑等风格）
- **分镜解析**：将剧本自动解析为分镜列表，包含场景描述、对话、旁白
- **AI 生图**：SiliconFlow / Pollinations 等云端生图（无需本地 GPU）
- **角色参考图**：可为各角色上传参考照，SiliconFlow 生图时尽量保持外形一致
- **AI 配音**：Edge TTS；角色参考图区可为每人指定音色，未指定则按性别自动分配
- **视频合成**：MoviePy + FFmpeg 合成竖屏 MP4；可选图生视频/本地动效；可叠加本地 BGM
- **断点续跑**：已有剧本时「续跑生成」，自动跳过已完成的分镜图/动效/配音
- **单镜操作**：编辑/AI 改写剧本、重生本镜图/配音/动效、导出 SRT 字幕
- **历史记录**：自动保存剧本与成片路径，可加载续做
- **PyQt5 桌面 GUI**：一键生成或分步生成

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
3. 可选：在「角色参考图」上传参考照，并为角色选择 **配音音色**
4. 点击 **一键生成视频**

### 续跑生成
中断或分步做到一半时：先 **生成剧本**（或加载剧本），再点 **续跑生成**。程序会检测 `output/` 下已有素材，只补缺失步骤并合成成片。

### 分步生成
1. **生成剧本** → **生成图片+动效** → **生成配音** → **合成视频**

### AI科普口播（程序员老韩类）

1. 风格选 **「AI科普口播」** 或 **「程序员口播」**（二者相同）
2. 输入本期主题，例如：`DeepSeek 三个必会功能，别再瞎用 ChatGPT`
3. 角色参考图里给「老韩」选固定 **男声音色**（可选上传半身照作一致性参考）
4. **一键生成** 或分步生成；程序会自动偏向 **真人纪实 + 静图口播**（少动效）

成片结构：钩子 → 分点干货 → 总结 → 关注引导；以 **旁白字幕** 为主。若要演示软件界面，建议后期用剪映叠 **真录屏**。

### 其他
- **设置 → 声音**：旁白/男女默认音色、BGM 文件与音量
- **文件 → 导出字幕 (SRT)**、**续跑一键生成**
- 选中分镜后可 **编辑本镜** / **AI改写本镜** / **重生本镜图|配音|动效**

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
│   ├── pipeline_resume.py
│   ├── bgm_mixer.py
│   └── character_refs.py
├── ui/
│   ├── main_window.py
│   ├── settings_dialog.py
│   ├── character_refs_panel.py
│   ├── scene_edit_dialog.py
│   └── scene_rewrite_dialog.py
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
