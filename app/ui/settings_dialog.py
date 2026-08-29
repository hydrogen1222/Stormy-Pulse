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
    QLineEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


def _make_card_frame(title: str = "", subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
    """Create a styled visual card container for layout settings."""
    frame = QFrame()
    frame.setObjectName("settingsCard")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 12)
    layout.setSpacing(8)

    if title:
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 4)
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        header_layout.addWidget(title_label)
        if subtitle:
            sub_label = QLabel(subtitle)
            sub_label.setObjectName("cardSubtitle")
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
    return spin


def _make_scale_controls(initial_val: float) -> tuple[QHBoxLayout, QSlider, QDoubleSpinBox]:
    """Create a synchronized slider + double spinbox scale control."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)

    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(50, 200)
    slider.setValue(int(round(initial_val * 100)))

    spin = QDoubleSpinBox()
    spin.setRange(0.50, 2.00)
    spin.setSingleStep(0.05)
    spin.setDecimals(2)
    spin.setSuffix("x")
    spin.setValue(float(initial_val))
    spin.setFixedWidth(70)

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

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        # Tab Widget
        tabs = QTabWidget()
        main_layout.addWidget(tabs, 1)

        # Build Pages
        tabs.addTab(self._build_basic_page(), "⚙️ 基础与性能")
        tabs.addTab(self._build_layout_page(), "🎨 界面元素与布局")
        tabs.addTab(self._build_fonts_page(), "🔤 字体样式")

        # Dialog Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确认保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

        # Hook live updates
        self._hook_signals()

        # Apply initial theme
        self.set_theme(self.settings_data.get("app_theme", "dark"))

    def set_theme(self, theme_name: str):
        """Apply dynamic high-contrast theme stylesheet to dialog itself."""
        self.is_light = (theme_name == "light")
        dlg_bg = "#f8fafc" if self.is_light else "#0e101f"
        dlg_fg = "#0f172a" if self.is_light else "#e1e4ff"
        chk_fg = "#1e293b" if self.is_light else "#d8deff"
        chk_bg = "#ffffff" if self.is_light else "#181a2e"
        chk_border = "#cbd5e1" if self.is_light else "#424970"

        pane_bg = "#ffffff" if self.is_light else "#151628"
        pane_border = "#e2e8f0" if self.is_light else "#292d47"
        tab_bg = "#f1f5f9" if self.is_light else "#1a1c30"
        tab_fg = "#64748b" if self.is_light else "#929bbd"
        tab_sel_bg = "#ffffff" if self.is_light else "#272b4a"
        tab_sel_fg = "#0f172a" if self.is_light else "#ffffff"

        card_bg = "#ffffff" if self.is_light else "#1a1b2e"
        card_border = "#e2e8f0" if self.is_light else "#2d314d"
        hover_border = "#cbd5e1" if self.is_light else "#3f466e"
        title_color = "#4f46e5" if self.is_light else "#7c8cff"
        sub_color = "#64748b" if self.is_light else "#727999"

        spin_bg = "#f8fafc" if self.is_light else "#121324"
        spin_fg = "#0f172a" if self.is_light else "#d1d7ff"
        spin_border = "#cbd5e1" if self.is_light else "#333859"

        groove_bg = "#e2e8f0" if self.is_light else "#252842"

        btn_bg = "#cbd5e1" if self.is_light else "#23253d"
        btn_fg = "#0f172a" if self.is_light else "#aeb8ff"
        btn_hover = "#94a3b8" if self.is_light else "#2e3357"
        btn_border = "#cbd5e1" if self.is_light else "#3c426e"

        combo_bg = "#f8fafc" if self.is_light else "#121324"
        combo_fg = "#0f172a" if self.is_light else "#d1d7ff"
        combo_border = "#cbd5e1" if self.is_light else "#333859"
        combo_drop_bg = "#ffffff" if self.is_light else "#181a2e"
        combo_sel_bg = "#6366f1" if self.is_light else "#333859"

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {dlg_bg};
                color: {dlg_fg};
                font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
            }}
            QLabel {{
                color: {dlg_fg};
            }}
            QCheckBox {{
                color: {chk_fg};
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid {chk_border};
                background: {chk_bg};
            }}
            QCheckBox::indicator:checked {{
                background: #6366f1;
                border-color: #4f46e5;
            }}

            QTabWidget::pane {{
                border: 1px solid {pane_border};
                background: {pane_bg};
                border-radius: 6px;
            }}
            QTabBar::tab {{
                background: {tab_bg};
                color: {tab_fg};
                padding: 10px 20px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
                font-weight: bold;
                border: 1px solid {pane_border};
                border-bottom: none;
            }}
            QTabBar::tab:selected {{
                background: {tab_sel_bg};
                color: {tab_sel_fg};
                border-bottom: 2px solid #6366f1;
            }}
            QTabBar::tab:hover:!selected {{
                background: {pane_border};
            }}

            QFrame#settingsCard {{
                background-color: {card_bg};
                border: 1px solid {card_border};
                border-radius: 10px;
                padding: 10px;
            }}
            QFrame#settingsCard:hover {{
                border-color: {hover_border};
            }}
            QLabel#cardTitle {{
                font-weight: bold;
                font-size: 13px;
                color: {title_color};
            }}
            QLabel#cardSubtitle {{
                font-size: 11px;
                color: {sub_color};
            }}

            QLineEdit, QDoubleSpinBox {{
                background: {spin_bg};
                color: {spin_fg};
                border: 1px solid {spin_border};
                border-radius: 4px;
                padding: 4px 8px;
            }}
            QLineEdit:focus, QDoubleSpinBox:focus {{
                border-color: #6366f1;
            }}

            QSlider::groove:horizontal {{
                height: 4px;
                background: {groove_bg};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: #6366f1;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }}
            QSlider::handle:horizontal:hover {{
                background: #4f46e5;
            }}
            QSlider::sub-page:horizontal {{
                background: #6366f1;
                border-radius: 2px;
            }}

            QPushButton {{
                background-color: {btn_bg};
                color: {btn_fg};
                border: 1px solid {btn_border};
                border-radius: 6px;
                padding: 8px 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {btn_hover};
                color: #ffffff;
                border-color: #6366f1;
            }}

            QComboBox, QFontComboBox {{
                background: {combo_bg};
                color: {combo_fg};
                border: 1px solid {combo_border};
                border-radius: 6px;
                padding: 5px 10px;
                padding-right: 28px;
                min-height: 22px;
            }}
            QComboBox:focus, QFontComboBox:focus {{
                border-color: #6366f1;
            }}
            QComboBox::drop-down, QFontComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 26px;
                border-left: 1px solid {combo_border};
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
                background-color: {tab_bg};
            }}
            QComboBox::drop-down:hover, QFontComboBox::drop-down:hover {{
                background-color: {pane_border};
            }}
            QComboBox::down-arrow, QFontComboBox::down-arrow {{
                width: 0;
                height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {combo_fg};
            }}
            QComboBox::down-arrow:hover, QFontComboBox::down-arrow:hover {{
                border-top: 6px solid #6366f1;
            }}
            QComboBox QAbstractItemView, QFontComboBox QAbstractItemView {{
                background-color: {combo_drop_bg};
                color: {combo_fg};
                selection-background-color: {combo_sel_bg};
                selection-color: #ffffff;
                border: 1px solid {combo_border};
                border-radius: 6px;
                padding: 4px;
                outline: none;
            }}
            QComboBox QAbstractItemView::item, QFontComboBox QAbstractItemView::item {{
                padding: 4px 8px;
                min-height: 24px;
            }}
        """)

    def _build_basic_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        card, card_layout = _make_card_frame("性能与渲染后端", "设置渲染帧率限制与硬件加速引擎")
        form = QFormLayout()
        form.setSpacing(12)

        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["30", "60", "120", "144", "165", "No Limit"])
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

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("深色模式 (Dark)", "dark")
        self.theme_combo.addItem("浅色模式 (Light)", "light")
        current_theme = self.settings_data.get("app_theme", "dark")
        self.theme_combo.setCurrentIndex(1 if current_theme == "light" else 0)
        form.addRow("界面外观主题:", self.theme_combo)

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
        title_card, title_layout = _make_card_frame("🎴 歌曲名称与艺术家", "分别控制顶部歌曲名称和艺术家的显示、大小缩放与位置微调")
        title_toggles = QHBoxLayout()
        self.cb_top_title = QCheckBox("显示歌曲名称")
        self.cb_top_title.setChecked(self.settings_data.get("show_track_title", True))
        self.cb_top_artist = QCheckBox("显示艺术家")
        self.cb_top_artist.setChecked(self.settings_data.get("show_track_artist", True))
        title_toggles.addWidget(self.cb_top_title)
        title_toggles.addWidget(self.cb_top_artist)
        title_toggles.addStretch()
        title_layout.addLayout(title_toggles)

        title_form = QFormLayout()
        title_form.setSpacing(8)

        self.custom_title_edit = QLineEdit()
        self.custom_title_edit.setPlaceholderText("留空则自动读取歌曲元数据（默认）")
        self.custom_title_edit.setText(self.settings_data.get("custom_track_title", ""))
        title_form.addRow("自定义歌曲名:", self.custom_title_edit)

        title_scale_val = self.settings_data.get("module_scale_title")
        if title_scale_val is None or title_scale_val == 1.0:
            title_scale_val = self.settings_data.get("font_scale_title", 1.0)
        title_scale_row, self.title_scale_slider, self.title_scale_spin = _make_scale_controls(title_scale_val)
        title_form.addRow("歌曲名称缩放:", title_scale_row)

        self.title_x_spin = _make_offset_spin(self.settings_data.get("layout_title_x", 0.0))
        self.title_y_spin = _make_offset_spin(self.settings_data.get("layout_title_y", 0.0))
        title_form.addRow("歌曲名称偏移:", _pair_widget("X", self.title_x_spin, "Y", self.title_y_spin))

        self.custom_artist_edit = QLineEdit()
        self.custom_artist_edit.setPlaceholderText("留空则自动读取歌曲元数据（默认）")
        self.custom_artist_edit.setText(self.settings_data.get("custom_track_artist", ""))
        title_form.addRow("自定义艺术家:", self.custom_artist_edit)

        artist_scale_val = self.settings_data.get("module_scale_artist")
        if artist_scale_val is None or artist_scale_val == 1.0:
            artist_scale_val = self.settings_data.get("font_scale_artist", 1.0)
        artist_scale_row, self.artist_scale_slider, self.artist_scale_spin = _make_scale_controls(artist_scale_val)
        title_form.addRow("艺术家缩放:", artist_scale_row)

        self.artist_x_spin = _make_offset_spin(self.settings_data.get("layout_artist_x", 0.0))
        self.artist_y_spin = _make_offset_spin(self.settings_data.get("layout_artist_y", 0.0))
        title_form.addRow("艺术家偏移:", _pair_widget("X", self.artist_x_spin, "Y", self.artist_y_spin))

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
        self.reset_btn = QPushButton("🔄 一键恢复默认排版与尺寸")
        self.reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_btn.setObjectName("resetBtn")
        self.reset_btn.clicked.connect(self._reset_layout_defaults)
        layout.addWidget(self.reset_btn)

        scroll.setWidget(page)
        return scroll

    def _build_fonts_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        card, card_layout = _make_card_frame("字体选择 (下拉列表与即时字形预览)", "点击下拉箭头挑选系统已安装字体，或直接输入名称快速定位")
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

        for combo in (
            self.title_font_combo,
            self.artist_font_combo,
            self.lyric_original_font_combo,
            self.lyric_translation_font_combo,
        ):
            combo.setFontFilters(QFontComboBox.FontFilter.AllFonts)
            combo.setMaxVisibleItems(16)

        card_layout.addLayout(form)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _reset_layout_defaults(self):
        """Reset all scale and offset spinboxes to default 1.0 / 0.0."""
        self.custom_title_edit.clear()
        self.custom_artist_edit.clear()

        for spin in (
            self.title_x_spin,
            self.title_y_spin,
            self.artist_x_spin,
            self.artist_y_spin,
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
            self.artist_scale_spin,
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
        title_scale = float(self.title_scale_spin.value())
        artist_scale = float(self.artist_scale_spin.value())

        return {
            "fps": fps_val,
            "visual_canvas_ratio": self.canvas_ratio_combo.currentText(),
            "render_backend": selected_backend,
            "app_theme": self.theme_combo.currentData() or "dark",
            "show_fps": self.cb_fps.isChecked(),
            "show_track_title": self.cb_top_title.isChecked(),
            "show_track_artist": self.cb_top_artist.isChecked(),
            "custom_track_title": self.custom_title_edit.text().strip(),
            "custom_track_artist": self.custom_artist_edit.text().strip(),
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
            "layout_artist_x": float(self.artist_x_spin.value()),
            "layout_artist_y": float(self.artist_y_spin.value()),
            "layout_lyrics_x": float(self.lyrics_x_spin.value()),
            "layout_lyrics_y": float(self.lyrics_y_spin.value()),
            "layout_left_hud_x": float(self.left_hud_x_spin.value()),
            "layout_left_hud_y": float(self.left_hud_y_spin.value()),
            "layout_right_hud_x": float(self.right_hud_x_spin.value()),
            "layout_right_hud_y": float(self.right_hud_y_spin.value()),
            "font_scale_title": title_scale,
            "font_scale_artist": artist_scale,
            "font_scale_lyrics": float(self.lyrics_scale_spin.value()),
            "font_scale_hud": hud_scale,
            "font_scale_left_hud": hud_scale,
            "font_scale_right_hud": hud_scale,
            "module_scale_title": title_scale,
            "module_scale_artist": artist_scale,
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
            self.cb_top_artist,
            self.cb_left_hud,
            self.cb_right_hud,
            self.cb_lyrics,
            self.cb_dev_hud,
        ):
            cb.toggled.connect(lambda _: _notify())

        self.custom_title_edit.textChanged.connect(lambda _: _notify())
        self.custom_artist_edit.textChanged.connect(lambda _: _notify())

        for combo in (self.fps_combo, self.canvas_ratio_combo, self.render_backend_combo):
            combo.currentIndexChanged.connect(lambda _: _notify())

        def _on_theme_changed():
            theme_val = self.theme_combo.currentData() or "dark"
            self.set_theme(theme_val)
            _notify()

        self.theme_combo.currentIndexChanged.connect(lambda _: _on_theme_changed())

        for fcombo in (
            self.title_font_combo,
            self.artist_font_combo,
            self.lyric_original_font_combo,
            self.lyric_translation_font_combo,
        ):
            fcombo.currentFontChanged.connect(lambda _: _notify())

        for slider in (
            self.title_scale_slider,
            self.artist_scale_slider,
            self.lyrics_scale_slider,
            self.hud_scale_slider,
            self.effect_scale_slider,
        ):
            slider.valueChanged.connect(lambda _: _notify())

        for spin in (
            self.title_scale_spin,
            self.artist_scale_spin,
            self.lyrics_scale_spin,
            self.hud_scale_spin,
            self.effect_scale_spin,
            self.title_x_spin,
            self.title_y_spin,
            self.artist_x_spin,
            self.artist_y_spin,
            self.lyrics_x_spin,
            self.lyrics_y_spin,
            self.left_hud_x_spin,
            self.left_hud_y_spin,
            self.right_hud_x_spin,
            self.right_hud_y_spin,
        ):
            spin.valueChanged.connect(lambda _: _notify())
