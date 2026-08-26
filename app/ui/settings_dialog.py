"""
Settings dialog for music visualizer engine.
Provides structured, card-based layout controls and live preview.
"""
from __future__ import annotations

from typing import Callable, Dict, Any, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QDoubleSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


def _make_card_frame(title: str = "", subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
    """Create a styled visual card container for layout settings."""
    frame = QFrame()
    frame.setObjectName("settingsCard")
    frame.setStyleSheet("""
        QFrame#settingsCard {
            background-color: #1a1b2e;
            border: 1px solid #2d314d;
            border-radius: 10px;
            padding: 10px;
        }
        QFrame#settingsCard:hover {
            border-color: #3f466e;
        }
    """)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 12)
    layout.setSpacing(8)

    if title:
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 4)
        title_label = QLabel(title)
        title_label.setStyleSheet("font_weight: bold; font-size: 13px; color: #7c8cff;")
        header_layout.addWidget(title_label)
        if subtitle:
            sub_label = QLabel(subtitle)
            sub_label.setStyleSheet("font-size: 11px; color: #727999;")
            header_layout.addWidget(sub_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

    return frame, layout


def _make_offset_spin(value: float) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(-50.0, 50.0)
    spin.setSingleStep(0.5)
    spin.setDecimals(1)
    spin.setSuffix("%")
    spin.setValue(float(value))
    spin.setStyleSheet("""
        QDoubleSpinBox {
            background: #121324;
            color: #d1d7ff;
            border: 1px solid #333859;
            border-radius: 4px;
            padding: 3px 6px;
        }
        QDoubleSpinBox:focus {
            border-color: #5c6cff;
        }
    """)
    return spin


def _make_scale_controls(initial_val: float) -> tuple[QHBoxLayout, QSlider, QDoubleSpinBox]:
    """Create a synchronized slider + double spinbox scale control."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)

    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(50, 200)
    slider.setValue(int(round(initial_val * 100)))
    slider.setStyleSheet("""
        QSlider::groove:horizontal {
            height: 4px;
            background: #252842;
            border-radius: 2px;
        }
        QSlider::sub-page:horizontal {
            background: #5c6cff;
            border-radius: 2px;
        }
        QSlider::handle:horizontal {
            background: #aab4ff;
            width: 14px;
            height: 14px;
            margin: -5px 0;
            border-radius: 7px;
        }
        QSlider::handle:horizontal:hover {
            background: #ffffff;
        }
    """)

    spin = QDoubleSpinBox()
    spin.setRange(0.50, 2.00)
    spin.setSingleStep(0.05)
    spin.setDecimals(2)
    spin.setSuffix("x")
    spin.setValue(initial_val)
    spin.setFixedWidth(70)
    spin.setStyleSheet("""
        QDoubleSpinBox {
            background: #121324;
            color: #d1d7ff;
            border: 1px solid #333859;
            border-radius: 4px;
            padding: 3px 4px;
        }
    """)

    updating = [False]

    def _on_slider(v: int):
        if updating[0]:
            return
        updating[0] = True
        spin.setValue(v / 100.0)
        updating[0] = False

    def _on_spin(v: float):
        if updating[0]:
            return
        updating[0] = True
        slider.setValue(int(round(v * 100)))
        updating[0] = False

    slider.valueChanged.connect(_on_slider)
    spin.valueChanged.connect(_on_spin)

    row.addWidget(slider, 1)
    row.addWidget(spin)
    return row, slider, spin


def _pair_widget(label1: str, spin1: QDoubleSpinBox, label2: str, spin2: QDoubleSpinBox) -> QWidget:
    row = QWidget()
    row_layout = QHBoxLayout(row)
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.setSpacing(6)
    row_layout.addWidget(QLabel(label1))
    row_layout.addWidget(spin1)
    row_layout.addWidget(QLabel(label2))
    row_layout.addWidget(spin2)
    return row


class SettingsDialog(QDialog):
    """Modern, card-based settings dialog with grouped controls."""

    def __init__(
        self,
        parent: Optional[QWidget],
        settings_data: Dict[str, Any],
        gpu_available: bool = False,
        render_backend: str = "cpu",
        on_live_update: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        super().__init__(parent)
        self.settings_data = settings_data
        self.gpu_available = gpu_available
        self.render_backend = render_backend
        self.on_live_update = on_live_update

        self.setWindowTitle("引擎与界面设置")
        self.resize(580, 560)
        self.setStyleSheet("""
            QDialog {
                background: #121222;
                color: #e1e4ff;
                font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
            }
            QLabel {
                color: #c4caef;
            }
            QCheckBox {
                color: #d8deff;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #424970;
                background: #181a2e;
            }
            QCheckBox::indicator:checked {
                background: #5c6cff;
                border-color: #7c8cff;
            }
        """)

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        # Tab Widget
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #292d47;
                border-radius: 8px;
                background: #151628;
            }
            QTabBar::tab {
                background: #1a1c30;
                color: #929bbd;
                padding: 8px 18px;
                font-size: 12px;
                font-weight: bold;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #272b4a;
                color: #ffffff;
                border-bottom: 2px solid #5c6cff;
            }
            QTabBar::tab:hover:!selected {
                background: #21243d;
                color: #c4caef;
            }
        """)
        main_layout.addWidget(tabs, 1)

        # Build Pages
        tabs.addTab(self._build_basic_page(), "⚙️ 基础与性能")
        tabs.addTab(self._build_layout_page(), "🎨 界面元素与布局")
        tabs.addTab(self._build_fonts_page(), "🔤 字体样式")

        # Dialog Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确认保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.setStyleSheet("""
            QPushButton {
                background-color: #272b4a;
                color: #e1e4ff;
                border: 1px solid #3c426e;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #353b66;
                border-color: #5c6cff;
            }
            QPushButton:pressed {
                background-color: #1e213b;
            }
        """)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

        # Hook live updates
        self._hook_signals()

    def _build_basic_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        card, card_layout = _make_card_frame("性能与渲染后端", "设置渲染帧率限制与硬件加速引擎")
        form = QFormLayout()
        form.setSpacing(12)

        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["60", "120", "144", "165", "No Limit"])
        current_fps = self.settings_data.get("fps", 60)
        self.fps_combo.setCurrentText("No Limit" if current_fps == 0 else str(current_fps))
        form.addRow("目标渲染帧率:", self.fps_combo)

        self.cb_fps = QCheckBox("在界面左上角显示 FPS 帧率计数")
        self.cb_fps.setChecked(self.settings_data.get("show_fps", True))
        form.addRow("", self.cb_fps)

        self.canvas_ratio_combo = QComboBox()
        self.canvas_ratio_combo.addItems(["16:9", "9:16"])
        self.canvas_ratio_combo.setCurrentText(self.settings_data.get("visual_canvas_ratio", "16:9"))
        form.addRow("画布长宽比例:", self.canvas_ratio_combo)

        self.render_backend_combo = QComboBox()
        self.render_backend_combo.addItem("CPU 渲染 (QPainter)", "cpu")
        self.render_backend_combo.addItem("GPU 硬件加速 (OpenGL)", "gpu")
        if not self.gpu_available:
            self.render_backend_combo.setItemData(1, 0, Qt.ItemDataRole.UserRole - 1)
            self.render_backend_combo.setToolTip("当前运行环境未检测到可用的 GPU/OpenGL 支持")
        self.render_backend_combo.setCurrentIndex(1 if self.render_backend == "gpu" and self.gpu_available else 0)
        form.addRow("渲染引擎后端:", self.render_backend_combo)

        combo_style = """
            QComboBox {
                background: #121324;
                color: #d1d7ff;
                border: 1px solid #333859;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QComboBox:focus { border-color: #5c6cff; }
            QComboBox::drop-down { border: none; }
        """
        self.fps_combo.setStyleSheet(combo_style)
        self.canvas_ratio_combo.setStyleSheet(combo_style)
        self.render_backend_combo.setStyleSheet(combo_style)

        card_layout.addLayout(form)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _build_layout_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # 1. Title Block Card
        title_card, title_layout = _make_card_frame("🎴 歌曲标题与曲目信息", "控制顶部歌曲名/艺术家的显示与平移")
        self.cb_top_title = QCheckBox("显示顶部歌曲标题")
        self.cb_top_title.setChecked(self.settings_data.get("show_track_title", True))
        title_layout.addWidget(self.cb_top_title)

        title_form = QFormLayout()
        title_form.setSpacing(8)

        title_scale_val = self.settings_data.get("module_scale_title", 1.0)
        title_scale_row, self.title_scale_slider, self.title_scale_spin = _make_scale_controls(title_scale_val)
        title_form.addRow("标题整体缩放:", title_scale_row)

        self.title_x_spin = _make_offset_spin(self.settings_data.get("layout_title_x", 0.0))
        self.title_y_spin = _make_offset_spin(self.settings_data.get("layout_title_y", 0.0))
        title_form.addRow("位置偏移微调:", _pair_widget("X", self.title_x_spin, "Y", self.title_y_spin))

        title_layout.addLayout(title_form)
        layout.addWidget(title_card)

        # 2. Lyrics Block Card
        lyrics_card, lyrics_layout = _make_card_frame("🎤 歌词面板", "控制右侧/中央动态歌词的尺寸与位置")
        self.cb_lyrics = QCheckBox("显示歌词面板")
        self.cb_lyrics.setChecked(self.settings_data.get("show_lyrics", False))
        lyrics_layout.addWidget(self.cb_lyrics)

        lyrics_form = QFormLayout()
        lyrics_form.setSpacing(8)

        lyrics_scale_val = self.settings_data.get("module_scale_lyrics", 1.0)
        lyrics_scale_row, self.lyrics_scale_slider, self.lyrics_scale_spin = _make_scale_controls(lyrics_scale_val)
        lyrics_form.addRow("歌词面板缩放:", lyrics_scale_row)

        self.lyrics_x_spin = _make_offset_spin(self.settings_data.get("layout_lyrics_x", 0.0))
        self.lyrics_y_spin = _make_offset_spin(self.settings_data.get("layout_lyrics_y", 0.0))
        lyrics_form.addRow("位置偏移微调:", _pair_widget("X", self.lyrics_x_spin, "Y", self.lyrics_y_spin))

        lyrics_layout.addLayout(lyrics_form)
        layout.addWidget(lyrics_card)

        # 3. HUD Panels Card
        hud_card, hud_layout = _make_card_frame("📊 数据仪表 (HUD)", "控制左下角与右下角音频状态参数面板")
        hud_toggles = QHBoxLayout()
        self.cb_left_hud = QCheckBox("显示左侧信息")
        self.cb_left_hud.setChecked(self.settings_data.get("show_left_hud", True))
        self.cb_right_hud = QCheckBox("显示右侧监控")
        self.cb_right_hud.setChecked(self.settings_data.get("show_right_hud", True))
        hud_toggles.addWidget(self.cb_left_hud)
        hud_toggles.addWidget(self.cb_right_hud)
        hud_toggles.addStretch()
        hud_layout.addLayout(hud_toggles)

        hud_form = QFormLayout()
        hud_form.setSpacing(8)

        hud_scale_val = self.settings_data.get("module_scale_left_hud", 1.0)
        hud_scale_row, self.hud_scale_slider, self.hud_scale_spin = _make_scale_controls(hud_scale_val)
        hud_form.addRow("HUD 整体缩放:", hud_scale_row)

        self.left_hud_x_spin = _make_offset_spin(self.settings_data.get("layout_left_hud_x", 0.0))
        self.left_hud_y_spin = _make_offset_spin(self.settings_data.get("layout_left_hud_y", 0.0))
        hud_form.addRow("左面板位置偏移:", _pair_widget("X", self.left_hud_x_spin, "Y", self.left_hud_y_spin))

        self.right_hud_x_spin = _make_offset_spin(self.settings_data.get("layout_right_hud_x", 0.0))
        self.right_hud_y_spin = _make_offset_spin(self.settings_data.get("layout_right_hud_y", 0.0))
        hud_form.addRow("右面板位置偏移:", _pair_widget("X", self.right_hud_x_spin, "Y", self.right_hud_y_spin))

        hud_layout.addLayout(hud_form)
        layout.addWidget(hud_card)

        # 4. Effect Core Card
        effect_card, effect_layout = _make_card_frame("⚛️ 视觉特效核心", "调整音频脉冲中心圈及调试参数")
        effect_form = QFormLayout()
        effect_form.setSpacing(8)

        effect_scale_val = self.settings_data.get("module_scale_effect", 1.0)
        effect_scale_row, self.effect_scale_slider, self.effect_scale_spin = _make_scale_controls(effect_scale_val)
        effect_form.addRow("特效核心半径缩放:", effect_scale_row)

        self.cb_dev_hud = QCheckBox("开启开发者模式 (HUD 显示完整 Visual DNA 极值)")
        self.cb_dev_hud.setChecked(self.settings_data.get("show_dev_hud", False))
        effect_form.addRow("", self.cb_dev_hud)

        effect_layout.addLayout(effect_form)
        layout.addWidget(effect_card)

        # Reset button
        reset_btn = QPushButton("🔄 一键恢复默认排版与尺寸")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #23253d;
                color: #aeb8ff;
                border: 1px solid #3c426e;
                border-radius: 6px;
                padding: 8px 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2e3357;
                color: #ffffff;
                border-color: #5c6cff;
            }
        """)
        reset_btn.clicked.connect(self._reset_layout_defaults)
        layout.addWidget(reset_btn)

        scroll.setWidget(page)
        return scroll

    def _build_fonts_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        card, card_layout = _make_card_frame("字体选择", "自定义歌曲名称与动态歌词的字体样式")
        form = QFormLayout()
        form.setSpacing(12)

        self.title_font_combo = QFontComboBox()
        self.title_font_combo.setCurrentFont(QFont(self.settings_data.get("title_font_family", "") or "Segoe UI"))
        form.addRow("歌曲名字体:", self.title_font_combo)

        self.artist_font_combo = QFontComboBox()
        self.artist_font_combo.setCurrentFont(QFont(self.settings_data.get("artist_font_family", "") or "Segoe UI"))
        form.addRow("艺术家字体:", self.artist_font_combo)

        self.lyric_original_font_combo = QFontComboBox()
        self.lyric_original_font_combo.setCurrentFont(
            QFont(
                self.settings_data.get("lyric_original_font_family", "")
                or self.settings_data.get("lyric_font_family", "")
                or "Microsoft YaHei UI"
            )
        )
        form.addRow("原文歌词字体:", self.lyric_original_font_combo)

        self.lyric_translation_font_combo = QFontComboBox()
        self.lyric_translation_font_combo.setCurrentFont(
            QFont(
                self.settings_data.get("lyric_translation_font_family", "")
                or self.settings_data.get("lyric_font_family", "")
                or "Microsoft YaHei UI"
            )
        )
        form.addRow("译文歌词字体:", self.lyric_translation_font_combo)

        combo_style = """
            QFontComboBox {
                background: #121324;
                color: #d1d7ff;
                border: 1px solid #333859;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QFontComboBox:focus { border-color: #5c6cff; }
        """
        self.title_font_combo.setStyleSheet(combo_style)
        self.artist_font_combo.setStyleSheet(combo_style)
        self.lyric_original_font_combo.setStyleSheet(combo_style)
        self.lyric_translation_font_combo.setStyleSheet(combo_style)

        card_layout.addLayout(form)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _reset_layout_defaults(self):
        """Reset all scale and offset spinboxes to default 1.0 / 0.0."""
        for spin in (
            self.title_x_spin,
            self.title_y_spin,
            self.lyrics_x_spin,
            self.lyrics_y_spin,
            self.left_hud_x_spin,
            self.left_hud_y_spin,
            self.right_hud_x_spin,
            self.right_hud_y_spin,
        ):
            spin.setValue(0.0)

        for spin in (
            self.title_scale_spin,
            self.lyrics_scale_spin,
            self.hud_scale_spin,
            self.effect_scale_spin,
        ):
            spin.setValue(1.0)

        if self.on_live_update:
            self.on_live_update(self.collect_settings())

    def collect_settings(self) -> Dict[str, Any]:
        """Collect all controls into a clean settings dictionary."""
        fps_text = self.fps_combo.currentText()
        fps_val = 0 if fps_text == "No Limit" else int(fps_text)
        selected_backend = self.render_backend_combo.currentData() or "cpu"

        hud_scale = float(self.hud_scale_spin.value())

        return {
            "fps": fps_val,
            "visual_canvas_ratio": self.canvas_ratio_combo.currentText(),
            "render_backend": selected_backend,
            "show_fps": self.cb_fps.isChecked(),
            "show_track_title": self.cb_top_title.isChecked(),
            "show_left_hud": self.cb_left_hud.isChecked(),
            "show_right_hud": self.cb_right_hud.isChecked(),
            "show_lyrics": self.cb_lyrics.isChecked(),
            "show_dev_hud": self.cb_dev_hud.isChecked(),
            "title_font_family": self.title_font_combo.currentFont().family(),
            "artist_font_family": self.artist_font_combo.currentFont().family(),
            "lyric_font_family": self.lyric_original_font_combo.currentFont().family(),
            "lyric_original_font_family": self.lyric_original_font_combo.currentFont().family(),
            "lyric_translation_font_family": self.lyric_translation_font_combo.currentFont().family(),
            "layout_title_x": float(self.title_x_spin.value()),
            "layout_title_y": float(self.title_y_spin.value()),
            "layout_artist_x": float(self.title_x_spin.value()),
            "layout_artist_y": float(self.title_y_spin.value()),
            "layout_lyrics_x": float(self.lyrics_x_spin.value()),
            "layout_lyrics_y": float(self.lyrics_y_spin.value()),
            "layout_left_hud_x": float(self.left_hud_x_spin.value()),
            "layout_left_hud_y": float(self.left_hud_y_spin.value()),
            "layout_right_hud_x": float(self.right_hud_x_spin.value()),
            "layout_right_hud_y": float(self.right_hud_y_spin.value()),
            "font_scale_title": float(self.title_scale_spin.value()),
            "font_scale_artist": float(self.title_scale_spin.value()),
            "font_scale_lyrics": float(self.lyrics_scale_spin.value()),
            "font_scale_hud": hud_scale,
            "font_scale_left_hud": hud_scale,
            "font_scale_right_hud": hud_scale,
            "module_scale_title": float(self.title_scale_spin.value()),
            "module_scale_lyrics": float(self.lyrics_scale_spin.value()),
            "module_scale_left_hud": hud_scale,
            "module_scale_right_hud": hud_scale,
            "module_scale_effect": float(self.effect_scale_spin.value()),
        }

    def _hook_signals(self):
        """Hook widget change signals for live preview."""
        if not self.on_live_update:
            return

        def _notify():
            self.on_live_update(self.collect_settings())

        for cb in (
            self.cb_fps,
            self.cb_top_title,
            self.cb_left_hud,
            self.cb_right_hud,
            self.cb_lyrics,
            self.cb_dev_hud,
        ):
            cb.toggled.connect(lambda _: _notify())

        for combo in (self.fps_combo, self.canvas_ratio_combo, self.render_backend_combo):
            combo.currentIndexChanged.connect(lambda _: _notify())

        for fcombo in (
            self.title_font_combo,
            self.artist_font_combo,
            self.lyric_original_font_combo,
            self.lyric_translation_font_combo,
        ):
            fcombo.currentFontChanged.connect(lambda _: _notify())

        for slider in (
            self.title_scale_slider,
            self.lyrics_scale_slider,
            self.hud_scale_slider,
            self.effect_scale_slider,
        ):
            slider.valueChanged.connect(lambda _: _notify())

        for spin in (
            self.title_scale_spin,
            self.lyrics_scale_spin,
            self.hud_scale_spin,
            self.effect_scale_spin,
            self.title_x_spin,
            self.title_y_spin,
            self.lyrics_x_spin,
            self.lyrics_y_spin,
            self.left_hud_x_spin,
            self.left_hud_y_spin,
            self.right_hud_x_spin,
            self.right_hud_y_spin,
        ):
            spin.valueChanged.connect(lambda _: _notify())
            spin.valueChanged.connect(lambda _: _notify())
