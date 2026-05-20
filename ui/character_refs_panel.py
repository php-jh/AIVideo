"""
主界面「角色参考图」面板：多人物、每人一张图（人物A → 图片A）。
"""
import os
from typing import List, Dict, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QLineEdit,
    QScrollArea, QFileDialog, QMessageBox, QFrame, QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QFont

# 主界面嵌入用紧凑尺寸（横向滚动）；弹窗仍用大卡片
CARD_WIDTH = 152
THUMB_W, THUMB_H = 88, 110
# 紧凑卡片完整高度：名称+缩略图+竖排按钮+移除
COMPACT_CARD_HEIGHT = THUMB_H + 168
CARD_WIDTH_DIALOG = 300
THUMB_W_DIALOG, THUMB_H_DIALOG = 220, 300
GRID_COLS = 3
FONT_PT = 13
IMAGE_FILTER = "图片 (*.png *.jpg *.jpeg *.webp *.bmp)"

_BTN_STYLE_PRIMARY = (
    "QPushButton { background: #4a69bd; color: white; border-radius: 6px; "
    "padding: 10px 18px; font-size: 14px; min-height: 40px; }"
    "QPushButton:hover { background: #6a89ed; }"
)
_BTN_STYLE_SECONDARY = (
    "QPushButton { background: #3a3a5c; color: #e6e6e6; border-radius: 6px; "
    "padding: 10px 18px; font-size: 14px; min-height: 40px; }"
)


def _btn_style(primary: bool, compact: bool) -> str:
    h = "32px" if compact else "40px"
    fs = "12px" if compact else "14px"
    pad = "6px 10px" if compact else "10px 18px"
    if primary:
        return (
            f"QPushButton {{ background: #4a69bd; color: white; border-radius: 6px; "
            f"padding: {pad}; font-size: {fs}; min-height: {h}; }}"
            "QPushButton:hover { background: #6a89ed; }"
        )
    return (
        f"QPushButton {{ background: #3a3a5c; color: #e6e6e6; border-radius: 6px; "
        f"padding: {pad}; font-size: {fs}; min-height: {h}; }}"
    )


class CharacterRefCard(QFrame):
    """单个角色：名称 + 缩略图 + 上传/清除。"""

    changed = pyqtSignal()

    def __init__(
        self, name: str = "", ref_path: str = "", parent=None,
        card_width: int = CARD_WIDTH, thumb_w: int = THUMB_W, thumb_h: int = THUMB_H,
    ):
        super().__init__(parent)
        self._ref_path = ""
        self._thumb_w = thumb_w
        self._thumb_h = thumb_h
        self.setObjectName("characterRefCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "#characterRefCard { background: #252545; border: 1px solid #3a3a5c; border-radius: 10px; }"
        )
        self.setFixedWidth(card_width)
        self._compact_card = thumb_w < 150
        if not self._compact_card:
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._build_ui()
        if self._compact_card:
            h = max(COMPACT_CARD_HEIGHT, self.sizeHint().height())
            self.setFixedSize(card_width, h)
        self.set_name(name)
        if ref_path:
            self.set_reference_image(ref_path)

    def _build_ui(self):
        compact = self._thumb_w < 150
        pad = 10 if compact else 16
        layout = QVBoxLayout(self)
        layout.setContentsMargins(pad, pad, pad, pad)
        layout.setSpacing(8 if compact else 12)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("角色名，如：林晓")
        self.name_edit.setMinimumHeight(32 if compact else 44)
        font = QFont("Microsoft YaHei", FONT_PT)
        self.name_edit.setFont(font)
        self.name_edit.setStyleSheet(
            "QLineEdit { background: #1a1a2e; color: #e6e6e6; border: 1px solid #3a3a5c; "
            "border-radius: 6px; padding: 8px 12px; font-size: 14px; }"
        )
        self.name_edit.textChanged.connect(lambda: self.changed.emit())
        layout.addWidget(self.name_edit)

        thumb_text = "点「上传图片」" if compact else "未上传\n点击「上传图片」"
        self.thumb = QLabel(thumb_text)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setFixedSize(self._thumb_w, self._thumb_h)
        self.thumb.setFont(QFont("Microsoft YaHei", 10 if compact else 12))
        self.thumb.setWordWrap(True)
        fs = 10 if compact else 13
        self.thumb.setStyleSheet(
            "QLabel { background: #1a1a2e; color: #8892b0; border: 2px dashed #4a69bd; "
            "border-radius: 8px; font-size: %dpx; padding: 4px; }" % fs
        )
        layout.addWidget(self.thumb, alignment=Qt.AlignCenter)

        self.file_label = QLabel("")
        self.file_label.setWordWrap(True)
        self.file_label.setStyleSheet("color: #8892b0; font-size: 12px;")
        self.file_label.setMaximumHeight(40)
        if not compact:
            layout.addWidget(self.file_label)

        self.btn_upload = QPushButton("上传图片")
        self.btn_upload.setStyleSheet(_btn_style(True, compact))
        self.btn_upload.setFixedHeight(32 if compact else 40)
        self.btn_upload.setCursor(Qt.PointingHandCursor)
        self.btn_upload.clicked.connect(self._pick_image)

        self.btn_clear = QPushButton("清除")
        self.btn_clear.setStyleSheet(_btn_style(False, compact))
        self.btn_clear.setFixedHeight(32 if compact else 40)
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.clicked.connect(self._clear_image)

        if compact:
            layout.addWidget(self.btn_upload)
            layout.addWidget(self.btn_clear)
        else:
            btn_row = QHBoxLayout()
            btn_row.setSpacing(10)
            btn_row.addWidget(self.btn_upload)
            btn_row.addWidget(self.btn_clear)
            layout.addLayout(btn_row)

        self.btn_remove = QPushButton("移除")
        self.btn_remove.setMinimumHeight(28 if compact else 36)
        self.btn_remove.setStyleSheet(
            "QPushButton { background: transparent; color: #e74c3c; border: none; font-size: 12px; }"
            "QPushButton:hover { color: #ff6b6b; }"
        )
        layout.addWidget(self.btn_remove)

    def set_remove_callback(self, callback):
        self.btn_remove.clicked.connect(callback)

    def get_name(self) -> str:
        return self.name_edit.text().strip()

    def get_reference_path(self) -> str:
        return self._ref_path if self._ref_path and os.path.isfile(self._ref_path) else ""

    def set_name(self, name: str):
        self.name_edit.blockSignals(True)
        self.name_edit.setText(name or "")
        self.name_edit.blockSignals(False)

    def set_reference_image(self, path: str):
        path = (path or "").strip()
        if path:
            path = os.path.abspath(os.path.expanduser(path))
        if path and os.path.isfile(path):
            self._ref_path = path
            pix = QPixmap(path)
            if not pix.isNull():
                self.thumb.setPixmap(
                    pix.scaled(self._thumb_w, self._thumb_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                self.thumb.setStyleSheet(
                    "QLabel { background: #1a1a2e; border: 2px solid #4a69bd; border-radius: 8px; }"
                )
            self.file_label.setText(os.path.basename(path))
        else:
            self._clear_image(silent=True)
        self.changed.emit()

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window() or self,
            f"为「{self.get_name() or '角色'}」选择参考图",
            "",
            IMAGE_FILTER,
        )
        if path:
            self.set_reference_image(path)

    def _clear_image(self, silent=False):
        self._ref_path = ""
        self.thumb.clear()
        compact = self._thumb_w < 150
        self.thumb.setText("点「上传图片」" if compact else "未上传\n点击「上传图片」")
        self.thumb.setStyleSheet(
            "QLabel { background: #1a1a2e; color: #8892b0; border: 2px dashed #4a69bd; "
            "border-radius: 8px; font-size: 13px; }"
        )
        self.file_label.setText("")
        if not silent:
            self.changed.emit()

    def to_character_dict(self, existing: Optional[dict] = None) -> dict:
        ch = {"name": self.get_name(), "description": ""}
        if existing:
            ch["description"] = existing.get("description", "")
            for k in ("age", "gender", "personality"):
                if k in existing:
                    ch[k] = existing[k]
        ref = self.get_reference_path()
        if ref:
            ch["reference_image"] = ref
        return ch


class CharacterRefsPanel(QWidget):
    """
    网格排列多卡片：人物A→图A，人物B→图B。
    apply_to_script(script) 写入 script['characters']。
    """

    changed = pyqtSignal()

    def __init__(self, parent=None, scroll_min_height: int = 0, large_cards: bool = False):
        super().__init__(parent)
        self._script: Optional[dict] = None
        self._cards: List[CharacterRefCard] = []
        self._large_cards = large_cards
        self._card_w = CARD_WIDTH_DIALOG if large_cards else CARD_WIDTH
        self._thumb_w = THUMB_W_DIALOG if large_cards else THUMB_W
        self._thumb_h = THUMB_H_DIALOG if large_cards else THUMB_H
        self._scroll_min_height = scroll_min_height or (
            (THUMB_H_DIALOG + 120) if large_cards else COMPACT_CARD_HEIGHT + 16
        )
        self._horizontal_cards = not large_cards
        self.setStyleSheet("background: transparent;")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(14)

        if self._large_cards:
            hint = QLabel(
                "为每个角色单独上传一张参考照（正面或半身更清晰）。"
                "生图请在设置中选 SiliconFlow；人物A 用图A、人物B 用图B。"
            )
            hint.setWordWrap(True)
            hint.setFont(QFont("Microsoft YaHei", FONT_PT))
            hint.setStyleSheet("color: #8892b0; font-size: 14px;")
            root.addWidget(hint)
        else:
            hint = QLabel("为各角色上传参考图（SiliconFlow 生图时按角色匹配）")
            hint.setFont(QFont("Microsoft YaHei", 11))
            hint.setStyleSheet("color: #8892b0; font-size: 12px;")
            root.addWidget(hint)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)
        self.btn_sync = QPushButton("从剧本同步角色名")
        self.btn_sync.setStyleSheet(_BTN_STYLE_PRIMARY)
        self.btn_sync.setMinimumHeight(36 if not self._large_cards else 44)
        self.btn_sync.setToolTip("根据剧本 characters 与分镜对话中的角色名生成卡片")
        self.btn_sync.clicked.connect(self.sync_names_from_script)
        toolbar.addWidget(self.btn_sync)

        self.btn_add = QPushButton("+ 添加角色")
        self.btn_add.setStyleSheet(_BTN_STYLE_SECONDARY)
        self.btn_add.setMinimumHeight(36 if not self._large_cards else 44)
        self.btn_add.clicked.connect(lambda: self.add_card())
        toolbar.addWidget(self.btn_add)

        self.status_label = QLabel("")
        self.status_label.setFont(QFont("Microsoft YaHei", FONT_PT))
        self.status_label.setStyleSheet("color: #64ffda; font-size: 14px;")
        toolbar.addWidget(self.status_label)
        toolbar.addStretch()
        root.addLayout(toolbar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._cards_scroll = scroll
        scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #3a3a5c; border-radius: 8px; "
            "background-color: #252545; }"
        )

        self.cards_host = QWidget()
        self.cards_host.setStyleSheet("background-color: #252545;")
        if self._horizontal_cards:
            card_strip_h = COMPACT_CARD_HEIGHT + 16
            scroll.setFixedHeight(card_strip_h)
            self.cards_host.setMinimumHeight(COMPACT_CARD_HEIGHT)
            self.cards_layout = QHBoxLayout(self.cards_host)
            self.cards_layout.setContentsMargins(8, 8, 8, 8)
            self.cards_layout.setSpacing(12)
            self.cards_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        else:
            self.cards_layout = QGridLayout(self.cards_host)
            self.cards_layout.setContentsMargins(16, 16, 16, 16)
            self.cards_layout.setSpacing(20)
            self.cards_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(self.cards_host)
        root.addWidget(scroll, 0)

    def _relayout_cards(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(self.cards_host)
        if self._horizontal_cards:
            for card in self._cards:
                self.cards_layout.addWidget(card, 0, Qt.AlignLeft | Qt.AlignTop)
        else:
            for i, card in enumerate(self._cards):
                row, col = divmod(i, GRID_COLS)
                self.cards_layout.addWidget(card, row, col, Qt.AlignTop | Qt.AlignLeft)

    def set_script(self, script: Optional[dict]):
        self._script = script
        self.load_from_script(script)

    def _find_existing_char(self, name: str) -> Optional[dict]:
        if not self._script:
            return None
        for ch in self._script.get("characters") or []:
            if isinstance(ch, dict) and (ch.get("name") or "").strip() == name:
                return ch
        return None

    def add_card(self, name: str = "", ref_path: str = "", insert_at: int = -1) -> CharacterRefCard:
        card = CharacterRefCard(
            name, ref_path, self.cards_host,
            card_width=self._card_w, thumb_w=self._thumb_w, thumb_h=self._thumb_h,
        )
        card.changed.connect(self._on_card_changed)
        card.set_remove_callback(lambda c=card: self._remove_card(c))

        if insert_at >= 0 and insert_at < len(self._cards):
            self._cards.insert(insert_at, card)
        else:
            self._cards.append(card)
        self._relayout_cards()
        self._update_status()
        return card

    def _remove_card(self, card: CharacterRefCard):
        if len(self._cards) <= 1:
            QMessageBox.information(self.window() or self, "提示", "至少保留一个角色位。")
            return
        reply = QMessageBox.question(
            self.window() or self,
            "确认",
            f"移除角色「{card.get_name() or '未命名'}」？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._cards.remove(card)
        self.cards_layout.removeWidget(card)
        card.deleteLater()
        self._relayout_cards()
        self._on_card_changed()

    def clear_cards(self):
        for card in list(self._cards):
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

    def load_from_script(self, script: Optional[dict]):
        self._script = script
        self.clear_cards()
        chars = []
        if script:
            chars = script.get("characters") or []
        if chars:
            for ch in chars:
                if not isinstance(ch, dict):
                    continue
                self.add_card(
                    ch.get("name", ""),
                    ch.get("reference_image", ""),
                )
        else:
            self.add_card()
        self._update_status()

    def merge_from_script(self, script: Optional[dict]):
        """剧本更新后合并：保留已上传的图，补全新角色名。"""
        self._script = script
        if not script:
            self.load_from_script(None)
            return

        refs_by_name: Dict[str, str] = {}
        for card in self._cards:
            n = card.get_name()
            p = card.get_reference_path()
            if n and p:
                refs_by_name[n] = p

        for ch in script.get("characters") or []:
            if not isinstance(ch, dict):
                continue
            n = (ch.get("name") or "").strip()
            p = (ch.get("reference_image") or "").strip()
            if n and p and os.path.isfile(p):
                refs_by_name[n] = os.path.abspath(p)

        names = self.collect_character_names_from_script()
        if not names and not refs_by_name:
            if not self._cards:
                self.add_card()
            return

        if not names:
            names = list(refs_by_name.keys())

        self.clear_cards()
        for name in names:
            self.add_card(name, refs_by_name.get(name, ""))
        if not self._cards:
            self.add_card()
        self.apply_to_script(script)
        self._update_status()

    def collect_character_names_from_script(self) -> List[str]:
        """从剧本 characters + 各镜对话收集角色名（去重、保序）。"""
        names: List[str] = []
        seen = set()
        if not self._script:
            return names

        def add(n: str):
            n = (n or "").strip()
            if n and n not in seen:
                seen.add(n)
                names.append(n)

        for ch in self._script.get("characters") or []:
            if isinstance(ch, dict):
                add(ch.get("name", ""))

        for scene in self._script.get("scenes") or []:
            if not isinstance(scene, dict):
                continue
            for d in scene.get("dialogues") or []:
                add(d.get("character", ""))
            for c in scene.get("characters") or []:
                if isinstance(c, dict):
                    add(c.get("name", ""))
                elif isinstance(c, str):
                    add(c)
        return names

    def sync_names_from_script(self):
        if not self._script:
            QMessageBox.warning(self.window() or self, "提示", "请先生成或加载剧本。")
            return
        names = self.collect_character_names_from_script()
        if not names:
            QMessageBox.information(self.window() or self, "提示", "剧本中暂无角色名，可手动添加。")
            return

        existing_by_name: Dict[str, CharacterRefCard] = {}
        for card in self._cards:
            n = card.get_name()
            if n:
                existing_by_name[n] = card

        for card in list(self._cards):
            if not card.get_name() and not card.get_reference_path():
                self._remove_card_silent(card)

        for name in names:
            if name not in existing_by_name:
                old = self._find_existing_char(name)
                ref = old.get("reference_image", "") if old else ""
                self.add_card(name, ref)

        self._relayout_cards()
        self._update_status()
        self.changed.emit()
        QMessageBox.information(
            self.window() or self,
            "已同步",
            f"已同步 {len(names)} 个角色：\n" + "、".join(names),
        )

    def _remove_card_silent(self, card: CharacterRefCard):
        if card in self._cards:
            self._cards.remove(card)
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self._relayout_cards()

    def apply_to_script(self, script: Optional[dict] = None) -> bool:
        """将面板数据写入 script['characters']。返回是否成功。"""
        target = script if script is not None else self._script
        if target is None:
            return False

        characters = []
        for card in self._cards:
            name = card.get_name()
            ref = card.get_reference_path()
            if not name and not ref:
                continue
            if not name:
                QMessageBox.warning(
                    self.window() or self,
                    "提示",
                    "有角色已上传图片但未填写角色名，请补全后再生成。",
                )
                return False
            if ref and not os.path.isfile(ref):
                QMessageBox.warning(
                    self.window() or self,
                    "提示",
                    f"角色「{name}」的参考图不存在：\n{ref}",
                )
                return False
            characters.append(card.to_character_dict(self._find_existing_char(name)))

        target["characters"] = characters
        self._update_status()
        return True

    def _on_card_changed(self):
        self._update_status()
        self.changed.emit()
        if self._script:
            self.apply_to_script(self._script)

    def _update_status(self):
        n = len(self._cards)
        with_img = sum(1 for c in self._cards if c.get_reference_path())
        self.status_label.setText(f"共 {n} 个角色位，已上传 {with_img} 张参考图")

    def has_any_reference(self) -> bool:
        return any(c.get_reference_path() for c in self._cards)

    def load_portraits_from_dir(self, portrait_dir: str) -> int:
        """
        从定妆照目录加载已生成的角色头像，自动匹配到对应角色卡片。
        返回匹配数量。
        """
        if not os.path.isdir(portrait_dir):
            return 0
        matched = 0
        for card in self._cards:
            name = card.get_name()
            if not name or card.get_reference_path():
                continue
            from core.character_portraits import safe_char_filename
            safe = safe_char_filename(name)
            path = os.path.join(portrait_dir, f"{safe}.png")
            if os.path.isfile(path) and os.path.getsize(path) > 2000:
                card.set_reference_image(path)
                matched += 1
        if matched > 0:
            self._update_status()
        return matched
