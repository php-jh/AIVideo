"""
AI Short Drama Generator - Application Entry Point
"""
import os
import sys

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont, QPalette, QColor

from ui.main_window import MainWindow
from logger import setup_logging
from core.ffmpeg_utils import configure_ffmpeg

logger = setup_logging()


def _apply_dark_palette(app: QApplication) -> None:
    """Fusion + 深色调色板，避免 Windows 原生样式下控件白底。"""
    app.setStyle("Fusion")
    p = QPalette()
    bg = QColor("#1a1a2e")
    panel = QColor("#252545")
    p.setColor(QPalette.Window, bg)
    p.setColor(QPalette.WindowText, QColor("#e6e6e6"))
    p.setColor(QPalette.Base, panel)
    p.setColor(QPalette.AlternateBase, QColor("#1e2038"))
    p.setColor(QPalette.Text, QColor("#e6e6e6"))
    p.setColor(QPalette.Button, QColor("#3a3a5c"))
    p.setColor(QPalette.ButtonText, QColor("#e6e6e6"))
    p.setColor(QPalette.Highlight, QColor("#4a69bd"))
    p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ToolTipBase, panel)
    p.setColor(QPalette.ToolTipText, QColor("#e6e6e6"))
    app.setPalette(p)


def main():
    logger.info("启动 AI Short Drama Generator")
    configure_ffmpeg()

    app = QApplication(sys.argv)
    app.setApplicationName("AI Short Drama Generator")
    app.setApplicationDisplayName("AI Short Drama Generator")
    _apply_dark_palette(app)

    # 设置默认字体（支持中文）
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    logger.info("主窗口已显示")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
