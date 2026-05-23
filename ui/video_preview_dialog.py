"""
历史记录 / 成片预览：应用内播放 MP4。
"""
import os
from typing import Optional

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QMessageBox,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QFont

try:
    from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
    from PyQt5.QtMultimediaWidgets import QVideoWidget

    _HAS_QT_MEDIA = True
except ImportError:
    _HAS_QT_MEDIA = False


class VideoPreviewDialog(QDialog):
    """应用内视频预览（需 PyQt5 多媒体模块）。"""

    def __init__(self, video_path: str, title: str = "", parent=None):
        super().__init__(parent)
        self._video_path = os.path.abspath(video_path)
        self._title = title or os.path.basename(self._video_path)
        self._player = None
        self._qt_playback_failed = False
        self.setWindowTitle(f"播放成片 — {self._title}")
        self.setMinimumSize(400, 720)
        self.resize(405, 780)
        self._build_ui()
        self._load_media()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title_label = QLabel(self._title)
        title_label.setFont(QFont("Microsoft YaHei", 11))
        title_label.setWordWrap(True)
        title_label.setStyleSheet("color: #e6e6e6;")
        layout.addWidget(title_label)

        path_label = QLabel(self._video_path)
        path_label.setStyleSheet("color: #8892b0; font-size: 11px;")
        path_label.setWordWrap(True)
        layout.addWidget(path_label)

        if _HAS_QT_MEDIA:
            self.video_widget = QVideoWidget()
            self.video_widget.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Expanding
            )
            self.video_widget.setStyleSheet("background: #000;")
            layout.addWidget(self.video_widget, 1)

            self._player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
            self._player.setVideoOutput(self.video_widget)
            self._player.stateChanged.connect(self._on_state_changed)
            self._player.error.connect(self._on_error)
        else:
            layout.addWidget(
                QLabel("当前环境未加载 Qt 多媒体模块，将用系统播放器打开。")
            )

        btn_row = QHBoxLayout()
        self.btn_play = QPushButton("播放")
        self.btn_play.setMinimumHeight(36)
        self.btn_play.clicked.connect(self._toggle_play)
        btn_row.addWidget(self.btn_play)

        self.btn_stop = QPushButton("停止")
        self.btn_stop.setMinimumHeight(36)
        self.btn_stop.clicked.connect(self._stop)
        btn_row.addWidget(self.btn_stop)

        btn_open = QPushButton("系统播放器打开")
        btn_open.setMinimumHeight(36)
        btn_open.clicked.connect(lambda: open_video_externally(self._video_path, self))
        btn_row.addWidget(btn_open)

        btn_close = QPushButton("关闭")
        btn_close.setMinimumHeight(36)
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _load_media(self):
        if not _HAS_QT_MEDIA or not self._player:
            return
        url = QUrl.fromLocalFile(self._video_path)
        self._player.setMedia(QMediaContent(url))

    def _on_state_changed(self, state):
        if not _HAS_QT_MEDIA:
            return
        if state == QMediaPlayer.PlayingState:
            self.btn_play.setText("暂停")
        else:
            self.btn_play.setText("播放")

    def _on_error(self):
        if not self._player or self._qt_playback_failed:
            return
        self._qt_playback_failed = True
        err = self._player.errorString()
        if not err:
            err = "未知原因（Qt 多媒体模块缺少解码器或文件格式不兼容）"
        msg = (
            f"Qt 内置播放器无法播放：\n{err}\n\n"
            f"文件：{self._video_path}\n\n"
            f"正在尝试用系统播放器打开…"
        )
        QMessageBox.information(self, "播放器提示", msg)
        open_video_externally(self._video_path, self)

    def _toggle_play(self):
        if not _HAS_QT_MEDIA or not self._player or self._qt_playback_failed:
            open_video_externally(self._video_path, self)
            return
        if self._player.state() == QMediaPlayer.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _stop(self):
        if self._player:
            self._player.stop()

    def showEvent(self, event):
        super().showEvent(event)
        if _HAS_QT_MEDIA and self._player:
            self._player.play()

    def closeEvent(self, event):
        if self._player:
            self._player.stop()
        super().closeEvent(event)


def open_video_externally(video_path: str, parent=None) -> bool:
    """用系统默认程序打开视频。"""
    import platform
    import subprocess

    if not video_path or not os.path.isfile(video_path):
        if parent:
            QMessageBox.information(parent, "提示", "视频文件不存在。")
        return False
    try:
        if platform.system() == "Windows":
            os.startfile(video_path)
        elif platform.system() == "Darwin":
            subprocess.run(["open", video_path], check=False)
        else:
            subprocess.run(["xdg-open", video_path], check=False)
        return True
    except Exception as e:
        if parent:
            QMessageBox.critical(parent, "错误", f"无法打开视频:\n{e}")
        return False


def play_video(parent, video_path: str, title: str = "") -> None:
    """打开预览弹窗；若 Qt 多媒体不可用则直接调用系统播放器。"""
    if not video_path or not os.path.isfile(video_path):
        QMessageBox.information(parent, "提示", "该记录没有可播放的成片文件。")
        return
    if _HAS_QT_MEDIA:
        dlg = VideoPreviewDialog(video_path, title=title, parent=parent)
        dlg.exec_()
    else:
        open_video_externally(video_path, parent)
