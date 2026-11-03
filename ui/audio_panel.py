"""Правая панель акустического анализатора: Live FFT Спектр и 2D-Спектрограмма."""
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from core.defaults import AUDIO_PROFILE
from core.audio_engine import LIMIT_FREQ_MIN
from ui.viewboxes import FFTFilterViewBox, SpectrogramTimelineViewBox
from ui.styles import (
    create_timeline_cursor, SPINBOX_CLEAN_QSS, BTN_CYAN_QSS, BTN_GREEN_QSS,
    SPLITTER_VERTICAL_QSS, PEN_AXIS, PEN_AXIS_TEXT, AXIS_LABEL_STYLE,
    STATUS_LABEL_STYLE, CONTROLS_LABEL_STYLE, COLOR_FFT_CURVE, COLOR_PEAK
)
from core.texts import (
    CHART_TITLE_3, CHART_TITLE_4, AXIS_LABEL_FREQ, AXIS_UNIT_HZ,
    AXIS_LABEL_SPL, AXIS_UNIT_DB, AXIS_LABEL_TIME, AXIS_UNIT_S,
    BTN_PLAY, LBL_BOOST, SUFFIX_DB, BTN_RENDER_VIEW, BTN_SCALE_LOG,
    LBL_Y_MIN, LBL_Y_MAX
)


class CleanLogFrequencyAxis(pg.AxisItem):
    """Шкала частот с автоматическим переключением в полный формат герц при сильном зуме."""
    def __init__(self, analyzer_ref=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.analyzer = analyzer_ref
        self.enableAutoSIPrefix(False)

    def tickStrings(self, values, scale, spacing):
        """Форматирует метки частот: 'k' в обзоре и точные герцы при глубоком приближении."""
        strings = []
        is_lin = hasattr(self, 'analyzer') and self.analyzer and getattr(self.analyzer, 'freq_scale_mode', 'Log') == "Linear"
        
        view_range = self.range
        span = view_range[1] - view_range[0] if view_range and len(view_range) == 2 else 1000.0
        is_deep_zoom = span < 3000.0 if is_lin else span < 0.8

        for val in values:
            hz = float(val) if is_lin else (10.0 ** val)
            if is_deep_zoom:
                strings.append(f"{hz:.0f}" if hz >= 1000 else (f"{hz:.1f}" if hz < 100 else f"{hz:.0f}"))
            else:
                if hz >= 1000:
                    k_val = hz / 1000.0
                    strings.append(f"{round(k_val)}k" if abs(k_val - round(k_val)) < 0.05 else f"{k_val:.1f}k")
                else:
                    strings.append(f"{round(hz)}")
        return strings


class AudioPanel(QtWidgets.QWidget):
    """Виджет правой панели со спектром Live FFT, спектрограммой и тулбаром DAW."""
    def __init__(self, parent_analyzer):
        super().__init__()
        self.analyzer = parent_analyzer
        self.setMinimumWidth(360)
        self.init_ui()

    def init_ui(self):
        """Сборка графиков и тулбара панели аудио."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Вертикальный сплиттер между графиками FFT и 2D-Спектрограммы
        self.v_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.v_splitter.setChildrenCollapsible(False)
        self.v_splitter.setStyleSheet(SPLITTER_VERTICAL_QSS)

        # 1. Верхний график: Live FFT Спектр
        self.freq_axis = CleanLogFrequencyAxis(self.analyzer, orientation='bottom')
        self.freq_axis.setPen(PEN_AXIS)
        self.freq_axis.setTextPen(PEN_AXIS_TEXT)
        self.freq_axis.setLabel(AXIS_LABEL_FREQ, units=AXIS_UNIT_HZ, **AXIS_LABEL_STYLE)

        self.fft_vb = FFTFilterViewBox(self.analyzer)
        self.plot_fft = pg.PlotWidget(viewBox=self.fft_vb, axisItems={'bottom': self.freq_axis})
        self.plot_fft.showGrid(x=True, y=True, alpha=0.18)
        self.plot_fft.setYRange(-10.0, 40.0, padding=0)
        
        ax_fft_l = self.plot_fft.getAxis('left')
        ax_fft_l.setPen(PEN_AXIS)
        ax_fft_l.setTextPen(PEN_AXIS_TEXT)
        self.plot_fft.setLabel('left', AXIS_LABEL_SPL, units=AXIS_UNIT_DB, **AXIS_LABEL_STYLE)
        self.plot_fft.setTitle(CHART_TITLE_3, justify='left')

        self.fft_curve = self.plot_fft.plot(pen=pg.mkPen(color=COLOR_FFT_CURVE, width=2))
        self.peak_scatter = self.plot_fft.plot(pen=None, symbol='x', symbolSize=12, symbolPen=pg.mkPen(COLOR_PEAK, width=2.5))
        self.peak_text_items = []
        for _ in range(16):
            txt = pg.TextItem("", color=COLOR_PEAK, anchor=(0.5, 1.2))
            txt.setFont(QtGui.QFont("Segoe UI", 9, QtGui.QFont.Weight.Bold))
            self.plot_fft.addItem(txt)
            self.peak_text_items.append(txt)

        nyq = (self.analyzer.engine.sample_rate / 2.0) if self.analyzer.engine else 8000.0
        self.plot_fft.setXRange(np.log10(LIMIT_FREQ_MIN), np.log10(nyq), padding=0)
        self.v_splitter.addWidget(self.plot_fft)

        # 2. Нижний график: 2D Спектрограмма
        self.spec_vb = SpectrogramTimelineViewBox(self.analyzer)
        self.plot_spec = pg.PlotWidget(viewBox=self.spec_vb)
        self.plot_spec.showGrid(x=True, y=True, alpha=0.18)
        
        ax_spec_l = self.plot_spec.getAxis('left')
        ax_spec_l.setPen(PEN_AXIS)
        ax_spec_l.setTextPen(PEN_AXIS_TEXT)
        self.plot_spec.setLabel('left', AXIS_LABEL_FREQ, units=AXIS_UNIT_HZ, **AXIS_LABEL_STYLE)

        ax_spec_b = self.plot_spec.getAxis('bottom')
        ax_spec_b.setPen(PEN_AXIS)
        ax_spec_b.setTextPen(PEN_AXIS_TEXT)
        self.plot_spec.setLabel('bottom', AXIS_LABEL_TIME, units=AXIS_UNIT_S, **AXIS_LABEL_STYLE)
        self.plot_spec.setTitle(CHART_TITLE_4, justify='left')
        
        self.img_overview = pg.ImageItem()
        self.img_overview.setZValue(1)
        self.plot_spec.addItem(self.img_overview)

        self.img_highres = pg.ImageItem()
        self.img_highres.setZValue(2)
        self.plot_spec.addItem(self.img_highres)

        self.cursor_line_audio = create_timeline_cursor()
        self.plot_spec.addItem(self.cursor_line_audio, ignoreBounds=True)
        self.v_splitter.addWidget(self.plot_spec)

        self.v_splitter.setSizes([5000, 5000])
        layout.addWidget(self.v_splitter, stretch=1)

        # 3. Нижняя панель управления аудио
        controls_layout = QtWidgets.QHBoxLayout()
        controls_layout.setContentsMargins(2, 2, 2, 2)
        controls_layout.setSpacing(6)

        self.btn_play = QtWidgets.QPushButton(BTN_PLAY)
        self.btn_play.setFixedSize(68, 26)
        self.btn_play.setStyleSheet(BTN_GREEN_QSS)
        self.btn_play.clicked.connect(self.analyzer.toggle_play)
        controls_layout.addWidget(self.btn_play)

        lbl_boost = QtWidgets.QLabel(LBL_BOOST)
        lbl_boost.setStyleSheet(CONTROLS_LABEL_STYLE)
        controls_layout.addWidget(lbl_boost)

        self.spin_boost = QtWidgets.QDoubleSpinBox()
        self.spin_boost.setRange(0, 100)
        self.spin_boost.setValue(30.0)
        self.spin_boost.setSingleStep(5)
        self.spin_boost.setSuffix(SUFFIX_DB)
        self.spin_boost.setFixedWidth(68)
        self.spin_boost.setStyleSheet(SPINBOX_CLEAN_QSS)
        self.spin_boost.valueChanged.connect(self.analyzer.on_boost_changed)
        controls_layout.addWidget(self.spin_boost)

        self.btn_render = QtWidgets.QPushButton(BTN_RENDER_VIEW)
        self.btn_render.setFixedSize(88, 26)
        self.btn_render.setStyleSheet(BTN_GREEN_QSS)
        self.btn_render.clicked.connect(self.analyzer.render_current_view)
        controls_layout.addWidget(self.btn_render)

        self.btn_scale = QtWidgets.QPushButton(BTN_SCALE_LOG)
        self.btn_scale.setFixedSize(78, 26)
        self.btn_scale.setStyleSheet(BTN_CYAN_QSS)
        self.btn_scale.clicked.connect(self.analyzer.toggle_freq_scale)
        controls_layout.addWidget(self.btn_scale)

        lbl_ymin = QtWidgets.QLabel(LBL_Y_MIN)
        lbl_ymin.setStyleSheet(CONTROLS_LABEL_STYLE)
        controls_layout.addWidget(lbl_ymin)

        self.spin_ymin = QtWidgets.QSpinBox()
        self.spin_ymin.setRange(int(AUDIO_PROFILE["limit_db_min"]), int(AUDIO_PROFILE["limit_db_max"]))
        self.spin_ymin.setValue(-10)
        self.spin_ymin.setFixedWidth(44)
        self.spin_ymin.setStyleSheet(SPINBOX_CLEAN_QSS)
        self.spin_ymin.valueChanged.connect(self.on_fft_yrange_changed)
        controls_layout.addWidget(self.spin_ymin)

        lbl_ymax = QtWidgets.QLabel(LBL_Y_MAX)
        lbl_ymax.setStyleSheet(CONTROLS_LABEL_STYLE)
        controls_layout.addWidget(lbl_ymax)

        self.spin_ymax = QtWidgets.QSpinBox()
        self.spin_ymax.setRange(int(AUDIO_PROFILE["limit_db_min"]), int(AUDIO_PROFILE["limit_db_max"]))
        self.spin_ymax.setValue(40)
        self.spin_ymax.setFixedWidth(44)
        self.spin_ymax.setStyleSheet(SPINBOX_CLEAN_QSS)
        self.spin_ymax.valueChanged.connect(self.on_fft_yrange_changed)
        controls_layout.addWidget(self.spin_ymax)

        controls_layout.addStretch()

        self.lbl_audio_status = QtWidgets.QLabel("")
        self.lbl_audio_status.setFixedHeight(30)
        self.lbl_audio_status.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.lbl_audio_status.setStyleSheet(STATUS_LABEL_STYLE)
        controls_layout.addWidget(self.lbl_audio_status, stretch=1)

        layout.addLayout(controls_layout)

    def on_fft_yrange_changed(self):
        """Синхронизирует введенные пределы Y Min / Y Max с графиком FFT."""
        ymin = self.spin_ymin.value()
        ymax = self.spin_ymax.value()
        if ymin < ymax:
            self.plot_fft.setYRange(ymin, ymax, padding=0)